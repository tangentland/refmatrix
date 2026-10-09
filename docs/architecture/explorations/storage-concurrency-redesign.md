---
gmd: "0.1"
id: exploration-storage-concurrency-redesign
title: "Exploration: the shared writer binding, and four ways to stop serializing the store"
tags: [exploration, storage, duckdb, lance, vortex, concurrency, partition, roaring]
metadata:
  node_type: exploration
  status: in-progress
  created: 2026-10-08
---

# Exploration: the shared writer binding, and four ways out {#root}

**Date:** 2026-10-08
**Status:** In progress. Options framed; nothing measured yet ([[#measure]]).
**Motivation:** Three bugs in one week came from one mechanism.
- ch-bsd r9 #b-1: the read mirror answered from the wrong partition.
- r10 #s-1: an unknown partition was answered as partition 1.
- bug-098: concurrent writes landed in each other's partition, and so did their derive stamps.

0.77.1 fixed bug-098 at every site the sweep found. The mechanism is still there. The user asked
three questions on 2026-10-08:
- Should a store have one partition?
- Could DuckDB be read-only, with writes going straight to Lance?
- Should we look at Vortex again? viascope designed a Vortex roaring-bitmap encoding.

rel: derives-from -> [[bug_registry#registry]]
rel: related-to -> [[refmatrix/adr-0003-canonical-partition-layout]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: related-to -> [[plan-22-audited-removal-and-repair]]
rel: related-to -> [[plan-23-bounded-write-harness]]
rel: related-to -> [[refmatrix/ARCHITECTURE]]

## Background: what serializes the store today {#background}

- **The daemon owns the store.** One daemon per store holds one DuckDB connection and one `Store`
  object. Every write op takes `_store_lock`. A long ingest yields that lock cooperatively
  (`_partition_keeping_yield` since 0.77.1) so hook writes can interleave.
- **The Store has a mutable binding.** It carries a current partition (`_partition_name`,
  `_partition_id`) that ops switch with `with_partition`. Every bug above was a reader or writer
  observing some other op's binding.
- **Reads from other processes** go through the snapshot file (`catalog.read.duckdb`) and the
  in-memory mirror, because DuckDB lets only one process open a database read-write.
- **Vectors live in Lance,** one directory per partition and one dataset per kind. Linkages are
  pyroaring bitmap fragments.

### What DuckDB actually allows {#duckdb-concurrency}

From the DuckDB concurrency documentation (LTS, read 2026-10-08):
- One process may read and write. Other processes may only read (`READ_ONLY`).
- Within that one process, writer threads run concurrently under MVCC with optimistic concurrency.
  "Appends will never conflict, even on the same table". Separate rows do not conflict either.
  Only two threads updating or deleting the SAME row conflict.
- Writing from several processes is unsupported. The documented workarounds include a single
  server process that owns all access, which is what the daemon is.

The daemon follows the cross-process rule correctly. Inside the process it serializes far more
than DuckDB requires: one connection, one lock, and a shared binding. The serialization comes from
our design, not from DuckDB. {#duckdb-concurrency-body}

### Where partitions are actually crossed {#cross-partition}

A store has exactly two partitions: `<project>` and `sessions-<project>`. The `memory-<project>`
partition was merged away by ADR-0003. Census, 2026-10-08:
- **Project partition only:** context, scan-prompt, memory recall, embed.
- **Sessions partition only:** session recall and the session-card ingest-gmd job.
- **Both:** `_store_health`'s derive check (on every ping), and the plan-13 sweep, which was never
  built.
- **The "federated" `search.py` functions** cross STORES, not partitions. They already open each
  store separately.

So cross-partition reads inside a store are rare. Cross-partition WRITE interference, on the
other hand, was the bug. {#cross-partition-body}

## Option A: partition-scoped handles on per-op cursors {#option-a}

Every op gets an immutable `(store, partition_id)` handle carrying its own DuckDB cursor on the
daemon's single instance. Nothing switches a shared binding.

- **Removes the class.** No op can observe another op's partition, because none is shared.
- **Opens real in-process concurrency.**
  - Appends (ingest, memory add, session cards) could run on separate threads without
    `_store_lock`.
  - Same-row update/delete conflicts need a retry.
  - The cooperative-yield machinery could go.
- **Needs a Store-state audit.** DuckDB's MVCC covers only its tables. The pyroaring fragment
  buffer, the `content_rank` caches and the Lance datasets are Python- or Lance-side, and keep
  their own locks.
- **Risk:**
  - Per-op handles must be cursors on the existing instance. A second `duckdb.connect` to the same
    file "with a different configuration" raised `ConnectionException` before (memory
    `project_session_0322_to_0327`).
  - The ART-index corruptions we have hit (2026-09-14, the cliquet phantom) happened under a SINGLE
    writer, and more real concurrency may expose more of them.
- **Cost:** a mechanical refactor of every `self._partition_id` read in `store.py` (about 7k
  lines). No on-disk change.

## Option B: one partition per store {#option-b}

`sessions-<project>` moves to its own catalog file, with its own lock, inside the same daemon.

- **Removes the contention,** not just the race. Hook-driven session-card jobs never share a lock
  or a binding with a project ingest.
- **Cheap to lose:** the sessions partition is small (17-186 documents per store), and almost
  nothing reads across.
- **Costs:**
  - A layout change: an ADR-0003 amendment, plus a migration on every store.
  - Every read that does cross (health, a future sweep) becomes a two-store read.
- **Composes with A.** A fixes the class; B removes the contention that made the class bite.

## Option C: DuckDB read-only, writes straight to Lance {#option-c}

Lance becomes the system of record for entities, linkages and stamps as well as vectors. DuckDB
runs per process, in memory and read-only, scanning Lance datasets through Arrow.

- **Buys:**
  - No catalog write lock, because Lance versions are readable by any process while a writer
    commits the next one.
  - No snapshot file and no mirror.
  - No persisted DuckDB indexes, so no ART corruption.
  - One store for rows and vectors, so the dual-write orphan class goes away.
- **Costs:**
  1. **Small writes are Lance's weak spot, and they are most of our traffic.** Every write is a
     commit and a new version. Updates and deletes are delete plus append; bug-085 was one Lance
     commit per entity freezing the daemon. Memory adds, flag toggles, stamps, learn-drain entries
     and watcher re-syncs would need a write buffer that batches into commits, plus routine
     compaction (plan-17 exists because version churn already costs today).
  2. **No multi-table transactions.** One logical write spans entities, links, evidence and
     fragments, and Lance commits per dataset. `facts.log` would have to become the true source,
     with Lance as a materialization.
  3. **Read latency.** `content_rank` is 21 ms on DuckDB tables with indexes. Over Lance it needs
     Lance scalar indexes plus DuckDB scan pushdown, or an in-memory materialization, which is
     today's mirror rebuilt from another source.
- **Prior art:** memory `project_snapshot_tier_plan` (2026-06-04) concluded that DuckDB, not
  Lance, is the main source of lock pain. That supports the goal, but not this route by itself.

## Option D: Vortex, with roaring bitmaps as a native encoding {#option-d}

viascope's history, checked 2026-10-08 (viascope git; the `docs/architecture/archive/` copies were
renamed to Lance and only cite the ADRs):
- **ADR-0007 "Vortex Over Parquet"** was Accepted on 2026-02-02. `vortex-storage.md` (881 lines,
  `7104ef743`) specified it on 02-05.
- **ADR-0008 "Custom Vortex Roaring Codec"** stayed **Proposed (Design Goal)**. It describes one
  Vortex slot file holding both the sparse index, as a roaring encoding with BSI bit planes, and
  the event columns, with set operations computed over the compressed bitmaps:
  `index[a].intersect(index[b]).intersect(index["confidence > 90"])`, then decompress only the
  matches.
- **It was never built.** No code commit imports Vortex; the history shows Vortex only in docs.
- **viascope moved to Lance on 02-06** (ADR-0007 addendum, during tech-stack validation). The
  stated reasons:
  - MVCC and dataset versioning ("readers don't block writers"), where Vortex's concurrent access
    was custom work.
  - `pylance` wheels for Python 3.14, against Rust FFI for Vortex.
  - Maturity: production-ready against incubating.
  ADR-0008 was superseded by "pyroaring BSI sidecars on Lance". That is refmatrix's layout today.

**Why it fits refmatrix specifically:** refmatrix's core primitive is a roaring bitmap per
`(linkage, concept)`, and its query DSL is set algebra over those bitmaps. A columnar file where a
bitmap is a first-class encoding would hold the linkage cells and the entity columns in one
atomically written file. That is ADR-0008's "atomic slots: index and events always consistent",
and it ends the bitmap-fragment / DuckDB / Lance three-way consistency problem.

**State of the February blockers, re-checked 2026-10-08** (web: docs.rs, PyPI, duckdb.org):
1. **Roaring is an upstream Vortex encoding now.**
   - The `vortex-roaring` crate provides `RoaringBoolArray` (bool arrays as roaring) and
     `RoaringIntArray` (integer sets as roaring), with a `Portable` format compatible with other
     roaring libraries (Java, Go, and so pyroaring's interchange format).
   - docs.rs shows `vortex-roaring` at 0.21.1, while the Vortex Python package is at 0.88.0. So
     it is NOT yet established that roaring ships in current Vortex, or that it is reachable from
     Python.
   - The crate docs describe no AND/OR/filter kernels over the compressed form. ADR-0008's
     "set operations without full decompression" would still be ours to build.
2. **Python bindings: resolved.** `vortex-data` 0.88.0 (2026-10-08) has abi3 wheels for Python
   3.11-3.14 on macOS arm64, zero-copy Arrow conversion, and a `duckdb` extra. It is an LF AI &
   Data project under Apache-2.0.
3. **DuckDB: resolved.** A core DuckDB `vortex` extension (announced 2026-01-23) reads
   (`read_vortex(...)`) and writes (`COPY ... TO ... (FORMAT vortex)`), with expressions evaluated
   over compressed segments.
4. **Write model: still open.** Vortex is a FILE format: immutable files with no dataset
   versioning or MVCC, the thing viascope chose Lance for. We would own versioning, compaction and
   the small-write buffer, the same costs as option C.

**First concrete step:** confirm a roaring-encoded column round-trips through `vortex-data` 0.88 in
Python, and that `read_vortex` filters on it from DuckDB. If either fails, D waits on upstream.

## Measurements that decide it {#measure}

1. **Small-write rate per op type,** from `facts.log`: what option C or D must batch.
2. **Lance version and fragment growth** when those writes are replayed against a cliquet copy
   (option C).
3. **`content_rank` latency** with DuckDB scanning Lance, and Vortex if it reads, against 21 ms
   today (C, D).
4. **Option A's concurrency:** one writer thread against N cursor writer threads on a cliquet copy.
   Measure conflict rate, throughput, and whether ART errors appear under load.
5. **Bitmap set algebra:** pyroaring today, against `RoaringIntArray` columns through
   `vortex-data` + DuckDB `read_vortex` (D). This includes whether the intersection happens
   compressed or after decode.

## Recommendation so far {#recommendation}

**A first.** It fixes the bug class with no on-disk change, and it absorbs parts of plans 22 and 23.
Weigh **B** once A shows what really crosses partitions. Treat **C** and **D** as the long-horizon
storage question. Measure them before any ADR. D moved closer on 2026-10-08: the Python bindings
and DuckDB support now exist, and roaring is an upstream encoding. What remains is the roaring
round-trip check and the write/versioning model.

{#recommendation-body}
