---
gmd: "0.1"
id: bsd-plan4-daemon-resilience-r3-ef4365a
title: "ch-bsd — plan-4 daemon resilience, round 3: all eight r2 findings closed at their lines and proven live; but the plan's own deploy step is a bare `kickstart -k` under launchd's 5 s ExitTimeOut (five daemons SIGKILLed mid-drain tonight), and the #s-5 remedy waits on a heartbeat the shutdown stops first"
severity: BULLSHIT
plan: plan-4-daemon-resilience
task: remedy-plan-4-r2
tags: [bsd, plan-4, daemon, hub, watchdog, launchd, heartbeat]
---

# ch-bsd findings — plan-4 daemon resilience, round 3 (remedy 26d99dc + 1c5a68e, merged ef4365a) {#root}

**Commit range:** e1dba80..ef4365a (branch `remedy-plan-4-r2`: 26d99dc merged 168820d; 1c5a68e merged ef4365a); judged together with 4d31e24 (bug-015, merged f4187d6) and 72f61e0 / f733f6c (bug-014, merged 4ab21eb / 7bca4bb) on the same surfaces. Production = HEAD 7bca4bb / deploy `~/refmatrix` 0.69.1 (`rmx version -v`: `/Users/tholley/refmatrix/src`), fleet relaunched onto it 03:02–03:05.
**Date:** 2026-09-15 03:21
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-4 commits):** 14 (daemon, hub, launchctl, cli; test_plan4_remedy_r2 481 lines; plan Q9–Q11; task-4.1 spec; summary; mock + bug registries)

rel: evidence-for -> [[plan-4-daemon-resilience]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r2-e1dba80]]
rel: derives-from -> [[bsd-pattern-guard-cannot-fire]]

## What closed (verified by probe, by launchd's own log, or live — not by reading) {#verified}

