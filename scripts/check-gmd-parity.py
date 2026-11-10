#!/usr/bin/env python3
"""Corpus-wide parity: lint's registered anchor set == the store ingester's node-id set.

WHY (bug-179, 2026-11-09). `tools/gmd/lint.py` registered every `{#id}` on a line; the store
ingester (`refmatrix.ingest_gmd.parse_gmd`) registers only the first. A compaction packed 200
ids onto 12 lines of `workflow/bullshit/IMPRESSIONS.md`, lint passed with 0 errors, and 188 ids
resolved to `(unknown symbol)`. It was the second time the two parsers disagreed (bug-036 was the
first), and bug-036's one-file parity test lives in the suite, which nobody runs on a docs-only
commit. So the invariant runs HERE, called by `scripts/lint-gmd.sh` — the gate that does run on
a docs commit — and `tests/test_bug179_anchor_parity.py` calls the same `find_divergences`, so
the suite and the gate cannot drift apart.

Scope is whatever the caller passes (files or directories). A file lint does not treat as GMD is
skipped, as lint skips it. Memory dirs are parsed the way the bridge parses them
(`parse_gmd(..., lenient=True, memory_ids=True)`, `ingest_gmd_paths(as_memory=True)`). Ids
excluded from the comparison: `__root__` (the ingester's synthetic doc node) and the ingester's
auto `_hN` / `_hN_M` heading ids, which lint never registers by design.

This script is refmatrix-specific (it imports `refmatrix`), so it lives in `scripts/`, not in the
vendored `tools/gmd/` mirror (spec #d6), and runs under `.venv-eval/bin/python`.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The checkout's own `src/` first: the gate verifies THIS tree's ingester, never whatever
# `refmatrix` the interpreter happens to have installed (the deploy venv is an editable install
# of a different tree).
sys.path.insert(0, str(ROOT / "src"))

from refmatrix.ingest_gmd import parse_gmd  # noqa: E402

LINT_PATH = ROOT / "tools" / "gmd" / "lint.py"
_AUTO_ID = re.compile(r"^_h\d+(?:_\d+)?$")

Divergence = tuple[Path, set, set]  # (path, lint-only ids, ingester-only ids)


def _load_lint():
    if not LINT_PATH.is_file():
        raise FileNotFoundError(f"gmd lint not found at {LINT_PATH}")
    name = "_gmd_parity_lint"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, LINT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve their module by name
    spec.loader.exec_module(mod)
    return mod


def _files(lint, targets: list[Path]) -> list[Path]:
    """Expand files/dirs exactly as lint does, honouring `.gmd/config.yml` `ignore:`."""
    strs = [str(t) for t in targets]
    files = lint.collect_files(strs)
    if files:
        root = lint._repo_root(files[0])
        if root is not None:
            ignore = lint.load_config(root).get("ignore") or []
            if ignore:
                files = lint.collect_files(strs, ignore)
    return files


def _ingest_ids(path: Path, *, memory: bool) -> set[str] | None:
    doc = (parse_gmd(path, lenient=True, memory_ids=True) if memory else parse_gmd(path))
    if doc is None:
        return None
    return {n.id for n in doc.nodes if n.id != "__root__" and not _AUTO_ID.match(n.id)}


def scan(paths, memory_dirs=()) -> tuple[list[Divergence], list[tuple[Path, str]]]:
    """Return (divergences, failures). A failure is a file either parser raised on: it is
    reported, never skipped."""
    lint = _load_lint()
    divergences: list[Divergence] = []
    failures: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    groups = [(False, [Path(p) for p in paths]), (True, [Path(p) for p in memory_dirs])]
    for memory, targets in groups:
        if not targets:
            continue
        for f in _files(lint, targets):
            key = f.resolve()
            if key in seen:
                continue
            seen.add(key)
            try:
                ldoc, _issues = lint.parse_doc(f)
            except Exception as e:  # lint reports this as parse-fail; parity reports it too
                failures.append((f, f"lint.parse_doc raised {type(e).__name__}: {e}"))
                continue
            if ldoc.gmd_version is None:
                continue  # not GMD to lint (and lint says so itself, as an error or opt-out)
            lint_ids = set(ldoc.node_ids)
            try:
                ing = _ingest_ids(f, memory=memory)
            except Exception as e:
                failures.append((f, f"parse_gmd raised {type(e).__name__}: {e}"))
                continue
            # Lint treats the file as GMD and the ingester does not: every lint id is then
            # absent from the store, which is a divergence, not a skip.
            ing_ids = ing if ing is not None else set()
            if lint_ids != ing_ids:
                divergences.append((f, lint_ids - ing_ids, ing_ids - lint_ids))
    return divergences, failures


def find_divergences(paths, memory_dirs=()) -> list[Divergence]:
    """`[(path, lint_only_ids, ingester_only_ids), ...]` over every GMD doc in scope; empty
    means parity. Raises if either parser fails on a file, so a crash is never a pass."""
    divergences, failures = scan(paths, memory_dirs)
    if failures:
        raise RuntimeError("gmd parity: parse failures: " + "; ".join(
            f"{p}: {msg}" for p, msg in failures))
    return divergences


def _parse_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    paths: list[str] = []
    mem: list[str] = []
    it = iter(argv)
    for a in it:
        if a == "--memory-dir":
            try:
                mem.append(next(it))
            except StopIteration:
                raise SystemExit("check-gmd-parity: --memory-dir needs a path")
        else:
            paths.append(a)
    return paths, mem


def main(argv: list[str]) -> int:
    """`check-gmd-parity.py <path>... [--memory-dir <dir>]...`; 0 = parity, 1 = divergence or
    parse failure, 2 = usage."""
    paths, mem = _parse_argv(argv)
    if not paths and not mem:
        print("usage: check-gmd-parity.py <path>... [--memory-dir <dir>]...", file=sys.stderr)
        return 2
    divergences, failures = scan(paths, mem)
    for p, lint_only, ing_only in divergences:
        print(f"{p}: error: [anchor-parity] lint and the store ingester disagree — "
              f"lint-only: {sorted(lint_only) or '-'}; ingester-only: {sorted(ing_only) or '-'}")
    for p, msg in failures:
        print(f"{p}: error: [parity-parse-fail] {msg}")
    n = len(divergences) + len(failures)
    print(f"gmd parity: {len(divergences)} divergent doc(s), {len(failures)} parse failure(s)",
          file=sys.stderr if n else sys.stdout)
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
