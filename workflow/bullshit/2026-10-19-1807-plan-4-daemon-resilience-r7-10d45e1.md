---
gmd: "0.1"
id: bsd-plan4-daemon-resilience-r7-10d45e1
title: "ch-bsd plan-4 r7 — the r6 amendment closes all five r6 findings in behaviour (10/10 mutants killed, including r6's two survivors); services export their own binary safely; one stale mock-registry classification left"
tags: [bsd, plan-4, launchd, daemon, identity, resolver, remedy]
severity: MEH
plan: plan-4-daemon-resilience
task: task-4.6-r5-remedy
---

# ch-bsd findings — plan-4 r7: task 4.6 r6 amendment (e4de166..10d45e1) {#root}

**Commit:** 10d45e1 (range `e4de166..10d45e1`: RED + spec `#r6-amend` `e12b5a7`, GREEN
`10d45e1`; branch `plan4-remedy-w1`; clone `/Volumes/littlebig/refmatrix-plan4-remedy`)
**Date:** 2026-10-19 (written 2026-10-19T18:07:27-0700)
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 9 (`cli.py`, `daemon.py`, `hub.py`, `launchctl.py`, `upgrade.py`, the 4.6 test
file, spec, summary, mock registry)

rel: derives-from -> [[bsd-plan4-daemon-resilience-r6-a710e48]]
rel: evidence-for -> [[task-4.6-r5-remedy]]

**Safety.** I used the same method as r6:
- Every probe and mutant ran in `git archive` copies of `10d45e1` and `e4de166` under the
  scratchpad (`r7/`), using `.venv-eval/bin/python -B` and a `PYTHONPATH` pinned to the copy.
- No `src/` or `tests/` file in the clone was edited.
- No launchd, live store, socket, `~/.refmatrix`, real venv, `~/bin/rmx` or
  `~/claude_tools/refmatrix` was touched.
- The live plists were read only (PlistBuddy).

## What closed, in behaviour {#closed}

- **r6 #b-1 (hub UI supervise): CLOSED.**
  - Real-process probe: `pb/<tree>/svc/rmx` is a real executable that answers the deployed
    identity. It runs `rmx hub start --no-detach --no-http` with HOME set to tmp. Its `Hub.run`
    then spawns the exact child shape from `ui/server.py:191`
    (`sys.executable -m refmatrix.cli daemon launchctl install --check`, env `{**os.environ}`):
    ```
    head  HUB RMX_BIN = …/pb/head/svc/rmx
          CHILD rc 1 | plist DRIFT not installed: …/home/Library/LaunchAgents/…plist   (resolver passed)
    base  HUB RMX_BIN = None
          CHILD rc 1 | Error: cannot tell which rmx to render into a plist: … cli.py …
    ```
  - AC-30 drives `/api/projects/init {"launchd": true}` through the real server code and asserts
    the written `ProgramArguments[0]`.
  - Mutants KILLED: N4 (export removed from `hub start`), N5 (from `daemon start`) and N10
    (export raises).
- **r6 #s-1 (watchdog resumed before verify): CLOSED.**
  - The r6 probe re-run at HEAD gives `['verify', 'pause', 'graceful_stop', 'kickstart',
    'verify', 'resume']`. At a710e48 it gave `… kickstart, resume, verify`.
  - When verify fails to converge (40 s, sleep stubbed), the order is `… verify, resume` and the
    command exits 1 with the verify's own message. The new `except click.ClickException: raise`
    keeps that message from being re-wrapped.
  - The pause is `grace*2+60` (120 s at the default 30 s grace). That covers the stop grace plus
    the 40 s verify.
  - Mutants KILLED: N3 (`after_kick` after the resume) and N9 (CLI verifies outside the helper).
- **r6 #m-1 (untested behaviours): CLOSED.** r6's two survivors are now KILLED:
  - M4 (resume out of `finally`), by `test_supervised_restart_resumes_when_the_verify_raises`;
  - M10 (session unload wait dropped), by
    `test_session_force_install_raises_when_the_bootout_does_not_unload`.
- **r6 #m-2 (rule-(a)-only messages): CLOSED.**
  - `_print_code_identity` and `_verify_relaunch` now word the dev tree through
    `upgrade.dev_tree_message`.
  - The daemon ping and the hub identity carry `dev_reason`.
  - A remote identity that reports no reason is said to be unexplained, not guessed as
    venv-mismatch.
  - Mutants KILLED: N7 (ping drops `dev_reason`) and N8 (the old wording).
