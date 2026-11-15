---
gmd: "0.1"
id: measurement-learned-rows-cli-store-2026-11-14
title: "Learned and protected rows on cli.py / store.py, and orphaned learned evidence store-wide (2026-11-14, read-only copy)"
tags: [measurement, learned-rows, bug-107, plan-29, task-29.7]
metadata:
  node_type: measurement
  created: 2026-11-14
---

# Learned rows on cli.py / store.py, read-only count {#root}

Taken by the lead on 2026-11-14 on a copy of the dev store's `catalog.read.duckdb` (scratchpad),
opened `read_only=True` with `.venv-eval`. Learned row = `linkage_evidence` whose concept entity
is named `query/%` (the shape `daemon._learn_grep_hits` writes). Grep learning has been off
fleet-wide since 2026-10-15 (`~/.refmatrix/learn.off`), so these rows predate that date.

rel: evidence-for -> [[plan-review-2026-11-13#lead]]
rel: related-to -> [[bug_registry]]

## Counts {#counts}

| path | entities | protected | learned evidence (by `file`) | attached to a live entity | orphaned (entity row gone) |
|---|---|---|---|---|---|
| `src/refmatrix/cli.py` | 1,063 | 1 (code) | 14,633 | 3 (entity path `../src/refmatrix/cli.py`) | 14,630 |
| `src/refmatrix/store.py` | 500 | 0 | 1,335 | 0 | 1,335 |
| whole store | — | 2,427 | 107,563 | 79,399 (628 entities) | 28,164 |

Top orphaned files: `cli.py` 14,630; `daemon.py` 1,860; `store.py` 1,335; `workflow/bug_registry.md`
1,042; `verbs.py` 712; `ingest.py` 474; `hub.py` 411; `workflow/test_mock_registry.md` 358. {#counts-top}

## What it means {#meaning}

- The knowledge 29.5's merge would purge from `cli.py` / `store.py` is **already** gone from the
  live graph: bug-107 purged the file entities at earlier edits. What 29.5 would touch is 3
  attached learned evidence rows and 1 protected entity.
- 28,164 learned evidence rows (26% of all) are orphaned: their entity row is gone, the evidence
  row remains (vacuum has not dropped them). With 29.7's F1 (bug-247), a rebuild from `facts.log`
  can re-attach evidence of a file changed in place, so orphaned is not necessarily final.
- The orphaned rows' line numbers refer to file versions from before 2026-10-15; a month of edits
  has moved them, so re-keying them through 29.5's merge-time line map would place them wrongly.
