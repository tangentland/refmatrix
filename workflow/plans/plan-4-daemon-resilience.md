---
gmd: "0.1"
id: plan-4-daemon-resilience
title: "A read never kills the daemon; index corruption is repaired in-band; supervisors never SIGKILL a working daemon"
tags: [plan, remediation, bsd]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-09-14
  bsd_findings: "#bs-3, incident 2026-09-14, G3, G9"
---

# Proposed Plan: A read never kills the daemon; index corruption is repaired in-band; supervisors never SIGKILL a working daemon {#root}

**Date:** 2026-09-14
**Status:** Accepted
**Location:** `workflow/plans/plan-4-daemon-resilience.md` — permanent home; stage is `metadata.status`.

rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: specifies -> [[task-4.1-plan-4-daemon-resilience]]
rel: specifies -> [[task-4.2-plan-4-daemon-resilience]]
rel: specifies -> [[task-4.3-plan-4-daemon-resilience]]
rel: specifies -> [[task-4.4-plan-4-daemon-resilience]]

## Context {#context}

BSD #bs-3 + the 2026-09-14 incident: `_op_learn_from_grep` (fed by every `rmx grep` miss, including the PreToolUse rewrite)
upserts entities unguarded; with a drifted entities PK/UNIQUE ART index the daemon fast-exits, launchd respawns it, the next grep
kills it again (39 runs). Boot-time repair rebuilds only `idx_entity_links_lk_concept`. The corruption itself came from the hub
watchdog `kickstart -k` (SIGKILL) on a daemon that was merely reconnecting to an idle-evicted model worker. Separately, the
orderly launchd service spawned 11,251 times behind a manual unsupervised daemon.

## Proposed Approach {#proposed-approach}

1. Read surfaces degrade: `_op_learn_from_grep` catches DuckDB fatals, logs `learn skipped: store invalid`, returns
   `{"added": 0, "skipped": "store-invalid"}`, and sets `d._repair_needed = "entities"` + writes `.refmatrix/repair.needed`.
   Fast-exit remains for write ops.
2. `rmx repair-index --entities` (in-band, daemon-routed op `repair_entities`) = the offline recipe: rebuild `entities` from
   itself with fresh PK/UNIQUE + 5 secondary indexes, abort on real dup groups, CHECKPOINT; boot runs it when `repair.needed`
   exists (before serving) and clears the marker; `daemon status` shows `repair pending`.
3. Watchdog: a daemon heartbeat file (`.refmatrix/heartbeat`, touched every 5 s by a thread that holds no locks) lets
   `hub.Watchdog._check` classify `dead` (pid gone or heartbeat > 60 s stale) vs `busy` (pid alive, heartbeat fresh, ping slow);
   busy never restarts; `_restart` sends graceful `daemon stop` first and only `kickstart -k` after `RMX_HUB_KILL_GRACE_S` (30).
   The model-worker reconnect path becomes non-blocking for the ping responder.
4. `rmx daemon start` under a supervisor that finds an unsupervised live daemon on the same root: stop it gracefully, adopt the
   root, log `adopted unsupervised daemon pid=…` — no permanent exit-1 loop. Apply to orderly.

## Open Questions {#open-questions}

### Q1: Q1 Repair in the daemon process or a lean subprocess? {#q1}
**Status:** RESOLVED

**Decision:** In the daemon at boot BEFORE the store is opened for serving (single writer, no contention); the 0.3 s rebuild on 75k rows makes it cheap.
**Rationale:** see Decisions Log.

### Q2: Q2 Heartbeat file vs richer ping? {#q2}
**Status:** RESOLVED