Logs: `workflow/review-output/pytest-bsd-plan4-r3-head.log` (**96 passed** at HEAD: plan4_remedy(_r2), hub_watchdog(_grace), daemon_adopt, bug015_wedge, verb_parity), `bsd-plan4-r3-probe.log` (P1), and the unified log (`log show`, launchd's own words) quoted below.

- **#b-1 (supervised gate) — closed, live.** `is_supervised_start` reads `XPC_SERVICE_NAME`; launchd really exports it: `ps -wwE` on the live project daemon (pid 55186) shows both `XPC_SERVICE_NAME=com.refmatrix.daemon.refmatrix-fb619c669f75` and `RMX_SUPERVISED=1`. `launchctl print` on all 8 labels: `RMX_SUPERVISED => 1` on 8/8 (r2: 6/8). `~/bin/rmx daemon launchctl install --check` → `plist in sync` on the project root AND on `~/.refmatrix` (the two r2 drifters). `launchctl.check` compares bytes, then loaded state, then the loaded job's env (`loaded_env` parses `launchctl print`); `install(force)` waits `BOOTOUT_WAIT_S`=45 s and raises (bug-013); `reinstall` re-checks; `relaunch-fleet` reinstalls on drift before restarting; `restart --relaunch` bootstraps an installed-but-unloaded plist. Tests are fakes for the launchd half (registered), real for the gate.
- **#b-2 (heartbeat) — closed, live.** `pool.submit(no-op).add_done_callback(_touch)`: a late completion ticks. `_SlowPool` (3× interval) advances the file, `_DeadPool` does not. Live: heartbeat ages 0.0–5.0 s on all 8 daemons while serving. In the bug-015 wedge (01:46) the beat went stale because the no-op genuinely never completed (all four cli workers behind a 300 s worker socket), ping failed for the same reason (ping is a `CLI_OPS` op on the same pool, `_handle` daemon.py:2633), the watchdog counted three misses and restarted signal-first — the designed wedge path, not a false positive.
- **#b-3 (stop order) — closed, live.** `daemon.graceful_stop` is the one implementation: `stop` op when ping answers, else SIGTERM at t=0, then the grace, never SIGKILL. `stop_daemon` = graceful_stop → SIGTERM if the op was ignored → heartbeat-gated SIGKILL; `hub.graceful_stop` delegates and logs the report. Real-daemon test (`_SilentDaemon`, SIGTERM lands < 1.5 s). Live hub.log 01:47:28 / 01:53:33 / 02:26:33: `{'stop_op': 'skipped: not answering ping (SIGTERM sent now)', 'signal': 'SIGTERM'}`; adoption on this root at 01:33:39 asked the standalone daemon to stop and it was gone in 2 s.
- **#b-4 (typed foreground gate) — closed.** `refuse_unsupervised_start` → `discovery.daemon_status(retries=0)`: up refused, busy refused with the pid and "not reaping it", absent serves; real busy daemon survives with its socket; source asserted free of `elif ping(root)`.
- **#s-5 (numbers) — closed on paper only; see [[#b-2]] below.** `DEFAULT_KILL_GRACE_S` 45 ≥ 3 × 10 + 10.
- **#m-6 — closed.** socketpair through the real `Daemon._handle` → `ok:false "repair aborted…"`, no `os._exit`, ping answers.
- **#m-7 / #m-8 — closed.** Registry rows for `_SlowPool`, the socketpair dispatcher, the r2 fakes; task-4.1 spec title + requirement amended to Q7.
- **bug-012** (`is_alive` reaps a zombie child via `waitpid(WNOHANG)`, foreign pids fall to `kill(0)`) — correct for every caller I traced (hub, CLI, adoption: none of them is the daemon's parent except tests and `spawn_daemon_subprocess`).
- Gates: `install-hooks --check` in sync; plan status `in-progress` in both files (honest); deferral sweep of every added line in the five commits: no hard or soft deferral (the two "plan 4" hits are docstring citations of this plan).
- **thiquet 03:04:29 is NOT a new wedge.** launchd: `service inactive` 03:04:18–19 (relaunch-fleet's kick had already stopped pid 51370), then `Successfully spawned rmx[55229] because semaphore` at 03:04:29.138 — the hub's kick, landing inside launchd's 10 s ThrottleInterval gap. `restarts=1` is that. See [[#s-3]].

## Findings {#findings}

### BULLSHIT: the plan's own deploy step is a bare `launchctl kickstart -k` under launchd's `exit timeout = 5` — every daemon that needs more than 5 s to drain is SIGKILLed mid-drain, holding the DuckDB writer; launchd did it five times tonight {#b-1}

**File:** `src/refmatrix/cli.py:3030-3046` (`daemon restart`, loaded branch: `lc.kickstart(root, restart=True)` with no `graceful_stop`), `src/refmatrix/cli.py:2575-2577` (`relaunch-fleet` → `daemon restart --relaunch` per root), `src/refmatrix/launchctl.py` `render_plist` (no `ExitTimeOut` key), `src/refmatrix/daemon.py:1530-1600` (shutdown: 3 pool drains × `RMX_DAEMON_SHUTDOWN_TIMEOUT_S`=10 s, flush lock 5 s, store close 5 s — up to 40 s), `src/refmatrix/cli.py` `_verify_relaunch` (`os.kill(_old_pid, 9)` on a pid that still answers ping — a working daemon — with no heartbeat gate)
**What:** Q11 says "one stop order for every supervisor" and the remedy gave the hub a 45 s grace. The deploy path (Q8: `relaunch-fleet`, run twice tonight for bug-015 and bug-014) never calls `graceful_stop`; it hands the kill to launchd, whose budget on every label is
```
launchctl print gui/501/com.refmatrix.daemon.<label>   →   exit timeout = 5      (all 8 labels; the plist sets none)
```
launchd's log for the two relaunch-fleet runs (`log show --predicate 'process == "launchd"'`, 01:00–03:30):
```
02:18:57 refmatrix-fb619 [26176] service state: SIGTERMed
02:19:02 refmatrix-fb619 [26176] Service did not exit 5 seconds after SIGTERM. Sending SIGKILL.
02:19:02 refmatrix-fb619 [26176] exited due to SIGKILL | sent by launchd[1], ran for 1528613ms
02:35    refmatrix-fb619 [46871] Service did not exit 5 seconds after SIGTERM. Sending SIGKILL.
03:04    cliquet  [51434] … Sending SIGKILL.      03:04 thiquet [51370] … Sending SIGKILL.      03:04 viascope [51628] … Sending SIGKILL.
```
Five SIGKILLs by launchd at the 5 s mark, two of them on the project store (26176, 46871) and the two largest stores (viascope 713k-row index, cliquet). Each daemon's rmxd.log has no `daemon stopped` line for those pids (the clean global-store restarts at 02:34:53 and 03:04:03 do). The same runs also show five freshly spawned instances SIGTERMed by launchd at 686 ms, 857 ms, 941 ms, 2.2 s and 9.5 s of age (refmatrix 42834/51219, thiquet 55209, viascope 51609, orderly 51556) — a booting daemon (store open, then the unconditional `repair_entity_links_index` at daemon.py:1263) killed by the second half of `-k`.
**Why it's bullshit:** The plan's charter (constitution XII, Q6/Q11: "supervisors never SIGKILL a working daemon"; #s-5 was filed and "closed" because 30 s could not cover a 40 s drain) is contradicted by the plan's own deploy step with a 5 s budget nobody put beside the 10-10-10-5-5 drain, on the night the numbers were reconciled to 45. The boot-time index repair that runs on every start (`repaired idx_entity_links_lk_concept` on all 7 project boots tonight) exists because SIGKILLed daemons leave that index broken; the deploy path is the SIGKILL generator. `_verify_relaunch` adds a raw `kill -9` of a daemon that ANSWERS ping (the one state that proves it is working).
**Fix:** (1) `render_plist`: `"ExitTimeOut": int(DEFAULT_KILL_GRACE_S)` (one number with the hub's grace; `launchctl.check` then flags all 8 live plists and `relaunch-fleet` re-renders them — the delivery path r3 built). (2) `daemon restart` loaded branch: `daemon.graceful_stop(root, grace=DEFAULT_KILL_GRACE_S)` first, then `kickstart` WITHOUT `-k` when it stopped, `-k` only when it did not (and say so). (3) `_verify_relaunch`: gate the `kill -9` on `heartbeat_age > HEARTBEAT_STALE_S`, else raise. Test: a spawned daemon whose drain sleeps 8 s (patch `RMX_DAEMON_SHUTDOWN_TIMEOUT_S`) survives `daemon restart` with `daemon stopped` in its log; a render test for `ExitTimeOut`; and re-read launchd's log after the next relaunch-fleet: zero `Sending SIGKILL` lines is the acceptance.
**Pattern match:** YES — [[bsd-impressions#imp-consolidated-2]] (a bound on one path is not a bound on the command: the grace was raised on the hub and the deploy path has its own), [[impression_bsd_partial_bound_guard]], r2 #s-5 (two numbers never put side by side — now three).
rel: contradicts -> [[plan-4-daemon-resilience#decisions-log]]
rel: contradicts -> [[project-profile#constraints]]

### BULLSHIT: `_await_shutdown` (#s-5's remedy) cannot wait from the only state its caller can hand it — it reads a heartbeat the shutdown stops first; the test patches `heartbeat_age` to 0.0 {#b-2}

**File:** `src/refmatrix/hub.py:300-320` (`_await_shutdown`: `if heartbeat_age(root) >= RMX_HUB_KILL_GRACE_S: return`), caller `hub.py:_check` (reaches `_restart(alive=True)` only when `hb_age > HEARTBEAT_STALE_S` after three misses), `src/refmatrix/daemon.py:1501` (`self._stop_heartbeat()` is the first act of shutdown, before the drains), `tests/test_plan4_remedy_r2.py:284-300` (`read_pid`→4242, `is_alive`→True, `heartbeat_age`→`iter([0.0]*1000)`)
**What:** Arithmetic: the watchdog restarts an alive daemon only with a heartbeat older than 60 s; `_await_shutdown` waits only with one younger than 45 s; the daemon stops its own beat at the first line of shutdown, so across the 45 s grace the age only grows. Probe P1 (`bsd-plan4-r3-probe.log`): a real heartbeat file aged to 61 s (the youngest `_check` restarts on), a live pid, nothing else patched → `_await_shutdown` returned in **0.0 ms**. Live, all three watchdog restarts tonight: `01:47:28 watchdog graceful stop …: still alive after 45s grace` and `01:47:28 watchdog kickstarted` in the same second — no "waiting one more" line exists in hub.log. The only way in is a queued no-op completing AFTER the SIGTERM (the wedge clearing mid-drain), which is the case that needs no extra wait.
**Why it's bullshit:** The r2 fix text said "skip `-k` while the pid is alive with a heartbeat younger than the grace start"; the remedy implemented the sentence and the test manufactured the state. Second sighting in this plan of a guard that measures a value its caller has already ruled out (r1 #s-7: heartbeat = interpreter liveness; r2 #b-2: heartbeat = cli latency; now: heartbeat = "shutting down"), fourth across plans → PATTERN filed ([[bsd-pattern-guard-cannot-fire]]). Also the 01:47 case shows what #s-5 actually needs: the daemon finished its own shutdown (`daemon stopped`) in the same second the kick landed; with [[#b-1]]'s `ExitTimeOut` the post-grace `-k` becomes SIGTERM + 45 s, which is the wait this code was meant to be.
**Fix:** The "is it shutting down?" signal has to be produced BY the shutdown: write `shutdown.started` (mtime) at daemon.py:1501 and have `_await_shutdown` wait while that file is younger than the grace and the pid is alive; delete the heartbeat read. Test: run `Watchdog._check` (not `_restart`) on a real daemon whose `_shutdown_event` handler sleeps — the state the caller produces — and assert the extra wait. Write the caller's precondition (`hb_age > 60`) as a comment beside the callee's branch.
**Pattern match:** YES — [[impression_bsd_same_input_guard]], [[bsd-impressions#imp-grace-before-signal]] ("write the caller's precondition beside the callee's branch conditions"), [[impression_bsd_tests_bypass_wiring]].
rel: contradicts -> [[plan-4-daemon-resilience#decisions-log]]

### SKETCHY: the watchdog's no-process branch has no grace and `relaunch-fleet` never pauses it — five hub kicks tonight, all inside a relaunch's throttle gap {#s-3}

**File:** `src/refmatrix/hub.py:_check` (`if not proc_alive: restarted = self._restart(root, alive=False)` — the only branch without a miss window), `src/refmatrix/cli.py:hub_relaunch_fleet` (no `pause`/`resume` around the per-root restart; the `Watchdog.pause` primitive exists for exactly "an operator doing a bootout … must not fight a respawn")
**What:** hub.log `watchdog kickstarted` with no `graceful stop` line = the dead branch: 02:19:12 and 02:35:11 (project), 02:36:17 (orderly), 02:36:43 (viascope), 03:04:29 (thiquet) — each 10–26 s after relaunch-fleet's own kick on that root, each spawning the new instance early (`because semaphore`) inside launchd's `ThrottleInterval`=10 s. `read_pid` returns None for a pid file naming a SIGKILLed pid, so a relaunch in progress reads as "genuinely dead". The pid file is written at boot line 1219 before the store opens, so the kick's window onto a BOOTING daemon is sub-second — but the counter (`restarts=1` on thiquet) and the log now say "wedge" for a deploy, which is what prompted this audit's question.
**Fix:** `relaunch-fleet` (and `daemon restart --relaunch`) pause the watchdog for the root for the grace and resume after `_verify_relaunch`; and/or the dead branch requires two consecutive no-process ticks (one interval) before kicking. Test: `_check` twice with `read_pid`→None: one restart, at the second tick.
**Pattern match:** YES — r1 #b-2 (two supervisors competing for one root), [[bsd-pattern-busy-is-not-absent]] (a dead-pid pid file during a respawn is "restarting", not "absent").

### SKETCHY: `launchctl.check` / `reinstall` render against `which rmx`, not the `--rmx` that `relaunch-fleet` was given, and nothing refuses a dev-tree binary — an automated path to point all eight plists at a dev venv {#s-4}

**File:** `src/refmatrix/cli.py:hub_relaunch_fleet` (`rmx = rmx_bin or sys.argv[0]` for the restart; `lc.check(root)` / `lc.reinstall(root)` take no binary), `src/refmatrix/launchctl.py:_rmx_path` (`$RMX_BIN` else `shutil.which("rmx")`), `launchctl.py:check` docstring ("Run it with the DEPLOYED rmx" — a comment where a check belongs), no `dev_tree` / `runtime_identity` reference anywhere in launchctl.py
**What:** From a shell where `rmx` resolves to `.venv-eval/bin/rmx` (or any dev checkout), `check` reports `ProgramArguments` drift on every plist and `reinstall` rewrites all 8 to the dev binary before restarting; `_verify_relaunch` then fails "[DEV TREE]" per store, after the plist is already rewritten. Plan 1's incident (the deploy venv executing the dev tree) gets a one-command reproduction from the drift fixer plan 4 added to close r2 #b-1.
**Fix:** `check(root, *, rmx=...)` / `reinstall(root, *, rmx=...)` take the binary `relaunch-fleet` resolved; `install` refuses a binary whose `runtime_identity()` is `dev_tree` unless `--allow-dev`. Test: `check` with `RMX_BIN` pointing at a dev tree → `(False, "... dev tree ...")`, no write.
**Pattern match:** YES — [[feedback_deploy_tree_is_the_runtime]], [[impression_bsd_gate_in_an_artifact_no_deploy_step_rerenders]] (the fix for "no deploy step re-renders the artifact" is a step that re-renders it with whatever ran it).

### MEH: `stop_daemon` drops the ping-discovered pid after a failed grace — a stale pid file now returns "stopped" on a running daemon {#m-5}

**File:** `src/refmatrix/daemon.py:5321-5326` (`stop_daemon`: after `graceful_stop` returns False, `pid = read_pid(root)`; `if pid is None: return True`)
**What:** `graceful_stop` recovers the real pid from the ping result when the pid file is stale or absent (the case the old docstring named: "orphaned daemon survived a losing concurrent spawn that overwrote it") and then throws it away; `read_pid` returns None for a stale file, so the SIGTERM-after-ignored-stop and the SIGKILL gate are skipped and the caller is told True. The r2 code kept the discovered pid.
**Fix:** `graceful_stop` records `rep["pid"]`; `stop_daemon` uses `rep.get("pid") or read_pid(root)`. Test: `_SilentDaemon` with its pid file pointing at a dead pid → `stop_daemon` returns False with `kill` in the report.

### MEH: the heartbeat's `_touch` swallows `OSError` — a beat that cannot write is a silent "wedge" to every supervisor {#m-6}

**File:** `src/refmatrix/daemon.py:989-993` (`def _touch: try hb.touch() except OSError: pass`)
**What:** A full disk, a removed `.refmatrix/`, or a permission change stops the beat with no log line; the hub then reads "wedged" after 60 s and restarts a healthy daemon, and nothing on either side says why. (Carried from r1; the callback rewrite kept it.)
**Fix:** log once per distinct `errno` (`self._log(f"heartbeat touch failed: {exc!r}")`), keep serving.

### MEH: bug-014's fakes (`_Fine` worker, client socket raising on send, stale-reference drop) are not in the mock registry {#m-7}

**File:** `workflow/test_mock_registry.md:46` (row names `_BrokenWorker` + two spies for `tests/test_bug015_wedge.py`), `git show 72f61e0 --stat` / `f733f6c --stat` (no registry change; 39 + 4 test lines added)
**What:** Three new fakes in the same file, one registry row unchanged. Registry-untouched-plus-tests-added is the shape the plan-1 three-strike rule was armed for; the row's "permanent for the drop/bound assertions" does not name the keep-the-worker path.
**Fix:** extend row 46 (or add a bug-014 row) naming `_Fine`, the send-raising client socket, and the two-worker stale-reference case.

## Verdict {#verdict}

**DIRTY — 7 findings (2 BULLSHIT, 2 SKETCHY, 3 MEH).** Plan-4 may NOT flip to `completed`.

All eight r2 findings closed at their quoted lines and held up live: the gate rides launchd's own variable and 8/8 labels carry it, the beat ticks on completion on every daemon, the stop order is one function and the hub's three restarts tonight signalled at t=0, the foreground gate is typed, the dispatcher path is tested for real, and bug-013's forced reinstall now waits and verifies. What this round found is the supervisor the plan never listed: launchd itself, with a 5 s ExitTimeOut, behind the plan's own deploy step — five daemons SIGKILLed mid-drain tonight in launchd's own words ([[#b-1]]) — and a remedy for #s-5 that is unreachable from its caller by arithmetic and by shutdown order ([[#b-2]]). thiquet's 03:04:29 restart is a deploy race, not a wedge ([[#s-3]]). bug-015's remedy (bounded shared-worker client, SIGUSR1 dump, rerank budget) is real and wired; its root cause stays a hypothesis until a wedge is caught with `kill -USR1`, as the summary says.

Gates this round: 96 passed at HEAD (`pytest-bsd-plan4-r3-head.log`); `install-hooks --check` in sync; `launchctl install --check` in sync on both r2 drifters; live fleet 8/8 supervised with 0–5 s heartbeats; probe P1 (`bsd-plan4-r3-probe.log`); launchd unified log 01:00–03:30 (five `Sending SIGKILL` lines on `com.refmatrix.daemon.*`, all during relaunch-fleet).

rel: contradicts -> [[project-profile#constraints]]
rel: contradicts -> [[claude#no-silent-failures]]
