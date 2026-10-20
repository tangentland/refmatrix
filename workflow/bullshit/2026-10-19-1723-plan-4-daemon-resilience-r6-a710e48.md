---
gmd: "0.1"
id: bsd-plan4-daemon-resilience-r6-a710e48
title: "ch-bsd plan-4 r6 — task 4.6 closes all six r5 findings in behaviour (21/23 mutants killed), but the one binary resolver breaks the hub UI's launchd onboarding on the real deploy, and the shared restart helper resumes the watchdog before the relaunch verify"
tags: [bsd, plan-4, launchd, daemon, identity, resolver, remedy]
severity: BULLSHIT
plan: plan-4-daemon-resilience
task: task-4.6-r5-remedy
---

# ch-bsd findings — plan-4 r6: task 4.6 r5 remedy (419ef6e..a710e48) {#root}

**Commit:** a710e48 (range `419ef6e..a710e48`: RED + spec `9dd5b38`, GREEN `9851562`, test fixes
`a710e48`; branch `plan4-remedy-w1`; clone `/Volumes/littlebig/refmatrix-plan4-remedy`)
**Date:** 2026-10-19 (written 2026-10-19T17:23:33-0700)
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 17 (`cli.py`, `launchctl.py`, `session_launchctl.py`, `upgrade.py`, `conftest.py`,
`fake_rmx.py`, eight test files, spec, summary, plan-4, mock registry)

rel: derives-from -> [[bsd-plan4-daemon-resilience-r5-390f378]]
rel: evidence-for -> [[task-4.6-r5-remedy]]

**Safety.** Every probe and mutant ran in `git archive` copies of `a710e48` and `419ef6e` under the
session scratchpad (`r6/head`, `r6/base`, `r6/m/<mutant>`). They used `.venv-eval/bin/python -B`
with `PYTHONPATH` set to the copy, and conftest's import pin confirmed the copy was the code under
test. No `src/` or `tests/` file in the clone was edited. Nothing touched launchd, a live store, a
socket, `~/.refmatrix`, a real venv, or `~/claude_tools/refmatrix`. The live plists were only read
(`plutil`, and one byte copy into a tmp dir). The deploy binary was never executed. Its identity
was computed by calling `runtime_identity(prefix=, import_file=)` on its paths.

## What closed, in behaviour {#closed}

- **r5 #b-1: CLOSED.**
  - Probe P4 re-run: a real process that ignores SIGTERM, with a fresh heartbeat and
    `RMX_STOP_GRACE_S=1`. `_default_restart` → **False**, with `daemon pid=… still alive after the
    1s grace — not restarted; restart it manually`. The predecessor is still alive and the log
    never says "daemon stopped". At `390f378` it returned True.
  - Failure-branch probes Q3: `graceful_stop` raising, `kickstart` raising, and the hub being down
    at pause. The first two return False and name the manual fix. All three make 0 standalone
    `stop_daemon` calls.
  - `upgrade` now restarts the STORE (`store_root=_root()`) and no longer restarts the repo root.
  - Mutants KILLED:
    - M1: stop's False ignored
    - M2: status raise falls through
    - M3: bare `kickstart -k` restored
    - M14: `daemon restart` guesses unsupervised
    - M16: CLI drops `store_root`
    - M17: the repo root is restarted
    - M21: kick failure falls back to standalone
- **r5 #s-1: CLOSED for argv[0]-run processes.**
  - Real-process P1: `bins/ran/rmx` is a real script that runs the copy's CLI. `PATH` finds
    `bins/onpath/rmx`, which answers `dev_tree: true`.
  - At HEAD, `ran/rmx daemon launchctl install --check` compares against a render for **`ran`**:
    `ProgramArguments: installed […/onpath/rmx …] != rendered […/ran/rmx …]`.
  - At `419ef6e` the same command refused with `…/onpath/rmx is a dev tree`.
  - Mutants KILLED: M5 (the `which` fallback re-added) and M15 (bootstrap `install(root)` with
    default flags).
  - The resolver's one non-argv[0] caller regressed: see [[#b-1]].
