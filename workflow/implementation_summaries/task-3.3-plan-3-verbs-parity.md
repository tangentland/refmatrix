---
gmd: "0.1"
id: impl-task-3.3-plan-3-verbs-parity
title: "Task 3.3 — generated TOOLS + parity gate"
tags: [implementation-summary, plan-3]
metadata:
  node_type: implementation-summary
  task: task-3.3-plan-3-verbs-parity
---

# Task 3.3 — TOOLS generated, parity asserted {#root}

rel: implements -> [[task-3.3-plan-3-verbs-parity]]

## What shipped {#shipped}

- `Verb.aliases` + `verb(..., aliases={...})`: alias tool-args (`from`→`sender`, `note`→`text`, `subject`→`label`) are part of the generated schema, map onto the param in `Verb.run`, and un-require the aliased param. Missing required args raise `VerbArgsError` (a ValueError) so the MCP dispatcher reports caller bugs as `isError`.
- `mcp.TOOLS = _build_tools()` from `verbs.VERBS`: name, description, schema, and a `_verb_tool(name)` handler carrying `verb_name`. The hand-written 28-entry dict and `_apply_verb_schemas` are gone.
- `verbs.CLI_MAP` (verb → click path) + `verbs.MCP_ONLY` (reasoned exceptions: `rmx_where`, `rmx_search`).
- `tests/test_verb_parity.py`: `set(TOOLS) == set(VERBS)`; every handler dispatches to its verb; schemas exactly equal; every verb kwarg and alias exposed; every verb has a CLI twin or an MCP_ONLY reason and the click path resolves; click defaults equal verb defaults for shared params (13 pairings).

## Note {#note}

The running `rmx mcp` server is a per-client stdio process: `/mcp` reconnect is needed to serve the regenerated tool list.

## TDD record {#tdd}

Delivered in the plan-3 r1 remedy (the original task landed without one — ch-bsd #bs-3): RED `workflow/review-output/pytest-plan3-r1-red.log` (51 failed / 12 passed across test_verb_parity, test_verbs_migrated, test_plan3_remedy), GREEN `pytest-plan3-r1-green.log` (63 passed). See [[impl-remedy-plan-3-verbs-parity#tdd]] for the per-verb tests and the mutation checks.

