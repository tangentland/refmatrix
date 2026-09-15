---
gmd: "0.1"
id: impl-task-3.1-plan-3-verbs-parity
title: "Task 3.1 — memory_recall verb owns recall semantics"
tags: [implementation-summary, plan-3]
metadata:
  node_type: implementation-summary
  task: task-3.1-plan-3-verbs-parity
---

# Task 3.1 — one recall implementation {#root}

rel: implements -> [[task-3.1-plan-3-verbs-parity]]

## What shipped {#shipped}

- `verbs.memory_recall(root, *, query, k, scope, kinds, fuse, rerank, since_seconds, since, recent, session_start, exclude_mtype, include_session, subject, degree)` returns `{memories, mode, widened, since_seconds}` and owns: the session-start 7d default + widen-when-empty, the session/* exclusion (`include_session` opts in), `since` duration parsing, the scope merge (`merge_scope`, round-robin), subject leaves, and degree context (`attach_context`). Empty query keeps the MCP contract (= recent).
- Shared helpers moved into verbs: `parse_duration`, `mt_excluded`, `global_recall_rows`, `merge_scope`, `attach_context`, `payload_memory_recall`, `resolve_session`. cli.py keeps thin aliases so existing callers/tests keep working.
- `cli.py:memory_recall`: `--recent` / `--session-start` / `--subject` call the verb and render; the hybrid (dense, replica-first) path keeps its routing per the verbs module policy but uses the shared helpers. Daemon-down: the CLI degrades to the lock-free reader (or the store) with a stderr note in table mode; the verb itself refuses (daemon-routed).

## TDD record {#tdd}

RED `workflow/review-output/pytest-plan3-RED.log` (13 failed incl. 5 real-store spawned-daemon verb tests); GREEN `pytest-plan3-GREEN.log` (138 passed across verb/MCP/recall/hook/save-state files). The verb tests spawn a real daemon on a short tmp root with memories at controlled ages — no monkeypatch of the verb.
