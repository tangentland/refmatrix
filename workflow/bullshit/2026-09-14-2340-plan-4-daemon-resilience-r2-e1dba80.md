---
gmd: "0.1"
id: bsd-plan4-daemon-resilience-r2-e1dba80
title: "ch-bsd — plan-4 daemon resilience, round 2: every r1 fix is real at its quoted line; but the supervisor gate lives in a plist no deploy step re-renders (2 of 8 live labels run without it and loop on exit 1), the serving-derived heartbeat turns a BUSY daemon into a wedge after 60 s, and stop_daemon still spends its grace before the signal"
severity: BULLSHIT
plan: plan-4-daemon-resilience
task: remedy-plan-4-r1
tags: [bsd, plan-4, daemon, hub, watchdog, heartbeat, launchd]
---

# ch-bsd findings — plan-4 daemon resilience, round 2 (remedy e1dba80) {#root}

**Commit range:** 90182c2..e1dba80 (branch `remedy-plan-4-r1`, 87a63d7, merged `--no-ff` as e1dba805e83ee564b454adfdc4b74ac922d16c8f). Judged against production at HEAD e1dba80 / deploy 0.69.1 (`~/bin/rmx version -v`: `/Users/tholley/refmatrix/src`).
**Date:** 2026-09-14 23:40
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 12 (5 src, 3 tests, plan, summary, 2 registries)

rel: evidence-for -> [[plan-4-daemon-resilience]]
rel: derives-from -> [[bsd-plan4-daemon-resilience-r1-6ae4b6f]]
rel: derives-from -> [[bsd-pattern-busy-is-not-absent]]

## What closed (verified by probe or live, not by reading) {#verified}

Probes: `workflow/review-output/bsd-plan4-r2-probe.log` (in-process daemon on a short `/tmp` root, `serve_forever` on the main thread, REAL socket / pid file / heartbeat / `Watchdog._check`), `bsd-plan4-r2-survey.log` (live fleet via the deploy venv), `pytest-bsd-plan4-r2-head.log` (six plan-4 files + verb parity: **67 passed** at HEAD).

- **#b-1 abort on the wire — closed.** `_op_repair_entities` raises; probe P1 through the real `_handle`: `{"ok": false, "error": "repair aborted: 2 real duplicate group(s) …"}` and the daemon answers ping afterwards. `_is_fatal_invalidation` on that message → `False` (no fast-exit). Mutation A recorded.
- **#b-2 (adoption) — closed at the quoted line.** `test_adoption_never_kills_a_busy_predecessor` is a real spawned daemon, SIGSTOPped; adoption returns True, the pid survives, `_reap_predecessor` yields on the fresh heartbeat (mutation D recorded). `repair-index --entities` refuses `_SilentDaemon` (real stalled socket) and opens no `catalog*.duckdb`.
- **#b-3 (watchdog) — closed for the hub path.** `hub.graceful_stop` signals first (`stop` op when ping answers, else SIGTERM) and then waits; `_restart(alive=True)` → `graceful_stop` → `kickstart -k` (order test + live-daemon test + mutation C on the live-daemon test).
- **#b-4 — closed.** `_fast_exit_if_invalidated` writes `repair.needed` from every detector (`test_fast_exit_queues_the_boot_repair`, mutation B).
- **#b-5 — closed.** `rebuild_entities_indexes` raises `RepairAbort` on `kind != "duckdb"`; the SQLite test proves the memory row survives.
- **#b-6 — closed live.** Survey 23:31: all 8 daemons answer `version=0.69.1`, heartbeat ages 1.1–4.5 s, pid files match. rmxd.log shows `relaunch-fleet`'s sequence (tholley 23:18:25 → refmatrix 23:18:45 → atldb :51 → cliquedb :54 → cliquet :58 → orderly 23:19:01 → viascope :04; thiquet was unloaded by `--force` and got its start at 23:20:49). `rmx hub status` prints `v0.69.1` per row; the STALE branch is under test. thiquet's log carries a REAL adoption: `23:20:49 adopted unsupervised daemon pid=75200 … (answers ping)`. Hub health ring since 23:20: 26/26 `up` on all 8, `restarts=0`.
- **#m-10 / #m-11 / #m-12 / #s-8 — closed.** Deferred exit asserted inside the patched `os._exit`; boot repair proven on a spawned daemon; `report=` dict filled (`test_stop_daemon_reports_why_it_could_not_ask`); four registry rows.
- Gates: `~/bin/rmx install-hooks --check` → in sync; plan status `in-progress` in both files (honest); deferral sweep of the diff: no hard or soft deferral ("deferred exit" is a thread name, not a deferral).

