#!/usr/bin/env python3
"""Task 31.6: where the `rel:` lines that lint resolves by a NON-id form landed in a catalog.

`resolver_landing.py <catalog-copy> <census --lines output> <tree-root>`

Input 2 is `resolver_census.py ... --lines` run from `<tree-root>` (the tree the catalog was
ingested from, so evidence `file` paths match). Memory-dir sources are skipped. Each such
`rel:` line is classed with `scripts/check-rel-landing.py`'s own rules:

  target_unresolved   no `rel:` evidence row at this file + line
  stale               evidence rows, none joining a live edge with both entities present
  <binding>           a live row; `_bind` of its target: doc_or_memory, anchor_node, misbound,
                      bound_via_denotes, other_concept (a path-less concept)

Read-only: open a COPY of `catalog.read.duckdb` (never the live file); this script opens what
it is given with `read_only=True`.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    catalog, lines_file, tree = argv
    import duckdb
    spec = importlib.util.spec_from_file_location(
        "_crl", ROOT / "scripts" / "check-rel-landing.py")
    crl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(crl)
    con = duckdb.connect(catalog, read_only=True)
    want: dict[tuple[str, int], tuple[str, str]] = {}
    for ln in open(lines_file, encoding="utf-8"):
        m = re.match(r"^(\S+?):(\d+): rel \[\[([^\]]+)\]\] form=(\w+)", ln)
        if m and "/memory/" not in m.group(1):
            f = os.path.realpath(os.path.join(tree, m.group(1)))
            want[(f, int(m.group(2)))] = (m.group(3), m.group(4))
    lt = {int(i): n for i, n in con.execute("SELECT id, name FROM linkage_types").fetchall()}
    den = next((i for i, n in lt.items() if n == crl.DENOTES), None)
    ents = {int(r[0]): (r[1], r[2], r[3], int(r[4])) for r in con.execute(
        "SELECT id, kind, name, path, partition_id FROM entities").fetchall()}
    doc_names = {(p, n) for k, n, _path, p in ents.values() if k in ("doc", "memory")}
    denotes_from: set[int] = set()
    if den is not None:
        denotes_from = {int(c) for (c,) in con.execute(
            "SELECT el.concept_id FROM entity_links el JOIN entities d ON d.id = el.entity_id "
            "WHERE el.linkage_id = ? AND d.kind IN ('doc', 'memory')", (den,)).fetchall()}
    ev: dict[tuple[str, int], list[tuple[int, bool]]] = {}
    for e, f, line, detail, live in con.execute(
            "SELECT le.entity_id, le.file, le.line, le.detail, "
            "  (EXISTS (SELECT 1 FROM entity_links el WHERE el.entity_id = le.entity_id "
            "           AND el.linkage_id = le.linkage_id AND el.concept_id = le.concept_id) "
            "   AND EXISTS (SELECT 1 FROM entities x WHERE x.id = le.entity_id) "
            "   AND EXISTS (SELECT 1 FROM entities y WHERE y.id = le.concept_id)) AS live "
            "FROM linkage_evidence le WHERE le.detail LIKE 'rel: %'").fetchall():
        if not f or (detail or "").endswith("(root-mirror)"):
            continue
        ev.setdefault((os.path.realpath(f), int(line)), []).append((int(e), bool(live)))
    by_form: Counter = Counter()
    by_target: Counter = Counter()
    for key, (ref, form) in sorted(want.items()):
        rows = ev.get(key, [])
        if not rows:
            cls = "target_unresolved"
        else:
            hit = next((t for t, live in rows if live), None)
            cls = "stale" if hit is None else crl._bind(hit, ents, doc_names, denotes_from)
        by_form[(form, cls)] += 1
        by_target[(ref.split("#")[0], cls)] += 1
    print(f"rel lines lint resolves by a non-id form (repo sources): {len(want)}")
    for (form, cls), n in sorted(by_form.items()):
        print(f"  {form:8s} {cls:20s} {n}")
    tot: Counter = Counter()
    for (_form, cls), n in by_form.items():
        tot[cls] += n
    print("totals: " + ", ".join(f"{c} {n}" for c, n in sorted(tot.items())))
    print("by target doc:")
    for (t, cls), n in sorted(by_target.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {t:42s} {cls:20s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
