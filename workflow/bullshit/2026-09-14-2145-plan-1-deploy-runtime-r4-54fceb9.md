---
gmd: "0.1"
id: bsd-plan1-deploy-runtime-r4-54fceb9
title: "plan-1 round 4: identity_error never leaves the daemon — every new consumer reads a wire field the ping drops; hub's own error still unread; plan flipped completed on a remedy that does not run"
tags: [bsd, findings, plan-1, deploy, re-review]
severity: BULLSHIT
plan: plan-1-deploy-runtime
task: task-1.1-plan-1-deploy-runtime, task-1.2-plan-1-deploy-runtime, task-1.3-plan-1-deploy-runtime
metadata:
  node_type: bsd-report
  commit_range: 54fceb9^..54fceb9
  round: 4
---

# ch-bsd findings — plan-1-deploy-runtime round 4 (54fceb9^..54fceb9) {#root}

**Commits:** 851ff17 (fix(identity): identity_error is unknown everywhere; ping-exception guard test; plan-1 closed), 54fceb9 (merge remedy-plan-1-r3)
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 8 (cli.py, hub.py, tests/test_plan1_remedy.py, r3 report, remedy summary, task-1.3 spec, plan-1 status, mock registry)

rel: amends -> [[bsd-plan1-deploy-runtime-r3-e6c4081]]
rel: evidence-for -> [[plan-1-deploy-runtime#q3]]

## Verified (read-only, live 0.69.0 at d68856d) {#verified}

- Deploy: `~/refmatrix` at d68856d; `~/refmatrix/.venv` imports `/Users/tholley/refmatrix/src/refmatrix/__init__.py` 0.69.0; `rmx version -v` shows no `[DEV TREE]`. `rmx daemon status` prints the deploy `code:` line, supervised. `rmx hub status` (hub pid 8370, started 21:35:26) shows 8 stores up, only orderly `[UNVERIFIED v0.65.0]` (plan task 4.4).
- **Live tick pending from r3 (#m-4-r2):** CLOSED. `rmx bus history global:queues` → alert `#797abc926f30` at 21:18:19 (the previous hub's first tick after 20:47:46) carries the orderly row `{'identity': 'unknown', 'version': '0.65.0'}`; the unknown row is hot and published.
- **#s-1-r3 registry rows:** CLOSED. `workflow/test_mock_registry.md` gained `hub.bus` (FakeBus) and `Hub` self with stubbed `_gather_queues` (FakeHub/QuietHub/HotHub/ColdHub) rows; the new `HotHub`/`ColdHub` stubs in `test_queue_alert_once_reports_whether_it_published` are covered by the second row.
- **#m-2-r3 lint scope:** CLOSED. `./scripts/lint-gmd.sh` scans CLAUDE.md, docs/, workflow/, the profile AND the memory dir → 0 errors (`workflow/review-output/lint-gmd-bsd-plan1-r4.log`); task 1.3 now names that scope and why a memory-dir-only lint shows the ADR ids as dangling (it shows 4 today, by design).
- **#m-3-r3 ping-exception branch:** CLOSED. `test_relaunch_fails_when_the_ping_itself_raises` makes `daemon.call` raise `OSError`; the assertion on "cannot be read" fails on the old code because CliRunner would report the bare traceback without that text.
- **`_queue_alert_once` bool:** asserted (True for a hot row, False for a cold one).
- Tests (dev tree, `.venv-eval`): `test_plan1_remedy.py` + `test_runtime_identity_surface.py` + `test_upgrade.py` + `test_subject.py` → 44 passed in 2.09 s (`workflow/review-output/pytest-bsd-plan1-r4-54fceb9.log`). E2E surfaces: `~/bin/rmx install-hooks --check` → hooks in sync; `tests/test_verb_parity.py` → 38 passed (`pytest-bsd-plan1-r4-parity-54fceb9.log`).
- Deferral sweep over the added lines of 851ff17: no hard or soft deferrals ("fallback guess" is descriptive). Hard sweep of `src/refmatrix` for plan-1 references: none; the `Phase 1/2` hits (helix, duckdb_view, store.py:646) predate plan 1 and were filed in the run-1 report.
- Task specs 1.1/1.2/1.3 `status: complete`; plan file `status: completed` (see [[#b-1-r4]] and [[#m-3-r4]]).

### Round-3 findings — status {#status}

| # | Status | Evidence |
|---|--------|----------|
| #s-1-r3 FakeBus/FakeHub unregistered | CLOSED | two registry rows, cover the r3 and r4 stubs |
| #m-2-r3 memory-dir lint | CLOSED | full-scope lint 0 errors; task 1.3 names the scope |
| #m-3-r3 ping-exception untested | CLOSED | OSError test; mutation-strong |
| #m-4-r3 `identity_error` read by nobody | **NOT CLOSED** → [[#b-1-r4]] | consumers added; producer never sends it; hub's own error still unread |
| also-reviewed bool | CLOSED | asserted both ways |
| r3 live tick (orderly unknown on the bus) | CLOSED | alert 21:18:19 carries `identity: unknown` |

## Findings {#findings}

### BULLSHIT: `identity_error` never leaves the daemon — every consumer added for #m-4-r3 reads a wire field `_op_ping` drops; the hub's own error is still read by nobody {#b-1-r4}

**File:** `src/refmatrix/daemon.py:2419-2427` (`_op_ping`, OPS `"ping"` at daemon.py:4709); consumers `src/refmatrix/hub.py:976-982` (`_daemon_identity`), `src/refmatrix/cli.py:2853-2859` (`_verify_relaunch`), `src/refmatrix/cli.py:2986-2990` (`daemon status`); second producer `src/refmatrix/hub.py:1021-1024` (`_hub_identity`) with its consumer `src/refmatrix/cli.py:2477-2478` (`hub status`)
**What:** 851ff17 adds three readers of `result["identity_error"]` on the daemon ping and claims "identity_error is unknown everywhere". `_process_identity()` (daemon.py:2434-2445) does store `identity_error` when `runtime_identity()` raises, but `_op_ping` builds its response by hand — `"code_path": ident["code_path"], "dev_tree": ident["dev_tree"]` — and never copies `identity_error`. The field exists only inside the daemon process.
**Why it's bullshit:** none of the new branches can execute in production. Replayed in the dev venv with `runtime_identity` patched to raise and `_PROCESS_IDENTITY` reset, then calling the real `_op_ping`:
```
PROCESS_IDENTITY: {'code_path': '…/src/refmatrix/__init__.py', 'dev_tree': False, 'identity_error': 'no pth'}
PING RESULT     : {'pid': 12242, 'root': '/tmp/x/.refmatrix', 'backend': None, 'version': '0.69.0', 'code_path': '…/src/refmatrix/__init__.py', 'dev_tree': False}
identity_error on the wire: False
```
So a daemon that could not compute its identity still pings `code_path=<fallback guess>, dev_tree=False` and: `_daemon_identity` returns it as verified-clean, `hub status`/`hub queues` render no flag, the alert loop treats the row as cold, `daemon status` prints a clean `code:` line, and `_verify_relaunch` reaches the path compare — exactly the r3 finding, unchanged in production. All four new tests (`test_relaunch_fails_when_the_daemon_could_not_compute_its_identity`, `test_daemon_identity_with_identity_error_is_unknown`, `test_daemon_status_flags_identity_error_as_unverified`, plus the hub-row assertion) patch `daemon_mod.call` to return a result that already contains `identity_error`; they prove the readers, not the wire. The RED log (`pytest-plan1-r3-red.log`) went red on the readers for the same reason. The mutation the summary cites ("reverting the `identity_error` branch in `_daemon_identity` fails the test") is the wrong mutation: deleting `identity_error` from the PRODUCER leaves every test green — which is the shipped state.
Second half: #m-4-r3 named two producers. `_hub_identity` (the hub's own tree) does reach the CLI — `_op_hub_info` spreads `**_hub_identity()` and `hub.status()` merges it into `st` — but `hub_status` still prints `_print_code_identity(st["code_path"], st.get("dev_tree"))` and never reads `st.get("identity_error")`. Probe (`hub_mod.status` patched to return `identity_error="no pth"`): output is `code: /x/refmatrix/__init__.py` with no `[UNVERIFIED]` and no error text. The commit message's "hub status: [UNVERIFIED] + the error" is true for daemon rows and false for the hub's own line.
**Evidence:** probes `scratchpad/ping_probe.py` and `scratchpad/hub_own_probe.py` (output quoted above); `RMXGREP_MODE=plain grep -rn identity_error src/refmatrix` → producers daemon.py:2444, hub.py:1024; readers hub.py:976/982/1000, cli.py:2853/2857/2986/2990; no line in `_op_ping` or `hub_status` touches it.
**Fix:** (1) `_op_ping`: return `**ident` (or add `"identity_error": ident.get("identity_error")`) so the field crosses the socket — one line; (2) `hub_status`: when `st.get("identity_error")`, print `code: … [UNVERIFIED] — hub could not compute its identity: <err>` instead of `_print_code_identity`; (3) a real-path test: patch `upgrade.runtime_identity` to raise, reset `daemon._PROCESS_IDENTITY`, call `_op_ping` with a stub daemon, and feed THAT dict into `_daemon_identity` / the `daemon status` renderer — the test must go through the producer, not a hand-written ping result; (4) the same for `_hub_identity` → `hub_status`. Effort: ~10 lines.
**Pattern match:** YES — [[bsd-impressions#imp-tests-bypass-wiring]] (surface tested with the wire faked), [[bsd-impressions#imp-unread-diagnostic-field]] (the r3 finding's own shape, moved one hop upstream), [[bsd-impressions#imp-fix-at-quoted-line]] (fix landed at the consumer lines the finding quoted, not at the producer), [[bsd-pattern-tests-prove-existence-not-wiring]]. Third occurrence of tests-bypass-wiring in plan 1 → escalated from the MEH the r3 finding carried to BULLSHIT per the 3-strike rule. Also a cheap fix: the correct fix was one line in the producer; the remedy wrote three readers and four tests around a field that was never sent.

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[bsd-pattern-tests-prove-existence-not-wiring]]

### SKETCHY: `rmx hub queues` dies with a raw `TimeoutError` traceback when one daemon is busy {#s-2-r4}

**File:** `src/refmatrix/cli.py:2505-2515` (`hub_queues` catches only `VerbError`), `src/refmatrix/verbs.py:826-830` (`queues` → `hub_mod.rpc("queues")`, default 30 s), `src/refmatrix/hub.py:511-524` (`_gather_queues`: per-root `daemon.call(... timeout=10.0)` + `_daemon_identity` 2 s, 8 roots)
**What:** live at 21:39:20 (`.refmatrix/cli.log`): `["hub","queues"] exit_code=1 latency_ms=30023 error="TimeoutError: timed out"`, printed as a 40-line Python traceback, while a sibling audit's `rmx grep` held the refmatrix daemon for 30 s. Three re-runs at 21:39:58-21:40:02 succeeded in 1.8 s. The hub's queues op walks 8 daemons with a 10 s call + 2 s identity ping each; a single busy daemon pushes the op past the CLI's 30 s rpc timeout, and the resulting `TimeoutError` is not a `VerbError`, so the twin prints a traceback instead of the "busy ≠ absent" line plan 2 r3 established for the other daemon-state paths.
**Why it's sketchy:** loud, not silent — but it is the identity surface plan 1 built, and its failure mode under a busy daemon is the one this ledger has now seen in every plan ([[bsd-impressions#imp-socket-sim-probe]]). The `--json` twin (`rmx_queues` over MCP) has the same exposure.
**Fix:** `verbs.queues` wraps `TimeoutError`/`OSError` into `VerbError("hub queues timed out after 30 s — a daemon is busy; retry or `rmx daemon status <root>`")`; and/or `_gather_queues` caps per-root work (identity ping only when the 10 s status call returned) so 8 roots cannot exceed the rpc budget.
**Pattern match:** YES — [[bsd-impressions#imp-partial-bound]] (30 s bound on the rpc, 96 s of work behind it).

### MEH: `workflow/plan-of-plans.md` still lists plan 1 as `in-progress` while the plan file says `completed` {#m-3-r4}

**File:** `workflow/plan-of-plans.md:21`, `workflow/plans/plan-1-deploy-runtime.md:8`
**What:** the status flip in 851ff17 touched the plan file only. `plan-of-plans.md` is the first hop of the source-of-truth order in CLAUDE.md and disagrees with the second.
**Fix:** flip both in the same commit — after [[#b-1-r4]] is closed, not before.

### MEH: RED record covers 2 of the 5 new tests; the relaunch `identity_error` test is unaccounted for {#m-4-r4}

**File:** `workflow/review-output/pytest-plan1-r3-red.log`, `workflow/implementation_summaries/remedy-plan-1-deploy-runtime.md#round-3`
**What:** the RED run selected 4 tests (`.FF.`, 15 deselected); the summary says two failed and "the ping-exception and bool tests passed on arrival". `test_relaunch_fails_when_the_daemon_could_not_compute_its_identity` was neither in the run nor mentioned. On paper it would have been red (without the guard the fixture reaches `relaunch verified`), so this is record-keeping, not a false claim — but the record is the thing the summary is for.
**Fix:** re-run RED with all five selected, or state which were regression guards.

## Plan status {#plan-status}

The flip to `completed` in 851ff17 is **not justified**. My r3 verdict allowed the flip once #s-1-r3 was addressed in the same commit — that condition is met — but the same commit claims #m-4-r3 closed with code that cannot run against a real daemon, and the field that "is unknown everywhere" is dropped at the socket. A plan whose last remedy is dead on the wire is not complete. Revert to `in-progress` (both files), land the producer-side fix + real-path test, and flip in that commit.

## Also reviewed {#also}

- `hub status` and `hub queues` correctly render orderly as `UNVERIFIED` from `identity == "unknown"` (the `code_path`-absent path, which the wire does carry); the `--json` row carries `identity_error` when present. Not a finding — that path works because it keys on absence, not on the dropped field.
- `daemon status` new `else` branch (ping without `code_path` → `[UNVERIFIED]`) is reachable (pre-0.66.3 daemons); fine.
- `_verify_relaunch` check order (exception → no code_path → identity_error → dev_tree → path compare) is right once the field arrives.
- The four untracked plan-4 RED tests and `test_graph_landing.py::test_context_op_honors_partition_under_ambient_drift` were not run and are not counted, per the brief.

## Verdict {#verdict}

**DIRTY — 4 findings (1 BULLSHIT, 1 SKETCHY, 2 MEH). Blocker: [[#b-1-r4]].**

Three of the four r3 findings closed for real (registry, lint scope, ping-exception test) and the r3 live-tick question is answered by the 21:18:19 alert. The fourth — the one that was the substance of the round — shipped readers for a field the producer never sends, tested against hand-written ping results, and the hub's own error line is still unread. One line in `_op_ping`, one branch in `hub_status`, and a test that starts at the producer close it. Plan 1 stays open until then.

rel: contradicts -> [[claude#no-silent-failures]]
