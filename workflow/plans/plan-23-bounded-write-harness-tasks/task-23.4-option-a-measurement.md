---
gmd: "0.1"
id: task-23.4-option-a-measurement
title: "Task 23.4: Option A measurement #4 (one writer thread vs N per-op cursor writers), with go/no-go ranges written before it runs"
tags: [task, measurement, duckdb, concurrency, option-a, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-15
---

# Task 23.4: measure Option A's concurrency before plan-23's code lands {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending. Ranges CONFIRMED by the user 2026-10-14 (d9l); procedure corrected under the
> confirmed numbers 2026-10-14 (d9m: integrity by name, no 60 s cap, retry in place, pinned
> workload, ordered runs, positive control) and corrected AGAIN (d9y: dependency-ordered dealing
> across threads, a differential dead-bit check, the LIVE log's `st_birthtime`; ranges
> unchanged), and corrected a third time (d9ap, 2026-10-15: dangling `entity_links` rows counted
> in the differential census and excluded from the by-name hash; ranges unchanged; new pin).
> Round 7 (2026-10-15, the plan-16/22 r7 re-review's m-5): the `dead-linkage` sub-class is
> classified and counted, and the cliquedb example count is corrected; ranges unchanged; the
> procedure text changed, so a NEW PIN is needed: the orchestrator records d9ba at the
> round-7 revision commit. See [[#rev-round-7]]; round 6: [[#rev-round-6]]; round 5: [[#rev-round-5]]; round 3: [[#rev-round-3]]; round 2:
> [[#rev-round-2]].
> Depends on: — (runs in parallel with 23.0; gates nothing in plan-23)
> Feeds: the d2b revisit (plan-17's per-dataset Lance lock; whether Option A becomes a plan)

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: implements -> [[exploration-storage-concurrency-redesign#measure]]
rel: derives-from -> [[exploration-storage-concurrency-redesign#option-a]]
rel: derives-from -> [[plan-review-2026-10-14#t2]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: related-to -> [[feedback_causal_story_before_evidence]]
rel: related-to -> [[feedback_generated_data_off_watched_tree]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns23-1]]
rel: implements -> [[plan-review-2026-10-14#t9]]
rel: implements -> [[plan-review-2026-10-14#t9-approvals]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns23-r3-4]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#nm23-r3-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#ns23-r4-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#nm23-r4-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3#ns23-r6-4]]
rel: implements -> [[plan-review-2026-10-14#t12-approvals]]
rel: derives-from -> [[bsd-plan16-22-spec-rereview-r7-331b414#m-5]]
rel: related-to -> [[task-22.1a-provenance-free-classes#r1-dangling]]

## Why {#why}

d2b keeps plan-23 first with the `bind(batch)` seam and does not fold Option A in. d2e runs
Option A's measurement #4 in Wave 1, in parallel with 23.0, so the Option A question has data
before plan-23's code lands. The decision-log review (#s-2, #b-6 item 2) found the measurement had
no owner, no pre-registered rule and a revisit trigger ("when Option A lands") that nothing
schedules. #t8-amendments: this task owns it, its ranges are written here BEFORE the run, and the
d2b revisit is triggered by THIS task's verdict.

23.1 does NOT wait for this task: `bind(batch)` is the interface either outcome uses (today a lock
plus `with_partition`, under A a per-op cursor handle). {#why-body}

## Requirements {#requirements}

1. **R1 Sandboxed copy.** The input is a COPY of the cliquet store's lock-free read snapshot
   (`catalog.read.duckdb`, the store resolved from the registered daemon list at run time) AND a
   copy of its `facts.log` (the replay source, R3), both copied into a short tmp dir OFF every
   watched tree in a first "copy" phase. Never the active writer slot, never `Store()` on a live
   root, no `rmx` call, no socket. After the copy phase the script installs 23.0's audit hook (or,
   before 23.0 lands, the same hook copied into the script) with a deny set of every store root in
   the registered daemon list and every socket; from then on it may open nothing outside its tmp
   dir except read-only Python imports. {#r1}
2. **R2 The prototype.** `eval/option_a/measure_cursor_writers.py` opens ONE `duckdb.connect` on
   the copy and gives each writer thread its own `con.cursor()`. It never opens a second
   `duckdb.connect` on the same file (the "different configuration" `ConnectionException`, Option A
   #risk). Each thread runs explicit `BEGIN … COMMIT` transactions issuing the SQL shapes of the
   real write paths (`upsert_entity`'s `INSERT … ON CONFLICT`, `entity_links` inserts, `UPDATE` of
   existing entity rows, row deletes) AND the `bitmap_fragments` upsert (ns23-1 item 1): every
   replayed transaction that adds or removes a link also reads its `(partition_id, linkage)`
   fragment row, sets or clears the bit with pyroaring, and upserts the re-serialized blob in the
   SAME transaction, as 23.1 R1.3 does inside every batch. That row is shared by every link of
   one linkage in one partition, so it is the most contended row in Option A, and leaving it out
   would bias the verdict toward GO. The prototype is not product code and lives in `eval/`, not
   `src/`. No number it produces is reported as refmatrix performance (the benchmark-path rule):
   it measures DuckDB's behaviour on this schema. {#r2}
3. **R3 Two workloads.**
   - **Replay (the verdict workload), pinned (d9m, d9y).** The LAST 20,000 write events, in file
     order, of the copied `facts.log` whose `ts` is later than the LIVE `facts.log`'s
     `st_birthtime`. A `facts.log` compaction replaces the file by atomic rename, so the live
     file's birth time is the last compaction's time; everything before it in the file is a
     `dump_catalog_to_log` snapshot in dump order (with historical `ts` values,
     `store.py:7264-7275`), not a workload, and is never replayed.
     - **Whose birth time (d9y; ns23-r4-3 item 3).** The copy is a new inode, so its own
       `st_birthtime` is the copy time; no event is later than it, and a window read from the
       copy is always empty. The copy phase therefore reads `os.stat(<live facts.log>).st_birthtime`
       (a `stat`, not an open, so AC-5's two-open count is unchanged) immediately before it opens
       the live file to copy it, and records it in the jsonl as `live_birthtime`, with the live
       inode. The copy's own stat is never used for the window. If the live inode changed between
       the stat and the open (a compaction in that gap), the copy phase retries once and then
       stops as INVALID.
     - The copy phase records the live birth time, the file size and the count of qualifying
       events. Fewer than 20,000 qualifying events makes
     the measurement INVALID (no verdict; the count is reported, and the copy is retaken later).
     The count is the script's `--events` parameter; its verdict value is 20,000 and `--verdict`
     refuses a jsonl recorded with any other value. The smoke test passes a small value.
     Each event maps to ONE transaction over the SQL shapes above.
     - **Dealing in dependency order across threads (d9y; ns23-r4-3 item 1).** Transactions are
       dealt to threads by a hash of their PRIMARY row key's NAMES (the entity's `(partition,
       kind, name)`, or the link's `(src name, linkage, dst name)`), AND every transaction carries
       the set of entity NAMES it touches: an entity event touches its own; a link event touches
       both ends (`src` and `dst`, each as `(partition, kind, name)`); a delete touches its
       entity. A **per-name log-position barrier** orders them across threads: a transaction at
       log position `i` does not BEGIN until every transaction at a position `j < i` that touches
       any of its names has COMMITTED (its retries included). So an entity's create precedes
       every link to it, and a later delete follows every earlier link, whichever threads they
       were dealt to. Per-name log order then holds for every name a transaction touches, which
       makes the end state interleaving-independent BY NAME by construction. The barrier is
       built once before the run: for each transaction, the log positions of its nearest earlier
       transaction on each of its names; plus one `threading.Event` per position, set at its
       commit. A waiting thread blocks on its predecessors' events. A wait is not a conflict and
       is not counted in R5's conflict rate; total barrier wait per thread is recorded beside it.
     - The shared fragment rows remain the only cross-thread WRITE contention by design: every
       fragment change is a single bit owned by one link key.
     What a correct concurrent run MAY still differ in is the entity ids: `entities.id` is
     `DEFAULT nextval('seq_entities_id')` (`duckdb_catalog.py:50`), DuckDB sequences are not
     transactional, so a conflicted or retried create burns an id, and concurrent creates take ids
     in commit order. Every bit of a fragment (`concept << 32 | entity`) and every `entity_links`
     key embeds those ids. So the end state is interleaving-independent BY NAME, not by id, and R6
     compares by name (ns23-r3-4 item 1).
   - **Hot rows (context only):** every thread updates the same 100 existing entities. Reported,
     never used for the verdict.
   Lance and the `content_rank` caches are out of scope (Option A #risk says they keep their own
   locks); the report says so. The PERSISTED fragment row is in scope (R2). The IN-MEMORY
   fragment cache is binding state (bug-105): under Option A it must be per-op or keyed by
   partition, which is a correctness item for the Option A plan, not a number this task measures
   (R7). {#r3}
4. **R4 Runs (d9m).** N ∈ {1, 2, 4, 8} writer threads; three runs per N; every run drains the
   whole pinned workload, as the serial reference does. There is NO 60 s cap (ns23-r3-4 item 2:
   a stopped run leaves each thread at a different log position, so no expected state exists for
   it). A watchdog of 10 × the N=1 median drain time only detects a hang: a run that trips it is
   INVALID, never a verdict.
   - **Retry in place, in key order (ns23-r3-4 item 3).** A conflict (`duckdb.TransactionException`
     with "Conflict") rolls back and the SAME thread retries the SAME transaction at once, before
     any later transaction of its stream, up to K = 5 attempts. Every attempt that conflicts is
     counted (R5's conflict rate). Nothing is re-applied after the run, so no key's transactions
     are ever reordered.
   - A transaction that still conflicts on its 5th attempt is `retry_exhausted`: its key's stream
     halts there (later transactions of that key are not applied), the run continues for the
     other keys, and the end state then differs from the reference, which R6 reports as
     `integrity_mismatch`. A transaction whose barrier waits on a halted predecessor is halted
     too (recorded as `blocked_by_exhausted`), so the run ends instead of waiting forever. At N =
     1 that is INVALID; at N > 1 it is NO-GO, by the confirmed rows
     as written (a writer that cannot commit after 5 in-place retries is not a viable concurrent
     writer). {#r4}
5. **R5 Metrics, per run.** Committed write transactions per second; conflict rate (conflicted /
   attempted transactions); failed transactions; p95 transaction latency; and ART / internal errors:
   any `duckdb.FatalException`, `duckdb.InternalException`, or an error text naming an ART index,
   during the run OR during R6's integrity pass. A conflict on a `bitmap_fragments` row is counted
   separately as well as in the total. {#r5}
6. **R6 Integrity pass after every run.** `CHECKPOINT`; close; reopen; full scan of every indexed
   table; `SELECT partition_id, kind, name, COUNT(*) … HAVING COUNT(*) > 1` on `entities` returns 0
   rows; and the end state equals the EXPECTED state (ns23-1 item 4).
   - **Expected state, defined.** Before the measured runs, one reference run applies the same
     pinned transaction list serially, in log order, on a fresh copy. Because writes are dealt by
     key behind the per-name barrier (R3, d9y) and retried in place (R4), a correct concurrent run reaches the same state BY NAME
     whatever the interleaving. Nothing is re-applied after a run.
   - **Compared BY NAME, never by sequence-assigned id (d9m; ns23-r3-4 item 1).** Per-table row
     counts, and an order-independent content hash per table over name tuples resolved through
     that run's OWN `entities` / `partitions` / `linkage_types` tables:
     - `entities`: `(partition name, kind, name)`;
     - `entity_links`: `(entity's partition name, entity kind, entity name, linkage name,
       concept's partition name, concept name)` plus `weight`, over the ALIVE rows only. A
       **dangling** row is EXCLUDED from this hash explicitly (d9ap; ns23-r6-4). The resolver
       CLASSIFIES each row before it resolves it, in the order and with the predicate
       `Store.repair_fragments` applies (`store.py:4377-4395`), which is plan-22's table
       ([[task-22.1a-provenance-free-classes#r1-dangling]]):
       1. **entity-dead**: `entity_id` absent from `entities` (whatever its linkage and
          concept; the repair's `links_dead_entity`);
       2. else **`dead-linkage`** (round 7, r7 plan-16/22 m-5): `linkage_id` absent from
          `linkage_types` (the repair counts it under `links_skipped` only and never checks its
          concept). It has no linkage NAME to resolve, so it is counted under its raw
          `linkage_id`;
       3. else **concept-dead**: `concept_id` in neither `entities` nor `concepts` (the
          repair's `links_dead_concept`).
       A row in any of the three goes to the census below, never into the hash. The resolver
       neither raises on such a row (which would make every copy of a live snapshot INVALID at
       N = 1, forever: bug-111 established that live catalogs hold them; on cliquedb on
       2026-10-14, 5,298 entity-dead rows and 1 concept-dead row, the r6/r7 plan-22 recount
       ([[bsd-plan16-22-spec-rereview-r7-331b414#spot-check]]), correcting this spec's round-6
       "8 dead-concept", and 0 `dead-linkage` rows) nor drops it silently by an inner join
       (which would make a run that creates or loses dangling rows invisible);
     - `bitmap_fragments`: every bit of every blob decoded to `(concept_id, entity_id)` and
       resolved to `(row's partition name, linkage, concept name, entity kind, entity name)`.
     - **Dead bits and unknown-partition rows are DIFFERENTIAL, not absolute (d9y; ns23-r4-3
       item 2).** A copy of a live snapshot already holds bits whose id resolves to no entity
       (about 410 dead-concept bits on the census copy, the bug-105 rows under a `partition_id`
       with no `partitions` row, and bits `purge_entity`'s bound-partition sweeps keep
       regrowing). So a **census** counts, per `(partition name or unknown id, linkage)`, the
       bits whose entity is absent from `entities` or whose concept is in neither `entities` nor
       `concepts` (the bug-105 hotfix's alive predicate), and the rows under an unknown
       `partition_id`, and records the dead bits whose ids the workload never touches as an id
       set. **The census also counts dangling `entity_links` rows (d9ap; ns23-r6-4)**: per
       linkage name, the entity-dead rows and the concept-dead rows separately (the split
       `repair_fragments` reports as `links_dead_entity` / `links_dead_concept` at 0.78.1),
       and per raw `linkage_id` the `dead-linkage` rows (round 7), and
       records the dangling rows whose ids the workload never touches as a set of `(entity_id,
       linkage_id, concept_id)` triples. The workload's replayed row deletes are why this half
       exists: a delete shape that does not also delete the entity's links creates dangling rows,
       and a correct concurrent run creates exactly the reference run's. It runs on the fresh copy before the reference run (the pre-run census, recorded),
       after the reference run, and after every measured run. A measured run is a mismatch iff
       its post-run census differs from the REFERENCE run's post-run census (the bit counts, the
       dangling-link counts, and both untouched-id sets). Dead bits the pre-run census already held are therefore never a
       mismatch by themselves; a dead bit that a measured run creates and the reference does not
       is. The copy is not repaired before the run: its pre-run state is the measurement's input.
     Any difference is `integrity_mismatch`, a lost or duplicated write. {#r6}
7. **R7 Output.** Raw rows to `workflow/review-output/option-a-measure-<date>.jsonl` (gitignored
   evidence); the verdict, the ranges below, the replay size and the hot-row numbers appended to
   [[exploration-storage-concurrency-redesign#measure]] item 4. The same append adds one line to
   the exploration's Option A store-state audit: the in-memory fragment cache
   (`Store._fragments` / `_dirty_fragments`) is binding state that a per-op handle must own
   (bug-105, nb23-1). {#r7}

## Go/no-go ranges (pre-registered) {#ranges}

**CONFIRMED by the user, 2026-10-14 (d9l: "2 - yes"); frozen.** The numbers below were amended
in revision round 2 per ns23-1 and d9d, then confirmed as d9l. The procedure they are applied to
(R3's pinned workload, R4's drain-to-completion and in-place retry, R6's by-name comparison, AC-3's
positive control, AC-1's run order) was corrected under those same numbers and acknowledged by the
user as d9m ("a - yes"). The procedure was corrected again under the same numbers as d9y ("1 -
agree": dependency-ordered dealing, a differential dead-bit check, the live log's birth time;
[[#rev-round-5]]). It was corrected a third time under the same numbers as d9ap (2026-10-15,
"all four - i agree": dangling `entity_links` rows counted in the differential census and
excluded from the by-name hash; [[#rev-round-6]]), which moves the spec pin ([[#ac-1]]). Neither
the numbers nor the procedure change after this point without a new user decision and a new spec
pin ([[#ac-1]]) (nm23-r3-1: one status).

**Definitions** (ns23-1 item 4):
- `T(N, k)`: committed transactions per second of run `k ∈ {1, 2, 3}` at N threads.
- **speedup** = `min_k T(4, k) / median_k T(1, k)`: the WORST N=4 run against the typical serial
  run.
- **conflict rate** = `max_k` of (conflicted / attempted transactions) over the three N=4 runs,
  counting the fragment-row conflicts (R5).
- Errors and integrity are checked at EVERY N, every run.

**What this table decides** (ns23-1 item 2): concurrency only, that is whether Option A's
concurrent appends are proposed. It does NOT decide Option A's binding-removal half (per-op
handles, no shared `_partition_id`, the fragment cache per op). That half is the cure for the
bug-098 / bug-105 class and is decided on correctness, in its own proposal, whatever this table
returns.

Rows are checked top to bottom; the first that matches is the verdict.

| condition | verdict | consequence |
|---|---|---|
| any error, `integrity_mismatch`, or non-empty R6 duplicate query at **N = 1** | INVALID | the run is a test failure (a broken copy, a replay-mapping bug, or a DuckDB bug at one writer), not evidence about concurrency; fix and re-run; no verdict is recorded (ns23-1 item 3) |
| any ART / internal error, `integrity_mismatch`, or non-empty duplicate query at **N > 1** | NO-GO | Option A's concurrency is closed and recorded in the exploration; `bind` stays the only write interface; the d2b revisit closes with this data; plan-17 keeps `bind`, no per-dataset Lance lock |
| conflict rate > 5 %, or speedup < 1.1× | NO-GO | as above |
| conflict rate ≤ 1 % and speedup ≥ 1.5× | GO | Option A's concurrency is proposed as a plan for Wave 2 (per-op cursor handles behind `bind`, concurrent appends, conflict retry); the d2b revisit re-asks plan-17's per-dataset lock question under A |
| otherwise (conflict 1-5 %, or speedup 1.1-1.5×) | GO-serial | concurrency is not proposed now: the gain does not pay for the conflict handling. For plan-17 this is the same as NO-GO (17.1 keeps `bind`, no per-dataset Lance lock). The exploration records the numbers so a later re-measure can be compared |

{#ranges-body}

## Acceptance criteria {#acceptance}

1. **Runs are ordered after the confirmation, against a NAMED spec sha (d9m, d9y; ns23-r3-4
   item 5, nm23-r4-2 item 3).** The ranges (d9l, logged at `3021cd6`, committer time
   2026-10-14T13:15:27-07:00) and the procedure (d9m, logged at `5a8bf29`, 13:31:33-07:00;
   corrected again as d9y, logged at `ef4fa7c`, 14:15:18-07:00) are confirmed.
   - **The spec pin.** The procedure text that implements d9y is this file as committed by the
     round-5 revision. That commit's sha cannot be written into the file it commits, and a
     `git log -S` search stops returning one commit as soon as a later revision adds or
     removes the searched string, so neither is the pin. Instead, the commit that lands this
     revision ALSO adds one row to the decision log ([[plan-review-2026-10-14]]) naming the
     literal sha: "23.4 procedure pin = `<sha>` (d9y text)". That row is the pin; a later
     procedure change needs a new user decision AND a new pin row.
   - **Pin superseded (d9ap, round 6).** d9ad pinned `d454bf9` (the d9y text). d9ap changes the
     procedure (R6's dangling-link rule, AC-3's fixture), so `d454bf9` is no longer the pin and
     a jsonl recorded against it is refused. **pin: the round-6 revision commit, recorded in
     plan-review as d9as.** `--spec-pin` takes the sha in the d9as row; everything else in this
     AC is unchanged.
   - The check orders RUNS, not commits: the `ts` of the FIRST row of every
     `option-a-measure-*.jsonl` is later than the pinned commit's committer time, and every row
     records `git log -1 --format=%H -- <this file>` at run start. `--verdict` takes the pinned
     sha as a required literal argument (`--spec-pin <sha>`, copied from the decision row) and
     refuses a jsonl whose first row is earlier than that commit, or whose recorded spec sha is
     not that literal value. {#ac-1}
2. Every run has an R6 integrity row; a run with no integrity row is a failed run, not a pass.
   {#ac-2}
3. Self-check of the error detector, both directions (pre-registered):
   - **Negative control:** a run against a copy whose `entities` unique index is dropped and a
     duplicate row inserted makes R6's duplicate query non-empty, and the verdict code returns
     NO-GO. A detector that cannot fire would return GO on a corrupt copy.
   - **Positive control (d9m, d9y; ns23-r3-4, ns23-r4-3):** the smoke test at N = 2 over a
     workload that CREATES entities and contains one forced conflict (two threads made to update
     one shared fragment row in overlapping transactions) AND one cross-thread dependency pair
     (a create of entity `X` dealt to thread 1, followed in log order by a link to `X` dealt to
     thread 2, and a later delete of another entity `Y` dealt to thread 2 after a link to `Y` on
     thread 1; the test asserts the dealing put them on different threads, so the case is real).
     It retries in place, honours the barrier, and passes R6 with NO `integrity_mismatch`,
     although its entity ids differ from the serial reference's (the test asserts they differ).
     The smoke fixture's catalog also carries 3 pre-existing dead bits, one row under an
     unknown `partition_id`, and 3 pre-existing dangling `entity_links` rows (d9ap: one whose
     entity id is in no `entities` row, one whose concept id is in neither `entities` nor
     `concepts`; round 7: one whose live entity carries a `linkage_id` with no `linkage_types`
     row AND whose concept id is also in neither table, so only the classification ORDER
     makes it `dead-linkage`); the run is still not a mismatch (the differential check), and its census reports
     all three in the untouched set, each under its own class.
     A detector that only proves it can fire is half a detector.
   - **Negative control for the differential check (d9y):** a measured run that, by a test seam,
     sets one extra bit for an entity id that does not exist reports `integrity_mismatch`
     although the copy's 3 pre-existing dead bits are the same in both runs.
   - **Negative control for dangling links (d9ap):** a measured run that, by a test seam, inserts
     one extra `entity_links` row naming an entity id that does not exist reports
     `integrity_mismatch` (its dangling-link count differs from the reference's), although the
     fixture's 3 pre-existing dangling rows are the same in both runs.
   - Mutations, each must FAIL: R6 hashing `entity_links` / fragments by id → the positive
     control reports `integrity_mismatch`; a conflicted transaction re-applied after the run
     instead of in place, on a stream with an unlink after the conflicted link → the positive
     control reports `integrity_mismatch`; the per-name barrier removed (dealing by primary key
     only) → the positive control's cross-thread pair reports `integrity_mismatch` (forced by a
     seam that delays thread 1's create until thread 2's link has been attempted); the dead-bit
     check made absolute → the positive control reports `integrity_mismatch` on its 3
     pre-existing dead bits; the dead-bit check removed → the differential negative control
     returns no mismatch; the duplicate query removed → the negative control returns GO; a
     by-name resolver that RAISES on a dangling `entity_links` row → the positive control (and
     the N = 1 reference) is INVALID, so the control FAILS; dangling rows dropped by an inner join
     with no census count → the dangling-link negative control returns no mismatch; **round 7:**
     a classifier with no `dead-linkage` rule (the linkage-name lookup raises on the dead
     `linkage_id`) → the positive control and the N = 1 reference are INVALID, so the control
     FAILS; a classifier that checks the concept BEFORE the linkage (so the `dead-linkage` row,
     whose concept is also dead in the fixture, is counted concept-dead) → the census's
     `dead-linkage` count is 0 where the fixture planted 1, and the test's assertion on the
     per-class untouched set FAILS. {#ac-3}
4. The verdict is mechanical: `measure_cursor_writers.py --verdict` reads the jsonl and prints the
   matching row of [[#ranges]]; the appended exploration text quotes that output. {#ac-4}
5. **Live untouched, by the guard, not by stat (ns23-1 item 5).** A live daemon changes the active
   slot and `facts.log` through normal activity, so size and mtime prove nothing. Instead the
   script's audit hook (R1) logs every open and connect: the log shows exactly two read-only opens
   of live paths (the snapshot and `facts.log`, both in the copy phase) and nothing else outside
   the tmp dir. Pre-registered mutation: make the replay read the LIVE `facts.log` in place after
   the copy phase; the hook must raise `SandboxViolation` and the run must abort with no verdict.
   {#ac-5}
6. **The fragment row is in the workload (ns23-1 item 1).** The jsonl of every run records the
   number of `bitmap_fragments` upserts and fragment-row conflicts; a replay whose link events
   produce 0 fragment upserts fails the run. Mutation: the replay without the fragment upsert
   FAILS this check. {#ac-6}
7. **INVALID is not NO-GO (ns23-1 item 3).** The smoke test injects one error at N=1 (a copy with
   a dropped table): `--verdict` prints `INVALID` and records no verdict. Mutation: treat it as
   NO-GO FAILS. The same holds for a pinned-workload shortfall (d9m): a fixture `facts.log` with
   fewer than `--events` events after its birth time prints `INVALID` with the count; mutation:
   replaying the pre-birth snapshot lines to make up the count FAILS. A third case (d9y;
   ns23-r4-3 item 3): a fixture "live" `facts.log` with a known birth time and 30 events after
   it is COPIED by the copy phase; the window holds those 30 events, read from the live file's
   birth time, and the jsonl's `live_birthtime` equals the fixture's. Mutation: the window read
   from the copy's own `st_birthtime` FAILS (0 events, INVALID). {#ac-7}

## Test strategy {#test-strategy}

The measurement is not a pytest run; it opens only its tmp copy (R1). The harness's own smoke test
(`tests/test_option_a_measure_smoke.py`: two threads, 20 synthetic transactions on a fixture
catalog in a tmp dir, AC-3's detector check) runs under 23.0's sandbox and lands after 23.0; until
then the measurement script sets `HOME`, `RMX_HOME` and `REFMATRIX_ROOT` into its tmp dir itself.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| d2e (measurement #4 in Wave 1, ∥ 23.0) | this file, [[#root]] header |
| #t8-amendments d2b/d2e (task 23.4; ranges before it runs; revisit = 23.4's verdict) | [[#ranges]], [[#ac-1]] |
| decision-log #s-2 (no owner, no rule, no gate; 23.1 does not wait) | [[#why]], [[#ranges]] |
| decision-log #b-6 item 2 (d2b revisit unscheduled) | [[#ranges]] consequence column |
| d2b (plan-17 through `bind`, revisit recorded) | [[#ranges]] |
| 23 #option-a (neutral, cut the seam) | [[#why]] |

## Revision round 2 (2026-10-14) {#rev-round-2}

(Round 2 cited the confirmation as "d9d"; it is d9l. d9d asked for the amendment; d9l confirmed it.)

| finding / decision | answered at |
|---|---|
| ns23-1 item 1 (workload omits `bitmap_fragments`) | [[#r2]], [[#r3]], [[#r5]], [[#ac-6]] |
| ns23-1 item 2 (binding removal coupled to throughput) | [[#ranges]] "What this table decides", GO-serial row |
| ns23-1 item 3 (an error at N=1 is a broken run) | [[#ranges]] INVALID row, [[#ac-7]] |
| ns23-1 item 4 (expected counts; "worst of three") | [[#r3]] (dealing by key), [[#r6]], [[#ranges]] definitions |
| ns23-1 item 5 (live stat fails on normal activity) | [[#r1]], [[#ac-5]] |
| d9d (amend first, then present for confirmation) | [[#ranges]] (CONFIRMED 2026-10-14), [[#ac-1]] |
| nb23-1 (Option A store-state audit lists the fragment cache) | [[#r3]], [[#r7]] |
| nm17-2 (plan-17 names GO-serial) | [[#ranges]] GO-serial consequence |

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]] and [[plan-review-2026-10-14#t9-approvals]]
(d9l, d9m).

| finding / decision | answered at |
|---|---|
| ns23-r3-4 item 1 (oracle hashes sequence-assigned ids), d9m "integrity by NAME" | [[#r3]] (what a correct run may differ in), [[#r6]] (by-name tuples), [[#ac-3]] positive control + id-hash mutation |
| ns23-r3-4 item 2 (60 s stop breaks the expected state), d9m "no 60 s cap" | [[#r4]] (drain to completion; hang watchdog = INVALID) |
| ns23-r3-4 item 3 (post-run re-apply reorders keys), d9m "retry in place, in key order" | [[#r4]] (K = 5 in place; `retry_exhausted`), [[#r6]] (nothing re-applied), [[#ac-3]] mutation |
| ns23-r3-4 item 4 (workload unpinned), d9m "size and window pinned" | [[#r3]] (last 20,000 events after the file's birth time; fewer = INVALID) |
| ns23-r3-4 item 5 (AC-1 orders commits, not runs), d9m "AC-1 orders runs" | [[#ac-1]] |
| ns23-r3-4 fix "positive control" | [[#ac-3]] |
| nm23-r3-1 (status stated three ways; d9d vs d9l) | [[#root]] header, [[#ranges]] status paragraph, [[#rev-round-2]] note |
| d9l (ranges confirmed) | [[#ranges]] (numbers unchanged) |
| d9m (procedure corrected under the confirmed numbers) | [[#r3]], [[#r4]], [[#r6]], [[#ac-1]], [[#ac-3]], [[#ranges]] status |

## Revision round 5 (2026-10-14) {#rev-round-5}

Source: [[bsd-plan23-17-spec-rereview-r4-878647c]] and [[plan-review-2026-10-14#t11-approvals]]
(d9y: the procedure corrected again; the ranges, d9l, unchanged).

| finding / decision | answered at |
|---|---|
| ns23-r4-3 item 1 (by-key dealing ignores create/delete → link dependencies), d9y "dependency order" | [[#r3]] (per-name log-position barrier), [[#r4]] (`blocked_by_exhausted`), [[#r6]] (expected state), [[#ac-3]] (cross-thread pair in the positive control; barrier-removed mutation) |
| ns23-r4-3 item 2 (absolute dead-bit check fires on any live copy), d9y "differential" | [[#r6]] (census before the reference, after the reference and after every run; mismatch = difference from the reference's census), [[#ac-3]] (dead bits in the smoke fixture; differential negative control; two mutations) |
| ns23-r4-3 item 3 (the copy's `st_birthtime` → 0 events), d9y "the LIVE log's `st_birthtime`" | [[#r3]] ("Whose birth time": `os.stat` of the live file in the copy phase, recorded as `live_birthtime`), [[#ac-7]] third case |
| nm23-r4-2 item 3 (AC-1's spec sha has nothing to compare against) | [[#ac-1]] (a decision-log pin row names the literal sha; `--spec-pin` compares against it) |
| d9l (ranges) | [[#ranges]]: unchanged |

## Revision round 6 (2026-10-15) {#rev-round-6}

Source: [[bsd-plan23-17-spec-rereview-r6-0e77da3]] and [[plan-review-2026-10-14#t12-approvals]]
(d9ap). The ranges are unchanged; the procedure changes, so the pin moves (d9ad's `d454bf9` is
superseded by the round-6 revision commit, to be recorded as d9as).

| finding / decision | answered at |
|---|---|
| ns23-r6-4 (by-name hash of `entity_links` has no rule for dangling rows; the census covers bits only), d9ap | [[#root]] header, [[#r6]] (`entity_links` hash over ALIVE rows; dangling rows classified first and excluded explicitly; census counts them per linkage, entity-dead and concept-dead, plus the untouched-triple set; mismatch rule extended), [[#ranges]] status paragraph (d9ap, pin moves), [[#ac-1]] (pin superseded: the round-6 revision commit, d9as), [[#ac-3]] (2 dangling rows in the smoke fixture; a dangling-link negative control; two new mutations: the resolver that raises, and the silent inner join) |

## Revision round 7 (2026-10-15) {#rev-round-7}

Source: [[bsd-plan16-22-spec-rereview-r7-331b414#m-5]] (assigned to plan-23's owner). The ranges
(d9l) are unchanged. The procedure TEXT changes (a third dangling sub-class in R6's resolver and
census; AC-3's fixture and mutations), so d9as's pin (the round-6 commit) is superseded: **the
orchestrator records d9ba = the round-7 revision commit as the new pin row**, and AC-1's
`--spec-pin` takes that sha. Until d9ba is recorded, no measured run is valid. The round-6
table above is unchanged history.

| finding / decision | answered at |
|---|---|
| r7 m-5 (the stale "8 dead-concept" count; no `dead-linkage` case in the dangling definition) | [[#root]] header (new pin needed), [[#r6]] (the three-class resolver in the repair's order; the count corrected to 5,298 entity-dead + 1 concept-dead + 0 `dead-linkage` on cliquedb; the census counts `dead-linkage` per raw `linkage_id`), [[#ac-3]] (a third pre-existing dangling row; two new mutations) |
