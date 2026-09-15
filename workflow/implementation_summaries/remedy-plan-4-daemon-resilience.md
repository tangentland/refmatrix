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

## Round 4 (bsd-plan4-r3, ef4365a) {#round-4}

rel: evidence-for -> [[bsd-plan4-daemon-resilience-r3-ef4365a]]

| Finding | Fix |
|---------|-----|
| #b-1 the deploy step was a bare `launchctl kickstart -k` under launchd's 5 s ExitTimeOut — five daemons SIGKILLed mid-drain; `_verify_relaunch` SIGKILLed a predecessor that answers ping; the standalone restart spawned beside a live predecessor | `launchctl.EXIT_TIMEOUT_S` (45) in the plist (`ExitTimeOut`) = the hub's grace = `daemon.DEFAULT_STOP_GRACE_S` (`stop_grace_s()`, `RMX_STOP_GRACE_S`); `daemon restart` under launchd: pause → `graceful_stop` → kickstart without `-k` when stopped, `-k` said otherwise; `_verify_relaunch` kills only on a stale heartbeat (a fresh one: loud failure); the standalone path refuses to spawn while the predecessor lives — Q12. Live acceptance 2026-09-15 05:27–05:40 (`deploy-r6-r4.log`): two `relaunch-fleet` runs, all 9 labels `exit timeout = 45`, **0 launchd SIGKILL lines on `com.refmatrix.*`** (24 in the 4 h before) |
| #b-2 `_await_shutdown` read a heartbeat the shutdown stops first — unreachable from its caller's state (0.0 ms in the r3 probe) | the daemon writes `shutdown.started` as the first act of shutdown (removed at boot); `_await_shutdown` waits on the marker bounded by `SHUTDOWN_BUDGET_S`; proven through `Watchdog._check` on a real process that traps SIGTERM, writes the marker and drains 3 s — the kick lands after it is gone — Q13 |
| #s-3 the no-process branch kicked inside a relaunch's throttle gap; nothing paused the watchdog | two consecutive no-process ticks; `daemon restart` pauses/resumes the watchdog for the root via the hub RPC, best-effort — Q14 |
| #s-4 `check` / `reinstall` rendered against `which rmx` and nothing refused a dev tree | `rmx=` threaded from `relaunch-fleet` through `check` / `reinstall` / `install` / `render_plist`; `binary_identity` asks the binary (`rmx version -v --json`, new); `install` refuses a dev tree before writing, `check` names it — Q15 |
| #m-5 `stop_daemon` dropped the ping-discovered pid | `report["pid"]` from `graceful_stop`, escalation on it — Q16 |
| #m-6 `_touch` swallowed OSError | `Daemon._heartbeat_touch` logs once per errno — Q16 |
| (found on the way) `reinstall` on plist drift = `install(force=True)` = a bootout, which is the same SIGTERM + 5 s SIGKILL on the OLD plist — the drift fixer would have killed every draining daemon on its first run; and the hub's own plist had no ExitTimeOut either (launchd SIGKILLed the hub at 04:26:17 on my own `kickstart -k`) | `install(force=True)` asks the daemon to stop with the grace before the bootout (a clean exit 0 is not respawned by KeepAlive, so the bootout unloads an idle job); `render_hub_plist` carries `ExitTimeOut`; `install_hub(force=True)` sends the hub's `stop` op and waits for its socket to go before the bootout — tests `test_forced_install_stops_the_daemon_gracefully_before_the_bootout`, `test_hub_plist_carries_the_exit_timeout_too`, `test_forced_hub_install_stops_the_hub_before_the_bootout` |
| (found on the deploy) `install_hub(force=True)` printed `hub supervised` and the hub label was gone: a 3 s bootout wait, a bootstrap on a job still unloading, then launchd finished the bootout (bug-022, bug-013's hub twin). The fleet then relaunched with the hub down and every daemon went private for good (16 model processes; the shared rerank fell to 16–25 s for 10 docs — bug-024, todo G14) | `install_hub` waits `BOOTOUT_WAIT_S` for the unload (error otherwise), bootstraps through one helper, settles `HUB_SETTLE_S` and re-checks, bootstrapping once more when the label vanished; `_hub_install_fakes` drives launchd as a state machine (three tests; mutations P4-P/Q). The dev-tree refusal test now fakes every launchd surface (bug-023: mutation P4-G had installed a real agent for a tmp root) |
| #m-7 bug-014's fakes unregistered | the bug-015 row names `_Fine`, the client socket closed before the reply, and the stale-reference drop |

TDD: RED `workflow/review-output/pytest-plan4-r4-red.log` (16 failed / 3 passed; the draining-predecessor test was then tightened past the old 5 s grace and re-run RED), GREEN `pytest-plan4-r4-green.log` (19 passed). Mutations `pytest-plan3-r6-plan4-r4-mutation.log` P4-A…K: ExitTimeOut removed, `-k` without a stop order, the heartbeat gate removed, `_await_shutdown` back on the heartbeat, the dead branch on one tick, the marker never written, the dev-tree refusal removed, the discovered pid dropped, the standalone spawn beside a live predecessor, the touch failure silent, no watchdog pause — each fails the test that names it.

