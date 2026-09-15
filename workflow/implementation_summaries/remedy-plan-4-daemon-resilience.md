---
gmd: "0.1"
id: impl-remedy-plan-4-daemon-resilience
title: "Plan-4 remediation after ch-bsd plan-4 r1 (6ae4b6f): signal first, never kill a working daemon, every detector repairs, the whole fleet relaunches"
tags: [implementation-summary, plan-4, remediation]
metadata:
  node_type: implementation-summary
  plan: plan-4-daemon-resilience
---

# Plan-4 remediation (round 1) {#root}

rel: implements -> [[plan-4-daemon-resilience]]
rel: evidence-for -> [[bsd-plan4-daemon-resilience-r1-6ae4b6f]]

| Finding | Fix |
|---------|-----|
| #b-1 abort swallowed inside `ok:true` | `_op_repair_entities` RAISES `RepairAbort`; `_handle` answers `ok:false`; the CLI prints the abort and no success line |
| #b-2 adoption SIGKILLed a busy predecessor; offline repair opened the writer | `_adopt_unsupervised` classifies by ping + heartbeat (busy with a fresh heartbeat is WORKING: stop request + grace, never a kill); `_reap_predecessor` YIELDS to a fresh heartbeat; `daemon.stop_daemon` withholds SIGKILL while the heartbeat is fresh and reports it; `repair-index --entities` refuses a busy daemon — Q6 |
| #b-3 grace spent before any signal | `hub.graceful_stop(root, grace)`: `stop` op (or SIGTERM) FIRST, then the grace; `_restart(alive=True)` uses it before `kickstart -k`; timed on a real SIGSTOPped daemon — Q6 |
| #b-4 one of eight detectors queued the repair | `_fast_exit_if_invalidated` writes `repair.needed` from every detector — Q7 |
| #b-5 SQLite branch wiped the graph | `rebuild_entities_indexes` refuses non-DuckDB with `RepairAbort`; test on an `RMX_BACKEND=sqlite` store proves the rows survive |
| #b-6 5 of 8 stores never relaunched; no surface showed it | `rmx hub relaunch-fleet` (per supervised root, verified) + `hub status` prints each daemon's version and `STALE (hub vX)`; the live fleet was relaunched with the deployed binary (all 8 on 0.69.1 with heartbeats) — Q8 |
| #s-7 heartbeat proved scheduling only | the tick is a no-op the cli pool must complete within the interval; a dead pool stops it — Q5 |
| #s-8 unregistered mocks | four registry rows |
| #m-9 adoption unconditional | gated on `RMX_SUPERVISED=1` (set by the daemon plist); a manual foreground start on a running store refuses |
| #m-10 invalidated store served until an unrelated op | a degraded read arms a deferred exit (`RMX_DEGRADE_EXIT_S`) — Q7 |
| #m-11 boot wiring unproven | `test_boot_repair_runs_on_a_spawned_daemon` |
| #m-12 `stop_daemon` swallowed the stop failure | `report=` dict (`stop_op`, `kill`) filled and logged by adoption / the watchdog |

TDD: RED `workflow/review-output/pytest-plan4-r1-red.log` (14 failed / 2 passed), GREEN `pytest-plan4-r1-green.log` (16 passed) + `pytest-plan4-r1-green-suites.log`. Mutations `pytest-plan4-r1-mutations.log`: (A) returning the abort dict again fails the op test; (B) dropping the marker from the fast-exit fails the boot-repair-queued test; (C) sleeping the grace before the signal fails `test_graceful_stop_on_a_live_daemon_returns_quickly` (the SIGSTOPped-daemon timing test cannot see the order — both shapes cost the grace there); (D) SIGKILLing with a fresh heartbeat fails the busy-predecessor test.

## Round 2 (bsd-plan4-r2, e1dba80) {#round-2}

rel: evidence-for -> [[bsd-plan4-daemon-resilience-r2-e1dba80]]

