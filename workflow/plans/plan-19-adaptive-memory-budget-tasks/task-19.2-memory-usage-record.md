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
> Depends on: 19.1 (the pack renderer whose byte spans 21.1's single emission site turns into
> `delivered` events, 19.1 R8); 23.0 (sandbox); 23.1 (`bind(partition_name)`, the
> non-consuming `tail(log, offset)` reader, the tick registry, the drain offset committed in the
> batch transaction, d2a); 23.2 (the write-count / lock-hold recorder); 21.1 (the recall-event
> schema in `recall-events.jsonl`: `name`, `kind`, `partition`, `scope`, `session`, `cwd`, `root`,
> `channel`, `stage`, `evidence`, exported as `telemetry.RECALL_EVENT_FIELDS_V1`).
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

1. **R1 A sidecar table, keyed by names, holding RAW counts** (d9e). `memory_usage(
   partition_name, scope, name, first_seen, last_seen, lifetime_hits, used_memory_get_by_name,
   used_context_by_name, used_focus_note, recency_hits, recency_used_memory_get_by_name,
   recency_used_context_by_name, recency_used_focus_note, recency_ts)`, primary key
   `(partition_name, scope, name)`.
   - **NOT in `memory_content.metadata`.** Re-ingesting a memory file rewrites that metadata.
   - **Keyed by memory name, not entity id**, so a purge-and-re-add keeps its history.
   - **Keyed by partition NAME, not `partition_id`**: a partition rebuild (bug-098's repair)
     reassigns the integer. The name is the event's `partition` field (21.1 R10), never the
     daemon's currently bound partition.
   - **Raw, unweighted, per evidence.** Every stored number is an exact count of events (the
     `lifetime_*` / `used_*` columns) or a decayed count of events of ONE kind (the `recency_*`
     columns), each event weighing 1. No weight, base or floor is stored; they apply at READ time
     (R7). A future evidence kind (21.1 R12's reserved `file_read` / `cited_in_answer`) is a
     migration adding its own pair of columns, never folded into an existing one.
   - `lifetime_used` is not a column: where a single number is shown (R9, ADR-0004's text) it is
     the read-time sum of the three `used_*` columns.
   - **`first_seen`** (re-review #m-3) = the `ts` of the earliest folded event for that key (min
     over events, so drop-and-replay and slot merge both reproduce it). A virtual row (R7) has
     `first_seen = null`; 19.3's tie-breaks use the memory's frontmatter `created`, never
     `first_seen`.
2. **R2 Exact counts.** Memories are a small domain (329 files on 2026-10-14), so counts are
   exact; no sketch (#rule-no-undercount).
3. **R3 What counts.** This task CONSUMES events; it emits none. The ONE writer of events is 21.1's
   `telemetry.emit_recall_events` ([[task-21.1-context-usage-telemetry#requirements]] R11); 19.1's
   pack supplies byte spans to it and emits nothing itself (19.1 R8). Field names below are
   21.1 R10's, read through `telemetry.RECALL_EVENT_FIELDS_V1`.
   - **Kinds.** Only events with `kind == "memory"` are folded. `code`, `doc`, `session` and
     `subject` events are skipped and counted under `skipped_kind` (a subject row is not a
     memory; 19.1 R2 keeps subjects out of recall by default).
   - **Channels** (re-review #b-1): 21.1 R10's ONE channel enum, verbatim: `session_start`,
     `prompt_recall`, `scan_prompt`, `precompact`, `context`, `recall`, `nudge`. `cli` and `mcp`
     are `invocation` values, never channels. A `delivered` event with `kind=memory` on ANY of
     these channels is a hit (scan-prompt and context deliveries of a memory name it in a payload
     the agent receives, so they count), except `precompact` while gated (below). `nudge` emits
     only `kind=code` today and is therefore skipped by kind. An event whose `channel` is not in
     the enum (for example `cli`) is malformed: skipped and counted, never folded.
   - A **hit** is a `stage=delivered` event: the memory was NAMED in a payload. `retrieved`
     events (trimmed hits) are never counted.
   - A **use** is a `stage=used` event per 21.1 R12, counted into the column of its `evidence`
     (`memory_get_by_name`, `context_by_name`, `focus_note`). Its matcher, its delivered-set
     lookup and its global destination are 21.1 R12's, not re-specified here. A `used` event is
     never emitted by the daemon op `_op_memory_get`, by `memory_recall`'s internal per-hit read
     (`verbs.py:766`), or by any `invocation=hook` call; AC-2 holds this fold to that contract. An
     unknown `evidence` value is skipped and counted (`skipped_evidence`), never mapped.
   - **PreCompact** (d5d; re-review #m-2). The verdict is the committed constant
     `PRECOMPACT_STDOUT_DELIVERED` in `src/refmatrix/hooks.py`: `None` until 19.5 R1 records the
     probe, then `True` or `False`. The fold imports it. While it is not `True`, `delivered`
     events with `channel=precompact` are skipped and counted (`skipped_precompact`); if it is
     `False`, 19.1 R4 removes that hook.
   - Every counted event carries `name`, `partition`, `scope`, `session`, `cwd`, `root` (21.1
     R10). An event without `name` or `partition` is skipped and counted, never resolved by
     entity id or by the bound partition.
4. **R4 Global hits and uses are counted in the global store** (d8e). 21.1 R8/R12 append every
   `scope=global` event (hit or use) to the GLOBAL root's `recall-events.jsonl`; the global store's
   daemon folds that file into the global store's `memory_usage`, keyed by name. A project store's
   fold skips any `scope=global` row it meets and counts the skip. No fold writes another store's
   catalog.
5. **R5 Folded exactly-once from `recall-events.jsonl`** (d4a, d2a; 19 #b-5). Names are 23.1's
   ([[task-23.1-queue-and-drain]] R1, R4, R6), exact:
   - The fold is registered as `Daemon.tick_registry.register("memory_usage", runner,
     kind="tail")`, reading through `TailLog(path, key_fn=…, merge_fn=…)`: a non-consuming reader
     that never rotates, unlinks or rewrites the log, and stops at the last complete newline (a
     lock-free appender can leave a torn tail).
   - Each batch is applied through `bind(partition_name)` with the partition NAME taken from the
     events (23.1 cuts a batch at every partition change; never `with_partition` across a yield,
     the bug-098 race), and the new offset (`queue_offsets`, segment = the file name) is
     committed in the SAME DuckDB transaction as the counter updates.
   - The batch `merge_fn` SUMS: two `delivered` events for one name add 2. No coalesce-by-key, no
     dedupe.
   - There is no overflow drop: the log is append-only and the fold resumes from its offset.
   - Every row is classified by 21.1 R5's `telemetry.row_provenance(row, reader_root=<this
     store's root>)`; only `attributed` events are folded. `test_artifact` rows are skipped and
     counted; events without `cwd`/`root` are `malformed` and skipped and counted (events never
     have legacy classes: every v1 event carries both fields). Because the classifier compares
     test bases with `reader_root`, a sandbox store folds its own sandbox's events, and the live
     store drops any test tree's (re-review #b-1).
   - `recall-events.jsonl` is the retained replay source (the d2a amendment): 21.1 R8 makes it
     append-only, never truncated or rotated by any writer, which AC-6's drop-and-replay relies
     on.
6. **R6 Survives a slot merge.** `replica_merge` gets a rule for `memory_usage`: on a conflict
   between slots, take the elementwise max of `lifetime_hits`, each `used_*` column and
   `last_seen`, the min of `first_seen` (nulls last), and the four `recency_*` columns with
   `recency_ts` together from the row with the later `recency_ts`. It never keeps an older A-side
   row over a newer one (decision-log #s-1). 23.1 R8's `queue_offsets` rule (the larger
   `offset_bytes`) is plan-23's and is not repeated here.
7. **R7 Decay and floor, computed at READ time** (d9e). This module is the ONE decay/floor
   library (plan review C4); helix's age tiers import it, and no other formula may be added.
   - **Fold time (raw only).** On each counted event of kind `k` (hits, or one `used` evidence):
     every `recency_*` column of the row is decayed to the event's `ts`, then `recency_k += 1`, and
     `recency_ts ← ts`. All components share one `recency_ts`, so decaying them together is exact.
   - `decayed(r, r_ts, t) = r · 2^(−(t − r_ts) / H)`, `H = RMX_MEMORY_RECENCY_HALFLIFE_DAYS`
     (default 14), read at read time, so `H` can change without a rewrite.
   - **Read time.** `score(row, t, *, params=DEFAULT_SCORE_PARAMS)` in `memory_usage.py`:
     - `W = w_hit · lifetime_hits + Σ_e w_e · used_e`;
     - `floor = base · (1 + log1p(W))` (never zero; 19 #b-4);
     - asserted floor (d8b: ADR-0004 #rule-asserted-floor's definition, unchanged): a memory that
       is `type: feedback`, or `protected`, or `rel:`-anchored (it carries or is the target of a
       `rel:` edge) has `floor_eff = max(floor, asserted_floor)`, else `floor_eff = floor`;
     - `recency_effective(t) = max(floor_eff, decayed(w_hit · recency_hits + Σ_e w_e ·
       recency_used_e, recency_ts, t))`.
   - **Defaults** (d9e, accepted as tunable starting defaults): `DEFAULT_SCORE_PARAMS = {base:
     0.25, asserted_floor: 1.0, w_hit: 1, w_e: 2 for every evidence}`. Changing any of them, or
     `H`, rewrites no row and needs no replay (AC-17).
   - **Known interaction, recorded not hidden** (re-review #s-5): with these defaults 298 of 326
     memory files (91%, measured 2026-10-14) carry a `rel:` and sit at `asserted_floor = 1.0`,
     the score of one fresh delivery; for them 19.3's order is decided by memories with ≥ 2 recent
     deliveries or uses, and otherwise falls to the `created` tie-break. `rmx memory usage` prints
     the `at_floor` count (R9) so this is visible, and because the parameters are read-time a
     re-tune is a one-line change. The ADR text for the floor is the orchestrator's pending
     ADR-0004 amendment (d9i, [[plan-19-adaptive-memory-budget#open-after-revision]] item 1);
     this task implements the amended formula above, not the current `log1p`-only text.
   - **A memory with no events** has a virtual row: every count 0, `first_seen = null`, so
     `recency_effective = floor_eff ≥ base`. No write is needed to create it.
   - The `lifetime_hits` and `used_*` columns never decay.
8. **R8 Never deletes.** No code path in this task removes, folds or prunes a memory. The score is
   an input to 19.3 only.
9. **R9 Visible.** `rmx memory usage [--top N] [--cold N] [--scope project|global]` lists scores
   with the raw lifetime columns (per evidence) and the read-time `lifetime_used` sum, virtual
   rows included, and prints one summary line with the fold's skip counters
   (`skipped_kind`, `skipped_precompact`, `skipped_evidence`, `skipped_global`, test-artifact and
   malformed counts) and `at_floor=<n>/<total>`. The MCP twin goes through the verb (verb-parity
   test).

## Acceptance criteria {#acceptance}

All ACs run in task 23.0's sandbox: a tmp project store and, where the global leg is under test,
a tmp global store; never `_root()` of the live tree. Unless an AC says otherwise, events are
appended through 21.1's `telemetry.emit_recall_events` with `cwd`/`root` inside the sandbox.

1. **Hit and use.** Delivering X in a SessionStart pack and then `rmx memory get X` run as the
   agent (`CLAUDECODE=1`, same session) gives, after one fold: `lifetime_hits == 1`,
   `used_memory_get_by_name == 1`, the other `used_*` columns 0.
2. **Recall is not use.** One dense recall that names 5 hits leaves every `used_*` column 0 and
   five `lifetime_hits == 1`.
3. **Sum, not dedupe.** Two `delivered` events for X in one batch give `lifetime_hits == 2`.
4. **Purge between append and fold.** Append an event for X, purge and re-add X's file (new
   entity id), fold: the count lands on name X.
5. **Re-ingest.** Re-ingesting X's file (the bridge) leaves its `memory_usage` row byte-identical.
6. **Drop and replay** (d8e). Fold 200 events; drop the `memory_usage` table and reset the fold's
   offset; replay from offset 0: identical rows, `first_seen` included.
7. **Exactly-once.** Kill the fold between the counter update and COMMIT (an injected fault in
   the transaction): after restart, every count equals the number of events (no loss, no double).
8. **Global route** (d8e). A global hit and a global `used` (21.1 AC-11c's note) from a project
   session increment the GLOBAL store's row for that name (`lifetime_hits == 1`,
   `used_focus_note == 1`); the project store's fold reports two `scope=global` skips and writes
   nothing for them.
9. **Floor.** A never-recalled memory has `recency_effective > 0`. With the clock advanced 10
   half-lives, a memory with 1 hit and 1 use has `recency_effective == floor > 0` and unchanged
   lifetime columns. A feedback memory never ranks below `asserted_floor`.
10. **Slot merge.** Two slots with diverging `memory_usage` rows merge to the R6 rule's row.
11. **Torn tail.** A log whose last line has no newline: the fold stops before it and reads it
    whole on the next tick.
12. **Lock holds.** 1,000 events fold in ≤ 2 `bind` holds per 500 events, measured with 23.2's
    recorder on a real `_FairLock`; every batch releases.
13. **PreCompact.** With `PRECOMPACT_STDOUT_DELIVERED is None` (and with it `False`), `delivered`
    events with channel `precompact` leave every count unchanged and appear in
    `skipped_precompact`; with it `True` they count.
14. **Isolation.** 23.0's guard records 0 live connects for this task's test files.
15. **Kinds and channels** (re-review #b-1). One batch holds: a `scan_prompt` `delivered` event
    with `kind=memory` (counts: +1 hit), a `scan_prompt` `delivered` with `kind=code` named like a
    memory (no row; `skipped_kind == 1`), a `context` `delivered` with `kind=memory` (+1 hit), a
    `subject` delivery (skipped), and an event with `channel="cli"` (rejected as malformed: not
    in the enum).
16. **Real emitters, one contract** (re-review #b-1; cross-plan). The fold runs over the
    `recall-events.jsonl` that 21.1 AC-8's harness writes (the GENERATED hook commands, real
    `scan-prompt` and `memory recall`, memories seeded in partition `intuition`, cwd in the
    sandbox): every `delivered` memory event lands on `("intuition", "project", name)`. One extra
    event with `cwd`/`root` under `/private/var/folders/x/pytest-of-u/pytest-7/t0` is skipped and
    counted as a test artifact. A test asserts that every field the fold reads is a member of
    `telemetry.RECALL_EVENT_FIELDS_V1`.
17. **Read-time parameters** (d9e). Folding 50 events, then scoring with `w_e = 5` and
    `base = 0.1` instead of the defaults: the stored rows are byte-identical before and after,
    and the scores change exactly as R7's formula predicts.
18. **Mutations that must FAIL a test:**
    - decay applied to `lifetime_hits` or a `used_*` column;
    - the floor's `1 +` removed (AC-9's never-recalled case);
    - keyed by entity id (AC-4), by `partition_id`, or by the bound partition instead of the
      event's `partition` (AC-16: events in `intuition`, the bound partition is the default);
    - a dedupe coalesce in `merge_fn` (AC-3);
    - counting a `used` event emitted from `_op_memory_get` or recall's internal call (AC-2);
    - counting trimmed (undelivered) hits;
    - counting `kind=code` deliveries (AC-15);
    - the offset committed after the batch transaction (AC-7);
    - the project fold counting a global hit or use (AC-8);
    - `replica_merge` keeping the A-side row (AC-10);
    - the drain taking one hold per event (AC-12);
    - weights applied at fold time (AC-17: stored rows change);
    - `cwd` ignored by the classifier call (AC-16's pytest-temp event folded);
    - `reader_root` passed as the live root in the sandbox (AC-16: every own event skipped).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/store.py` | the `memory_usage` table (migration, raw per-evidence columns), batch upsert |
| `src/refmatrix/memory_usage.py` (new) | the fold consumer (`TailLog` + `row_provenance`), the read-time `score()` with `DEFAULT_SCORE_PARAMS` (the ONE decay/floor library) |
| `src/refmatrix/hooks.py` | the `PRECOMPACT_STDOUT_DELIVERED` constant (value set by 19.5 R1) |
| `src/refmatrix/replica_merge.py` | the `memory_usage` merge rule (R6) |
| `src/refmatrix/daemon.py` | register the fold in plan-23's tick registry |
| `src/refmatrix/verbs.py`, `cli.py`, `mcp.py` | `rmx memory usage` and its verb (emission is 19.1 R8 and 21.1 R11/R12) |

## Test strategy {#test-strategy}

- **Sandbox:** task 23.0 (tmp `HOME`, global root, registry; injected store roots; spawned `rmx`
  children refuse sockets outside the tmp root; the conftest guard). The global leg uses a tmp
  global store.
- **RED:** AC-1, AC-2, AC-9, AC-15 and AC-16 on a real sandbox store, failing today (no table, no fold).
- The decay/floor function is property-tested: monotone non-increasing in time, never below the
  floor, floor > 0 at zero counts, floor monotone in lifetime counts.
- Lock holds and write counts use 23.2's recorder and a real `_FairLock`; no mocks of the store.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 19 #b-4 | R7 (nonzero floor, `base`, `asserted_floor`, virtual rows), AC-9, mutation |
| 19 #b-5; d2a; d4a | R5, AC-3, AC-4, AC-7, AC-11, mutations |
| 19 #b-6 | R3 (`used` only per 21.1 R12; recall's internal `memory_get` never counts), AC-2, mutation. CORRECTED in round 2: at `32dde06` the focus-note matcher was NOT specified (re-review #b-5); it is now, in 21.1 R12, with 21.1 AC-11c |
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

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]] /
[[plan-review-2026-10-14#t9-fixes]].

| finding / decision | answered at |
|---|---|
| re-review #b-1 (19.2 side: `partition` key, `cwd`/`root` filter, channel enum, counted kinds) | R1 (`partition_name` from the event), R3 (kinds: memory only; channels: 21.1's enum verbatim, `cli`/`mcp` removed; `scan_prompt`/`context` deliveries count), R5 (`row_provenance` with `reader_root`); AC-15, AC-16; mutations |
| re-review #b-5 (19.2 side; the false revision row) | R3 (matcher, lookup and destination are 21.1 R12's); R4 (global uses); AC-8; corrected 19 #b-6 row in [[#rev-2026-10-14]] |
| re-review #s-1 (`delivered` claimed three ways) | R3 (the ONE writer is 21.1's `emit_recall_events`; 19.1 supplies spans); header |
| re-review #s-5 (degenerate score at `asserted_floor = 1.0`) | R7 "Known interaction" (recorded, `at_floor` printed, read-time re-tune); d9e accepts the defaults |
| re-review #m-2 (PreCompact constant unnamed) | R3 (`hooks.PRECOMPACT_STDOUT_DELIVERED`); AC-13 |
| re-review #m-3 (`first_seen`) | R1 (min event `ts`; virtual rows null; 19.3 uses `created`); AC-6 |
| d9e (raw per-evidence counts; weights and floors at read time; defaults tunable) | R1, R7 (`score`, `DEFAULT_SCORE_PARAMS`); AC-17; mutation |
| d9i (ADR-0004 floor amendment, drafted by the orchestrator, pending) | R7 (implements the amended formula; reference only) |
| 23.1 names (cross-plan contract) | R5 (`tick_registry.register(..., kind="tail")`, `TailLog`, `bind(partition_name)`, `queue_offsets`); R6 |
