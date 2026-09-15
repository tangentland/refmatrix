---
gmd: "0.1"
id: bsd-plan2-hooks-reproducible-r4-d68856d
title: "plan-2-hooks-reproducible round 4: r3's eight items are closed and reproduced against a real stalled socket; the SessionStart bridge hook is the next partial bound (30 s behind the writer lock, 210 s worst), and save-state's new subject-filing error is written and never read"
tags: [bsd, findings, plan-2, hooks, re-review]
severity: SKETCHY
plan: plan-2-hooks-reproducible
task: task-2.1-plan-2-hooks-reproducible, task-2.2-plan-2-hooks-reproducible, task-2.3-plan-2-hooks-reproducible
metadata:
  node_type: bsd-report
  commit_range: c9d75af..d68856d
  round: 4
---

# ch-bsd findings — plan-2-hooks-reproducible round 4 (c9d75af..d68856d) {#root}

**Commits audited:** ba8a9e2 (remedy-plan-2-r3), b26b684 (merge), d68856d (regenerated settings.json). The range also carries the plan-1 r3 and plan-3 remedies (851ff17, 3cf5499) — audited in their own rounds; only plan-2 surfaces are judged here.
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-2 surfaces):** `src/refmatrix/cli.py`, `src/refmatrix/discovery.py`, `src/refmatrix/handoff.py`, `src/refmatrix/hooks.py`, `tests/test_plan2_remedy.py`, `docs/hooks/intuition-style-hooks.md`, `workflow/test_mock_registry.md`, `.claude/settings.json`, `.claude/rmx-hooks.json`
**Deployed:** `~/refmatrix` at d68856d == master; `~/bin/rmx version -v` → 0.69.0, code `~/refmatrix/src/refmatrix`, editable target `~/refmatrix/src`; `rmx install-hooks --check` live → "hooks in sync"; `.claude/settings.json:55` Stop `--timeout 5`, `:172` PreCompact `--timeout 30`.
**Tests:** `workflow/review-output/pytest-bsd-plan2-r4-d68856d.log` — 37 passed in 2.4 s (test_plan2_remedy, test_hooks_reproducible, test_repo_hooks_in_sync, test_docs_hooks_target); slowest: detach-on-silent-daemon 1.27 s, Stop-busy 0.50 s, daemon_status budget 0.50 s.
**Method:** every closure below was reproduced under `.venv-eval` in a throwaway `/tmp` root with a simulated daemon (own pid in `rmxd.pid` + a listening unix socket) in three states: silent; answers `ping` and stalls a chosen op; answers every op after 0.4 s. No live store was touched; live surfaces were read only.

rel: amends -> [[bsd-plan2-hooks-reproducible-r3-c9d75af]]
rel: evidence-for -> [[plan-2-hooks-reproducible]]

## Round-3 findings: status after remediation {#status}

| # | Finding | Status | Evidence (simulation, `--timeout 0.5`) |
|---|---------|--------|----------|
| #b-1 | subject filing unbounded (180 s with a subject) | CLOSED | subject set, `subject_upsert` stalls → 0.51 s, exit 1, "promoted id=42 but subject filing under 'topic-x' not confirmed within 0.5s"; `subject_link` stalls → 0.51 s, same shape; ops seen `[ping, memory_add, subject_upsert(, subject_link)]` — no re-ping between them. The test's call spy asserts every call carries `(0.5, 0)` and would fail if the kwargs were dropped. Residual: the budget is per call, not per command (#m-3). |
| #s-2 | busy reported as "not running" | CLOSED | silent socket + live pid → 0.51 s, "daemon busy pid=N … not confirmed this turn"; "not running"/"daemon start" absent. One `daemon_status(retries=0)` probe; `focus summarize` has no bare `ping` left. |
| #s-3 | detach costs 7.4 s for a 1 s budget | CLOSED for the state it named | silent socket, `RMX_DETACH_WAIT_S=1` → 1.27 s wall, message "not answering for 1.3s" (matches wall). The test is the real pid+socket simulation, unpatched. The other daemon state is #s-1. |
| #s-4 | `daemon_status` patch unregistered | CLOSED | registry rows for `_SilentDaemon` and `discovery.daemon_status` (names the two remaining patch sites); graduation-log row for the detach test. |
| #m-5 | PreCompact promote unbounded | CLOSED | generator emits `--timeout 30`; `.claude/settings.json:172` and `rmx-hooks.json` regenerated in d68856d; live check in sync. |
| #m-6 | "skipped" wording | CLOSED | "promote not confirmed within 0.5s (timed out); the daemon may still complete it". |
| #m-7 | `--no-claude --apply` strands the block | CLOSED | probe: full apply (19 managed entries) → `install(claude=False, search=True, apply=True)` → only the 2 search entries remain, `check()` clean, a user `echo mine` Stop hook survives; `search=False` → zero managed, clean; dry run prints the reap line and leaves the file byte-identical. |
| #m-8 | hook commands unobserved | OPEN (user-gated) | last `source=hook` promote row is still 20:55:32 (pre-`--timeout` argv); no `--timeout 5`, `--timeout 30`, `--detach`, `focus context`, or `save-state` hook rows. Claude Code has not been restarted. Carried as #m-5 below. |

