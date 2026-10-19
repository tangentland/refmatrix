---
gmd: "0.1"
id: task-4.5-r4-remedy
title: "Task 4.5: plan-4 round-4 remedy — unknown binary fails closed, one stop grace on every stop path, a reachable --allow-dev, ExitTimeOut on the session indexer"
tags: [task, plan-4, remedy, bsd, launchd, daemon]
metadata:
  node_type: task
  status: approved
  plan: plan-4-daemon-resilience
  wave: W1-a
  created: 2026-10-19
---

# Task 4.5: plan-4 round-4 remedy (W1-a) {#root}

> Plan: [[plan-4-daemon-resilience]]
> Ledger: [[bsd-plan4-daemon-resilience-r4-ffed3df]]
> Wave: W1-a of plan-review-2026-10-14 section `t11-folded-waves` (on branch `wave0-spec-reviews`)
> Status: Approved — TDD RED written (`tests/test_task4_5_r4_remedy.py`)
> Depends on: task 23.0 (test sandbox, 0.79.1) for the hub.log isolation

rel: part-of -> [[plan-4-daemon-resilience]]
rel: amends -> [[plan-4-daemon-resilience]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r4-ffed3df]]
rel: derives-from -> [[plan-review-2026-10-14]]
rel: depends-on -> [[plan-4-daemon-resilience#status-2026-10-01]]

## Scope {#scope}

The open r4 findings as re-verified on 2026-10-01 and again on HEAD `d4bf001` (2026-10-19):
#s-2, #s-3, #s-4, #m-5, #m-6, plus todo G9. r4 #b-1 (hub plist) is CLOSED (bug-028, `7db2e38`)
and is out of scope. Closing this task plus a clean ch-bsd r5 lets plan-4 flip `completed`.

rel: derives-from -> [[bsd-plan4-daemon-resilience-r4-ffed3df#s-2]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r4-ffed3df#s-3]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r4-ffed3df#s-4]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r4-ffed3df#m-5]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r4-ffed3df#m-6]]

## Requirements {#requirements}

### R1 — an unknown binary identity fails closed (r4 #s-2) {#r1}

`binary_identity()` returns `{"dev_tree": None, "error": …}` for a binary whose answer is not the
identity JSON (a pre-0.69 binary printing a version line, a binary that exits non-zero, a path
that does not exist). Its docstring says "unknown, never 'fine'"; the three guards read
`if ident.get("dev_tree"):` and `None` is falsy, so unknown passes:

- `launchctl._refuse_dev_tree` (`launchctl.py:139`) — reached by `install`, `install_hub`,
  `render_hub_plist`;
- `launchctl.check_hub` (`launchctl.py:575`);
- `launchctl.check` (`launchctl.py:741`).

Every guard treats anything but `dev_tree is False` as a refusal. `_refuse_dev_tree` raises a
`RuntimeError` reading `identity unknown`, naming the binary, the identity `error` (the field
nobody read) and the override `--allow-dev`. `check` / `check_hub` return `(False, "… identity unknown …")` and never a
`drifted from its render` reason — an unknown binary is not drift to be "fixed" by
`relaunch-fleet` → `reinstall`. The explicit override (`allow_dev=True`) still installs.

### R2 — one stop grace on every stop path (r4 #s-3) {#r2}

`daemon.stop_daemon(root, *, timeout: float = 5.0)` keeps launchd's old 5 s as its default. The
one helper is `daemon.stop_grace_s()` (`RMX_STOP_GRACE_S`, default `launchctl.EXIT_TIMEOUT_S`).
Enumeration of every stop path at `d4bf001`:

| # | Path | Call | Grace today |
|---|------|------|-------------|
| 1 | `rmx daemon stop` (`cli.py:3057`) | `stop_daemon(root)` | 5.0 default — WRONG |
| 2 | `rmx daemon restart`, launchd branch (`cli.py:3267`) | `graceful_stop(grace=stop_grace_s())` | ok |
| 3 | `rmx daemon restart`, standalone (`cli.py:3297`) | `stop_daemon(timeout=stop_grace_s())` | ok |
| 4 | `restart --relaunch` `_respawn` kick (`cli.py:3327`) | `stop_daemon(root)`, False discarded | 5.0 — WRONG, and spawns beside a live predecessor |
| 5 | `rmx compact` (`cli.py:7670`) | `stop_daemon(root)` | 5.0 — WRONG |
| 6 | `upgrade._default_restart` (`upgrade.py:313`) | `stop_daemon(root)` | 5.0 — WRONG |
| 7 | `launchctl.install(force)` (`launchctl.py:649`) | `graceful_stop(grace=EXIT_TIMEOUT_S)` | the constant, bypassing the helper's override |
| 8 | hub UI `POST /api/daemon {action: stop}` (`ui/server.py:263`, new since r4) | `stop_daemon(root)` | 5.0 — WRONG |

Supervisor paths, listed for completeness and deliberately NOT converged here: the hub watchdog
(`hub.py:372`, `RMX_HUB_KILL_GRACE_S`, defaulting to the same `EXIT_TIMEOUT_S`) and adoption
(`daemon.py:1329`, `ADOPT_GRACE_S` = 20 s: a False there yields to the heartbeat-gated startup
reap and is never reported to an operator as a failure — plan-4 [[plan-4-daemon-resilience#q6]]).

Requirement: paths 1-8 resolve their grace through `stop_grace_s()` — `stop_daemon`'s
`timeout` defaults to `None` meaning `stop_grace_s()`, and `launchctl.install` asks the helper.
`_respawn` (path 4) honours a False the way path 3 does: it raises a `ClickException` naming the
still-alive predecessor and does not spawn.

### R3 — the daemon-plist `--allow-dev` is reachable (r4 #m-5) {#r3}

Decision: wire, do not delete. Parity with `rmx hub launchctl install --allow-dev`
(`cli.py:2649`, bug-028), and the refusal message has told operators to use it since r3. `rmx
daemon launchctl install` gains `--allow-dev` (same help text as the hub's) forwarded to
`launchctl.install(allow_dev=…)`. The refusal message names the CLI flag `--allow-dev`, not the
Python parameter `allow_dev`.

### R4 — the session-indexer plist carries ExitTimeOut (r4 #m-6) {#r4}

`session_launchctl.render_plist` sets `"ExitTimeOut": int(EXIT_TIMEOUT_S)` read from
`launchctl.EXIT_TIMEOUT_S` — one source, no second literal.

### R5 — tests stay out of the live hub.log; the marker-wait line names its root (r4 #s-4) {#r5}

Two halves. (a) Isolation: closed by task 23.0 — `hub.hub_home()` (hence `hub_log_path()`)
resolves under `RMX_SANDBOX_ROOT` (`tests/test_sandbox_redirect.py::
test_redirect_canary_every_home_derived_path_is_in_the_sandbox`), and the audit hook refuses any
write under the real `~/.refmatrix` (`tests/test_sandbox_refusal.py`). This task adds a guard
that a watchdog log line written by a test lands in the sandbox hub.log. (b) The
`_await_shutdown` line (`hub.py:354`) is the one watchdog line with no `{root}` — every sibling
names it; it must name the root so a reader of hub.log can attribute it.

### R6 — todo G9 (orderly spawn-loop) is closed, not open {#r6}

G9 ("orderly launchd service spawn-loops behind a manual daemon, 11k runs") is the incident task
4.4 fixed: a supervised start adopts an unsupervised live daemon instead of exiting 1 into the
KeepAlive loop (`Daemon._adopt_unsupervised`, `tests/test_daemon_adopt.py`, two tests); r1
verified orderly adopted with launchd `runs` static for 30 min; r2's residual (the
`RMX_SUPERVISED` gate missing from 2/8 plists) was closed in r3 and every plist is drift-checked
by `launchctl.check`. It is not a real open defect; the todo row still reads `Resolveable`. No
new test — the requirement is bookkeeping: the G9 row flips to Done citing task 4.4,
`tests/test_daemon_adopt.py` and this spec.

rel: depends-on -> [[task-4.4-plan-4-daemon-resilience]]

## Acceptance Criteria {#acceptance}

- **AC-1 (R1)** {#ac-1} `_refuse_dev_tree` raises (`identity unknown`) for each of: a binary printing `rmx 0.68.0`,
  one exiting 3 with no output, a path that does not exist. The message names the binary, the
  identity error, and `--allow-dev`. A binary answering `dev_tree: false` is not refused (control).
- **AC-2 (R1)** {#ac-2} `launchctl.install(root, rmx=<unknown>)` raises (`identity unknown`) before any plist is
  written and before any `launchctl` subprocess call; with `allow_dev=True` it installs (control).
  The same holds for `reinstall(root, rmx=<unknown>)` (the `relaunch-fleet` path: the installed
  daemon plist survives byte-identical) and `install_hub(rmx=<unknown>)`. Older tests that rendered
  against an unreadable binary take the shared `deployed_rmx` fixture (`tests/conftest.py`).
- **AC-3 (R1)** {#ac-3} `launchctl.check(root, rmx=<unknown>)` on an installed plist rendered
  for another binary returns `(False, why)` with `identity unknown` in `why` and no `drifted` reason.
- **AC-4 (R1)** {#ac-4} `launchctl.check_hub(rmx=<unknown>)` — the same.
- **AC-5 (R2)** {#ac-5} With `RMX_STOP_GRACE_S=7.5`, paths 1, 5, 6, 7, 8 hand `graceful_stop`
  a grace of 7.5 (paths 2 and 3 already do; regression controls), and `stop_daemon(root)` with
  no timeout does too.
- **AC-6 (R2)** {#ac-6} `rmx daemon stop` against a real process that drains 6 s after SIGTERM
  with a fresh heartbeat exits 0 with `daemon stopped` (at HEAD: exit 1 at 5.0 s).
- **AC-7 (R2)** {#ac-7} `rmx daemon restart --standalone --relaunch`: when `_respawn`'s stop
  returns False the command fails naming the predecessor and `spawn_daemon` is called exactly
  once (the initial respawn), and that stop was given `stop_grace_s()`.
- **AC-8 (R3)** {#ac-8} `rmx daemon launchctl install --allow-dev` with a dev-tree binary
  writes the plist whose `ProgramArguments[0]` is that binary; without the flag the command
  fails and its message names `--allow-dev`. No real launchd is touched.
- **AC-9 (R4)** {#ac-9} `session_launchctl.render_plist(root)["ExitTimeOut"] ==
  int(launchctl.EXIT_TIMEOUT_S)`, and `session_launchctl.py` names `EXIT_TIMEOUT_S` (no literal).
- **AC-10 (R5a)** {#ac-10} `hub.hub_log_path()` is under `RMX_SANDBOX_ROOT`, and a line logged by
  `Watchdog._await_shutdown` lands in that file. GREEN at HEAD by design (23.0 regression guard).
- **AC-11 (R5b)** {#ac-11} the `_await_shutdown` "still alive after the grace and shutting down"
  line contains `str(root)`.
- **AC-12 (R6)** {#ac-12} `docs/architecture/todo.md` G9 row reads Done with the citations in
  [[#r6]]; the plan-4 `#status-2026-10-01` table gains a row per finding closed by this task.
- **AC-13** {#ac-13} no test in `tests/test_task4_5_r4_remedy.py` calls real `launchctl`, opens a
  live store, or writes outside the sandbox / its tmp roots (23.0 audit hook enforces).

## Files to Create / Modify {#files}

- `src/refmatrix/launchctl.py` — `_refuse_dev_tree`, `check`, `check_hub` (R1); `install` grace
  via `daemon.stop_grace_s()` (R2); refusal message (R3).
- `src/refmatrix/daemon.py` — `stop_daemon(timeout: float | None = None)` (R2).
- `src/refmatrix/cli.py` — `_respawn` honours False (R2); `daemon launchctl install --allow-dev`
  (R3).
- `src/refmatrix/session_launchctl.py` — `ExitTimeOut` (R4).
- `src/refmatrix/hub.py` — `{root}` in the `_await_shutdown` line (R5b).
- `docs/architecture/todo.md`, `workflow/plans/plan-4-daemon-resilience.md` (R6).
- `tests/test_task4_5_r4_remedy.py` (new, RED), `workflow/test_mock_registry.md`.

## Test Strategy {#tests}

Tier 1 (pytest), all inside the 23.0 sandbox: launchd surfaces are faked exactly as
`tests/test_plan4_remedy_r3.py` fakes them (plist path, agents dir, `_wait_loaded`,
`_loaded_env_drift`, `subprocess.run` recorder primed AFTER the identity cache); real child
processes stand in for draining daemons (`_draining_process`, reused); tmp roots are short
`/tmp/rmx45-*`. RED evidence: `workflow/review-output/task4.5-red.log`.

rel: depends-on -> [[test_mock_registry]]
