---
gmd: "0.1"
id: impl-task-5.2-plan-5-memory-bridge-complete
title: "Task 5.2 — bridge overlap: wait for the active job"
tags: [implementation-summary, plan-5]
metadata:
  node_type: implementation-summary
  task: task-5.2-plan-5-memory-bridge-complete
---

# Task 5.2 — two bridges do not print FAILED at each other {#root}

rel: implements -> [[task-5.2-plan-5-memory-bridge-complete]]

## What shipped {#shipped}

`cli._bridge_wait_for_active_job`: when the daemon's single-active-ingest guard refuses the bridge (`ingest already active: job <id>`), `_sync_memory_dir` polls `ingest_gmd_status` for that job every 0.5 s, bounded by `RMX_BRIDGE_WAIT_S` (120). If the finished job's `args.targets` cover the memory dir, its report is the bridge's report (`waited=True`, `waited_job=<id>`); if it covered something else, the bridge runs its own ingest once the slot is free; a wait that runs out or a job that ended in error is a named `error` with the job id and the manual command. The result dict carries `waited` / `waited_job` for save-state and MCP.

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-5.2-red.log` (3 failed). GREEN `pytest-task-5.2-green.log` (3 passed on a real spawned daemon with a real 350-file `ingest_gmd_start` job in flight — same target, other target, and a 0.2 s budget that runs out). Mutation `pytest-task-5.2-mutation.log`: replacing the wait with the old "report the error" fails both wait tests.
