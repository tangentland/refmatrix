---
gmd: "0.1"
id: task-15.2-derive-history-and-counts
title: "Task 15.2: every derive records what it produced, and the record is kept"
tags: [task, derive, store, schema]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
---

# Task 15.2: `derive_history` + the counts {#root}

> Plan: [plan-15-derive-impact-tracking](../plan-15-derive-impact-tracking.md)
> Status: Pending
> Depends on: Task 15.1

rel: part-of -> [[plan-15-derive-impact-tracking]]
rel: depends-on -> [[task-15.1-per-pass-code-identity]]

## Requirements {#requirements}

A new append-only table. `derive_stamps` keeps its current-state contract untouched — four readers
depend on it (`derive_status`, `rmx fingerprint`, the hub alert, the daemon status line) and none of
them asks for history. {#req-table}

```sql
CREATE TABLE IF NOT EXISTS derive_history (
    id           INTEGER PRIMARY KEY,
    partition_id INTEGER NOT NULL REFERENCES partitions(id),
    pass_name    TEXT NOT NULL,
    version      TEXT NOT NULL,
    code_hash    TEXT,
    derived_at   REAL NOT NULL,
    duration_s   REAL,
    counts       TEXT NOT NULL   -- JSON: the structural shape after this derive
);
```

`counts` is the partition's shape AFTER the pass, as a JSON object. Fixed key set, cheap to compute,
and partition-scoped the way the rest of the catalog is — `entity_links` and `linkage_evidence` carry
no `partition_id` and must be scoped by joining `entities`, which is how every existing
partition-scoped query in `store.py` does it: {#req-counts}

| key | source |
|---|---|
| `entities` | `entities` per partition, plus a `by_kind` sub-object |
| `concepts` | entities of kind `concept` |
| `links` | `entity_links` joined through `entities` |
| `evidence` | `linkage_evidence` joined through `entities` |
| `tracked_files` | `tracked_files` per partition |
| `bitmap_fragments` | per partition |
| `pagerank` | per partition |
| `memory_content` | joined through `entities` |

`stamp_derive` writes a history row alongside the upsert, in the SAME transaction: a stamp that
claimed a derive the history did not record would make the two disagree, and the pair is only useful
if they cannot. {#req-atomic}

Retention: keep the most recent **N = 50** rows per `(partition_id, pass_name)`, pruned on insert.
`global:queues` reached 3,196 rows unbounded (bug-061); an append-only table with no retention is
that defect wearing a different name. The prune is counted and the count is returned, never silent.
{#req-retention}

Failure is SAID, never swallowed — the same rule `_stamp_ingest` already follows: a history write
that fails prints and lets the derive stand, because losing the derive would be worse than losing
its record. A pass whose counts cannot be computed records `counts: {"error": "<type>: <msg>"}`
rather than a partial object that reads as real. {#req-loud}

## Acceptance criteria {#acceptance}

1. A derive writes one history row with counts matching an independent query of the same tables.
2. Two derives of the same unchanged corpus produce two rows whose counts are IDENTICAL — a no-op
   derive is visibly a no-op (plan acceptance #2).
3. A derive that genuinely adds content produces a row whose counts differ in the expected keys and
   nowhere else.
4. The 51st derive of one pass leaves 50 rows; the pruned count is reported.
5. `derive_stamps` still answers exactly what it answers today, byte-for-byte in shape — asserted by
   a test that reads it directly, so this task cannot quietly change the current-state contract.
6. A store created before this table exists gains it without error, and its pre-existing stamp reads
   as having NO history rather than as a zero-count derive. Zero and unknown are different, and
   conflating them would invent a baseline.
7. **The cost is measured, not asserted**: the summary records the counts-query wall time against the
   duration of the pass it follows, on this project's real store.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/store.py` | the `derive_history` DDL, `derive_counts()`, history write + prune inside `stamp_derive`, `derive_history(pass_name=None, limit=...)` reader |

## Test strategy {#test-strategy}

`tests/test_derive_history.py` against real stores. The no-op case (criterion 2) is the one that
matters most and is easiest to fake: it must run the REAL pass twice over an unchanged tree, not call
`stamp_derive` twice by hand, because calling the stamp twice trivially produces equal counts while
proving nothing about the pass. Criterion 6 builds a store, drops the table, and reopens it. {#tests}
