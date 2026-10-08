---
gmd: "0.1"
id: task-17.2-hub-nightly-tick
title: "Task 17.2: the hub runs maintenance nightly at 03:30 with catch-up, serially, pause-aware, and says what happened"
tags: [task, hub, schedule, maintenance]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 17.2: the nightly tick {#root}

> Plan: [plan-17-nightly-store-maintenance](../plan-17-nightly-store-maintenance.md)
> Status: Pending
> Depends on: 17.1

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[task-17.1-vectors-maintain-op]]
rel: related-to -> [[project_bus_retention_global_queues]]

## Why {#why}

The hub already runs a periodic loop: `_queue_alert_loop` (`hub.py:699`) calls
`_bus_retention_once` (`hub.py:714`) on each tick. That is the precedent this extends ("a sweep
needing its own thread is a thread that can go missing"). Decisions d-1 (03:30 + catch-up) and
d-4 (orphans nightly) are fixed. {#why-body}

## Requirements {#requirements}

1. **R1 Schedule.** The local time is `RMX_HUB_MAINTAIN_AT` (default `03:30`; `off` disables).
   Each tick checks whether the scheduled time has passed since the last run, using a per-store
   `last_maintained` stamp persisted in `~/.refmatrix/maintain.json`.
2. **R2 Catch-up.** A night missed while the machine slept runs at the first tick after wake.
   Runs never stack: at most one run per store per scheduled day.
3. **R3 Serial and pause-aware.** Stores run one at a time, in registry order. A store that is
   paused (`Watchdog.is_paused`, `hub.py:221`), not running, or not supervised is skipped and named.
4. **R4 Calls the op.** Each store gets `vectors_maintain` (17.1) through the store's daemon
   socket, with the call's timeout bounded by `RMX_MAINTAIN_STORE_TIMEOUT_S` (default 600) and
   `retries=0`. That avoids `daemon.call`'s default `retries=2`, which triples a timeout.
5. **R5 Failure isolation.** A failed store is logged and counted, and the next store still runs.
   A store failing N consecutive nights (default 3) publishes one alert. A one-off failure does
   not.
6. **R6 Report.** One summary per run to `global:queues`: stores run/skipped/failed, bytes
   reclaimed, orphans reaped. `global:queues` retention already bounds it. Per-store detail goes
   to `hub.log`.
7. **R7 Plan-19 hook point.** The run calls a list of per-store maintenance steps, not one
   hard-coded op, so plan-19's memory compile (19.4) and plan-18's DuckDB step join by
   registration.

## Acceptance criteria {#acceptance}

1. With an injected clock: one run per scheduled day per store; a run at the first tick after a
   simulated 2-day sleep, and exactly one; nothing before 03:30.
2. A paused store is skipped and named; a failing store does not stop the next.
3. Three consecutive failures produce exactly one alert; a success resets the count.
4. Every call uses `retries=0` and the bounded timeout (asserted on the real client call, not a
   kwargs list).
5. Mutations that must FAIL a test:
   - no catch-up;
   - stacking runs;
   - the pause ignored;
   - default retries.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/hub.py` | the schedule check on the existing tick, the step registry, the stamps, the summary |

## Test strategy {#test-strategy}

The tick runs with an injected clock and stores that are real tmp daemons (a short tmp root for
`sun_path`). The test suite must not reach the live hub (bug-088): the tick under test is
constructed in-process with its own home.
