---
gmd: "0.1"
id: bsd-plan2-hooks-reproducible-r7-8d0a665
title: "plan-2-hooks-reproducible round 7: the bound now holds on the wire (12 live runs 1.86–4.66 s at --timeout 5, results, exit 0) and r6's #s-2/#m-3/#m-4/#m-5/#m-6 are closed; but the rerank leg the bound was built around is dead as deployed — the 1 s probe timeout stays on the socket and every score call inherits it, so a healthy worker (25 docs in 1.0 s) never reranks a hook (0/12), each abandoned request starves the next probe, and the same shape shipped in scan-prompt eleven minutes later"
tags: [bsd, findings, plan-2, hooks, re-review]
severity: BULLSHIT
plan: plan-2-hooks-reproducible
task: task-2.1-plan-2-hooks-reproducible, task-2.2-plan-2-hooks-reproducible, task-2.3-plan-2-hooks-reproducible
metadata:
  node_type: bsd-report
  commit_range: 3fa98bc..8d0a665
  round: 7
---

# ch-bsd findings — plan-2-hooks-reproducible round 7 (3fa98bc..8d0a665, judged at 7bca4bb) {#root}

**Commits audited:** f14ab96 (remedy-plan-2-r6), 4a8260d (merge), cd826bc (follow-up), 8d0a665 (merge), ffa2896 (docs). Judged at HEAD 7bca4bb with the two later commits on the same surfaces read: 4d31e24 (bug-015: `SHARED_OP_TIMEOUT_S`, `scan-prompt --timeout`) and 72f61e0/f733f6c (bug-014: the hub keeps its workers). The other merges in the range belong to plans 3/4/5/6.
**Date:** 2026-09-15
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-2 commits):** 6 (`src/refmatrix/cli.py`, `reranker.py`, `hooks.py`, `verbs.py`; `tests/test_plan2_remedy_r6.py` new, `tests/test_plan2_remedy.py`; `.claude/settings.json`, README, plan, summary, registry)
**Deployed:** `~/refmatrix` at 7bca4bb (`~/bin/rmx version -v` → 0.69.1, code `~/refmatrix/src/refmatrix`); `~/bin/rmx install-hooks --check` → "hooks in sync"; fleet 8/8 v0.69.1; hub restarted 03:02:45 with bug-014, embed worker warm 03:02:56, rerank worker warm 03:03:09 (`~/.refmatrix/hub.log`). Every measurement below ran after 03:05 on the warm, healthy workers.
**Tests:** `workflow/review-output/pytest-bsd-plan2-r7-7bca4bb.log` — 55 passed in 17.65 s (test_plan2_remedy_r6, test_plan2_remedy, test_hooks_reproducible, test_repo_hooks_in_sync, test_docs_hooks_target); `pytest-bsd-plan2-r7-parity-7bca4bb.log` — 44 passed (verb + MCP parity). The remedy's RED/GREEN/mutation logs exist and say what the summary says (8 failed RED incl. a 300 s stalled-worker run; mutations A/B/C each fail their test; the follow-up's own RED/GREEN is a 1-test run).
**Method:** (1) the exact deployed hook argv timed on the live store, read-only, 12 runs spaced 8 s, plus a leg decomposition (`--no-rerank`, `--scope project/global`, `--timeout 10`); (2) the hub's shared workers timed directly over `models.sock` (`info`, `rerank` at 5/25/50 docs, `embed`); (3) a fake `models.sock` in a `/tmp` root under `.venv-eval` that answers `info` at once and `rerank` after 1.5 s (`leak_r7.py`, session scratchpad) — the deployed call shape vs the control; (4) a tmp `RMX_HOME` with a global root and no daemon behind a real project daemon (`gsim_r7.py`); (5) `.refmatrix/cli.log` `source=hook` rows, `~/.refmatrix/hub.log`.

rel: amends -> [[bsd-plan2-hooks-reproducible-r6-3fa98bc]]
rel: evidence-for -> [[plan-2-hooks-reproducible]]

