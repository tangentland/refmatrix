---
gmd: "0.1"
id: impl-task-4.6-r5-remedy
title: "Task 4.6: plan-4 r5 remedy — one launchd restart helper, one binary resolver, the dev venv is a dev tree, the session plist joins the lifecycle, identity is not drift"
tags: [implementation-summary, plan-4, remedy, launchd, daemon, identity, bsd]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-10-19
---

# Task 4.6: plan-4 round-5 remedy (GREEN) {#root}

rel: implements -> [[task-4.6-r5-remedy]]
rel: part-of -> [[plan-4-daemon-resilience]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378]]
rel: depends-on -> [[impl-task-4.5-r4-remedy]]

Branch `plan4-remedy-w1` in the clone `/Volumes/littlebig/refmatrix-plan4-remedy`. RED commit
`9dd5b38`. GREEN: all 38 tests in `tests/test_task4_6_r5_remedy.py` pass
(`workflow/review-output/task4.6-green-file.log`). The plan-4, launchctl, upgrade and session
families are in `workflow/review-output/task4.6-green-families.log`, and the full suite is in
`workflow/review-output/task4.6-green-full.log`. See [[#suite]] for the results.

## B1: one launchd restart helper, and every failure is reported (r5 #b-1) {#b1}

- `launchctl.supervised_restart(root, *, log=print) -> tuple[str, bool]` is the sequence lifted
  out of `rmx daemon restart`, in this order:
  - watchdog pause (`grace * 2 + 60`, through `refmatrix.hub.rpc`, looked up at call time);
  - `daemon.graceful_stop(grace=stop_grace_s())`;
  - the "still alive … kickstart -k" line when the stop was ignored;
  - `kickstart(restart=not stopped)`;
  - the resume in a `finally`.

  A hub that is down is logged. A `kickstart` failure propagates. `cli._watchdog_pause` and
  `cli._watchdog_resume` moved into `launchctl` as `_watchdog_pause` and `_watchdog_resume`.
- `rmx daemon restart` (launchd branch) calls the helper. A failure is a `ClickException` that
  names the error and `--standalone`, and nothing is spawned. The old
  "kickstart failed …; restarting standalone" fallback is gone.
- `rmx daemon restart` also had its own `except Exception: loaded = False` around `is_loaded`.
  That was the same guess-unsupervised shape as B1.4. It is now a `ClickException` that names
  `--standalone`.
- `upgrade._default_restart(root, *, log=print) -> bool`:
  - On darwin it probes `launchctl.status`. If the probe raises, it logs and returns False.
  - When the store is loaded, it calls `supervised_restart`. If that raises, it logs (naming
    `rmx daemon restart --relaunch`) and returns False. `stop_daemon` is never called.
  - Otherwise it calls `stop_daemon(timeout=stop_grace_s(), report=rep)`. A False result logs
    the still-alive pid, the grace and "manually", and returns False. An exception is logged and
    returns False.
  - It says `daemon stopped` only after a real stop. `upgrade.py` has no `kickstart(` call.
- B1-root: `upgrade.upgrade(..., store_root=None)` hands `store_root` to `restart_fn`. With None
  it restarts nothing, logs `rmx daemon restart --relaunch` / `rmx hub relaunch-fleet`, and
  reports `restarted=False`. `rmx upgrade` passes `store_root=_root()` when that directory exists.

## S1: one binary resolver (r5 #s-1) {#s1}

- `launchctl._rmx_path()` resolves in this order:
  1. `$RMX_BIN`;
  2. else `os.path.abspath(sys.argv[0])` (symlinks not resolved) when its basename is
     `rmx`/`refmatrix` and it is an executable file;
  3. else `FileNotFoundError` naming `sys.argv[0]` and `RMX_BIN`.

  There is no `which rmx` fallback, and the unused `shutil` import is gone.
- `cli._plist_rmx()` wraps it as a `ClickException`. These commands resolve through it:
  - `daemon launchctl install` (including `--check` and `--allow-dev`);
  - `hub launchctl install` and `hub launchctl status`;
  - `hub relaunch-fleet` (when `--rmx` is not given);
  - `session launchctl install`.

  `cli.py` keeps no `sys.argv[0]` for plist purposes.
- The bug-013 bootstrap in `rmx daemon restart` is `lc.reinstall(root, rmx=_plist_rmx())`. It
  re-renders with `installed_flags`, so `--no-watch`, `--debounce-ms`, `--watch-root` and
  `RMX_PARTITION` survive.

## S2: a source tree that is not the deploy tree is a dev tree (r5 #s-2) {#s2}

- `upgrade.deploy_root() -> Path | None` returns `$RMX_DEPLOY_ROOT` (expanded and resolved), else
  `~/refmatrix`. It returns the path only when it holds a `pyproject.toml`.
- `runtime_identity` adds `deploy_root` and `dev_reason`. `dev_reason` is one of
  `venv-mismatch`, `no-deploy-tree`, `not-deploy-tree` or None.
  - Rule (a) is the existing mismatch.
  - Rule (b) applies when the import path is not under the prefix and `code_root` is set. If no
    deploy tree exists, the result is `no-deploy-tree` (fail closed). If `code_root` is a
    different tree, the result is `not-deploy-tree`.
  - A wheel install under the prefix is never dev by rule (b).
- `upgrade.dev_tree_message(ident)` writes the refusal for both rules. It reads the new keys with
  `.get`, so older identity dicts still work. When rule (b) fired, the message names
  `dev_reason`, `deploy_root` and `RMX_DEPLOY_ROOT`.
- `rmx version -v --json` carries both keys. Paths are written as strings, and a missing value as
  null. `-v` also prints `dev reason:` and `deploy root:`.

## S3: the session plist joins the lifecycle (r5 #s-3) {#s3}

- `session_launchctl` has the following functions:
  - `render_plist(..., rmx=None)` is pure.
  - `install(..., rmx=None, allow_dev=False)` runs `_refuse_dev_tree` first.
  - `running_pid(root)` reads the `pid = N` line.
  - `_wait_tick_done` waits up to `stop_grace_s()` for the tick and never signals it. A tick
    that outlives the grace raises "still running … plist was NOT rewritten".
  - After the bootout, `install` waits up to `launchctl.BOOTOUT_WAIT_S` (read at call time) and
    raises if the label is still loaded.
  - `installed_flags`, `check(root, *, rmx=None)` and `reinstall(root, *, rmx=None)` mirror the
    daemon's versions.
- `launchctl.plist_diff(have, want)` is the one diff for the daemon, hub and session checks. A
  missing `ExitTimeOut` reads `ExitTimeOut: installed None != rendered 45`.
- `rmx hub relaunch-fleet` checks every discovered root whose session plist is installed,
  whether or not its daemon is supervised. On drift it runs `slc.reinstall(root, rmx=rmx)` and
  prints `reinstalled … session-indexer plist`. Failures are printed per root and counted.
- `rmx session launchctl install --check` exits 1 and prints the reason without writing anything.
  `--allow-dev` uses the daemon command's help text.
- `_refuse_dev_tree`'s message now also names `rmx session launchctl install`.

## M1: an identity objection is not drift (r5 #m-1) {#m1}

- `launchctl.CheckReason(str)` carries `.kind`, one of `identity`, `drift`, `missing` or
  `unloaded`. `launchctl.reason_kind(why)` returns `drift` for a plain string.
- `check`, `check_hub` and `session_launchctl.check` return a typed reason. A True result still
  carries `""`.
- With an identity objection:
  - `daemon launchctl install --check` prints `binary not verified — …` and exits 1, with no
    DRIFT and no fix line. Drift output is unchanged.
  - `hub launchctl status` prints `binary not verified`.
  - `hub launchctl install --check` prints `binary not verified` and exits 1.
- `rmx hub relaunch-fleet` asks `_identity_objection(rmx)` once, before the loop. When the binary
  is not verified it prints `binary not verified — …`, names `--rmx <the deployed rmx>`, exits 1
  and touches no store.

## Suite {#suite}

The full suite in the clone gave 4 failed, 3032 passed and 19 skipped. There were zero
`DEV TREE` / `is a dev tree` failures. The 4 failures, by error text:

- `test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate`
  fails with dangling-doc errors in `docs/INDEX.md`. This is the known repo-scope gate.
- `test_plan4_remedy.py::test_plist_marks_the_daemon_supervised_and_adoption_is_gated` and
  `test_plan4_remedy_r2.py::test_reinstall_verifies_the_label_is_loaded_afterwards` both fail
  with `FileNotFoundError: cannot tell which rmx …`. They render a plist without `RMX_BIN` or
  `deployed_rmx`, and passed only through the removed `which rmx` fallback. They need the
  `deployed_rmx` fixture (the [[task-4.6-r5-remedy#m2]] rule), but they are not in the migrated
  list.
- `test_upgrade.py::test_from_dev_promote_fast_forwards_and_installs` expects `restarted=True`
  from an `upgrade(...)` call that passes no `store_root`. That contradicts AC-7
  (`test_upgrade_without_a_store_root_restarts_nothing`), so the call needs `store_root=`.

No test was edited by the implementer.

## Not done here {#not-done}

- There is no version bump: release-merge bookkeeping owns it.
- The task 3.4 verb lists live on another branch and were not touched.
