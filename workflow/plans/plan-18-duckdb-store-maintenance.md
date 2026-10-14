---
gmd: "0.1"
id: plan-18-duckdb-store-maintenance
title: "Plan 18: DuckDB catalog maintenance (checkpoint / vacuum) on the nightly maintenance tick"
tags: [plan, hub, daemon, duckdb, maintenance]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
---

# Plan 18: DuckDB store maintenance {#root}

> Status: DRAFTING (a stub). Split out of plan-17 by the user on 2026-10-07 (plan-17 d-3). Plan-17
> keeps the Lance vectors lean; this plan does the same for the DuckDB catalog.
> **Scope kept MINIMAL** (plan review C12, user 2026-10-07): measure + `CHECKPOINT` as a step on
> plan-17's tick. No slot-rewrite VACUUM until ADR-0004's helix plan decides whether snapshot
> manifests replace A/B slot reconciliation.

rel: depends-on -> [[plan-17-nightly-store-maintenance]]

## Why {#why}

The catalog is DuckDB writer slots `catalog.A/B.duckdb`, plus a read snapshot. On this store
`catalog.read.duckdb` is 603 MB. The cliquet repair (memory `project_cliquet_catastrophic_repair`)
took an 82 GB catalog down to 46 MB. Nothing runs `CHECKPOINT` or reclaims free blocks on a
schedule. {#why-body}

## To decide before specs {#open}

- **Measure first:** catalog file size against live data size per fleet store, the WAL size, and the
  free-block ratio (`PRAGMA database_size`).
- **Slot rotation:** a VACUUM or rewrite must respect the A/B writer slots and the `active` marker
  (`project_slot_drift_root_cause_fixed`). That probably means a rewrite into the inactive slot plus
  an atomic swap, not an in-place VACUUM.
- **Daemon op shape:** the same rules as plan-17's `vectors_maintain`: under `_store_lock`, bounded,
  fingerprinted, and scheduled by plan-17's hub tick.

## Contract to meet (drift note, 2026-10-14) {#contract-2026-10-14}

Plan-17's tick changed in the Wave 0 revisions; this plan's task specs, when written, start from it:

- **A registered step on 17.2's hub `maintenance_steps` registry** (17.2 `#r2-registry`), not on
  plan-23's daemon tick registry. It declares `requires_arming` and the reason. A CHECKPOINT that
  rewrites the catalog is user-visible state, so the expected answer is `True`: it dry-runs until
  the `run_id` of a successful hand run arms it (17.2 `#r7-unarmed`, the per-step ledger
  `<root>/maintain/runs.jsonl`).
- **Calls with `retries=0`, single-flight per store** (d3e), reported as `still_running` /
  `stuck` under 17.2's ceiling (`RMX_MAINTAIN_STUCK_AFTER`), never re-sent onto a running pass.
- **Order against 17.4:** the daily `facts.log` copy (17.4) and a CHECKPOINT must not run on the
  same store at the same time; state which runs first in the store's serial pass.
- **Order against the bug-105 repair:** the first CHECKPOINT on a store runs after
  `rmx repair-index --fragments` has been applied there.
- **Tests** in plan-23 task 23.0's sandbox only (d1a/d1b), on catalog copies.
- **Wave:** [[plan-review-2026-10-14#t10-waves]] (Wave 4).

rel: depends-on -> [[plan-review-2026-10-14#t10-waves]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]
