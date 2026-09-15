---
gmd: "0.1"
id: bsd-plan2-hooks-reproducible-r2-6cc33e9
title: "plan-2-hooks-reproducible round 2: the three BULLSHIT items are closed by render and probe; residual is a Stop hook that costs seconds, not 0.13 s, and a --check that reports false drift after --no-claude"
tags: [bsd, findings, plan-2, hooks, re-review]
severity: SKETCHY
plan: plan-2-hooks-reproducible
task: task-2.1-plan-2-hooks-reproducible, task-2.2-plan-2-hooks-reproducible, task-2.3-plan-2-hooks-reproducible
metadata:
  node_type: bsd-report
  commit_range: 03f46b8..6cc33e9
  round: 2
---

# ch-bsd findings — plan-2-hooks-reproducible re-review (03f46b8..6cc33e9) {#root}

**Commits audited:** 0d2cba5 (0.68.1 remediation), 9fbbcd6 + 65f1858 (remedy-hooks-check-stability), 6cc33e9 (wrapper paths recorded). Plan-3 (82bbc2b, 8ba4799) and the rmxgrep fix (cf3d87d) share the range and are out of this audit's scope.
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed (plan-2 surfaces):** `src/refmatrix/hooks.py`, `src/refmatrix/search_hooks.py`, `src/refmatrix/cli.py` (focus_summarize, ingest_gmd), `tests/conftest.py`, `tests/test_plan2_remedy.py`, `tests/test_docs_hooks_target.py`, `tests/test_repo_hooks_in_sync.py`, `README.md`, `docs/INTEGRATION.md`, `docs/hooks/intuition-style-hooks.md`, `.claude/rmx-hooks.json`, `workflow/test_mock_registry.md`, `workflow/bug_registry.md`
**Deployed:** `~/refmatrix` at 6cc33e9, `~/bin/rmx` imports `~/refmatrix/src/refmatrix` 0.68.1; `rmx install-hooks --check` exits 0 live. Master is one test-only commit ahead (3f88873, `tests/test_subject.py`).

rel: amends -> [[bsd-plan2-hooks-reproducible-03f46b8]]
rel: evidence-for -> [[plan-2-hooks-reproducible]]

## Round-1 findings: status after remediation {#status}

