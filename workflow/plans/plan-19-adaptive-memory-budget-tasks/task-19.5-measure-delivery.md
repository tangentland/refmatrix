---
gmd: "0.1"
id: task-19.5-measure-delivery
title: "Task 19.5: probe the harness's delivery limit per hook and per event, decide PreCompact, and measure what reaches the agent per channel"
tags: [task, memory, measurement, hooks, budget]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 19.5: measure delivery, not production {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: R1 (the probe) depends on nothing and runs FIRST: it sets 19.1's default and decides
> PreCompact (d5d). R2/R3 run after 19.1–19.3 and 21.1 (the recall-event schema), in 23.0's
> sandbox.

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: specified-by -> [[bsd-plan19-spec-review-3104a81]]

## Why {#why}

Today's sizes measure what the hooks PRODUCE. What matters is what the agent SEES. The ~10k
whole-delivery limit is a user-stated figure that matches the behaviour seen (16 KB and 26 KB
outputs arrived as 2 KB previews), but it has not been probed directly, nor whether it applies per
hook or to an event's combined output. UserPromptSubmit runs scan-prompt (up to 2,000 tokens), the
focus hook and the recall IN PARALLEL (`hooks.py:263-265`), so a per-event cap would make a 9,500
recall budget overflow on every prompt. And the documented hook contract adds stdout to the
context only for SessionStart and UserPromptSubmit; whether PreCompact's reaches the agent is
unknown. Hard-coding an unmeasured limit is the bug-042 shape. {#why-body}

## Requirements {#requirements}

1. **R1 Threshold probe** (in a SCRATCH project, never this repo's settings).
   - (a) **Per hook.** A throwaway UserPromptSubmit hook emits 9,000 / 9,900 / 10,000 / 10,100 /
     11,000 chars of numbered lines; a Claude Code session records which arrive whole and which
     as a preview, and the unit (chars vs bytes, via a multibyte payload).
   - (b) **Per event** (19 #s-2). Two hooks on ONE UserPromptSubmit event, 5,000 + 6,000 chars:
     both whole → the cap is per hook; either previewed → per event. The verdict is recorded.
   - (c) **PreCompact** (19 #s-1, d5d). A PreCompact hook emits a unique marker line; after a
     `/compact`, the session is asked to quote any marker it holds. Marker present → PreCompact
     stdout reaches the agent; absent → it does not, and 19.1 R4 drops the PreCompact recall
     (keeping only save-state / promote), and 19.2 never counts PreCompact as `delivered`.
   - The result table goes into [[reference_hook_output_10k_cap]] (a memory overwrite or amend per
     MEMORY-RULES) and sets `DEFAULT_HOOK_BUDGET_CHARS` (limit minus a 5% margin; if per event,
     19.1 R1's per-event formula).
2. **R2 Delivery metric, read from the C7 events** (19 #m-6). For each channel (SessionStart,
   per-prompt, PreCompact if R1(c) keeps it, scan-prompt) on the 20-prompt set of 19.1 AC-2:
   - **before** (today's hooks): distinct memories named inside the delivered payload, which is
     the whole output when under the limit, else its first 2 KB;
   - **after** (19.1–19.3): distinct memories per 21.1's `delivered` events, compared with the
     `retrieved` events of the same `query_id`, and cross-checked against the names counted in
     the payload (the two counts must agree, or the run fails).
   - "Memory" excludes `mtype=subject` and `session/*` rows (d8a).
3. **R3 Index reach.** The number of memories named in `MEMORY.md` before and after 19.3, and
   19.3 R4's executed reachability result.
4. **R4 The fixed baseline for 19.6** (d5b). R2's "after" numbers, per channel, plus scan-prompt's
   delivered size, are written to `eval/production/memory_delivery/baseline-fixed.json` (counts
   and sizes only, no prompt text) and committed. 19.6 compares against this file, not a re-run.
5. **R5 The production path.** Every number comes from the CLI commands the hooks run, in task
   23.0's sandbox, on catalog and memory-dir COPIES (and a tmp global store copy for the
   `--scope both` leg). No measurement connects to a live socket.

## Acceptance criteria {#acceptance}

1. The probe's table (size → whole / preview; unit; per hook vs per event; PreCompact verdict) is
   in the reference memory and the implementation summary, and 19.1's default and PreCompact
   branch derive from it.
2. The before/after table per channel shows the median distinct memories delivered; 19.1 AC-2
   (≥ 5x) is judged from it. The `delivered` event counts equal the payload name counts on every
   prompt.
3. The scan-prompt budget (2,000 tokens) is recorded with its delivered size, and any follow-up is
   named in the summary (19.6 owns the split, d5b).
4. `baseline-fixed.json` exists, is committed, and holds no prompt text.
5. 23.0's guard records 0 live connects for the measurement run.

## Files {#files}

`eval/production/memory_delivery/` (the script, REPORT.md, `baseline-fixed.json`,
`PROMPTS.sha256`; the prompt file itself is local per d8f). The probe hook scripts live in the
scratch project only.

## Test strategy {#test-strategy}

R1 is a manual probe in a scratch Claude Code project, recorded, not a pytest. R2–R4 run as a
script in task 23.0's sandbox (tmp `HOME`, global root, registry; spawned `rmx` children refuse
sockets outside the tmp root) on copies; the script fails loudly if the event counts and payload
counts disagree.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 19 #s-1; d5d | R1(c), AC-1 |
| 19 #s-2 | R1(b), AC-1 |
| 19 #m-6 | R2, AC-2 |
| 19 #b-7; d1a/d1b | R5, [[#test-strategy]], AC-5 |
| 19 #s-3 (baseline unit, named prompt set) | R2 |
| d5b (fixed baseline for 19.6) | R4, AC-4 |
| d8a (subjects not counted as memories) | R2 |
| d8f (prompt text stays local) | R4, [[#files]] |
