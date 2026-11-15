#!/usr/bin/env python3
"""Task 31.1 census: how many markdown files carry a non-string frontmatter `id:` / `title:`.

`frontmatter_census.py <repo-root>... [--memory-dir <dir>]...`

Read-only. Walks each root the way the code+docs ingest does (`GMD_EXTS`, `should_ignore`
judged against the root) and each memory dir the way the bridge does (every `*.md`), reads each
file with the ingester's OWN `_parse_frontmatter` (this checkout's `src/`), and counts:

  fm            files with a frontmatter block
  id_list       `id` parsed as a NON-EMPTY list  (the bug-244 raising shape)
  id_empty      `id` parsed as `[]` (an empty value, or `id: []`): falls back to stem/path today
  title_list    `title` parsed as a non-empty list
  title_empty   `title` parsed as `[]`
  yaml_nonstr   `id:` / `title:` whose raw scalar a YAML reader would type as non-string
                (int, float, bool, null, date) -- the minimal parser reads these as strings, so
                they do not raise; counted for information
  nested_id     an INDENTED `id:` / `title:` line inside the frontmatter (a `metadata:` child):
                the minimal parser flattens it onto the top-level key

Opens no store. Prints counts per root; `--paths` also prints the files of every non-zero class
(local use only: fleet paths are not committed).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from refmatrix.ingest import GMD_EXTS, should_ignore  # noqa: E402
from refmatrix.ingest_gmd import _parse_frontmatter  # noqa: E402

_NONSTR = re.compile(
    r"^(?:[-+]?\d+(?:\.\d+)?|true|false|yes|no|on|off|null|~|\d{4}-\d{2}-\d{2}(?:[Tt ][0-9:.+-]+Z?)?)$", re.I)
CLASSES = ("fm", "id_list", "id_empty", "title_list", "title_empty", "yaml_nonstr", "nested_id")


def _walk(root: Path, memory: bool):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x != ".git")
        for name in sorted(files):
            p = Path(d) / name
            if memory:
                if p.suffix == ".md":
                    yield p
            elif p.suffix in GMD_EXTS and not should_ignore(p, root):
                yield p


def census(root: Path, memory: bool) -> tuple[dict, dict, int, int]:
    counts = {k: 0 for k in CLASSES}
    hits: dict[str, list[str]] = {k: [] for k in CLASSES}
    files = unreadable = 0
    for p in _walk(root, memory):
        files += 1
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            unreadable += 1
            continue
        fm, body_start = _parse_frontmatter(lines)
        if not body_start:
            continue
        counts["fm"] += 1
        for key in ("id", "title"):
            v = fm.get(key)
            if isinstance(v, list):
                cls = f"{key}_list" if v else f"{key}_empty"
                counts[cls] += 1
                hits[cls].append(str(p))
            elif isinstance(v, str) and _NONSTR.match(v.strip()):
                counts["yaml_nonstr"] += 1
                hits["yaml_nonstr"].append(f"{p}: {key}: {v}")
        for raw in lines[1:max(body_start - 1, 1)]:
            if raw[:1] in (" ", "\t") and re.match(r"\s+(id|title)\s*:", raw):
                counts["nested_id"] += 1
                hits["nested_id"].append(f"{p}: {raw.strip()}")
                break
    return counts, hits, files, unreadable


def main(argv: list[str]) -> int:
    show = "--paths" in argv
    args = [a for a in argv if a != "--paths"]
    targets: list[tuple[Path, bool]] = []
    it = iter(args)
    for a in it:
        if a == "--memory-dir":
            targets.append((Path(next(it)).expanduser(), True))
        else:
            targets.append((Path(a).expanduser(), False))
    if not targets:
        print(__doc__, file=sys.stderr)
        return 2
    total = {k: 0 for k in CLASSES}
    tfiles = 0
    print("root\tkind\tfiles\tunreadable\t" + "\t".join(CLASSES))
    for root, memory in targets:
        if not root.is_dir():
            print(f"{root}\tMISSING")
            continue
        counts, hits, files, unreadable = census(root.resolve(), memory)
        tfiles += files
        for k in CLASSES:
            total[k] += counts[k]
        print(f"{root}\t{'memory' if memory else 'repo'}\t{files}\t{unreadable}\t"
              + "\t".join(str(counts[k]) for k in CLASSES))
        if show:
            for k in CLASSES[1:]:
                for h in hits[k]:
                    print(f"    {k}: {h}")
    print(f"TOTAL\t-\t{tfiles}\t-\t" + "\t".join(str(total[k]) for k in CLASSES))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
