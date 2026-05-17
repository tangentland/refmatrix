# refmatrix — Performance

This document covers the performance model: where the speed comes from, where
the bottlenecks are, what the scoring stack does, and how rmx benchmarks
against vector retrieval (CodeRankEmbed) on the standard CSN evaluation.

## Where the speed comes from

### 1. Roaring bitmaps for set operations

Every `(linkage_type, concept_id)` cell is a `BitMap64` of entity column ids,
packed as `(concept_id << 32) | entity_id` (`store.py:30-34`). Set ops are
roaring's native primitive:

| Operation                                | Cost                                              |
|------------------------------------------|---------------------------------------------------|
| `defines:X AND mentions:X`               | bitmap intersection — sublinear in entity count   |
| `defines:X OR mentions:X`                | bitmap union — sublinear                          |
| `defines:X AND NOT mentions:X`           | bitmap difference — sublinear                     |
| Compose 6 terms with parens              | composed bitmap algebra — still sublinear         |

The `grep "doesn't scale"` problem is precisely the one bitmaps make go away.
A 100-file codebase and a 100k-file codebase pay the same big-O for boolean
combinations of relations; only the constant differs.

### 2. DuckDB catalog (phase 3) for analytics

Phase 3 stores the entire catalog — entities, linkages, evidence, AND the
bitmap blobs — in a single DuckDB file (`duckdb_catalog.py:CATALOG_DDL`).
Benefits:

- One file, one lock, one transaction boundary.
- Analytical queries (top concepts, density, eval harness) compile to
  vectorized DuckDB plans instead of N+1 SQLite roundtrips.
- `entity_links` table shadows the bitmap content with weights so SQL queries
  can rank/filter without touching the bitmap layer.
- Bitmap fragments persist as BLOB rows in `bitmap_fragments`, UPSERTed
  atomically (`store.py:_flush_fragments_duckdb`, lines 839-863).

### 3. Daemon hot-path — eliminate process / catalog open cost

Every CLI invocation that *doesn't* go through the daemon pays:

- Python interpreter startup (~100ms baseline).
- DuckDB / SQLite file open + WAL replay.
- Bitmap fragment load on first access.

With `rmx daemon start`, the daemon owns the catalog forever and clients
send a JSON op over a Unix socket. Cost shifts to:

- Socket connect (~1ms).
- One JSON round-trip per op.
- Zero fragment reload — bitmaps stay loaded.

Measured: `rmx stats` drops from ~280ms (cold) to ~5ms (via daemon).
`rmx query` drops from ~350ms to ~15ms for a typical 3-term boolean.

### 4. Incremental sync — skip-on-unchanged

`sync.py:_sync_paths()` compares each touched file's disk mtime against
`tracked_files.mtime` (`sync.py:129-140`). Unchanged files are skipped
before any extraction work happens. Practical effect: a `git commit` that
touches 3 files triggers ~3 reingest passes, not a full reindex.

### 5. Deferred cross-file linkages

`store.deferred_links()` is a context manager that buffers cross-file
linkages (e.g. `Foo defines Bar` where `Bar` is mentioned in another file's
docstring) and flushes them in one batch at end-of-pass instead of writing
per-file. This is what made the markdown/ADR/pseudo ingest passes
order-independent and ~3x faster on large doc trees.

## Bottlenecks and their mitigations

| Bottleneck                                       | Mitigation                                             |
|--------------------------------------------------|--------------------------------------------------------|
| First-ever ingest (no `.tldr` cache)             | `rmx tldr-warm . --semantic` — one big amortized pass  |
| Concurrent catalog writers (editor + watcher)    | `rmx daemon start` — single writer, socket-mediated    |
| `Stop` hook blocking agent shutdown              | `flush_queue_async` — return immediately, drain async  |
| DuckDB file growth from churn                    | `rmx compact` (EXPORT/IMPORT) — reclaim free space     |
| Noisy ubiquitous concepts (`self`, `the`, etc.)  | `rmx prune-noise --min-df 2 --max-df-ratio 0.5`        |
| Bitmap fragments holding deleted entity ids      | `rmx vacuum` — drop zero-linkage concepts + stale rows |
| DuckDB WAL bloat on rapid bursts                 | `rmx checkpoint` (also auto-run inside daemon)         |

## The scoring stack — when ranking matters

Set ops are unranked by design. For *finding the right entity* (e.g. NL → code
retrieval, `rmx context`), refmatrix ranks via a composed scorer:

```
score(query, entity) = BM25(query, entity)
                     × coverage(query, entity) ** α
                     × Σ_linkage w_linkage × hits_linkage(query, entity)
                     × co_mention(query, entity) ** β
```

| Term            | What it measures                                              | Where                                                 |
|-----------------|---------------------------------------------------------------|-------------------------------------------------------|
| BM25            | TF/IDF-style term match against entity text                   | `eval/retrievers/rmx_retriever.py:_retrieve_bm25`     |
| coverage^α      | Fraction of query terms that hit the entity (raised to α=3)   | same                                                  |
| linkage weights | Per-linkage contributions (docstring linkage at 0.30, etc.)   | `eval/retrievers/rmx_retriever.py:373-407`            |
| co_mention^β    | Linkage-coupled co-mention (raised to β=2, NOT raw frequency) | `eval/retrievers/rmx_retriever.py:_retrieve_bm25_multi`|

