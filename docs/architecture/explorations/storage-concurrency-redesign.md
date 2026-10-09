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

### Round-trip check, run 2026-10-08 {#option-d-check}

Setup: `vortex-data` 0.88.0, duckdb 1.5.6 with the `vortex` extension, pyroaring and pyarrow, in
a throwaway venv. Scripts and logs are in `workflow/measurements/vortex-roaring-0.88/`.
1. **Built-in encodings round-trip, and DuckDB reads them.** A cliquet-shaped workload: 2,000
   linkage cells over 80k entities, 153,805 memberships, as a long `(concept_id u32, entity_id u32)`
   table.
   - Python round-trip: exact.
   - `read_vortex` filtering one 54,696-id cell: 18.6 ms, identical to pyroaring.
   - `COPY ... TO (FORMAT vortex)` and re-read: identical.
   - **File 337 KB, against 251 KB of serialized pyroaring (+34%).**
   - **Intersecting the two largest cells: 5.5 ms in DuckDB, against 0.04 ms in pyroaring
     (about 140x slower).**
2. **There is no roaring encoding in Python 0.88.**
   - The module exposes no Roaring array type: its encodings are ALP, ALP-RD, FastLanes
     bit-packed/FoR/delta, FSST, run-end, sparse, dict, ZigZag, byte-bool and sequence.
   - The compressor never picks roaring for an id set. A 1%-dense set of 80k ids becomes FastLanes
     bit-packed at 17 bits/id (2.2 KB). A 60%-dense set also becomes bit-packed at **102 KB, where
     a roaring bitmap container would be about 10 KB**. A boolean mask stays plain bits (10 KB).
3. **A Python-defined roaring encoding cannot reach a file.**
   - `vortex.registry.register(cls)` accepts a `PyArray` subclass (with `id` as a class
     attribute), and an instance constructs.
   - But `compress` and `io.write` reject it ("not an instance of 'PythonArray'").
   - The extension binary carries "PythonArray deserialization is not supported", "execution is
     not supported", "scalar_at ... validity ... not supported".
   - So Python encodings are in-memory only, and native DuckDB could never decode one anyway.

**Verdict on D today:** the format, the Python bindings and the DuckDB path all work. But the thing
D is FOR is not reachable from Python 0.88: bitmaps as a native, compressed, operable encoding.
Getting it means a Rust-side Vortex encoding (the `vortex-roaring` crate route) built into a
custom wheel and a custom DuckDB extension build. That is a toolchain commitment, not a library
choice. Re-check when `vortex-data` exposes roaring arrays or Python encodings gain serialization.

## Option E: viascope's BSI sidecar, the encoder that WAS built {#option-e}

When ADR-0008's Vortex codec was superseded, viascope built the bitmap encoding as a pyroaring
**bit-sliced index (BSI)** sidecar next to its Lance datasets. This is
`src/viascope/storage/bsi.py` (517 lines, `2ba1f7ad3`, 2026-02-07, live today; used by
`slot_manager`, `data_node` and `bsi_characterization`).
- **Numeric dimensions** (`_NumericBSI`): 64 bit-slice bitmaps per column. A float64 is stored as
  its IEEE-754 bits; uints are stored as-is. `gte`/`lte` are bit-serial AND/OR/ANDNOT over the
  slices, so a range filter is a bitmap.
- **String dimensions** (`_DictEncodedBSI`): an append-only dictionary (string to index) plus 64
  slices over the index. 100k distinct values cost 64 bitmaps plus the dict, not 100k bitmaps.
  Equality is an O(64) AND/ANDNOT walk.
- **Presence bitmaps** per optional column (`_has_*`), and a single bitmap for booleans.
- **Lifecycle:** one serialized sidecar file per Lance slot. Row ids are Lance row positions.
  `build_from_lance` rebuilds it from the dataset, so the sidecar is a derived, disposable index.

**Why it matters here:** refmatrix's bitmaps answer membership ("entities with linkage L to
concept C"). They cannot answer VALUES: edge weight, `updated_at`, PageRank, derive time,
confidence. Every value filter goes to DuckDB today. A BSI over those columns makes "members of
C with weight >= w, touched since t" pure bitmap algebra, composable with the linkage cells and
with no DuckDB round-trip. It is also the general form of ADR-0004's discrete weight-tier
bitmaps.
- With option C it is the read side: viascope already runs Lance plus a BSI sidecar.
- With A or B it is an additive index layer.

**Caveats when porting:**
- **Negative floats.** Raw IEEE bits compare correctly as unsigned integers only for non-negative
  floats: a negative float has the sign bit set, so it sorts above every positive value, in
  reverse order. Use the order-preserving transform (flip all bits of negatives, set the sign
  bit of positives), or a fixed-point uint.