## Round-6 findings: status after remediation {#status}

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| #b-1 | the per-prompt hook with `--timeout 5` deployed held the turn 12.8 s idle / 26.8 s live | **CLOSED as a bound; reopened as [[#b-1]] for the leg it was built around** | Live, healthy workers, exact argv: 4.66 / 1.93 / 1.95 s (03:07–03:08), then five spaced runs 1.87 / 1.96 / 1.90 / 1.97 / 1.93 s, `--timeout 10` 2.32 / 1.86 s — all exit 0, 5 rows. cli.log hook rows today with `--timeout 5`: 02:37:32 5163 ms, 03:01:20 5021 ms, 03:05:33 1845 ms, 03:07:59 4469 ms, then 1735 / 1753 ms — max 5163 ms = budget + 0.16 s, every exit 0. Acceptance (wall ≤ budget + 1 s with results) met; Q7's tighter + 0.6 s also met. The clock starts before `_memory_intent` (`cli.py:10095-10097`), the verb takes `_left(budget)` (`:10246`), the global leg takes `_left(30)` + `retries=0` on both paths (`:10199-10200`, `verbs.py:741`, `hub.global_call(retries)` at `hub.py:144-152`), the replica leg bounds `shared_available`, the embed client and the rerank client (`:9264-9275`), skips under `RERANK_MIN_S` and says so (`:9282-9284`), re-raises the deadline (`:9300-9301`). But see [[#b-1]]: not one of the 12 runs reranked. |
| #s-2 | closure tests scoped/toleranced to miss the failing legs | CLOSED | `elapsed < 1.6` for a 1 s budget on both hook argvs (`test_plan2_remedy_r6.py:57-67`, `test_plan2_remedy.py:526`); the deadline test runs `scope="both"` with a `dm.call` spy asserting `retries == 0` and `timeout ≤ budget` on the global root (`:72-100`); a held GLOBAL store on a real socket behind a real spawned project daemon (`:103-123`); a real `models.sock` that accepts and never answers on the replica path (`:126-170`, 2 s budget < 2.6 s). Residual: the two rerank tests fake the reranker and the client (`_SlowReranker`, `_Timing`, `_Client`), so nothing in the suite puts a `rerank` call on a socket after an `info` probe — which is exactly where [[#b-1]] lives. |
| #m-3 | PreCompact recall unbudgeted, not hook mode | CLOSED | `hooks.py:341` `--timeout 30`; installed `.claude/settings.json` PreCompact `memory recall --recent --since 1h --k 20 --scope both --json --timeout 30`; `hook_mode` includes `RMX_INVOCATION_SOURCE == "hook"` (`cli.py:10153-10154`); `test_precompact_recall_is_bounded_and_hook_env_is_hook_mode` runs it on a held writer → `[]`, exit 0, < 1.6 s. |
| #m-4 | MCP `timeout` None vs CLI 60 s | CLOSED | CLI `--timeout` default 30.0 (`cli.py`, the `memory recall` option); `verbs.memory_recall(timeout: float | None = 30.0)`; parity gates 44 passed. |
| #m-5 | registry row named a file with no patch | CLOSED | row 41 names `tests/test_plan3_remedy_r3.py`. |
| #m-6 | SessionStart recall unobserved live | CLOSED | cli.log 02:20:42 `memory recall --session-start --k 10 --scope both --json --timeout 10` 55 ms exit 0 (source=hook). `focus context` still unseen (user-gated; no longer carried). |

## Findings {#findings}

### BULLSHIT: the rerank leg is dead as deployed — `info(timeout=probe_timeout)` sets the socket to 1 s and never restores it, `score` → `call("rerank")` passes no timeout and inherits it, so on a healthy worker that needs ~1.0 s for the hook's 20-doc pool the rerank fails on every run, and each abandoned request holds the worker so the next run's probe fails too {#b-1}

