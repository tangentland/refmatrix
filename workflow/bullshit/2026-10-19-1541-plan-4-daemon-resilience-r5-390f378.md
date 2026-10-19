---
gmd: "0.1"
id: bsd-plan4-daemon-resilience-r5-390f378
title: "ch-bsd plan-4 r5 — task 4.5 closes the six r4 findings in their tests (16/16 mutants killed), but `rmx upgrade` still discards a failed stop and reports a restart; the daemon CLI still resolves `which rmx`; the session indexer never gets its ExitTimeOut"
tags: [bsd, plan-4, launchd, daemon, stop-grace, identity, remedy]
severity: BULLSHIT
plan: plan-4-daemon-resilience
task: task-4.5-r4-remedy
---

# ch-bsd findings — plan-4 r5: task 4.5 r4 remedy (d4bf001..390f378) {#root}

**Commit:** 390f378 (range `d4bf001..390f378`: RED `a8e30f3`, GREEN `8e20890`, test fixes `390f378`;
branch `plan4-remedy-w1`; clone `/Volumes/littlebig/refmatrix-plan4-remedy`)
**Date:** 2026-10-19 (written 2026-10-19T15:41:50-0700)
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 15 (`launchctl.py`, `daemon.py`, `cli.py`, `hub.py`, `session_launchctl.py`,
`tests/conftest.py`, `tests/fake_rmx.py`, three test files, spec, summary, plan-4, todo, mock registry)

rel: derives-from -> [[bsd-plan4-daemon-resilience-r4-ffed3df]]
rel: evidence-for -> [[task-4.5-r4-remedy]]

**Safety.** All probes and mutants ran in `git archive 390f378` copies under the session scratchpad
(`r5/`, `m/<mutant>/`). I used `.venv-eval/bin/python -B` with an absolute `PYTHONPATH` set to the
copy, and conftest's import pin confirmed the copy was the code under test. The 23.0 sandbox was
active for every pytest run. I did not edit `src/` or `tests/` in the clone. Nothing touched
launchd, a live store, a socket, `~/.refmatrix` or `~/claude_tools/refmatrix`. Live state was only
READ: `plutil` on the installed plists, `~/.refmatrix/hub.log`, `~/bin/rmx`, and the deploy venv's
`pyvenv.cfg` and editable `.pth`. I did not execute the deploy binary. I classified it by calling
`runtime_identity(prefix=, import_file=)` on its paths.

## What closed, in behaviour {#closed}

