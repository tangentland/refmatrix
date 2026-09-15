---
gmd: "0.1"
id: task-4.3-plan-4-daemon-resilience
title: "Task 4.3: Heartbeat + watchdog grace + graceful restart"
tags: [task, plan-4]
metadata:
  node_type: task
  status: pending
  plan: plan-4-daemon-resilience
---

# Task 4.3: Heartbeat + watchdog grace + graceful restart {#root}

> Plan: [[plan-4-daemon-resilience]]
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-4-daemon-resilience]]

## Requirements {#requirements}

- Watchdog test with a fake root: alive pid + fresh heartbeat + failing ping → no restart; stale heartbeat → restart; restart path calls graceful stop before kill (recorded call order).

## Files to Create / Modify {#files}

- `src/refmatrix/daemon.py`: `_start_heartbeat()` thread touching `.refmatrix/heartbeat` every 5 s, no locks; ping responder must not await model-worker reconnect (move reconnect into the worker proxy's own thread with a timeout).
- `src/refmatrix/hub.py:Watchdog._check`: `dead = pid missing or heartbeat older than RMX_HUB_HEARTBEAT_STALE_S (60)`; busy → no action, log once; `_restart`: `daemon stop` (SIGTERM) → wait `RMX_HUB_KILL_GRACE_S` (30) → `kickstart -k` only if still alive.

## Test Strategy (RED first) {#test-strategy}

tests/test_hub_watchdog.py (monkeypatched launchctl/pkill calls recorded in a list — external process mocks, registered).

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-4.3-plan-4-daemon-resilience.md`.
- Committed on branch `task-4.3-plan-4-daemon-resilience`; merged `--no-ff` to `master`.
