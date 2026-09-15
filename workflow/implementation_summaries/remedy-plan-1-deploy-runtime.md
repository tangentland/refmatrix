---
gmd: "0.1"
id: impl-remedy-plan-1-deploy-runtime
title: "Plan-1 remediation after ch-bsd bsd-plan1 (cabce24): the guard fires in the incident state"
tags: [implementation-summary, plan-1, remediation]
metadata:
  node_type: implementation-summary
  plan: plan-1-deploy-runtime
---

# Plan-1 remediation {#root}

rel: implements -> [[plan-1-deploy-runtime]]
rel: evidence-for -> [[bsd-plan1-deploy-runtime-cabce24]]

| Finding | Fix |
|---------|-----|
| #b-1 alert never gates on dev_tree | `hub._queue_row_is_hot(row)` includes `dev_tree`; `_queue_alert_loop` uses it; `test_gather_queues_carries_identity_end_to_end` drives the real `_gather_queues` with only discovery/daemon RPC patched |
| #b-2 verify skippable | `upgrade.upgrade()` calls `runtime_identity()` FIRST on every path and raises on `dev_tree`; the "already up to date" path runs `verify_editable`; `rmx daemon restart --relaunch` compares the new daemon's `code_path` to the CLI's import path and fails loud |
| #s-3 unknown rendered clean | `_daemon_identity` returns `{unknown, version}`; queue rows get `identity: unknown`; `hub status` prints `[UNVERIFIED vX]` / `[DEV TREE]` / clean as three states (CliRunner test) |
| #s-4 hub's own tree | `_op_hub_info` carries `version/code_path/dev_tree` (`_hub_identity`, cached); `hub status` prints the hub's `code:` line |
| #s-5 tests bypass wiring | end-to-end `_gather_queues` test; `hub status` test; mock registry rows added |
| #s-8 finder-style marker passes | `editable_target(strict=True)` raises "marker present but target unreadable"; `verify_editable` uses strict |
| #m-6 memory overstates | `feedback_deploy_tree_is_the_runtime` reworded; 19 legacy memories migrated to GMD frontmatter (`tools/gmd/migrate_memory.py`) + four legacy wikilinks repointed, so the bridge takes them |
| #m-7 identity per ping | `daemon._process_identity()` cached once per process, never raises |
| #m-9 status before gate | plan back to `in-progress`; task specs `complete`; `completed` only after CLEAN |

Also folded in (found by the plan-3 full suite): `SharedWorkerClient.info(timeout=)` bounded adoption probe (`RMX_SHARED_PROBE_TIMEOUT_S`, 5 s) and no reconnect-retry on `TimeoutError` — a mute `models.sock` cost a daemon 300 s (the wedge the watchdog SIGKILLed on 2026-09-14). `test_daemon_falls_back_when_shared_socket_does_not_answer` now passes in seconds; it timed out at the session-start commit too.

RED `workflow/review-output/pytest-remedy12-RED.log` (19 failed); GREEN `pytest-remedy12-GREEN.log`.

## Round 3 (bsd-plan1-r3, e6c4081) {#round-3}

rel: evidence-for -> [[bsd-plan1-deploy-runtime-r3-e6c4081]]

| Finding | Fix |
|---------|-----|
| #s-1-r3 FakeBus/FakeHub unregistered | two registry rows (`hub.bus`, `Hub` self with stubbed `_gather_queues`) |
| #m-2-r3 memory-dir lint dangling ADR links | the three links are correct ADR ids in `docs/adr/`; task 1.3 now names the scope (`scripts/lint-gmd.sh`, which lints memory dir + docs together → 0 errors) |
| #m-3-r3 ping-exception branch untested | `test_relaunch_fails_when_the_ping_itself_raises` (daemon.call raises OSError → exit≠0, "cannot be read") |
| #m-4-r3 `identity_error` read by nobody | `hub._daemon_identity` → `{unknown, version, error}`; `_annotate_identity` stamps `identity: unknown` + `identity_error` (hot row); `_verify_relaunch` raises "could not compute its identity"; `daemon status` prints `[UNVERIFIED]` + the error; `hub status` appends the error to `[UNVERIFIED vX]` |
| also-reviewed: `_queue_alert_once` bool | asserted in `test_queue_alert_once_reports_whether_it_published` |

