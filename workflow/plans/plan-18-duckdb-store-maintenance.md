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