**File:** `src/refmatrix/modelsrv.py:150-172` (`call`: `if timeout is not None: self._sock.settimeout(timeout)` — set for this call, never reset to `self.timeout`), `:182-191` (`info(timeout=)` → that `call`), `src/refmatrix/reranker.py:157-166` (`RemoteReranker.score` → `self._client.call("rerank", …)` with no `timeout`, so the socket keeps the probe's 1 s), `:318-319` (`SharedWorkerClient("rerank", timeout=timeout)` then `client.info(timeout=probe_timeout)` — docstring `:295-299` says `timeout` "bounds every score call"; it does not), `src/refmatrix/cli.py:9291-9292` (`shared_reranker(timeout=rem, probe_timeout=min(rem, RERANK_PROBE_S=1))` — the deployed hook shape, cd826bc), `src/refmatrix/scan.py:953-957` (same shape, bug-015 4d31e24, comment: "the probe gets 1 s, the score call the rest" — the score call gets 1 s).
**What:** The hub's rerank worker has been warm since 03:03:09. Timed directly over `models.sock` from the deployed venv: `info` 1 ms; `rerank` 25 docs 0.98 s / 1.06 s, 50 docs 2.78 s, 5 docs 0.41 s; `embed` 52 ms. The hook's pool is `k × DEFAULT_POOL_MULT` = 5 × 4 = 20 docs → ~0.9 s. Twelve runs of the exact hook argv on the live store after that, spaced 8 s so nothing of mine overlapped:

| run | argv | wall | stderr |
|---|---|---|---|
| 03:07:59 | `--timeout 5` | 4.66 s | `rerank skipped: 0.6s of the budget left (< 2s)` |
| 03:08:01 | `--timeout 5` | 1.93 s | `rerank failed (TimeoutError: timed out)` |
| 03:08:03 | `--timeout 5` | 1.95 s | `rerank skipped: shared worker unavailable` |
| spaced ×5 | `--timeout 5` | 1.87 / 1.96 / 1.90 / 1.97 / 1.93 s | failed / unavailable / failed / unavailable / failed |
| | `--scope project` | 1.89 s | `rerank failed (TimeoutError: timed out)` |
| | `--timeout 10` ×2 | 2.32 / 1.86 s | failed / unavailable |
| | `--no-rerank` (both / project) | 0.96 / 0.80 s | — |

0 of 12 reranked; the two warnings alternate because the worker is still scoring the request run N abandoned at 1 s when run N+1's 1 s `info` probe arrives, so `shared_reranker` returns None ("unavailable"). Doubling the budget changes nothing — the score call's bound is `RERANK_PROBE_S`, not `rem`. On a fake `models.sock` under `.venv-eval` (`leak_r7.py`: `info` answered at once, `rerank` after 1.5 s): deployed shape `shared_reranker(timeout=4.0, probe_timeout=1.0)` → socket timeout after `info()` = **1.0**, `score` → `TimeoutError` at 1.00 s; control `shared_reranker(timeout=4.0)` → socket 4.0, scored in 1.51 s. The remedy's own live log (`live-recall-hook-4a8260d.log`) shows the same signature — run 1 `rerank failed (TimeoutError: timed out)` at 2.42 s wall, which no 300 s or `rem`-bounded socket can produce — and the summary reads it as "the hub's rerank worker is broken, bug-014/015". The worker was fixed at 03:03; the hook's outcome did not change.
**Why it's bullshit:** r6 #b-1's fix (1) said: bound the rerank with `_left()`, skip it when the budget cannot fit it, never skip the answer. The remedy bounded it, then the follow-up cd826bc fixed "the probe ate 4 of 5 s" by giving the probe 1 s — and, through a socket the client never resets, gave the score call 1 s too. A rerank that fits the budget (4 s left, 1 s needed) is now failed instead of run, on every prompt, with a warning that sounds like the fleet's fault. That is dead code on the audited surface (`apply_rerank` on the hook path is unreachable in production on a healthy worker — rule 1), a cheap fix (the symptom went away; the docstring at `reranker.py:295-299` and Q7's "the rerank client is constructed with the remaining budget" are now false on the wire — rule 10), and self-concealing (the r6 #b-1 measurement `--no-rerank` 0.96 s vs 1.9 s "with" rerank is the cost of a 1 s timeout, not of a rerank). The tests could not see it because every rerank test fakes the client (`_Client`, `_Timing`, `_SlowReranker`) — [[impression_bsd_tests_bypass_wiring]] — and the one real socket (`_SilentModelSocket`) never answers `info`, so no test has ever put a `rerank` frame on a socket after a bounded probe. Sibling: the identical call shape shipped in `scan.py:956-957` eleven minutes later (bug-015) with a comment asserting the opposite of what it does — [[impression_bsd_quoted_line_sibling]]; `scan-prompt --timeout 5` live: 1.47 s, and its rerank failure is invisible (the hook line ends `2>/dev/null || true`). Third sibling, the other direction: `daemon.py:758-762` constructs the client with `SHARED_OP_TIMEOUT_S` (30) and probes with `PROBE_TIMEOUT_S` (45), so the daemon's "30 s bound" is 45 s on the socket — bounded, misreported (bug-015's, noted, not filed).
**Evidence:** `probe_r7.out` and `leak_r7.py` output in the session scratchpad (copied above); cli.log rows 03:07:59 → 03:08:03 and the five spaced runs; hub.log 1717-1722 (workers warm 03:02:56 / 03:03:09; no failures after); `git show cd826bc -- src/refmatrix/reranker.py` (the `probe_timeout` line); `modelsrv.py:150-172` — no `settimeout(self.timeout)` after a timed call.
**Fix:** In `SharedWorkerClient.call`, restore `self._sock.settimeout(self.timeout)` after a per-call `timeout` (a `finally:` on the timed branch), or have `info()` restore it — one place fixes `memory recall`, `scan-prompt` and the daemon's 45-vs-30 s at once. Then a real-socket test in `test_plan2_remedy_r6.py`: a `models.sock` that answers `info` at once and `rerank` after ~1.5 s; `shared_reranker(timeout=4, probe_timeout=1).score(...)` must return scores (the `leak_r7.py` control is the template), and `_replica_memory_recall` through it must return `reranked: True`. Re-measure the hook: with a warm worker it should say nothing on stderr and return in ~2 s with `reranked` hits; `--no-rerank` should be ~1 s faster, not 1 s equal. Also `RemoteReranker.score` could pass `timeout=self._client.timeout` explicitly so the bound is visible at the call. ~3 lines + 1 test.
**Pattern match:** YES — [[impression_bsd_quoted_line_sibling]] (scan.py), [[impression_bsd_tests_bypass_wiring]] (fake client), [[impression_bsd_cost_measured_idle]] (the bound was measured, the answer was not), cheap fix (rule 10).

rel: contradicts -> [[plan-2-hooks-reproducible#decisions-log]]
rel: contradicts -> [[claude#no-workarounds]]
rel: contradicts -> [[impression_bsd_quoted_line_sibling]]
rel: contradicts -> [[impression_bsd_tests_bypass_wiring]]

### SKETCHY: the r6 test file patches `dm.call`, `dm.ping`, `discovery.daemon_status`, `discovery.store_name`, `hub.global_store_root` and `hub.ensure_global_daemon` and none of those registry rows name it — third plan-2 registry gap (r5 #s-2, r6 #m-5, r7) {#s-2}

**File:** `tests/test_plan2_remedy_r6.py:72-77, 108-112, 262-268` vs `workflow/test_mock_registry.md:29, 39, 41` (`daemon.call`/`daemon.ping`, `discovery.daemon_status` rows — the last names `tests/test_plan2_remedy.py` and four other files, not `_r6`); no row anywhere names `hub.global_store_root` or `hub.ensure_global_daemon` as a patch target (row 48 names `hub.global_call`).
**What:** Rows 45 and 47 register the socket simulation and the reranker/client fakes correctly. The daemon-side and hub-side patches in the same file were not added. `git show --stat cd826bc f14ab96` touches the registry only for the two new rows.
**Why it's sketchy:** MEH by itself; escalated to SKETCHY as the third plan-2 registry omission in three rounds ([[impression_bsd_registry_row_deferral]] noted the 3-for-3 in plan 1; plan 2 is now 3-for-3 as well).
**Fix:** add `tests/test_plan2_remedy_r6.py` to rows 29/39/41 and a `hub.global_store_root` / `hub.ensure_global_daemon` (tmp root / no-op) entry. Five words and one row.

rel: contradicts -> [[claude#no-mocks]]

### MEH: `ensure_global_daemon()` runs before the budgeted global call — a bare `ping` (0.5 s × 3) and, on a missing daemon, `spawn_daemon_subprocess(wait_for_ready=30)` sit outside `_left()` {#m-3}

**File:** `src/refmatrix/hub.py:125-152` (`global_call` → `ensure_global_daemon()` → `daemon_mod.ping(root)` → `spawn_daemon_subprocess(...)` with the 30 s default wait → `ping` again; only the `daemon_mod.call` after it takes `timeout`/`retries`).
**What:** Simulated under a tmp `RMX_HOME` (global root exists, no daemon, real project daemon, `RMX_SHARED_MODELS=0`): `--session-start --scope both --timeout 1` → 0.44 s, exit 0, the hook spawned the global daemon and the second run took 0.02 s. On an empty tmp store the boot is fast; on the live global store during the boot window plan-4 opens on every relaunch, the ping fails (plan-5 r2's booting-is-absent shape) and the hook both waits for and double-spawns a daemon launchd is already bringing up. Not observed live today.
**Fix:** `ensure_global_daemon(timeout=)` with the ping through `discovery.daemon_status` and `wait_for_ready=min(30, left)`; in hook mode a missing global daemon is "global rows omitted", not a spawn. ~6 lines. Plan-4/plan-5 own the classifier; the budget is plan-2's.

## Deferral sweep {#deferrals}

Hard and soft patterns over every added line of f14ab96 and cd826bc in `src/`: none. The r5/r6 exemptions stand (`memory list` step comments).

## Verdict {#verdict}

**DIRTY — 3 findings (1 BULLSHIT, 1 SKETCHY, 1 MEH).**

The bound is real on the wire now: one clock from before the partition probe, every leg on it, and twelve live runs of the deployed argv on the healthy fleet between 1.86 s and 4.66 s with results and exit 0 — the acceptance number holds, and the `[]`-in-5.1 s and exit-1 shapes the summary describes were the daemon wedge and the pre-follow-up code, both since fixed. Round 6's #s-2/#m-3/#m-4/#m-5/#m-6 are closed and each reproduced.

**May plan-2 flip to `completed`? No.** The leg the whole round was about — the rerank on the shared worker — does not run: the follow-up's 1 s probe bound stays on the socket and the score call inherits it, so a healthy worker that answers in 1.0 s is failed on every prompt and the abandoned requests make the next probe fail in turn. Q7's "the rerank client is constructed with the remaining budget" is false on the wire, the docstring says the opposite of what the code does, and the only tests that touch the rerank fake the client. It is a three-line fix in `SharedWorkerClient.call` (restore `self.timeout` after a timed call) plus one real-socket test — and it also fixes `scan-prompt` and the daemon's misreported 30 s. Land that, add [[#s-2]]'s registry words, re-measure the hook with `reranked: True` hits and no stderr, and this plan can close with [[#m-3]] tracked.

rel: evidence-for -> [[feedback_measure_the_path_users_run]]
rel: contradicts -> [[plan-2-hooks-reproducible#decisions-log]]
