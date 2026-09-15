---
gmd: "0.1"
id: task-5.2-plan-5-memory-bridge-complete
title: "Task 5.2: Bridge overlap: wait for the active job"
tags: [task, plan-5]
metadata:
  node_type: task
  status: complete
  plan: plan-5-memory-bridge-complete
---

# Task 5.2: Bridge overlap: wait for the active job {#root}

> Plan: [[plan-5-memory-bridge-complete]]
> Status: Complete
> Depends on: 5.1

rel: part-of -> [[plan-5-memory-bridge-complete]]

## Requirements {#requirements}

- Test daemon with a long-running fake ingest job registered → `_sync_memory_dir` returns `waited=True` and no error; with a job on another target → runs its own ingest after.

## Files to Create / Modify {#files}

- `src/refmatrix/cli.py:_sync_memory_dir`: catch `RuntimeError("ingest already active")` → `daemon.call(root, "ingest_gmd_status", …)` loop with sleep 1 s until done or `RMX_BRIDGE_WAIT_S`; if the finished job's targets include memdir → return its report with `"waited": True`; else run once more.

## Test Strategy (RED first) {#test-strategy}

tests/test_memory_bridge.py::test_bridge_waits_for_active_job.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-5.2-plan-5-memory-bridge-complete.md`.
- Committed on branch `task-5.2-plan-5-memory-bridge-complete`; merged `--no-ff` to `master`.