## Findings {#findings}

### BULLSHIT: the adoption gate (#m-9) is delivered by a plist field that no deploy step re-renders — the project store and the global store run WITHOUT it, and a supervised start on them now exits 1 into the KeepAlive loop the plan exists to end {#b-1}

**File:** `src/refmatrix/daemon.py:5376-5385` (`serve_foreground`: `supervised = os.environ.get("RMX_SUPERVISED") == "1"` else `raise RuntimeError("daemon already running…")`), `src/refmatrix/launchctl.py:154-156` (`RMX_SUPERVISED` in `render_plist`), `src/refmatrix/launchctl.py:358-359` (`install`: `if p.exists() and is_loaded(root) and not force: return p`), `src/refmatrix/cli.py:2544-2574` (`relaunch-fleet` restarts processes, never touches a plist)
**What:** Adoption now runs only when the environment carries `RMX_SUPERVISED=1`, which only a freshly rendered plist sets. Live at 23:2x:
```
com.refmatrix.daemon.refmatrix-fb619c669f75.plist   supervised=0 mtime=15:26:24
com.refmatrix.daemon.tholley-506f24b692ed.plist     supervised=0 mtime=16:05:46
(the other six: supervised=1, mtime 23:18–23:20)
launchctl print …refmatrix-fb619c669f75: REFMATRIX_ROOT => …/claude_tools/refmatrix/.refmatrix   (no RMX_SUPERVISED)
launchctl print …tholley-506f24b692ed:   REFMATRIX_ROOT => /Users/tholley/.refmatrix              (no RMX_SUPERVISED)
```
`relaunch-fleet` (the plan's own deploy step, Q8) relaunched both at 23:18:25 / 23:18:45 with the old plists; `launchctl.install` returns early on an installed+loaded label unless `--force`, and `--force` is the known "leaves it unloaded" bug (thiquet needed a second install tonight). There is no plist drift check anywhere (`grep render_plist(.*) ==` → nothing), unlike hooks (`install-hooks --check`).
**Why it's bullshit:** On those two stores the r1 code (unconditional adoption) has been replaced by the pre-plan behaviour. Reproduced on a tmp store (`RMX_HOME` tmp, unsupervised daemon up, launchd-style start with the dev binary):
```
without RMX_SUPERVISED: Error: daemon already running for …; stop it before launching in the foreground … exit=1 after 0s
with RMX_SUPERVISED=1:  … adopted unsupervised daemon pid=92739 … (answers ping) … daemon starting pid=92747
```
exit 1 in 0 s under `KeepAlive` = one spawn per ThrottleInterval — the orderly incident (11,251 runs), now armed on the project store this audit runs against and on the global memory store, the moment anyone runs `rmx daemon start --standalone` or a test leaves a daemon behind on either root. The summary says "gated on `RMX_SUPERVISED=1` (set by the daemon plist)"; the test asserts `b"RMX_SUPERVISED" in launchctl.render_plist(root)` — an existence check on the RENDER, not on what launchd runs.
**Fix:** (1) re-install the two plists now (and verify `launchctl print` shows the variable). (2) Make the gate independent of a plist rewrite: launchd exports `XPC_SERVICE_NAME=<label>` to every job it spawns — `supervised = env.get("XPC_SERVICE_NAME", "").startswith("com.refmatrix.daemon.")` needs no re-render and cannot be forgotten; keep `RMX_SUPERVISED` as the explicit override. (3) Add `rmx daemon install --check` (installed plist == rendered plist, the hooks shape) and have `relaunch-fleet` refuse or re-install on drift, so the next plist-borne setting has a delivery path.
**Pattern match:** YES — [[impression_bsd_existence_check_tests]] (render asserted, installed file not), [[bsd-impressions#imp-consolidated-1]] (summaries claiming bookkeeping that did not happen) ("set by the daemon plist" — for 6 of 8), and the plan-2 shape (installed artifact ≠ generated artifact) one artifact over.
rel: contradicts -> [[plan-4-daemon-resilience#q4]]
rel: contradicts -> [[project-profile#constraints]]

### BULLSHIT: cheap fix — the serving-derived heartbeat (#s-7 / Q5) measures cli-pool queue latency, so a BUSY daemon reads as a WEDGE after 60 s; the state task 4.3 was built to protect is now the state it restarts {#b-2}

**File:** `src/refmatrix/daemon.py:984-995` (`_start_heartbeat._runner`: `fut = pool.submit(lambda: True); fut.result(timeout=interval)` → touch only if it returned in time), consumers `src/refmatrix/hub.py:262-285` (`_check`), `src/refmatrix/daemon.py:1134-1141` (`_reap_predecessor` yield), `src/refmatrix/daemon.py:5300-5306` (`stop_daemon` kill withhold), `src/refmatrix/daemon.py:940-945` (`_adopt_unsupervised` `fresh`)
**What:** The tick is a no-op submitted to the same 4-worker `cli_pool` that serves `ping`, `memory_recall`, `partition_list` (takes `_store_lock`), `context`. A late completion is discarded (`fut.result(timeout=interval)` raises, the future keeps running, its completion touches nothing). So the file advances only while the cli queue delay is under 5 s — the same condition under which ping answers. Probe P2, a real serving daemon with 4 in-flight cli ops (the shape of four 19 s recalls behind the writer lock, r1's live "busy-heartbeat ×8" window):
```
t+ 0s ping=False hb_age=  0.7s bg checkpoint ok
t+28s ping=False hb_age= 28.3s bg checkpoint ok
t+55s ping=False hb_age= 55.8s bg checkpoint ok
t+61s ping=False hb_age= 61.4s bg checkpoint ok watchdog: busy-grace-1/3
bg ops served during saturation: 12
```
The daemon served 12 background ops over the socket while its heartbeat stood still; the REAL `Watchdog._check` (real ping / pid / heartbeat, only `_restart` recorded) left the busy branch at 61 s and entered the miss-grace path: with `WATCHDOG_INTERVAL_S=15` the third miss lands at ≈105 s of cli saturation → `_restart(alive=True)` → SIGTERM → `kickstart -k` 30 s later if the drain (3 pools × `RMX_DAEMON_SHUTDOWN_TIMEOUT_S`=10 s, then the store close) overruns the grace.
**Why it's bullshit:** Task 4.3's acceptance ("alive pid + fresh heartbeat + failing ping → no restart") and Q2's rationale ("a ping that must go through the accept loop is exactly what blocks when the daemon is busy") are undone by routing the liveness tick through that queue. Every other r1 remedy leans on `heartbeat_age`: a saturated 0.69 daemon now also (a) fails `_adopt_unsupervised`'s `fresh` test → `_reap_predecessor` sees a stale heartbeat → SIGTERM, 3 s, **SIGKILL by the supervised start** (the r1 #b-2 outcome, one signal later); (b) loses `stop_daemon`'s kill withhold. The r1 fix text said "a saturated-but-progressing pool still ticks; a deadlocked one stops" — the implementation ticks only when the pool is nearly idle. The `_DeadPool` test proves the never-completes case; no test submits a pool that completes late. Correct fix, two lines: `fut.add_done_callback(lambda f: hb.touch())` (a progressing pool ticks at its own pace; only a no-op that NEVER completes stops the beat), and keep the unconditional touch before the pools exist. Test: a pool whose no-op completes after 3× the interval must still advance the file.
**Evidence:** probe P2 above; `WATCHDOG_INTERVAL_S` hub.py:39; `HEARTBEAT_STALE_S` 60 s; drain budget daemon.py:1497-1502.
**Pattern match:** YES — [[bsd-impressions#imp-consolidated-2]] (the verbatim-fix note) (my own suggestion implemented in a way that fails its own sentence), [[impression_bsd_same_input_guard]] (r1 #s-7 already: a guard that cannot see the incident; now it sees the wrong one), cheap-fix rule 10 (effort delta: two lines).
rel: contradicts -> [[plan-4-daemon-resilience#q2]]
rel: contradicts -> [[plan-4-daemon-resilience#q5]]

### BULLSHIT: `stop_daemon` still spends its grace BEFORE the first signal — #b-3 was fixed in the hub and not in the sibling the adoption path and `rmx daemon stop` call (escalated: 4th fix-at-the-quoted-line) {#b-3}

**File:** `src/refmatrix/daemon.py:5248-5290` (`stop_daemon`: ping fails → `report["stop_op"]="skipped: not answering ping (SIGTERM after the wait)"` → poll `timeout` seconds → SIGTERM → 2 s), callers `daemon.py:958` (`_adopt_unsupervised`, `timeout=ADOPT_GRACE_S`=20), `cli.py` `daemon stop` (5 s)
**What:** The comment now documents the defect ("SIGTERM after the wait"). Probe P3 on the busy daemon of P2: `stop_daemon(timeout=3, report=…)` → the daemon's `_shutdown_event` set at **+4.99 s** (0.5 s ping + 3 s idle poll + per-iteration pings + SIGTERM). Adoption of a busy predecessor therefore logs `adopted … (busy, heartbeat fresh): asking it to stop` and asks nothing for 20 s, then SIGTERMs, then 2 s later yields; launchd respawns in 10 s and the cycle repeats every ~32 s until the predecessor exits — each cycle's only stop request arrives 20 s in. `hub.graceful_stop` (the r1 fix) has the right order and lives in `hub.py`, unreachable from the daemon's own adoption.
**Why it's bullshit:** Same defect, same file, forty lines from the line r1 quoted; the r1 fix text named "signal first, then wait" as the rule. Escalation: SKETCHY → BULLSHIT — fix-at-the-quoted-line is on its 4th sighting ([[bsd-impressions#imp-fix-at-quoted-line]] plan-2 r3, [[bsd-impressions#imp-quoted-line-sibling]] plan-3 r2, [[bsd-impressions#imp-busy-absent-call-tree]] plan-3 r3, r1 #b-2's CLI sibling).
**Fix:** move `graceful_stop` into `daemon.py` and make `stop_daemon` use it when ping fails (SIGTERM at t=0, then the wait, then the heartbeat-gated SIGKILL); `hub.graceful_stop` becomes an alias. Test: on the P2-style busy daemon, `_shutdown_event` set within 1 s of the call.
**Pattern match:** YES — as above; also [[bsd-impressions#imp-grace-before-signal]].
rel: contradicts -> [[plan-4-daemon-resilience#q6]]

### BULLSHIT: a new bare `ping(root)` gate in `serve_foreground` — a busy daemon is not refused, it is reaped {#b-4}

**File:** `src/refmatrix/daemon.py:5381` (`elif ping(root): raise RuntimeError(...)`)
**What:** The unsupervised foreground start refuses only a daemon that ANSWERS. A busy one (alive, socket held, not answering) falls through to `_reap_predecessor`, which yields only while the heartbeat is fresh — and #b-2 shows a working, cli-saturated daemon's heartbeat is stale after 60 s → SIGTERM, 3 s, SIGKILL by an operator's `rmx daemon start --no-detach`. The classifier the same diff uses in `repair-index --entities` (`verbs.require_daemon`, typed busy) was not used here.
**Why it's bullshit:** Standing rule since plan-3 r2 ([[bsd-impressions#imp-busy-absent-verb-layer]]): a diff that ADDS a bare `ping(` gate is BULLSHIT on sight; this is the 5th busy≠absent sighting ([[bsd-pattern-busy-is-not-absent]]).
**Fix:** `require_daemon(root)`: up → refuse as now; busy → refuse with the busy message; absent → serve.
rel: contradicts -> [[project-profile#constraints]]

### SKETCHY: the watchdog's `kickstart -k` after the grace cannot be covered by the daemon's own shutdown budget {#s-5}

**File:** `src/refmatrix/hub.py:304-314` (`_restart`), `src/refmatrix/daemon.py:1497-1502`
**What:** A daemon that takes the SIGTERM drains three pools at up to `RMX_DAEMON_SHUTDOWN_TIMEOUT_S`=10 s each and then closes the store; `RMX_HUB_KILL_GRACE_S`=30 s. `_restart` kickstarts `-k` (SIGKILL) at 30 s without re-reading the heartbeat or checking whether the pid is mid-shutdown. "Knowingly" is recorded in Q6 but the two numbers were not reconciled: a daemon doing exactly what it was asked can be SIGKILLed while closing DuckDB — the corruption the plan names.
**Fix:** grace ≥ 3 × drain + close margin (or drain budget shared across pools), and skip `-k` while the pid is alive with a heartbeat younger than the grace start (it is shutting down; wait one more grace). Record in Q6.

### MEH: no test drives `repair_entities` through `_handle`; the CLI test fakes `dm.call` with a canned `ok:false` {#m-6}

**File:** `tests/test_plan4_remedy.py::test_repair_index_entities_cli_reports_the_abort`, `::test_repair_entities_op_raises_so_the_dispatcher_answers_ok_false`
**What:** The op test stops at the raise; the CLI test starts at a hand-written wire result. The wrap (`_handle` → `ok:false`, no fast-exit on the message) was proven by my probe P1, not by the suite. Add the in-process variant (Daemon on a tmp root, store method patched, `dm.call` for real).
**Pattern match:** YES — [[impression_bsd_tests_bypass_wiring]].

### MEH: registry rows name the wrong files {#m-7}

**File:** `workflow/test_mock_registry.md:42,46-49`
**What:** `test_plan4_remedy.py` also fakes `hub.rpc`, `discovery.daemon_status`, `dm.call` (canned), `discovery.discover_roots`, `launchctl.is_loaded/kickstart`, `hub.graceful_stop` — none attributed to it; the task-4.3 row still says `daemon.stop_daemon` for `test_hub_watchdog.py`, which now records `hub.graceful_stop`.

### MEH: task 4.1's spec and title are now false by Q7 {#m-8}

**File:** `workflow/plans/plan-4-daemon-resilience-tasks/task-4.1-plan-4-daemon-resilience.md:4,12,16`, `tests/test_daemon_learn_guard.py:47-51`
**What:** "learn_from_grep never fast-exits … the daemon keeps serving" — the daemon now exits 2 s after a degraded read (Q7, my #m-10). The decision is recorded in the plan; the task spec was not amended and the test's assertion text was rewritten instead ("the READ itself must never…"). Amend the spec (requirement: answers the read, exits within `RMX_DEGRADE_EXIT_S`, marker present) so the spec and the test say the same thing.

## Verdict {#verdict}

**DIRTY — 8 findings (4 BULLSHIT, 1 SKETCHY, 3 MEH).** Plan-4 may NOT flip to `completed`.

Every r1 finding closed at the line it quoted, and the fleet is genuinely on 0.69.1 with heartbeats. What remains is the remedy's own residue: #b-1 (the gate reaches 6 of 8 stores and the two it misses are this project's and the global store — re-install now, then a plist-independent gate + a drift check), #b-2 (the heartbeat must tick on completion, not on completion-within-interval), #b-3 (`stop_daemon` signals first), #b-4 (typed classifier in the foreground gate). #s-5 needs the two numbers reconciled in Q6.

Gates this round: 67 passed at HEAD (`pytest-bsd-plan4-r2-head.log`: plan4_remedy, learn_guard, hub_watchdog, repair_entities, daemon_adopt, verb_parity); `install-hooks --check` in sync; live survey 8/8 v0.69.1; probes P1–P3 in `bsd-plan4-r2-probe.log`; tmp-store reproduction of the supervised start with/without the flag (in this report, stdout).

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[project-profile#constraints]]
