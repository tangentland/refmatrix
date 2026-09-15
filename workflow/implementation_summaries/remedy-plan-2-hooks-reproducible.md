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