### Reciprocal Rank Fusion (RRF) for multi-signal fusion

`fuse_rrf` (`query.py:33-49`, k=60) combines rankings from multiple linkage
types without needing per-linkage hyperparameters. Used heavily inside
`context.py` for symbol neighborhood walks (`_fused_rows`,
`_entity_anchored_rows`).

### Production variant

| Variant name                       | Components                                                 |
|------------------------------------|------------------------------------------------------------|
| `tf_rrf` (baseline)                | Plain term-frequency rankings fused with RRF               |
| `bm25_docstring30_cov30_cm20` ★    | BM25 + docstring linkage 0.30 + coverage^3 + co-mention^2  |

★ is the tuned production variant. Configured in `eval/run.py:52-80`.

## Benchmark results

### CSN Python — MRR@10

| Retriever                            | MRR@10  | Notes                                  |
|--------------------------------------|---------|----------------------------------------|
| rmx tuned (bm25_docstring30_cov30_cm20) | **0.972** | symbolic, no embeddings                |
| CodeRankEmbed                        | 0.959   | dense vector retrieval                 |
| rmx baseline (tf_rrf)                | ~0.90   | plain TF + RRF                         |

### CSN JavaScript — MRR@10

| Retriever                            | MRR@10  | Notes                                  |
|--------------------------------------|---------|----------------------------------------|
| rmx tuned                            | **0.939** | margin LARGER on JS than Python        |
| CodeRankEmbed                        | 0.916   |                                        |

The symbolic margin grows on JS because rmx's linkage-aware scorer benefits
from JS's higher density of cross-file relations (imports, requires, dynamic
dispatch surfaces) that vector retrieval flattens out.

### Eval harness — `eval/run.py`

```bash
# corpus ingest + parallel retrieve + metrics + run.tsv save
python -m refmatrix.eval.run --dataset csn_python --variant bm25_docstring30_cov30_cm20
```

Metrics emitted (`eval/metrics.py`):

- `mrr@10`, `mrr@1000`
- `recall@1/10/100/200/500/1000`
- `nDCG@10` (relevance-weighted)

Results land in `eval/results/<dataset>/<variant>/run.tsv`.

## How `tldr` participates in performance

`llm-tldr` does the expensive per-function semantic extraction *once*, into
a cache. refmatrix indexes from the cache, so the heavy lifting is amortized:

| Without llm-tldr                                  | With llm-tldr                                       |
|---------------------------------------------------|-----------------------------------------------------|
| `ingest --source tree`: file-level entities only  | `ingest --source metadata`: full per-unit semantics |
| No call graph                                     | Full call graph as `calls` / `called_by` linkages   |
| No signatures, docstrings, CFG/DFG summaries      | All staged into `entities.meta` JSON blob           |
| Scoring stack has less to work with               | Linkage-aware scorer has dense signal               |

`rmx tldr-warm` runs llm-tldr only on first ingest; thereafter the
incremental sync layer re-runs the tldr-aware ingest pass on `.py` changes
only when the call graph cache exists (`sync.py:171-178`). Non-Python file
changes skip the tldr step entirely.

## Maintenance ops — keep the index lean

| Command            | What it does                                                                  | When to run                       |
|--------------------|-------------------------------------------------------------------------------|-----------------------------------|
| `rmx vacuum`       | Drop zero-linkage concepts, purge stale `tracked_files` rows                  | Weekly / after big deletions      |
| `rmx prune-noise`  | Mark/drop concepts with DF below `--min-df` or DF/N above `--max-df-ratio`    | After initial bulk ingest         |
| `rmx checkpoint`   | DuckDB WAL flush + index rebuild                                              | After write bursts (auto in daemon) |
| `rmx compact`      | DuckDB EXPORT to parquet then IMPORT back — reclaims fragmented space         | When `.refmatrix/catalog.duckdb` is >2x expected size |

## Profiling tips

- `rmx telemetry` reads `.refmatrix/query.log` (JSONL) and summarizes p50/p99
  per op. Useful for spotting slow queries.
- `rmx daemon status` reports queue depth — a growing queue means the watcher
  is producing dirty paths faster than the daemon can ingest them. Usual
  cause: a build step touching thousands of files. Add the build output
  directory to `.tldrignore` (shared with llm-tldr) or to the watcher's
  `IGNORE_DIRS` list (`watch.py:26-40`).
- `rmx stats` shows entity counts per kind and total bitmap cardinality per
  linkage type. Outlier linkages (one type holding 90% of bitmap mass) often
  point at a noise concept that `prune-noise` should remove.

## Roadmap

- **Migrate fragment storage fully into DuckDB+Lance** (queued; see
  memory `project_queued_work`). Current phase 3 stores bitmaps as DuckDB
  BLOBs; Lance would give vectorized scan + columnar persistence.
- **JS/TS dataset expansion** (blocked on DuckDB+Lance migration). CSN JS
  result above is encouraging; broader JS/TS coverage needs more annotated
  corpus.
- **Optional embedding sidecar.** Symbolic stack already beats CodeRankEmbed
  on CSN; an embedding layer would be additive, not replacement — likely
  fused via RRF alongside the existing rankers rather than as a separate
  retrieval path.