Every closure below was verified by rendering or probing in a throwaway project under `.venv-eval` (`RMX_CLAUDE_HOOKS_DIR` and `RMX_AGENT_BASHRC` pointed at tmp; no live store touched), not by reading the tests.

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| #b-1 | dead `--enforce` | CLOSED | `_claude_hook_block(project_root=proj, enforce=True)` with an empty `.claude/` renders the four enforcement entries; `enforce=None` renders zero; all four classify as rmx-managed so `--force` reaps and `--check` sees them. `test_enforce_forced_on_emits_entries_without_scripts` asserts the forced case. |
| #b-2 | prefix signature deleted `enforce-*.sh` | CLOSED | `_RMX_HOOK_SIGNATURES` names `enforce-test-to-file.sh` and `enforce-rmx-grep.sh` exactly. Probe: a seeded `enforce-my-own-policy.sh` hook and a foreign `rmx context foo` hook both survive two `install(apply=True, force=True)` passes; `statusLine` preserved. |
| #b-3 | docs dropped | CLOSED (one residual, see #s-3) | README table names `.claude/settings.json` (committed), lists all nine events, and points at `--check`; `INTEGRATION.md:95` rewritten; the intuition doc's preamble now names the generator. `test_docs_hooks_target.py` pins it. |
| #s-4 | `check()` blind spots | CLOSED | Managed entries are a Counter of `(event, matcher, full-entry JSON)`. Probe against a managed Stop entry: `timeout` key, duplicated block, trailing-space command edit, deleted entry, entry moved to another event, matcher change — all six report drift. Foreign hooks appear as `? event/matcher: cmd` without failing. The three search scripts are compared to `render_scripts(flags["wrappers"])`: an edited or missing guard script fails the check; a legacy flags file without `wrappers` still checks (falls back to the process's `wrapper_paths()`). |
| #s-5 | status flipped before gate | CLOSED | plan `status: in-progress`; task 2.1/2.2/2.3 `complete`. |
| #s-6 | Stop promote + direct store open | CLOSED as specified; new evidence in #s-1 | Q4 recorded. `focus_summarize` no-daemon branch is a `ClickException`; the `_store().add_memory` fallback is gone. `test_focus_summarize_promote_refuses_without_daemon` would fail if the fallback returned (tmp root would create a store and exit 0). Master's 3f88873 adds the same assertion against a spawned daemon. |
| #s-11 | busy ≠ absent | CLOSED (accounting residual, see #m-5) | Simulation with a live pid file + socket file and nothing listening: `daemon_status` → `busy=True`; `ingest-gmd --detach` retries for `RMX_DETACH_WAIT_S` then fails with `daemon busy pid=N … catch-up skipped; retry shortly`. Pid file without socket → `no daemon running`. Neither file → `no daemon running`. |
| #m-7 | flags only via claude path | PARTIAL, see #s-2 | Flags are now recorded on every project-scope apply, and `wrappers` is recorded so the script comparison is venv-independent (`.claude/rmx-hooks.json` carries `~/refmatrix/bin/rmxgrep`). But the `claude` flag itself is not recorded. |
| #m-8 | registry / template drift | CLOSED | Five rows added to `workflow/test_mock_registry.md` (`cli._root`, `daemon.ping`/`call`, `search_hooks.hooks_dir`, …); the catch-all count updated. Bug registry gained bug-002/003/006 for this plan. |
| #m-9 | hooks not yet run | PARTIAL (user-gated) | `focus summarize --promote` has fired from a hook four times since 20:06 (all exit 0). `ingest-gmd --detach`, `focus context --top 15` and `save-state --no-sync` still have no `source=hook` row in cli.log. Not a failure; needs a session start / resume / compaction to observe. |
| #m-10 | deploy behind | CLOSED | `~/refmatrix` at 6cc33e9 = the audited head. |

**Test isolation (conftest):** `RMX_CLAUDE_HOOKS_DIR` is set for every test; `test_repo_hooks_in_sync` deliberately unsets it to read the real `~/.claude/hooks` read-only. I traced every home-directory write reachable from `hooks.install()`: the search scripts (`hooks_dir()`, isolated), the agent bashrc (`RMX_AGENT_BASHRC`, isolated), and the user-scope claude/search paths, which only print a snippet. A `scope="user"` apply with `agent_env=True, search=True` in the probe left `~/.claude/settings.json`, `settings.local.json`, `agent-bashrc.sh` and the rewriter untouched (mtimes compared). `tests/test_search_hooks.py` carries its own `env_hooks` fixture. The global-store tests (`test_hub`, `test_global_memory`, `test_bus`) set `RMX_HOME` to tmp. No remaining test in the hook surface can write outside tmp.

**Tests:** `workflow/review-output/pytest-bsd-plan2-r2-6cc33e9.log` — 55 passed (test_plan2_remedy, test_hooks_reproducible, test_docs_hooks_target, test_repo_hooks_in_sync, test_agent_env, test_search_hooks, the executable-scripts test).

## Findings {#findings}

### SKETCHY: the Stop-hook promote's cost premise is false in production — 55 s, 15 s and 6.6 s on its first three firings, in the foreground of every turn end {#s-1}

**File:** `src/refmatrix/hooks.py` (Stop entry `rmx focus summarize --promote`, no `& disown`), `src/refmatrix/cli.py:8934` (`_memory_daemon_call` default `timeout=60.0`), `workflow/plans/plan-2-hooks-reproducible.md#q4` ("costs 0.13 s")
**What:** Q4 keeps the Stop promote on the strength of a 0.13 s measurement. That number was taken (by me, round 1) on an idle daemon. The live cli.log rows for the hook since the config went live:

| ts | source | exit | latency |
|----|--------|------|---------|
| 20:06:23 | hook | 0 | 55,024 ms |
| 20:10:28 | hook | 0 | 15,464 ms |
| 20:14:53 | hook | 0 | 6,556 ms |
| 20:20:26 | hook | 0 | 112 ms |

