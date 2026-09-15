---
gmd: "0.1"
id: impl-task-4.3-plan-4-daemon-resilience
title: "Task 4.3 — heartbeat + watchdog grace + graceful restart"
tags: [implementation-summary, plan-4]
metadata:
  node_type: implementation-summary
  task: task-4.3-plan-4-daemon-resilience
---

# Task 4.3 — supervisors never SIGKILL a working daemon {#root}

rel: implements -> [[task-4.3-plan-4-daemon-resilience]]
rel: derives-from -> [[project_daemon_watchdog_grace_spawn]]

## What shipped {#shipped}

- `daemon.heartbeat_path` / `heartbeat_age` (`inf` when absent) and `Daemon._start_heartbeat()` / `_stop_heartbeat()`: a lock-free thread touches `.refmatrix/heartbeat` every `RMX_HEARTBEAT_S` (5); started in `serve_forever` right after the pid file, BEFORE the store open and the boot repairs, stopped at shutdown (plan Q2: a file, because a ping must pass the accept loop, which is exactly what stalls when the daemon is busy).
- `hub.Watchdog._check`: on a failed ping, `no-process` → restart now; process alive and heartbeat ≤ `RMX_HUB_HEARTBEAT_STALE_S` (60) → `busy-heartbeat-Ns`, miss counter reset, NEVER restarted; heartbeat stale or absent (pre-0.69 daemon) → the existing miss-grace window, then a restart. Reason strings are the health ring the UI/`hub status` show.
- `Watchdog._restart(root, *, alive)`: a live-but-wedged daemon gets `daemon.stop_daemon(root, timeout=RMX_HUB_KILL_GRACE_S)` (the `stop` op, then SIGTERM) BEFORE `launchctl kickstart -k` / spawn; a dead process skips the courtesy.

## Note on the ping responder {#responder}

The spec asked for the model-worker reconnect to be moved off the ping responder. The reconnect probe was already bounded by plan-1 (`SharedWorkerClient.info(timeout=PROBE_TIMEOUT_S)`, 5 s, no retry on timeout) and runs on the worker pool, not the accept loop; with the heartbeat the supervisor no longer depends on the ping at all during that window. No further machinery was added — recorded here so the decision is visible, not silent.

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-4.3-red.log` (4 failed). GREEN `pytest-task-4.3-green.log` (39 passed with the hub, hub-watchdog-grace, daemon liveness/shutdown/reap suites; the two older watchdog tests' `_restart` stubs now accept the `alive` keyword). Mutations `pytest-task-4.3-mutation.log`: (A) removing the fresh-heartbeat gate fails `test_busy_daemon_with_fresh_heartbeat_is_never_restarted`; (B) removing the graceful stop fails `test_stale_heartbeat_past_grace_restarts_gracefully_first`.
