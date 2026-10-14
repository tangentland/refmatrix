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
> Status: Pending (revision round 2, 2026-10-14: ranges amended per ns23-1 and d9d, PROPOSED for
> the user's confirmation before the run; see [[#rev-round-2]])
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
   - **Replay (the verdict workload):** the cliquet store's most recent write events from the
     copied `facts.log` (count recorded), each mapped to ONE transaction over the SQL shapes above.
     Transactions are dealt to threads by a hash of their row key (the entity's `(partition_id,
     kind, name)`, or the link's `(src, linkage, dst)`), so every write to one key stays on one
     thread in log order. The shared fragment rows are the only cross-thread contention by design,
     and every fragment change is a single bit owned by one link key, so the end state does not
     depend on the interleaving (R6).
   - **Hot rows (context only):** every thread updates the same 100 existing entities. Reported,
     never used for the verdict.
   Lance and the `content_rank` caches are out of scope (Option A #risk says they keep their own
   locks); the report says so. The PERSISTED fragment row is in scope (R2). The IN-MEMORY
   fragment cache is binding state (bug-105): under Option A it must be per-op or keyed by
   partition, which is a correctness item for the Option A plan, not a number this task measures
   (R7). {#r3}
4. **R4 Runs.** N ∈ {1, 2, 4, 8} writer threads; three runs per N; each run either drains the
   replay or stops at 60 s. A conflict (`duckdb.TransactionException` with "Conflict") is retried
   once; a second conflict is counted as a failed transaction. {#r4}
5. **R5 Metrics, per run.** Committed write transactions per second; conflict rate (conflicted /
   attempted transactions); failed transactions; p95 transaction latency; and ART / internal errors:
   any `duckdb.FatalException`, `duckdb.InternalException`, or an error text naming an ART index,
   during the run OR during R6's integrity pass. A conflict on a `bitmap_fragments` row is counted
   separately as well as in the total. {#r5}
6. **R6 Integrity pass after every run.** `CHECKPOINT`; close; reopen; full scan of every indexed
   table; `SELECT partition_id, kind, name, COUNT(*) … HAVING COUNT(*) > 1` on `entities` returns 0
   rows; and the end state equals the EXPECTED state (ns23-1 item 4).
   - **Expected state, defined.** Before the measured runs, one reference run applies the same
     transaction list serially, in log order, on a fresh copy. Because writes are dealt by key
     (R3), a correct concurrent run reaches the same state whatever the interleaving. A failed
     transaction (R4) is re-applied serially after the run ends, so expected and actual cover the
     same set.
   - **Compared:** per-table row counts, and a content hash per table (`entities` over
     `(partition_id, kind, name)`; `entity_links` over its key; `bitmap_fragments` over
     `(partition_id, linkage, blob)`). Any difference is `integrity_mismatch`, a lost or duplicated
     write. {#r6}
7. **R7 Output.** Raw rows to `workflow/review-output/option-a-measure-<date>.jsonl` (gitignored
   evidence); the verdict, the ranges below, the replay size and the hot-row numbers appended to
   [[exploration-storage-concurrency-redesign#measure]] item 4. The same append adds one line to
   the exploration's Option A store-state audit: the in-memory fragment cache
   (`Store._fragments` / `_dirty_fragments`) is binding state that a per-op handle must own
   (bug-105, nb23-1). {#r7}

## Go/no-go ranges (pre-registered) {#ranges}

**PROPOSED, for the user's confirmation before the run (d9d).** Amended in revision round 2 per
ns23-1; the user confirms or changes these numbers before the first measured run (AC-1), and after
that they are frozen.

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

1. The ranges table is confirmed by the user (quoted, dated) and committed BEFORE the first
   measured run; the commit that adds the first `option-a-measure-*.jsonl` reference is later than
   the confirmation commit (checked by `git log`). {#ac-1}
2. Every run has an R6 integrity row; a run with no integrity row is a failed run, not a pass.
   {#ac-2}
3. Self-check of the error detector (pre-registered): a run against a copy whose `entities` unique
   index is dropped and a duplicate row inserted makes R6's duplicate query non-empty, and the
   verdict code returns NO-GO. A detector that cannot fire would return GO on a corrupt copy.
   {#ac-3}
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
   NO-GO FAILS. {#ac-7}

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

| finding / decision | answered at |
|---|---|
| ns23-1 item 1 (workload omits `bitmap_fragments`) | [[#r2]], [[#r3]], [[#r5]], [[#ac-6]] |
| ns23-1 item 2 (binding removal coupled to throughput) | [[#ranges]] "What this table decides", GO-serial row |
| ns23-1 item 3 (an error at N=1 is a broken run) | [[#ranges]] INVALID row, [[#ac-7]] |
| ns23-1 item 4 (expected counts; "worst of three") | [[#r3]] (dealing by key), [[#r6]], [[#ranges]] definitions |
| ns23-1 item 5 (live stat fails on normal activity) | [[#r1]], [[#ac-5]] |
| d9d (amend first, then present for confirmation) | [[#ranges]] (marked PROPOSED), [[#ac-1]] |
| nb23-1 (Option A store-state audit lists the fragment cache) | [[#r3]], [[#r7]] |
| nm17-2 (plan-17 names GO-serial) | [[#ranges]] GO-serial consequence |
