#!/usr/bin/env python3
"""Task 31.6 R10 (ruling L136): the evidence-less edges on `rel:` verbs in a catalog, by shape.

`rel_residue_census.py <catalog-copy>`

Read-only: a COPY of `catalog.read.duckdb`, opened `read_only=True`.

The verbs are the linkages that carry at least one `rel:` evidence row, minus the linkages the
ingest writes with no evidence (`part-of` among them: its containment edges have none by
design). The RESIDUE class of the spec is the shape "target = a path-less concept named after
a doc or memory of its partition", from a doc, a memory or a GMD node.
"""
import sys
import duckdb
con = duckdb.connect(sys.argv[1], read_only=True)
q = lambda sql, *a: con.execute(sql, a).fetchall()
NOEV = {"part-of", "mentions", "imports", "titles", "aliases", "lead", "denotes", "same_as", "coref"}
rel_verbs = [n for (n,) in q(
    "SELECT DISTINCT lt.name FROM linkage_evidence le JOIN linkage_types lt ON lt.id = le.linkage_id "
    "WHERE le.detail LIKE 'rel: %'") if n not in NOEV]
print("linkages with a rel: evidence row, minus the no-evidence ingest linkages:", len(rel_verbs), sorted(rel_verbs))
ph = ",".join("?" * len(rel_verbs))
base = f"""
  FROM entity_links el JOIN linkage_types lt ON lt.id = el.linkage_id
  JOIN entities s ON s.id = el.concept_id JOIN entities t ON t.id = el.entity_id
  WHERE lt.name IN ({ph}) AND NOT EXISTS (SELECT 1 FROM linkage_evidence le
     WHERE le.entity_id = el.entity_id AND le.linkage_id = el.linkage_id AND le.concept_id = el.concept_id)"""
print("edges on those verbs:", q(f"SELECT count(*) FROM entity_links el JOIN linkage_types lt ON lt.id=el.linkage_id WHERE lt.name IN ({ph})", *rel_verbs)[0][0])
print("...with no evidence row:", q("SELECT count(*)" + base, *rel_verbs)[0][0])
print("by (source kind, source has path, target kind, target has path, target named after a doc/memory):")
for r in q("""SELECT s.kind, s.path IS NOT NULL, t.kind, t.path IS NOT NULL,
       EXISTS (SELECT 1 FROM entities d WHERE d.partition_id = t.partition_id AND d.name = t.name AND d.kind IN ('doc','memory') AND d.id <> t.id),
       count(*)""" + base + " GROUP BY 1,2,3,4,5 ORDER BY 6 DESC", *rel_verbs):
    print("  ", r)
print("by verb, for target = path-less concept named after a doc/memory:")
for r in q("SELECT lt.name, s.kind, count(*)" + base + """ AND t.kind='concept' AND t.path IS NULL
       AND EXISTS (SELECT 1 FROM entities d WHERE d.partition_id = t.partition_id AND d.name = t.name AND d.kind IN ('doc','memory'))
       GROUP BY 1,2 ORDER BY 3 DESC""", *rel_verbs):
    print("  ", r)
den = q("SELECT id FROM linkage_types WHERE name='denotes'")
print("denotes linkage id:", den)
print("of the class: source also has a LIVE evidence-backed edge of the same verb to the doc/memory the concept is named after:",
  q("SELECT count(*)" + base + """ AND t.kind='concept' AND t.path IS NULL
     AND EXISTS (SELECT 1 FROM entities d JOIN entity_links e2 ON e2.entity_id = d.id AND e2.concept_id = el.concept_id AND e2.linkage_id = el.linkage_id
                 WHERE d.partition_id = t.partition_id AND d.name = t.name AND d.kind IN ('doc','memory'))""", *rel_verbs)[0][0])
print("partitions:", q("SELECT p.name, count(*)" + base.replace("WHERE lt.name", "JOIN partitions p ON p.id = s.partition_id WHERE lt.name") + " GROUP BY 1", *rel_verbs))
