---
gmd: "0.1"
id: task-16.8-precise-identifier-context
title: "Task 16.8: rmx context answers an identifier as precisely as grep, plus callers and tests, in a --brief form"
tags: [task, context, agent, identifier]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 16.8: precise identifier answers {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending
> Depends on: 16.7 (to measure the change)

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: derives-from -> [[exploration-agent-context-usage]]

## Why {#why}

Exact-identifier lookups are ~55% of the agent's greps. Replaying 9 of them through `rmx context`
gave 4 hits, 4 partials and 1 miss:
- **The partials:** DEFINED BY named the file **with no line number**.
- **The miss:** `_drop_lance_for_purge`, where only a test was shown.
- **Output friction:**
  - each test listed twice, under two id forms;
  - edge direction that reads inverted (tests listed under CALLS);
  - `[helix]` "last worked … then:" headers on code anchors;
  - JSON 2.4x the text form.

{#why-body}

## Requirements {#requirements}

1. **R1 `path:line` on definitions.** DEFINED BY rows (`LINKAGE_LABELS`, `context.py:40`) render
   `path:line` from the defining evidence. A row with no line evidence says `(line unknown)`;
   it never drops silently.
2. **R2 One id form.** An entity appears once per group. The duplicate `tests/x.py::f` /
   `tests.x.py.f` forms collapse to the canonical one.
3. **R3 Direction labels that read correctly.** For an anchor X: `CALLS` lists what X calls,
   `CALLED BY` lists X's callers, `TESTED BY` lists the tests that reference X. The label table and
   the edge direction are checked against the ingest's emission direction (`link(linkage,
   concept, entity)`), with a test per label.
4. **R4 No helix block on code anchors** unless `--helix` is given. Helix stays on concepts and
   memories (its measured use).
5. **R5 `--brief`:** the definition `path:line` + signature line, up to 5 callers `path:line`, up to
   5 tests `path:line`, and nothing else, in ≤ 200 tokens. MCP `rmx_context` gets a `brief: true`
   argument.
6. **R6 Exact-symbol misses fall to the definition.** When the ref is an exact symbol name with a
   `defines` edge, the defining file:line is the first row, even if content ranking would bury
   it.

## Acceptance criteria {#acceptance}

1. Re-running the exploration's 9-identifier replay (the same patterns) on a catalog copy gives
   **≥ 8 of 9** hits with a line number. It was 4 of 9.
2. `--brief` output is ≤ 200 tokens on all 9, and each contains the definition `path:line`.
3. No entity appears twice in any group across the 9.
4. A label/direction test per relation type (`calls`, `called_by`, tested-by) on a fixture with a
   known call graph.
5. Mutations that must FAIL a test:
   - DEFINED BY without the line;
   - dedupe disabled;
   - label swap;
   - helix on code anchors re-enabled.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/context.py` | DEFINED BY line, dedupe, labels, helix gate, the brief renderer |
| `src/refmatrix/cli.py`, `verbs.py`, `mcp.py`, `daemon.py` (`_op_context`) | `--brief` / `brief` passthrough |

## Test strategy {#test-strategy}

RED on AC-1's fixture analogue: a small ingested Python tree where `rmx context <fn>` currently
returns the file without a line. The replay script for AC-1 lives under `eval/production/` and runs
on a catalog copy through the CLI.
