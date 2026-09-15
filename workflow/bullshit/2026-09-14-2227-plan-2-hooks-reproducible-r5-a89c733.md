---
gmd: "0.1"
id: bsd-plan2-hooks-reproducible-r5-a89c733
title: "plan-2-hooks-reproducible round 5: r4's five items are closed and reproduced on a real socket; the plan cannot close because the hook that fires on EVERY prompt (`memory recall --stdin-json`) is unbounded and holds the turn for the store 20 s at the median — the bound covers the three hooks the findings named and not the one users pay for"
tags: [bsd, findings, plan-2, hooks, re-review]
severity: BULLSHIT
plan: plan-2-hooks-reproducible
task: task-2.1-plan-2-hooks-reproducible, task-2.2-plan-2-hooks-reproducible, task-2.3-plan-2-hooks-reproducible
metadata:
  node_type: bsd-report
  commit_range: d68856d..a89c733
  round: 5
---

# ch-bsd findings — plan-2-hooks-reproducible round 5 (d68856d..a89c733) {#root}

**Commits audited:** c338a96 (remedy-plan-2-r4), a89c733 (merge). The deploy also carries 80021a4 (plan-3 r2) and 0036d80 (test fakes); only plan-2 surfaces are judged here — the plan-3 liveness change does not touch the three hook paths in `cli.py`.
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-2 surfaces):** `src/refmatrix/cli.py`, `src/refmatrix/verbs.py`, `tests/test_plan2_remedy.py`, `docs/hooks/intuition-style-hooks.md`, `workflow/plans/plan-2-hooks-reproducible.md`, `workflow/plan-of-plans.md`, `workflow/implementation_summaries/remedy-plan-2-hooks-reproducible.md`
**Deployed:** `~/refmatrix` at 0036d80 (191e510 on top is docs-only); `~/bin/rmx version -v` → 0.69.1, code `~/refmatrix/src/refmatrix`; `rmx install-hooks --check` live → "hooks in sync".
**Tests:** `workflow/review-output/pytest-bsd-plan2-r5-a89c733.log` — 41 passed in 5.18 s (test_plan2_remedy, test_hooks_reproducible, test_repo_hooks_in_sync, test_docs_hooks_target); slowest: ping-only detach 2.01 s, silent detach 1.26 s.
**Method:** every r4 closure reproduced under `.venv-eval` in a throwaway `/tmp` root against a real pid file + real unix socket (`_SilentDaemon` subclass that answers a chosen op set and stalls the rest) — script `sim_plan2_r5.py` in the session scratchpad. Live surfaces read only: `.refmatrix/cli.log` hook rows, `~/bin/rmx` timings of the recall hook command (read-only recalls), `rmx hub status`, `rmx partition list`.

rel: amends -> [[bsd-plan2-hooks-reproducible-r4-d68856d]]
rel: evidence-for -> [[plan-2-hooks-reproducible]]

## Round-4 findings: status after remediation {#status}

| # | Finding | Status | Evidence (real socket, `RMX_DETACH_WAIT_S=1` / `--timeout` as shown) |
|---|---------|--------|----------|
| #s-1 | detach bounded only on a silent socket (210 s, blank traceback) | CLOSED | silent → 1.26 s "not answering for 1.3s"; answers `ping` only → 2.01 s, ops `[ping, partition_list, ingest_gmd_start]`, "answers ping but did not accept the ingest job within 1s: timed out — catch-up skipped"; answers `ping`+`partition_list`, start stalls → 1.01 s, same message. No traceback in any state. Under the production default (env unset) the same two states cost 20.0 s and 10.0 s — bounded, loud, and inside Claude Code's 60 s; the message under-reports the first (#m-3 below). |
| #s-2 | `filed_subject_error` read by nobody | CLOSED | `verbs.save_state` result carries `filed_subject_error='topic-x: boom'` when `subject_upsert` answers `ok:false`; `rmx save-state` prints "subject filing failed: topic-x: boom — the digest landed but the subject index does not reach it" and exits 0; the MCP dispatcher returns the verb dict unfiltered (`VERBS[name].run`), so the key reaches MCP callers. |
| #m-3 | additive per-call budget | CLOSED | every op answers after 0.4 s at `--timeout 0.5` → 0.51 s wall (was 1.24 s), the second call times out inside the deadline; `subject_link` stalls at `--timeout 1` → 1.01 s; `memory_add` stalls → 1.01 s; ping-only at the shipped `--timeout 5` → 5.01 s. Doc states the deadline arithmetic. |
| #m-4 | refusal worded as timeout | CLOSED | `subject_upsert` → `ok:false "boom"` → 0.06 s, "the daemon refused the subject filing under 'topic-x': boom — `rmx focus subject` to inspect"; "still complete" absent. |
| #m-5 | hook commands unobserved | HALF-CLOSED | Stop `focus summarize --promote --timeout 5` now has three live `source=hook` rows: 21:50:11 (52 ms, exit 0), 21:50:20 (112 ms, exit 0), **22:11:25 (5037 ms, exit 1)** — the bound held under the deploy window and failed loud. PreCompact `--timeout 30`, SessionStart `ingest-gmd --detach`, and `focus context` rows are still absent (no SessionStart/PreCompact since 20:55). Carried as #m-5 below. |

