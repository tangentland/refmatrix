---
gmd: "0.1"
id: task-9.3-plan-9-context-cost-telemetry
title: "Task 9.3: `rmx telemetry --context`: bytes per command, per-prompt hook budget"
tags: [task, plan-9]
metadata:
  node_type: task
  status: complete
  plan: plan-9-context-cost-telemetry
---

# Task 9.3: `rmx telemetry --context`: bytes per command, per-prompt hook budget {#root}

> Plan: [[plan-9-context-cost-telemetry]]
> Status: Complete
> Depends on: 9.2

rel: part-of -> [[plan-9-context-cost-telemetry]]

## Requirements {#requirements}

- `rmx telemetry --context` reports, from `cli.log`: total bytes, per-command total and p50/p95, and the **per-prompt hook budget** — the summed `out_bytes` of the always-on hook commands grouped per prompt, which is the number answering "what does rmx charge me every turn".
- Grouping a "prompt" is the one real modelling choice: hook records carry `source="hook"` and a pid + ts. Group by the ts window of a `UserPromptSubmit` firing, and STATE the grouping rule in the output rather than leaving a reader to infer it.
- Commands with no `out_bytes` (every row before 9.2) are reported as an explicit uncounted total, never folded into the average as zeros. A pre-field row is unknown, not free.
- Output honours the existing `--format` choices on the command.

## Files to Create / Modify {#files}

- modify `src/refmatrix/telemetry.py` (`summarize_context` or equivalent)
- modify `src/refmatrix/cli.py` (`telemetry` command: `--context` flag)

## Test Strategy (RED first) {#test-strategy}

`tests/test_context_cost.py` (extended):
- per-command totals and percentiles match hand-computed values on a fixture log
- rows without `out_bytes` are counted into an `uncounted` total and excluded from the averages — asserted on a mixed legacy/new fixture
- the hook budget sums only hook-sourced rows within one grouping window
- the rendered output names its grouping rule
- mutation check: folding uncounted rows in as zeros turns the mixed-fixture test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-9.3-plan-9-context-cost-telemetry.md`.
- Committed on branch `task-9.3-plan-9-context-cost-telemetry`; merged `--no-ff` to `master`.