- **r5 #s-2: CLOSED.**
  - On tmp venv-shaped trees:
    - the dev tree's own `.venv-eval` gives `dev_tree=True, not-deploy-tree`;
    - the deploy tree's own `.venv` gives False;
    - a missing deploy root gives `no-deploy-tree`.
  - On the REAL paths (read only):
    - `~/refmatrix/.venv` + `~/refmatrix/src` gives `dev_tree=False, deploy_root=/Users/tholley/refmatrix`,
      both with `HOME` set and with it unset (`Path.home()` falls back to pwd);
    - `~/claude_tools/refmatrix/.venv-eval` gives `dev_tree=True, not-deploy-tree`.
  - The deploy venv's editable `.pth` is `/Users/tholley/refmatrix/src`.
  - Mutants KILLED: M6 (rule b), M7 (deploy compare) and M20 (`RMX_DEPLOY_ROOT` ignored).
- **r5 #s-3: CLOSED.**
  - I copied the live `com.refmatrix.session-indexer.refmatrix-fb619c669f75.plist` into a tmp
    LaunchAgents dir. `check` → `drift`, and the ONLY differing key is
    `ExitTimeOut: installed None != rendered 45`.
  - `installed_flags` recovers `{600, False, sessions-refmatrix}`.
  - `reinstall` (with a fake launchctl) runs `bootout`, waits for the unload, runs `bootstrap`,
    and `check` → True. The rewritten plist differs from the live one only in `ExitTimeOut`.
  - The AC-18 real-`sleep` tick tests pass.
  - Mutants KILLED:
    - M8: session guard removed
    - M9: tick wait made a no-op
    - M11: fleet skips the session check
    - M19: render ignores `rmx`
    - M23: no byte compare
- **r5 #m-1: CLOSED.** Mutants KILLED: M12 (fleet's upfront identity check), M13 (`check`
  identity kind turned into drift), M18 (hub status) and M22 (daemon `--check`).
- **r5 #m-2: CLOSED.**
  - The 10 targeted files (including every migrated test) give **180 passed, 0 failed in a
    scratch copy that is not the dev tree**.
  - The branch's full-suite log `task4.6-tests-fixed-full.log` shows 1 failed (the gmd repo-scope
    gate), 3036 passed, and zero `[DEV TREE]` failures.
- **Deferral sweep:** there are no hard or soft deferral hits in the added `src/`/`tests/` lines.

## Audit questions {#questions}

