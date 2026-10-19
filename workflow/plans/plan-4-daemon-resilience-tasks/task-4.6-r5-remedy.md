---
gmd: "0.1"
id: task-4.6-r5-remedy
title: "Task 4.6: plan-4 round-5 remedy — upgrade honours a failed stop and restarts through the shared launchd helper, one binary resolver for every plist command, the dev venv reads as a dev tree, the session indexer joins the plist lifecycle, identity is not drift"
tags: [task, plan-4, remedy, bsd, launchd, daemon, identity]
metadata:
  node_type: task
  status: approved
  plan: plan-4-daemon-resilience
  wave: W1-a
  created: 2026-10-19
---

# Task 4.6: plan-4 round-5 remedy (W1-a) {#root}

> Plan: [[plan-4-daemon-resilience]]
> Ledger: [[bsd-plan4-daemon-resilience-r5-390f378]]
> Predecessor: [[task-4.5-r4-remedy]] (RED `a8e30f3`, GREEN `8e20890`, test fixes `390f378`)
> Status: Approved — TDD RED written (`tests/test_task4_6_r5_remedy.py`, plus the migrated tests
> listed in [[#m2]])
> Decisions: the orchestrator's decisions for B1, S1, S2, S3, M1 and M2 are final. This spec
> records them and adds the details they leave open. Each added detail is marked **(spec)**
> and has its reason next to it.

rel: part-of -> [[plan-4-daemon-resilience]]
rel: amends -> [[plan-4-daemon-resilience]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378]]
rel: depends-on -> [[task-4.5-r4-remedy]]

## Scope {#scope}

This task covers all six r5 findings: #b-1, #s-1, #s-2, #s-3, #m-1 and #m-2. Once this task is
done and a ch-bsd r6 comes back CLEAN, plan-4 can flip to `completed`. The B1 work also turned up
a sibling defect that r5 did not name: `rmx upgrade` hands its restart the *repo* root, not a
store root. See [[#b1-root]].

rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378#b-1]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378#s-1]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378#s-2]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378#s-3]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378#m-1]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378#m-2]]

## Requirements {#requirements}

### B1 — `rmx upgrade` honours a failed stop and restarts through the ONE launchd helper {#b1}

`upgrade._default_restart` (`upgrade.py:298-320` at `390f378`) has four defects:

- it throws away `stop_daemon`'s False;
- it prints `daemon stopped`;
- it returns True while the predecessor is still alive;
- its launchd branch is the bare `kickstart -k` that r3 #b-1 removed from `rmx daemon restart`.

It also has two `except Exception: pass` blocks. If the launchd probe or `kickstart` raises, the
code falls through to stopping a SUPERVISED daemon. That daemon exits 0, so KeepAlive does not
respawn it, and the next read starts an unsupervised daemon beside the label. This is bug-013.

Requirements:

1. **One helper.** `launchctl.supervised_restart(root, *, log=print) -> tuple[str, bool]` returns
   `(label, stopped)`. It is the launchd restart sequence lifted unchanged out of `rmx daemon
   restart` (`cli.py:3256-3284`):
   - pause the hub watchdog for `root` for `grace * 2 + 60` s;
   - `daemon.graceful_stop(root, grace=daemon.stop_grace_s())`;
   - when that returns False, log the "still alive after the … grace; launchd kickstart -k will
     SIGTERM it and SIGKILL it at ExitTimeOut" line;
   - `kickstart(root, restart=not stopped)`;
   - resume the watchdog in a `finally`.

   The watchdog pause and resume go through `refmatrix.hub.rpc`, looked up on the module at call
   time so the existing r3 fakes still apply. A hub that is down is logged and the restart goes
   on. That is today's `_watchdog_pause` / `_watchdog_resume`, which move into the helper or are
   called by it. A `kickstart` failure propagates as an exception and is never swallowed.
2. **Both callers use it.** `rmx daemon restart` (launchd branch) and `upgrade._default_restart`
   (launchd branch) both call `launchctl.supervised_restart`. No second hand-rolled sequence
   remains: `upgrade.py` contains no `kickstart(` call of its own.
3. **A kickstart failure never falls through to a stop.**
   - `_default_restart`: catches the helper's exception, logs it naming the error and the manual
     fix (`rmx daemon restart --relaunch`), and returns False. `stop_daemon` is not called.
   - **(spec)** `rmx daemon restart`: on the same exception it fails with exit != 0, naming the
     error and `--standalone` as the deliberate override. It never falls back to the standalone
     stop+spawn on its own. Today (`cli.py:3275-3277`, "kickstart failed …; restarting
     standalone") the standalone path stops the already gracefully stopped supervised daemon and
     spawns an unsupervised one beside the loaded label. That is the bug-013 state this same
     command bootstraps around (`cli.py:3229-3240`). The helper has one failure meaning, so both
     callers honour it.
4. **The probe is reported, not swallowed.**
   - When `launchctl.status(root)` raises (darwin only), `_default_restart` logs the exception
     (type and message) and returns False. It does not guess that the daemon is unsupervised and
     stop it.
   - On a non-darwin platform the launchd probe is skipped and the standalone path runs. There is
     no launchd there, so this is not a guess.
5. **The standalone stop is honoured.**
   - `_default_restart` calls `daemon.stop_daemon(root, timeout=daemon.stop_grace_s(),
     report=rep)`.
   - On False it logs a line naming the still-alive pid (`rep["pid"]` or `read_pid`), the grace,
     and "restart it manually". It returns False and never logs `daemon stopped`.
   - Any exception from the stop is logged (type and message) and returns False.
   - `upgrade.upgrade` then records `restarted=False` and appends its existing "(restart the
     daemon manually if needed)" hint.

#### B1 (spec) — `upgrade` restarts a STORE, not the repo {#b1-root}

`upgrade.upgrade` calls `restart_fn(root)` with `root = package_root()`: the git tree being
upgraded, such as `~/refmatrix`. That is not a store. `launchctl.status(~/refmatrix)` names a
label that is never loaded, and `stop_daemon(~/refmatrix)` finds no pid and returns True. So the
live `rmx upgrade` reports `restarted=True` without restarting anything. That is the same false
report as B1, by a different route.

Requirements:

- `upgrade.upgrade(..., store_root: Path | None = None)` passes `store_root` to `restart_fn`.
- When `store_root` is None, no restart is attempted. `restarted` is False, and the log names the
  manual fix: `rmx daemon restart --relaunch`, or `rmx hub relaunch-fleet` for the fleet.
- The CLI `rmx upgrade` passes `store_root=_root()` when that directory exists.

### S1 — one binary resolver for every plist-writing command {#s1}

`launchctl._rmx_path()` becomes THE resolver, and it resolves the binary the operator actually
ran (bug-028 semantics, `cli.py:2659-2661`):

1. `$RMX_BIN` when set (explicit operator override).
2. Else `sys.argv[0]`, made absolute with `os.path.abspath`. Symlinks are NOT resolved, because a
   plist bakes `~/bin/rmx` as written. This applies when the basename is `rmx` or `refmatrix`
   and the path is an executable file.
3. Else `FileNotFoundError`, naming `sys.argv[0]` and `RMX_BIN`. There is **no `which rmx`
   fallback**: from a dev shell `which rmx` is a binary the operator did not run. That is the r5
   P1 probe, where the refusal named `bins/onpath/rmx`.

Every plist command resolves through it:

- `rmx daemon launchctl install`, `install --check` and `install --allow-dev`;
- the bug-013 bootstrap inside `rmx daemon restart`;
- `rmx hub launchctl install`, `install --check` and `status`;
- `rmx hub relaunch-fleet`, when `--rmx` is not given;
- `rmx session launchctl install` and its new `--check` ([[#s3]]);
- the library defaults (`rmx or _rmx_path()`) in `render_plist`, `render_hub_plist`, `install`,
  `install_hub`, `check`, `check_hub`, and the `session_launchctl` functions.

`cli.py` keeps no `sys.argv[0]` of its own for plist purposes.

**Restart's bootstrap keeps the installed flags.** In the bug-013 state (plist installed, label
not loaded), `rmx daemon restart` calls `launchctl.reinstall(root, rmx=_rmx_path())`. That
re-renders with `installed_flags(root)`. Today it calls `install(root)`, which re-renders with
default flags and drops `--no-watch`, `--debounce-ms`, `--watch-root` and `RMX_PARTITION`.

### S2 — a venv whose code is not the deploy tree is a dev tree {#s2}

`upgrade.runtime_identity` (`upgrade.py:102-136`) sets `dev_tree = venv_tree != code_root`. The
dev tree's own `.venv-eval` imports the dev tree's `src/`, so the two agree and the venv reads as
"not a dev tree". `.venv-eval/bin/rmx hub launchctl install` then passes every guard and renders
uncommitted code into a plist: the 2026-09-14 hazard.

Requirements:

1. **`upgrade.deploy_root() -> Path | None`** is the tree named by `$RMX_DEPLOY_ROOT` (user-
   expanded and resolved), else `Path.home() / "refmatrix"`. It returns the path only when it
   holds a `pyproject.toml`, else None.
2. **`runtime_identity` adds two keys.**
   - `deploy_root` is a `Path` or None.
   - `dev_reason` is one of `"venv-mismatch"`, `"not-deploy-tree"`, `"no-deploy-tree"` or None.
3. **`dev_tree` is True when either rule holds:**
   - (a) the existing rule: the venv belongs to one tree and the code comes from another
     (`dev_reason="venv-mismatch"`);
   - (b) the code comes from a **source tree** and that tree is not the deploy tree. A source tree
     means the import path is not under the interpreter prefix and `code_root` is not None. This
     covers an editable install and a `PYTHONPATH` checkout.
     - `deploy_root` is None (no deploy tree exists): `dev_reason="no-deploy-tree"`.
     - Otherwise, `code_root` resolved differs from `deploy_root` resolved:
       `dev_reason="not-deploy-tree"`.
   - A wheel install (import path under the prefix's `site-packages`, as with pipx) is never a
     dev tree by rule (b). There is no tree to confuse.
4. **(spec) Fail closed when no deploy tree exists.** A source-tree install with no deploy tree is
   a dev tree. Under the 23.0 sandbox, `~/refmatrix` does not exist, so the dev tree and every
   clone classify the same way. That makes the suite tree-independent, which is the [[#m2]] goal.
   A contributor running from a `git clone` sets `RMX_DEPLOY_ROOT` to that tree, or passes
   `--allow-dev`. The refusal says so.
5. **Messages.**
   - `upgrade.upgrade`'s dev-tree refusal names `dev_reason`, `deploy_root` and `RMX_DEPLOY_ROOT`
     when rule (b) fired. It reads the new keys with `.get`, because older identity dicts lack
     them (`tests/test_plan1_remedy.py` feeds one).
   - `rmx version -v --json` carries both new keys, as strings or null.
6. **Consumers are unchanged.** `daemon._process_identity`, `hub._hub_identity`,
   `_verify_relaunch`, `launchctl.binary_identity`, and the `global:queues` alert gate keep
   reading `dev_tree`. Daemons the dev tree spawns for its own test stores now report
   `dev_tree=True`. That is accurate.

### S3 — the session-indexer plist joins the plist lifecycle {#s3}

`session_launchctl` has:

- no identity guard;
- no check;
- no reinstall;
- a bare bootout in `install(force=True)`, under the OLD plist's 5 s ExitTimeOut.

Nothing on deploy re-renders a session plist, and 0/6 installed labels carry ExitTimeOut.

Requirements:

1. **`rmx=` parameter.** `render_plist(root, *, partition, interval_seconds, all_projects,
   rmx=None)` renders `rmx or _rmx_path()`. Like the daemon render, the render itself stays pure
   and carries no guard.
2. **Guarded install.** `install(root, *, partition, interval_seconds, all_projects, force,
   rmx=None, allow_dev=False)`:
   - calls `launchctl._refuse_dev_tree(rmx)` unless `allow_dev`;
   - does this before any bootout, write or bootstrap. Unknown fails closed exactly as R1 of
     [[task-4.5-r4-remedy#r1]].
3. **Graceful bootout.** When `install(force=True)` finds the label loaded:
   - It waits for an in-flight tick to finish before the bootout. The tick's pid comes from the
     `pid = N` line of `launchctl print`, via `running_pid(root) -> int | None`.
   - It waits up to `daemon.stop_grace_s()`.
   - A tick that outlives the grace raises `RuntimeError`, naming the pid and the grace, and
     says the plist was NOT rewritten. The bootout never runs on a mid-write ingest under the old
     5 s ExitTimeOut.
   - **(spec)** The tick is never signalled. It is a one-shot ingest that finishes on its own, so
     waiting is the graceful stop.
   - After the bootout it waits up to `launchctl.BOOTOUT_WAIT_S` for the label to unload, and
     raises when it is still loaded. This is the daemon's bug-013 shape.
4. **`installed_flags(root)`** recovers `interval_seconds` (StartInterval), `all_projects`
   (`--all-projects` in ProgramArguments) and `partition` (`RMX_PARTITION`) from the installed
   plist.
5. **`check(root, *, rmx=None) -> (bool, CheckReason)`**, the daemon `check`'s shape:
   - an identity objection first;
   - a missing plist;
   - the installed bytes against the render from installed flags;
   - an installed-but-unloaded label.

   A drift reason names every differing key. A plist without `ExitTimeOut` reads `ExitTimeOut:
   installed None != rendered 45`, so a label lacking ExitTimeOut is reported by check.
6. **`reinstall(root, *, rmx=None)`** re-renders with `installed_flags` through
   `install(force=True)`, re-runs a plain install when the label did not load, then verifies with
   `check`. It raises when `check` does not converge.
7. **`rmx hub relaunch-fleet`** checks every discovered root whose session plist is installed,
   supervised daemon or not. On drift it runs `session_launchctl.reinstall(root, rmx=rmx)` and
   prints `reinstalled … session-indexer …`. A failure is printed per root and counted.
8. **(spec) CLI parity.** `rmx session launchctl install` gains `--check` (exit 1 on drift, prints
   the reason, writes nothing) and `--allow-dev`, the same help text as the daemon command. Adding
   options changes the generated CLI tree, so regenerate it (see the family-list memory).

### M1 — an identity objection is not drift {#m1}

1. **`launchctl.CheckReason(str)`** carries `.kind`, one of `"identity"`, `"drift"`, `"missing"`
   or `"unloaded"`. Because it is a `str` subclass, existing fakes returning plain strings keep
   working, and a plain string reads as drift.
2. **Which kind each check returns.** `check`, `check_hub` and `session_launchctl.check` return
   `kind="identity"` for an `_identity_objection`, and `"drift"` for a render mismatch or a
   loaded-env mismatch.
3. **`rmx daemon launchctl install --check`** on an identity objection:
   - prints `binary not verified — {why}` and exits 1;
   - never prints `DRIFT`;
   - never recommends `install --force` or `relaunch-fleet`.

   Drift keeps today's output.
4. **`rmx hub launchctl status`** prints `binary not verified — {why}` for an identity objection,
   never `plist drift`.
5. **`rmx hub relaunch-fleet`** asks `_identity_objection(rmx)` once, before the loop. When the
   binary is not verified it:
   - prints `binary not verified — …` once;
   - names `--rmx <the deployed rmx>` as the fix;
   - exits 1;
   - touches no store: no `check`, no `reinstall`, no `daemon restart` subprocess.

   It never relays `--allow-dev`, a flag `relaunch-fleet` does not have.

### M2 — no test depends on which tree runs it {#m2}

Every test that renders, installs or checks a plist, or runs `upgrade` / `daemon restart
--relaunch`, takes the shared `deployed_rmx` fixture (`tests/conftest.py` + `tests/fake_rmx.py`).
It no longer reads whatever `rmx` is on PATH or whatever the test interpreter imports. The
fixture now pins three inputs, so the identity of the test environment is an input and not an
accident:

- `RMX_BIN` points to a real script answering the identity JSON with `dev_tree: false`, whose
  `import_path` is inside a tmp deploy-shaped tree.
- `RMX_DEPLOY_ROOT` is that tree.
- `upgrade.runtime_identity` is wrapped so that its DEFAULT `prefix` / `import_file` are the tree's
  `.venv` and `src/refmatrix/__init__.py`. Explicit arguments pass through, and the classifier
  that runs is the real one.

Goal: zero dev-tree-dependent failures in a clone AND in the dev tree. In the clone the 19
"clone-only DEV TREE" failures of the task 4.5 full run go to 0. Migrated tests are listed in
[[#migrated]].

## Acceptance Criteria {#acceptance}

All tests are in `tests/test_task4_6_r5_remedy.py` unless a migrated file is named.

**B1**

- **AC-1 (B1.5)** {#ac-1}
  - Setup: a real process that ignores SIGTERM and keeps its heartbeat fresh, with
    `RMX_STOP_GRACE_S=1`, and launchd reporting nothing.
  - `_default_restart(root)` returns False.
  - Its log names "manually" and never says `daemon stopped`.
- **AC-2 (B1.1-2)** {#ac-2}
  - Setup: launchd reports the store loaded and `RMX_STOP_GRACE_S=7.5`.
  - `_default_restart` returns True.
  - It runs, in order: watchdog pause, `graceful_stop(grace=7.5)`, `kickstart(restart=False)`,
    watchdog resume.
  - There is no bare `kickstart(restart=True)`.
- **AC-3 (B1.2)** {#ac-3} `rmx daemon restart` (launchd branch) and `_default_restart` (launchd
  branch) both call `launchctl.supervised_restart`.
- **AC-4 (B1.3)** {#ac-4}
  - `kickstart` raises during `_default_restart`.
  - Result: False, the error is logged, and `stop_daemon` is never called.
- **AC-5 (B1.3 spec)** {#ac-5}
  - `kickstart` raises during `rmx daemon restart`.
  - Result: exit != 0, the output names `--standalone`, and `spawn_daemon` is never called.
- **AC-6 (B1.4)** {#ac-6}
  - `launchctl.status` raises during `_default_restart`.
  - Result: False, the exception is logged, and `stop_daemon` is never called.
- **AC-7 (B1-root)** {#ac-7}
  - `upgrade.upgrade(..., store_root=S)` hands `S` to `restart_fn`.
  - `rmx upgrade` passes `store_root=_root()`.

**S1**

- **AC-8 (S1)** {#ac-8} `_rmx_path()` with `RMX_BIN` unset and a `sys.argv[0]` that is not an
  rmx binary raises `FileNotFoundError`, even when an `rmx` is on PATH.
- **AC-9 (S1, the P1 probe)** {#ac-9}
  - Setup: two binaries. The operator ran binary `ran`; PATH finds binary `onpath`.
  - Case `ran` deployed, `onpath` dev:
    - `rmx daemon launchctl install` writes `ProgramArguments[0] == ran`;
    - `install --check` reports in sync against a plist rendered for `ran`.
  - Case `ran` dev, `onpath` deployed: `install --allow-dev` writes `ran`.
- **AC-10 (S1)** {#ac-10} `rmx hub launchctl install --check` and `rmx hub relaunch-fleet` (no
  `--rmx`) hand `RMX_BIN` to `check_hub` / `check`.
- **AC-11 (S1)** {#ac-11}
  - Setup: the bug-013 state. A plist rendered for `ran` with `--no-watch --debounce-ms 900` is
    installed and the label is not loaded.
  - `rmx daemon restart` bootstraps it through `reinstall`.
  - The re-written plist keeps both flags and `ProgramArguments[0] == ran`.

**S2** (all on tmp-built, venv-shaped trees; never the real venvs)

- **AC-12 (S2.3b)** {#ac-12}
  - Shape: a dev tree whose `.venv-eval` editable target is its own `src/`, with a separate
    deploy tree `P` (`RMX_DEPLOY_ROOT=P`).
  - Result: `dev_tree=True`, `dev_reason="not-deploy-tree"`, `deploy_root=P`.
- **AC-13 (S2.3b)** {#ac-13}
  - Shape: the deploy tree's own `.venv` → `P/src`.
  - Result: `dev_tree=False` (control).
  - With `RMX_DEPLOY_ROOT` unset and `HOME=<tmp>`, `<tmp>/refmatrix` is the deploy root: that
    tree is clean and the dev tree is dev.
- **AC-14 (S2.4)** {#ac-14}
  - Shape: the deploy root does not exist.
  - Result: a tree-backed editable install is `dev_tree=True`, `dev_reason="no-deploy-tree"`.
  - A wheel install (import path under the prefix) is `dev_tree=False` (control).
- **AC-15 (S2.5)** {#ac-15}
  - `upgrade.upgrade` refuses a not-deploy-tree interpreter with a message naming the deploy root
    and `RMX_DEPLOY_ROOT`.
  - `rmx version -v --json` carries `deploy_root` and `dev_reason`.

**S3**

- **AC-16 (S3.2)** {#ac-16}
  - `session_launchctl.install` refuses a dev-tree binary and an unknown binary. Nothing is
    written and no `launchctl` call is made.
  - `allow_dev=True` installs the dev binary.
- **AC-17 (S3.5)** {#ac-17} `session_launchctl.check`:
  - an installed, loaded plist without `ExitTimeOut` → `(False, why)`, with `ExitTimeOut` in
    `why` and `why.kind == "drift"`;
  - a plist installed with `interval_seconds=120, all_projects=True` → in sync;
  - an unloaded label → not ok;
  - a dev binary → `kind == "identity"`, no `drifted`.
- **AC-18 (S3.3)** {#ac-18} `session_launchctl.install(force=True)` on a loaded label:
  - with a tick (a real child process) that exits within the grace, the bootout happens only
    after it exited;
  - with a tick that outlives the grace, it raises, no bootout is made, and the installed plist
    is unchanged.
- **AC-19 (S3.6)** {#ac-19} `session_launchctl.reinstall` re-renders a drifted plist with its
  installed flags. The result carries `ExitTimeOut` and `check` passes.
- **AC-20 (S3.7)** {#ac-20}
  - Setup: two roots (one daemon-supervised, one not), each with an installed session plist that
    lacks `ExitTimeOut`.
  - `rmx hub relaunch-fleet` runs `session_launchctl.reinstall` for both and says so.
- **AC-21 (S3.8)** {#ac-21} `rmx session launchctl install --check` exits 1 naming `ExitTimeOut`
  for a plist without it.

**M1**

- **AC-22 (M1.1-2)** {#ac-22}
  - `launchctl.check` → `why.kind`: `"identity"` for a dev binary, `"drift"` for a missing
    `RMX_SUPERVISED`.
  - `check_hub` → `why.kind == "identity"` for a dev binary.
- **AC-23 (M1.3)** {#ac-23} `rmx daemon launchctl install --check` with a dev binary:
  - exits 1 and prints `binary not verified`;
  - no `DRIFT`, no `install --force`, no `relaunch-fleet`.
- **AC-24 (M1.4)** {#ac-24} `rmx hub launchctl status` with a dev binary prints `binary not
  verified` and never `plist drift`.
- **AC-25 (M1.5)** {#ac-25} `rmx hub relaunch-fleet --rmx <dev>`:
  - exits 1 and prints `binary not verified`;
  - no `--allow-dev`, no `drift`;
  - zero `reinstall` calls and zero `daemon restart` subprocesses.

**M2**

- **AC-26 (M2)** {#ac-26}
  - Every test in [[#migrated]] passes in the clone at HEAD (it is no longer clone-only), except
    the ones marked RED-by-S1.
  - After GREEN, the full suite in the clone shows no `[DEV TREE]` / `is a dev tree` /
    `this interpreter runs a DEV TREE` failure.
  - The same run in the dev tree gives the same failure set.
- **AC-27** {#ac-27} No test in this task calls real `launchctl`, opens a live store, executes
  `~/bin/rmx` or a real venv's `rmx`, or writes outside the sandbox / its tmp roots. The 23.0
  audit hook enforces this.

## Migrated tests {#migrated}

These tests move onto `deployed_rmx`. All are GREEN at HEAD after migration unless marked.

- `tests/test_plan4_remedy_r2.py`:
  - `test_plist_check_sees_a_missing_supervised_variable`
  - `test_plist_check_keeps_the_installed_flags`
  - `test_plist_check_reports_a_missing_plist`
  - `test_launchctl_install_check_cli_exits_1_on_drift`
  - `test_install_force_raises_when_the_bootout_does_not_complete`
  - `test_install_force_reloads_and_verifies_the_loaded_env`
  - `test_install_raises_when_the_loaded_job_lacks_the_rendered_env`
  - `test_check_reports_a_loaded_job_that_lacks_the_rendered_env`
  - `test_check_reports_an_installed_but_unloaded_label`
  - `test_relaunch_bootstraps_an_installed_but_unloaded_plist_instead_of_spawning`: **RED by
    S1**. It now asserts that the bootstrap goes through `reinstall` with the resolved binary.
  - `test_relaunch_fleet_reinstalls_a_drifted_plist_before_restarting` (pre-emptive: it relied
    on `sys.argv[0]` being pytest)
- `tests/test_plan4_remedy_r3.py`:
  - `test_verify_relaunch_kills_a_predecessor_only_when_its_heartbeat_is_stale`
  - `test_daemon_restart_relaunch_pauses_the_watchdog_for_the_root_and_resumes`
- `tests/test_plan4_remedy.py`: `test_relaunch_fleet_relaunches_every_supervised_store`
  (pre-emptive, same reason)
- `tests/test_plan1_remedy.py`:
  - `test_upgrade_verifies_editable_on_the_already_up_to_date_path`
  - `test_daemon_restart_relaunch_fails_on_code_path_mismatch`
- `tests/test_upgrade.py`:
  - `test_from_dev_promote_fast_forwards_and_installs`
  - `test_check_is_readonly`
  - `test_already_up_to_date_is_noop`
  - `test_upgrade_from_dev_verifies_editable_after_install`
  - `test_non_fast_forward_refuses`: it passed in a clone for the WRONG reason (the dev-tree
    refusal is an `UpgradeError` too). It now matches the ff-only refusal.
  - `test_runtime_identity_clean_when_venv_imports_its_own_tree` and
    `test_runtime_identity_unknown_when_prefix_has_no_tree`: pinned with `RMX_DEPLOY_ROOT` to
    their own fake tree. Under S2 a tmp tree is otherwise "no deploy tree". Their premise, that
    the tree is the deploy tree, is now stated rather than implied.
- `tests/test_onboard_huballd_curator.py`: `test_hub_plist_renders_valid` asserts
  `ProgramArguments[0] == deployed_rmx`.

## Files to Create / Modify {#files}

- `src/refmatrix/launchctl.py`:
  - `_rmx_path` (S1);
  - `supervised_restart` (B1);
  - `CheckReason`, plus `check` / `check_hub` kinds (M1).
- `src/refmatrix/upgrade.py`:
  - `_default_restart` (B1);
  - `upgrade(store_root=)` (B1-root);
  - `deploy_root`, plus `runtime_identity` keys and rule (S2).
- `src/refmatrix/session_launchctl.py`:
  - `render_plist(rmx=)`;
  - `install(rmx=, allow_dev=)` and the graceful bootout;
  - `running_pid`, `installed_flags`, `check`, `reinstall` (S3).
- `src/refmatrix/cli.py`:
  - `daemon restart` (B1, S1 bootstrap);
  - `daemon launchctl install` (S1, M1);
  - `hub launchctl install/status` (S1, M1);
  - `hub relaunch-fleet` (S1, S3, M1);
  - `session launchctl install --check/--allow-dev` (S3);
  - `upgrade` passes `store_root` (B1-root);
  - `version --json` keys (S2).
- `tests/test_task4_6_r5_remedy.py` (new), `tests/conftest.py` (`deployed_rmx`),
  `tests/fake_rmx.py` (identity `import_path`), and the migrated files above.
- `workflow/test_mock_registry.md`, `workflow/plans/plan-4-daemon-resilience.md`.

## Test Strategy {#tests}

Tier 1 (pytest), inside the 23.0 sandbox.

- **launchd** is faked at the `subprocess.run` boundary with a state machine (`bootstrap` loads,
  `bootout` unloads, `print` answers per state), installed AFTER the identity cache is primed.
  This is the task 4.5 rule: `binary_identity` execs through the same process-wide function.
- **Binaries** are real scripts from `tests/fake_rmx.py`.
- **Draining daemons and in-flight ticks** are real child processes.
- **Identity trees** are tmp directories shaped like a venv: `pyproject.toml`, `src/refmatrix/`,
  and a prefix with a path-style `__editable__` `.pth`.

RED evidence: `workflow/review-output/task4.6-red.log`. Every new test is proven RED at HEAD
`419ef6e` for the reason named in its docstring.

rel: depends-on -> [[test_mock_registry]]
