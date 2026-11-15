#!/usr/bin/env python3
"""Task 31.6 census: lint's corpus against the ingest's corpus, and the stem / project order.

`corpus_diff.py <project-root> <lint-scope-path>... [--memory-dir <dir>]...`

Read-only, no store. Run from the project root with `scripts/lint-gmd.sh`'s scope.

LINT CORPUS: the GMD docs `tools/gmd/lint.py` keeps for those paths. INGEST CORPUS: every file
under `<project-root>` the ingest walk includes (`GMD_EXTS`, `should_ignore`) that the strict
parser (`parse_gmd(path)`) reads as authored GMD, plus the memory dirs as the bridge parses them.

Reports: docs in each corpus and in the difference; ids and stems that are unique among lint's
docs and shared in the ingest corpus (a ref through one resolves for lint and is ambiguous for
an ingest-side resolver that sees every ingested doc); how many cross-doc refs use such an id or
stem; and the refs whose target differs between the orders `id -> stem -> project` (lint today)
and `id -> project -> stem`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from refmatrix.ingest import GMD_EXTS, should_ignore  # noqa: E402
from refmatrix.ingest_gmd import parse_gmd  # noqa: E402


def _load_lint():
    spec = importlib.util.spec_from_file_location("_cd_lint", ROOT / "tools" / "gmd" / "lint.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_cd_lint"] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    proot = Path(argv[0]).resolve()
    paths: list[str] = []
    mem: list[str] = []
    it = iter(argv[1:])
    for a in it:
        (mem if a == "--memory-dir" else paths).append(next(it) if a == "--memory-dir" else a)
    lint = _load_lint()
    files = lint.collect_files(paths)
    ignore = lint.load_config(proot).get("ignore") or []
    if ignore:
        files = lint.collect_files(paths, ignore)
    mem_files = lint.collect_files(mem) if mem else []

    ldocs: dict = {}
    for f in [*files, *mem_files]:
        doc, _i = lint.parse_doc(f)
        if doc.gmd_version is not None:
            ldocs.setdefault(doc.doc_id or f.stem, doc)
    lint_paths = {d.path.resolve() for d in ldocs.values()}

    ing: dict[Path, str] = {}
    for d, dirs, names in os.walk(proot):
        dirs[:] = sorted(x for x in dirs if x != ".git")
        for name in sorted(names):
            p = Path(d) / name
            if p.suffix in GMD_EXTS and not should_ignore(p, proot):
                try:
                    gd = parse_gmd(p)
                except Exception as e:
                    print(f"parse_gmd raised on {p}: {type(e).__name__}: {e}", file=sys.stderr)
                    continue
                if gd is not None:
                    ing[p.resolve()] = gd.doc_id
    for f in mem_files:
        gd = parse_gmd(f, lenient=True, memory_ids=True)
        if gd is not None:
            ing[f.resolve()] = gd.doc_id

    only_ing = sorted(p for p in ing if p not in lint_paths)
    only_lint = sorted(p for p in lint_paths if p not in ing)
    print(f"lint corpus: {len(lint_paths)} GMD docs; ingest corpus: {len(ing)} authored GMD "
          f"docs; ingest-only: {len(only_ing)}; lint-only: {len(only_lint)}")
    by_dir = Counter(str(p.relative_to(proot)).split("/")[0] if proot in p.parents else "(memory)"
                     for p in only_ing)
    print("ingest-only docs by top directory: "
          + ", ".join(f"{k} {n}" for k, n in by_dir.most_common()))

    def owners(pathset):
        ids, stems = defaultdict(list), defaultdict(list)
        for p in pathset:
            ids[ing.get(p) or p.stem].append(p)
            stems[p.stem].append(p)
        return ids, stems
    l_ids, l_stems = owners([p for p in lint_paths if p in ing])
    i_ids, i_stems = owners(list(ing))
    id_clash = sorted(k for k, v in i_ids.items() if len(v) > 1 and len(l_ids.get(k, [])) == 1)
    stem_clash = sorted(k for k, v in i_stems.items() if len(v) > 1 and len(l_stems.get(k, [])) == 1)
    print(f"ids unique for lint, shared in the ingest corpus: {len(id_clash)} {id_clash[:12]}")
    print(f"stems unique for lint, shared in the ingest corpus: {len(stem_clash)} {stem_clash[:12]}")

    by = dict(ldocs)
    stem_only = {}
    for d in ldocs.values():
        if d.path.stem not in by and d.path.stem not in stem_only:
            stem_only[d.path.stem] = d
    refs_id_clash = refs_stem_clash = order_diff = both = 0
    amb_stem_refs = Counter()
    lstem_n = Counter(d.path.stem for d in ldocs.values())
    proj_cache: dict = {}
    for doc in ldocs.values():
        pdir = doc.path.parent
        if pdir not in proj_cache:
            proj_cache[pdir] = lint.project_name(doc.path)
        project = proj_cache[pdir]
        for _line, _raw, tdoc, _anchor, _in_rel in doc.refs:
            if tdoc is None:
                continue
            if tdoc in ldocs:
                if tdoc in id_clash:
                    refs_id_clash += 1
                continue
            s = stem_only.get(tdoc)
            p = ldocs.get(f"{project}/{tdoc}") if project else None
            if s is not None and p is not None:
                both += 1
                if s is not p:
                    order_diff += 1
            if s is not None:
                if tdoc in stem_clash:
                    refs_stem_clash += 1
                if lstem_n[tdoc] > 1 and p is None:
                    amb_stem_refs[tdoc] += 1
    print(f"refs through an id that is shared in the ingest corpus: {refs_id_clash}")
    print(f"refs through a stem that is shared in the ingest corpus only: {refs_stem_clash}")
    print(f"refs where both the stem and the project form hit: {both}; of them a different "
          f"doc by the two orders: {order_diff}")
    print(f"refs resolved only through a stem several lint docs share: "
          f"{sum(amb_stem_refs.values())} {dict(amb_stem_refs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