## Findings {#findings}

### BULLSHIT: the hook that fires on every prompt is unbounded and holds the turn for the store — `memory recall --stdin-json` p50 20.0 s over 36 completed rows today, 19.6 s when I ran the command myself; the closure commit bounded the three hooks the findings named and left this one at the library default {#b-1}

**File:** `src/refmatrix/hooks.py:301-313` (UserPromptSubmit `rmx memory recall --stdin-json --k 5 --scope both --json`, no `--timeout`, no hook `timeout`), `:270-289` (SessionStart `rmx memory recall --session-start --k 10 --scope both --json`, same), `src/refmatrix/verbs.py:650-654` (`_call(root, "memory_recall", …, timeout=180.0)` → `daemon.call` default `retries=2` = 540 s), `:660-661` (`memory_get` per hit, `timeout=30.0`, default retries), `:323` (`hub_mod.global_call(op, args, timeout=30.0)` for `--scope both`), `src/refmatrix/cli.py:9848` (`hook_mode = bool(session_start or stdin_json)` — the CLI knows it is a hook and passes no budget).
**What:** `.refmatrix/cli.log`, `source=hook`, `exit_code=0`, argv `memory recall --stdin-json …`:

| day | n | p50 | max |
|---|---|---|---|
| 2026-07-23 | 83 | 11 ms | 121 ms |
| 2026-08-04 | 23 | 89 ms | 6.4 s |
| 2026-08-28 | 20 | 5.4 s | 28.8 s |
| 2026-09-04 | 37 | 10.7 s | 27.8 s |
| 2026-09-06 | 44 | 17.8 s | 29.8 s |
| 2026-09-14 | 36 | **20.0 s** | 24.2 s |

