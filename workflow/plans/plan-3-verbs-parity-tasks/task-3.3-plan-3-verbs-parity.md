---
gmd: "0.1"
id: task-3.3-plan-3-verbs-parity
title: "Task 3.3: Generated TOOLS + parity test"
tags: [task, plan-3]
metadata:
  node_type: task
  status: pending
  plan: plan-3-verbs-parity
---

# Task 3.3: Generated TOOLS + parity test {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: Pending
> Depends on: 3.2

rel: part-of -> [[plan-3-verbs-parity]]

## Requirements {#requirements}

- Adding a `@verb` without a tool, or a tool without a verb, fails the suite. Schemas contain every parameter of the verb signature.

## Files to Create / Modify {#files}

- `src/refmatrix/verbs.py:tool_schema(verb) -> dict` from the signature (types → JSON schema; `schema_overrides` dict for enums/required); `mcp.TOOLS = [tool_schema(v) for v in REGISTRY]`.
- `tests/test_verb_parity.py`: tools == verbs, handler identity, every verb has a CLI command that calls it (mapping table in `verbs.CLI_MAP`, asserted).

## Test Strategy (RED first) {#test-strategy}

tests/test_verb_parity.py rewritten; tests/test_mcp_parity.py kept green.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-3.3-plan-3-verbs-parity.md`.
- Committed on branch `task-3.3-plan-3-verbs-parity`; merged `--no-ff` to `master`.
