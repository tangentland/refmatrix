---
gmd: "0.1"
id: perf-bitmap-materialisation-2026-11-14
title: "Performance analysis: materialising more of the bitmap matrix (measurement only)"
tags: [performance, bitmap, adjacency, measurement]
---

# Performance analysis: materialising more of the bitmap matrix {#root}

Measurement only. Nothing under `src/` or `tests/` was edited, and nothing was committed. Every
number below comes from the scripts in this directory and their `*.out` logs.

## Method and environment {#method}

- **Code:** dev tree `src/` at `e82233a`. HEAD moved to `b12724d` during the run (plan-29 docs
  commits only). `git diff e82233a b12724d` shows no change to `store.py`, `query.py`,
  `pagerank.py`, `ppr.py`, `scan.py` or `backend.py`, so the measured code is the same at both shas.
- **Interpreter:** `.venv-eval` Python 3.14.5, numpy 2.4.4, duckdb 1.5.2, pyroaring 1.1.0. The
  machine has 16 cores (12 performance) and 128 GB of RAM.
- **Data:** a `cp` of the live `catalog.read.duckdb` (1,174,679,552 B, taken 13:54) into the short
  root `/private/tmp/claude-501/pb4SpU/`. It is opened only through `Store(root, partition="refmatrix",
  read_only=True)`, which binds `catalog.read.duckdb` and skips every migration and write path
  (store.py:1332, 1565). No daemon or hub was started or contacted, `REFMATRIX_ROOT` was never
  exported, and no `rmx` command was run. Partition `refmatrix` (id 4) has 127,047 entities
  (114,562 concepts), 34 linkages, 1,177,027 fragment bits, 1,383,823 `entity_links` rows (all
  partitions) and 7,139,742 B of serialised fragments.
- **Disk tier:** the copy has no `facts.log`, so I wrote a 12,345-byte placeholder into the copy
  root. That turns on `cached_adjacency`'s npz tier there. Its npz lives in the copy root, not in
  the live store.
- **Logs:** the live `query.log`, `cli.log` and `rmxd.log` were read as text only (`logstats.py`,
  `hitrate.py`). The window is 2026-11-07 to 2026-11-14.