34 of today's 36 completed rows exceed 11 s. Independent timing with the deployed binary (read-only recall, no `RMX_INVOCATION_SOURCE`): `--scope both` 19.6 s, `--scope project` 20.6 s, `--scope global` 14.0 s, `--session-start --scope both` 6.1 s (its one live row today: 30.2 s at 18:10:26). Claude Code runs UserPromptSubmit hooks synchronously before the model sees the prompt: every prompt in this session has waited ~20 s on the store. The bound on the path is `daemon.call`'s library default — up to 540 s on `memory_recall` plus 90 s per `memory_get` hit plus 30 s on the hub — so "past the bound it fails loud" is not true of this hook in any state.
**Why it's bullshit:** Q4's invariant is the plan's own rule: "A hook may shout; it may not hold the turn for the store." The plan is now `completed` on the strength of `--timeout 5` (Stop), `--timeout 30` (PreCompact), and the detach budget (SessionStart bridge) — three of the five memory-path hooks the generator emits (`hooks.py:99-101` lists "memory recall" first among them). The two recall hooks are the ones with the highest firing rate (36 today vs 3 Stop promotes) and the highest measured cost, and they carry no bound at all. This is the third sighting of [[bsd-impressions#imp-partial-bound]] in three rounds (r3 #b-1: one of three calls; r4 #s-1: the probe and none of the calls; r5: three of five hooks) → BULLSHIT by the 3+ escalation rule I armed in r4, and a PATTERN file is filed ([[bsd-pattern-partial-bound]]). It is also rule 10 in the "scope shrunk silently" shape: the closure commit says "every call on the detach path carries the budget" and flips the status, with the per-prompt hook unmentioned. The 20 s itself is not plan-2's doing — the per-day table dates the regression to 2026-08-28..09-06 (the model-worker / rerank / bodies releases) and its root cause is ch-performance-tuner's — but the bound is plan-2's deliverable, and the reason Q4 exists is that a hook's cost is whatever the fleet makes it. My own miss: r2 recorded "at 20:06 a UserPromptSubmit memory recall took 24 s" as context for the Stop finding and filed nothing on it; r3/r4 timed only the hooks the findings named. Same shape as [[bsd-impressions#imp-cost-measured-idle]] — the number that was never re-measured was the one on the path users run.
**Evidence:** cli.log per-day p50 above; `time ~/bin/rmx memory recall --stdin-json --k 5 --scope both --json` ← `{"prompt":"daemon restart relaunch verifies the new pid"}` → real 19.63 s; `grep -n "timeout" hooks.py` → the recall entries carry none; `verbs._call` signature `timeout: float = 60.0` with no `retries` parameter (always the library's 2).
**Fix:** (1) `memory recall` hook modes take a budget: `--timeout` option (default 5 s when `--stdin-json`/`--session-start`, 60 s otherwise) threaded to `verbs.memory_recall(timeout=…)` → `_call(…, timeout=budget, retries=0)`, the per-hit `memory_get` and the hub `global_call` under the same deadline (the `_left()` helper from `_file_under_active_subject` is the template); past it the hook prints `# rmx: warning: recall skipped: daemon busy (not confirmed within 5s)` on stderr and exits 0 — never 2, which would erase the prompt. Generator emits the option; regenerate; `install-hooks --check`. ~15 lines + one `_PingOnlyDaemon` test asserting wall < budget + 1 for both hook modes. (2) File the 20 s at idle with ch-performance-tuner as its own item (the cost is in the project daemon's `memory_recall`; `--scope global` alone is 14 s, so the hub store has it too) — the bound will make it loud on every prompt until it is fixed, which is what the invariant asks for.
**Pattern match:** YES — imp-partial-bound (3rd → BULLSHIT), imp-cost-measured-idle, feedback_measure_the_path_users_run.

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
rel: contradicts -> [[bsd-impressions#imp-partial-bound]]
rel: contradicts -> [[bsd-impressions#imp-cost-measured-idle]]
rel: evidence-for -> [[bsd-pattern-partial-bound]]

### SKETCHY: the mock-registry row for the `discovery.daemon_status` patch says "the two remaining patch sites" — this remedy added two more and did not touch the row {#s-2}

**File:** `workflow/test_mock_registry.md:41` (names `test_stop_promote_bounds_subject_filing_and_is_loud`, `test_promote_timeout_message_says_not_confirmed`), `tests/test_plan2_remedy.py:430` (`test_stop_promote_never_exceeds_its_timeout_across_calls`), `:459` (`test_subject_filing_refusal_is_not_reported_as_a_timeout`) — both `monkeypatch.setattr("refmatrix.discovery.daemon_status", …)`.
**What:** Four tests patch the classifier; the registry lists two and asserts that is all of them. The new `_PingOnlyDaemon` row (`:44`) is present and correct — the omission is the sites list on the row next to it.
**Why it's sketchy:** r3 #s-4 was this exact row missing entirely; second plan-2 sighting → MEH escalated to SKETCHY by the 2+ rule. Plan 1 went 3-for-3 on registry omissions ([[bsd-impressions#imp-registry-three-strikes]]); a remedy that adds patch sites and does not `git show --stat` a registry is the signature.
**Fix:** one row edit naming the four sites; the two new ones are legitimately isolating the deadline arithmetic and the refusal wording, so no graduation is needed.

rel: contradicts -> [[claude#no-mocks]]

### MEH: the detach hook's busy message reports the last leg, not the wait — "did not accept the ingest job within 10s" after the process held the turn 20 s {#m-3}

**File:** `src/refmatrix/cli.py:8322-8325` (`_probe_budget = min(10, RMX_DETACH_WAIT_S)` for `partition_list`), `:8341-8351` (`ingest_gmd_start` at `max(1, budget)`, message says `within {budget:g}s`), `src/refmatrix/hooks.py:285` (the generated hook sets no `RMX_DETACH_WAIT_S`, so both legs default to 10 s).
**What:** Simulation, env unset, daemon answers `ping` only: wall 20.01 s, message "within 10s". The two legs are separate budgets, not one deadline — the same additive shape #m-3 in r4 fixed for the Stop path — and r3 #s-3 established that the busy message must report what the operator actually waited.
**Fix:** one `deadline` for the detach path (probe start + budget); `partition_list` and `ingest_gmd_start` each get `_left()`; message prints `waited:.1f`. 6 lines.

### MEH: `_legacy_memory_partition_exists` turns a timeout into "no legacy partition", caches the miss for the process, and says nothing — its verb twin warns {#m-4}

**File:** `src/refmatrix/cli.py:9120-9148` (`retries=0` + comment "A miss here only means 'assume the project partition'"; `except Exception: found = False`; `cached[cache_key] = found`), `src/refmatrix/verbs.py` `memory_partition` (same probe, `logging.warning("partition_list failed … using %r")` — "tolerant, but never mute").
**What:** On a busy writer the bridge ingest now routes to the project partition on a single 10 s miss with no output. Unreachable today — no live store carries a `memory-<project>` row (refmatrix: `refmatrix`, `sessions-refmatrix`, a stray `memory-viascope`; viascope: `viascope`, `sessions-viascope`) — which is why this is MEH and not a silent-failure finding. The swallow predates this commit; the remedy shortened the fuse and added the comment that normalizes it.
**Fix:** warn on stderr like the verb; do not cache a `found` produced by an exception (a second `rmx memory` command in the same process should re-probe).

### MEH: PreCompact `--timeout 30`, the SessionStart `--detach` bridge, and `focus context` are still unobserved live (carried from r4 #m-5; the Stop half is closed) {#m-5}

**File:** `.refmatrix/cli.log` (`source=hook` rows since 20:55: `focus summarize --promote --timeout 5` ×3 — the 22:11:25 row is the bound holding at 5.04 s, exit 1 — plus `focus hook`, `scan-prompt`, `memory recall --stdin-json`; no PreCompact or SessionStart rows).
**What:** The Stop entry is now proven on the live path in the busy state. The remaining three wait on a compaction or a session start; the next audit reads their rows. Cannot gate closure.

## Deferral sweep {#deferrals}

Hard: none in the plan-2 hunks (the `Phase 1/2/3` hits in `cli.py:11375-11402` are step comments in `memory list`, not deferrals). Soft: "the digest … probably lands — only the reply is lost" (r4 exemption stands); "A miss here only means 'assume the project partition'" is a behavior, not a deferral, and is filed as #m-4.

## Verdict {#verdict}

**DIRTY — 5 findings (1 BULLSHIT, 1 SKETCHY, 3 MEH).**

Round 4's five items are closed for real: each reproduced on a real socket in the state it named, the deadline holds to the tenth of a second, the refusal wording is right, the save-state error reaches CLI and MCP, and the Stop bound has now been seen holding live. The plan-2 remedies are the best-executed remedy series in this ledger.

**Does `completed` stand? No.** Q4 says a hook may not hold the turn for the store, and the hook that fires on every prompt holds it 20 s at the median, unbounded, with 36 live rows today proving it. That is the incident Q4 was written for, at twelve times the Stop hook's frequency. Revert to `in-progress` until #b-1's bound is in the generator and regenerated (or, the rule-9a alternative: the plan records a decision scoping Q4 to the write hooks AND files a concrete task with acceptance criteria for the recall-hook bound — I recommend the ~15-line fix; the decision would be more work than the code). #s-2 is a one-row edit; #m-3/#m-4 fit the same closing commit; #m-5 waits on the user.

rel: evidence-for -> [[feedback_measure_the_path_users_run]]
rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
