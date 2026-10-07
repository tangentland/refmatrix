---
gmd: "0.1"
id: plan-17-nightly-store-maintenance
title: "Plan 17: the hub keeps every store lean — nightly vector compaction, old-version cleanup, and orphan reaping as a daemon op"
tags: [plan, hub, daemon, lance, maintenance, performance]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
---

# Plan 17: nightly store maintenance from the hub {#root}

> Status: DRAFTING, with the decisions taken ([[#decisions]]). The user asked on 2026-10-07: "we should
> add a nightly compaction job to the hub process to keep projects lean and fast". Next: task specs
> 17.1-17.3, then spec review.

rel: motivates -> [[bug_registry#registry]]
rel: related-to -> [[project_daemon_wedge_per_entity_lance_delete]]
rel: related-to -> [[project_bus_retention_global_queues]]

## Why {#why}

Lance commits a new dataset VERSION on every write (append, delete, upsert), and nothing in
refmatrix ever compacts a dataset or removes its old versions. No `compact_files` or
`cleanup_old_versions` call exists in `src/`. The cost compounds:

- **bug-085.** Each Lance delete on a 60,944-version `code.lance` cost about 1-2 s. A file re-sync
  issued one delete per entity under `_store_lock`, and the daemon wedged for 7+ minutes per edit.
  The batching fix (0.76.1) cuts the COUNT of deletes; it does not stop the growth.
- **Measured on 2026-10-07**, the one-off compaction of this project's store
  (`workflow/review-output/lance-compact-live.log`):
  - `vectors/` went from 1.3 GB to 105 MB.
  - `code.lance` went from 61,395 versions / 168 fragments / 10,192 deletion files to 1 / 1 / 0.
  - rows, the id set and a vector checksum were identical before and after on all 5 datasets;
  - the whole pass took 27 s with the daemon stopped.
- **The rest of the fleet** (version directories summed per store):

| store | vectors | Lance versions |
|---|---|---|
| cliquedb | 1.1 GB | 59,382 |
| viascope | 925 MB | 32,113 |
| cliquet | 75 MB | 4,941 |
| atldb | 24 MB | 1,354 |
| orderly | 9.5 MB | 225 |
| global, thiquet | < 1 MB | ≤ 5 |

- **The first fleet run, by hand, 2026-10-07** (backups `vectors.bak-20261007-precompact`; logs
  `workflow/review-output/lance-compact-{viascope,cliquedb}.log`): viascope went from 925 MB to
  229 MB and cliquedb from 1.1 GB to 62 MB. cliquedb's `concept.lance` was 739 MB with 46,606
  versions. The fingerprints were identical everywhere.
- **Orphan vectors.** After the compaction, 559 of `code.lance`'s 5,495 vectors and 1 doc vector have
  no catalog row. They were in the pre-compaction backup too. They surface in `search-dense` as
  `kind ? name ?` hits. `Store.gc_vectors` (behind `rmx embed --gc`) reaps them, but nothing runs it.
  {#why-numbers}

## Design (draft) {#design}

- **One daemon op does the work.** `vectors_maintain` is a verb first, with CLI
  `rmx vectors maintain` and MCP parity per the verbs rule.
  - The daemon owns the Lance handles and `_store_lock`. A hub- or CLI-side open would race the
    daemon's cached `LanceVectorStore` handle, and today's run had to STOP the daemon for exactly
    that reason.
  - Per dataset, under the lock, it runs: `gc_vectors` (orphans), then `optimize.compact_files()`,
    then `cleanup_old_versions(older_than=24h)` ([[#d-2]]).
  - Afterwards it drops and reopens the cached handles, so no reader holds a version whose files
    were removed.
  - It fingerprints each dataset before and after: rows plus a hash of the id set. A mismatch fails
    the op loudly and leaves the dataset as it was.
  - It is bounded: one dataset per lock hold, with the lock released between datasets, so a nightly
    pass cannot wedge the daemon the way bug-085 did.
- **Skip thresholds.** A dataset under N versions (default 100) and with no orphans is skipped, so a
  quiet store costs one directory listing.
- **The hub only schedules.** A nightly tick, on the timer that already drives
  `_bus_retention_once`:
  - calls `vectors_maintain` on each registered, supervised, running store, SERIALLY;
  - skips paused stores (`rmx hub pause`);
  - records `last_maintained` per store, so a night missed while the laptop slept runs at the next
    wake rather than waiting a day;
  - logs per-store results to `hub.log`;
  - publishes one summary to `global:queues`, which bus retention already bounds.
- **No silent failures.** A failed store is logged and counted in the summary, and the next store
  still runs. A store that fails N nights running alerts once. {#design-body}

## Tasks (draft) {#tasks}

| task | what | acceptance |
|---|---|---|
| 17.1 | `vectors_maintain` daemon op + verb + CLI/MCP, built on `gc_vectors` and the Lance optimizer, handle refresh, and before/after fingerprints | on a real Lance store: versions → 1, fingerprints identical, orphans removed; a forced mismatch leaves the dataset intact and returns ok:false; reads after the op succeed through the daemon's cached handle; lock released between datasets (measured) |
| 17.2 | hub nightly scheduler: time-of-day, catch-up after sleep, pause-aware, serial, summary publish | a fake clock drives one run per night; a missed night runs on wake; a paused store is skipped and named; a failing store does not stop the rest |
| 17.3 | fleet rollout: run once by hand on cliquedb + viascope with backups, measure size and latency before/after; docs + registry | before/after table in the implementation summary; backups removed after N days |

## Decisions (user, 2026-10-07) {#decisions}

- **d-1. A fixed local time with catch-up** {#d-1}. Default 03:30, overridable by
  `RMX_HUB_MAINTAIN_AT`. A night missed while the machine slept runs at the next wake.
- **d-2. Keep a 24 h window of old versions** {#d-2}: `cleanup_old_versions(older_than=24h)`. That
  leaves up to a day of versions as a rollback point. Lean, but deliberately not minimal.
- **d-3. DuckDB maintenance is plan-18, not part of this plan** {#d-3}
  ([[plan-18-duckdb-store-maintenance]]). Plan-17 covers vectors only.
- **d-4. Orphans are reaped nightly** {#d-4}: `gc_vectors` runs inside the op, and the counts are
  logged and published.
