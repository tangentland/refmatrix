---
gmd: "0.1"
id: task-17.3-fleet-rollout
title: "Task 17.3: roll maintenance out to the 8 registered daemons by hand — dry run, backup, run, arm — measure before and after, and document it"
tags: [task, rollout, measurement, docs]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-14
---

# Task 17.3: fleet rollout {#root}

> Plan: [plan-17-nightly-store-maintenance](../plan-17-nightly-store-maintenance.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 17.1, 17.2; deployed

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[task-17.1-vectors-maintain-op]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81#s-4]]
rel: derives-from -> [[plan-review-2026-10-14#t3]]

## Why {#why}

After 17.2 deploys, every store is unarmed, so the hub only dry-runs it (decision d3d). The real
nightly op starts store by store, when this task arms it by hand after a dry run and a backup. The
2026-10-07 hand compaction covered refmatrix, viascope and cliquedb; refmatrix has regrown
(17-261 versions per dataset, 150 MB, spec review #verified), and the stores it skipped have never
been compacted. {#why-body}

## Requirements {#requirements}

1. **R1 By hand, every registered daemon** (decision d3d; spec review #s-4, #s-6). {#r1-hand-run}
   For each of the 8 stores in the registered daemon list (cliquet, global, thiquet, atldb,
   viascope, refmatrix, orderly, cliquedb), through the deployed `rmx` and its daemon only:
   1. `rmx vectors maintain --dry-run`; read the report (orphans, `missing`, cap refusals);
   2. back up `vectors/` with an APFS clone (`cp -c -R`) to `vectors.bak-<date>-maintain`;
   3. `rmx vectors maintain`; read the report; an `ok:false` or `refused:*` stops the rollout for
      that store and is reported to the user before anything else;
   4. `rmx hub maintain arm --root <root>`.

   A store whose daemon does not answer is skipped and counted; it is not run in-process.
   Backups are deleted only after the user confirms (this replaces the old "after N days").
2. **R2 Measure** (spec review #s-4; decision #t3-fixes "17.3 latency on refmatrix, cliquedb,
   thiquet"). {#r2-measure}
   - **Every store, before/after:** vectors bytes, versions per dataset, orphans reaped, `missing`,
     per-dataset hold seconds, `check_s`.
   - **Latency on refmatrix, cliquedb and thiquet:** one watch-flush re-sync of a large file
     (`src/refmatrix/store.py`-sized), timed before and after the hand run, with `code.lance`'s
     version count recorded at each timing.
     - The latency comparison is ASSERTED only for a store whose `code.lance` had ≥ 10,000
       versions before the run (r7's effect lives near 61k versions; below that both numbers are
       small and the comparison cannot fail). If none of the three qualifies at rollout time, the
       comparison runs on a throwaway clone with ≥ 30,000 versions (a 2026-10-07
       `vectors.bak-20261007-precompact` if one still exists), under a short `mkdtemp()` root off
       every watched tree, never the live store.
     - thiquet (≤ 5 versions) is the small-store control: its maintenance must take the R5 skip
       path, and its `check_s` is recorded.
   - The global store is memory-only (no filesystem ingest), so it gets no latency leg.
   - **No-match re-sync** (17.1 R9): on the ≥ 30k-version clone, a re-sync of a file whose ids
     carry no vector commits 0 Lance versions.
   - **Hold bound** (spec review #s-1): cliquedb's `concept.lance` step (or the clone's largest
     dataset) holds `_store_lock` < 60 s, read from the op's report.
3. **R3 Docs.**
   - `docs/PERFORMANCE.md` gets the maintenance section (schedule, arming, the tag rollback
     point, the orphan list and `rmx vectors restore`).
   - `docs/INDEX.md` and the ARCHITECTURE index.
   - The plan-17 decisions (d-1..d-4, d2b, d3a..d3e) are recorded in the implementation summary.
4. **R4 Watch one night.** After the first scheduled 03:30 run with the fleet armed, `hub.log` and
   the `global:queues` summary are read: every store `ok` or `skipped`, the tags held per dataset,
   and no `cli.log` row with `lance_retries > 0` that is unexplained. The result goes into the
   implementation summary.

## Acceptance criteria {#acceptance}

1. The before/after table for all 8 stores is in the implementation summary.
2. On the store or clone with ≥ 10,000 pre-run `code.lance` versions, the after-run re-sync latency
   is ≤ 1/5 of the before-run latency. Fails if maintenance did not compact.
3. The no-match re-sync on the clone commits 0 Lance versions.
4. Every reported hold is < 60 s; any hold ≥ 60 s is a finding in the summary, not averaged away.
5. Each store is armed only after its dry run, backup and hand run succeeded (order visible in the
   rollout log).
6. One scheduled night observed and reported.
7. Backups removed only after the user confirms.

## Test strategy {#test-strategy}

This task runs no new test suite; it is a rollout on live stores through the DEPLOYED `rmx` and the
daemons, never a dev-venv `rmx`. Any re-run of 17.1/17.2's suites during the rollout uses the 23.0
sandbox (decisions d1a/d1b). Every measurement command's output is captured to
`workflow/review-output/plan17-rollout-*.log`.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 17 #s-4 (latency cannot fail, global, store list, backups) | [[#r1-hand-run]], [[#r2-measure]], AC-2, AC-7 |
| 17 #s-6 (8 stores) | [[#r1-hand-run]] |
| 17 #s-1 (numeric hold bound) | [[#r2-measure]], AC-4 |
| 17 #b-6 (61k-clone measurement) | [[#r2-measure]], AC-3 |
| 17 #s-8 (no in-process run) | [[#r1-hand-run]] |
| d3d (arm by hand after dry run + backup) | [[#r1-hand-run]], AC-5 |
| #t3-fixes (latency on refmatrix, cliquedb, thiquet) | [[#r2-measure]] |
| d3c (reader retries observed) | R4 |
| d1a/d1b (23.0) | [[#test-strategy]] |
