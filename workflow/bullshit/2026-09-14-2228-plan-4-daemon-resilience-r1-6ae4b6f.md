---
gmd: "0.1"
id: bsd-plan4-daemon-resilience-r1-6ae4b6f
title: "ch-bsd — plan-4 daemon resilience, round 1: gates work where they run, but the abort is green on the wire, adoption SIGKILLs a busy predecessor, the kill grace is spent before the signal, the sqlite branch wipes the graph, and 5 of 8 daemons never got the code"
severity: BULLSHIT
plan: plan-4-daemon-resilience
task: task-4.1..4.4
tags: [bsd, plan-4, daemon, hub, watchdog, repair]
---

# ch-bsd findings — plan-4 daemon resilience, round 1 (tasks 4.1–4.4) {#root}

**Commit range:** d68856d..6ae4b6f (task branches 4385835 / 06d3654 / 9904caa / d0610ab, each merged `--no-ff`: 1640ba4, 74eba3b, 0785ef6, 6ae4b6f245de6242cec613b2dca3a929b4a603e0) plus 190a9d1 (docs) and 23549ae (test hygiene). Judged against production at HEAD 191e510 / deploy 0.69.1.
**Date:** 2026-09-14 22:28
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 20 (4 src, 6 tests, 4 task specs, 4 summaries, plan, mock registry)

rel: evidence-for -> [[plan-4-daemon-resilience]]
rel: derives-from -> [[bsd-plan3-verbs-parity-r2-209270d]]
rel: derives-from -> [[bsd-plan1-deploy-runtime-r5-7b35e80]]

## What is real (verified, not read) {#verified}

- **4.1 degrade** — `_op_learn_from_grep` catches an invalidation-classified exception, logs, writes `repair.needed`, answers `{added:0, skipped:'store-invalid'}`; `os._exit` never called (`test_daemon_learn_guard`, 2 passed at HEAD).
- **4.2 boot repair, through the REAL boot** (probe `bsd-plan4-r1-probe-p5.log`): a spawned daemon with a marker on disk logged `repaired entities rows=3 indexes=6 (queued by learn_from_grep)`, cleared the marker, wrote a heartbeat, and served `memory_get`. Wiring at `serve_forever` (daemon.py:1184-1188) is real. `rmx daemon status` prints `repair pending: entities`.
- **4.3 gate, live**: the hub (pid 38024, 0.69.1, restarted 22:15:55) has classified `/Users/tholley/claude_tools/refmatrix/.refmatrix` as `busy-heartbeat-{0..5}s` on eight consecutive failed pings 22:25:25–22:27:58 with `restart_count=0`, while cli.log shows 19 s `memory recall` latencies and three `sync --since` runs on that store. This is the incident state (ping stalled, process alive) and it was NOT restarted. `heartbeat` files tick at 1–5 s on the three 0.69 daemons.
- **4.4 adoption, live**: orderly rmxd.log `2026-09-14T21:54:28 adopted unsupervised daemon pid=39128 … asking it to stop`; `launchctl print` at 22:24 `state = running, pid = 27922, runs = 12296` (static since 21:54, 30 min); ping `version=0.69.0` from `~/refmatrix/src`; `rmx hub status` has no `[UNVERIFIED]` row. Q4 ("no operator step") holds.
- **Q3 (ping responder)** accepted: `_op_ping` (daemon.py:2568-2595) touches no worker; the reconnect probe is `client.info(timeout=modelsrv.PROBE_TIMEOUT_S)` = 5 s (daemon.py:742, modelsrv.py:64). Decision recorded in the summary and the plan's log — not silent.
- TDD record: RED/GREEN/mutation logs exist for all four tasks with the stated counts; the six plan-4 test files pass at HEAD (30 passed, `pytest-bsd-plan4-r1-head.log`); `test_verb_parity.py` 38 passed; `~/bin/rmx install-hooks --check` → `hooks in sync`. Plan status honest (`in-progress` in the plan and plan-of-plans). Deferral sweep of the diff: no new hard or soft deferral.

## Findings {#findings}

### BULLSHIT: `rmx repair-index --entities` reports SUCCESS when the daemon aborts the repair {#b-1}