## Findings {#findings}

### SKETCHY: the SessionStart bridge hook is bounded only when the daemon is silent — when it answers `ping` and the writer holds the store lock, `partition_list` retries for 30 s, and a saturated bg pool makes it 210 s with a blank traceback {#s-1}

**File:** `src/refmatrix/cli.py:9034-9036` (`_legacy_memory_partition_exists`: `daemon_mod.call(root, "partition_list", {}, timeout=10.0)` — default `retries=2`), `:8304-8306` (`daemon_mod.call(root, "ingest_gmd_start", op_args, timeout=60.0)` — default `retries=2`, no `except`), `src/refmatrix/daemon.py:3377` (`_op_partition_list` takes `d._store_lock`), `:2547` (`ingest_gmd_start` is not in `CLI_OPS` → bg pool)
**What:** The remedy found the hidden full-cost `ping` under `_memory_partition_default` and threaded `daemon_up` past it. Directly under that ping is a `partition_list` RPC that takes the writer lock on the daemon side and keeps the library default of two retries; after it, the detach start call keeps 60 s × 3. Measured against the simulation with `RMX_DETACH_WAIT_S=1`:

| daemon state | wall | exit | output |
|---|---|---|---|
| silent (the state #s-3 named) | 1.27 s | 1 | "busy pid=N … not answering for 1.3s" |
| answers `ping`, everything else stalls | **210.3 s** | 1 | *(blank — uncaught `TimeoutError`)* |
| answers `ping` + `partition_list`, start op stalls | 180.2 s | 1 | *(blank)* |

Ops seen in state 2: `ping, partition_list ×3, ingest_gmd_start ×3`. The realistic production leg is the first 30 s: `_op_partition_list` blocks on `_store_lock` whenever the bridge ingest or a post-commit sync holds the writer — the same state that produced the 55 s / 15 s live Stop rows. The 180 s leg needs the 12-worker bg pool saturated, which is rarer but is exactly the "fleet has been busy" condition [[bsd-impressions#imp-cost-measured-idle]] warns about. In both legs the hook ends in a traceback, not the loud busy message; the "one cheap probe" now bounds the classification and nothing after it.
**Why it's sketchy:** Q4's invariant ("a hook may not hold the turn for the store") is the plan's own rule and applies to every hook the generator emits, not to the Stop entry alone. This is the second sighting of [[bsd-impressions#imp-partial-bound]] in two rounds (r3 #b-1: the Stop bound covered one of three calls; r4: the detach bound covers the probe and none of the calls) → SKETCHY by the 2+ escalation; a third sighting is BULLSHIT. Rule 10 in shape: the remedy edited the line above the 30 s call.
**Fix:** `retries=0` on the `partition_list` call (or `timeout=min(10, budget)`); give `ingest_gmd_start` `timeout=budget, retries=0`; catch `(TimeoutError, socket.timeout, OSError)` around both and raise the same "daemon busy pid=N … catch-up skipped" ClickException the silent branch already has. Extend the simulation test with a `ping`-answering socket that stalls `partition_list` and assert wall < budget + 1. Effort: ~8 lines.
**Pattern match:** YES — imp-partial-bound (2nd), imp-cost-measured-idle.

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
rel: contradicts -> [[bsd-impressions#imp-partial-bound]]

### SKETCHY: save-state's new `filed_subject_error` is written by `finalize_save_state` and read by nothing — the CLI prints `filed_subject` only, and the verb drops the key before MCP sees it {#s-2}

**File:** `src/refmatrix/handoff.py:428-429` (writes `out["filed_subject_error"]`), `src/refmatrix/verbs.py:717-721` (`save_state` copies `lint`, `filed_subject`, `sync` — not the error), `src/refmatrix/cli.py:10842-10844` (prints only when `fin.get("filed_subject")`), `src/refmatrix/cli.py:1459` (`_subject_link` docstring: "save-state: `filed_subject_error` in its result")
**What:** The commit message says "save-state: subject-filing failure surfaces as filed_subject_error". Grep for readers: none in `src/`. `verbs.save_state` is the ONE implementation both CLI and MCP go through and it rebuilds its result from named keys; the new key is not among them. A stalled or failed subject filing on `rmx save-state` therefore renders exactly as it did under `except: pass` — the handoff is "promoted", the subject index silently does not reach it, and the operator sees nothing. The invariant the same commit established for the Stop path ("a failure is loud … the operator must know the subject index does not reach it") is not true for save-state.
**Why it's sketchy:** Second sighting of [[bsd-impressions#imp-unread-diagnostic-field]] (plan-1 r3: `identity_error` written by two producers, read by none) → SKETCHY by escalation. On a memory path, an error key nobody reads is a silent failure with extra steps (CLAUDE.md no-silent-failures). Not on the hook path (`save-state --no-promote --no-sync` promotes nothing, so it never files), which is why it is not BULLSHIT.
**Fix:** `res["filed_subject_error"] = fin.get("filed_subject_error")` in `verbs.save_state`; in the CLI, `elif res.get("filed_subject_error"): console.print("[yellow]subject filing failed[/] …")`; a test that stalls `subject_upsert` (the `_SilentDaemon` after a real promote, or the call spy) and asserts the string is in `rmx save-state` output and in the MCP result. Effort: ~4 lines + one test.
**Pattern match:** YES — imp-unread-diagnostic-field (2nd), imp-silent-memory.

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[bsd-impressions#imp-unread-diagnostic-field]]

### MEH: the Stop promote's budget is additive per call — worst case is probe + 3 × `--timeout`, not `--timeout`; the doc says "the bound covers the whole hook path" {#m-3}

**File:** `src/refmatrix/cli.py:1150-1188` (one probe at 0.5 s, then `memory_add`, `subject_upsert`, `subject_link` each with the full `timeout`), `docs/hooks/intuition-style-hooks.md:132-134`
**What:** Simulation, every op answering after 0.4 s at `--timeout 0.5` → 1.24 s wall, exit 0. Under the shipped `--timeout 5` with a subject set, a daemon that answers each call just inside the bound holds the turn up to 15.5 s; a daemon that stalls only `subject_link` holds it ~10 s before the loud failure. Both are under Claude Code's 60 s and far under the 180 s r3 measured, so the invariant is materially met — but "`--timeout 5` bounds the daemon write … the bound covers the whole hook path" reads as a 5 s command bound, and the per-call arithmetic is nowhere.
**Fix:** either a deadline (`remaining = deadline - monotonic()` passed to each call, so the command never exceeds `--timeout`), or state the arithmetic in the option help and the doc. Effort: 5 lines either way.

### MEH: a daemon `ok: false` reply on subject filing is reported as "not confirmed within 0.5s (boom)" — the message assumes a timeout {#m-4}

**File:** `src/refmatrix/cli.py:1212-1217`
**What:** Simulation: `subject_upsert` answers `{"ok": false, "error": "boom"}` in 0.01 s → "promoted id=42 but subject filing under 'topic-x' not confirmed within 0.5s (boom); the daemon may still complete it". The daemon refused; it will not "still complete it". Branch on the exception type (`TimeoutError`/`socket.timeout`/`OSError` → not-confirmed wording; `RuntimeError` → "subject filing failed: boom"). One `isinstance`.

### MEH: the five regenerated hook commands are still unobserved under the running Claude Code session (carried from r3 #m-8) {#m-5}

**File:** `.refmatrix/cli.log` (`source=hook` rows since 20:55: `focus hook --event tool/tool-pre/input/say` only; the last promote row is 20:55:32 with the pre-`--timeout` argv)
**What:** User-gated on a Claude Code restart; the config is right on disk and in sync live. The next audit reads a `--timeout 5` row's latency under load, a `--timeout 30` PreCompact row, and an `ingest-gmd --as-memory --detach` SessionStart row — the live version of #s-1.

## Deferral sweep {#deferrals}

Hard: none in the plan-2 hunks. Soft: one hit, `cli.py` comment "the digest (upserted by name) probably lands — only the reply is lost" — a factual hedge about a race the code cannot observe, not deferred work; exempt. `_subject_link`'s "Best-effort" docstring (r1 exemption) is removed by this diff.

## Verdict {#verdict}

**DIRTY — 5 findings (0 BULLSHIT, 2 SKETCHY, 3 MEH).**

Round 3's eight items are closed, and closed for real: each was reproduced against a live pid + real socket in the state the finding named, the tests that cover them are the simulation rather than patches of the classifier, the registry and the deploy match the summary, and the plan status stayed honest (`in-progress`, tasks `complete`). What remains is the same shape one hook over: the SessionStart bridge is bounded in the silent state and not behind the writer lock (#s-1), and the save-state error key added to replace `except: pass` has no reader (#s-2). Neither is BULLSHIT by the severity table and neither is on the Stop path Q4 named.

**May the plan flip to `completed`?** Yes — no BULLSHIT finding blocks it. The two SKETCHY items need either the ~12 lines named above or a written justification in the plan; my recommendation is the fix in the closing commit, since #s-1 is the third round in which a hook's bound stopped one call short and the next sighting is BULLSHIT by rule. #m-5 cannot gate closure (it waits on the user).

rel: evidence-for -> [[feedback_measure_the_path_users_run]]
rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
