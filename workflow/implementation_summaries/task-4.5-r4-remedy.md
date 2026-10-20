---
gmd: "0.1"
id: impl-task-4.5-r4-remedy
title: "Task 4.5: plan-4 r4 remedy — unknown binary fails closed, one stop grace, a reachable --allow-dev, the session indexer's ExitTimeOut"
tags: [implementation-summary, plan-4, remedy, launchd, daemon, bsd]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-10-19
---

# Task 4.5: plan-4 round-4 remedy (GREEN) {#root}

rel: implements -> [[task-4.5-r4-remedy]]
rel: part-of -> [[plan-4-daemon-resilience]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r4-ffed3df]]

Branch `plan4-remedy-w1` in the clone `/Volumes/littlebig/refmatrix-plan4-remedy`. RED commit
`a8e30f3` (22 RED, 3 GREEN by design). GREEN: all 25 tests in `tests/test_task4_5_r4_remedy.py`
pass (`workflow/review-output/task4.5-green.log`).

## R1 — an unknown identity fails closed (r4 #s-2) {#r1}

`launchctl._identity_objection(rmx) -> str | None` is now the ONE reading of `binary_identity`.
It returns None only for an explicit `dev_tree is False`; `True` names the dev tree; anything else
(None: a version-line binary, a non-zero exit, a missing path) reads `identity unknown` and names
the identity `error`. The three former `if ident.get("dev_tree"):` sites converge on it:

- `_refuse_dev_tree` raises `RuntimeError("refusing to render a plist: <why>. … --allow-dev …")`;
- `check` and `check_hub` return `(False, "<why>; … not rendered against it …")` before any
  render, so an unknown binary is never reported as `drifted` drift for `relaunch-fleet` to fix.

## R2 — one stop grace on every stop path (r4 #s-3) {#r2}

- `daemon.stop_daemon(root, *, timeout: float | None = None, report=None) -> bool` — None resolves
  `stop_grace_s()`. Paths 1 (`rmx daemon stop`), 5 (`rmx compact`), 6 (`upgrade._default_restart`)
  and 8 (hub UI `POST /api/daemon stop`) call it without a timeout and so take the one grace.
- Path 7: `launchctl.install(force=True)` calls `graceful_stop(grace=daemon.stop_grace_s())`.
- Path 4: `cli` `_respawn` (the `--relaunch` kick) stops with `stop_grace_s()` and on a False raises
  a `ClickException` naming the still-alive predecessor; it never spawns beside it.
- Unchanged by design: the hub watchdog (`RMX_HUB_KILL_GRACE_S`) and adoption (`ADOPT_GRACE_S`).

## R3 — `--allow-dev` on the daemon plist (r4 #m-5) {#r3}

`rmx daemon launchctl install --allow-dev` (help text identical to the hub's) forwards to
`launchctl.install(allow_dev=)`. The refusal names the CLI flag, not the Python parameter. The
generated CLI tree lists commands, not options: `scripts/gen-cli-tree.py --check` is clean.

## R4 / R5b / R6 {#r4-r6}

- R4: `session_launchctl.render_plist` sets `"ExitTimeOut": int(EXIT_TIMEOUT_S)`, imported from
  `launchctl` — one source.
- R5b: the `Watchdog._await_shutdown` line now reads `watchdog <root>: pid=… still alive …`.
- R6: `docs/architecture/todo.md` G9 → Done (task 4.4, `tests/test_daemon_adopt.py`, this spec);
  plan-4 `#status-2026-10-01` gains one CLOSED row per finding.

rel: depends-on -> [[task-4.4-plan-4-daemon-resilience]]

## Tests this change breaks on purpose (for ch-test-engineer) {#broken-tests}

Six pre-existing tests rendered or installed the HUB plist against a binary whose identity is
unknown, without `allow_dev` — they passed only because of the r4 #s-2 defect:

- `tests/test_launchctl_label.py::test_hub_plist_disables_objc_fork_safety` (fake rmx `exit 0`);
- `tests/test_plan4_remedy_r3.py::test_hub_plist_carries_the_exit_timeout_too` and the four
  `test_forced_hub_install_*` tests (`RMX_BIN=/usr/local/bin/rmx`, which does not exist).

They now fail with `identity unknown`. The fix belongs in the tests (pass `allow_dev=True`, or a
binary answering `dev_tree: false`), not in the guard. No test was edited here.

## Verification {#verification}

Related files: `workflow/review-output/task4.5-related.log` (baseline at the RED commit:
`task4.5-related-baseline.log`); full suite: `workflow/review-output/task4.5-green-full.log` —
26 failed, 2970 passed, 19 skipped. By error text: 19 are the clone-only DEV TREE refusals
(`.venv-eval/bin/rmx` imports the clone's `src/`; plan1 ×2, plan4-remedy-r2 ×10, r3 ×2, upgrade ×4,
`test_onboard_huballd_curator::test_hub_plist_renders_valid`), 1 is the gmd repo-scope gate
(the clone has no memory dir), and 6 are [[#broken-tests]] (`identity unknown`). The DEV TREE
refusals' wording changed (`refusing to render a plist: <rmx> is a dev tree: it imports …`) but
not their cause. `scripts/gen-cli-tree.py --check` clean; GMD lint: zero errors in the files this
task touched.