TDD: RED `workflow/review-output/pytest-plan1-r3-red.log` (2 failed: identity_error unknown, status UNVERIFIED; the ping-exception and bool tests passed on arrival — regression guards, not drivers). GREEN `pytest-plan1-r3-green.log` (24 passed across test_plan1_remedy + test_runtime_identity_surface). Mutation: reverting the `identity_error` branch in `_daemon_identity` fails `test_daemon_identity_with_identity_error_is_unknown`.

## Round 4 (bsd-plan1-r4, 54fceb9) {#round-4}

rel: evidence-for -> [[bsd-plan1-deploy-runtime-r4-54fceb9]]

| Finding | Fix |
|---------|-----|
| #b-1-r4 `identity_error` never crossed the wire | `_op_ping` forwards `identity_error` from `_process_identity()`; `hub status` renders the hub's own `identity_error` as `[UNVERIFIED]` + the error; producer-side test `test_real_ping_carries_identity_error_and_every_consumer_sees_unknown` starts at `runtime_identity` raising, calls the REAL `_op_ping`, and feeds that dict to `_daemon_identity` and the relaunch guard |
| #s-2-r4 `rmx hub queues` traceback on a busy fleet | `verbs.queues` wraps `TimeoutError`/`OSError` into a `VerbError` naming the busy daemon; the CLI catches both; `_gather_queues` skips the 2 s identity ping for a root whose 10 s stats call failed and marks the row `identity: unknown` (hot) |
| #m-3-r4 plan-of-plans disagreed | plan-1 back to `in-progress` in BOTH places until CLEAN; plan-4 row now `in-progress` |
| #m-4-r4 RED covered 4 of 5 tests | `workflow/review-output/pytest-plan1-r3-red-all5.log`: all five r3 tests run against the pre-remedy commit (c9d75af) in a throwaway worktree — 3 failed (identity unknown, status UNVERIFIED, relaunch identity_error), 2 passed on arrival (ping-exception, bool) |

TDD: RED `pytest-plan1-r4-red.log` (4 failed), GREEN `pytest-plan1-r4-green.log` (94 passed across plan-1, identity, hub, watchdog, parity suites). Mutation: reverting the `_op_ping` forward fails the producer-side test at its first assertion.

Also found while closing: bug-008 ([[bug-registry#registry]]) — the live rewriter hook was overwritten with dev-tree paths a second time (21:43, by a dev-venv apply outside this session's tests); regenerated from the deploy build, durable fix deferred to plan 6.

## Round 5 (bsd-plan1-r5, 7b35e80) {#round-5}

rel: evidence-for -> [[bsd-plan1-deploy-runtime-r5-7b35e80]]

| Finding | Fix |
|---------|-----|
| #b-1-r5 third unregistered-mock strike | rows: `hub.status` (new), `hub.rpc`/`is_running` and `discovery.*` rows now name `tests/test_plan1_remedy.py` (and `test_plan3_remedy_r2.py`) |
| #b-2-r5 bug-008 deferral unanchored | `task-6.5-plan-6-deferrals-docs-benchmark` written with acceptance criteria (runtime wrapper resolution + foreign-tree refusal); plan-6 breakdown/`rel:` + plan-of-plans task count updated; deferral row points at it |
| #m-3-r5 dead `except` in `hub_queues` | deleted — `_hub_rpc` owns the wording |

Plan 1 → `completed` in the plan file and plan-of-plans, per the r5 verdict ("may flip in the commit that adds the rows and anchors the deferral"). No source behaviour changed beyond the dead-branch removal (`test_hub_queues_reports_a_busy_fleet_instead_of_a_traceback` still passes through the VerbError arm).