At 20:10:28 a git post-commit `sync --since HEAD~1` (34 s) ran concurrently; at 20:06 a UserPromptSubmit `memory recall` took 24 s and another was never completed (exit/latency null). The daemon log has no per-op timing, so the cause (writer queue behind the detached bridge or a sync, or a slow digest) is not established from logs; what is established is that the hook is foreground, its daemon call may wait up to 60 s, and Claude Code holds the turn end until it returns.
**Why it's sketchy:** The decision is recorded, which is what #s-6 asked for, but it rests on the one number the production path contradicts. This is [[feedback_measure_the_path_users_run]] in miniature: the cost of a hook is its cost while the daemon is doing what the other hooks make it do.
**Fix:** Re-decide Q4 with these numbers. Either bound the hook path (`--timeout` on `_memory_daemon_call` of a few seconds, fail loud) or run the promote off the turn like the flush (`( … ) & disown` loses loudness, so log to `rmxd.log`/cli.log instead). Effort: small; the decision is the work.
**Pattern match:** YES — [[bsd-impressions#imp-guard-vs-incident-state]] (measured/tested on the idle state); [[feedback_measure_the_path_users_run]].

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]

### SKETCHY: `--no-claude --apply` then `--check` reports 17 lines of false drift — the flag that decides the render is the one not recorded {#s-2}

**File:** `src/refmatrix/hooks.py:442-448` (`record_flags(... memory_hooks, primer, scan_prompt, search, wrappers, **hook_opts)` — no `claude`), `src/refmatrix/hooks.py` `render_managed` (always renders the claude block), `tests/test_plan2_remedy.py::test_flags_recorded_without_claude` (asserts only that the file exists)
**What:** Round-1 #m-7 asked for flags to be recorded on every project-scope apply so `--check` could describe a `--no-claude` install. The remedy did exactly the line I suggested and no more: the file is written, but `claude=False` is not in it, so `render_managed` renders the full block and `check()` emits a `+` line for every claude entry. Probe: `install(claude=False, search=True, apply=True)` → `check()` returns `(False, 17 '+' lines)`. Before the remedy the answer was "no rmx-hooks.json — run --apply"; now it is a wrong answer with the same exit code.
**Why it's sketchy:** The covering test proves the bookkeeping (file exists) and not the behaviour (check is right afterwards) — the [[bsd-impressions#imp-tests-bypass-wiring]] shape. In fairness the recommendation in round 1 was incomplete; the remedy followed it. Filed as SKETCHY, not cheap-fix BULLSHIT, for that reason.
**Fix:** Record `claude=claude` in `record_flags`; in `render_managed`, skip `_claude_hook_block` when `flags.get("claude", True)` is False; extend the test to assert `check(proj)[0] is True` after the `--no-claude` apply. Effort: three lines.
**Pattern match:** YES — 3rd sighting of a guard tested only in the fixed state.

rel: contradicts -> [[plan-2-hooks-reproducible#q5]]

### SKETCHY: the rewritten intuition doc still defers the Stop hook to a "Phase C4" that exists nowhere, while the generator now emits a Stop hook {#s-3}

**File:** `docs/hooks/intuition-style-hooks.md:29` ("`Stop` | (out of scope — Phase C4)"), `:124-131` ("Stop — auto-capture (Phase C4, deferred)… deferred to **Phase C4 (not yet shipped)**. For now, capture observations explicitly…")
**What:** This diff rewrote the doc's preamble to say "read this doc to understand each event; edit `hooks.py:_claude_hook_block` to change one". The Stop row and section it now vouches for say Stop is out of scope and deferred. Since 0.67 the generator's Stop entry runs `focus summarize --promote`, which writes a `session/digest` memory every turn — the auto-capture the section says is not shipped. `grep -rn "Phase C4\|\bC4\b" workflow/ docs/` finds no plan, task, or ADR section by that name outside this doc.
**Why it's sketchy:** Rule 9a — a deferral with no concrete scheduled task behind it, in a doc this commit touched to make accurate. The deferred feature (LLM auto-extract of the transcript) is a different thing from the shipped STM digest, so this is a stale-and-unanchored doc deferral rather than a code gap; hence SKETCHY rather than BULLSHIT.
**Fix:** Rewrite the Stop row/section to describe the generated `focus summarize --promote` entry; either drop the Phase C4 promise or file a task spec for transcript auto-extract the sentence can point to.
**Pattern match:** YES — stale deferral family from [[bsd-0661-e2e-memory-bridge]].

rel: contradicts -> [[task-2.3-plan-2-hooks-reproducible#files]]

### MEH: the promote refusal tells the operator to use `--no-promote`, which `focus summarize` does not have {#m-4}

**File:** `src/refmatrix/cli.py:1148-1150` (`… or use \`--no-promote\``), `:1104` (`@click.option("--promote", is_flag=True)`)
**What:** `focus summarize --help` has no `--no-promote`; the Stop hook is the only production caller and passes `--promote`. The message points at a flag that does not exist.
**Fix:** "… or run without `--promote`". One string.

### MEH: the busy branch of `ingest-gmd --detach` is proven only by this audit's simulation, and its wait accounting is off by ~2x {#m-5}

**File:** `src/refmatrix/cli.py:8118-8133`, `tests/` (no test references `RMX_DETACH_WAIT_S` or a busy daemon)
**What:** Each loop iteration costs one `ping` (0.5 s × 2 retries ≈ 1 s) plus `sleep(1)` but counts as 1 s, and `daemon_status` pings once more before the loop. Probe with `RMX_DETACH_WAIT_S=2` took 4.8 s wall and reported "not answering for 2s"; at the default 10 s a SessionStart hook will block roughly 22 s before the busy error. No test exercises `st["busy"]`; `test_ingest_gmd_detach_without_daemon_fails_loud` covers only the absent branch.
**Fix:** Measure the deadline with `time.monotonic()`; add a test that seeds `rmxd.pid` (own pid) + an empty `rmxd.sock` and asserts the busy message. Effort: ten lines.

### MEH: three of the four new hook commands remain unobserved from a hook {#m-6}

**File:** `.refmatrix/cli.log` (`source=hook` rows since 19:49: `focus summarize --promote` ×4; zero rows for `ingest-gmd --as-memory --detach`, `focus context --top 15`, `save-state --no-promote --no-sync`)
**What:** User-gated (session start / resume / compaction). Recorded so the next audit checks the rows, not the config. Note the two `ingest-gmd --detach` rows at 20:03/20:04 are this auditor's manual runs (`source=unknown`), not the hook.

### MEH: master is one commit ahead of the deploy tree {#m-7}

**File:** `~/refmatrix` at 6cc33e9; `master` at 3f88873 (`tests/test_subject.py` only — no `src/` change, so the fleet runs the audited code). Plan-1's fast-forward contract applies on the next deploy.

## Deferral sweep {#deferrals}

Hard: none in the plan-2 source files. Soft: `hooks.py:130,151` "best-effort" (focus-event plumbing, exempted by the loudness contract, unchanged from round 1); `docs/hooks/intuition-style-hooks.md:124-131` (#s-3). `docs/INTEGRATION.md:34` "phase 3" is a backend label, not a deferral.

## Verdict {#verdict}

**DIRTY — 7 findings (0 BULLSHIT, 3 SKETCHY, 4 MEH).**

All three round-1 BULLSHIT items are closed and each closure was reproduced by render or probe, not by reading the test. `--check` now proves what Q5 says it proves; `--force` no longer eats same-prefix user hooks; the docs name the file that is written. Nothing here blocks the next task. What keeps the plan from `completed` under its own contract is a decision (#s-1: Q4 was taken on an idle-daemon number that the first three production firings contradict by two orders of magnitude) and two small omissions (#s-2: record `claude`; #s-3: fix the Stop section the diff vouched for). #m-4/#m-5 are one-line and ten-line fixes. #m-6 waits on the user.

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
rel: evidence-for -> [[feedback_measure_the_path_users_run]]