- **Load:** the 1-minute load average ranged from 3.4 to 9.2 (another agent's suite was running).
  It is printed at the start and end of every block in the `*.out` files. Each run is
  single-threaded on a 16-core machine. The q3b and q_loadbitmap runs overlapped the q3
  depth-2/topn run, which is when the load reached about 9. Per-call primitives measured in
  isolation (`load_bitmap` at 3.1 ms per call, `noise_concept_ids` at 8.5 ms) matched the
  concurrent runs, so I treat the "today" numbers as not materially distorted. Every result is a
  median plus p90 over 5 or more runs, except "topn today", which is one run (about 7.7 min each).
- **Identity:** every prototype result is asserted equal to today's (`assert a == b`) unless the
  table says otherwise.

## Q1: adjacency, cold vs in-process vs disk {#q1}

| Measurement | Median | p90 | Notes |
|---|---|---|---|
| `build_adjacency`, fresh Store | 1252 ms | 1380 ms | n=5 |
| `build_adjacency`, fragment already loaded | 1364 ms | 1371 ms | n=5. Fragment load is not the cost |
| of which: op-ids SQL / iterating 834,472 mention bits / typed-rows SQL (333,027 rows) | 8 / 31 / 139 ms | | Measured phases sum to about 178 ms. By subtraction, about 1.2 s is spent elsewhere in the function (the per-edge Python `add()` dict loop is the only remaining work; I did not profile it separately) |
| `CSRAdjacency.from_dict` | 195 ms | 209 ms | |
| `cached_adjacency`, first call (build + from_dict + npz write) | 1522 ms | | |
| `cached_adjacency`, warm in-process | 0.79 µs | 0.92 µs | n=50 |
| `cached_adjacency`, disk tier (fresh Store + npz load) | 20.7 ms | 22.3 ms | n=7. npz load + index dict alone: 19.4 ms |
| **Vectorised CSR build prototype** (numpy over `to_array()` + `fetchnumpy()`) | **506 ms** (528 ms with a fresh Store) | 549 ms | Same edge set as `build_adjacency`: 116,552 nodes, 1,888,764 directed edges, max weight difference 0 |

Sizes: 116,552 nodes and 944,382 undirected edges. The CSR arrays take 31.2 MB, or 40.1 MB traced
with the index dict. The npz file is 33.0 MB. The dict-of-dicts that `build_adjacency` returns is
196 MB traced (272 MB peak). The disk-tier CSR equals a fresh build as an edge set, but its row
order differs: `entity_links` is read without `ORDER BY`. On 18 real seed sets, PPR results were
still bit-identical.

## Q2: the five bypass sites {#q2}

| Site | Reached by | Frequency (logs, 7 days) | Params match cache key? | Must it rebuild? |
|---|---|---|---|---|
| **ppr.py:269** `rank_related_for_prompt` | `scan.py:802` `_ppr_rerank` ← `scan_prompt(rank="ppr")`. **The installed UserPromptSubmit hook** (`rmx scan-prompt --composite-every 3 --max-tokens 2000 --timeout 5`) does not pass `--rank`, so it gets the default `ppr` (cli.py:9684). `_net_rerank` also falls back here | **every prompt with a concept match**: 389 scan-prompts per week (20-125 per day). Live scan-prompt latency is p50 2818 ms and p90 13,042 ms | Yes. `link_weight=2.0` and `exclude_operational=True` are the defaults of both functions | No. It needs a dict API that `CSRAdjacency` lacks: `overlay_prompt_clique` does `dict(adj)` and `seed_coverage` does `set(adj.get(n, {}))`. With the hook defaults (`RMX_SCAN_CLIQUE_W`=2.0, `RMX_SCAN_COVERAGE_ALPHA`=3) both run on every prompt. **Measured on the copy:** 1322 ms median (p90 1402) per call today, against **8.4 ms (p90 14.0)** for a prototype over a warm CSR with a seed-row overlay. Outputs matched 18/18 and were bit-exact |
| ppr.py:211 `rank_related` | No production caller. Only tests/test_v2_features.py and tests/test_scan_prompt_expansion.py | 0 | Yes | No |
| enrich.py:126 `enrich_concepts` | `scan_prompt(rank="enrich")` | 0 this week. The last `--rank` in cli.log is from 2026-08-28 | Yes | Same dict-API need (`overlay_prompt_clique`, and `walk()` over dict rows) |
| net.py:139 `build_net` | `scan_prompt(rank="net")` | 0 this week | Yes | Iterates `adj.get(cid, {})` keys. `_NeighborView` has no `__iter__`, so this needs an adapter |
| daemon.py:6682 `_op_pagerank` | `rmx pagerank` (cli.py:11285) → `pagerank_compute` op. No scheduler or derive trigger found in the code or in rmxd.log | 1 real run this week (2022 ms) and 7 in all of cli.log | Yes (`link_weight` defaults to 2.0) | **Yes.** It is the derive pass, it must see the current graph, and `pagerank()` needs `adj.keys()`. It could reuse an in-process CSR built in the same write batch, but at this frequency there is nothing to gain |

**Whether the disk tier would actually be fresh (hitrate.out):** the disk key is the `facts.log`
size. Between consecutive scan-prompts last week, some write signal fell in the gap for 365 of 390
pairs, so a facts.log-keyed cache could have been fresh for **at most 25 of 390 prompts (6%)**.
Broken down by source: watch flushes alone fall between 198/390 pairs, the session indexer 128/390,
and non-skip ingests 57/390. A partition-scoped edge-version key would therefore still miss about
half the prompts (watch flush alone). On a miss the cost is a full rebuild. Caveat: these are log
signals, not facts.log byte growth, so 6% is a lower bound on the real hit rate. The in-process
tier has the same problem in a daemon, because `_invalidate_content_rank_caches` drops it at every
write batch. `rmx context` (`--degree 1`, context.py:658, 96 calls this week, p50 688 ms) is the
only caller that already uses the cache, and it is exposed to the same misses.

## Q3: pre-split rows and `neighbors` {#q3}

**Build:** `{linkage: {concept_id: BitMap}}` built from the fragments takes 234-240 ms from a
fresh Store and 167-169 ms with fragments loaded. That gives 123,448 rows and 1,177,027 bits, the
same count as the fragments. Serialised rows total 6,615,417 B against 7,139,742 B for the
fragments. Python allocation traced at 14.6 MB (41.5 MB peak).

**The hop primitive (measured):** `load_bitmap` costs **3.1 ms per call** (680 calls, warm). A dict
row lookup costs 0.044 µs. The range mask that `load_bitmap` builds on every call
(`BitMap64().add_range(c<<32, (c+1)<<32)`) covers 2^32 values as **65,536 run containers**.
Building and freeing it alone takes a median 3.2 ms (2.2 ms build, 1.3 ms free), which is about
the whole per-call average. The AND itself (`frag & mask`) takes 5.8 µs. On the `mentions`
fragment a whole call takes 6.0-6.9 ms. The cost is per call and does not depend on row size.

**`neighbors` (warm Store, a fresh `QueryEngine` per call as in `graphread`, `strict=True`; 35
seeds; every result asserted IDENTICAL):**

| Seed in-degree (partition p50 = 1, p90 = 13, p99 = 255, max 5445) | Depth | \|result\| | Today med / p90 | Pre-split med / p90 |
|---|---|---|---|---|
| 1 (14 seeds) | 1 | 1 | 117-134 / 121-145 ms | 14.1-16.5 / 14.5-21.3 ms |
| 4-33 (9 seeds) | 1 | 4-30 | 119-135 / 122-136 ms | 15.1-18.9 / 15.6-19.8 ms |
| 62-243 (6 seeds) | 1 | 55-199 | 130-150 / 131-156 ms | 21.4-38.3 / 21.9-38.9 ms |
| 496-2429 (6 seeds) | 1 | 388-1793 | 120-166 / 122-167 ms | 14.9-59.8 / 15.3-60.0 ms |
| 1 (14 seeds) | 2 | 1-27 | 217-241 / 225-258 ms | 15.0-20.1 / 15.4-21.9 ms |
| 4-13 | 2 | 7-31 | 547-1494 / 570-1536 ms | 16.4-18.5 / 17.5-18.9 ms |
| 30-62 | 2 | 30-91 | 2.6-5.9 / 2.7-5.9 s | 18.6-26.6 / 19.1-27.1 ms |
| 161-243 | 2 | 174-620 | 12.6-20.8 / 12.7-21.0 s | 35.6-70.1 / 36.7-70.5 ms |
| 496-917 | 2 | 879-1641 | 40.6-72.4 / 40.8-72.9 s | 16.5-113 / 17.0-121 ms |
| 2429 | 2 | 3634 | **186.5 s / 187.0 s** | **21.1 / 21.8 ms** |

Per-seed lines are in q3.out and q3b.out. The prototype's floor of about 15 ms is SQL it shares
with today's code (`noise_concept_ids` at 8.5 ms, plus `resolve_concept_ids` and
`denotes_equivalents`). **Frequency:** `query.log` shows **1** `neighbors` call in 7 days (406 ms).
The per-call gain is large, but almost nothing calls it.

