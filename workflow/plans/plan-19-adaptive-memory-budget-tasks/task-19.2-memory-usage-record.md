---
gmd: "0.1"
id: task-19.2-memory-usage-record
title: "Task 19.2: every memory carries an exact lifetime usage record and a decaying recency score with a floor"
tags: [task, memory, usage, decay, counters]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 19.2: memory usage, counted exactly, decayed safely {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending
> Depends on: 19.1 (the pack output names which memories were delivered)

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#amend-counter-rules]]

## Why {#why}

No usage signal exists. Memory rows carry only `gmd_content_hash` and `gmd_pass2_done`, and
`query.log` has 0 memory-recall rows. So every selection rule (index fold, recall order) is
recency or a fixed order. 19.3 needs a value score, and ADR-0004's counter rules say how to build
one without losing knowledge. {#why-body}

## Requirements {#requirements}

1. **R1 A sidecar table, keyed by name.** The table is
   `memory_usage(partition_id, name, first_seen, last_seen, lifetime_hits, lifetime_used,
   recency, recency_ts)`, primary key `(partition_id, name)`.
   - **NOT in `memory_content.metadata`.** Re-ingesting a memory file rewrites that metadata, so a
     bridge run would erase the record.
   - **Keyed by name, not entity id**, so a purge-and-re-add of the same file keeps its history.
2. **R2 Exact counts.** Memories are a small domain (≈500 rows), so the counts are exact; no sketch
   (rule #rule-no-undercount).
3. **R3 What counts.**
   - A **hit**: the memory was delivered inside a payload. That means 19.1's pack lines/bodies,
     NOT merely retrieved and then trimmed.
   - A **use**: the memory was fetched by name (`rmx memory get` / MCP `rmx_memory_get`), or its
     name/anchor appears in a later focus note or STM ref within the same session.

   Both carry the channel (`session_start | prompt | precompact | cli | mcp`).
4. **R4 No write per event under the lock.** Events go into plan-23's `BoundedQueue`
   (`.refmatrix/memory_usage.queue.jsonl`) and are applied by its bounded drain on the daemon's
   existing flush tick (plan review C5). Events use 21.1's ONE recall-event schema (C7): this task
   counts `delivered` and `used`.
5. **R5 Decay, with every ADR-0004 rule. This module is the ONE decay/floor library** (plan review
   C4): helix's age tiers and touch counters (ADR-0004) import it, and no other formula may be
   added.
   - `recency` decays with half-life `RMX_MEMORY_RECENCY_HALFLIFE_DAYS` (default 14), applied at
     read time from `(recency, recency_ts)`, so the parameter can change without a rewrite.
   - The floor is `floor = base * log1p(lifetime_hits + 2*lifetime_used)`, and asserted memories
     (type feedback, protected, `rel:`-anchored) get `max(floor, asserted_floor)`.
   - The lifetime fields never decay.
6. **R6 Never deletes.** No code path in this task removes a memory, folds it or prunes it. The
   score is an input to 19.3 only.
7. **R7 Visible.** `rmx memory usage [--top N] [--cold N]` lists scores with their lifetime fields,
   and the MCP twin goes through the verb (verb-parity test).

## Acceptance criteria {#acceptance}

1. Delivering memory X in a SessionStart pack and then `rmx memory get X` gives, after one drain:
   `lifetime_hits == 1`, `lifetime_used == 1`, channel recorded.
2. Re-ingesting X's file (the bridge) leaves its `memory_usage` row byte-identical.
3. With the clock advanced by 10 half-lives, `recency_effective(X) == floor(X) > 0`, and the
   lifetime fields are unchanged.
4. 1,000 queued events drain in ≤ 2 lock acquisitions per 500 events. Measured: the writer lock
   is never held longer than the batch bound, asserted with a probe thread (the r8 #s-2 test
   shape).
5. Mutations that must FAIL a test:
   - decay applied to `lifetime_hits`;
   - the floor removed;
   - keyed by entity id;
   - counting trimmed (undelivered) hits;
   - the drain taking one lock per event.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/store.py` | the `memory_usage` table (migration), upsert batch, read with decay |
| `src/refmatrix/memory_usage.py` (new) | queue append/drain, the decay + floor function |
| `src/refmatrix/daemon.py` | drain on the existing flush tick |
| `src/refmatrix/cli.py`, `verbs.py`, `mcp.py` | 19.1 records hits; `memory get` records uses; `rmx memory usage` |

## Test strategy {#test-strategy}

- **RED:** AC-1 and AC-2 on a real store, failing today because no table exists.
- The decay/floor function is property-tested: monotone non-increasing in time, never below the
  floor, floor monotone in lifetime counts.
- The drain lock-hold probe uses a real RLock and a probe thread; no mocks of the store.
