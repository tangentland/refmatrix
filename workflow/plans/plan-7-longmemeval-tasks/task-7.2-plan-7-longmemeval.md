---
gmd: "0.1"
id: task-7.2-plan-7-longmemeval
title: "Task 7.2: Dedicated off-tree store built on the production ingest path"
tags: [task, plan-7]
metadata:
  node_type: task
  status: pending
  plan: plan-7-longmemeval
---

# Task 7.2: Dedicated off-tree store built on the production ingest path {#root}

> Plan: [[plan-7-longmemeval]]
> Status: Pending
> Depends on: 7.1

rel: part-of -> [[plan-7-longmemeval]]

## Requirements {#requirements}

- Build is `rmx init` (no hooks, no agents, no memory hooks) -> `rmx ingest-gmd --as-memory --memory-mtype longmemeval/session` -> `rmx embed --kinds memory` -> `rmx memory compile`. No adapter class, no direct `Store()` open ([[feedback_store_calls_via_daemon]], [[feedback_measure_the_path_users_run]]).
- Plain `rmx ingest` is NOT acceptable: the general markdown pass extracts only structured signals and leaves prose transcripts with zero `mentions` rows (measured on MemAware: 1309 docs, 0 mentions, 3 concepts). `ingest-gmd` is the pass that runs the body term-frequency sweep every symbolic surface reads.
- Own partition, no watcher, no launchd job. `RMX_LOG=0` by default for the build (the store is rebuildable from `corpus/`), overridable with `--facts-log`.
- Each pass is separately skippable and reports wall-clock; the run prints `rmx stats` at the end.
- Ingest throughput and final entity/vector counts are recorded in `REPORT.md` — a corpus this size is itself a scale datum.

## Files to Create / Modify {#files}

- create `eval/production/longmemeval/ingest.py`

## Test Strategy (RED first) {#test-strategy}

`tests/test_longmemeval_ingest.py`:
- the command sequence is asserted against a recorded-subprocess fake — specifically that `ingest-gmd --as-memory` is the ingest call and plain `ingest` never appears
- a non-zero exit from any pass aborts with the pass named and the elapsed time, and does not continue to the next pass
- mutation check: deleting the `--as-memory` argument turns the test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-7.2-plan-7-longmemeval.md`.
- Committed on branch `task-7.2-plan-7-longmemeval`; merged `--no-ff` to `master`.
