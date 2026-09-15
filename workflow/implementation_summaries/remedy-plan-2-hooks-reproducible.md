---
gmd: "0.1"
id: impl-remedy-plan-2-hooks-reproducible
title: "Plan-2 remediation after ch-bsd bsd-plan2 (03f46b8)"
tags: [implementation-summary, plan-2, remediation]
metadata:
  node_type: implementation-summary
  plan: plan-2-hooks-reproducible
---

# Plan-2 remediation {#root}

rel: implements -> [[plan-2-hooks-reproducible]]
rel: evidence-for -> [[bsd-plan2-hooks-reproducible-03f46b8]]

| Finding | Fix |
|---------|-----|
| #b-1 dead `--enforce` | `want()` returns True whenever `enforce is True`; test renders with no scripts on disk |
| #b-2 prefix signature deletes user hooks | `_RMX_HOOK_SIGNATURES` names the two exact scripts; test seeds `enforce-my-own-policy.sh` and proves it survives `--force` |
| #b-3 docs dropped | README hooks table (nine events, settings.json, `--check`), `docs/INTEGRATION.md`, `docs/hooks/intuition-style-hooks.md`; `tests/test_docs_hooks_target.py` |
| #s-4 check() blind spots | multiset of full entry JSON (duplicates, extra keys), foreign hooks listed as `?` lines, search scripts compared to `render_scripts()` |
| #s-5 status before gate | plan back to `in-progress`; task specs `complete` |
| #s-6 Stop promote | decision Q4 recorded; `focus summarize --promote` refuses loudly with the daemon down |
| #s-11 busy ≠ absent | `ingest-gmd --detach` distinguishes busy (retries `RMX_DETACH_WAIT_S`, busy-specific message) from absent |
| #m-7 flags only via claude path | recorded on every project-scope `--apply` |
| #m-8 registry / template drift | mock registry rows; enforcement command strings documented as mirroring cat-herder `.claude/settings.json` |
| #m-9 hooks not yet run | requires a Claude Code restart (user action) |

Also: the `set -o #` chain (rmxgrep piped-stdin rule, function-not-alias bashrc) shipped in cf3d87d.

## Round 3 (bsd-plan2-r3, c9d75af) {#round-3}

rel: evidence-for -> [[bsd-plan2-hooks-reproducible-r3-c9d75af]]

| Finding | Fix |
|---------|-----|
| #b-1 subject filing unbounded (180 s with a subject) | `_file_under_active_subject(…, timeout, retries, daemon_up)` → `_subject_upsert` / `_subject_link` take the budget and no longer re-ping; a failure is a loud ClickException ("subject filing … not confirmed within Ns"); save-state surfaces `filed_subject_error` instead of `except: pass` |
| #s-2 busy reported as "not running" | `focus summarize --promote` classifies with ONE `discovery.daemon_status(root, retries=0)`: up → bounded call; busy → `daemon busy pid=N … not confirmed this turn`; absent → refuse |
| #s-3 detach costs 7.4 s for a 1 s budget | one cheap probe, the wait measured from it, message reports the real wall; the hidden 2 s full-cost ping in `_memory_partition_default` → `_legacy_memory_partition_exists` now reuses the classification (`daemon_up`); `daemon_status(timeout, retries)` |
| #s-4 daemon_status patch unregistered | registry rows (`_SilentDaemon`, `discovery.daemon_status`); the detach test graduated to the real silent-socket simulation (graduation log) |
| #m-5 PreCompact promote unbounded | `--timeout 30` in the generator; doc |
| #m-6 "skipped" is not what happens | "promote not confirmed within Ns; the daemon may still complete it" |
| #m-7 `--no-claude --apply` strands the block | `install()` reaps rmx entries from settings.json when `claude=False` (`_reap_claude_hooks`); `--check` clean afterwards |
| #m-8 hook commands unobserved | still user-gated on a Claude Code restart; the regenerated `.claude/settings.json` carries `--timeout 5` (Stop) and `--timeout 30` (PreCompact) |

