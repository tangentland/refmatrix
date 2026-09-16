---
gmd: "0.1"
id: task-9.1-plan-9-context-cost-telemetry
title: "Task 9.1: query.log rows carry `invocation`"
tags: [task, plan-9]
metadata:
  node_type: task
  status: complete
  plan: plan-9-context-cost-telemetry
---

# Task 9.1: query.log rows carry `invocation` {#root}

> Plan: [[plan-9-context-cost-telemetry]]
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-9-context-cost-telemetry]]

## Requirements {#requirements}

- `telemetry.log_query.__exit__` writes `"invocation": invocation_source()` into every record. The function ALREADY EXISTS, is already correct, and is already used by `log_cli_invocation` — this task adds the one call, it does not write a classifier.
- The key is `invocation`, **not** `source`. `query.log`'s `source` already means the SURFACE (`scan-prompt`, `grep-replica`, `context-replica`); `cli.log`'s `source` means the FORM. Reusing the name across the two logs would make every future join silently wrong.
- `summarize()` gains `by_invocation`, and `zero_result_*` becomes sliceable by it — the slice the failed `brief/unanswered` gate needed and could not compute.
- **Old rows keep reading.** 2,527 rows of history predate the field. Every reader defaults it to `"unknown"`, and that path is tested with a record that genuinely lacks the key. A backfill that dropped history would destroy the only baseline this plan has.
- Still best-effort: telemetry must never fail the command it is describing.

## Files to Create / Modify {#files}

- modify `src/refmatrix/telemetry.py` (`log_query.__exit__`, `summarize`)

## Test Strategy (RED first) {#test-strategy}

`tests/test_telemetry_invocation.py`:
- a record written under `RMX_INVOCATION_SOURCE=hook` carries `invocation="hook"`; unset + no tty carries `"unknown"`
- an unrecognised value falls back to `"unknown"` rather than being written through
- `invocation` and `source` are DIFFERENT keys on the same record, and `source` still holds the surface name
- `summarize` over a mixed log returns `by_invocation` counts that partition the row set exactly
- a legacy record with NO `invocation` key is counted as `"unknown"` and does not raise
- zero-result rows can be sliced by invocation (hook-only vs interactive)
- mutation check: deleting the `invocation` line turns the first test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-9.1-plan-9-context-cost-telemetry.md`.
- Committed on branch `task-9.1-plan-9-context-cost-telemetry`; merged `--no-ff` to `master`.
