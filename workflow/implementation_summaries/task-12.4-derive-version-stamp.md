---
gmd: "0.1"
id: task-12.4-derive-version-stamp-summary
title: "Implementation summary: a store says which code derived its graph"
tags: [summary, plan-12, store, health, store-decay]
metadata:
  node_type: summary
  task: task-12.4-derive-version-stamp
  created: 2026-09-16
---

# Implementation summary: task 12.4 (bug-039) {#root}

rel: implements -> [[task-12.4-derive-version-stamp]]
rel: part-of -> [[plan-12-open-bug-remediation]]
rel: derives-from -> [[project_store_decays_behind_green_health]]

## What shipped {#shipped}

- `derive_stamps(partition_id, pass_name, version, derived_at)` in BOTH catalog DDLs
  (`store.CATALOG_DDL`, `duckdb_catalog.CATALOG_DDL`), created on connect — existing stores gain it
  without a migration step.
- `Store.stamp_derive(pass_name, *, version=None, at=None)` — upsert on `(partition, pass)`.
- `Store.derive_status()` -> `{passes, oldest_version, running_version, stale, reason}`.
- `ingest._stamp_ingest` called at the end of `ingest_path` (both the direct and cooperative
  paths), `ingest_gmd_paths` stamps `gmd`.
- `daemon._op_derive_status` + `_store_health["derive"]` (what the hub's alert tick reads).
- `cli.render_derive_warning` + a line in `rmx daemon status`.

## Two decisions worth keeping {#decisions}

- **An unstamped partition holding tracked files reads STALE, not unknown.** That is precisely the
  state the incident hid in for ten days. "No information" would have preserved the blind spot the
  table exists to remove.
- **The stamp lands AFTER the transaction commits, and only on a clean return.** A crashed ingest
  leaves the previous stamp standing rather than claiming a derive that never finished.

## Two things the build corrected {#corrections}

1. `at` is a reserved word in DuckDB (`Parser Error: syntax error at or near "FROM"`). Column is
   `derived_at`.
2. The renderer was first inserted between `@daemon.command("status")` and `def daemon_status()`,
   so click decorated the helper — `Got unexpected extra arguments (stale oldest_version ...)`.
   Caught by the test, not by reading.

## RED / GREEN / mutation / live {#evidence}

- RED: `workflow/review-output/red-task-12.4.log` — 13 failed.
- GREEN: `workflow/review-output/green-task-12.4.log` — 13 passed.
- Mutation A (drop `_stamp_ingest` from `ingest_path`): `test_a_real_ingest_stamps_the_store` RED —
  the wiring test, not the helper test.
- Mutation B (`derive_status` stops flagging unstamped+tracked):
  `test_tracked_files_with_no_stamp_at_all_read_stale` RED.
- Regression: `test_ingest_graphify`, `test_ingest_markdown`, `test_ingest_progress`,
  `test_daemon_adopt`, `test_daemon_liveness` — 36 passed.
- **Live, on a throwaway store** (not the project store): a real `rmx ingest .` stamped
  `gmd/ingest/semantic` at 0.71.0 and `rmx daemon status` printed nothing; after stamping `0.49.1`
  and restarting the daemon it printed
  `derive: 0.49.1 (running 0.71.0) — stale; re-derive with rmx reingest --force`.

## Not done here {#not-done}

The project's own store is already re-derived (2026-09-16) but carries NO stamp, so it will read
stale until its next ingest — which is the correct reading of "derived before the version that
records it". The memory `project_store_decays_behind_green_health` still says the condition has no
detector; it needs an amending memory.
