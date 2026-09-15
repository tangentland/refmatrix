---
gmd: "0.1"
id: task-4.1-plan-4-daemon-resilience
title: "Task 4.1: learn_from_grep answers the read, marks the repair, exits deferred"
tags: [task, plan-4]
metadata:
  node_type: task
  status: complete
  plan: plan-4-daemon-resilience
---

# Task 4.1: learn_from_grep answers the read, marks the repair, exits deferred {#root}

> Plan: [[plan-4-daemon-resilience]]
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-4-daemon-resilience]]

## Requirements {#requirements}

- With `store.upsert_entity` monkeypatched to raise a DuckDB `FatalException`, `_op_learn_from_grep` returns `{"added":0,"skipped":"store-invalid"}` (the READ itself never fast-exits), `repair.needed` exists, and the daemon exits within `RMX_DEGRADE_EXIT_S` so the supervisor respawns it onto the boot repair — amended per plan Q7 (r1 #m-10: an invalidated store must not keep serving until an unrelated op trips it; ch-bsd r2 #m-8 asked for the spec and the test to say the same thing).

## Files to Create / Modify {#files}

- `src/refmatrix/daemon.py:_op_learn_from_grep`: wrap `_learn_grep_hits` in the same guard as the context learn (`daemon.py:3579`); on `_is_fatal_invalidation(exc)`: log, `_mark_repair_needed("entities")`, return skipped.
- `Daemon._mark_repair_needed(table)`: sets attribute + writes `.refmatrix/repair.needed` (JSON `{table, at, op}`).

## Test Strategy (RED first) {#test-strategy}

tests/test_daemon_learn_guard.py (spawned test daemon on a short tmp root).

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-4.1-plan-4-daemon-resilience.md`.
- Committed on branch `task-4.1-plan-4-daemon-resilience`; merged `--no-ff` to `master`.
