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
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: — (runs in parallel with 23.0; gates nothing in plan-23)
> Feeds: the d2b revisit (plan-17's per-dataset Lance lock; whether Option A becomes a plan)

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: implements -> [[exploration-storage-concurrency-redesign#measure]]
rel: derives-from -> [[exploration-storage-concurrency-redesign#option-a]]
rel: derives-from -> [[plan-review-2026-10-14#t2]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: related-to -> [[feedback_causal_story_before_evidence]]
rel: related-to -> [[feedback_generated_data_off_watched_tree]]

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
   (`catalog.read.duckdb`, the store resolved from the registered daemon list at run time), copied
   with `cp` into a short tmp dir OFF every watched tree. Never the active writer slot, never
   `Store()` on a live root, no `rmx` call, no socket. {#r1}
2. **R2 The prototype.** `eval/option_a/measure_cursor_writers.py` opens ONE `duckdb.connect` on
   the copy and gives each writer thread its own `con.cursor()`. It never opens a second
   `duckdb.connect` on the same file (the "different configuration" `ConnectionException`, Option A
   #risk). Each thread runs explicit `BEGIN … COMMIT` transactions issuing the SQL shapes of the
   real write paths (`upsert_entity`'s `INSERT … ON CONFLICT`, `entity_links` inserts, `UPDATE` of
   existing entity rows, row deletes). The prototype is not product code and lives in `eval/`, not
   `src/`. No number it produces is reported as refmatrix performance (the benchmark-path rule):
   it measures DuckDB's behaviour on this schema. {#r2}
3. **R3 Two workloads.**
   - **Replay (the verdict workload):** the cliquet store's most recent write events from its
     `facts.log` (count recorded), mapped to the SQL shapes above and dealt round-robin to the
     threads.
   - **Hot rows (context only):** every thread updates the same 100 existing entities. Reported,
     never used for the verdict.
   Lance, the pyroaring fragment buffer and the `content_rank` caches are out of scope (Option A
   #risk says they keep their own locks); the report says so. {#r3}
4. **R4 Runs.** N ∈ {1, 2, 4, 8} writer threads; three runs per N; each run either drains the
   replay or stops at 60 s. A conflict (`duckdb.TransactionException` with "Conflict") is retried
   once; a second conflict is counted as a failed transaction. {#r4}
5. **R5 Metrics, per run.** Committed write transactions per second; conflict rate (conflicted /
   attempted transactions); failed transactions; p95 transaction latency; and ART / internal errors:
   any `duckdb.FatalException`, `duckdb.InternalException`, or an error text naming an ART index,
   during the run OR during R6's integrity pass. {#r5}
6. **R6 Integrity pass after every run.** `CHECKPOINT`; close; reopen; full scan of every indexed
   table; `SELECT partition_id, kind, name, COUNT(*) … HAVING COUNT(*) > 1` on `entities` returns 0
   rows; row counts equal the replay's expected counts. {#r6}
7. **R7 Output.** Raw rows to `workflow/review-output/option-a-measure-<date>.jsonl` (gitignored
   evidence); the verdict, the ranges below, the replay size and the hot-row numbers appended to
   [[exploration-storage-concurrency-redesign#measure]] item 4. {#r7}

## Go/no-go ranges (pre-registered) {#ranges}

Evaluated on the REPLAY workload, worst of the three runs, throughput speedup = N=4 throughput /
N=1 throughput. Rows are checked top to bottom; the first that matches is the verdict. The numbers
below were written by the spec reviser on 2026-10-14 and are CONFIRMED BY THE USER BEFORE THE RUN
(listed in [[plan-23-bounded-write-harness#open-after-revision]]); after confirmation they are
frozen and the run cannot change them.

| condition | verdict | consequence |
|---|---|---|
| any ART / internal error in any run at any N, or a non-empty R6 duplicate query | NO-GO | Option A's concurrency is closed and recorded in the exploration; `bind` stays the only interface; the d2b revisit closes with this data; plan-17 keeps `bind`, no per-dataset Lance lock |
| conflict rate > 5 %, or speedup < 1.1× | NO-GO | as above |
| conflict rate ≤ 1 % and speedup ≥ 1.5× | GO | Option A is proposed as a plan for Wave 2 (per-op cursor handles behind `bind`, concurrent appends, conflict retry); the d2b revisit re-asks plan-17's per-dataset lock question under A |
| otherwise (conflict 1-5 % or speedup 1.1-1.5×) | GO-serial | only A's binding-removal half (immutable per-op handles, writes still on one writer thread) may be proposed; no concurrency; plan-17 keeps `bind` |

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
5. Live untouched: a stat of the cliquet store's active slot and `facts.log` (size + mtime) before
   and after the measurement is unchanged. {#ac-5}

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
