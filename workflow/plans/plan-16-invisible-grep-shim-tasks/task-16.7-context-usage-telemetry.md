---
gmd: "0.1"
id: task-16.7-context-usage-telemetry
title: "Task 16.7: telemetry that can count how the agent uses rmx context, MCP calls included"
tags: [task, telemetry, context, mcp, agent]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 16.7: make agent context usage measurable {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending
> Depends on: — (first of the agent-context tasks; 16.8–16.10 are judged by what it counts)

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: derives-from -> [[exploration-agent-context-usage]]

## Why {#why}

The exploration measured 3 CLI `context` calls against ~1,100 agent greps in 14 days, and could not
count MCP calls at all:
- `invocation` is `unknown` on every agent grep and context row.
- `telemetry.invocation_source` (`telemetry.py:151`) documents that "the MCP server set[s]"
  `RMX_INVOCATION_SOURCE`. `mcp.py` never does.
- The daemon's `_op_context` (MCP `rmx_context`) writes no `query.log` row.
- `cardinality` reads 0 on `-E` alternation greps that matched.

Without these, no change in 16.8–16.10 can be shown to change behaviour. {#why-body}

## Requirements {#requirements}

1. **R1** `mcp.serve_stdio` sets `RMX_INVOCATION_SOURCE=mcp` for its process. `mcp` joins
   `INVOCATION_SOURCES`.
2. **R2** Every daemon read op reached from MCP or CLI for context (`context`, and `memory_recall`
   / `ann_search` when called as verbs) appends one `query.log` row:
   `kind`, `body`, `source`, `invocation`, `cardinality`, `latency_ms`, `outcome`, `answered_by`,
   `warnings_n`. The row is written by the CALLER side (verb/CLI), never under the daemon's
   writer lock.
3. **R3** `cardinality` for an `-E` alternation grep counts the matched rows (the grep-replica
   path), not 0.
4. **R4** `rmx telemetry agent-usage --days N` prints per-invocation counts and p50/p95 for
   context, grep, recall and MCP tools. It is the instrument 16.8–16.10 report against.

## Acceptance criteria {#acceptance}

1. An MCP `rmx_context` call through the real stdio server (a subprocess test) produces exactly
   one `query.log` row with `invocation=mcp` and `kind=context`.
2. A CLI `rmx context X` run from a non-tty with no env produces `invocation=unknown`; with the
   hook env it produces `hook`.
3. `rmx grep -E 'a|b' file`, matching 3 lines, logs `cardinality=3`.
4. `rmx telemetry agent-usage --days 14` on a copy of today's `query.log` reproduces the
   exploration's counts (3 CLI context calls, about 1,100 greps), to within rows written since.
5. Mutations that must FAIL a test:
   - the env set after the first verb call;
   - the row written inside the daemon under the lock;
   - `cardinality` hard-coded to the old value.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/mcp.py` | set the env in `serve_stdio` |
| `src/refmatrix/telemetry.py` | `mcp` source; the `agent-usage` report |
| `src/refmatrix/verbs.py` / `cli.py` | caller-side `query.log` row for context / recall |
| `src/refmatrix/cli.py` (grep-replica) | `-E` cardinality |

## Test strategy {#test-strategy}

RED on AC-1 (no row today) and AC-3 (0 today). The MCP test spawns the real server over stdio on a
tmp store with a short root (the `sun_path` limit).
