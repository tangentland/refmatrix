---
gmd: "0.1"
id: bsd-plan2-hooks-reproducible-r3-c9d75af
title: "plan-2-hooks-reproducible round 3: r2's seven items are closed on paper, but the 'bounded' Stop promote still holds the turn 180 s when a subject is active, and a busy daemon is called 'not running'"
tags: [bsd, findings, plan-2, hooks, re-review]
severity: BULLSHIT
plan: plan-2-hooks-reproducible
task: task-2.1-plan-2-hooks-reproducible, task-2.2-plan-2-hooks-reproducible, task-2.3-plan-2-hooks-reproducible
metadata:
  node_type: bsd-report
  commit_range: e6c4081..c9d75af
  round: 3
---

# ch-bsd findings — plan-2-hooks-reproducible round 3 (e6c4081..c9d75af) {#root}

**Commits audited:** 79f4d2f (remedy-plan-2-r2), 5e1a819 (merge), c9d75af (regenerated settings.json).
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-2 surfaces):** `src/refmatrix/cli.py`, `src/refmatrix/hooks.py`, `tests/test_plan2_remedy.py`, `docs/hooks/intuition-style-hooks.md`, `.claude/settings.json`, `.claude/rmx-hooks.json`, `workflow/plans/plan-2-hooks-reproducible.md`
**Deployed:** `~/refmatrix` at c9d75af == master; `~/refmatrix/.venv` imports `~/refmatrix/src/refmatrix` 0.68.1; daemon pid 87227 supervised; `rmx install-hooks --check` exits 0 live ("hooks in sync").
**Tests:** `workflow/review-output/pytest-bsd-plan2-r3-c9d75af.log` — 49 passed (test_plan2_remedy, test_hooks_reproducible, test_docs_hooks_target, test_repo_hooks_in_sync, test_search_hooks).
**Method:** every closure and every finding below was reproduced under `.venv-eval` in a throwaway root with a simulated daemon (own pid in `rmxd.pid` + a listening unix socket that either stays silent or answers `ping` and stalls everything else). No live store was touched; the live tree was read only.

rel: amends -> [[bsd-plan2-hooks-reproducible-r2-6cc33e9]]
rel: evidence-for -> [[plan-2-hooks-reproducible]]

## Round-2 findings: status after remediation {#status}

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| #s-1 | Stop promote 55 s live | PARTIAL — see #b-1, #s-2 | `_memory_daemon_call(..., timeout, retries=0)` passes through to `daemon.call` (confirmed by a call spy: `{'timeout': 5.0, 'retries': 0}`); against a daemon that answers ping and stalls `memory_add`, `--timeout 0.5` → 0.50 s wall, `--timeout 5` → 5.01 s wall, exit 1, "daemon busy … promote skipped this turn". The generator's Stop entry carries `--timeout 5`; `.claude/settings.json:55` matches; Q4 re-decided with the live numbers. The live cli.log row at 18:06:24 (180,164 ms, `TimeoutError`) is the unbounded path's true cost: 60 s × 3 attempts — so the `retries=0` passthrough is the load-bearing half of the fix, and it is real. But the command makes up to three daemon calls, and only the first is bounded (#b-1); and the pre-check `ping` still conflates busy with absent (#s-2). |
| #s-2 | `--no-claude` false drift | CLOSED | `rmx-hooks.json` records `claude`; `render_managed` returns only the search block when `claude is False`. Probe: `install(claude=False, search=True, apply=True)` → `check()` = `(True, "")`, settings carry only PreToolUse/PostToolUse; a flags file with the `claude` key removed (legacy) still checks clean. Residual for re-apply on a project that already has the block: #m-7. |
| #s-3 | "Phase C4" doc deferral | CLOSED | Stop row and section describe the shipped `focus summarize --promote --timeout 5`; "no LLM-driven auto-extract … and none is planned" removes the deferral rather than re-anchoring it. `test_intuition_doc_describes_the_shipped_stop_hook` pins it. The heading keeps its old anchor id `{#stop-auto-capture-phase-c4-deferred}` — correct GMD practice (stable ids), not a stale deferral. |
| #m-4 | refusal names `--no-promote` | CLOSED | Message now says "run `rmx focus summarize` without --promote"; test asserts `--no-promote` absent. |
| #m-5 | busy wait accounting | PARTIAL — see #s-3 | The loop is wall-clock (`time.monotonic`, `ping(timeout=0.5, retries=0)`, 0.25 s sleep) and the message reports pid + measured seconds. But the budget starts after ~6 s of unbudgeted full-cost pings, and the covering test patches both `daemon_status` and `ping`, so it measures 1.25 s where the real path costs 7.4 s. |
| #m-6 | hook commands unobserved | OPEN (user-gated) | Last `source=hook` row for the promote is 20:55:32 — after c9d75af (20:53:41) but still the old command line (no `--timeout`), because Claude Code loaded hooks at session start. No `--timeout 5` firing, no `ingest-gmd --detach`, `focus context`, or `save-state` hook row yet. Not a failure. |
| #m-7 | deploy behind | CLOSED | deploy == master == c9d75af. |

