---
gmd: "0.1"
id: impl-task-4.2-plan-4-daemon-resilience
title: "Task 4.2 — repair-index --entities, in-band and at boot"
tags: [implementation-summary, plan-4]
metadata:
  node_type: implementation-summary
  task: task-4.2-plan-4-daemon-resilience
---

# Task 4.2 — the offline recipe, in-band {#root}

rel: implements -> [[task-4.2-plan-4-daemon-resilience]]
rel: derives-from -> [[project_refmatrix_entities_index_crashloop_0914]]

## What shipped {#shipped}

- `Store.rebuild_entities_indexes() -> {rows, indexes, constraints, indexes_before}`: aborts (`store.RepairAbort`) on real duplicate groups on `(partition_id, kind, name)` or `id`; otherwise CREATE `entities_new` from the live column list (information_schema / PRAGMA, so `vectors_partition` and future columns survive) with `PRIMARY KEY` + `CHECK(kind)` + `UNIQUE(partition_id, kind, name)`, INSERT … SELECT, DROP, RENAME, recreate the five `idx_entities_*` (+ `idx_entities_canonical` where the column exists), CHECKPOINT. DuckDB rebuilds every index from the table on CREATE, which is what drops a phantom leaf.
- `Daemon._run_pending_repair()`: reads `repair.needed` (from 4.1); `entities` → rebuild under the writer lock, log `repaired entities rows=N indexes=M (queued by <op>)`, clear the marker; a `RepairAbort` is logged loudly and the marker KEPT; unknown table → cleared with a log line. Wired into `serve_forever` right after the entity_links index repair, before anything is served (plan Q1).
- Daemon op `repair_entities` + `rmx repair-index --entities` (daemon-routed when up, offline `Store` otherwise, clears the marker). `rmx daemon status` prints `repair pending: <table>` while the marker exists.

## Note {#note}

An already-invalidated DuckDB refuses every statement until the process restarts, so the in-band op serves the marker-but-still-up case and operator triage; after a fatal the path is `rmx daemon restart` → boot repair. The spec's "5 indexes" is 6 on every current catalog (`idx_entities_canonical` exists since 0.3.3); the test asserts `>= 5` and the report names what was there before.

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-4.2-red.log` (5 failed). GREEN `pytest-task-4.2-green.log` (26 passed with learn-guard, liveness, reap and store suites). Mutation `pytest-task-4.2-mutation.log`: disabling both duplicate checks fails `test_rebuild_aborts_on_real_duplicate_groups` (disabling only the first does not — the id check catches the same fake, which is why both are needed for the mutation to bite).