TDD: RED `workflow/review-output/pytest-plan2-r3-red.log` (7 failed), GREEN `pytest-plan2-r3-green.log` (118 passed across hook/subject/save-state/ingest suites). The silent-daemon tests are timed against a real socket: Stop promote 2.5 s max, detach 3.0 s max for a 1 s budget (was 3.2 s before the hidden ping was found; 7.4 s in the audit).

## Round 4 (bsd-plan2-r4, d68856d) {#round-4}

rel: evidence-for -> [[bsd-plan2-hooks-reproducible-r4-d68856d]]

| Finding | Fix |
|---------|-----|
| #s-1 detach bounded only on a silent socket | `partition_list` runs with `retries=0` and a timeout capped by the hook budget (`_memory_partition_default(timeout=…)`); `ingest_gmd_start` runs with `timeout=budget, retries=0` and a stall is the same loud `daemon busy pid=N … catch-up skipped` message; `_PingOnlyDaemon` (answers ping, stalls every other op) times it: < 4 s for a 1 s budget (was 210 s / blank traceback) |
| #s-2 `filed_subject_error` read by nothing | `verbs.save_state` carries it; the CLI prints `subject filing failed: …`; test drives a refusing `subject_upsert` through the verb and the CLI |
| #m-3 additive per-call budgets | `focus summarize --promote` computes one deadline; `_file_under_active_subject(deadline=…)` gives each subject call only what is left; doc says so |
| #m-4 refusal reported as a timeout | timeout family → "not confirmed within Ns; the daemon may still complete it"; any other error (an `ok:false` reply) → "the daemon refused the subject filing: …" |
| #m-5 hooks unobserved | still user-gated on a Claude Code restart |

TDD: RED `workflow/review-output/pytest-plan2-r4-red.log` (4 failed, 211 s — the unbounded detach stall is in the timing), GREEN `pytest-plan2-r4-green.log` (114 passed). Plan status → `completed` in this commit per the r4 verdict ("may flip once the two SKETCHY items are fixed in the closing commit").

## Round 5 (bsd-plan2-r5, a89c733) {#round-5}

rel: evidence-for -> [[bsd-plan2-hooks-reproducible-r5-a89c733]]

| Finding | Fix |
|---------|-----|
| #b-1 the per-prompt recall hook was unbounded (p50 20 s live) | `verbs.memory_recall(timeout=)` is ONE deadline over the partition probe (`memory_partition(timeout=)`, retries=0), the recall / recent / subject op, every per-hit `memory_get`, the global store and the context bundles (`_call(retries=)`); past it a typed `VerbBusyError("recall not confirmed within Ns")`. `rmx memory recall --timeout` (None → 5 s in `--stdin-json`/`--session-start`, 60 s otherwise) threads the same budget through the CLI's dense path (partition pinned once under the budget, `memory_recall`/`memory_get` with retries=0) and the memory group's startup partition probe (`_memory_intent(partition_timeout=)`); in the hook modes a busy daemon past the budget is `# rmx: warning: recall skipped: daemon busy …` on stderr + `[]` + exit 0 — never exit 2. The generator emits `--timeout 5` (UserPromptSubmit) and `--timeout 10` (SessionStart); `_PingOnlyDaemon` times both hook modes at < 2.5 s for a 1 s budget |
| #s-2 registry row named two of four sites | row lists all five `daemon_status` patch sites |
| #m-3 detach budgets additive, message named one leg | one deadline from the first probe (`_detach_left`) over the legacy-partition probe and `ingest_gmd_start`; the message reports `waited N.Ns of a Bs budget` |
| #m-4 legacy-partition probe cached a timeout silently | a failed probe warns on stderr and is NOT cached; the next command re-probes |
| #m-5 hooks unobserved | user-gated |

Plan-2 status back to `in-progress` (plan file + plan-of-plans) until ch-bsd r6 is CLEAN. TDD: RED `workflow/review-output/pytest-plan2-r5-red.log` (5 failed), GREEN `pytest-plan2-r5-green.log` (163 passed across hook, recall, parity, MCP, subject and migrated-verb suites). Mutations `pytest-plan2-r5-mutations.log`: (A) the generator without the budgets fails the generator test; (B) a deadline that never raises fails the verb deadline test and the bounded-hook-modes test.