## Findings {#findings}

### BULLSHIT: the "bounded" Stop promote holds the turn for 180 s when the session has an active subject — the bound covers one of the command's three daemon calls {#b-1}

**File:** `src/refmatrix/cli.py:1167` (`_file_under_active_subject(s, eid)` after the bounded promote), `:1401-1408` (`_subject_upsert` → `_memory_daemon_call("subject_upsert", …)` with defaults `timeout=60.0, retries=2`), `:1411-1422` (`_subject_link`, same defaults, wrapped in `except Exception: pass`), `tests/test_plan2_remedy.py::test_stop_promote_is_bounded_and_fails_loud_when_busy`
**What:** Q4 was re-decided on the invariant "a hook may shout; it may not hold the turn for the store", and the remedy passes `--timeout 5, retries=0` to the `memory_add` call. The same command then files the digest under the active subject through two more daemon calls that keep the 60 s × 3 defaults. Reproduced with a simulated daemon that answers `ping` and `memory_add` and stalls `subject_upsert`, after `Stm.set_subject("plan two")`:

| state | `--timeout 5` wall | exit | output |
|-------|-------------------|------|--------|
| no subject, `memory_add` stalls | 5.01 s | 1 | `daemon busy … promote skipped this turn` |
| subject active, `subject_upsert` stalls | **180.2 s** | 1 | `promoted focus_summary_s1 (id=42)` then an uncaught `TimeoutError` |

Call spy: `[('memory_add', {'timeout': 5.0, 'retries': 0}), ('subject_upsert', {'timeout': 60.0, 'retries': 2})]`. Subjects are a shipped, used feature (`focus change-subject`; the live STM has `2739f535….subject.json`). In a subject-bound session the Stop hook's cost on a busy writer is the unbounded 180 s that the 18:06:24 live row already measured, and Claude Code's own 60 s hook limit kills it rather than rmx failing loud. `_subject_link` additionally swallows its timeout silently.
**Why it's bullshit:** Rule 10, cheap fix: the remedy bounded the line the round-2 finding quoted, not the invariant Q4 was re-decided on. The covering test patches `ping → True` and `call → raise`, so the second call can never be reached and the test cannot fail for this. This is [[bsd-impressions#imp-guard-vs-incident-state]] a third time in three plans and [[bsd-impressions#imp-cost-measured-idle]] a second time: the bound was proved in the one state the test constructs.
**Fix:** Thread `timeout`/`retries` into `_file_under_active_subject` → `_subject_upsert` / `_subject_link` (or give `_memory_daemon_call` a module-level hook budget the Stop path sets once); make the subject-filing failure a loud `ClickException` like the promote's, not `except: pass`; extend the test with a subject set and a `call` that raises only for `subject_upsert`, asserting wall < timeout × 2. Effort: ~10 lines. The invariant is then true for the command, not the line.
**Pattern match:** YES — guard-for-tested-state (3rd plan), cost-measured-idle (2nd), rule 10.

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
rel: contradicts -> [[feedback_measure_the_path_users_run]]

