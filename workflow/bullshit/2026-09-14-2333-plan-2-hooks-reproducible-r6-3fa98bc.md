---
gmd: "0.1"
id: bsd-plan2-hooks-reproducible-r6-3fa98bc
title: "plan-2-hooks-reproducible round 6: r5's four code items are closed and reproduced; #b-1 is not — the per-prompt hook with `--timeout 5` deployed took 26.8 s and 18.9 s live and 12.8 s idle, because the budget covers the daemon calls and not the rerank on the shared model worker, the global store on the dense path, or the startup partition probe; 4th partial-bound sighting"
tags: [bsd, findings, plan-2, hooks, re-review]
severity: BULLSHIT
plan: plan-2-hooks-reproducible
task: task-2.1-plan-2-hooks-reproducible, task-2.2-plan-2-hooks-reproducible, task-2.3-plan-2-hooks-reproducible
metadata:
  node_type: bsd-report
  commit_range: 1eea8ed..3fa98bc
  round: 6
---

# ch-bsd findings — plan-2-hooks-reproducible round 6 (1eea8ed..3fa98bc, judged at e1dba80) {#root}

**Commits audited:** f11cf05 (remedy-plan-2-r5), be3901e (merge), 3fa98bc (regenerated `.claude/settings.json`). The paths were judged at HEAD e1dba80; the later plan-3 r4 / plan-5 r2 / plan-4 r2 merges touch `memory_partition`, `_call`, `_store()` and are credited or blamed to their plans.
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 12 (`src/refmatrix/cli.py`, `hooks.py`, `verbs.py`; 3 test files; `.claude/settings.json` + `rmx-hooks.json`; plan, plan-of-plans, summary, mock registry)
**Deployed:** `~/refmatrix` at e1dba80 (`~/bin/rmx version -v` → 0.69.1, code `~/refmatrix/src/refmatrix`); `~/bin/rmx install-hooks --check` → "hooks in sync"; fleet 8/8 at v0.69.1, restarts=0; the deploy tree carried f11cf05 from 22:39:56 (reflog), so every live `--timeout 5` row below ran the remedy.
**Tests:** `workflow/review-output/pytest-bsd-plan2-r6-3fa98bc.log` — 104 passed in 13.76 s (test_plan2_remedy, test_hooks_reproducible, test_repo_hooks_in_sync, test_docs_hooks_target, test_verb_parity, test_mcp_parity, test_mcp_memory_recall_routing, test_verbs_memory_recall). RED/GREEN/mutation logs named in the summary exist (5 failed → 163 passed; mutation B fails the deadline test).
**Method:** (1) the deployed `~/bin/rmx` timed on the live project store, read-only, under the idle fleet, with the exact hook argv; (2) the dense leg decomposed on the deployed venv (replica reader + shared workers, read-only); (3) real pid file + real unix socket simulation in `/tmp` roots under `.venv-eval` — `_PingOnlyDaemon` as the project store, then a fast project daemon with `_PingOnlyDaemon` as the global store via `RMX_HOME` — script `sim_plan2_r6.py` in the session scratchpad; (4) `.refmatrix/cli.log` `source=hook` rows; `~/.refmatrix/hub.log`.

rel: amends -> [[bsd-plan2-hooks-reproducible-r5-a89c733]]
rel: evidence-for -> [[plan-2-hooks-reproducible]]

