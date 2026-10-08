---
gmd: "0.1"
id: task-19.5-measure-delivery
title: "Task 19.5: measure what reaches the agent per channel, and probe the harness's whole-delivery limit"
tags: [task, memory, measurement, hooks, budget]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 19.5: measure delivery, not production {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending
> Depends on: — (the threshold probe runs FIRST and sets 19.1's default); the before/after part
> runs after 19.1–19.3

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[reference_hook_output_10k_cap]]

## Why {#why}

Today's sizes measure what the hooks PRODUCE. What matters is what the agent SEES. The ~10k
whole-delivery limit is a user-stated figure that matches the behaviour seen in this session (16 KB
and 26 KB outputs arrived as 2 KB previews), but it has not been probed directly. Hard-coding an
unmeasured limit is the bug-042 shape (built to the wrong unit). {#why-body}

## Requirements {#requirements}

1. **R1 Threshold probe.**
   - A throwaway UserPromptSubmit hook, installed in a SCRATCH project (never this repo's settings),
     emits 9,000 / 9,900 / 10,000 / 10,100 / 11,000 chars of numbered lines.
   - A Claude Code session in that project records which outputs arrive whole and which arrive as
     a preview, and in which unit the limit is counted (chars vs bytes, via a multibyte payload).
   - The result goes into [[reference_hook_output_10k_cap]] and sets `RMX_HOOK_BUDGET_CHARS`'s
     default (limit minus a 5% margin).
2. **R2 Delivery metric.** For each channel (SessionStart, per-prompt, PreCompact,
   scan-prompt) on 20 recorded prompts: the distinct memories named inside the delivered payload
   (the whole output when under the limit, else its first 2 KB), before (today's hooks) and after
   (19.1–19.3).
3. **R3 Index reach.** The number of memories named in `MEMORY.md`, before and after 19.3, and the
   R4 reachability result.
4. **R4 The production path.** Every number comes from the CLI commands the hooks run (the
   benchmark path IS the production path), on catalog and memory-dir COPIES.

## Acceptance criteria {#acceptance}

1. The probe's result table (size → whole/preview, unit) is in the reference memory and the
   implementation summary. The 19.1 default derives from it.
2. The before/after table per channel shows the median distinct-memories-delivered. 19.1's AC-2
   (≥ 5x) is judged from it.
3. The scan-prompt budget (2,000 tokens) is recorded with its delivered size, and any follow-up is
   named in the summary.

## Files {#files}

`eval/production/memory_delivery/` (a script + REPORT.md); the probe hook script lives in the
scratch project only.
