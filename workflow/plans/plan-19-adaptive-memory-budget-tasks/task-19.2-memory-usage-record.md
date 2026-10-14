---
gmd: "0.1"
id: task-19.2-memory-usage-record
title: "Task 19.2: every memory carries an exact lifetime usage record and a decaying recency score with a nonzero floor, folded exactly-once from recall-events.jsonl"
tags: [task, memory, usage, decay, counters]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 19.2: memory usage, counted exactly, decayed safely {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 19.1 (the pack's `delivered` events, R8); 23.0 (sandbox); 23.1 (`bind(batch)`, the
> non-consuming `tail(log, offset)` reader, the tick registry, the drain offset committed in the
> batch transaction, d2a); 23.2 (the write-count / lock-hold recorder); 21.1 (the recall-event
> schema in `recall-events.jsonl`, with `name`, `entity_id`, `scope`, `session`, `stage`).
> Scheduled after 23.1 in the Wave 1 order ([[plan-review-2026-10-14#t8-wave1]]).

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#amend-counter-rules]]
rel: depends-on -> [[task-19.1-pack-recall-under-budget]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: specified-by -> [[bsd-plan19-spec-review-3104a81]]

## Why {#why}

No usage signal exists. Memory rows carry only `gmd_content_hash` and `gmd_pass2_done`, and
`query.log` has 0 memory-recall rows. So every selection rule (index fold, recall order) is
recency or a fixed order. 19.3 needs a value score, and ADR-0004's counter rules say how to build
one without losing knowledge. {#why-body}

## Requirements {#requirements}

1. **R1 A sidecar table, keyed by names.** `memory_usage(partition_name, scope, name,
   first_seen, last_seen, lifetime_hits, lifetime_used, recency, recency_ts)`, primary key
   `(partition_name, scope, name)`.
   - **NOT in `memory_content.metadata`.** Re-ingesting a memory file rewrites that metadata.
   - **Keyed by memory name, not entity id**, so a purge-and-re-add keeps its history.
   - **Keyed by partition NAME, not `partition_id`**: a partition rebuild (bug-098's repair)
     reassigns the integer.
2. **R2 Exact counts.** Memories are a small domain (329 files on 2026-10-14), so counts are
   exact; no sketch (#rule-no-undercount).
3. **R3 What counts.** This task CONSUMES events; it emits none. Emitters are 19.1 R8 (the
   pack's `delivered`) and 21.1 R11/R12 (`retrieved`, `used`).
   - A **hit** is a `delivered` event: the memory was NAMED in a payload. `retrieved` events
     (trimmed hits) are never counted.
   - A **use** is a `used` event per 21.1 R12: an explicit agent call naming an item delivered
     earlier in the same session (`memory_get_by_name`, `context_by_name`, `focus_note`). It is
     never emitted by the daemon op `_op_memory_get`, by `memory_recall`'s internal per-hit
     `memory_get` call (`verbs.py:766`), or by any `invocation=hook` call. AC-2 holds this fold
     to that contract.
   - Channel ∈ `session_start | prompt_recall | precompact | recall | cli | mcp`. Until 19.5 R1's
     verdict (recorded as a committed constant) shows PreCompact stdout reaches the agent (d5d),
     the fold does NOT count `delivered` events whose channel is `precompact`, and reports how
     many it skipped; if the verdict is negative, 19.1 R4 removes that hook.
   - Every counted event carries `name`, `entity_id`, `scope`, `partition` (by name) and
     `session` per 21.1's schema; an event without `name` is skipped and counted, never resolved
     by entity id.
4. **R4 Global hits are counted in the global store** (d8e). 21.1 R8 appends a hit on a global
   memory to the GLOBAL root's `recall-events.jsonl` with `scope=global`; the global store's
   daemon folds that file into the global store's `memory_usage`, keyed by name. A project
   store's fold skips any `scope=global` row it meets and counts the skip. No fold writes another
   store's catalog.
5. **R5 Folded exactly-once from `recall-events.jsonl`** (d4a, d2a; 19 #b-5).
   - The fold is a consumer in plan-23's TICK REGISTRY (one registry, one shared budget), of type
     `tail(log, offset)`: a non-consuming reader that never rotates, unlinks or rewrites the log,
     and stops at the last complete newline (a lock-free appender can leave a torn tail).
   - Each batch is applied through 23.1's `bind(batch)` with the partition bound explicitly per
     batch (never `with_partition` across a yield, the bug-098 race), and the new offset is
     committed in the SAME DuckDB transaction as the counter updates.
   - The batch `merge_fn` SUMS: two `delivered` events for one name add 2. No coalesce-by-key,
     no dedupe.
   - There is no overflow drop: the log is append-only and the fold resumes from its offset.
   - Rows whose cwd or root is a pytest temp dir are skipped through the ONE shared predicate of
     d8d, `telemetry.is_test_artifact_row` (21.1 R5), and the skip is counted.
   - `recall-events.jsonl` is the retained replay source (the d2a amendment): 21.1 R8 makes it
     append-only, never truncated or rotated by any writer, which AC-6's drop-and-replay relies
     on.
6. **R6 Survives a slot merge.** `replica_merge` gets a rule for `memory_usage`: on a conflict
   between slots, take the elementwise max of `lifetime_hits`, `lifetime_used` and `last_seen`,
   the min of `first_seen`, and `(recency, recency_ts)` from the row with the later
   `recency_ts`. It never keeps an older A-side row over a newer one (decision-log #s-1).
7. **R7 Decay with every ADR-0004 rule. This module is the ONE decay/floor library** (plan review
   C4); helix's age tiers import it, and no other formula may be added.
   - On each event, `recency ← decayed(recency, recency_ts, ts) + w` with `w = 1` for
     `delivered` and `w = 2` for `used`; `recency_ts ← ts`.
   - `decayed(r, r_ts, t) = r · 2^(−(t − r_ts) / H)`, `H = RMX_MEMORY_RECENCY_HALFLIFE_DAYS`
     (default 14), applied at read time, so `H` can change without a rewrite.
   - **The floor is never zero** (19 #b-4, ADR-0004 #rule-floor):
     `floor = base · (1 + log1p(lifetime_hits + 2·lifetime_used))`, with `base = 0.25`.
   - **Asserted floor** (d8b: ADR-0004 #rule-asserted-floor's definition, unchanged): a memory
     that is `type: feedback`, or `protected`, or `rel:`-anchored (it carries or is the target
     of a `rel:` edge) has floor `max(floor, asserted_floor)`, `asserted_floor = 1.0` (the
     recency of one fresh delivery). This is the protection-against-loss signal only; 19.3's
     FOLD ORDER uses a separate tier.
   - `recency_effective(t) = max(floor_eff, decayed(recency, recency_ts, t))`.
   - **A memory with no events** has a virtual row: `lifetime_hits = lifetime_used = 0`,
     `recency = 0`, `first_seen` = its frontmatter `created` (file ctime when absent), so its
     `recency_effective = floor_eff ≥ 0.25`. No write is needed to create it.
   - The lifetime fields never decay.
8. **R8 Never deletes.** No code path in this task removes, folds or prunes a memory. The score is
   an input to 19.3 only.
9. **R9 Visible.** `rmx memory usage [--top N] [--cold N] [--scope project|global]` lists scores
   with their lifetime fields, virtual rows included; the MCP twin goes through the verb
   (verb-parity test).

## Acceptance criteria {#acceptance}

All ACs run in task 23.0's sandbox: a tmp project store and, where the global leg is under test,
a tmp global store; never `_root()` of the live tree.

1. **Hit and use.** Delivering X in a SessionStart pack and then `rmx memory get X` run as the
   agent (`CLAUDECODE=1`, same session) gives, after one fold: `lifetime_hits == 1`, `lifetime_used == 1`, channel recorded.
2. **Recall is not use.** One dense recall that names 5 hits leaves every `lifetime_used == 0`
   and five `lifetime_hits == 1`.
3. **Sum, not dedupe.** Two `delivered` events for X in one batch give `lifetime_hits == 2`.
4. **Purge between append and fold.** Append an event for X, purge and re-add X's file (new
   entity id), fold: the count lands on name X.
5. **Re-ingest.** Re-ingesting X's file (the bridge) leaves its `memory_usage` row byte-identical.
6. **Drop and replay** (d8e). Fold 200 events; drop the `memory_usage` table and reset the fold's
   offset; replay from offset 0: identical rows.
7. **Exactly-once.** Kill the fold between the counter update and COMMIT (an injected fault in
   the transaction): after restart, every count equals the number of events (no loss, no double).
8. **Global route** (d8e). A global hit from a project session increments the GLOBAL store's row
   for that name; the project store's fold reports one `scope=global` skip and writes nothing for
   it.
9. **Floor.** A never-recalled memory has `recency_effective > 0`. With the clock advanced 10
   half-lives, a memory with 1 hit and 1 use has `recency_effective == floor > 0` and unchanged
   lifetime fields. A feedback memory never ranks below `asserted_floor`.
10. **Slot merge.** Two slots with diverging `memory_usage` rows merge to the R6 rule's row.
11. **Torn tail.** A log whose last line has no newline: the fold stops before it and reads it
    whole on the next tick.
12. **Lock holds.** 1,000 events fold in ≤ 2 `bind` holds per 500 events, measured with 23.2's
    recorder on a real `_FairLock`; every batch releases.
13. **PreCompact.** Without a recorded 19.5 R1 verdict, `delivered` events with channel
    `precompact` leave every count unchanged and appear in the fold's skip report.
14. **Isolation.** 23.0's guard records 0 live connects for this task's test files.
15. **Mutations that must FAIL a test:**
    - decay applied to `lifetime_hits`;
    - the floor's `1 +` removed (AC-9's never-recalled case);
    - keyed by entity id (AC-4) or by `partition_id`;
    - a dedupe coalesce in `merge_fn` (AC-3);
    - counting a `used` event emitted from `_op_memory_get` or recall's internal call (AC-2);
    - counting trimmed (undelivered) hits;
    - the offset committed after the batch transaction (AC-7);
    - the project fold counting a global hit (AC-8);
    - `replica_merge` keeping the A-side row (AC-10);
    - the drain taking one hold per event (AC-12).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/store.py` | the `memory_usage` table (migration), batch upsert, read with decay |
| `src/refmatrix/memory_usage.py` (new) | the fold consumer, the decay + floor library |
| `src/refmatrix/replica_merge.py` | the `memory_usage` merge rule (R6) |
| `src/refmatrix/daemon.py` | register the fold in plan-23's tick registry |
| `src/refmatrix/verbs.py`, `cli.py`, `mcp.py` | `rmx memory usage` and its verb (emission is 19.1 R8 and 21.1 R11/R12) |

## Test strategy {#test-strategy}

- **Sandbox:** task 23.0 (tmp `HOME`, global root, registry; injected store roots; spawned `rmx`
  children refuse sockets outside the tmp root; the conftest guard). The global leg uses a tmp
  global store.
- **RED:** AC-1, AC-2 and AC-9 on a real sandbox store, failing today (no table, no fold).
- The decay/floor function is property-tested: monotone non-increasing in time, never below the
  floor, floor > 0 at zero counts, floor monotone in lifetime counts.
- Lock holds and write counts use 23.2's recorder and a real `_FairLock`; no mocks of the store.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 19 #b-4 | R7 (nonzero floor, `base`, `asserted_floor`, virtual rows), AC-9, mutation |
| 19 #b-5; d2a; d4a | R5, AC-3, AC-4, AC-7, AC-11, mutations |
| 19 #b-6 | R3 (`used` only per 21.1 R12; recall's internal `memory_get` never counts; the focus-note signal is 21.1 R12's `focus_note` evidence, a specified matcher), AC-2, mutation |
| 19 #b-7; d1a/d1b | [[#test-strategy]], AC-14 |
| 19 #s-1; d5d | R3 (PreCompact `delivered` not counted until the verdict), AC-13 |
| 19 #s-4; d8e | R1 (partition name), R4, R5 (retained log), AC-6, AC-8 |
| 19 #s-6 (header) | header |
| d8b (floor keeps ADR definition) | R7 asserted floor |
| d8d (pytest temp rows filtered) | R5 |
| decision-log #s-1 (`replica_merge`, retention) | R5, R6, AC-10 |
| decision-log #s-3 (tail reader, tick registry) | R5 |
| decision-log #s-4 (global route) | R4 |
| #t8-wave1 | header |