- **(1) Deploy safety.** Walked as `~/bin/rmx` → `~/refmatrix/.venv` → `~/refmatrix/src`, with
  `RMX_DEPLOY_ROOT` unset:
  - **`rmx upgrade`:** the identity is clean (above).
    - `_root()` resolves the cwd's store, or `~/.refmatrix`.
    - A loaded label goes through `supervised_restart`.
    - A missing store says "no daemon restarted".
  - **`rmx daemon restart --relaunch`:** `is_loaded` → `supervised_restart` → `_verify_relaunch`.
    - The CLI's identity is clean.
    - The launchd-started daemon computes the same deploy identity, so the [DEV TREE] gate
      passes.
  - **`rmx hub relaunch-fleet`:** argv[0] = `/Users/tholley/bin/rmx`.
    - `_identity_objection` execs `~/bin/rmx version -v --json`, which is clean.
    - Every session plist is reinstalled once for `ExitTimeOut`. A tick that outlives the 30 s
      grace makes that root FAILED and counted, and the command exits 1 for a rerun.
    - Daemon plists are unchanged: their render already carries `ExitTimeOut` 45.
  - **`rmx session launchctl install --check`:** reports `session plist DRIFT … ExitTimeOut` and
    exits 1. It writes nothing.
  - **The hub's self-restart** is `os._exit(1)` on a worker version mismatch
    (`modelsrv.py:339-343`). launchd respawns `ProgramArguments`, and no resolver is involved.

  The only deploy path that breaks is [[#b-1]].
- **(2) launchd-run processes.** The daemon and hub plists both have `ProgramArguments[0] =
  /Users/tholley/bin/rmx` (`plutil`). Each process's `sys.argv[0]` is that path, which is
  absolute and executable, so `_rmx_path()` would succeed. Neither `daemon.py` nor `hub.py`
  calls `_rmx_path` or a plist render, install or check: the only callers are `cli.py` plist
  commands and `launchctl`/`session_launchctl` defaults. **But the hub's own children run as
  `sys.executable -m refmatrix.cli`**, which sets argv[0] = `…/refmatrix/cli.py`:
  - `ui/server.py:191`, `:578`
  - `scheduler.py:131`
  - `daemon.py:6764`

  `scheduler.py:131`, `daemon.py:6764` and `ui/server.py:578` (allow-list `ingest/embed/sync/…`)
  never reach the resolver. `ui/server.py:202` does: see [[#b-1]].
- **(3) Watchdog pause/resume:** resume runs on every failure branch (`finally`, probe Q3). It
  now runs BEFORE `_verify_relaunch`: see [[#s-1]]. A mutant moving resume out of `finally` (M4)
  survives: see [[#m-1]].
- **(4) Session tick wait:** correct, and the wait never signals. The bootout-unload wait (M10)
  is untested: see [[#m-1]]. Not filed: a tick that StartInterval launches in the sub-second gap
  between the last `running_pid` poll and the bootout. With a 600 s interval the gap is
  negligible.
- **(5) `except Exception: pass` / hand-rolled restarts:** an AST scan of `launchctl.py`,
  `session_launchctl.py` and `upgrade.py` finds **zero**. The remaining `kickstart(` callers are
  all intended:
  - `cli.py:3041`: `daemon start` defers to launchd, with no `-k`.
  - `cli.py:3284` / `:3315`: `_verify_relaunch`'s `-k`, gated on a stale heartbeat.
  - `cli.py:3685`: the explicit operator command `daemon launchctl kickstart`.
  - `hub.py:385`: the watchdog, excluded by design since r5.

  `daemon.py:6853` (`graceful_stop`'s pid-from-ping lookup) is a pre-existing except-pass. It is
  benign, because the wait falls back to the socket, and it is not filed.

## Findings {#findings}

### BULLSHIT: the one binary resolver breaks the hub UI's "supervise (launchd)" onboarding on the real deploy — `rmx daemon launchctl install` runs as `python -m refmatrix.cli`, and its argv[0] is `cli.py` {#b-1}

**File:** `src/refmatrix/launchctl.py:190-205` (`_rmx_path`: `RMX_BIN`, else argv[0] when its
basename is `rmx`/`refmatrix`, else raise). The caller is `src/refmatrix/ui/server.py:189-202`
(`run(["daemon", "launchctl", "install"], "launchctl")` → `subprocess.run([sys.executable, "-m",
"refmatrix.cli", *args], …)`), reachable from the Projects tab checkbox `#onboard-launchd`
(`ui/static/app.js:176`, `:187-188`).
**What:** S1 removed the `which rmx` fallback. This UI step calls a plist command from a process
whose argv[0] is never an `rmx` binary, so it now raises. Probe, on a copy with a fake HOME and a
tmp store, run exactly as the hub runs it:
```
head  python -m refmatrix.cli daemon launchctl install
      Error: cannot tell which rmx to render into a plist: this process was started as
      '…/head/src/refmatrix/cli.py' (sys.argv[0]), which is not an `rmx`/`refmatrix`
      executable, and RMX_BIN is not set …            rc=1
base  _rmx_path() with argv[0]=…/cli.py  ->  resolved …/bins/rmx   (which rmx)
```
The live hub plist sets `PATH=/Users/tholley/bin:…` and no `RMX_BIN` (`plutil`). At `419ef6e`
the step therefore rendered `/Users/tholley/bin/rmx`, which is right. At HEAD, every "init + supervise"
from the hub UI returns `{"step": "launchctl", "ok": false}` and the project is never supervised.
**Why it's bullshit:** this is a production path on the deployed hub, and it now refuses where
it used to work. The spec's S1 list (`task-4.6-r5-remedy#s1`) names every CLI entry point and
every library default. It missed the one caller that reaches a plist command through
`-m refmatrix.cli`. No test drives `/api/projects/init` with `launchd: true`, so the 180 green
targeted tests and the 3036-test full suite cannot see it.
**Fix:**
- In the hub process, resolve `launchctl._rmx_path()`. Under launchd that is
  `/Users/tholley/bin/rmx`, from the hub's own argv[0].
- Pass it as `RMX_BIN` in the child env of `project_init.run`, or exec that binary instead of
  `-m refmatrix.cli`.
- Do the same for any future hub-spawned plist command.
- Add a test that posts `/api/projects/init {"launchd": true}`, with the real subprocess and a
  launchd fake, `RMX_BIN` unset, and the hub's argv[0] pinned to a `deployed_rmx`-style binary.
  It must assert the rendered `ProgramArguments[0]`.
- Optional: `_rmx_path` could recognise `-m refmatrix.cli` and refuse with a message naming the
  hub caller, but the env pass is the fix.

**Pattern match:** YES. See [[impression_bsd_quoted_line_sibling]]. The resolver converged on
the callers the r5 probe exercised and missed the sibling that is not run through argv[0]. It is
also a convergence that ended at the callers its own enumeration listed.
rel: contradicts -> [[task-4.6-r5-remedy#s1]]

### SKETCHY: `supervised_restart` resumes the hub watchdog BEFORE `rmx daemon restart --relaunch` verifies — the r3 #s-3 pause no longer covers the relaunch window it was added for {#s-1}

**File:** `src/refmatrix/launchctl.py:976-985` (`finally: _watchdog_resume` right after
`kickstart`), `src/refmatrix/cli.py:3299-3316` (`_verify_relaunch` now runs after the helper
returns)
**What:** at `419ef6e`, `_verify_relaunch(...)` and its `return` sat inside the
`try: … finally: _watchdog_resume(root)`. The watchdog stayed paused for the up-to-40 s verify,
and for verify's own `kickstart -k` of a clinging predecessor. The helper was described as
"lifted unchanged", but it resumes as soon as the kick returns. Probe (copies, the r3 fakes plus a
recorder on `served_identity`):
```
head  ['verify', 'pause', 'graceful_stop', 'kickstart', 'resume', 'verify']
base  ['verify', 'pause', 'graceful_stop', 'kickstart', 'verify', 'resume']
```
The 2026-09-15 incident behind r3 #s-3 was the hub's no-process branch kicking relaunching
daemons inside launchd's ThrottleInterval. The two-tick no-process gate (`hub.py:288-302`)
narrows that risk but does not remove it. `_verify_relaunch`'s kill-9 + kick path creates exactly
the "no process" window, now with the watchdog live.
**Fix:** let `supervised_restart` take an `after_kick` callable that runs inside the `try` (the
CLI passes its `_verify_relaunch`), or let it return before resuming and let the caller own the
resume. Then extend `test_daemon_restart_relaunch_pauses_the_watchdog_for_the_root_and_resumes`
to assert that the last verify comes before `resume`.
**Pattern match:** YES. See [[impression_bsd_quoted_line_sibling]]: an extraction moved the
boundary of a guard it claimed to preserve.
rel: contradicts -> [[task-4.6-r5-remedy#b1]]

### MEH: two spec'd S3/B1 behaviours have no test — moving resume out of `finally` (M4) and dropping the session bootout-unload wait (M10) both pass 98/98 {#m-1}

**File:** `src/refmatrix/launchctl.py:983-984` (`finally: _watchdog_resume`),
`src/refmatrix/session_launchctl.py:184-188` (`_wait_loaded(expected=False)` → raise)
**What:** B1.1 requires the resume in a `finally`, and S3.3 requires a raise when the label is
still loaded after bootout. Mutants M4 (`except Exception: raise` and resume only on success) and
M10 (`if False:` around the unload check) SURVIVE the four targeted files
(`test_task4_6_r5_remedy`, `plan4_remedy_r3`, `plan4_remedy_r2`, `test_upgrade`). The behaviour
is correct at HEAD (probe Q3 saw a resume on both failure branches). Nothing would notice a
regression.
**Fix:**
- Assert `resume` in `calls` in the AC-4 kickstart-raising test and in a `graceful_stop`-raising
  twin.
- Add a `_Launchd` mode whose `bootout` leaves the session label loaded, and assert `RuntimeError`
  plus an unchanged plist.

**Pattern match:** YES. See [[impression_bsd_partial_bound_guard]].
rel: contradicts -> [[task-4.6-r5-remedy#acceptance]]

### MEH: the dev-tree prescriptions on the status and relaunch surfaces still describe only rule (a) — "fix the editable install first" for a venv whose editable install is correct {#m-2}

**File:** `src/refmatrix/cli.py:2938` (`_print_code_identity`: "this venv belongs to another
tree"), `src/refmatrix/cli.py:3202-3208` (`_verify_relaunch`: "a venv that belongs to … is
running another tree; fix the editable install first"), `daemon.py:3412` / `:3432` (the ping
carries `dev_tree` but no `dev_reason`)
**What:** S2.5 added `upgrade.dev_tree_message(ident)`, which names `dev_reason`, `deploy_root`
and `RMX_DEPLOY_ROOT`, and only `upgrade.upgrade` uses it. Under rule (b), a `.venv-eval` shell
running `rmx daemon restart --relaunch` or `rmx version -v` is told its venv belongs to another
tree and to fix the editable install. Both claims are false; the real fix is to run the deployed
rmx or set `RMX_DEPLOY_ROOT`. This fails safe, since the refusal itself is right.
**Fix:** route both messages through `dev_tree_message`, and carry `dev_reason` in the daemon
ping so `_verify_relaunch` can name it.
**Pattern match:** YES. See [[impression_bsd_quoted_line_sibling]]: the message was fixed at
the one site the spec quoted.
rel: contradicts -> [[task-4.6-r5-remedy#s2]]

### MEH: bookkeeping lags the last commit — the summary still lists 4 failures and the registry still says "internal-pending … re-classify once GREEN lands" {#m-3}

**File:** `workflow/implementation_summaries/task-4.6-r5-remedy.md` (`## Suite`: "4 failed …
They need the `deployed_rmx` fixture"), `workflow/test_mock_registry.md` (the `supervised_restart`
recorder row: `internal-pending`)
**What:** `a710e48` fixed three of the four failures (1 failed, 3036 passed), and GREEN
`9851562` landed the helper. Neither document was updated, so the summary describes open
failures that are closed, and the registry row carries a stale reclassification.
**Fix:** update `## Suite` to the `a710e48` run, and flip the row to `internal-active`.
**Pattern match:** NO.
rel: contradicts -> [[test_mock_registry]]

## Mutation table {#mutations}

23 mutants were run on scratch copies against the four targeted files (`scratchpad/r6/mut.log`).
21 were KILLED:
- M1: stop's False ignored
- M2: status raise falls through
- M3: bare `-k`
- M5: `which` fallback
- M6: rule b off
- M7: deploy compare off
- M8: session guard off
- M9: tick wait no-op
- M11: fleet skips session
- M12: no upfront identity
- M13: identity as drift
- M14: probe guesses unsupervised
- M15: bootstrap `install(root)`
- M16: CLI drops store
- M17: repo root restarted
- M18: hub status as drift
- M19: session render ignores `rmx`
- M20: `RMX_DEPLOY_ROOT` ignored (the `deployed_rmx` fixture's self-check)
- M21: kick failure to standalone
- M22: daemon `--check` as drift
- M23: no byte compare

**SURVIVED:** M4 (resume not in `finally`) and M10 (no session unload wait). See [[#m-1]]. No
test exists for the [[#b-1]] path, so no mutant there could be killed.

## Verdict {#verdict}

5 findings (1 BULLSHIT, 1 SKETCHY, 3 MEH). All six r5 findings close in behaviour, and every
closure except the two in [[#m-1]] is mutation-guarded. **Plan-4 may NOT flip `completed`:**
- [[#b-1]] breaks a deployed hub feature that worked at `419ef6e`.
- [[#s-1]] reopens the relaunch window that r3 #s-3 closed.

Round 7 is small:
- one env var in `ui/server.py` plus a test;
- move `_verify_relaunch` inside the helper's pause;
- two assertions;
- two message routes;
- the bookkeeping.

rel: contradicts -> [[plan-4-daemon-resilience#decisions-log]]
