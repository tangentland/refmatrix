---
gmd: "0.1"
id: task-19.4-keep-derived-layers-current
title: "Task 19.4: subjects recompile on a schedule; the index regenerates on every bridged memory write and at SessionStart"
tags: [task, memory, compile, index, schedule]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 19.4: keep the derived memory layers current {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending
> Depends on: 19.3; plan-17 task 17.2 (the nightly tick), with the fallback below until it lands

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[plan-17-nightly-store-maintenance]]

## Why {#why}

- `rmx memory compile --apply` (`cli.py:12576`) runs only by hand, so subjects go stale as memories
  accrue.
- `memory_index` runs only from save-state (`handoff._ss_update_index`, `handoff.py:224`). A memory
  written any other way reaches the index only at the next save-state.

19.3's subject-tiered index is only as good as these two layers' freshness. {#why-body}

## Requirements {#requirements}

1. **R1 Scheduled compile.** Memory compile (apply) joins plan-17's nightly maintenance tick, per
   store, serially, skipping paused stores, with results logged and published.
   - Until 17.2 lands, save-state runs compile when the last compile is older than 24 h (a stamp
     in `.refmatrix/`). The bound is `RMX_MEMORY_COMPILE_BUDGET_S`, default 60.
   - Over budget, it is skipped and that is said; it is never silent.
2. **R2 Index on write.** The ingest-gmd memory bridge, after a successful batch that added or
   changed memory files, regenerates `MEMORY.md` through `memory_index.write`, the same function
   save-state calls. That covers the SessionStart detach bridge too.
3. **R3 Compile never loses.** Compile only re-files `part-of` edges between subjects and members.
   A memory that leaves every subject renders in its type section (19.3 R1). No memory is
   removed.
4. **R4 Loud.** Every path reports compiled/skipped/failed with counts (no `|| true`, no bare
   except, per the memory-path rule).

## Acceptance criteria {#acceptance}

1. Writing a new memory file and running only the SessionStart bridge (no save-state) produces an
   index that names the new memory.
2. With plan-17's tick (or the save-state fallback with a stamp older than 24 h), subjects
   recompile once and the stamp updates. A second run inside 24 h skips and says so.
3. A compile that moves memory X out of every subject leaves X reachable (19.3 R4 check passes).
4. Mutations that must FAIL a test:
   - the bridge not regenerating the index;
   - the stamp never updated;
   - the over-budget path silent.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/ingest_gmd.py` | regenerate the index after a memory batch |
| `src/refmatrix/handoff.py` | the stamped compile fallback |
| `src/refmatrix/hub.py` / plan-17's tick | the compile step (when 17.2 lands) |

## Test strategy {#test-strategy}

RED on AC-1 (today the bridge never touches the index). Real fixture stores; the clock is
injected for the 24 h stamp; there are no mocks of compile.
