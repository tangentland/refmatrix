---
gmd: "0.1"
id: impl-task-4.1-plan-4-daemon-resilience
title: "Task 4.1 — learn_from_grep never fast-exits"
tags: [implementation-summary, plan-4]
metadata:
  node_type: implementation-summary
  task: task-4.1-plan-4-daemon-resilience
---

# Task 4.1 — a read surface never takes the daemon down {#root}

rel: implements -> [[task-4.1-plan-4-daemon-resilience]]

## What shipped {#shipped}

- `daemon._op_learn_from_grep`: `_learn_grep_hits` runs inside a guard; an exception that `Daemon._is_fatal_invalidation` classifies as DuckDB index drift / invalidation is logged (`learn skipped: store invalid (...)`), recorded via `_mark_repair_needed("entities", op="learn_from_grep")`, and answered `{"added": 0, "skipped": "store-invalid"}`. Any other exception still raises. Write ops keep the fast-exit.
- `Daemon._mark_repair_needed(table, *, op)`: sets `_repair_needed` and writes `.refmatrix/repair.needed` (`{table, op, at}`, first writer wins). `daemon.repair_marker_path` / `read_repair_marker` are the shared readers task 4.2 uses.

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-4.1-red.log` (1 failed / 1 passed — the non-fatal re-raise passed on arrival, the degrade did not). GREEN `pytest-task-4.1-green.log` (20 passed with the daemon liveness/reap/shutdown suites). Mutation `pytest-task-4.1-mutation.log`: re-raising unconditionally (the pre-task behaviour) fails `test_learn_from_grep_degrades_instead_of_fast_exiting`.
