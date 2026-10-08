---
gmd: "0.1"
id: task-17.3-fleet-rollout
title: "Task 17.3: roll maintenance out to the fleet, measure before and after, and document it"
tags: [task, rollout, measurement, docs]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 17.3: fleet rollout {#root}

> Plan: [plan-17-nightly-store-maintenance](../plan-17-nightly-store-maintenance.md)
> Status: Pending
> Depends on: 17.1, 17.2; deployed

rel: part-of -> [[plan-17-nightly-store-maintenance]]

## Requirements {#requirements}

1. **R1 First run by hand.** `rmx vectors maintain --dry-run`, then a real run, on cliquet, atldb,
   orderly and the global store. These are the stores the 2026-10-07 hand compaction did not
   touch. Each store is backed up first (an APFS clone) and the backup deleted after the user
   confirms.
2. **R2 Measure.** Per store, before and after: vectors bytes, versions, orphans, and the latency
   of one watch-flush re-sync of a large file. bug-085's symptom is the acceptance test: r7
   measured a 20-file flush at 10.2 s before compaction and 0.2 s after.
3. **R3 Docs.**
   - `docs/PERFORMANCE.md` gets the maintenance section.
   - `docs/INDEX.md` and the ARCHITECTURE index.
   - bug-085's row gets "compaction: automated".
   - The plan-17 decisions are recorded in the implementation summary.
4. **R4 Watch one night.** After the first scheduled 03:30 run, `hub.log` and the `global:queues`
   summary are read, and the result goes into the summary.

## Acceptance criteria {#acceptance}

1. The before/after table for every store in the implementation summary.
2. One night's scheduled run observed and reported.
3. Backups removed only after the user confirms.