### SKETCHY: on a daemon that is alive but not answering ping, the Stop hook says "daemon not running — start it" — the busy≠absent fix from r2 was not applied to the sibling function edited in the same diff {#s-2}

**File:** `src/refmatrix/cli.py:1141` (`if daemon_mod.ping(root):` with defaults — 0.5 s × 3 + backoff), `:1156-1162` (the else branch: "daemon not running for … start it (`rmx daemon start`)")
**What:** Simulation with a live pid file and a listening socket that never replies (the state `daemon.ping`'s own docstring describes: index rebuild at startup, writer holding the lock, the cliquet "stale pid (socket unreachable)" incident): `focus summarize --promote --timeout 5` → 1.97 s wall, exit 1, "daemon not running … start it". The `--timeout` bound never engages because the branch it guards is not taken; the operator is told to start a daemon that is running. `ingest-gmd --detach` was fixed for exactly this in r2 (#s-11) by consulting `discovery.daemon_status`; `focus summarize` — in the same commit, ten lines from the new timeout code — still uses bare `ping`. Mitigation in fairness: `_op_ping` is served from the cli pool by a dispatcher thread, so this state is rarer than under the old single-threaded accept loop; it is not gone.
**Fix:** Replace the bare `ping` gate with `daemon_status(root)`: `up` → bounded call; `busy` → "daemon busy pid=N — promote skipped this turn"; else → "not running". Same shape as `ingest-gmd --detach`. Effort: six lines.
**Pattern match:** YES — [[bsd-impressions#imp-verbatim-fix]] (the fix landed where the finding pointed and nowhere else).

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]

### SKETCHY: `ingest-gmd --detach` on a busy daemon costs 7.4 s for a 1 s budget and reports 1.5 s; the test patches the two functions that carry the other 6 s (escalated from r2 #m-5) {#s-3}

**File:** `src/refmatrix/cli.py:8164` (`if (detach or progress) and not daemon_mod.ping(root):` — full-cost ping), `:8171` (`_disc.daemon_status(root)` — pings again at full cost), `:8172-8183` (the budgeted loop), `tests/test_plan2_remedy.py::test_detach_busy_branch_waits_wall_clock_and_names_the_pid`
**What:** Timed with the real `daemon_status` and real `ping` against the silent-socket simulation, `RMX_DETACH_WAIT_S=1`:

| step | cost |
|------|------|
| full-cost `ping` (defaults) ×2 before `daemon_status` | 1.96 s + 1.97 s |
| `daemon_status` (its own full-cost `ping`) | 1.97 s |
| budgeted loop (`ping` 0.5 s ×2 + sleeps) | 1.5 s |
| **wall** | **7.42 s** — message says "not answering for 1.5s" |

At the default 10 s budget the SessionStart bridge hook blocks ~16 s (was ~22 s in r2). The loop accounting #m-5 asked for is now honest about the loop; the command is not honest about itself. The test replaces `daemon_status` with a dict and `ping` with `lambda: False` and asserts `elapsed < 2.5` — it measures 1.25 s. To the question "is patching `discovery.daemon_status` the right boundary": no. The patched boundary is exactly the boundary that hides the cost. The pid-file + socket simulation exercises the real classifier and the real ping and is what surfaced both this and #s-2; run it with `RMX_DETACH_WAIT_S=0.5` and mark it slow (~4 s).
**Fix:** Use `daemon_status` once (drop the gate ping at 8164 or give it `timeout=0.5, retries=0`), start the monotonic clock before `daemon_status`, report the total. Replace the patched test with the simulation. Effort: ten lines.
**Pattern match:** YES — 2nd sighting of #m-5's shape → SKETCHY per escalation; [[bsd-impressions#imp-mock-the-sut]].

rel: contradicts -> [[bsd-impressions#imp-mock-the-sut]]

### SKETCHY: `discovery.daemon_status` monkeypatch is not in the mock registry {#s-4}

**File:** `tests/test_plan2_remedy.py:170` (`monkeypatch.setattr("refmatrix.discovery.daemon_status", …)`), `workflow/test_mock_registry.md` (rows 29-31 cover `daemon.call/ping`, `hub._daemon_identity`, `cli._root`; no `daemon_status` row)
**What:** New fake of a production classifier without a registry entry (rule 3). The `daemon.call` fake in `test_stop_promote_is_bounded…` is covered by row 29, which already lists this file.
**Fix:** One row; graduation plan = the simulation in #s-3, after which the patch can go.

### MEH: the PreCompact promote is the unbounded path — 60 s × 3 = 180 s, and the harness kills it at 60 s instead of rmx failing loud {#m-5}

**File:** `.claude/settings.json:172` (`rmx focus summarize --promote`, no `--timeout`), `src/refmatrix/hooks.py` PreCompact block
**What:** The Stop doc and Q4 designate PreCompact as the catch-up, so a longer budget is intended. But "longer" is currently the default the 18:06:24 live row measured at 180,164 ms, and Claude Code's 60 s hook limit ends it silently. Give it an explicit bound (e.g. `--timeout 30`) so the failure mode is rmx's loud message, not a harness kill.

### MEH: "promote skipped this turn" is not what happens — the daemon runs the write; only the reply is lost {#m-6}

**File:** `src/refmatrix/cli.py:1146-1149`, `src/refmatrix/daemon.py:2376-2400` (`_handle` reads the request, blocks on the future, `sendall` to a closed peer is caught)
**What:** By the time the client times out, the request is in the dispatcher's hands; `memory_add` runs to completion and the digest lands (upserted by name, so no duplicate). The message tells the operator the promote was skipped. Say "not confirmed within Ns; the daemon may still complete it". One string.

### MEH: `--no-claude --apply` on a project that already carries the rmx block strands the block — `--check` reports 17 `-` lines and `--force` cannot clear them {#m-7}

**File:** `src/refmatrix/hooks.py:504-513` (`render_managed` claude-False branch), `install()` (claude path skipped entirely when `claude=False`, no reaping)
**What:** Probe: full apply, then `install(claude=False, search=True, apply=True, force=True)` → `check()` = False with 17 installed-only lines; the Stop entry remains. `check()` is honest here (the entries are unexplained by the recorded flags), but the tool that wrote them offers no route back to clean short of hand-editing. Fresh-project `--no-claude` (the r2 scenario) is clean. Either reap rmx-managed entries when `claude=False` and `force`, or say so in the check output.

### MEH: the four hook commands are still unobserved under the regenerated config {#m-8}

**File:** `.refmatrix/cli.log` (`source=hook` rows: `focus summarize --promote` ×9 since 20:06, all the pre-`--timeout` command line; zero rows for `ingest-gmd --as-memory --detach`, `focus context --top 15`, `save-state --no-promote --no-sync`)
**What:** User-gated on a Claude Code restart. Next audit checks for a `--timeout 5` row and its latency under load, not the config.

## Deferral sweep {#deferrals}

Hard: none in the changed files (`Phase C`/`Phase C2` hits in `cli.py` are ADR-0001 phase labels on shipped code, not deferrals). Soft: none added; the r2 "Phase C4" deferral is removed rather than re-anchored. `hooks.py:130,151` "best-effort" unchanged (exempted, r1).

## Verdict {#verdict}

**DIRTY — 8 findings (1 BULLSHIT, 3 SKETCHY, 4 MEH).**

Round 2's seven items are each closed as literally stated, and the parts that are real are real: `retries=0` reaches `daemon.call`, the 5 s bound holds for the `memory_add` call, `--no-claude` checks clean on a fresh project, the doc no longer promises Phase C4, the refusal names a real action, the loop is wall-clock. What blocks is that the fix was scoped to the quoted line: the Stop hook is bounded in the one state the test builds and holds the turn 180 s with a subject active (#b-1), and calls a busy daemon "not running" (#s-2) — both reproduced with a simulated daemon, neither reachable by the shipped tests. #s-3 is #m-5 back for the same reason. Fix #b-1/#s-2 together (they share the same ten lines), replace the patched tests with the pid+socket simulation, and this closes.

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
rel: evidence-for -> [[feedback_measure_the_path_users_run]]
