---
gmd: "0.1"
id: task-3.1-plan-3-verbs-parity
title: "Task 3.1: memory_recall verb owns recall semantics"
tags: [task, plan-3]
metadata:
  node_type: task
  status: pending
  plan: plan-3-verbs-parity
---

# Task 3.1: memory_recall verb owns recall semantics {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-3-verbs-parity]]

## Requirements {#requirements}

- CLI `--session-start` output is byte-identical (table) before/after on a tmp store with 3 memories.
- MCP `rmx_memory_recall(session_start=True)` on an empty 7d window returns the newest-k rows (widen) and excludes `session/*` unless `include_session`.
- `pytest tests/test_mcp_memory_recall_routing.py tests/test_memory_recall*.py` green.

## Files to Create / Modify {#files}

- `src/refmatrix/verbs.py`: `@verb("rmx_memory_recall") def memory_recall(...)` moved from cli.py (`_mt_excluded`, `_global_rows`, session-start defaulting + widen, `_merge_scope`, `_attach_context`).
- `src/refmatrix/cli.py:memory_recall`: parse flags → `verbs.memory_recall(...)` → render; ~250 lines removed.
- `src/refmatrix/mcp.py:_t_memory_recall` → the verb.

## Test Strategy (RED first) {#test-strategy}

tests/test_verbs_memory_recall.py: real tmp store, three memories with controlled `created_at`, asserts widen + exclusion via the verb; mutation: comment out the widen → test fails.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-3.1-plan-3-verbs-parity.md`.
- Committed on branch `task-3.1-plan-3-verbs-parity`; merged `--no-ff` to `master`.
