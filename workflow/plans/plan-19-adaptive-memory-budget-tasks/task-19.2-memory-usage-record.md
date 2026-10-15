---
gmd: "0.1"
id: task-19.2-memory-usage-record
title: "Task 19.2: every memory carries an exact lifetime usage record and raw per-day counts from which a decaying recency score with a nonzero floor is computed at read time, folded exactly-once from recall-events.jsonl"
tags: [task, memory, usage, decay, counters]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-15
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

1. **R1 Two sidecar tables, keyed by names, holding ONLY raw counts** (d9e; round-3 #s-2).
   - `memory_usage(partition_name, scope, name, first_seen, last_seen, lifetime_hits,
     used_memory_get_by_name, used_context_by_name, used_focus_note)`, primary key
     `(partition_name, scope, name)`: the exact lifetime record (ADR-0004 #rule-two-records).
   - `memory_usage_daily(partition_name, scope, name, day, hits, used_memory_get_by_name,
     used_context_by_name, used_focus_note)`, primary key `(partition_name, scope, name, day)`,
     `day` = the date part of the event's `ts`: raw per-day counts, the ONLY input of recency.
     **`ts` is UTC by contract** (round-4 #s-2): 21.1 R10 stamps every event's `ts` as fixed-width
     ISO-8601 UTC with milliseconds and `Z` (`YYYY-MM-DDTHH:MM:SS.mmmZ`), and 21.1 R5's class 0
     makes any other form `malformed`, so the fold never sees a zone-less `ts`. `day` is
     `ts[:10]`, read off the string: no zone conversion runs at fold time, so the folding
     process's `TZ` and DST changes cannot move an event to another `day`. The repo's other
     timestamps (`query.log`, the STM ring) stay local naive and are never fold keys.
   - **No decayed value is stored anywhere.** The round-2 `recency_*` / `recency_ts` columns are
     withdrawn: a stored decayed sum embeds the fold-time half-life, depends on the order and the
     batching of events (23.1's `TailLog` coalesces by key per tick budget), and moves
     `recency_ts` backward on a clock-skewed event. Every stored number here is an integer count,
     a `min`, or a `max`, so the fold is commutative and associative: any order and any batch
     boundary give the same rows, exactly.
   - **NOT in `memory_content.metadata`.** Re-ingesting a memory file rewrites that metadata.
   - **Keyed by memory name, not entity id**, so a purge-and-re-add keeps its history.
   - **Keyed by partition NAME, not `partition_id`**: a partition rebuild (bug-098's repair)
     reassigns the integer. The name is the event's `partition` field (21.1 R10), never the
     daemon's currently bound partition.
   - **Raw, unweighted, per evidence.** Every count is an exact count of events of ONE kind,
     each event weighing 1. No weight, base, floor or half-life is stored; they apply at READ time
     (R7). A future evidence kind (21.1 R12's reserved `file_read` / `cited_in_answer`) is a
     migration adding its own column to BOTH tables, never folded into an existing one.
   - `lifetime_used` is not a column: where a single number is shown (R9, ADR-0004's text) it is
     the read-time sum of the three `used_*` columns.
   - **`first_seen`** (re-review #m-3) = the `ts` of the earliest folded event for that key (min
     over events, so drop-and-replay reproduces it; the slot-merge path is RETIRED, R6, d9ay).
     The fixed-width UTC form makes string `min` / `max` equal time order (round-4 #s-2). A
     virtual row (R7) has `first_seen = null`; 19.3's tie-breaks use the memory's frontmatter `created`, never
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
   - `key_fn` = `(partition_name, scope, name, day)`; the batch `merge_fn` SUMS each count and
     takes `min` / `max` of the events' `ts` (for `first_seen` / `last_seen`): two `delivered`
     events for one name add 2. It never dedupes. Because every merged value is a sum, a min or a
     max, the result does not depend on how 23.1 cuts or coalesces batches (round-3 #s-2).
   - There is no overflow drop: the log is append-only and the fold resumes from its offset.
   - Every row is classified by 21.1 R5's `telemetry.row_provenance(row, reader_root=<this
     store's root>, source="events")`; only `attributed` events are folded. `test_artifact` and
     `malformed` rows (the function decides both; this module carries no check of its own) are
     skipped and counted; unparseable lines are counted before classification. The classifier
     keys on the event's `root` (its `cwd` only when `root` is absent; round-3 #s-3), so a sandbox
     store folds its own events whatever the emitting process's cwd (pytest `tmp_path`, the
     repo), and the live store drops any test tree's (re-review #b-1).
   - `recall-events.jsonl` is the retained replay source (the d2a amendment): 21.1 R8 makes it
     append-only, never truncated or rotated by any writer, which AC-6's drop-and-replay relies
     on.
6. **R6 Survives a slot merge: RETIRED (d9ay).** Nothing in 19.2 implements or tests this
   requirement, and `replica_merge.py` leaves the Files table. d9ay extends d9ao's retirement of
   23.1 R8 ([[task-23.1-queue-and-drain#r8]]) to this slot-merge path, for the same reasons, read
   at HEAD `77ac38f`:
   - **No producer of diverged slots.** Writer rotation is dropped:
     `Daemon._refresh_replica_now` (`daemon.py:2862-2876` at `23ad703`) is a no-op returning
     `{"enabled": False, … "rotation dropped (snapshot-tier read path)"}`, and the refresh thread
     is not started, so no live path leaves two slots with diverging `memory_usage` rows. The
     frozen inactive slots predate both tables, so no slot pair holds diverged rows of them.
   - **The merge itself is broken (bug-113, open).** `replica_merge.merge_slots` builds its target
     through `duckdb_catalog.init_catalog`, which lacks `entities.vectors_partition`, and fails on
     every real store; an AC built on `init_catalog` slots would pass while the production command
     fails.
   - If a later plan revives slot merging, it adds `memory_usage` and `memory_usage_daily` to
     both `init_catalog` and `merge_slots`' table list and writes its own AC through
     `_op_replica_merge` on `Store.init()` slots; bug-113 is not a 19.2 dependency.
   - Original text, kept as history: "`replica_merge` gets a rule for both tables: on a conflict
     between slots, `memory_usage` takes the elementwise max of `lifetime_hits`, each `used_*`
     column and `last_seen`, and the min of `first_seen` (nulls last); `memory_usage_daily` takes
     the elementwise max of each count per `(partition_name, scope, name, day)`. It never keeps an
     older A-side row over a newer one (decision-log #s-1)."
7. **R7 Decay and floor, computed at READ time** (d9e). This module is the ONE decay/floor
   library (plan review C4); helix's age tiers import it, and no other formula may be added.
   - **Fold time (raw only).** Each counted event of kind `k` (a hit, or one `used` evidence)
     adds 1 to `k` in its `memory_usage` row and in its `memory_usage_daily` row for its UTC day,
     and folds its `ts` into `first_seen` (min) and `last_seen` (max). Nothing is decayed at fold
     time (round-3 #s-2).
   - **Recency, at read time only.** For each kind `k`:
     `recency_k(t) = Σ_day count_k(day) · 2^(−max(0, t − mid(day)) / H)`, where `mid(day)` is
     that UTC day's 12:00 as an epoch (computed in UTC, `calendar.timegm`, never `time.mktime`;
     round-4 #s-2), `t` is an epoch, and `H = RMX_MEMORY_RECENCY_HALFLIFE_DAYS` (default 14) is read when the
     score is computed. Because no stored value embeds `H`, changing `H` re-scores every memory
     exactly, with no rewrite and no replay (AC-17). A day in the future of `t` (clock skew)
     weighs 1, never more. Days with `t − mid(day) > 30·H` are not read (their weight is below
     2^−30 per event); that skip is the one approximation, and it never touches the lifetime
     columns. The per-day quantisation moves an event by at most 12 h, a factor of at most
     2^(0.5/H) (2.5% at `H = 14`); `H` below 1 day is refused.
   - **Read time.** `score(row, t, *, params=DEFAULT_SCORE_PARAMS)` in `memory_usage.py`:
     - `W = w_hit · lifetime_hits + Σ_e w_e · used_e`;
     - `floor = base · (1 + log1p(W))` (never zero; 19 #b-4);
     - asserted floor (d8b: ADR-0004 #rule-asserted-floor's definition, unchanged): a memory that
       is `type: feedback`, or user-asserted, or `protected`, or `rel:`-anchored (it carries or is
       the target of a `rel:` edge) has `floor_eff = max(floor, asserted_floor)`, else
       `floor_eff = floor`. **User-asserted**, mapped (round-3 #m-1): a memory whose frontmatter
       `metadata.type` is `user` or `guardrail` (MEMORY-RULES' types for the user's own facts and
       enforced rules); there is no other user-asserted marker in the catalog;
     - `recency_effective(t) = max(floor_eff, w_hit · recency_hits(t) + Σ_e w_e ·
       recency_used_e(t))`.
   - **Defaults** (d9e, accepted as tunable starting defaults): `DEFAULT_SCORE_PARAMS = {base:
     0.25, asserted_floor: 1.0, w_hit: 1, w_e: 2 for every evidence}`. Changing any of them, or
     `H`, rewrites no row and needs no replay (AC-17), because no stored value depends on them.
   - **Known interaction, recorded not hidden** (re-review #s-5): with these defaults 298 of 326
     memory files (91%, measured 2026-10-14) carry a `rel:` and sit at `asserted_floor = 1.0`,
     the score of one fresh delivery; for them 19.3's order is decided by memories with ≥ 2 recent
     deliveries or uses, and otherwise falls to the `created` tie-break. `rmx memory usage` prints
     the `at_floor` count (R9) so this is visible, and because the parameters are read-time a
     re-tune is a one-line change. The ADR text for the floor is ADR-0004 #rule-floor as amended
     and APPROVED on 2026-10-14 (d9k, `3021cd6`): `base * (1 + log1p(hits + 2*used))`, at read
     time over raw counts, which is the formula above.
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
6. **Drop and replay, any batching** (d8e; round-3 #s-2). 200 events over 40 UTC days, for 12
   names, with 15 events out of `ts` order (an event older than ones already appended, as
   parallel appenders produce). Fold them with 23.1's tick budget set so batches hold 1 event,
   then drop BOTH tables, reset the fold's offset and replay from offset 0 with batches of 7, then
   again with one batch of 200: all three runs give byte-identical `memory_usage` and
   `memory_usage_daily` tables (exact equality: every stored value is an integer, a min or a
   max), `first_seen` included. A second fold of a log holding the same events in a different
   order gives the same tables. **Zone independence** (round-4 #s-2): the 200 events include 20
   stamped within 2 h either side of 2026-11-01T09:00:00.000Z (the US fall-back hour, 02:00 PDT →
   01:00 PST) and 10 within an hour of a UTC midnight; the batch-of-7 replay runs once with
   `TZ=UTC` and once with `TZ=America/Los_Angeles` (both set in the fold process's environment and
   applied with `time.tzset()`), and both give byte-identical tables, equal to the batch-of-1 run.
   Pre-check, recorded before GREEN: a fold that derives `day` through local time (`time.localtime`)
   gives different `memory_usage_daily` rows under the two zones on this fixture.
7. **Exactly-once.** Kill the fold between the counter update and COMMIT (an injected fault in
   the transaction): after restart, every count equals the number of events (no loss, no double).
8. **Global route** (d8e). A global hit and a global `used` (21.1 AC-11c's note) from a project
   session increment the GLOBAL store's row for that name (`lifetime_hits == 1`,
   `used_focus_note == 1`); the project store's fold reports two `scope=global` skips and writes
   nothing for them.
9. **Floor.** A never-recalled memory has `recency_effective > 0`. With the clock advanced 10
   half-lives, a memory with 1 hit and 1 use has `recency_effective == floor > 0` and unchanged
   lifetime columns. A feedback memory, a `type: user` memory and a `type: guardrail` memory with
   no `rel:` edge each never rank below `asserted_floor`; a `type: project` memory with no `rel:`
   edge and no protection does (round-3 #m-1).
10. **RETIRED (d9ay) with R6.** No test is written for it, and it is not in the test list.
    Reason: R6 (rotation dropped, no producer of diverged slots; bug-113 breaks `replica_merge`).
    Original text, kept as history: "**Slot merge.** Two slots with diverging `memory_usage` rows
    merge to the R6 rule's row."
11. **Torn tail.** A log whose last line has no newline: the fold stops before it and reads it
    whole on the next tick.
12. **Lock holds.** 1,000 events fold in EXACTLY 2 batch `bind` holds (batch size 500),
    measured with 23.2's recorder on a real `_FairLock`; every batch releases. The count is
    asserted structurally (`holds == 2`; round-9 #m9-6), so a one-hold fold fails on any machine
    speed; a finalize hold, if the fold takes one, is recorded under its own label and asserted
    as exactly one, outside the 2. **Hold length** (round-8 #nm-5): the run's 23.1
    `RunResult.max_hold_s` ([[task-23.1-queue-and-drain#r1]], R1 item 5) is ≤ 0.5 s, and is
    within 50 ms of the recorder's largest measured hold for the same run (the two are
    different clocks; the tolerance is 23.1 AC-19's). The fold's holds take the same
    `_store_lock` as `_op_memory_recall` (`daemon.py:6108`), whose per-prompt hook budget is 5 s
    (21.1 R3); 0.5 s keeps one fold hold at a tenth of it. The bound is stated here for this
    task's fold; who owns bounded holds in general stays plan 23's (d9az).
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
    sandbox): every `delivered` memory event lands on `("intuition", "project", name)`. Three
    extra events, each with its expected class stated (round-3 #s-3):
    - (x) `root` inside this sandbox store, `cwd` = `/private/var/folders/x/pytest-of-u/pytest-7/t0`
      (an in-process emission from a pytest `tmp_path` cwd): `attributed`, FOLDED (+1 hit);
    - (y) `root` and `cwd` both under `/private/var/folders/x/pytest-of-u/pytest-7/t0`:
      `test_artifact`, skipped and counted;
    - (z) `root` under ANOTHER `/tmp/rmx-*` sandbox, `cwd` inside this sandbox: `test_artifact`,
      skipped and counted.
    A test asserts that every field the fold reads is a member of
    `telemetry.RECALL_EVENT_FIELDS_V1`, and that the fold module calls
    `row_provenance(…, source="events")` and holds no `cwd` / `root` / channel check of its own.
17. **Read-time parameters** (d9e; round-3 #s-2). Folding 50 events over 20 days, then scoring
    with `w_e = 5`, `base = 0.1`, and `H = 7` instead of the defaults: the stored rows of both
    tables are byte-identical before and after, and each score equals the value the test computes
    INDEPENDENTLY from its own list of the 50 events (each event decayed from its day's `mid` to
    `t` under the new `H`), to 1e-9 relative. The same check under `H = 28`.
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
    - (RETIRED, d9ay: "`replica_merge` keeping the A-side row (AC-10)"; R6 and AC-10 are
      retired, so this mutation has no test to fail);
    - the drain taking one hold per event (AC-12);
    - (round 8) the fold committing all 1,000 events in one hold (AC-12: `holds == 2` fails,
      structurally; round-9 #m9-6), or the batch size raised so one hold exceeds 0.5 s (AC-12:
      `max_hold_s` over the bound);
    - weights applied at fold time (AC-17: stored rows change);
    - any decayed value stored at fold time, or `H` read at fold time (AC-17 under `H = 7`: the
      score disagrees with the independent computation; AC-6: batchings differ);
    - `merge_fn` keeping the LAST value for a key instead of summing (AC-3; AC-6's batch-of-200
      run);
    - the classifier keyed on `cwd` instead of `root` (AC-16: event x skipped; the `cwd` fallback
      for rows without `root` is 21.1 AC-7's, since every v1 event carries `root`);
    - `reader_root` passed as the live root in the sandbox (AC-16: every own event skipped);
    - the fold carrying its own malformed / channel check instead of `row_provenance`'s (AC-16's
      no-own-check assertion);
    - the user-asserted class dropped from the asserted floor (AC-9: a `type: user` memory at
      10 half-lives below `asserted_floor`);
    - `day` derived through local time, or `mid(day)` through `time.mktime` (AC-6's two-zone
      replay differs);
    - a zone-less or local `ts` folded instead of rejected as `malformed` (21.1 AC-7 event g;
      AC-16's no-own-check assertion keeps the rule in `row_provenance`).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/store.py` | the `memory_usage` and `memory_usage_daily` tables (migration, raw per-evidence integer columns), batch upsert (sum / min / max) |
| `src/refmatrix/memory_usage.py` (new) | the fold consumer (`TailLog` + `row_provenance`), the read-time `score()` with `DEFAULT_SCORE_PARAMS` (the ONE decay/floor library) |
| `src/refmatrix/hooks.py` | the `PRECOMPACT_STDOUT_DELIVERED` constant (value set by 19.5 R1) |
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

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan19-21-spec-rereview-r3-6091648]] and [[plan-review-2026-10-14#t9-approvals]]
(d9k).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r3-6091648]]

| finding / decision | answered at |
|---|---|
| round-3 #s-2 (a sum `merge_fn` cannot carry per-event decay; `H` baked in at fold time; clock-skewed events) | R1 (two raw tables; `memory_usage_daily` per UTC day; no stored decayed value; round-2 `recency_*` withdrawn); R5 (`key_fn` with `day`; sum / min / max merge); R6 (merge rule for both tables); R7 (fold adds only; recency computed at read time from daily counts under the read-time `H`; skew weighs ≤ 1; the 30·H read cut and day quantisation stated); AC-6 (three batchings + reordered log, exact), AC-17 (`H` varied, independent computation); mutations |
| round-3 #s-3 (19.2 side: two test bases; vacuous `cwd` mutation; `malformed` in the reader) | R5 (`row_provenance(…, source="events")` decides `test_artifact` and `malformed`; root-keyed); AC-16 (events x, y, z with stated classes; no own check); mutations |
| round-3 #m-1 (stale "pending" ADR wording; user-asserted floor class) | R7 (d9k: approved at `3021cd6`; user-asserted = `metadata.type` `user` / `guardrail`); AC-9; mutation |
| d9k (ADR-0004 amendment approved) | R7 |
| cross-plan: 21.1 R5 signature | R5 uses `telemetry.row_provenance(row, *, reader_root, source="events")` exactly as 21.1 R5 states it |

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan19-21-spec-rereview-r4-878647c]] #s-2 and d9r of
[[plan-review-2026-10-14#t11-approvals]]. Code facts re-read at HEAD `39dffbb`: every timestamp
writer stamps local naive `time.strftime("%Y-%m-%dT%H:%M:%S")` (`telemetry.py:281`, `:329`,
`:425`; `stm.py:260`).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r4-878647c]]

| finding / decision | answered at |
|---|---|
| round-4 #s-2 (`day` = "UTC date" of a zone-less local `ts`) | R1 (`ts` UTC by 21.1 R10's contract, zone-less `ts` malformed by 21.1 R5; `day` = `ts[:10]`, no conversion at fold time; `first_seen` / `last_seen` string order = time order); R7 (`mid(day)` via `calendar.timegm`); AC-6 (two-zone replay across the 2026-11-01 fall-back hour and UTC midnights, with a recorded pre-check); mutations. The producer side: [[task-21.1-context-usage-telemetry#rev-round-5]] |
| d9r (user-asserted = `metadata.type` `user` or `guardrail`) | R7 asserted floor (already so since round 3); AC-9; mutation. Unchanged |

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers d9ay of [[plan-review-2026-10-14#t12-approvals]] (raised by the plan-23/17 round-7
re-review, #ns-x-r7-1): d9ao's retirement of 23.1 R8 / AC-13 extends to this task's slot-merge
path. No round-7 plan-19/21 finding names 19.2. Code facts read at write time at HEAD `77ac38f`:
`daemon.py:2814-2828` (`_refresh_replica_now`, a no-op); bug-113's registry row (open; the
`init_catalog` target lacks `entities.vectors_partition`).

rel: implements -> [[plan-review-2026-10-14#t12-approvals]]
rel: derives-from -> [[task-23.1-queue-and-drain#r8]]

| finding / decision | answered at |
|---|---|
| d9ay (19.2 R6 / AC-10 merge memory-usage rows through `replica_merge`, which nothing feeds and bug-113 breaks) | R6 RETIRED (reason, original text kept, revival conditions); AC-10 RETIRED (original text kept); the AC-10 mutation marked retired; R1 `first_seen` (slot merge no longer claimed); [[#files-to-modify]] (`replica_merge.py` row removed). Older revision tables that cite R6 / AC-10 are history and keep their text |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]] #nm-5 (19.2's fold hold is bounded in number,
not in length, against the recall it competes with) and #nm-7 (one cite). Code facts read at
write time at HEAD `23ad703`: `daemon.py:2862-2876` (`_refresh_replica_now`), `:6067`
(`_op_memory_recall`), `:6108` (its `_store_lock` hold); 23.1 R1 item 5's `RunResult.max_hold_s`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]
rel: depends-on -> [[task-23.1-queue-and-drain]]

| finding / decision | answered at |
|---|---|
| round-8 #nm-5 (19.2 side: AC-12 bounds the number of holds, not their duration; the fold competes with `_op_memory_recall` for `_store_lock`) | AC-12 (`RunResult.max_hold_s` ≤ 0.5 s, equal to the recorder's largest hold; the bound's ownership stays plan 23's, d9az); mutation |
| round-8 #nm-7 (`daemon.py:2814-2828`) | R6 (`:2862-2876`, read at `23ad703`) |

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan19-21-spec-diffcheck-r9-ebccb20#m9-6]]. Edit-level; no decision.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]]

| finding | answered at |
|---|---|
| r9 #m9-6 (`max_hold_s` "equals" the recorder across two clocks; the one-hold mutant killed only by timing) | AC-12 (`holds == 2` asserted structurally, a finalize hold labelled apart; `max_hold_s` within 50 ms of the recorder, 23.1 AC-19's tolerance); mutations (the one-hold mutant now fails on the count) |
