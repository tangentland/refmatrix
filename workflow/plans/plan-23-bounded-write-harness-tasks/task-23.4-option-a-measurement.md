---
gmd: "0.1"
id: task-23.4-option-a-measurement
title: "Task 23.4: Option A measurement #4 (one writer thread vs N per-op cursor writers), with go/no-go ranges written before it runs"
tags: [task, measurement, duckdb, concurrency, option-a, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-14
---

# Task 23.4: measure Option A's concurrency before plan-23's code lands {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending. Ranges CONFIRMED by the user 2026-10-14 (d9l); procedure corrected under the
> confirmed numbers 2026-10-14 (d9m: integrity by name, no 60 s cap, retry in place, pinned
> workload, ordered runs, positive control). See [[#rev-round-3]]; round 2: [[#rev-round-2]].
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
   - **Replay (the verdict workload), pinned (d9m).** The LAST 20,000 write events, in file
     order, of the copied `facts.log` whose `ts` is later than that file's `st_birthtime`. A
     `facts.log` compaction replaces the file by atomic rename, so the birth time is the last
     compaction's time; everything before it in the file is a `dump_catalog_to_log` snapshot in
     dump order, not a workload, and is never replayed. The copy phase records the birth time,
     the file size and the count of qualifying events. Fewer than 20,000 qualifying events makes
     the measurement INVALID (no verdict; the count is reported, and the copy is retaken later).
     The count is the script's `--events` parameter; its verdict value is 20,000 and `--verdict`
     refuses a jsonl recorded with any other value. The smoke test passes a small value.
     Each event maps to ONE transaction over the SQL shapes above.
     Transactions are dealt to threads by a hash of their row key's NAMES (the entity's
     `(partition, kind, name)`, or the link's `(src name, linkage, dst name)`), so every write to
     one key stays on one thread in log order. The shared fragment rows are the only cross-thread
     contention by design, and every fragment change is a single bit owned by one link key.
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
     `integrity_mismatch`. At N = 1 that is INVALID; at N > 1 it is NO-GO, by the confirmed rows
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
     key (R3) and retried in place (R4), a correct concurrent run reaches the same state BY NAME
     whatever the interleaving. Nothing is re-applied after a run.
   - **Compared BY NAME, never by sequence-assigned id (d9m; ns23-r3-4 item 1).** Per-table row
     counts, and an order-independent content hash per table over name tuples resolved through
     that run's OWN `entities` / `partitions` / `linkage_types` tables:
     - `entities`: `(partition name, kind, name)`;
     - `entity_links`: `(entity's partition name, entity kind, entity name, linkage name,
       concept's partition name, concept name)` plus `weight`;
     - `bitmap_fragments`: every bit of every blob decoded to `(concept_id, entity_id)` and
       resolved to `(row's partition name, linkage, concept name, entity kind, entity name)`; a
       bit whose id resolves to no entity is itself a mismatch.
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
user as d9m ("a - yes"). Neither the numbers nor the procedure change after this point without a
new user decision (nm23-r3-1: one status).

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

1. **Runs are ordered after the confirmation (d9m; ns23-r3-4 item 5).** The ranges (d9l, logged
   at `3021cd6`, committer time 2026-10-14T13:15:27-07:00) and the procedure (d9m, logged at
   `5a8bf29`, 13:31:33-07:00) are confirmed; the spec text that implements d9m is the commit that
   adds `#rev-round-3` to this file (`git log -S'rev-round-3' -- <this file>`). The check orders
   RUNS, not commits: the `ts` of the FIRST row of every `option-a-measure-*.jsonl` is later than
   that commit's committer time, and every row records the sha of this spec file's last commit
   at run start. `--verdict` refuses a jsonl whose first row is earlier, or whose recorded spec
   sha differs from the one the confirmation names. {#ac-1}
2. Every run has an R6 integrity row; a run with no integrity row is a failed run, not a pass.
   {#ac-2}
3. Self-check of the error detector, both directions (pre-registered):
   - **Negative control:** a run against a copy whose `entities` unique index is dropped and a
     duplicate row inserted makes R6's duplicate query non-empty, and the verdict code returns
     NO-GO. A detector that cannot fire would return GO on a corrupt copy.
   - **Positive control (d9m; ns23-r3-4):** the smoke test at N = 2 over a workload that CREATES
     entities and contains one forced conflict (two threads made to update one shared fragment
     row in overlapping transactions) retries in place and passes R6 with NO `integrity_mismatch`,
     although its entity ids differ from the serial reference's (the test asserts they differ, so
     the case is real). A detector that only proves it can fire is half a detector.
   - Mutations, each must FAIL: R6 hashing `entity_links` / fragments by id → the positive
     control reports `integrity_mismatch`; a conflicted transaction re-applied after the run
     instead of in place, on a stream with an unlink after the conflicted link → the positive
     control reports `integrity_mismatch`; the duplicate query removed → the negative control
     returns GO. {#ac-3}
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
   replaying the pre-birth snapshot lines to make up the count FAILS. {#ac-7}

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
