---
gmd: "0.1"
id: impl-task-3.2-plan-3-verbs-parity
title: "Task 3.2 — 18 direct-call MCP tools migrated to verbs"
tags: [implementation-summary, plan-3]
metadata:
  node_type: implementation-summary
  task: task-3.2-plan-3-verbs-parity
---

# Task 3.2 — every tool is a verb {#root}

rel: implements -> [[task-3.2-plan-3-verbs-parity]]

## What shipped {#shipped}

New `@verb`s in `verbs.py`, bodies moved from mcp.py: `where`, `search`, `locate`, `task`, `queues`, `ingest_status`, `recall_state`, `memory` (the action dispatcher + `_MEMORY_OPS` / `_memory_payload`), and nine `bus_*` verbs sharing `_bus_sender` (explicit → `$RMX_AGENT` → the store's project) and `_hub_rpc`. `mcp.py` no longer imports daemon/handoff/hub for any tool; the only special handler left is `_t_memory_add` (documented daemon-down bootstrap fallback), and it still calls the verb first.

## Compatibility {#compat}

`mcp._t_*` names remain as module attributes (the generated dispatchers) and `_MEMORY_OPS` / `_memory_payload` are re-exported, so existing callers and tests are unchanged.
