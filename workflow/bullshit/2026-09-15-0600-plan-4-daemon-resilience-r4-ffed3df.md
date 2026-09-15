---
gmd: "0.1"
id: bsd-plan4-daemon-resilience-r4-ffed3df
title: "ch-bsd — plan-4 daemon resilience, round 4: launchd's budget, the shutdown marker, the two-tick rule and the kept pid all close and hold live (0 SIGKILLs, a 29 s drain that survived); but the hub's own plist is rendered from `which rmx` with no dev-tree refusal and no drift check, and 'unknown binary' reads as 'not a dev tree'"
severity: BULLSHIT
plan: plan-4-daemon-resilience
task: remedy-plan-4-r3
tags: [bsd, plan-4, daemon, hub, watchdog, launchd, plist, grace]
---

# ch-bsd findings — plan-4 daemon resilience, round 4 (remedy 26404fe merged f5f0590, follow-up 5df7185 merged ffed3df) {#root}

**Commit range:** ef4365a..ffed3df. Plan-4 content: `26404fe` (merged `f5f0590`) and `5df7185` (merged `ffed3df`); judged at HEAD `ffed3df`, deploy `~/refmatrix` at `ffed3df` (`rmx version -v --json` → `dev_tree: false`, code `/Users/tholley/refmatrix/src`), fleet relaunched twice 05:27–05:40.
**Date:** 2026-09-15 06:00
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-4 surfaces):** `launchctl.py`, `daemon.py`, `hub.py`, `cli.py`, `tests/test_plan4_remedy_r3.py` (542 lines) + 4 legacy test files, plan Q12–Q16, summary, bug + mock registries, todo G14.

rel: evidence-for -> [[plan-4-daemon-resilience]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r3-ef4365a]]
rel: derives-from -> [[bsd-pattern-guard-cannot-fire]]

## What closed — checked, not read {#verified}

Gates run by me: **114 passed at HEAD** (`workflow/review-output/pytest-bsd-plan4-r4-head.log`: plan4_remedy(_r2,_r3), hub_watchdog(_grace), daemon_restart_cli, verb_parity); `rmx install-hooks --check` → in sync; launchd's own log since 05:20 captured to `bsd-plan4-r4-launchd.log` (356 `com.refmatrix.*` lines); probes `bsd-plan4-r4-probe-identity.log`, `bsd-plan4-r4-probe-stopgrace.log`.