## Round-5 findings: status after remediation {#status}

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| #b-1 | the per-prompt recall hook is unbounded (p50 20 s live) | **OPEN** (partially remedied) | The daemon legs now carry one deadline and both hook modes degrade to `[]` + exit 0 + warning on a held writer (sim: `_PingOnlyDaemon`, `--timeout 1/2/3` → exit 0, `[]`, warning). On the wire the hook is still not bounded: deployed `--stdin-json --k 5 --scope both --json --timeout 5` → **12.80 s** (project 14.22 s, global 12.65 s), full results, no warning, exit 0; live rows with `--timeout 5`: **23:10:53 → 26 788 ms**, **23:29:48 → 18 850 ms**, both exit 0. See [[#b-1]]. |
| #s-2 | registry row named 2 of 4 `daemon_status` sites | CLOSED | row names the five `test_plan2_remedy.py` sites; residual: it also names `tests/test_plan3_remedy.py`, which contains no `daemon_status` patch (the file is `test_plan3_remedy_r3.py`) — [[#m-5]]. |
| #m-3 | detach budgets additive, message named one leg | CLOSED | `_detach_deadline = t0 + budget` set after the `retries=0` classification; `_ingest_partition` and `ingest_gmd_start` both take `_detach_left()`; message prints `waited N.Ns of a Bs budget`; the r5 test asserts `waited` ≈ elapsed within 0.6 s at a 1 s budget and passes at HEAD. Floor `max(0.5, …)` gives each leg 0.5 s past the deadline — bounded, immaterial. |
| #m-4 | legacy-partition probe cached a timeout silently | CLOSED | `probe_failed` → stderr `partition_list probe failed (TimeoutError: timed out); assuming the project partition for THIS command only`, not cached; the r5 test proves a second call re-probes; the warning was seen verbatim in every sim run. |
| #m-5 | PreCompact / SessionStart / `focus context` hooks unobserved | HALF-CLOSED | PreCompact fired live at 23:23:21: `focus summarize --promote --timeout 30` 139 ms exit 0, `memory recall --recent --since 1h` 47 ms exit 0, `save-state --no-promote --no-sync` 92 ms exit 0. SessionStart (`--session-start … --timeout 10`, `ingest-gmd --detach`) and `focus context` rows are still absent since the argv changed. Carried as [[#m-6]]. |

## Findings {#findings}

### BULLSHIT: the per-prompt hook with `--timeout 5` deployed holds the turn 12.8 s idle and 26.8 s / 18.9 s live — the deadline covers the daemon RPCs and not the three legs that actually cost: the rerank on the hub's shared model worker, the global store on the dense path, and the startup partition probe that runs on a second budget {#b-1}