**Decision:** File. A ping that must go through the socket accept loop is exactly what blocks when the daemon is busy.
**Rationale:** see Decisions Log.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Q1 Repair in the daemon process or a lean subprocess? | In the daemon at boot BEFORE the store is opened for serving (single writer, no contention); the 0.3 s rebuild on 75k rows makes it cheap. | 2026-09-14 |
| Q2 | Q2 Heartbeat file vs richer ping? | File. A ping that must go through the socket accept loop is exactly what blocks when the daemon is busy. | 2026-09-14 |
| Q3 | (task 4.3) Move the model-worker reconnect off the ping responder? | Not as separate machinery: the probe is already bounded (plan 1, `PROBE_TIMEOUT_S` 5 s, no retry) and runs on the worker pool, and with the heartbeat file the supervisor no longer reads the ping for liveness at all. Recorded in [[impl-task-4.3-plan-4-daemon-resilience#responder]]. | 2026-09-14 |
| Q5 | (r1 #s-7) What does the heartbeat prove? | Serving progress, not scheduling: once the cli pool exists the tick is a no-op the pool must complete within the interval; a deadlocked pool stops the heartbeat and the watchdog's wedged branch is reachable for a 0.69 daemon. Before the pools exist (store open, boot repairs) the tick is unconditional. Amends Q2. | 2026-09-14 |
| Q6 | (r1 #b-2/#b-3/#m-9) When may a supervisor signal or kill? | Signal first, wait after: `hub.graceful_stop` sends the `stop` op (or SIGTERM) and THEN waits `RMX_HUB_KILL_GRACE_S`; `daemon.stop_daemon` escalates to SIGKILL only when the heartbeat is stale or absent (a wedge) and reports what it did; adoption (gated on `RMX_SUPERVISED=1`, set by the plist) asks a live-or-busy predecessor to stop and the startup reap YIELDS to a fresh heartbeat instead of killing. | 2026-09-14 |
| Q7 | (r1 #b-4/#m-10) Which detector queues the repair? | Every one: `_fast_exit_if_invalidated` writes `repair.needed` before exiting; a degraded read arms a deferred exit (`RMX_DEGRADE_EXIT_S`, 2 s) so the boot repair is seconds away, not "next op". | 2026-09-14 |
| Q8 | (r1 #b-6) How does a deploy reach every store? | `rmx hub relaunch-fleet` (per supervised root: `daemon restart --relaunch`, verified) is the deploy step; `rmx hub status` prints each daemon's version and flags one that differs from the hub's as STALE. | 2026-09-14 |
| Q9 | (r2 #b-2, amends Q5) When does the heartbeat tick? | On COMPLETION of the no-op the cli pool ran, however late (`add_done_callback`): a saturated pool that is making progress ticks at its own pace; only a no-op that never completes (deadlock) stops the beat. r1 waited one interval and discarded a late result, so a busy daemon read as a wedge after 60 s. | 2026-09-15 |
| Q10 | (r2 #b-1/#b-4) What makes a start supervised, and how is the plist kept current? | `daemon.is_supervised_start`: `RMX_SUPERVISED=1` OR launchd's own `XPC_SERVICE_NAME` naming a `com.refmatrix.daemon.*` label (no re-render needed). The unsupervised gate is typed (`refuse_unsupervised_start`: up → refuse, busy → refuse, absent → serve; never reaps). `rmx daemon launchctl install --check` compares the installed plist with its render (flags recovered from the installed ProgramArguments); `relaunch-fleet` reinstalls a drifted plist (verified loaded) before restarting. | 2026-09-15 |
| Q11 | (r2 #b-3/#s-5, amends Q6) One stop order for every supervisor | `daemon.graceful_stop` (stop op if ping answers, else SIGTERM at t=0, THEN the grace, never SIGKILL) is the one implementation; `stop_daemon` = graceful_stop + (SIGTERM if the stop op was ignored) + the heartbeat-gated SIGKILL; `hub.graceful_stop` delegates. `RMX_HUB_KILL_GRACE_S` defaults to 45 s (3 pool drains at 10 s + the store close), and the watchdog waits one more grace before `kickstart -k` while the pid is alive with a fresh heartbeat (it is shutting down). | 2026-09-15 |
| Q4 | (task 4.4) Operator step for orderly? | None: the supervised start adopts the unsupervised daemon on its own; the deploy at 21:54 did it (pid 39128 → 27922, launchd `runs` static). | 2026-09-14 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 4.1 | learn_from_grep never fast-exits | — |
| 4.2 | repair-index --entities, in-band and at boot | 4.1 |
| 4.3 | Heartbeat + watchdog grace + graceful restart | — |
| 4.4 | Supervised start adopts an unsupervised daemon; fix orderly | — |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation check on every new test;
implementation summary per task under `workflow/implementation_summaries/`; then `@ch-bsd` over the plan's commit range —
remedy and re-review until the verdict is CLEAN; then the plan's `metadata.status` → `completed`.