- **#b-1 (launchd is a supervisor too) — closed, live.** `launchctl print` on all 9 daemon+hub labels: `exit timeout = 45`; `EXIT_TIMEOUT_S` is one constant read by the daemon plist, the hub plist, `hub.DEFAULT_KILL_GRACE_S` and `daemon.DEFAULT_STOP_GRACE_S`. **Zero `Sending SIGKILL` / `did not exit` lines on any `com.refmatrix.*` label since the deploy** (24 in the four hours before) — I ran the query, not the deploy script. And the fix is not vacuous: at 05:28 this project's daemon drained **29 s** (`pool drain disp/cli/bg: timed out` ×3 at 10 s each, then `final flush skipped: _store_lock contended`) and launchd recorded `exited due to exit(0), ran for 3698588ms` — under the old 5 s budget that drain was the SIGKILL that corrupts the entity-links index. `daemon restart` under launchd now pauses the watchdog, `graceful_stop`s, and kicks without `-k` when it stopped; `_verify_relaunch` refuses to `kill -9` a predecessor whose heartbeat is fresh (mutation P4-C fails in 41.9 s); the standalone path refuses to spawn beside a live one (real `_draining_process`, mutation P4-I).
- **#b-2 (the shutdown produces its own signal) — closed, and it can fire.** `shutdown.started` is written at `daemon.py:1532`, the FIRST statement of `serve_forever`'s `finally` — before `_shutdown_event.set()` (1539) and 26 lines before `_stop_heartbeat()` (1558) — and unlinked at boot (1265). `_await_shutdown` reads the marker, not the beat, and carries its caller's precondition in the docstring. Against the PATTERN's three rules: the producer (the shutting-down daemon) is still running when the guard runs; the caller's state (`hb_age > 60`, pid alive) and the callee's condition (marker younger than 60 s) can both hold; the closing test drives `_check`, not `_restart`, on a real process that traps SIGTERM and drains 3 s, and asserts the kick landed after the process was gone. Mutations P4-D (back on the heartbeat) and P4-F (marker never written) fail.
- **#s-3 — closed.** `noproc_counts`: the dead branch kicks on the second consecutive no-process tick (mutation P4-E); `daemon restart` pauses/resumes the hub watchdog for the root, best-effort and said when the hub is down (the deploy log shows exactly that wording four times with the hub down). Both legacy tests were rewritten to the new contract, each asserting no restart on the first tick.
- **#s-4 — closed for the DAEMON plists only.** `rmx=` is threaded through `render_plist` / `check` / `reinstall` / `install`; `relaunch-fleet` passes the binary it resolved; `install` refuses a dev tree before anything is written or booted out (probe: a fake binary answering `dev_tree: true` → `RuntimeError`, plist not written, zero `launchctl` calls). See [[#b-1]] and [[#s-2]] for what it does not cover.
- **#m-5 / #m-6 — closed.** `graceful_stop` records `report["pid"]` and `stop_daemon` escalates on it (mutation P4-H); `_heartbeat_touch` logs once per errno and recovers when the directory returns (mutation P4-J).
- **bug-013 / bug-022 / bug-023 — closed.** `install(force)` asks the daemon to stop with the grace before launchd's bootout (P4-M); `install_hub(force)` sends the hub's stop op (P4-N), waits `BOOTOUT_WAIT_S` for the unload and errors instead of rewriting (P4-P), settles and bootstraps again when the label vanishes (P4-Q). The dev-tree test now fakes every launchd surface: after my own full run, `ls ~/Library/LaunchAgents | grep rmxp4` = **0** (bug-023 was a real agent for a deleted tmp root). The hub-install race itself is proven by the `_hub_install_fakes` state machine only — the live 05:27 failure predates the fix, and no forced hub reinstall has run on the fixed code. Honest, and said as much in the summary.
- **Registries / deferrals.** Mock registry rows exist for `_draining_process`, the launchd fakes, `_hub_install_fakes` and `_fake_binary` — the first round in this lineage with no registry gap. Deferral sweep over all 1207 added lines in the plan-4 sources and tests: no hard and no soft deferral. Plan status `in-progress` in both files. `bug-020`…`bug-024` and todo `G14` carry the deploy's own findings, including the one the plan created.

## Findings {#findings}

### BULLSHIT: the hub's own plist is rendered from `which rmx`, refuses nothing, and no `check` exists for it — Q15 covers 8 of the 9 plists this module writes {#b-1}

