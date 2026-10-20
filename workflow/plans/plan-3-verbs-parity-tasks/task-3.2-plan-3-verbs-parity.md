---
gmd: "0.1"
id: task-3.2-plan-3-verbs-parity
title: "Task 3.2: Migrate the 20 direct-call tools to verbs"
tags: [task, plan-3]
metadata:
  node_type: task
  status: completed
  plan: plan-3-verbs-parity
---

# Task 3.2: Migrate the 20 direct-call tools to verbs {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: Completed — shipped in 82bbc2b (0.68.0), merged to master at 8ba4799 "merge
> plan-3-verbs-parity (tasks 3.1–3.3)". Later ch-bsd remedy rounds and task 3.4 are owned
> by W1-b ([[plan-review-2026-10-14#t11-folded-waves]]). Status corrected 2026-10-19 (W1-d).
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
