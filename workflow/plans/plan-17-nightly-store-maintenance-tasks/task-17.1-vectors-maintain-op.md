---
gmd: "0.1"
id: task-17.1-vectors-maintain-op
title: "Task 17.1: a daemon op that reaps orphan vectors, compacts and cleans each Lance dataset — bounded, fingerprinted, never lossy"
tags: [task, daemon, lance, maintenance, compaction]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 17.1: the `vectors_maintain` op {#root}

> Plan: [plan-17-nightly-store-maintenance](../plan-17-nightly-store-maintenance.md)
> Status: Pending
> Depends on: — (17.2 schedules it)

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: derives-from -> [[project_daemon_wedge_per_entity_lance_delete]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]

## Why {#why}

Nothing in `src/` compacts a Lance dataset or removes old versions. By hand on 2026-10-07:
- refmatrix 1.3 GB → 105 MB (`code.lance` 61,395 → 1 version);
- viascope 925 MB → 229 MB;
- cliquedb 1.1 GB → 62 MB.

Every dataset's fingerprint was identical before and after (`workflow/review-output/lance-compact-*.log`).
Doing it by hand required STOPPING the daemon, because it caches a `LanceVectorStore` handle
(`store.py:3377-3406`, `self._vs`) that a cleanup can invalidate. Orphan vectors (559 in this
store's `code.lance`) are reaped only by a manual `embed --gc` (`daemon.py:5538`). That op builds
an embedder just to learn the vector dimension, so a maintenance pass could load a model.
{#why-body}

## Requirements {#requirements}

1. **R1 A verb + daemon op.** `vectors_maintain(partition=None, dry_run=False, kinds=None)`, with
   CLI `rmx vectors maintain` and MCP parity (the verb-parity test).
2. **R2 Per dataset, in order:**
   - (a) fingerprint: rows, a hash of the sorted id set, a vector checksum;
   - (b) reap orphans with `gc_vectors`, taking the dimension from the dataset schema, never from
     an embedder;
   - (c) `optimize.compact_files()`;
   - (d) `cleanup_old_versions(older_than=24h)` (plan-17 d-2);
   - (e) fingerprint again.

   Expected after == before minus the reaped orphans. Any other difference → `ok:false`, a loud
   error, and no further datasets touched in this run.
3. **R3 Bounded lock holds.** Each dataset's step runs in its own `_store_lock` acquisition, and
   the lock is released between datasets. Each hold is measured and reported. A hold over
   `RMX_MAINTAIN_HOLD_S` (default 60) is reported as a warning (not aborted mid-commit).
4. **R4 Handle refresh.** After cleanup, the daemon's cached `LanceVectorStore` (`self._vs`) and
   any read-store Lance handles are dropped and reopened before the lock is released, so no reader
   holds a removed version.
5. **R5 Skip cheap.** A dataset with < `RMX_MAINTAIN_MIN_VERSIONS` (default 100) versions and no
   orphans is skipped after one directory listing and reported as skipped.
6. **R6 Never lossy.** The only rows removed are orphans: vectors whose entity id is absent from the
   catalog. That is verified by the fingerprint arithmetic. The orphan list (ids + kind) is written
   to `.refmatrix/maintain/orphans-<ts>.jsonl` before removal, so a reaped id can be
   re-embedded if the catalog later proves it was wrong.
7. **R7 Report.** Per dataset: versions, fragments and deletion files before/after; bytes; orphans
   reaped; hold seconds; skipped/failed. Returned in the op result and logged to `rmxd.log`.

## Acceptance criteria {#acceptance}

1. On a real Lance store fixture with 500 versions, 3 fragments and 20 orphans:
   versions → ≤ 2 (24 h window: the current version plus any made in the window), orphans → 0,
   the fingerprint minus orphans unchanged, and the orphan file written.
2. A forced fingerprint mismatch (a test-only corruption of one vector between the two
   fingerprints) returns `ok:false`, and the remaining datasets are untouched.
3. A read through the daemon's cached handle after the op succeeds. The same read with R4 removed
   fails. That is the test of the refresh.
4. A probe thread can acquire `_store_lock` between datasets (released), and each hold is ≤ the
   measured bound.
5. A dry run changes nothing (versions, bytes, files) and reports what would happen.
6. Mutations that must FAIL a test:
   - no handle refresh;
   - the dimension taken from an embedder;
   - the lock held across datasets;
   - the fingerprint check skipped.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/vectors.py` | dimension from schema; compact + cleanup helpers |
| `src/refmatrix/store.py` | the maintain routine; handle drop/reopen |
| `src/refmatrix/daemon.py`, `verbs.py`, `cli.py`, `mcp.py` | the op, verb, CLI, MCP |

## Test strategy {#test-strategy}

Real Lance datasets in tmp stores; no Lance mocks. Lance-dependent test files skip only when lance
is not installed (the r8 #s-4 rule).