**A no-new-state alternative for the same primitive (q_loadbitmap.out, q_scanmatch.out):**

| Row extraction | `mentions` row (6-7 ms today) | 20 concepts × 34 linkages | Identity |
|---|---|---|---|
| `load_bitmap` today | 6.06-6.89 ms | 2149 ms | |
| `iter_equal_or_larger` scan (no mask) | 2.80 ms | 102 ms | 123,448/123,448 rows, plus 406 samples against `load_bitmap` |
| lazily decoded sorted `uint64` array + `np.searchsorted` | **24 µs** | not measured | 123,448/123,448 rows, plus 280 samples. Decoding all 34 fragments: 80 ms (fresh Store, includes the fragment loads), 9.4 MB |

On the per-prompt path, `match_concepts` (via `_salience`, scan.py:181) makes a median of 3.5
`load_bitmap` calls per prompt (p90 7, max 18) on 40 recent prompts. It runs 234.6 ms median today
and 206.0 ms with searchsorted rows, a saving of about 29 ms per prompt. Outputs were identical
40/40.

## Q4: transposed fragments ((entity << 32) | concept) {#q4}

| Measurement | Value |
|---|---|
| Build, all 34 linkages, fragments warm | 124 ms median (p90 126) |
| Serialised size | 5,210,300 B, or **0.73×** the original fragments' 7,139,742 B. It would be a second on-disk copy |
| Serialise / deserialise | 18.6 ms / 29.9 ms |
| Forward lookup over all linkages, transposed BitMap64 (range_cardinality pre-check + mask AND) | **3.5-14.0 ms** median across 11 entities with out-degree 1-310 |
| Same lookup via `entity_links` SQL (`WHERE entity_id=?`) | **0.41-0.86 ms** median |
| Forward pre-split rows in memory `{linkage: {entity: BitMap}}` (q4b) | build 195 ms; lookup **2.9 µs** median (p90 3.9) against 0.40 ms for SQL, on 63 entities |
| Set identity | transposed vs SQL: 0/11 mismatches. Forward rows vs SQL: 0/63 |

The transposed BitMap64 is **slower than the SQL it would replace**. It pays the same per-linkage
range-mask cost that `load_bitmap` does. I found no hot forward-lookup caller that the in-memory
forward rows would serve.

## Q5: filter bitmaps {#q5}

| Bitmap (partition 4) | Build from catalog (median) | Cardinality | Serialised |
|---|---|---|---|
| noise (concepts) | 1.84 ms | 28,285 | 11,427 B |
| protected | 1.17 ms | 2,427 | 5,701 B |
| partition (all entities) | 18.1 ms | 127,047 | 139,935 B |
| kind=concept / code / doc / memory | 9.9 / 1.5 / 1.3 / 0.8 ms | 114,562 / 10,140 / 1,779 / 566 | 126,908 / 12,474 / 4,568 / 1,601 B |
| **All of them, once** | **about 34.5 ms** | | |