**File:** `src/refmatrix/launchctl.py:249-253` (`render_hub_plist(*, port, host)` → `rmx = _rmx_path()`), `launchctl.py:334-390` (`install_hub`: no `rmx=`, no `_refuse_dev_tree`, no `binary_identity`), `src/refmatrix/cli.py:2480-2491` (`rmx hub launchctl install [--force]` — the command an operator runs from whatever shell they are in), and the absence of any `check_hub` sibling to `check(root, rmx=)`.
**What:** Q15 is written as a rule about plists: "`render_plist` / `check` / `reinstall` / `install` take `rmx=` … `install` refuses a dev-tree binary before anything is booted out or written". The same commit edited `render_hub_plist` — to add `ExitTimeOut` — two lines below the `_rmx_path()` call it left alone. Probe (`bsd-plan4-r4-probe-identity.log`), with `RMX_BIN` pointed at a binary that answers `dev_tree: true`:
```
render_hub_plist params: ['port', 'host']          # no rmx=
install_hub mentions _refuse_dev_tree: False | binary_identity: False
hub ProgramArguments[0] = …/bsdid-uw_duiz5/rmx_dev   # the dev binary, unrefused
hub ExitTimeOut = 45                                  # this round's fix, on the same plist
```
**Why it's bullshit:** The hub is not one more supervised process — it is the fleet's watchdog, the owner of the shared model workers (it spawns them with its own `venv=` and logs that path), and the version handshake that restarts every daemon. Plan 1's incident was a venv executing another tree; plan 4 built the refusal for that and pointed it at the daemon plists. Worse than the daemon case: a drifted daemon plist is caught by `check(root, rmx=)` on every `relaunch-fleet`, while nothing on any path ever compares the hub plist to its render, so a hub plist aimed at a dev tree survives every deploy silently. The daemon-side hole was r3 #s-4 (SKETCHY); this is the same hole on the sibling surface the same function touched — the quoted-line-sibling shape at its 4th sighting in this lineage, which the escalation rule takes to BULLSHIT.
**Fix:** `render_hub_plist(*, port, host, rmx=None)`; `install_hub(..., rmx=None, allow_dev=False)` calling `_refuse_dev_tree(rmx)` before the stop order and before the write; `hub_launchctl_install` passing `sys.argv[0]`; and a `check_hub()` that compares the installed hub plist to its render so `hub status` / `relaunch-fleet` can report the drift. Test: `install_hub(rmx=<dev binary>)` raises, writes no plist and makes zero `launchctl` calls — the shape `test_install_refuses_a_dev_tree_binary` already has.
**Pattern match:** YES — [[impression_bsd_quoted_line_sibling]], [[feedback_deploy_tree_is_the_runtime]], [[impression_bsd_gate_in_an_artifact_no_deploy_step_rerenders]].
rel: contradicts -> [[plan-4-daemon-resilience#decisions-log]]
rel: contradicts -> [[project-profile#constraints]]

### SKETCHY: `binary_identity` says an unknown binary is not a dev tree — its own docstring says the opposite, and `relaunch-fleet --rmx <anything unreadable>` then rewrites every drifted plist to it {#s-2}

**File:** `src/refmatrix/launchctl.py:107-132` (`binary_identity`: `except Exception → {"dev_tree": None, "error": …}`, docstring: "unknown, never 'fine'"), `launchctl.py:134-140` (`_refuse_dev_tree`: `if ident.get("dev_tree"):` — `None` is falsy), `launchctl.py:641-645` (`check`: same test, then it proceeds to compare and report drift).
**What:** Probe (`bsd-plan4-r4-probe-identity.log`), three binaries:
```
old-binary       {'dev_tree': None, 'error': 'JSONDecodeError: …'}      -> NO REFUSAL
failing-binary   {'dev_tree': None, 'error': 'IndexError: …'}           -> NO REFUSAL
dev-tree         {'dev_tree': True,  'import_path': '/dev/src/…'}       -> refused
```
A pre-0.69 binary, a binary whose venv is mid-rebuild, or a mistyped `--rmx /path/that/does/not/exist` all land in the first two rows. `check` then reports `ProgramArguments` drift on every plist (the path differs), `relaunch-fleet` calls `reinstall(rmx=…)` → `install(force=True, rmx=…)`, the refusal passes, and all eight plists are rewritten to a binary launchd cannot run — the r3 #s-4 incident with "unreadable" in place of "dev tree". The guard is correct for the case it was written against and cannot fire for the case its own docstring claims.
**Fix:** one line — `if ident.get("dev_tree") is not False: raise RuntimeError(… ident.get("error") …)`, and `check` returns `(False, "identity unknown: …")` so nothing "fixes" the drift. Test: a binary that prints a version line and one that exits non-zero both refuse.
**Pattern match:** YES — [[bsd-pattern-guard-cannot-fire]] (the branch that cannot take the safe path), [[impression_bsd_unread_diagnostic_field]] (`error` is recorded and read by nobody).
rel: contradicts -> [[plan-4-daemon-resilience#decisions-log]]

### SKETCHY: "ONE stop grace for every supervisor" reaches 3 of the 7 stop paths — `rmx daemon stop`, `catalog vacuum`, `rmx upgrade` and the `--relaunch` respawn still pass `stop_daemon`'s 5 s default, and the respawn ignores the False the main path was just taught to honour {#s-3}

**File:** `src/refmatrix/daemon.py:5392` (`stop_daemon(root, *, timeout: float = 5.0)` — the default nobody changed), callers `src/refmatrix/cli.py:2882` (`rmx daemon stop`), `cli.py:3152` (`_respawn`, the `kick` handed to `_verify_relaunch` on the standalone path: `stop_daemon(root)` then `spawn_daemon(...)` with the return discarded), `cli.py:6242` (`catalog vacuum`), `src/refmatrix/upgrade.py:313`. Fixed this round: `cli.py:3089`, `cli.py:3120`, `launchctl.py:550`.
**What:** Probe (`bsd-plan4-r4-probe-stopgrace.log`) against a real process that drains 9 s — well inside the 60 s budget this commit declared:
```
declared: stop_grace_s()=45  SHUTDOWN_BUDGET_S=60  stop_daemon default=5.0
stop_daemon(root)                          -> False after 5.0s  kill='withheld: heartbeat 0s old (working)'
stop_daemon(root, timeout=stop_grace_s())  -> True  after 9.1s
```
So `rmx daemon stop` prints "daemon did not stop within timeout" and exits 1 on a daemon that is shutting down exactly as designed, and `catalog vacuum` aborts on the same line. Nothing is killed — the heartbeat gate holds — but the operator is told a healthy drain failed, by the command whose plan just declared one number. `_respawn` is the sharper half: the #b-1 fix at `cli.py:3122` refuses to spawn beside a live predecessor, and thirty lines below, in the same function, the retry path stops for 5 s, throws the answer away and spawns. (`spawn_daemon`'s ping check and the child's `_reap_predecessor` yield catch it today — which is why this is SKETCHY, not the second BULLSHIT.)
**Fix:** `stop_daemon(root, *, timeout: float | None = None)` defaulting to `stop_grace_s()`, or pass it at the four call sites; `_respawn` honours the False the way its sibling does. Test: `rmx daemon stop` on the `_draining_process` (9 s) returns 0 with "daemon stopped".
**Pattern match:** YES — [[impression_bsd_partial_bound_guard]] / [[impression_bsd_quoted_line_sibling]]; "one number for every supervisor" is a claim about a set, and a `grep` of the set is the acceptance.
rel: contradicts -> [[plan-4-daemon-resilience#decisions-log]]

### SKETCHY: the tests write into the live `~/.refmatrix/hub.log`, and the new `_await_shutdown` line names no root — all 8 of tonight's marker-wait lines are tests, and nothing in the file says so {#s-4}

**File:** `src/refmatrix/hub.py:345` (`_log(f"watchdog: pid={pid} still alive after the grace and shutting down …")` — the only watchdog line without `{root}`; its siblings at 364/373/381 all carry it), `tests/test_plan4_remedy_r3.py:236` and `:253` (`hub_mod.Watchdog()._await_shutdown(root)` with `_log` unpatched — line 276 does patch it), `tests/test_plan4_remedy_r2.py:243,302`, `tests/test_plan4_remedy.py:118,128,143`, `src/refmatrix/hub.py:1051-1058` (`hub.graceful_stop` logs every call).
**What:** `hub_log_path()` is `~/.refmatrix/hub.log` regardless of the root under test, so a pytest run appends to the live hub's log. Counted now: **32 lines naming a `/tmp/rmxp4-…` root, 11 naming `/nowhere/.refmatrix`, 8 `still alive after the grace and shutting down`** — and my own verification run added three more at 05:55–05:56, including a marker-wait line for pid 28613 that reads exactly like a production event. Every one of the 8 marker-wait lines is a test: Q13's remedy has never been observed firing on a real store, and because the line names no root, no reader of hub.log can tell that. This is the surface r3 used to prove `_restart` signals at t=0 and to tell thiquet's throttle-gap kick from a wedge; it is also bug-023's family (a test reaching a live artifact), which this round was asked to flag.
**Fix:** add `{root}` to the line (one token, and it is the first thing a reader needs); point `hub_log_path` at a tmp `RMX_HOME` in the test fixtures, or patch `hub._log` in every test that instantiates a `Watchdog`. Acceptance: a full test run adds zero lines to `~/.refmatrix/hub.log`.
**Pattern match:** YES — [[impression_bsd_cost_measured_idle]] (the evidence surface must be able to distinguish the claim), bug-023.
rel: contradicts -> [[claude#no-silent-failures]]

### MEH: `install`'s `allow_dev` escape hatch cannot be reached from any command, and the refusal message tells the operator to use it {#m-5}

**File:** `src/refmatrix/launchctl.py:511` (`install(..., allow_dev: bool = False)` — the only occurrence of the name in `src/`), `launchctl.py:137-140` (the message: "Run this with the deployed rmx, **or pass allow_dev to install**"), Q15 ("`allow_dev` overrides").
**What:** No CLI option, no verb and no other caller passes it; `reinstall` does not forward it. A developer who genuinely wants a dev-tree plist on a scratch root is told to do something no command exposes, and the decisions log records an override that does not exist. A dead flag is dead code with a documentation cost.
**Fix:** either a hidden `--allow-dev` on `daemon launchctl install` that forwards it, or delete the parameter and the sentence.
**Pattern match:** YES — [[impression_bsd_dead_flag_surface]].

### MEH: the 10th `com.refmatrix.*` label — the session indexer — still carries launchd's 5 s default; "every label now `exit timeout = 45`" is wrong by one {#m-6}

**File:** `src/refmatrix/session_launchctl.py:46-83` (`render_plist`: `RunAtLoad`, `StartInterval`, `ProcessType`, no `ExitTimeOut`), Q12's live note ("every label now `exit timeout = 45`, the hub too"), and the deploy log's own exit-timeout table, which lists `com.refmatrix.session-indexer.viascope-0173069e2d90 5` three lines above the claim.
**What:** `launchctl print` confirms it: nine labels at 45, that one at 5. The harm is small — the job runs `rmx session ingest`, writes through the daemon and exits in ~0.7 s per launchd's own `ran for 753ms` — so a SIGKILL would abort a client loop, not a store write. The claim is the problem: this plan exists because two budgets were never put side by side, and the sweep that found launchd's stopped at the labels the plan already knew about.
**Fix:** `"ExitTimeOut": int(launchctl.EXIT_TIMEOUT_S)` in the session-indexer render too (one line, one constant), or state in Q12 which labels are out of scope and why.
**Pattern match:** YES — an "every X" claim a `launchctl print` loop disproves; the INDEX leaderboard note for runs 11–25 names this exact shape.

## Verdict {#verdict}

**DIRTY — 6 findings (1 BULLSHIT, 3 SKETCHY, 2 MEH).** Plan-4 may NOT flip to `completed`; the blocker is [[#b-1]] and it is roughly ten lines plus a test.

This is the strongest round in the lineage. All seven r3 items closed at their quoted lines, and the two that mattered closed in behaviour, not on paper: launchd's log has zero SIGKILLs on any `com.refmatrix.*` label since the deploy where it had 24 in the preceding four hours, and this project's daemon proved the budget is load-bearing by draining 29 s and exiting 0 where the old 5 s would have killed it mid-flush. The `_await_shutdown` guard now reads a value the shutting-down daemon itself produces, its caller's precondition is written beside it, and its closing test drives the caller on a real process — the three things [[bsd-pattern-guard-cannot-fire]] asked for. The mock registry is complete for the first time in this lineage, and the dev-tree test that once installed a real LaunchAgent now makes zero `launchctl` calls under a full run.

What is left is the surface the sweep did not enumerate, again: the hub's plist (the one plist with no `rmx=`, no refusal and no drift check), the unknown-binary branch of the new identity guard, and the four stop paths still holding launchd's old 5 s while three of them were changed to 45.

Gates: 114 passed at HEAD; `install-hooks --check` in sync; 9/9 daemon+hub labels at `exit timeout = 45`; hub up (pid 13847) with 8/8 daemons at v0.69.1, `restarts=0`, and exactly 2 model-worker processes after the second relaunch (bug-024's 16 are gone). Outside plan-4: `rmx daemon start --no-watch` (pid 41676, 10 days old) and `rmx daemon restart --relaunch` (pid 18148, 6 days old) are still alive on `/Volumes/littlebig/…` roots — a hung deploy command from before this plan, worth a look when the fleet is next idle.

rel: contradicts -> [[project-profile#constraints]]
rel: contradicts -> [[claude#no-mocks]]
