#!/usr/bin/env python3
"""Task 31.2 census: the orphaned evidence rows of a catalog, and what could be done with the
learned ones.

`orphan_census.py <catalog-copy> <tree-root>`

Read-only: `<catalog-copy>` is a COPY of `.refmatrix/catalog.read.duckdb`, opened
`read_only=True`; `<tree-root>` is the project the catalog indexes (files are read, never
written). No store is opened, no daemon is called.

A LEARNED evidence row is one `daemon._learn_grep_hits` wrote: `detail` starts with
`learned from grep `. An ORPHAN is an evidence row whose `entity_id` names no `entities` row
(`vacuum` step 3's predicate). For the learned orphans it reports:

  file_exists        the row's `file` (relative to the tree root, or absolute) is on disk
  live_entity        a `code` / `doc` entity named `file` exists now (the row could re-attach)
  concept_alive      the row's `query/<pattern>` concept still exists
  verifies           line > 0 and the CURRENT file holds the pattern on that line (literal
                     substring; `verifies_regex` = the pattern as a regex also counted)
  pairs              distinct (concept, file); `pairs_linked_now` = the live file entity carries
                     the concept's `mentions` link today; `pairs_evidence_now` = an attached
                     learned row exists for the pair today
  distinct_rows      distinct (concept, file, line, detail) among the orphans
"""
from __future__ import annotations

import ast
import re
import sys
from collections import Counter
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    import duckdb
    con = duckdb.connect(argv[0], read_only=True)
    tree = Path(argv[1]).resolve()
    q = lambda sql, *a: con.execute(sql, a).fetchall()  # noqa: E731

    total = q("SELECT count(*) FROM linkage_evidence")[0][0]
    orphan = q("SELECT count(*) FROM linkage_evidence le WHERE NOT EXISTS "
               "(SELECT 1 FROM entities e WHERE e.id = le.entity_id)")[0][0]
    c_gone = q("SELECT count(*) FROM linkage_evidence le WHERE NOT EXISTS "
               "(SELECT 1 FROM entities c WHERE c.id = le.concept_id)")[0][0]
    print(f"linkage_evidence rows: {total}; entity gone (vacuum step 3's set): {orphan}; "
          f"concept gone: {c_gone}")
    print("orphans by kind of row:")
    for cls, n in q(
            "SELECT CASE WHEN detail LIKE 'learned from grep %' THEN 'learned' "
            "            WHEN detail LIKE 'rel: %' THEN 'rel' ELSE 'other' END AS cls, count(*) "
            "FROM linkage_evidence le WHERE NOT EXISTS "
            "(SELECT 1 FROM entities e WHERE e.id = le.entity_id) GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {cls}: {n}")

    learned = q("SELECT count(*) FROM linkage_evidence WHERE detail LIKE 'learned from grep %'")[0][0]
    by_query = q("SELECT count(*) FROM linkage_evidence le JOIN entities c ON c.id = le.concept_id "
                 "WHERE c.name LIKE 'query/%'")[0][0]
    attached = q("SELECT count(*), count(DISTINCT le.entity_id) FROM linkage_evidence le "
                 "JOIN entities e ON e.id = le.entity_id "
                 "WHERE le.detail LIKE 'learned from grep %'")[0]
    print(f"learned rows (by detail): {learned}; by `query/` concept: {by_query}; "
          f"attached: {attached[0]} on {attached[1]} entities; orphaned: {learned - attached[0]}")
    prot = q("SELECT count(*) FROM entities WHERE protected = 1")[0][0]
    print(f"protected entities: {prot}")

    rows = q("SELECT le.concept_id, c.name, c.partition_id, le.file, le.line, le.detail "
             "FROM linkage_evidence le LEFT JOIN entities c ON c.id = le.concept_id "
             "WHERE le.detail LIKE 'learned from grep %' AND NOT EXISTS "
             "(SELECT 1 FROM entities e WHERE e.id = le.entity_id)")
    live = {(p, n): (i, pr) for i, n, p, pr in q(
        "SELECT id, name, partition_id, protected FROM entities WHERE kind IN ('code', 'doc')")}
    mentions = q("SELECT id FROM linkage_types WHERE name = 'mentions'")
    mid = mentions[0][0] if mentions else None
    linked = set()
    if mid is not None:
        linked = {(int(c), int(e)) for c, e in q(
            "SELECT el.concept_id, el.entity_id FROM entity_links el JOIN entities c "
            "ON c.id = el.concept_id WHERE el.linkage_id = ? AND c.name LIKE 'query/%'", mid)}
    ev_now = {(int(c), int(e)) for c, e in q(
        "SELECT DISTINCT le.concept_id, le.entity_id FROM linkage_evidence le JOIN entities e "
        "ON e.id = le.entity_id WHERE le.detail LIKE 'learned from grep %'")}

    cnt: Counter = Counter()
    pairs: set = set()
    distinct: set = set()
    files: Counter = Counter()
    cache: dict[str, "list[str] | None"] = {}
    unprotected_files: set = set()
    for cid, cname, part, f, line, detail in rows:
        cnt["orphans"] += 1
        distinct.add((cid, f, line, detail))
        files[f] += 1
        p = Path(f) if Path(f).is_absolute() else tree / f
        if f not in cache:
            try:
                cache[f] = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                cache[f] = None
        text = cache[f]
        if text is not None:
            cnt["file_exists"] += 1
        ent = live.get((part, f)) if part is not None else None
        if ent is not None:
            cnt["live_entity"] += 1
            if not ent[1]:
                unprotected_files.add(f)
        if cname is not None:
            cnt["concept_alive"] += 1
            pairs.add((cid, f, ent[0] if ent else None))
        try:
            pat = ast.literal_eval(detail[len("learned from grep "):])
        except (ValueError, SyntaxError):
            pat = None
            cnt["pattern_unparsed"] += 1
        if not line:
            cnt["line_zero"] += 1
        elif text is not None and pat is not None and 0 < int(line) <= len(text):
            s = text[int(line) - 1]
            if pat in s:
                cnt["verifies"] += 1
                if ent is not None and cname is not None:
                    cnt["verifies_and_reattachable"] += 1
            else:
                try:
                    if re.search(pat, s):
                        cnt["verifies_regex"] += 1
                except re.error:
                    pass
    print(f"learned orphans: {cnt['orphans']}")
    for k in ("file_exists", "live_entity", "concept_alive", "line_zero", "verifies",
              "verifies_regex", "verifies_and_reattachable", "pattern_unparsed"):
        print(f"  {k}: {cnt[k]}")
    print(f"  distinct_rows: {len(distinct)}")
    with_ent = [(c, e) for c, _f, e in pairs if e is not None]
    print(f"  pairs (concept, file): {len(pairs)}; with a live file entity: {len(with_ent)}; "
          f"pairs_linked_now: {sum(1 for p in with_ent if p in linked)}; "
          f"pairs_evidence_now: {sum(1 for p in with_ent if p in ev_now)}")
    print(f"  files: {len(files)}; on disk: {sum(1 for f in files if cache.get(f) is not None)}; "
          f"with a live entity that is not protected: {len(unprotected_files)}")
    print("  top files: " + "; ".join(f"{f} {n}" for f, n in files.most_common(8)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
