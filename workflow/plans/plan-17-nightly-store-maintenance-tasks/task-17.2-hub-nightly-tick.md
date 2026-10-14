---
gmd: "0.1"
id: task-17.2-hub-nightly-tick
title: "Task 17.2: the hub runs maintenance nightly at 03:30 with catch-up on its own thread — serial, single-flight, pause-aware, dry-run until armed — and says what happened"
tags: [task, hub, schedule, maintenance]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-14
---

# Task 17.2: the nightly tick {#root}

> Plan: [plan-17-nightly-store-maintenance](../plan-17-nightly-store-maintenance.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 17.1; 23.1 (tick-registry step interface); 23.0 (test sandbox)

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[task-17.1-vectors-maintain-op]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: related-to -> [[project_bus_retention_global_queues]]
rel: depends-on -> [[feedback_daemon_call_retries_multiply_timeouts]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14#t3]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: related-to -> [[task-19.4-keep-derived-layers-current]]

## Why {#why}

The hub's only periodic loop today is `_queue_alert_loop` (`hub.py:699`), which calls
`_bus_retention_once` (`hub.py:714`). Riding it was the old plan, and it fails three ways (spec
review #s-2): `RMX_HUB_QUEUE_ALERT_INTERVAL <= 0` returns from the loop at once (`hub.py:700-701`)
and would silently disable maintenance; the loop first ticks 1,800 s after hub start; and a serial
run of up to 8 × 600 s would hold off the alert and bus retention. Decision d3e puts maintenance on
its own step on 17.2's tick (plan-review C6), with a per-store budget, `retries=0` and a
single-flight op. Decision d3d makes an unarmed store dry-run only. {#why-body}

## Requirements {#requirements}

1. **R1 Own thread, schedule, catch-up, (store, step) stamps** (spec review #s-2, #m-5; d-1, d3e).
   {#r1-schedule}
   - A dedicated hub thread `_maintain_loop` wakes every `RMX_HUB_MAINTAIN_TICK_S` (default 300)
     and is started regardless of `RMX_HUB_QUEUE_ALERT_INTERVAL`. `RMX_HUB_MAINTAIN_AT` (default
     `03:30` local; `off` disables) is read at start; `off` writes one `hub.log` line
     `maintenance disabled (RMX_HUB_MAINTAIN_AT=off)`.
   - Stamps live in `~/.refmatrix/maintain.json`, keyed by (store root, step name):
     `{armed_at, last_attempt, last_success, consecutive_failures, last_outcome}`. Writes are
     atomic (tmp + rename) under an `fcntl` lock on `maintain.json.lock`, shared with R7's CLI.
   - A (store, step) is DUE when the most recent scheduled instant (today's 03:30 if now ≥ 03:30,
     else yesterday's) is later than its `last_attempt`. That gives catch-up after sleep (the
     first tick after wake runs a missed night) and no stacking (at most one attempt per store per
     step per scheduled day, however many nights were missed).
   - The clock (`now: Callable[[], datetime]`) is injected.
2. **R2 The step registry** (plan-review C6; R7 of the old spec). {#r2-registry}
   A run calls an ordered list of registered per-store steps, each a `(name, callable(root,
   dry_run) → result)` with its own budget, using the step interface of plan-23 23.1's tick
   registry. `vectors_maintain` (17.1) is the first step; 19.4's memory compile and plan-18's
   DuckDB step register into it. A failure in one step does not skip the store's other steps.
3. **R3 Roots: the registered daemon list, injected** (spec review #b-5, #s-6). {#r3-roots}
   - The run takes `roots: Callable[[], list[Path]]`. The production default is the registered
     daemon list: the launchd-supervised roots (`discovery._roots_from_launchd()`,
     `discovery.py:70`, 8 today including the global store), sorted by resolved path. It is NOT
     `registry.json` (3 stores) and NOT `discover_roots()` (which adds the cwd root).
   - Per root: supervised = it came from a launchd plist; running = `daemon_mod.ping(root)`
     answers; paused = `Watchdog.is_paused(root)` (`hub.py:221`). A root that is paused, not
     running or not supervised is skipped, named and counted in the summary (`skipped:paused`,
     `skipped:not_running`). Nothing runs in-process for a skipped store.
4. **R4 The call: retries=0, per-store budget, still-running is not failure** (d3e and its
   close-out amendment; decision review #s-6). {#r4-call}
   - Each step call is `daemon.call(root, op, args, timeout=RMX_MAINTAIN_STORE_TIMEOUT_S
     (default 600), retries=0)`.
   - A timeout, or an `already_running` reply (17.1 R11), is outcome `still_running`, never
     `failed`, and never counts toward R5. The hub then polls `vectors_maintain(status=True)`
     every 30 s until the store reports idle or the per-store budget
     `RMX_MAINTAIN_STORE_BUDGET_S` (default 1800) is spent; the op is never re-sent.
   - Strictly serial: the next store does not start while one is `still_running`. If the budget
     is spent with the store still running, the run stops; the remaining due stores are reported
     `deferred` and stay due for the next tick, and the still-running store's final report is
     read through `status=True` on the next tick and stamped then.
5. **R5 Failure isolation and alert** (spec review #m-5). {#r5-alert}
   A `failed` or `refused` outcome is logged and counted per (store, step), and the next store
   still runs. After `RMX_MAINTAIN_ALERT_AFTER` (default 3) consecutive failed runs of one
   (store, step), one alert is published to `global:queues`; a success resets the count and the
   alert. An `orphan_cap` refusal (17.1 R6) alerts on its first occurrence.
6. **R6 Report** (spec review #m-4). {#r6-report}
   One summary per run to `global:queues`: per outcome (`ok`, `dry_run:unarmed`, `skipped:*`,
   `refused:*`, `failed`, `still_running`, `deferred`) the store names; bytes reclaimed; `orphans`
   reaped; `missing` re-queued; holds over `RMX_MAINTAIN_HOLD_S`. Per-store detail goes to
   `hub.log`.
7. **R7 Unarmed = dry run** (spec review #s-3; d3d). {#r7-unarmed}
   - A (store, step) with no `armed_at` stamp runs with `dry_run=True` only, reported
     `dry_run:unarmed`. Its `last_attempt` is stamped, so the dry run happens once per scheduled
     day.
   - `rmx hub maintain arm --root <root> [--step vectors_maintain]` writes `armed_at` for that
     (store, step), under R1's lock. It is the only writer of `armed_at`; 17.3 runs it by hand after
     its dry run, backup and hand run. `rmx hub maintain disarm` clears it. CLI-only pending the
     verb-class ruling (plan `#open-after-revision` item 4).

## Acceptance criteria {#acceptance}

All tests run inside the 23.0 sandbox with injected `roots` and `now`; the stores are real tmp
daemons with short roots.

1. **AC-1 schedule.** One attempt per scheduled day per (store, step); nothing before 03:30; after a
   simulated 2-day sleep, exactly ONE run at the first tick after wake.
2. **AC-2 own thread.** With `RMX_HUB_QUEUE_ALERT_INTERVAL=0`, maintenance still runs on schedule;
   with `RMX_HUB_MAINTAIN_AT=off`, no step runs and the disable line is in `hub.log`.
3. **AC-3 roots.** The calls made equal the injected tmp roots, in path order. The 23.0 sandbox
   records ZERO connects to any root from the real LaunchAgents dir, `registry.json` or the cwd.
   A launchd-only root (in the injected supervised set, absent from `registry.json`) is
   maintained.
4. **AC-4 skips.** A paused store and a stopped store are skipped, named and counted; a failing
   store does not stop the next.
5. **AC-5 unarmed.** A store with no stamp gets `dry_run=True` (its Lance version count and bytes
   are unchanged) and is reported `dry_run:unarmed`; after `rmx hub maintain arm` it gets the
   real op on the next due day.
6. **AC-6 retries and single-flight.** A tmp daemon whose `vectors_maintain` blocks past the
   timeout receives the op exactly ONCE (counted daemon-side by 17.1 R11's state), the outcome is
   `still_running`, the failure count is unchanged, and the second store is not called until the
   first reports idle.
7. **AC-7 budget.** With the per-store budget spent, the run stops, the remaining stores are
   `deferred`, and the next tick runs them after the first store is idle.
8. **AC-8 alert.** Three consecutive failures of one (store, step) give exactly one alert; a
   success resets it. A vectors step that succeeds and a second registered step that fails on the
   same store: only the failing step's count rises, and only it is due again next day.
9. **AC-9 pre-registered mutations, each must FAIL a named AC:**
   - no catch-up → AC-1;
   - stacking runs after sleep → AC-1;
   - maintenance moved back onto `_queue_alert_loop` → AC-2;
   - `discover_roots()` used as the default with the injection removed → AC-3;
   - the pause ignored → AC-4;
   - unarmed stores run for real → AC-5;
   - default `retries` → AC-6;
   - a timeout counted as failed → AC-6;
   - stamps keyed by store only → AC-8.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/hub.py` | `_maintain_loop`, the schedule check, the step registry, the stamps, the summary |
| `src/refmatrix/cli.py` | `rmx hub maintain arm` / `disarm` |

## Test strategy {#test-strategy}

- Task 23.0's sandbox is mandatory (decisions d1a/d1b; spec review #b-5): `$HOME`, global root,
  registry path and LaunchAgents dir are redirected BEFORE `refmatrix` is imported
  (`launchctl.LAUNCH_AGENTS_DIR` is computed at import, `launchctl.py:20`), and spawned children
  refuse sockets outside the tmp dir. Setting `RMX_HOME` alone isolates nothing.
- `roots` and `now` are injected; no test reaches the live hub or a live daemon (bug-088).
- Store daemons are real tmp daemons with a short tmp root (`sun_path`).

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 17 #b-5 | [[#r3-roots]], AC-3, [[#test-strategy]] |
| 17 #s-2 | [[#why]], [[#r1-schedule]], AC-2 |
| 17 #s-3 | [[#r7-unarmed]], AC-5 |
| 17 #s-6 | [[#r3-roots]], AC-3 |
| 17 #m-4 | [[#r6-report]] (`missing`) |
| 17 #m-5 | [[#r1-schedule]] (stamps per (store, step)), [[#r5-alert]] (env name), AC-8 |
| d3d | [[#r7-unarmed]], AC-5 |
| d3e + close-out (retries=0, single-flight) | [[#r1-schedule]], [[#r4-call]], AC-6, AC-7 |
| decision review #s-6 | [[#r4-call]], AC-6 |
| plan-review C6 / 23.1 tick registry | [[#r2-registry]] (open item 1 in the plan) |
| d1a/d1b (23.0) | [[#test-strategy]] |