**File:** `src/refmatrix/daemon.py:4139-4152` (`_op_repair_entities`), `src/refmatrix/daemon.py:2551` (`_handle`), `src/refmatrix/cli.py:7738-7754`
**What:** On `RepairAbort` the op RETURNS `{"ok": False, "error": "repair aborted: …"}` as its result. `_handle` wraps every returned value unconditionally: `resp = {"ok": True, "result": result}`. The CLI checks `resp.get("ok")` (True), takes `resp["result"]`, and prints the success line.
**Why it's bullshit:** The abort — the one branch that exists to say "this is data, not an index; do not touch it" — is dead on the wire. An operator with real duplicate rows sees green.
**Evidence:** probe `workflow/review-output/bsd-plan4-r1-probe-p1-p3.log`, replaying `_handle`'s wrap and the CLI branch byte-for-byte:
```
P1 wire resp: {"ok": true, "result": {"ok": false, "error": "repair aborted: 2 real duplicate group(s) on (partition_id, kind, name)"}}
P1 CLI prints: [green]rebuilt entities[/] rows=None indexes=None constraints=
```
No test drives `repair_entities` through a daemon; `test_rebuild_aborts_on_real_duplicate_groups` calls the store method directly.
**Fix:** `raise` the `RepairAbort` inside the op (`_handle` then answers `ok:false, error:"repair aborted: …"`; the message matches no fast-exit needle, so the daemon stays up), and add a test that calls the op through a spawned daemon with a store patched to abort. One line.
**Pattern match:** YES — [[bsd-impressions#imp-quoted-line-sibling]] / [[bsd-impressions#imp-unread-diagnostic-field]] (an `ok:false` shape swallowed inside an `ok:true` envelope; 3rd plan in a row with an error field that a consumer never reads).
rel: contradicts -> [[claude#no-silent-failures]]

### BULLSHIT: the adoption path SIGKILLs a BUSY unsupervised daemon — busy ≠ absent, 4th sighting, in the plan titled "never SIGKILL a working daemon" {#b-2}

**File:** `src/refmatrix/daemon.py:936` (`_adopt_unsupervised`: `ping(self.root, timeout=0.5, retries=0)`), `src/refmatrix/daemon.py:1090-1110` (`_reap_predecessor`), sibling `src/refmatrix/cli.py:7738` (`repair-index --entities`: `if daemon_mod.ping(root)` else `_store()`)
**What:** Adoption is gated on a bare 0.5 s ping with no retry. A predecessor that is alive but not answering (mid-ingest, saturated cli_pool — the exact state the watchdog now calls `busy-heartbeat`) is "not adopted"; `serve_forever` then runs `_reap_predecessor`: SIGTERM, 3 s, SIGKILL. The sibling in the CLI: when the daemon is busy, `repair-index --entities` takes the OFFLINE branch and opens the writer slot directly (`_store()` → `_store_rw()`) under a daemon that holds it.
**Why it's bullshit:** The plan's own new signal (the heartbeat file, 4.3) is on disk and says "alive"; 4.4 ignores it and uses the ping shape that plan-3 r2 escalated to BULLSHIT-on-sight (`verbs._call`, `federated_locate`). The result is the corruption trigger the plan exists to remove, issued by the plan's own code path.
**Evidence:** probe `workflow/review-output/bsd-plan4-r1-probe-p2.log` — real spawned daemon, SIGSTOPped (alive, socket + pid file held, cannot answer):
```
predecessor pid 48487 answers ping: True
_adopt_unsupervised → False in 0.50s; logs=[]
_reap_predecessor → True in 3.54s; predecessor alive=False
```
A stopped process cannot take SIGTERM; it died at 3.5 s, i.e. from the SIGKILL at daemon.py:1103. `test_daemon_adopt` only covers an idle predecessor.
**Fix:** classify with `discovery.daemon_status` / `heartbeat_age` — `heartbeat_age(root) <= HEARTBEAT_STALE_S` ⇒ alive: send the `stop` op (bounded), then WAIT up to `ADOPT_GRACE_S` for the pid to exit before any reap; only a pid with a stale/absent heartbeat goes to `_reap_predecessor`. Same classifier in `repair-index --entities`: busy ⇒ refuse ("daemon busy; retry"), never a direct writer open.
**Pattern match:** YES — [[bsd-impressions#imp-busy-absent-verb-layer]] (4th sighting → PATTERN filed: [[bsd-pattern-busy-is-not-absent]]); [[bsd-impressions#imp-fix-at-quoted-line]] (sibling in the same diff).
rel: contradicts -> [[project-profile#constraints]]

### BULLSHIT: the 30 s "kill grace" is spent BEFORE any signal — the graceful stop is unreachable from the only state that calls it {#b-3}

**File:** `src/refmatrix/hub.py:302-307` (`_restart(alive=True)` → `stop_daemon(root, timeout=RMX_HUB_KILL_GRACE_S)`), `src/refmatrix/daemon.py:5186-5225` (`stop_daemon`)
**What:** `stop_daemon` sends the `stop` op ONLY if `ping(root, timeout=0.5)` answers; otherwise it polls the pid for `timeout` seconds doing nothing, then SIGTERMs, waits 2 s, returns. The watchdog reaches `_restart(alive=True)` only after three consecutive failed pings — so for its only caller the `stop` op branch cannot execute, the daemon receives nothing for 30 s, then SIGTERM, and `kickstart -k` (SIGKILL) follows 2 s later.
**Why it's bullshit:** The plan text: "`_restart` sends graceful `daemon stop` first and only `kickstart -k` after RMX_HUB_KILL_GRACE_S (30)" — the purpose is time to close DuckDB cleanly. The real window between the first signal and SIGKILL is 2 s (hard-coded `deadline2` at daemon.py:5222), on a store whose close was measured in the multi-second range (see `project_daemon_shutdown_lock_leak`). The 30 s env knob guards an idle wait.
**Evidence:** code as cited; the test fakes `stop_daemon` entirely (`test_hub_watchdog._wd`), so the sequence is asserted on a lambda. Live: hub.log `22:02:02 watchdog graceful stop …refmatrix/.refmatrix: stopped` / `22:02:12 kickstarted`, and launchd for that label records `last exit code = -15` — the daemon left by SIGTERM, with no shutdown line in rmxd.log after 21:52:33.
**Fix:** in the alive branch send SIGTERM (or the `stop` op when ping answers) FIRST, then wait `RMX_HUB_KILL_GRACE_S` for the pid to exit, then `kickstart -k`. Test with a spawned daemon whose SIGTERM handler sleeps, asserting the wall-clock between the first signal and the kill.
**Pattern match:** YES — [[bsd-impressions#imp-partial-bound]] (a bound applied to the wrong wait), [[bsd-impressions#imp-tests-bypass-wiring]] (the recorded-lambda test cannot see the order inside `stop_daemon`).
rel: contradicts -> [[plan-4-daemon-resilience#proposed-approach]]

### BULLSHIT: cheap fix — the boot repair is triggered by ONE of eight invalidation detectors; the sync-path order of the same incident still loops {#b-4}

**File:** `src/refmatrix/daemon.py:1019-1044` (`_fast_exit_if_invalidated`), callers at 1580 (periodic flush), 1628 (index repair), 1784 (facts compaction), 2151 (snapshot tick), 2439 (pre-flush repair), 2468 (watch flush), 2555 (op dispatch)
**What:** `_mark_repair_needed` has exactly one caller (`_op_learn_from_grep`, daemon.py:3530). Every other detector of the same DuckDB message fast-exits without a marker. The incident memory records the other order — "Every restart replayed `dirty.queue` and died on the same rows" — i.e. the watcher flush hits the phantom first: fast-exit → launchd respawn → boot repairs only `idx_entity_links_lk_concept` → replay → same fatal → loop, until a `rmx grep` miss happens to land in the up-window and writes the marker.
**Why it's bullshit:** The plan's deliverable is "index corruption is repaired in-band"; the implementation repairs it in-band when the first detector is a grep. Correct fix: `self._mark_repair_needed("entities", op=where)` inside `_fast_exit_if_invalidated` before `os._exit(2)` (the rebuild is 0.3 s and idempotent; a marker on a healthy table costs one rebuild). Effort delta: one line.
**Evidence:** `grep -n "_mark_repair_needed(" src/refmatrix/*.py` → definition + one caller.
**Fix:** as above, plus a test: watch-flush raising the needle message → marker exists before exit.
**Pattern match:** NO (first scope-shrink in plan 4).
rel: contradicts -> [[plan-4-daemon-resilience#context]]

### BULLSHIT: the SQLite branch of `rebuild_entities_indexes` wipes the graph and reports success {#b-5}

**File:** `src/refmatrix/store.py:3087-3096, 3128-3131` (the `not duck` branches)
**What:** The method carries a deliberate SQLite path (`PRAGMA table_info`, `AUTOINCREMENT`, `PRAGMA index_list`). On SQLite the FOREIGN KEYs to `entities(id)` are real and `ON DELETE CASCADE` (store.py:284, 305, 335, 364) and `PRAGMA foreign_keys = 1` is on; `DROP TABLE entities` cascades.
**Why it's bullshit:** A repair routine that deletes every concept, memory body and link, then returns `{rows, indexes, constraints}` as if it worked. Not reachable on the live fleet today (no `catalog.db` under any of the 8 roots; the boot path is `duckdb`-gated), but reachable from `rmx repair-index --entities` and the `repair_entities` op on any legacy store or `RMX_BACKEND=sqlite` (backend.py:41-57 keeps both routes), and the branch was written on purpose.
**Evidence:** probe `workflow/review-output/bsd-plan4-r1-probe-p4.log`:
```
PRAGMA foreign_keys = 1
report: {'rows': 2, 'indexes': 6, 'constraints': ['PRIMARY KEY', 'UNIQUE'], ...}
  ROWS LOST in concepts: 1 -> 0
  ROWS LOST in memory_content: 1 -> 0
  ROWS LOST in entity_links: 1 -> 0
```
**Fix:** refuse on `kind != "duckdb"` with `RepairAbort("entities rebuild is DuckDB-only")` and delete the SQLite branch — or, if SQLite must be supported, `PRAGMA foreign_keys = OFF` inside a transaction and assert child-table counts unchanged before commit. Test on a `backend="sqlite"` store.
**Pattern match:** NO.
rel: contradicts -> [[claude#no-silent-failures]]

### BULLSHIT: plan-4's runtime is live on 3 of 8 supervised stores; the brief's "fleet relaunched 22:20" is false and no surface can show it {#b-6}

**File:** deploy state; `src/refmatrix/cli.py:2497-2520` (`hub status` row rendering)
**What:** At 22:22 and again at 22:26 the daemons for viascope, atldb, cliquet, thiquet and cliquedb are the processes launched at 19:41 (pids 48752/48765/48726/48739/48705), answer ping with `version=0.66.3`, and have no `heartbeat` file (`heartbeat_age = inf`). Only the global store (0.69.1), orderly (0.69.0, adopted 21:54) and refmatrix (0.69.x, kickstarted 22:02) run plan-4 code. `rmx hub status` renders eight green rows with a code path and no version, so a half-deployed fleet is indistinguishable from a deployed one (the bsd-plan1 #s-3 shape, one field over).
**Why it's bullshit:** The heartbeat thread, the learn guard, the boot repair and the adoption are "started in a production path" only in processes that imported the code. Five stores — including cliquedb, whose ART drift is the recurring case — still run the ping-only watchdog contract on the daemon side and the pre-0.69 fast-exit on every grep miss.
**Evidence:** `~/refmatrix/.venv/bin/python` ping of every root (versions/heartbeat ages above); `ps -o lstart` for the five pids = `Sep 14 19:41`; `~/.refmatrix/hub.log` has no relaunch of those labels after 21:54.
**Fix:** relaunch the five with the deploy binary (`rmx daemon restart --relaunch` in each root — the boot path will run `repair_entity_links_index` as always); make `hub status` print each daemon's `version` and flag any that differs from the hub's. Re-check heartbeat ages after.
**Pattern match:** YES — [[bsd-impressions#imp-summary-claims-bookkeeping]] (an operational claim in the brief that the ledger contradicts), [[bsd-impressions#imp-unread-diagnostic-field]] (`version` crosses the ping wire and no status row renders it).
rel: contradicts -> [[claude#before-commit]]

### SKETCHY: the heartbeat proves the interpreter is scheduled, not that anything is served — a deadlocked 0.69 daemon is now never restarted {#s-7}

**File:** `src/refmatrix/daemon.py:956-981` (`_start_heartbeat._runner`: `hb.touch(); stop.wait(interval)`), `src/refmatrix/hub.py:269-273`
**What:** The heartbeat thread depends on nothing the serving path does (no pool, no lock, no accept loop). A `Daemon` that never bound a socket ticks it. The watchdog's `wedged-N-misses-heartbeat-Ns` branch is therefore reachable only for a SIGSTOPped process or a pre-0.69 daemon; a daemon deadlocked in its pools (this repo's history: `project_daemon_signal_hang`, the fork-in-threads hang, the `_store_lock` leak) reads as `busy-heartbeat` indefinitely with `restart_count=0`.
**Evidence:** probe `bsd-plan4-r1-probe-p1-p3.log`: real `ping`/`read_pid`/`heartbeat_age`, heartbeat thread started, pid file = a live pid, NO socket: eight `_check` calls → `['busy-heartbeat-0s' × 8]`, `restarts: 0`, no stop/spawn calls. Live: the refmatrix daemon missed eight consecutive pings over 2.5 min as `busy-heartbeat` — correct today (cli.log shows it working), but the signal could not have told a deadlock apart.
**Fix (or justify in the plan):** derive the tick from progress the serving path makes — e.g. the dispatcher submits a no-op to `cli_pool` every interval and touches the file on completion (a saturated-but-progressing pool still ticks; a deadlocked one stops), or touch from `_handle` on every answered request plus the idle tick. Then the wedged branch means something for a 0.69 daemon. Record the decision under Q2 either way.
**Pattern match:** YES — [[bsd-impressions#imp-guard-vs-incident-state]] (a guard built for the fixed state; the wedge state it replaced is no longer detectable).
rel: contradicts -> [[plan-4-daemon-resilience#q2]]

### SKETCHY: unregistered mocks in tasks 4.1, 4.2, 4.4 {#s-8}

**File:** `tests/test_daemon_learn_guard.py` (patches `dm._learn_grep_hits`, `dm.os._exit`, `_request_snapshot`), `tests/test_repair_entities.py` (patches DuckDB `con.execute` with `fake_execute`, `_log`), `tests/test_daemon_adopt.py` (`_log`), `workflow/test_mock_registry.md`
**What:** The registry gained one row (watchdog fakes, task 4.3 — correctly described). The `os._exit` fake, the collaborator fake and the DuckDB-connection fake are unregistered; the `execute` fake means the duplicate-detection SQL never meets a real duplicate (task spec 4.2 asked for "duplicate ids … through a raw connection").
**Fix:** register the three; replace the `execute` fake with a raw-connection duplicate on a UNIQUE-less copy, which is the spec's own recipe.
**Pattern match:** YES — [[bsd-impressions#imp-registry-2-strikes]] (first strike for plan 4).
rel: contradicts -> [[claude#no-mocks]]

### MEH: adoption is unconditional on `--no-detach`; the spec asked for a supervisor condition {#m-9}

**File:** `src/refmatrix/daemon.py:5281-5289` (`serve_foreground`), `src/refmatrix/launchctl.py:171` (plist `EnvironmentVariables`)
**What:** Task 4.4: "when launched under launchd (env/flag) and `daemon.pid` names a live unsupervised process". Implementation adopts on every foreground start. A manual `rmx daemon start --no-detach` on a launchd-supervised store stops the supervised daemon; KeepAlive respawns it in 10 s and it adopts back — two restarts, self-correcting, but the ownership rule is inverted for those seconds.
**Fix:** set `RMX_SUPERVISED=1` in the generated plist and gate `_adopt_unsupervised` on it (or on a `supervised=` kwarg from the CLI).

### MEH: after the 4.1 degrade the daemon serves an invalidated DuckDB with a healthy ping and heartbeat until an unrelated op trips the fast-exit {#m-10}

**File:** `src/refmatrix/daemon.py:3512-3531`
**What:** The degrade path returns before `_request_snapshot()`, so no tick fires; the periodic flush only touches DuckDB with dirty fragments. The exit that lets boot repair run is whichever store-touching op arrives next (`_handle` fast-exits on any op raising the needle). Documented in the 4.2 summary note, but nothing schedules it.
**Fix:** after answering the grep, arm a deferred exit (e.g. `_request_snapshot()` — the tick raises the invalidation and fast-exits within the debounce), so the repair is seconds away, not "next op".

### MEH: the boot wiring is proven by my probe, not by the suite {#m-11}

**File:** `tests/test_repair_entities.py::test_boot_runs_pending_repair_and_clears_marker`
**What:** Calls `_run_pending_repair()` on a hand-built `Daemon`; the `serve_forever` call site (inside the `duckdb` guard) is exercised by no test. Probe P5 (`bsd-plan4-r1-probe-p5.log`) did it with a spawned daemon. Add that variant to the suite so the guard placement is under test.
**Pattern match:** YES — [[bsd-impressions#imp-tests-bypass-wiring]].

### MEH: `stop_daemon` swallows every failure to send `stop` (`except Exception: pass`, daemon.py:5192-5196) — now on the watchdog's restart path {#m-12}

**What:** Pre-existing, but 4.3 makes it the supervisor's graceful path. A refused/timed-out `stop` op is indistinguishable from a sent one in hub.log (`graceful stop … stopped`). Log the exception in the hub line.

## Verdict {#verdict}

**DIRTY — 12 findings (6 BULLSHIT, 2 SKETCHY, 4 MEH).** Plan-4 may NOT flip to `completed`.

What must close before re-review: #b-1 (abort on the wire), #b-2 (busy predecessor / offline writer open), #b-3 (signal before the grace), #b-4 (marker from every detector), #b-5 (SQLite branch), #b-6 (relaunch the five stores and make the version visible). #s-7 needs a decision recorded under Q2 or a serving-derived tick; #s-8 the registry rows.

Gates run this round: plan-4 test files 30 passed at HEAD; verb parity 38 passed; `install-hooks --check` in sync; probes P1–P5 in `workflow/review-output/bsd-plan4-r1-probe-*.log`.

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[project-profile#constraints]]
