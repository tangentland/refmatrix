---
gmd: "0.1"
id: impl-bug-117-rebuild-non-concept
title: "bug-117: one edge-record format; every edge event names its concept kind; replay resolves by (kind, name)"
tags: [implementation-summary, bug-117, facts-log, replay, rebuild, edge-records, ingest]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-10-15
  updated: 2026-10-15
---

# bug-117: rebuild dropped edges whose concept end is not kind `concept` {#root}

rel: implements -> [[bug_registry#registry]]

## The defect {#defect}

facts.log `link` / `unlink` / `evidence` events named the concept end by NAME only (`c`), and both
replay paths (`rebuild_index_from_log`, `apply_log_delta` → `_apply_event_body`) looked it up as
an entity of kind `concept`. Every edge whose concept end is a doc anchor or a memory row (every
GMD `rel:` edge) was therefore dropped on a rebuild, on a rebuild after compaction, and on
incremental replay, and the full rebuild skipped it with no count. Found by ch-bsd plan-16/22 r7
`#code-facts` while 22.2's replay-order rule (d9av) was specified.

## One record format (the user, 2026-10-15) {#one-format}

The parallel-ingest recorder (`ingest_records.py`) spelled the same edge `src` / `dst`, a second
format for one thing. `src/refmatrix/edge_records.py` is now the only definition: `linkage`,
`c_kind`, `c`, `e_kind`, `e`, plus `weight` (link) or `file` / `line` / `span_end` / `detail`
(evidence). Built through it: `Store.link`, `unlink`, `bulk_link`, `link_many`, `add_evidence`,
the purge's unlinks, `dump_catalog_to_log`, and the recorder's `link` / `weighted_link` /
`bulk_link` / `add_evidence`. In an ingest record the end values may still be symbolic @-refs and a
kind is None until apply; the field names are the same. The recorder had also accepted evidence
`span_end` and dropped it; it now reaches the store.

## Legacy events {#legacy}

Every log written before 0.78.3 carries no `c_kind`. One rule (`resolve_legacy_kind`): a `concept`
of that name wins (what every old rebuild did); otherwise a name held by exactly ONE kind in the
partition is that entity; otherwise it is ambiguous or missing and COUNTED (`links_unresolved`,
`evidence_unresolved` in the rebuild's result; `skipped_unresolved` in `apply_log_delta`), never
guessed. Dead-endpoint skips are counted too (`links_skipped_dead`, `evidence_skipped_dead`). The
next facts.log compaction rewrites every edge with its kind.

Measured on a copy of the live refmatrix facts.log (2026-10-15): 790,235 link + 277,530 evidence
events resolve by the old rule; **3,054 link + 736 evidence events** would have been dropped by a
rebuild and now resolve; 0 ambiguous, 0 missing.

## Verification {#verification}

- RED at `403bb19`: `tests/test_bug117_rebuild_non_concept.py`, 7 of 7 fail for the named reason
  (`workflow/review-output/bug117-red.log`); the unlink test was strengthened with a surviving
  sibling so it cannot pass vacuously. The recorder test fails at master on the old field names.
- GREEN: 9 of 9, plus the log, compaction, ingest and record families (`bug117-green.log`).
- Mutations M1-M9 all KILLED (`bug117-mutations.log`). M9 (rebuild keyed without the kind)
  first SURVIVED; `test_one_name_held_by_two_kinds_keeps_both_edges` kills it.
- Full suite, 4 shards, compared by ERROR TEXT with the 0.78.2 branch run (same `src/` as master
  `403bb19`): 43 vs 43, identical, 0 new.
- Process: the fix commit `391ffeb` was checked with `git show --stat` to hold all three `src/`
  files before the mutation gate ran (`feedback_mutation_commit_must_hold_the_fix`).
