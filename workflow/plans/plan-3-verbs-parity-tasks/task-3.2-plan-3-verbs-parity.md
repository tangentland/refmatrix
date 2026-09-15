---
gmd: "0.1"
id: task-3.2-plan-3-verbs-parity
title: "Task 3.2: Migrate the 20 direct-call tools to verbs"
tags: [task, plan-3]
metadata:
  node_type: task
  status: pending
  plan: plan-3-verbs-parity
---

# Task 3.2: Migrate the 20 direct-call tools to verbs {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: Pending
> Depends on: 3.1

rel: part-of -> [[plan-3-verbs-parity]]

## Requirements {#requirements}

- `grep -n "daemon_mod\|handoff\." src/refmatrix/mcp.py` → only the verbs import.
- Existing MCP tests (`tests/test_mcp_*.py`) green unchanged.

## Files to Create / Modify {#files}

- `src/refmatrix/verbs.py`: `recall_state`, `memory_get`, `memory_add`, `memory_list`, `memory_dedup`, `memory_promote` (or one `memory(action=…)` mirroring the existing tool), `locate`, `task`, `where`, `search`, `ingest_status`, `queues`, `bus_pub/read/history/channels/mark_read/archive/unarchive/delete/purge/stats`.
- `src/refmatrix/mcp.py`: each `_t_*` becomes `verbs.<name>`; no daemon/handoff imports remain in mcp.py except through verbs.

## Test Strategy (RED first) {#test-strategy}

tests/test_mcp_tools.py extended per tool with a real tmp store where cheap; bus tools against a tmp hub bus file.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-3.2-plan-3-verbs-parity.md`.
- Committed on branch `task-3.2-plan-3-verbs-parity`; merged `--no-ff` to `master`.
