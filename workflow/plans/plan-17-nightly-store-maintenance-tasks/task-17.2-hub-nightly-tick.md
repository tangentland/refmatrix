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
> Status: Pending (revision round 3, 2026-10-14: re-review [[bsd-plan23-17-spec-rereview-r3-6091648]]
> (ns17-r3-3, nm17-r3-2, nm17-r3-3); see [[#rev-round-3]]. Round 2: [[#rev-round-2]])
> Depends on: 17.1; 23.0 (test sandbox). NOT on 23.1: the hub's `maintenance_steps` is its own
> registry, not 23.1's daemon `tick_registry` (ns17-1).

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[task-17.1-vectors-maintain-op]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns17-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns17-4]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns17-5]]
rel: implements -> [[plan-review-2026-10-14#t9-fixes]]
rel: related-to -> [[project_bus_retention_global_queues]]
rel: depends-on -> [[feedback_daemon_call_retries_multiply_timeouts]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14#t3]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: related-to -> [[task-19.4-keep-derived-layers-current]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns17-r3-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#nm17-r3-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#nm17-r3-3]]
rel: related-to -> [[plan-18-duckdb-store-maintenance#contract-2026-10-14]]

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
     `maintenance disabled (RMX_HUB_MAINTAIN_AT=off)` that also names every store whose live
     `facts.log` is excluded from Time Machine (`tmutil isexcluded <root>/facts.log`), because
     with `off` no daily copy is made for them (ns17-r3-3). `off` disables the STEPS only; the
     thread keeps running R8's backup-age check.
   - Stamps live in `~/.refmatrix/maintain.json`, keyed by (store root, step name):
     `{armed_at, last_attempt, last_success, consecutive_failures, last_outcome}`. Writes are
     atomic (tmp + rename) under an `fcntl` lock on `maintain.json.lock`, shared with R7's CLI.
   - A (store, step) is DUE when the most recent scheduled instant (today's 03:30 if now ≥ 03:30,
     else yesterday's) is later than its `last_attempt`. That gives catch-up after sleep (the
     first tick after wake runs a missed night) and no stacking (at most one attempt per store per
     step per scheduled day, however many nights were missed).
   - The clock (`now: Callable[[], datetime]`) is injected.
2. **R2 The step registry: the hub's own `maintenance_steps`** (plan-review C6; ns17-1).
   {#r2-registry}
   - It is NOT 23.1's `Daemon.tick_registry`, and shares nothing with it: that one runs in each
     store daemon every 30 s under ONE 5 s budget for drains and tails; this one runs in the hub
     once per scheduled day under a per-store budget of minutes. C6's "one tick, one stamp store"
     means THIS hub tick and `maintain.json`; d4a's "one registry" means the daemon's tick.
   - `maintenance_steps.register(MaintenanceStep(name, op, args, requires_arming, reason,
     after_idle=()))`, in a fixed order. `op` is a daemon op name; `args(root, dry_run, today) ->
     dict` builds its arguments (`today` is the injected clock's local date); `requires_arming:
     bool` and `reason` are stated by the registrant (R7); `after_idle: tuple[str, ...]` names
     earlier steps this one must not overlap (below).
   - **Every registered op must:** accept `dry_run` and `invoked_by="hub"`; be single-flight with
     the 17.1 R11 reply shape (`already_running`) and answer `status=True` lock-free; and append
     one line per completed run to the store's `<root>/maintain/runs.jsonl` (17.1 R12 shape, its
     own `step` name). A step that cannot meet these is not registered.
   - **Registration order** (ns17-r3-3): `factslog_backup` (17.4) FIRST, because it is cheap,
     lock-free and non-destructive and it is the only copy of the live log once 17.3 excludes it
     from Time Machine; then `vectors_maintain` (17.1); then 19.4's memory compile; then
     plan-18's DuckDB step.
   - **A store's steps are independent** (ns17-r3-3; plan-18 `#contract-2026-10-14` asked). Per
     store, the hub calls each DUE step in registration order:
     - after an earlier step's `ok`, `failed`, `refused`, `dry_run:unarmed` or `skipped:*`, the
       next step runs;
     - after an earlier step's `still_running` (R4) or `stuck`, the next step STILL runs at once,
       unless it names that step in `after_idle`; such a step is reported `deferred` for this
       store and stays due for the next tick. No plan-17 step declares `after_idle` (the backup
       copies from an open descriptor and is consistent under any concurrent write, 17.4 R2;
       `vectors_maintain` takes `_store_lock` in its own daemon). Plan-18 states whether its
       CHECKPOINT needs `after_idle=("factslog_backup",)` or more;
     - so nothing on one store, a hung compaction included, can stop the same store's backup.
3. **R3 Roots: the registered daemon list, injected** (spec review #b-5, #s-6). {#r3-roots}
   - The run takes `roots: Callable[[], list[Path]]`. The production default is the registered
     daemon list: the launchd-supervised roots (`discovery._roots_from_launchd()`,
     `discovery.py:70`, 8 today including the global store), sorted by resolved path. It is NOT
     `registry.json` (3 stores) and NOT `discover_roots()` (which adds the cwd root).
   - Per root: running = `daemon_mod.ping(root)` answers; paused = `Watchdog.is_paused(root)`
     (`hub.py:221`). A root that is paused or not running is skipped, named and counted in the
     summary (`skipped:paused`, `skipped:not_running`). Nothing runs in-process for a skipped
     store. There is no `not_supervised` outcome: every root comes from a plist by construction
     (nm17-2).
4. **R4 The call: retries=0, per-store budget, still-running is not failure** (d3e and its
   close-out amendment; decision review #s-6). {#r4-call}
   - Each step call is `daemon.call(root, op, args, timeout=RMX_MAINTAIN_STORE_TIMEOUT_S
     (default 600), retries=0)`.
   - A timeout, or an `already_running` reply (17.1 R11), is outcome `still_running`, never
     `failed`, and never counts toward R5. The hub moves on to the store's next step (R2); after
     the store's last step it polls EACH still-running step through THAT step's own op with
     `status=True` (`factslog_backup(status=True)`, plan-18's op, …; nm17-r3-3: not
     `vectors_maintain` for every step) every 30 s, until every one reports idle or the
     per-store budget `RMX_MAINTAIN_STORE_BUDGET_S` (default 1800) is spent; an op is never
     re-sent.
   - Serial: the next store does not start while one is `still_running`. If the budget is spent
     with the store still running, the run stops; the remaining due stores are reported
     `deferred` and stay due for the next tick, and the still-running store's final report is
     read through `status=True` on the next tick and stamped then.
   - **The ceiling (ns17-4).** A (store, step) still running across `RMX_MAINTAIN_STUCK_AFTER`
     (default 2) consecutive per-store budgets becomes outcome `stuck`: one alert is published to
     `global:queues` at once (it does not wait for `RMX_MAINTAIN_ALERT_AFTER`), it is never
     re-sent while its daemon still answers `already_running`, and it STOPS BLOCKING: the run
     moves on to the next store in the same tick. Serial order is a load rule, not a safety rule;
     the stores are separate daemons. When the stuck daemon later reports idle, its report is
     read, stamped, and `stuck` is cleared with one `hub.log` line.
5. **R5 Failure isolation and alert** (spec review #m-5). {#r5-alert}
   A `failed` or `refused` outcome is logged and counted per (store, step), and the next store
   still runs. After `RMX_MAINTAIN_ALERT_AFTER` (default 3) consecutive failed runs of one
   (store, step), one alert is published to `global:queues`; a success resets the count and the
   alert. An `orphan_cap` refusal (17.1 R6) alerts on its first occurrence and names the dataset
   and the release (`rmx vectors maintain --dry-run`, then `--confirm-orphans <sha>` by hand,
   once per capped dataset, d9c). A `stuck` outcome alerts per R4.
6. **R6 Report** (spec review #m-4). {#r6-report}
   One summary per run to `global:queues`: per outcome (`ok`, `dry_run:unarmed`, `skipped:*`,
   `refused:*`, `failed`, `still_running`, `stuck`, `deferred`) the store names; bytes reclaimed; `orphans`
   reaped; `missing` re-queued; holds over `RMX_MAINTAIN_HOLD_S`. Per-store detail goes to
   `hub.log`.
7. **R7 Arming, per (store, step), for every registered step** (spec review #s-3; d3d; ns17-5;
   d8g). {#r7-unarmed}
   - Each step declares `requires_arming` with a reason:

     | step | `requires_arming` | reason |
     |---|---|---|
     | `vectors_maintain` (17.1) | true | it deletes (orphans, old versions); d3d |
     | `factslog_backup` (17.4) | false | a copy that never deletes the last good copy and touches no store state (17.4 R5) |
     | 19.4 memory compile | stated by 19.4 | 19.4 owns its value and reason |
     | plan-18 DuckDB step | stated by plan-18 | plan-18 owns its value and reason |

     A step registered without both fields fails registration (an `AssertionError` at hub start,
     logged), so no step can arrive with an unstated policy.
   - A (store, step) with `requires_arming=true` and no `armed_at` stamp runs with `dry_run=True`
     only, reported `dry_run:unarmed`. Its `last_attempt` is stamped, so the dry run happens once
     per scheduled day. A step with `requires_arming=false` runs for real from its first day.
   - **Arming is one verb on both surfaces, gated by a hand run** (d8g: the gate is the record,
     not the surface; the verbs rule). Verb `hub_maintain_arm(root, step, run_id)`: CLI
     `rmx hub maintain arm --root <root> --step <step> --run-id <id>`, MCP parity through the
     verb-parity test. It reads `<root>/maintain/runs.jsonl` (17.1 R12) and refuses unless that
     file holds a line with this `run_id`, this `step`, `invoked_by` in `{"cli", "mcp"}` (a hand
     run on either surface; never `"hub"`), `dry_run: false` and `ok: true`, AND an EARLIER line
     (in file order) of the same `step` with `dry_run: true` and `ok: true` (nm17-r3-2: the gate
     proves d3d's ORDER, dry run then real run, not only a successful real run). `invoked_by` is
     set by the adapter, never by the caller (17.1 R1). On success it writes `armed_at` and `armed_by_run` for that (store, step), under
     R1's lock; it is the only writer of `armed_at`. `hub_maintain_disarm(root, step)` clears it
     and needs no run id. This settles the plan's former open item 4 (an agent can call the verb,
     but only after a real, successful hand run of that exact step on that store, which is the
     d3d order).

8. **R8 The backup-age alarm** (ns17-r3-3). {#r8-backup-age}
   - Each store daemon's `_store_health` (`daemon.py:3739`) reports `factslog_backup_age_h`,
     read from `<root>/backups/facts.log.daily.meta.json`'s `copied_at` (17.4 R4), and
     `factslog_backup_stale: true` when the age is over `RMX_FACTSLOG_BACKUP_STALE_H` (default
     48) or no copy exists. That surface needs no hub: `rmx daemon status` shows it with the hub
     down.
   - `rmx hub status` reports `factslog_backup_age_h` per registered store.
   - On EVERY `_maintain_loop` wake (every `RMX_HUB_MAINTAIN_TICK_S`), whether or not any step
     is due, and with `RMX_HUB_MAINTAIN_AT=off` too, the hub reads every registered root's meta
     file and publishes ONE alert to `global:queues` per store whose age is over the threshold,
     naming the store, the age and whether its live `facts.log` is excluded from Time Machine.
     The alert is not repeated while the store stays stale; a fresh copy clears it with one
     `hub.log` line.
   - What this cannot see, stated: with the hub down, no alert is published; the daemon's health
     surface still reports the staleness.

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
5. **AC-5 unarmed.** A store with no `vectors_maintain` stamp gets `dry_run=True` (its Lance
   version count and bytes are unchanged) and is reported `dry_run:unarmed`; after a successful
   hand run and `rmx hub maintain arm --step vectors_maintain --run-id <that run>` it gets the real
   op on the next due day.
6. **AC-6 retries and single-flight.** A tmp daemon whose `vectors_maintain` blocks past the
   timeout receives the op exactly ONCE (counted daemon-side by 17.1 R11's state), the outcome is
   `still_running`, the failure count is unchanged, and the second store is not called until the
   first reports idle.
7. **AC-7 budget.** With the per-store budget spent, the run stops, the remaining stores are
   `deferred`, and the next tick runs them after the first store is idle.
8. **AC-8 alert.** Three consecutive failures of one (store, step) give exactly one alert; a
   success resets it. A vectors step that succeeds and a second registered step that fails on the
   same store: only the failing step's count rises, and only it is due again next day.
9. **AC-10 stuck ceiling (ns17-4).** Two stores; store 1's op never returns (blocks on an event
   the test never sets) and answers `already_running` to `status=True`. With budget B and
   `RMX_MAINTAIN_STUCK_AFTER=2`: tick 1 ends with store 1 `still_running` and store 2 `deferred`;
   tick 2 ends with store 1 `stuck`, exactly one `stuck` alert on `global:queues`, store 2 RUN
   (its op received once), and store 1's op still received exactly once in total. Releasing the
   event: the next tick stamps store 1's report and clears `stuck`.
10. **AC-11 per-step arming (ns17-5).** One unarmed store with two registered test steps,
    `requires_arming=true` and `false`: the first is called with `dry_run=True`, the second with
    `dry_run=False`, on the first due day. Registering a step without `requires_arming` fails hub
    start with the named error.
11. **AC-12 the arm gate (ns17-5, d8g).** On a tmp store with `runs.jsonl`:
    - arm with the `run_id` of a successful non-dry hand run of that step → `armed_at` written;
    - arm with a dry run's id, a failed run's id, a `hub` run's id, another step's id, or an
      unknown id → refused, no stamp written;
    - arm with the id of a successful CLI (or MCP) real run that has NO earlier successful dry run
      of that step in `runs.jsonl` → refused (nm17-r3-2); after a dry run and a second real run,
      arming with the second run's id succeeds;
    - the verb is reachable through both the CLI and MCP (the verb-parity test lists it) and
      behaves identically through both.
12. **AC-13 step order and independence (ns17-r3-3, nm17-r3-3).** One store, three registered
    steps in production order: `factslog_backup`, then a test `vectors_maintain` op that blocks on
    an event the test never sets (the AC-10 shape), then a third test step; a fourth test step
    declares `after_idle=("vectors_maintain",)`. One due tick: the backup copies first (a new
    `.daily` exists), `vectors_maintain` is `still_running`, the third step RUNS (its op received
    once), the fourth is `deferred`. The hub's status polls go to `vectors_maintain`'s own op
    only, never to the other steps' ops with `vectors_maintain`'s name. With
    `factslog_backup` itself made to block, the later steps still run.
13. **AC-14 backup-age alarm (ns17-r3-3).** A store whose meta file says the copy is 3 days old
    and no step due (the injected clock before 03:30): the next wake publishes exactly one
    stale-backup alert naming the store; the following wakes publish none; a fresh copy clears it
    with one `hub.log` line. The same with `RMX_HUB_MAINTAIN_AT=off`, whose disable line names
    the stores whose live log is excluded. `_store_health` on that daemon reports
    `factslog_backup_stale: true` with the hub stopped.
14. **AC-9 pre-registered mutations, each must FAIL a named AC:**
   - no catch-up → AC-1;
   - stacking runs after sleep → AC-1;
   - maintenance moved back onto `_queue_alert_loop` → AC-2;
   - `discover_roots()` used as the default with the injection removed → AC-3;
   - the pause ignored → AC-4;
   - unarmed stores run for real → AC-5;
   - the `stuck` ceiling removed (still_running forever, others deferred) → AC-10;
   - `requires_arming` ignored (every unarmed step dry-runs, or every step runs for real) → AC-11;
   - the arm verb not checking `runs.jsonl` (any `run_id` accepted) → AC-12;
   - the arm gate without the earlier-dry-run condition → AC-12 (a real run with no dry run
     before it arms);
   - a later step skipped while an earlier one is `still_running` → AC-13;
   - `factslog_backup` registered after `vectors_maintain` → AC-13 (no copy while vectors
     blocks);
   - every still-running step polled through `vectors_maintain(status=True)` → AC-13;
   - `after_idle` ignored → AC-13 (the fourth step runs);
   - the backup-age check run only on due ticks, or not under `off` → AC-14;
   - the arm verb CLI-only (no MCP twin) → AC-12 (verb parity);
   - default `retries` → AC-6;
   - a timeout counted as failed → AC-6;
   - stamps keyed by store only → AC-8.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/hub.py` | `_maintain_loop`, the schedule check, `maintenance_steps`, the stamps, the `stuck` ceiling, the summary |
| `src/refmatrix/verbs.py`, `cli.py`, `mcp.py` | `hub_maintain_arm` / `hub_maintain_disarm` verbs on both surfaces |

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
| plan-review C6 / 23.1 tick registry | [[#r2-registry]] (settled in round 2: two registries) |
| d1a/d1b (23.0) | [[#test-strategy]] |

## Revision round 2 (2026-10-14) {#rev-round-2}

| finding / decision | answered at |
|---|---|
| ns17-1 (17.2's registry is not 23.1's; phantom dependency), #t9-fixes "17.2 keeps its own registry" | header, [[#r2-registry]] |
| ns17-4 (`still_running` has no ceiling), #t9-fixes | [[#r4-call]] (the ceiling), [[#r5-alert]], AC-10 |
| ns17-5 (arming only for vectors; verb class), #t9-fixes "arming per (store, step) for every registered step", d8g | [[#r2-registry]] (op obligations), [[#r7-unarmed]], AC-11, AC-12 |
| d9c (cap release named in the alert) | [[#r5-alert]] |
| nm17-2 (`skipped:not_supervised` unreachable) | [[#r3-roots]] |

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]].

| finding / decision | answered at |
|---|---|
| ns17-r3-3 (no staleness alarm after the TM exclusion; intra-store step order unstated; plan-18's order question) | [[#r1-schedule]] (`off` names excluded stores), [[#r2-registry]] (backup FIRST; steps independent; `after_idle`), [[#r4-call]], [[#r8-backup-age]], AC-13, AC-14, AC-9; 17.4 AC-8 |
| nm17-r3-2 (arm gate proves a run, not d3d's order; `invoked_by` defaults to "hand") | [[#r7-unarmed]] (earlier dry-run line; surface-valued `invoked_by`), AC-12, AC-9 |
| nm17-r3-3 (R4 polls `vectors_maintain(status=True)` for every step) | [[#r4-call]], AC-13 |
| nm17-r3-5 (19.4 AC-2 vs its own `requires_arming=True`) | not edited here (plan-19's file); handed to the 19/21 pair, see [[plan-17-nightly-store-maintenance#open-after-revision]] 6 |
| d9c (release per capped dataset) | [[#r5-alert]] |