| Finding | Fix |
|---------|-----|
| #b-1 the adoption gate rode `RMX_SUPERVISED` in a plist no deploy step re-rendered (2 of 8 live labels without it; a supervised start on them exits 1 into KeepAlive) | `daemon.is_supervised_start()`: `RMX_SUPERVISED=1` OR launchd's own `XPC_SERVICE_NAME` naming a `com.refmatrix.daemon.*` label — no re-render needed. `launchctl.installed_flags` / `check` (installed plist == its render, flags recovered from the installed ProgramArguments; env keys / args named in the drift message) / `reinstall` (force, then a plain install if the forced one left the label unloaded — the thiquet shape). `rmx daemon launchctl install --check` (exit 1 on drift); `rmx hub relaunch-fleet` reinstalls a drifted plist, verified loaded, BEFORE restarting the process — Q10. Deploy step: relaunch-fleet re-renders the two live plists |
| #b-2 the serving-derived heartbeat ticked only when the cli pool answered within the interval — a busy daemon read as a wedge after 60 s | the no-op's completion touches the file (`add_done_callback`), however late; only a no-op that never completes stops the beat. `_SlowPool` (completes at 3× the interval) advances the file; `_DeadPool` does not — Q9 amends Q5 |
| #b-3 `stop_daemon` spent its grace before the first signal (sibling of the r1 hub fix; 4th fix-at-the-quoted-line) | `daemon.graceful_stop` (stop op if ping answers, else SIGTERM at t=0, then the grace, never SIGKILL) is the one implementation; `stop_daemon` = graceful_stop → SIGTERM if the delivered stop op was ignored → the heartbeat-gated SIGKILL; `hub.graceful_stop` delegates and logs. On a silent daemon the SIGTERM lands within 1.5 s of the call — Q11 |
| #b-4 bare `ping` gate in `serve_foreground` reaped a busy daemon | `refuse_unsupervised_start`: up → "already running", busy → "busy pid=… not reaping it", absent → serve; the test proves the busy predecessor survives and keeps its socket. The gate is a helper: a RED run that reached `serve_forever` took the pytest process over (bug-009 shape, avoided) |
| #s-5 `kickstart -k` after the grace could SIGKILL a daemon mid-close | `RMX_HUB_KILL_GRACE_S` defaults to 45 s (3 drains × 10 s + the store close); `_await_shutdown`: while the pid is alive with a heartbeat younger than the grace, wait one more grace (or until it exits / goes stale) before the kick — Q11 |
| #m-6 `repair_entities` never driven through the dispatcher | `test_repair_entities_abort_reaches_the_wire_and_the_daemon_keeps_serving`: a socketpair request through the real `Daemon._handle` → `ok:false, "repair aborted…"`, no `os._exit`, `ping` still answers |
| #m-7 registry rows named the wrong files | the watchdog row lists `test_plan4_remedy.py` / `_r2.py` and their extra fakes; `hub.graceful_stop` replaces `daemon.stop_daemon`; `_SlowPool` and the socketpair dispatcher rows added |
| #m-8 task 4.1 spec contradicted Q7 | spec title + requirement amended: the read never fast-exits, the marker is written, the daemon exits within `RMX_DEGRADE_EXIT_S` |

Found on the way: `daemon.is_alive` answered True for a zombie (our own SIGTERM'd child before `wait`), so the signal-first test saw the whole grace elapse and then a stale-heartbeat SIGKILL; `is_alive` now reaps/sees a child zombie via `waitpid(WNOHANG)` (bug-012).

TDD: RED `workflow/review-output/pytest-plan4-r3-red.log` (15 failed / 1 passed — the dispatcher wiring test held already, which is what #m-6 asked to see), GREEN `pytest-plan4-r3-green.log` (68 passed across plan4_remedy(_r2), hub_watchdog(_grace), daemon_adopt, repair_entities, daemon_learn_guard, plan5_remedy, launchctl_label; then 32 passed for the two plan-4 files after `test_relaunch_fleet…` learned about the drift check). Mutations `pytest-plan4-r3-mutation.log`: (A) heartbeat back to tick-within-interval → heartbeat test fails; (B) gate ignores `XPC_SERVICE_NAME` → 2 supervised tests fail; (C) grace before the signal → signals-first test fails; (D) `relaunch-fleet` never checks the plist → its test fails.