- **#s-2 (unknown identity fails closed): CLOSED on every daemon/hub render, install and check
  path.** `_identity_objection` (`launchctl.py:137`) is the only place that reads `binary_identity`.
  Its three callers are `_refuse_dev_tree`, which covers `install`, `install_hub` and
  `render_hub_plist`, plus `check` and `check_hub`. A grep found no other `dev_tree` guard in
  `launchctl.py`. Probe P3 ran the end-to-end path `rmx hub relaunch-fleet --rmx <version-line
  binary>`. It printed `FAILED … identity unknown` for the store and exited 1. It made 0
  `launchctl`/`subprocess` calls, left the installed plist byte-identical, and restarted nothing.
  Mutants M1 (`if not dev`), M2 (check unguarded), M3 (check_hub unguarded) and M16 (install guard
  removed) are all KILLED. The session-indexer plist is not covered: see [[#s-3]].
- **The guard does NOT block a legitimate deploy.** `~/bin/rmx` is a symlink to
  `~/refmatrix/.venv/bin/rmx`, whose shebang is `~/refmatrix/.venv/bin/python`. The editable `.pth`
  points to `/Users/tholley/refmatrix/src`. That gives `venv_tree = code_root = ~/refmatrix`, so
  `dev_tree=False` (computed). The deploy binary prints the identity JSON as its last stdout line
  (`version --json`), and `binary_identity` reads the last line, so a deploy's
  `relaunch-fleet` → `check` → `reinstall` passes. The real hole is the opposite one: see
  [[#s-2]].
- **#s-3 (one stop grace):** these paths all take `stop_grace_s()`:
  - `daemon stop`
  - `compact`
  - `upgrade`'s fallback stop
  - the hub UI stop
  - `install --force`
  - the `--relaunch` kick
  - bare `stop_daemon(root)`

  Mutants M4, M5, M7 and M12-M15 (each reintroducing 5.0 s or the constant at one site) are all
  KILLED. AC-6 runs against a real process that drains for 6 s and passes at HEAD. `_respawn` now
  refuses on a False (mutant M6 KILLED). Note: in the real flow the kick is reached only after the
  stale-heartbeat `kill -9`, and a real `stop_daemon` returns False only for a fresh heartbeat. So
  this branch fires only when SIGKILL fails to land within 2 s. It is defensive, and the test
  reaches it through a fake. Not filed. **My own enumeration of stop paths** finds more than the
  spec's 8:
  - (9) `upgrade._default_restart`'s launchd branch: a bare `kickstart -k`
  - (10) `rmx daemon launchctl kickstart -k`
  - (11) `launchctl.uninstall`'s bootout, which has no graceful stop
  - (12) `session_launchctl.install --force`'s bootout
  - (13) `_reap_predecessor`: 3 s, gated on a stale heartbeat, legitimate
  - (14/15) the watchdog and adoption, excluded on purpose
  - (16) `_verify_relaunch`'s `kill -9`, gated on a stale heartbeat

  Paths 9-11 fall under launchd's ExitTimeOut, which is 45 on 8/8 daemon plists and the hub (read
  with `plutil`), so only the `RMX_STOP_GRACE_S` override is bypassed there. Path 9 is part of
  [[#b-1]] and path 12 is part of [[#s-3]].
- **#m-5:** `rmx daemon launchctl install --allow-dev` is wired (mutant M8 KILLED), and the refusal
  names the CLI flag (mutant M9 KILLED). It installs the wrong binary, though: see [[#s-1]].
- **#m-6:** the render carries `ExitTimeOut` from the shared constant (mutant M10 KILLED). It
  closes the render only, not the label: see [[#s-3]].
- **#s-4:** the `_await_shutdown` line names its root (mutant M11 KILLED). The live
  `~/.refmatrix/hub.log` holds 85 test-shaped lines, the last at 2026-10-15T03:37 (before 23.0).
  It gained none from this audit's runs (27 + 3 probes + 34 related tests + 16 mutant runs, all
  today).
- **G9:** the todo row flipped to Done with citations. `tests/test_daemon_adopt.py` passes in the
  copy. Closed as bookkeeping. I agree with that.
- Tests: `tests/test_task4_5_r4_remedy.py` gives 27 passed at HEAD. The related set
  (`test_daemon_adopt`, `test_plan4_remedy_r3`, `test_launchctl_label`) gives 32 passed and 2
  failed. Both failures are the clone-only `[DEV TREE]` refusals named in the summary. The full
  suite log (`task4.5-tests-fixed-full.log`) shows 20 failed, all clone-only DEV TREE plus the gmd
  repo-scope gate. Deferral sweep: no hits in the added lines. GMD lint: 0 errors in the four docs
  this task touched.

## Findings {#findings}

### BULLSHIT (escalated): `rmx upgrade` discards a failed stop, prints "daemon stopped" and reports `restarted=True` while the old daemon keeps serving — the third stop path in this plan to throw the False away {#b-1}

**File:** `src/refmatrix/upgrade.py:313-315` (`daemon_mod.stop_daemon(root)`, return value
discarded, then `log("daemon stopped …")` and `return True`); also `:305` (bare `kickstart -k`) and
`:308-309` / `:316-317` (`except Exception: pass` ×2)
**What:** Task 4.5 changed this path's grace (path 6 in the spec's table). It kept the discard that
R2 called WRONG at `_respawn`, thirty lines from where the discard was fixed. Probe P4 used a real
process with a fresh heartbeat that ignores SIGTERM, plus `RMX_STOP_GRACE_S=1`:
```
P4 _default_restart -> True in 1.0s; logs=['daemon stopped (next read spawns the upgraded daemon)'];
   predecessor alive=True; stop_daemon direct -> False
```
`upgrade.run` then sets `res.restarted = True` (`upgrade.py:280`) and logs `upgraded a -> b` without
the "restart the daemon manually" hint. The operator is told the upgrade landed while the old code
is still serving. Two related problems sit in the same function:
- **The launchd branch is the bare `kickstart -k`** (`:305`) that r3 #b-1 removed from
  `rmx daemon restart`. It has no graceful stop first and no watchdog pause (r3 #s-3).
- **Both `except Exception: pass` blocks swallow the error.** If `kickstart` raises, the code falls
  through to stopping a SUPERVISED daemon. That daemon exits 0, KeepAlive (`SuccessfulExit: false`)
  does not respawn it, and the next read starts an unsupervised daemon beside the launchd label.
  This is the bug-013 state that `daemon restart` explicitly bootstraps around (`cli.py:3229-3240`).

**Why it's bullshit:** this is the escalation rule. Each time, a stop's False was thrown away and the
command reported success:
- r3 #b-1: the standalone restart
- r4 #s-3: `_respawn`, which the r4 ledger graded SKETCHY because the daemon-side yield catches the
  double spawn
- this site: same shape, third run

r4's #s-3 named `upgrade.py:313` explicitly. The remedy fixed the number on that line and left its
return value unread. That is scope quietly narrowed to "the grace" when the finding was about
honouring the stop.
**Evidence:** P4 above (scratch `probe2.log`). Mutation M14 (5.0 s at `:313`) is killed only on the
grace. No test asserts on `_default_restart`'s return value or log when the stop fails.
**Fix:**
1. `if not daemon_mod.stop_daemon(root): log("daemon did not stop … restart it manually"); return False`.
2. Replace the bare `kickstart -k` with the `daemon restart` launchd sequence (pause, graceful stop
   with `stop_grace_s()`, kick, resume), or call `rmx daemon restart --relaunch` itself.
3. Have the `kickstart` failure log and return False rather than fall through to an unsupervised
   stop.
4. Add a test that uses the real `_draining_process(ignore_term=True, heartbeat=True)` and asserts
   `False` plus the manual-restart line.

**Pattern match:** YES. See [[impression_bsd_quoted_line_sibling]] (fix-at-the-quoted-line) and
[[impression_bsd_partial_bound_guard]]. This is the third False-discard in plan-4.
rel: contradicts -> [[task-4.5-r4-remedy#r2]]

### SKETCHY: the daemon commands still resolve `which rmx` while the hub and `relaunch-fleet` use `sys.argv[0]` — the new `--allow-dev` installs the binary on PATH, not the one the operator ran {#s-1}

**File:** `src/refmatrix/cli.py:3610` (`lc.check(root)`), `:3619` (`lc.install(...)` with no `rmx=`),
`:3238` (`daemon restart`'s bug-013 bootstrap `lc.install(root)`, which also drops the installed
flags). The other side is `cli.py:2662` / `:2701` / `:2771` (`sys.argv[0]`).
**What:** Probe P1 set up two binaries. The operator runs binary `ran`, which answers
`dev_tree:false`. `which rmx` finds `onpath`, which answers `dev_tree:true`. Same invocation:
```
daemon launchctl install          rc 1  refusing to render a plist: …/bins/onpath/rmx is a dev tree …
hub launchctl install             rc 0  hub ProgramArguments[0] = …/bins/ran/rmx
daemon launchctl install --check  rc 1  plist DRIFT …/bins/onpath/rmx is a dev tree …
daemon launchctl install --allow-dev  rc 0  daemon ProgramArguments[0] = …/bins/onpath/rmx
```
The refusal names a binary the operator never ran. The fix it recommends (`--allow-dev`, the
feature task 4.5 added) then writes that binary into the plist. bug-028's own comment at
`cli.py:2659-2661` says "`_rmx_path()` would resolve `which rmx`, which from a dev shell is the dev
venv". The daemon twin of the same command still does exactly that. Two "is it in sync?" answers
also exist for one store: `daemon launchctl install --check` (PATH) versus `relaunch-fleet`
(argv[0]).
**Fix:** one resolver: `_invocation_rmx()` = `RMX_BIN` or `sys.argv[0]`, used by daemon
install/check/restart-bootstrap. Restart-bootstrap should go through `reinstall`, so the installed
flags are kept. Add a test with the two-binary P1 setup.
**Pattern match:** YES. See [[impression_bsd_quoted_line_sibling]]. bug-028 fixed the hub site and
left the daemon sibling.
rel: contradicts -> [[task-4.5-r4-remedy#r3]]

### SKETCHY: the "dev tree" guard passes the dev tree's own venv — the binary a dev shell actually aims at plists {#s-2}

**File:** `src/refmatrix/upgrade.py:102-136` (`runtime_identity`: `dev_tree` = "venv tree ≠ code
tree"), read by `launchctl.py:150`
**What:** I computed `runtime_identity(prefix=~/claude_tools/refmatrix/.venv-eval,
import_file=~/claude_tools/refmatrix/src/refmatrix/__init__.py)`. It returns `dev_tree: False`,
the same answer as the deploy venv. So `.venv-eval/bin/rmx hub launchctl install --force` (argv[0])
passes every guard and renders uncommitted dev code into the hub plist. That is the 2026-09-14
hazard the guard was written for. The suite depends on this. About 20 tests render plists against
the ambient `which rmx` (`.venv-eval/bin/rmx`): `test_plan4_remedy_r2` ×10, r3 ×2, `plan1` ×2,
`upgrade` ×4, `onboard` ×1. They pass in the dev tree only BECAUSE the dev venv reads as "not a dev
tree". In this clone they are the "clone-only DEV TREE" failures. Pre-existing (r3 design). It is
filed because R1's message claims "an unreadable binary is never assumed to be the deployed one",
while a readable dev binary is assumed exactly that.
**Fix:** classify against the deploy tree, not venv/code agreement. Options:
- `dev_tree` is True when `code_root` is a git checkout with uncommitted changes or is not the
  deploy checkout (`~/refmatrix` or a configured `RMX_DEPLOY_ROOT`), or
- the plist guard additionally refuses a binary whose `code_root` ≠ the deploy root unless
  `--allow-dev` is passed.

Then move the ~20 tests onto `deployed_rmx`.
**Pattern match:** YES. The consolidated impression "guards built for the fixed state, not the incident" applies (a guard built for the
fixed state, not the incident).
rel: contradicts -> [[task-4.5-r4-remedy#r1]]

### SKETCHY: the session-indexer plist sits outside the plist lifecycle — no identity guard, no check, no reinstall; #m-6 closed in the render while 0/6 installed labels carry ExitTimeOut and nothing on deploy changes that {#s-3}

**File:** `src/refmatrix/session_launchctl.py:57` (`rmx = _rmx_path()`, no `_refuse_dev_tree`),
`:105-136` (`install`: no guard, no `allow_dev`, bare bootout at `:116` with no graceful stop and
no unload wait), and no `check`/`reinstall` anywhere. `relaunch-fleet` (`cli.py:2779-2790`) checks
daemon plists only.
**What:**
- `plutil` on the 6 installed `com.refmatrix.session-indexer.*.plist` files: **0/6 have
  ExitTimeOut**. The 8 daemon plists and the hub all have 45, because `relaunch-fleet` re-renders
  those.
- No production path re-renders a session-indexer plist. The live labels therefore keep launchd's
  5 s after this deploys, until someone runs `rmx session launchctl install --force` per store by
  hand. Nothing tells them to.
- That forced reinstall's bootout runs under the OLD plist's 5 s.
- Probe P2: `render_plist` happily renders a dev-tree binary and a version-line (unknown) binary
  into `ProgramArguments[0]`. These are the two shapes #s-2 just closed for the other two plist
  families.

This is r2 #b-1 again (a setting reaches only the plists nobody re-renders) and the [[#b-1]]
"plist SET is the unit" impression.
**Fix:**
1. Add `_refuse_dev_tree` plus `allow_dev` to `session_launchctl.render_plist`/`install`.
2. Add a `session_launchctl.check` and `reinstall` with the same shape as the daemon's.
3. Have `relaunch-fleet` check and reinstall the session label alongside each store.

**Pattern match:** YES. See [[impression_bsd_gate_in_an_artifact_no_deploy_step_rerenders]] and
[[impression_bsd_plist_set_is_the_unit]].
rel: contradicts -> [[task-4.5-r4-remedy#r4]]

### MEH: the CLI surfaces still call an identity objection "drift" and prescribe the drift fix {#m-1}

**File:** `src/refmatrix/cli.py:3614-3615` (`plist DRIFT {why}` + `fix: rmx daemon launchctl
install --force (or rmx hub relaunch-fleet)`), `cli.py:2705` (`hub launchctl status`: `plist drift
— {why}`). `relaunch-fleet`'s per-store failure also relays the refusal's advice to pass
`--allow-dev`, a flag `relaunch-fleet` does not have.
**What:** R1 says an unknown or dev binary "is not drift to be fixed". `check()` honours that, but
both commands that print its answer relabel it DRIFT (probe P1: `plist DRIFT …/onpath/rmx is a dev
tree`). This fails safe, since both prescribed fixes refuse, but it contradicts the requirement on
the surface an operator actually reads.
**Fix:** return a typed reason (`("identity", why)` vs `("drift", why)`) and print `binary not
verified` without the reinstall advice.
**Pattern match:** NO.
rel: contradicts -> [[task-4.5-r4-remedy#r1]]

### MEH: the `deployed_rmx` convergence stopped at the six tests the guard broke; ~20 plist tests still exec whatever `rmx` is first on PATH {#m-2}

**File:** `tests/test_plan4_remedy_r2.py` (10), `tests/test_plan4_remedy_r3.py` (2),
`tests/test_plan1_remedy.py` (2), `tests/test_upgrade.py` (4),
`tests/test_onboard_huballd_curator.py` (1)
**What:** 390f378 created "one deployed_rmx fixture for plist tests". The tests it did not migrate
still render through `_rmx_path()`. They exec the ambient binary's `version -v --json`, and their
result depends on which tree is on PATH: they pass in the dev tree via [[#s-2]] and fail in every
clone. On a shell where `which rmx` is `~/bin/rmx`, they exec the live deploy binary. That is
harmless for a read, but it is the live deploy.
**Fix:** move them onto `deployed_rmx`. The clone-only failure count should then drop by about 19.
**Pattern match:** YES. See [[impression_bsd_quoted_line_sibling]].
rel: contradicts -> [[test_mock_registry]]

## Mutation table {#mutations}

All 16 KILLED (targeted test files only, scratch copies, `scratchpad/mut.log`):
- M1 fail-open
- M2 check unguarded
- M3 check_hub unguarded (killed by `render_hub_plist`'s own guard raising)
- M4 install constant grace
- M5 stop_daemon 5 s
- M6 `_respawn` ignores False
- M7 `_respawn` 5 s
- M8 `--allow-dev` not forwarded
- M9 refusal message reverted to `allow_dev`
- M10 session ExitTimeOut removed
- M11 `{root}` removed from the hub line
- M12 `daemon stop` 5 s
- M13 compact 5 s
- M14 upgrade 5 s
- M15 UI 5 s
- M16 install guard removed

No mutant covers [[#b-1]]'s discarded return, because no test asserts on it.

## Verdict {#verdict}

6 findings (1 BULLSHIT, 3 SKETCHY, 2 MEH). The six r4 items close as stated, and every one is
guarded by a test that a mutant fails. Plan-4 may NOT flip `completed`:
- [[#b-1]] is the third False-discard and blocks.
- [[#s-1]] and [[#s-3]] are the sibling sites of this round's two convergences (the binary
  resolver and the plist set).

Round 6 needs:
- a few lines in `upgrade._default_restart`
- one resolver for the daemon commands
- the session-indexer guard plus check/reinstall, wired into `relaunch-fleet`
- typed check reasons
- the test migration

rel: contradicts -> [[plan-4-daemon-resilience#decisions-log]]
