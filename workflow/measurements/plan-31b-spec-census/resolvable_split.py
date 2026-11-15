#!/usr/bin/env python3
"""Task 31.2, plan-31 D14: split the orphaned learned evidence rows of a catalog into
RESOLVABLE (re-attached) and NOT (deleted with a manifest), by the spec's match rule.

`resolvable_split.py <catalog-copy> <tree-root>`

Read-only: a COPY of `catalog.read.duckdb`, opened `read_only=True`; files under the tree
root are stat'ed, never written.

A learned orphan (`detail` starts `learned from grep `, `entity_id` names no entity) is
RESOLVABLE when all three hold:
  C  its concept row exists and is named `query/...`;
  E  exactly one entity exists with the concept's partition, the kind the learner gives the
     file (`code` for the learner's code suffixes, else `doc`) and `name` = the row's `file`;
  F  the file is on disk (the row's `file`, relative to the tree root unless absolute).
Every other learned orphan is NOT resolvable; the first failing condition, in the order
C, E, F, is its reason.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

CODE_SUFFIXES = {".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php",
                 ".cpp", ".c", ".h", ".hpp", ".pseudo"}  # daemon._learn_grep_hits


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    import duckdb
    con = duckdb.connect(argv[0], read_only=True)
    tree = Path(argv[1]).resolve()
    rows = con.execute(
        "SELECT le.concept_id, c.name, c.partition_id, le.file, le.line, le.detail "
        "FROM linkage_evidence le LEFT JOIN entities c ON c.id = le.concept_id "
        "WHERE le.detail LIKE 'learned from grep %' AND NOT EXISTS "
        "(SELECT 1 FROM entities e WHERE e.id = le.entity_id)").fetchall()
    live: dict = {}
    for i, k, n, p in con.execute(
            "SELECT id, kind, name, partition_id FROM entities WHERE kind IN ('code', 'doc')"
            ).fetchall():
        live.setdefault((p, k, n), []).append(i)
    attached = {(int(c), int(e), f, ln, d) for c, e, f, ln, d in con.execute(
        "SELECT le.concept_id, le.entity_id, le.file, le.line, le.detail FROM linkage_evidence le "
        "JOIN entities e ON e.id = le.entity_id WHERE le.detail LIKE 'learned from grep %'"
        ).fetchall()}
    cnt: Counter = Counter()
    why_files: dict[str, Counter] = {"C": Counter(), "E": Counter(), "F": Counter()}
    exists: dict[str, bool] = {}
    pairs_ok: set = set()
    files_ok: set = set()
    dup = 0
    for cid, cname, part, f, line, detail in rows:
        cnt["orphans"] += 1
        if cname is None or not cname.startswith("query/"):
            cnt["not: C (concept gone)"] += 1
            why_files["C"][f] += 1
            continue
        kind = "code" if Path(f).suffix.lower() in CODE_SUFFIXES else "doc"
        ents = live.get((part, kind, f), [])
        if len(ents) != 1:
            cnt["not: E (no entity of the learner's kind and that name)"] += 1
            why_files["E"][f] += 1
            continue
        if f not in exists:
            p = Path(f) if Path(f).is_absolute() else tree / f
            exists[f] = p.is_file()
        if not exists[f]:
            cnt["not: F (file not on disk)"] += 1
            why_files["F"][f] += 1
            continue
        cnt["resolvable"] += 1
        pairs_ok.add((cid, ents[0]))
        files_ok.add(f)
        if (int(cid), int(ents[0]), f, line, detail) in attached:
            dup += 1
    for k in sorted(cnt):
        print(f"{k}: {cnt[k]}")
    print(f"resolvable rows equal to a row already attached to that entity: {dup}")
    print(f"resolvable: {len(pairs_ok)} (concept, entity) pairs on {len(files_ok)} files")
    for key, c in why_files.items():
        if c:
            print(f"not resolvable by {key}: {len(c)} file(s): "
                  + "; ".join(f"{f} {n}" for f, n in c.most_common(12)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