- **r6 #m-3 (bookkeeping): CLOSED as named.** The summary reports the `task4.6-r6-green-full.log`
  run (1 failed, 3049 passed), and the cited log files exist. The `supervised_restart` registry
  row is now `internal-active`. Its sibling row is not: see [[#m-1]].
- **Tests.**
  - Targeted run in a non-dev-tree scratch copy: the 10 r6 files plus `test_hub.py` and
    `test_bug129_hub_pidfile.py` give **225 passed, 0 failed**.
  - The branch's full log `task4.6-r6-green-full.log` has 1 failure (the gmd repo-scope gate) and
    3049 passed.
  - The deferral sweep over the added `src/` and `tests/` lines found nothing.

## The new startup export — deploy safety {#export}

`launchctl.export_service_binary` (`launchctl.py:207-235`) runs first in `hub start`
(`cli.py:2554-2558`) and `daemon start` (`cli.py:3013-3015`).

**Does launchd get `RMX_BIN=~/bin/rmx`? YES.** I read `ProgramArguments[0]` from all 8 daemon
plists and the hub plist with PlistBuddy: 9 of 9 are `/Users/tholley/bin/rmx`. That is a symlink to
`~/refmatrix/.venv/bin/rmx`. `_rmx_path` uses `abspath` without resolving symlinks, so it accepts
the path (`isfile`/`X_OK` follow the link) and exports `/Users/tholley/bin/rmx` as written.

**Can it pin a stale binary across a deploy? NO.**
- **Not persisted in a plist.** None of the 9 live plists has an `EnvironmentVariables:RMX_BIN`.
  The renderers build their env from explicit keys only. The only `os.environ` reads in
  `launchctl.py`/`session_launchctl.py` are `RMX_BIN` (the resolver), `RMX_WORKER_IDLE_S`,
  `RMX_HUB_QUEUE_ALERT_INTERVAL`, `RMX_HUB_SETTLE_S` and `RMX_LAUNCHCTL_BOOTOUT_WAIT_S`. A
  service's exported value never reaches a rendered plist.
- **A path, not a version.** The value is the stable symlink path. A deploy fast-forwards
  `~/refmatrix` under the same editable venv, so the next exec of that path runs the new code.
- **Children that survive a restart.** These are hub-spawned unsupervised daemons
  (`spawn_daemon_subprocess`, `hub.py:145/393`, `bus.py:538`, `ui/server.py:267`). They carry the
  same stable path. The hub itself restarts on every deploy (`modelsrv.py` version handshake,
  `os._exit(1)`) and re-exports from its fresh argv[0].
- **A service started from a transient binary** (a clone or tmp venv) would hand its children
  that path. Every consumer is a plist command, and those re-run the identity guard by exec at
  use time. A vanished binary reads "unknown" and a dev binary reads "dev tree", and both are
  refused (fail closed). This is not silent and not filed.
- **An operator's own `RMX_BIN`** is kept and never overwritten (N6 KILLED). That is the
  documented override.

**Does any service child inherit `RMX_BIN` where it must not? NO.**
- Nothing outside `launchctl.py` reads `RMX_BIN`. A grep of `src/`, `tools/`, `scripts/`, `bin/`
  and `.claude/hooks` finds no other reader, and the generated hooks do not use it.
- The hub's children are the scheduler (`curator scan`, `ingest`, `sync`), `/ws/op`
  (`ingest/embed/sync/vacuum/checkpoint/reingest`), the UI init steps and daemon spawns. Only the
  UI's `daemon launchctl install` consumes the variable, and that is the intended consumer.
- Claude Code hooks and the MCP server are children of Claude Code, not of the hub, so they
  inherit nothing from it.

**Test isolation.** `export_service_binary` writes `os.environ` directly. The new tests unset it
through `_clear_rmx_bin` (setenv then delenv, so monkeypatch restores it). Under pytest, argv[0]
is never an `rmx` binary, so an unpatched `hub start`/`daemon start` via CliRunner exports nothing.

## Findings {#findings}

### MEH: a sibling mock-registry row still says `internal-pending` for functions GREEN shipped {#m-1}

**File:** `workflow/test_mock_registry.md:150` (the `session_launchctl.check` / `reinstall` /
`is_installed` row: "`raising=False` for the not-yet-existing two", class `internal-pending /
internal-active / external`)
**What:** r6 #m-3 named the `supervised_restart` row, and that row was flipped
(`test_mock_registry.md:149`). The row directly below it describes `session_launchctl.check` and
`reinstall` as not yet existing and as `internal-pending`. Both have shipped since `9851562`, and
AC-17..AC-19 run them unfaked.
**Fix:** drop "not-yet-existing" and reclassify the row `internal-active / external`.
**Pattern match:** YES. See [[impression_bsd_quoted_line_sibling]]: the quoted row was fixed and
its sibling was not. The impact is bookkeeping only.
rel: contradicts -> [[test_mock_registry]]

## Mutation table {#mutations}

All 10 mutants were run against the four targeted files (`scratchpad/r7/mut.log`), and all 10
were KILLED:
- M4: resume out of `finally` (r6 survivor)
- M10: session unload wait dropped (r6 survivor)
- N3: `after_kick` after the resume
- N4: no export in `hub start`
- N5: no export in `daemon start`
- N6: export overwrites the operator's `RMX_BIN`
- N7: ping drops `dev_reason`
- N8: old rule-(a) wording
- N9: CLI verifies outside the helper
- N10: export raises

## Verdict {#verdict}

1 finding (0 BULLSHIT, 0 SKETCHY, 1 MEH). All five r6 findings close in behaviour, and each one is
mutation-guarded. The new startup export is deploy-safe:
- launchd services export `/Users/tholley/bin/rmx`;
- the value is never persisted in a plist;
- the path cannot go stale across a fast-forward deploy;
- no unintended consumer inherits it.

**Plan-4 has no blocker left: it may flip `completed`** once the one-line registry fix in
[[#m-1]] lands as part of the close-out sweep. That fix is MEH-only bookkeeping. Strictly, this
run is not CLEAN.

rel: contradicts -> [[plan-4-daemon-resilience#decisions-log]]