**File:** `src/refmatrix/cli.py:10234` (`_replica_memory_recall(...)` called before `_left()` exists for it; the function takes no budget), `:9202-9206` (`shared_reranker()` → `client.info()` with `timeout=None`; `apply_rerank` → `RemoteReranker.score` → `self._client.call("rerank", …)` with no timeout; `modelsrv.SharedWorkerClient` default `DEFAULT_TIMEOUT_S = 300`), `:10364` and `:9757-9760` (dense path `_global_rows(q, …)` → `_global_recall_rows(q, k, recent, since_s)` → `verbs.global_recall_rows(...)` with no `timeout` → 30 s), `src/refmatrix/hub.py:140-145` (`global_call` has no `retries` parameter → `daemon_mod.call(..., timeout=timeout)` with the library's 2 retries), `src/refmatrix/cli.py:9997` + `:10050` (`_memory_intent(partition_timeout=5)` runs its own 5 s probe; `_t_start = monotonic()` is taken afterwards, so the recall budget starts at zero again).
**What:** Four measurements of the shipped hook argv on the deployed binary and the live store:

| run | scope | wall | outcome |
|---|---|---|---|
| idle, `--timeout 5` | both | 12.80 s | 5 rows, no warning, exit 0 |
| idle, `--timeout 5` | project | 14.22 s | 5 rows, no warning, exit 0 |
| idle, `--timeout 5` | global | 12.65 s | `[]`, no warning, exit 0 |
| idle, `--timeout 5 --no-rerank` | project | 0.96 s | 5 rows |
| idle, `RMX_RECALL_REPLICA_FIRST=0 --timeout 5` | project | 5.13 s | `[]`, "recall skipped: daemon busy (recall not confirmed within 5s: timed out)" |
| live hook 23:10:53 (pid 72935) | both | 26.79 s | exit 0 |
| live hook 23:29:48 | both | 18.85 s | exit 0 |

Decomposed on the deployed venv (replica reader + shared workers): embed + `dense_recall` pool=20 **0.56 s**; `shared_reranker()` **6.31 s** (its `client.info()` probe — `hub.log` logs `models role=rerank op=info failed: BrokenPipeError` in pairs at 23:26:33, 23:27:19, 23:28:04, 23:28:11, one pair per run of mine); `apply_rerank` **6.22 s**. The rerank leg is ~12.5 s of the 12.8 s and sits inside `_replica_memory_recall`, which the budget never reaches: `SharedWorkerClient.info(timeout=None)` and `call("rerank")` both run at the 300 s worker default. Simulation of the other two legs (real sockets, `/tmp` roots): (a) project daemon answers ping and stalls every op → `--timeout 1/2/3` wall **2.01 / 4.01 / 6.01 s**, `--session-start --timeout 1/2` **2.02 / 4.03 s** — exactly twice the budget, because `_memory_intent`'s partition probe spends its own `partition_timeout` before `_t_start` is taken; (b) fast project daemon, global store (`RMX_HOME`) answers ping and stalls → `--session-start --scope both --timeout 1/2` wall **3.14 / 6.13 s** (three attempts of the remaining budget: `hub.global_call` cannot pass `retries=0`), and `--stdin-json --scope both --timeout 1` wall **90.18 s** (the dense path's global leg carries no budget at all: 30 s × 3). Every run exited 0 with `global rows omitted … timed out` — loud, but the turn was held.
**Why it's bullshit:** The r5 finding was "the hook that fires on every prompt is unbounded"; the closure commit says "ONE deadline over the partition probe, the recall op, per-hit memory_get, the global store and context bundles (retries=0 on every leg)" and the summary says the hook modes are timed "at < 2.5 s for a 1 s budget". The deployed hook took 26.8 s and 18.9 s on its first two live firings after the fix, with the budget in its argv — longer than the unbounded rows r5 measured (p50 20 s). Q4 is unchanged: a hook may shout; it may not hold the turn for the store. This is the fourth partial-bound sighting in four rounds (r3: one call of three; r4: the probe and none of the ops; r5: three hooks of five; r6: the daemon legs and not the model-worker, global, or probe legs) — [[bsd-pattern-partial-bound]] bumps to 4. The new shape is the one [[impression_bsd_cost_measured_idle]] warned about: the remedy bounded what the finding's *diagnosis* named (the daemon's `memory_recall`) rather than re-measuring where the seconds go; `--no-rerank` at 0.96 s would have shown it in one run. Two further consequences the tests cannot see: with the replica unavailable the budget *does* hold and the hook answers `[]` on every prompt (5.13 s) because the operation's idle cost (12 s of rerank daemon-side too) is above the budget — a bound set below the idle cost of the thing it bounds is a kill switch, not a budget; and the `< 2.5 s for a 1 s budget` tolerance is precisely wide enough to admit the 2.0 s additive shape the r4 #m-3 / r5 #m-3 findings closed on two sibling paths.
**Evidence:** timings above (`/usr/bin/time -p` on `~/bin/rmx memory recall --stdin-json --k 5 --scope both --json --timeout 5` with a prompt on stdin); cli.log rows pid 72935 (`latency_ms: 26788`) and 23:29:48 (`latency_ms: 18850`), both `"--timeout", "5"` in argv, `exit_code: 0`; sim output in this session's scratchpad (`sim_plan2_r6.py`: Q1 2.01/4.01/6.01 s, Q2 3.14/6.13 s and 90.18 s); `grep -n timeout src/refmatrix/reranker.py` → none on the score path; `hub.global_call` signature `(op, args=None, *, timeout=60.0)`.
**Fix:** (1) `_replica_memory_recall(..., deadline=)` — pass `_left()` into `SharedWorkerClient.info(timeout=)` and `.call("rerank", timeout=)` for both embed and rerank; when `_left()` is below what the rerank needs, skip the rerank and say so (`warnings`), do not skip the answer. (2) Take `_t_start` BEFORE `_memory_intent` (or pass the same deadline into `partition_timeout`) so the probe is inside the budget, and tighten the test to `elapsed < budget + 0.5`. (3) `hub.global_call(..., retries=)` threaded from `global_recall_rows(timeout=, retries=0)`; the dense path's `_global_rows` takes `_left(30.0)`. (4) A test that reaches each leg: `_PingOnlyDaemon` as the global store at `--scope both` on BOTH paths, and a stalled `SharedWorkerClient` (a socket that accepts and never answers) for the replica path — the simulation in this report is the template. (5) Separately, with ch-performance-tuner: the rerank worker's `info` op fails with a broken pipe on every call and the worker takes ~6 s to answer either op — that is the 12 s, and it is a hub/model-worker defect, not plan-2's; but the bound is plan-2's, and the bound must hold regardless of what the fleet costs. ~30 lines.
**Pattern match:** YES — imp-partial-bound (4th), imp-cost-measured-idle, feedback_measure_the_path_users_run.

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
rel: contradicts -> [[impression_bsd_partial_bound_guard]]
rel: contradicts -> [[impression_bsd_cost_measured_idle]]
rel: evidence-for -> [[bsd-pattern-partial-bound]]

### SKETCHY: the closure tests are built so the legs that fail cannot be in the assertion — `scope="project"` on the deadline test, a 2.5 s tolerance on a 1 s budget, and no test on the replica path {#s-2}

**File:** `tests/test_plan2_remedy.py:484-501` (`test_recall_hook_modes_are_bounded_and_degrade_to_empty`: `assert elapsed < 2.5` for `--timeout 1`; measured 2.01 s and 2.02 s — the additive shape passes by 0.48 s), `:518-543` (`test_verb_recall_timeout_is_a_deadline_across_calls`: `scope` left at the default `"project"`, so `seen` never contains the global leg whose `retries` is 2; `assert all(rt == 0 …)` is true of the population it sees), `RMX_RECALL_REPLICA_FIRST` untouched by any test and `shared_available()` true on this workstation, so the replica leg is exercised by nothing.
**What:** Three assertions that each prove the bound on the subset of the path that carries it. The summary quotes the first as the hook-mode proof ("< 2.5 s for a 1 s budget").
**Why it's sketchy:** [[impression_bsd_existence_check_tests]] — count the population versus the compared set: the deadline test's `seen` list is the daemon legs on the project store, never the global store; the tolerance is set above the failure it is meant to exclude. Second plan-2 sighting of a test whose tolerance or scope admits the finding's shape (r5 #m-3's remedy test was written the same way and passed at 1.24 s "for" a 0.5 s budget until the r5 report measured it) → SKETCHY.
**Fix:** `elapsed < budget + 0.5`; run the deadline test at `scope="both"` with a `global_call` spy asserting `retries == 0`; one replica-path test with a stalled worker socket. Comes free with [[#b-1]] fix (4).

rel: contradicts -> [[impression_bsd_existence_check_tests]]

### MEH: the third recall hook the generator emits (PreCompact `memory recall --recent --since 1h --k 20 --scope both --json`) carries no `--timeout` and the CLI does not treat it as a hook {#m-3}

**File:** `src/refmatrix/hooks.py:338-344` (no `--timeout`), `src/refmatrix/cli.py:10040` (`hook_mode = bool(session_start or stdin_json)` — `--recent` is interactive), `:10048` (budget → 60 s), `:10146-10151` (busy in non-hook mode → replica fallback, absent → `VerbError` → exit 1).
**What:** The generator has three recall hooks; the remedy budgeted two. The third runs at the interactive 60 s default — equal to Claude Code's own kill timer, so "fails loud before the harness kills it" (the r3 #m-5 rule the PreCompact promote got `--timeout 30` for) does not hold — and its global leg is 3× that. It fired live once at 23:23:21 (47 ms, exit 0), so the cost is not the issue today; the asymmetry with the other two is.
**Fix:** `--timeout 30` in the generator; either classify `RMX_INVOCATION_SOURCE=hook` as hook mode or accept the interactive semantics deliberately in the plan file. Regenerate + `install-hooks --check`. 3 lines.

### MEH: the MCP tool's `timeout` default is unbounded while the CLI's is 60 s; the parity defaults test passes on the literal `None == None` {#m-4}

**File:** `src/refmatrix/verbs.py:618` (`timeout: float | None = None` → `deadline = None` → `_retries = 2`, `memory_recall` op at 180 s × 3), `src/refmatrix/cli.py:10048` (`None` → 60 s interactive), `tests/test_verb_parity.py:43,157` (`rmx_memory_recall` no_twin excludes `since_seconds/kinds/exclude_mtype`; `timeout` IS compared — as `None` vs `None`).
**What:** The MCP schema now exposes `timeout` ("omit for the library defaults" — 540 s + 90 s per hit + 30 s global). An agent calling the tool with no timeout gets a different bound than an operator typing the command. Documented, so MEH; plan-3's surface (the parity gate compares declared defaults, not effective ones — the k 8 vs 10 shape from plan-3 r1).
**Fix:** either the verb owns the 60 s default (the CLI passes through) or the parity test compares effective defaults for `timeout`. Attributed to plan-3.

### MEH: the mock-registry row for `discovery.daemon_status` names `tests/test_plan3_remedy.py`, which contains no such patch {#m-5}

**File:** `workflow/test_mock_registry.md:41`; `grep -ln daemon_status tests/test_plan3*.py` → `tests/test_plan3_remedy_r3.py` only.
**What:** The r5 #s-2 remedy added the five plan-2 sites correctly and two cross-plan files by guess; one is the wrong filename.
**Fix:** `test_plan3_remedy.py` → `test_plan3_remedy_r3.py`. One word.

### MEH: SessionStart `--session-start … --timeout 10`, the `ingest-gmd --detach` bridge and `focus context` are still unobserved live (carried from r5 #m-5; the PreCompact third is closed) {#m-6}

**File:** `.refmatrix/cli.log` (`source=hook`, completed rows since 22:40: the two `--timeout 5` recalls, the three PreCompact commands at 23:23:21; no SessionStart rows despite the argv change at 23:10 implying a restart — the recall's own row would be `--session-start … --timeout 10`).
**What:** Cannot gate closure; the next audit reads the rows. Idle timing of the SessionStart recall on the deployed binary: 0.17 s.

## Deferral sweep {#deferrals}

Hard: none in the plan-2 hunks (`cli.py:11534-11561` "Phase 1/2/3" are step comments in `memory list`, unchanged). Soft (diff-added lines in `src/`): none. The r5 exemptions stand.

## Verdict {#verdict}

**DIRTY — 6 findings (1 BULLSHIT, 1 SKETCHY, 4 MEH).**

Round 5's four code items are closed and each reproduced on a real socket: the detach path is one deadline and reports its wait, the legacy probe warns and re-probes, the registry names the sites, and PreCompact has now been seen bounded live. The daemon-leg deadline in `verbs.memory_recall` is real and the hook-mode degrade (`[]` + warning + exit 0) is the right contract.

**May plan-2 flip to `completed`? No.** The r5 BULLSHIT was that the per-prompt hook holds the turn; the first two live firings of the remedied hook held it 26.8 s and 18.9 s, and the idle cost is 12.8 s against a 5 s budget with no warning printed. The budget was applied to the diagnosis (daemon RPCs) and not to the measurement (the rerank on the shared worker, then the global store, then the probe that runs before the clock starts). Fix [[#b-1]] (1)-(4) and re-measure the deployed argv under the idle fleet — the acceptance number is wall ≤ budget + 1 s on the exact hook command, on the live store, with results — then this plan can close with [[#m-3]]/[[#m-5]] in the same commit and [[#m-4]] handed to plan-3.

rel: evidence-for -> [[feedback_measure_the_path_users_run]]
rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
