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
