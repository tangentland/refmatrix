---
gmd: "0.1"
id: bsd-plan24-spec-review-cdcfbc3
title: "Plan-24 + task 24.0 pre-implementation spec review: spawn_ms holds the import (and a re-exec), the hook verbs D3 needs do not exist"
tags: [bsd, plan-24, spec-review, hooks, telemetry, mod]
severity: BULLSHIT
plan: plan-24-mod-transport
task: task-24.0-hook-cost-baseline
---

# ch-bsd findings — plan-24 / task 24.0 spec review at cdcfbc3 {#root}

**Commit:** cdcfbc3 (branch wave0-spec-reviews)
**Date:** 2026-10-20T11:19:31-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator (spec author)
**Scope:** workflow/plans/plan-24-mod-transport.md, task-24.0-hook-cost-baseline.md, the
exploration, plan-review t13-mod-gate; checked against src at HEAD and the deploy runtime.

rel: evidence-for -> [[plan-24-mod-transport]]
rel: evidence-for -> [[task-24.0-hook-cost-baseline]]

## Findings {#findings}

### BULLSHIT b1: D3 (verbs only) has no verbs for the hot hook work, and verbs resolve the session by ladder {#b1}

**File:** plan-24 tasks table; src/refmatrix/verbs.py:780-1673; task-3.4 R5 `hook` category
**What:** 24.6 moves focus hook (tool-pre/tool/input/say/session-start), scan-prompt,
recall-on-prompt, curator status --drain, sync --flush-queue and focus summarize --promote into the
mod. D3 says the per-store HTTP socket serves verbs ONLY. None of these is a verb: VERBS has 30
entries (context, query, memory*, focus, focus_note, change_subject, save_state, recall_state, bus*,
...) and task 3.4 classifies hook-invoked paths as LEGACY category `hook` = "not owed a verb";
3.7 (the plan's only verb dependency) is the `verb-it` backlog and excludes them.
**G1/G3 gap:** rmx_context (verbs.py:804), rmx_memory_recall (:939) and :1559 take no `session`
and call `resolve_event_session(root)` -> owner_lookup walks the CALLER's process ancestry. Run
in-daemon (24.2), that walks the daemon's launchd ancestry: session null every time. G3's
"STM refs from real results" needs a verb that accepts the tool name, input AND result; today
`focus hook --event tool` re-parses stdin.
**Fix:** add a task (or a named 24.2/24.4 requirement) that verbs the `hook` category:
`focus_observe(event, session, tool, input, result)`, `scan_prompt(session, prompt)`, prompt
recall, curator drain, sync flush, summarize/promote; every verb takes `session` explicitly;
the HTTP verb host requires the session from the request and never runs resolve_session_source
in-daemon (missing session = typed error, not a ladder). 24.6 depends on it.
**Pattern match:** YES (two ways to do X; verb-layer bypass, plan-3 r1).

### BULLSHIT b2: 24.0's spawn_ms contains the import, twice; import_ms is undefined for 79% of rows {#b2}

**File:** task-24.0 R1, AC-1; ~/refmatrix/.venv/bin/rmx; src/refmatrix/cli.py:14974-15043
**What:** the console-script shim is `from refmatrix.cli import cli_entry`: refmatrix/__init__
(imports Store, QueryEngine) and the 15,085-line cli.py (click, rich, handoff, query, store) load
BEFORE cli_entry's first statement. Then `_reexec_for_fork_safety` execv's the whole thing again
when OBJC_DISABLE_INITIALIZE_FORK_SAFETY is unset (it is, under Claude Code; HOOK_ENV does not set
it). execv keeps the pid, so create_time is pass 1's. Measured (deploy): `rmx version` 0.13-0.14 s;
same with the var set 0.07 s; `python -c pass` 0.01 s; `import refmatrix.cli` 0.07 s. So spawn_ms
~= 2 x (interpreter + full import); import_ms gets neither. The spec's premise is also wrong:
cli.log rows come from `log_cli_invocation` in cli_entry's finally (cli.py:15069, own t0), not
`log_query` (that writes query.log); `focus hook` (2,162 of the last 3,000 rows) never enters
log_query, so import_ms has no end point. AC-1's sitecustomize sleep runs at interpreter init
(and twice, via the re-exec), so it passes under the wrong split.
**Fix:** console-script target becomes a tiny `refmatrix/_entry.py` that stamps `time.time()`
and does the re-exec BEFORE importing refmatrix.cli, carrying pass-1's start in an env var
(`RMX_EXEC0_WALL`); fields `interp_ms` (create -> entry), `reexec_ms` (pass 1), `import_ms`
(entry -> cli_entry), `start_wall_ms` / `end_wall_ms`. AC: a delay-on-import fixture module lands
in import_ms, not interp_ms; reexec_ms > 0 on darwin without the var. Pin that the re-exec /
OBJC handling is held constant between windows (or reported apart): exporting the var in HOOK_ENV
halves every hook today without the mod, and the before/after would credit the mod.
**Pattern match:** YES (instrument measures the neighbour; bug-033 / plan-12 #b-2).

### SKETCHY s1: the blocking class is not per-entry {#s1}

- SessionStart entry 1 = backgrounded sync+primer subshell AND blocking `rmx curator status --drain`.
- `ingest-gmd --detach`: the parent pays spawn+import (96 ms p50) before it detaches: blocking,
  not 0 as R3 says.
- p20-0 entry has no HOOK_ENV: its python3 runs ~5 blocking `rmx` (ingest-gmd, memory list, memory
  get x3) logged as non-hook.
- Non-rmx hooks (enforce-test-to-file, enforce-rmx-grep, grep-rewrite-guard with
  /usr/bin/python3, adr-gate, grep-tool-teach) run on every Bash/Edit/Grep and are invisible.

**Fix:** a per-invocation prefix (`RMX_HOOK_BLOCKING=0` inside the background subshell, `1` on
--detach parents) from one helper, on every generated entry including project hooks; the report
lists the non-rmx hooks as unmeasured, with a one-time harness timing.

### SKETCHY s2: the sum overstates the wait and prompt grouping misassigns rows {#s2}

Hooks of one event run in parallel (UserPromptSubmit x3; PreToolUse Bash x4). cli.log `ts` is
1 s resolution and stamped at the END; scan-prompt p50 is 5 s, so the same prompt's focus input
and recall rows land BEFORE the scan-prompt row that "opens" it. That puts them in the previous
prompt. Overlap "from the rows' timestamps" is impossible with these fields. 62 of the last 3,000
rows are log_cli_intent rows (same pid, no latency).
**Fix:** ms start/end walls; a prompt opens at the earliest UserPromptSubmit-event row; metric =
the sum over event instances of the max blocking wall, where an instance = (session, hook_event,
start cluster); the sum is reported beside it. AC-4 fixture adds an overlapping trio and an intent
row.

### SKETCHY s3: R4's session resolver in cli_entry is blind, perturbs R6(b), and costs time off the clock {#s3}

cli_entry has no envelope (the subcommand consumed stdin). So the resolver reads the pid pointer
that the CONCURRENT input hook writes. On the first prompt after /clear or /resume it names the
old session (bug-139 class). Every unresolved row records a pointer-unresolved miss, about 72 per
prompt, which inflates the R6(b) count the report reads. It runs in the finally after the latency
is taken (proc_info 2.5 ms + verbs import 3.3 ms), so it is unmeasured blocking cost.
**Fix:** envelope-reading commands stash session_id for the row (`session_source`); the resolver
fallback does not record misses; R6(b) counts null-session rows.

### SKETCHY s4: the after window has no prompts and no mod cost {#s4}

24.6 moves scan-prompt into the mod, so the after window has no prompt-opening row. The mod's
calls write no rows, so "after" is ~0 by construction. The in-engine wait (HTTP + verb host) goes
unmeasured.
**Fix:** the 24.2 verb host writes one row per mod call (invocation=mod, hook_event, session,
prompt id, wall_ms) to the same log; prompts open on the event, not the command; after = residual
spawn + mod wait.

### SKETCHY s5: G5/G6 and hook-to-mod coexistence have no task {#s5}

- The fallback shell hooks keep `2>/dev/null || true` (G6; the project constraint).
- With the mod live, the shell hooks still fire on the same events, so injection and STM are
  doubled. 24.7's stand-down is for two mod copies (D5).
- The exploration keeps the fallback "until subagents / claude -p are known", and no task
  verifies them.
- G5's pane and its bus wake via prompt.submit are in no task (24.3 = bus HTTP, 24.5 = status
  line + toasts).

**Fix:** name each in 24.5/24.6/24.7.

### MEH m1: psutil is unneeded {#m1}

`stm._proc_info(os.getpid())[2]` already returns the kernel start time via libproc, with no
dependency. psutil is in neither venv. Drop R2 (feedback_prefer_existing_infra).

### MEH m2: stale citations {#m2}

24.0 `rel: implements -> [[exploration-claude-code-mod-transport#gate]]` (no longer a gate); the
"telemetry.py ~546 / ~559" premise (see b2).

## Verdict {#verdict}

9 findings (2 BULLSHIT, 5 SKETCHY, 2 MEH). Spec DIRTY: rewrite 24.0 R1/R3/R4/R5/R7, and add the
hook-verb + explicit-session work to plan-24 before 24.2/24.6 are specified.

rel: contradicts -> [[plan-24-mod-transport#decisions]]