- **Slice count.** The dictionary BSI always keeps 64 slices. `ceil(log2(dict size))` is enough.
  Empty pyroaring bitmaps are cheap, but each query walks all 64.
- **Row ids must be stable.** viascope's slots are append-only, so Lance positions work.
  refmatrix entity ids are already stable integers, so the BSI keys on entity id.

### Where the BSI is slow: measured 2026-10-08 {#option-e-bench}

Setup: viascope's `bsi.py` loaded unmodified from its file, against a numpy-built BSI with the same
layout. The data is uniform uint64 values in [0, 2^32), queried with `>=` at the median. Script and
log: `workflow/measurements/bsi-sidecar-2026-10-08/`. All variants return identical result sets.

| | 80k rows | 1M rows |
|---|---|---|
| **Build:** viascope as-is (per-row Python `BitMap.add`) | 283 ms | 3,561 ms |
| **Build:** numpy, 64 slices (bulk `BitMap(ids[mask])`) | 50 ms | 646 ms |
| **Build:** numpy, 32 slices | 49 ms | 633 ms |
| **Range query:** viascope | 0.11 ms | 0.69 ms |
| **Range query:** numpy-built, 64 slices | 0.07 ms | 0.43 ms |
| **Range query:** 32 slices | 0.06 ms | 0.35 ms |
| **Range query:** plain numpy scan, for reference | 0.05 ms | 0.99 ms |

- **Queries are not slow.** pyroaring is CRoaring underneath; a 64-slice range query over 1M rows
  takes under a millisecond. C++ buys nothing on reads.
- **The build pays a Python tax.** viascope calls `BitMap.add` once per set bit per row, plus a
  `to_pylist()` per row in `build_from_lance`. A bulk numpy build is 5.5-7x faster with no C++.
- **What remains is mostly CRoaring constructing 64 bitmaps.** C++ would mainly save the numpy
  masking passes. A further 2-5x is a guess, not a measurement.

**The user's evidence, 2026-10-08: "the place where python bitmaps were slow is
cliquedb/thiquet".** cliquedb runs pg_roaringbitmap from PL/pgSQL with no C extension, and thiquet
queries it. Its `reports/perf-benchmark-2026-07-14.md` at 1M nodes / 12.8M edges:
- set algebra 22.6 ms;
- k-hop 47.2 ms p50 and 1.4 s p95, about 7x Neo4j.

The bitmap operations there are C too. The cost is the interpreted loop that drives them: per-row
or per-hop calls from PL/pgSQL or Python. That matches the build result above. The rule both
measurements support: **keep the loop in C/C++, and keep each bitmap operation big.** {#option-e-rule}

**So, C++ where the loop is the hot path:**
- **Per-row incremental adds** (ingest time). Python call overhead dominates there. Batching is the
  cheaper fix; a small nanobind module over CRoaring is the C++ answer.
- **Iterative graph walks** (k-hop, PPR-style reach). Each step is a bitmap operation driven by an
  interpreted loop. This is cliquedb's 1.4 s tail, and refmatrix's `degree` walk is the same
  shape.
- **Set algebra inside the query engine.** A DuckDB C++ extension exposing roaring/BSI scalar and
  aggregate functions would put the bitmap and the loop in the same process as the SQL. That
  serves options A and C, and it is the larger prize than a faster sidecar build.

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
6. **BSI value filters** (E): a numpy-built BSI (not viascope's per-row build;
   [[#option-e-bench]]) over refmatrix's entity weights and timestamps on a cliquet copy. Compare a
   combined "linkage cell AND weight >= w AND recent" with today's DuckDB route.
7. **Where an interpreted loop drives bitmap operations** (the cliquedb/thiquet shape): profile
   refmatrix's `degree`/PPR walk and the ingest-time per-row adds. This decides whether a
   C++/nanobind module or a DuckDB C++ extension is earned.

## Recommendation so far {#recommendation}

**A first.** It fixes the bug class with no on-disk change, and it absorbs parts of plans 22 and 23.
Weigh **B** once A shows what really crosses partitions. Treat **C** and **D** as the long-horizon
storage question. Measure them before any ADR. D was checked on 2026-10-08
([[#option-d-check]]). The format and DuckDB path work; roaring is NOT reachable from Python 0.88.
So D needs a Rust encoding build, or waits on upstream. **E** (viascope's
BSI) is the cheapest experiment of all: the code exists, and it composes with any of A-C.

{#recommendation-body}