Today: `noise_concept_ids()` costs **8.5 ms** (p90 9.3) on every new `QueryEngine`, because it
returns a Python set. `BitMap(noise)` as `neighbors` builds it costs 8.2 ms in total.
`QueryEngine._universe()` costs **49.6 ms** against 18.1 ms for the partition bitmap, with
identical sets. The gain is small and confined to low-frequency query paths.

## Q6: `topn` {#q6}

| bm | Today (1 run) | Pre-split rows | Pre-split + per-call concept-set SQL | Identity |
|---|---|---|---|---|
| \|bm\| = 1 | **461.7 s** | 35.5 ms (p90 39.8) | 171.6 ms (p90 177.2) | identical |
| \|bm\| = 1793 | **464.6 s** | 94.8 ms (p90 95.7) | 232.9 ms (p90 235.5) | identical |

Today's cost is about 123k `load_bitmap` calls at 3-6 ms each, whatever the size of bm. `topn` is
reachable only through PQL `TopN` (query.py:470). The logs record no PQL TopN calls this week.

## Recommendation, ranked by benefit/cost {#recommendation}

Caveat for every option: **any new ON-DISK copy of the bitmap matrix needs a census of the
merge, purge and slot-swap paths** before it ships. That is the bug-105 cross-partition fragment
contamination and the bug-216/227 history. In-daemon-memory or per-process structures do not need
one: they die with the process and are invalidated at the write-batch boundary
(`_invalidate_content_rank_caches`). One related open question: `adjacency.cache.npz` is already an
on-disk derived copy, keyed on facts.log size. I did not check whether a purge or merge can change
the graph without growing facts.log.

1. **Vectorised adjacency build (no new state).** Build the CSR directly with numpy:
   **506 ms against 1559 ms** (1364 ms build + 195 ms from_dict), about 3×, with an identical edge
   set. It speeds up every miss: `cached_adjacency` cold, `rmx context --degree 1`, and all five
   bypass sites. Risk: low to medium. Row order differs, but PPR outputs on 18 seed sets were
   bit-identical. Expected effect on the hook: the per-prompt PPR path drops from 1.32 s to
   about 0.51 s (build) plus about 8 ms (walk), on every prompt and whatever the cache hit rate.
   Because the build then returns a CSR, this needs the dict-API adapter from (2).
2. **Point the per-prompt PPR rerank at the adjacency cache** (`ppr.rank_related_for_prompt`,
   and the same adapter for enrich and net). This needs a dict-compatible overlay over the CSR and
   a CSR-aware `seed_coverage`. Measured: **8.4 ms against 1322 ms** with the CSR warm, outputs
   identical 18/18. In today's one-shot hook process, the facts.log-keyed disk tier would have
   been fresh for at most 25 of 390 prompts. Most of the benefit therefore depends on (1), or on
   keeping the CSR **in daemon memory** with an off-lock vectorised rebuild (about 0.5 s) after each
   write batch, which the hook then reads. That variant adds no new on-disk copy. Benefit: the
   largest per-prompt saving available, on the most frequent path (389 per week). Cost: medium (an
   adapter, plus a daemon read path if the in-memory variant is chosen).
3. **Fix `load_bitmap`'s range mask (no new state).** Each call allocates and frees a 65,536-container
   mask (about 3.2 ms). A lazily decoded sorted array per linkage with `np.searchsorted` returns
   identical rows (123,448/123,448) in 24 µs against 6-7 ms, for 80 ms and 9.4 MB per process. The
   iterator variant needs no extra memory and still cuts the 20×34 mix 21× (2149 → 102 ms). It
   helps every `load_bitmap` caller: about 29 ms per prompt in `match_concepts`, the
   `context.py` bundles (1164, 1191, 1221), `co_occurrence` and DSL terms. Since the mask is
   most of today's `neighbors` and `topn` cost, it should remove most of that too; I did not
   measure that end to end. Cost: low (a single method). Risk: low.
4. **Pre-split rows in daemon memory**, if `neighbors`, `topn` or `co_occurrence` matter. The
   gains are dramatic per call (neighbors d2 off a hub: 186.5 s to 21 ms; topn: 462 s to
   35-95 ms) for a 167 ms build and 14.6 MB. The logs show about 1 call per week, so do (3) first:
   it takes most of the same win with no invalidation logic.
5. **Filter bitmaps (noise, protected, kind, partition):** 34.5 ms to build all of them once,
   saving 8.5 ms per QueryEngine on noise and 31 ms on `_universe`. Cheap, but it serves
   low-frequency paths. Fold it into (4) if (4) is done.
6. **Do not build transposed fragments on disk.** Forward lookups were 3.5-14 ms against 0.4-0.9 ms
   for SQL, plus 5.2 MB of new on-disk state that would need the census. If a hot forward-lookup
   caller turns up, in-memory forward rows (2.9 µs, 195 ms build) are the right shape.
