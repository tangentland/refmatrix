---
gmd: "0.1"
id: PERFORMANCE
title: "refmatrix — Performance"
tags: [performance, scoring, benchmarks, eval]
---

# refmatrix — Performance {#root}

rel: related-to -> [[SYSTEM]]
rel: related-to -> [[ARCHITECTURE]]

This document covers the performance model: where the speed comes from, where
the bottlenecks are, what the scoring stack does, and how rmx benchmarks
against vector retrieval (CodeRankEmbed) on the standard CSN evaluation.

## Where the speed comes from {#where-the-speed-comes-from}

### 1. Roaring bitmaps for set operations {#1-roaring-bitmaps-for-set-operations}

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

### 2. DuckDB catalog (phase 3) for analytics {#2-duckdb-catalog-phase-3-for-analytics}

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

### 3. Daemon hot-path — eliminate process / catalog open cost {#3-daemon-hot-path-eliminate-process-catalog-open-cost}

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

### 4. Incremental sync — skip-on-unchanged {#4-incremental-sync-skip-on-unchanged}

`sync.py:_sync_paths()` compares each touched file's disk mtime against
`tracked_files.mtime` (`sync.py:129-140`). Unchanged files are skipped
before any extraction work happens. Practical effect: a `git commit` that
touches 3 files triggers ~3 reingest passes, not a full reindex.

### 5. Deferred cross-file linkages {#5-deferred-cross-file-linkages}

`store.deferred_links()` is a context manager that buffers cross-file
linkages (e.g. `Foo defines Bar` where `Bar` is mentioned in another file's
docstring) and flushes them in one batch at end-of-pass instead of writing
per-file. This is what made the markdown/ADR/pseudo ingest passes
order-independent and ~3x faster on large doc trees.

## Bottlenecks and their mitigations {#bottlenecks-and-their-mitigations}

| Bottleneck                                       | Mitigation                                             |
|--------------------------------------------------|--------------------------------------------------------|
| First-ever ingest (no `.tldr` cache)             | `rmx tldr-warm . --semantic` — one big amortized pass  |
| Concurrent catalog writers (editor + watcher)    | `rmx daemon start` — single writer, socket-mediated    |
| `Stop` hook blocking agent shutdown              | `flush_queue_async` — return immediately, drain async  |
| DuckDB file growth from churn                    | `rmx compact` (EXPORT/IMPORT) — reclaim free space     |
| Noisy ubiquitous concepts (`self`, `the`, etc.)  | `rmx prune-noise --min-df 2 --max-df-ratio 0.5`        |
| Bitmap fragments holding deleted entity ids      | `rmx vacuum` — drop zero-linkage concepts + stale rows |
| DuckDB WAL bloat on rapid bursts                 | `rmx checkpoint` (also auto-run inside daemon)         |
| Resident model fattening the daemon into jetsam   | Models run in worker processes (default; `RMX_EMBED_SUBPROC=0` opts out) |

## Model processes — `RMX_EMBED_SUBPROC` and the rerank stage {#model-processes-rmx-embed-subproc-and-the-rerank-stage}

macOS jetsam SIGKILLs the fattest unmanaged anonymous process under system
memory pressure. A daemon that has served one recall holds a resident
sentence-transformers model; a daemon mid-ingest holds a large working set;
together they are the fattest process on the box, and SIGKILL is uncatchable.

In-process eviction cannot fix this. Dropping the model reference and calling
`gc.collect()` returns only ~84 MB of ~610 to the OS — torch's caching
allocator never gives the rest back on macOS. That fix shipped, was measured,
and was reverted.

So the model runs in a worker process instead (`refmatrix.embed_worker`,
spawned via `subproc.WorkerClient`). **This is the default**; set
`RMX_EMBED_SUBPROC=0` to opt back into the in-process model. Measured on this
repo, one embed + one ANN search, with the reranker enabled:

| Layout                    | Daemon RSS | Embed worker | Rerank worker | Fattest process |
|---------------------------|-----------:|-------------:|--------------:|----------------:|
| `RMX_EMBED_SUBPROC=0`     |   695 MB   |            — |             — |      **695 MB** |
| Default (worker process)  | **203 MB** |     576 MB   |      565 MB   |        576 MB   |

Three things change:

1. **The daemon stops being the jetsam target.** It drops to ~203 MB; the
   fattest process becomes a worker that can be respawned in seconds without
   touching the store, the catalog lock, or an in-flight ingest.
2. **Eviction becomes real.** `RMX_WORKER_IDLE_S=<seconds>` reaps an idle
   worker on the flush tick. The memory comes back because the process is
   gone — the thing in-process eviction could not deliver.
3. **A second model becomes affordable.** The cross-encoder reranker is
   subprocess-only by policy. In-process it would push a single process past
   1.2 GB; as its own worker it is just another evictable child.

If the worker cannot be spawned at all — an interpreter the child cannot reach,
a sandbox that forbids `fork`/`exec`, a pipe the OS refuses — the daemon logs
the failure and falls back to the in-process model rather than losing dense
retrieval. The log line is deliberately loud: the daemon is then carrying the
model's RSS again, which is the condition this whole mechanism exists to avoid.
A missing `[dense]` extra is not caught by that fallback, since the in-process
path would fail identically.

### The rerank stage {#the-rerank-stage}

The cross-encoder pass over the retrieved shortlist is **on by default**
(`RMX_RERANK=0`, or `--no-rerank` per call, disables it). BM25 and the
bi-encoder both score query and document
*independently*, which is what makes them cheap enough to run over a whole
partition and also what caps their precision. A cross-encoder scores the pair
jointly, so it can separate "the term appears" from "this is about that".

It reorders; it cannot recall. The op over-fetches
`k × RMX_RERANK_POOL_MULT` (default 4, capped by `RMX_RERANK_MAX_POOL`=100)
before reranking, because a true hit outside the retrieved pool is unreachable
no matter how good the reranker is. If recall is the problem, raise `-k`.

Every failure degrades to retrieval order and logs why: no `[dense]` extra, a
worker that died twice, a model that will not load, or a model that returns
non-finite scores. That last one is not hypothetical —
`cross-encoder/ms-marco-MiniLM-L-6-v2` returns NaN for every pair under
transformers 5.8.1 / torch 2.12, which is why the default is the L-12 sibling
and why `reranker._checked` rejects non-finite scores rather than sorting by
them (NaN compares False against everything and silently scrambles a ranking).

Both models therefore run out-of-process by default: the embedder because the
daemon must not be the jetsam target, the reranker because it is a second model
and only affordable as its own evictable child.

### Environment variables {#environment-variables}

| Variable                | Default | Effect                                             |
|-------------------------|---------|----------------------------------------------------|
| `RMX_EMBED_SUBPROC`     | `1`     | Run the embedder in a worker process (`0` opts out)|
| `RMX_WORKER_IDLE_S`     | `0`     | Reap workers idle this many seconds (`0` = never)  |
| `RMX_WORKER_TIMEOUT_S`  | `300`   | Per-call budget before a wedged worker is killed   |
| `RMX_RERANK`            | `1`     | Cross-encoder rerank stage (`0` opts out)          |
| `RMX_RERANK_MODEL`      | `cross-encoder/ms-marco-MiniLM-L-12-v2` | Reranker checkpoint |
| `RMX_RERANK_POOL_MULT`  | `4`     | Candidates reranked per `k` requested              |
| `RMX_RERANK_MAX_POOL`   | `100`   | Hard cap on the rerank pool                        |

## The scoring stack — when ranking matters {#the-scoring-stack-when-ranking-matters}

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

### Reciprocal Rank Fusion (RRF) for multi-signal fusion {#reciprocal-rank-fusion-rrf-for-multi-signal-fusion}

`fuse_rrf` (`query.py:33-49`, k=60) combines rankings from multiple linkage
types without needing per-linkage hyperparameters. Used heavily inside
`context.py` for symbol neighborhood walks (`_fused_rows`,
`_entity_anchored_rows`).

### Production variant {#production-variant}

| Variant name                       | Components                                                 |
|------------------------------------|------------------------------------------------------------|
| `tf_rrf` (baseline)                | Plain term-frequency rankings fused with RRF               |
| `bm25_docstring30_cov30_cm20` ★    | BM25 + docstring linkage 0.30 + coverage^3 + co-mention^2  |

★ is the tuned production variant. Configured in `eval/run.py:52-80`.

## Benchmark results {#benchmark-results}

### Two harnesses — and why only one of them counts {#two-harnesses}

Until 0.52 the headline CSN number came from `eval/run.py --model rmx`, a
BESPOKE index build (own tokenizer, per-token `add_concept`) that never called
`refmatrix.ingest`. Its 0.972 MRR@10 was a true number about code users never
executed. `eval/production/csn_code.py` is the honest harness: it materializes
the BEIR corpus as real files, runs production
`ingest_path(..., semantic=True)`, and ranks through `Store.content_rank` —
the exact functions `rmx ingest` / `rmx context` call. The number to defend
is the production one. {#honest-harness}

### CSN Python — production path (43 827 docs · 14 918 queries) {#csn-python-production}

| Retriever | MRR@10 | R@1 | R@10 | nDCG@10 |
|---|---|---|---|---|
| **rmx, production path** (shipped tuned stack) | **0.961** | 0.944 | 0.984 | 0.967 |
| CodeRankEmbed (dense, GPU) | 0.959 | 0.934 | 0.993 | 0.967 |
| rmx bespoke harness (historical, tuned) | 0.972 | — | — | — |

The production row is read from the committed artifact
`eval/production/results/csn_python/metrics.json` (full corpus, 43 827 docs ·
14 918 queries; `eval/production/csn_code.py --out …` at a965805 / 0.69.1,
2026-09-15: ingest 1913 s, retrieval 390 s); `tests/test_eval_artifact_cited.py`
compares the cited MRR@10 with the artifact. {#benchmark-artifact}

The production path is within a point of the bespoke index and still beats the
neural baseline — with no embeddings, no GPU, and `file:line` evidence behind
every score. The −0.011 vs bespoke is the honest cost of the plainer
production semantic pass vs the benchmark-tuned per-linkage tokenizer.

### CSN JavaScript / TypeScript (bespoke harness, historical) {#csn-js-ts}

| Corpus | rmx MRR@10 | CodeRankEmbed | Δ |
|---|---|---|---|
| csn_javascript | **0.939** | 0.916 | +0.023 |
| csn_typescript (real-world, fork dupes) | **0.365** | 0.358 | +0.007 |

Same-direction wins on three languages; margin compresses on noisier
real-world corpora. These two predate the production harness and carry its
caveat.

### The main-path incident — why every 2026-09-03 result was re-run {#main-path-incident}

Measured at 0.48.0: **43–83% of entities across the live fleet had zero
indexed terms.** `rmx ingest .` never GMD-dispatched markdown (plain `.md`
emitted no body terms), and `--semantic` was opt-in with no daemon setting
it — so the "full rebuild" produced stores whose content was structurally
unsearchable, and the mtime stamp then hid it from sync forever. The 0.48.0
fix (markdown→GMD dispatch, lenient parse, semantic default-on) plus
`rmx reingest --force` (0.49) invalidated and re-ran all eight open retrieval
experiments. Standing lesson: **benchmark the path users run** — a true
number about a bespoke path hid four defects. {#measure-the-path}

### Eval harnesses {#eval-harnesses}

```bash
# honest: production ingest + content_rank
python eval/production/csn_code.py --dataset csn_python

# historical: bespoke index, tuning ablations
python -m refmatrix.eval.run --dataset csn_python --variant bm25_docstring30_cov30_cm20
```

Metrics emitted (`eval/metrics.py`): `mrr@10/1000`, `recall@1/10/100/200/500/1000`,
`nDCG@10`. Results land in `eval/results/<dataset>/<variant>/run.tsv`.

## Proactive retrieval — the MemAware benchmark {#memaware}

CSN grades a lookup someone asked for. MemAware (`eval/memaware/`, Layer A:
90 questions, deterministic, no LLM) grades whether the system surfaces past
context **nobody asked for** — `rmx scan-prompt`'s actual job. rmx started
far behind and closed most of the ranking gap:

| Surface | hit@20 | MRR@20 | Note |
|---|---|---|---|
| bm25-per-session (reference) | 0.444 | 0.242 | flat BM25 over session files |
| `rmx context` (+lead signal) | 0.511 | 0.248 | +35% hit@20 from lead alone |
| `rmx scan-prompt` at 0.36.0 | 0.200 | 0.043 | starting point |
| `rmx scan-prompt` now | — | **0.241** | content fusion + bodies + rerank ≈ BM25 parity |

What moved it: per-concept content fusion with real idf/coverage (0.37.0,
hit@20 0.200→0.378), body text for rerank + candidate pool 10 (not 30 — a
bigger pool feeds the cross-encoder more distractors than signal), and the
`lead` linkage. **The remaining ceiling is recall, not ranking**: known-item
hit@1 on a healthy store is 0.808 post-re-derive (the earlier 0.447 "ceiling"
was pool contamination from the main-path incident), and questions whose gold
document is never retrieved are untouchable by any reordering prior. {#memaware-ceiling}

## Measured negatives — do not re-derive these {#negatives}

Ideas built, measured, and rejected; kept in-tree as documented conditions:

| Idea | Result | Why it loses |
|---|---|---|
| Degree-2 graph walk (`--rank enrich`) | MRR 0.013 vs PPR 0.065 — 5x worse | hop 2 from any hub concept is most of a bipartite corpus; PPR's restart bound adapts per node, a hop count can't |
| PRF query expansion from tldr bodies | 0.217 → 0.211 (5 terms) → 0.208 (10) | bodies describe nodes well, extend queries badly |
| Concept prefilter for dense ANN | exact null | candidate set already dominated by the same concepts |
| Phrase layer (skip-gram composition) | hit@20 identical | a phrase can't reach a doc its component words missed |
| RRF dense⊕symbolic recall fusion as default | dense 0.848 vs fused 0.794 MRR@10 | fusion wins Recall@10 (+0.143) and nDCG (+0.095) — right for set-oriented surfaces, wrong for top-1; `--fuse` stays opt-in |
| 7 of 8 structural signals (tags, heading depth, protected, …) | flat | only `lead` position paid: +20% MRR, +35% hit@20 on held-out questions |

PPR (personalized PageRank with salience-seeded restart) is the shipped
default ranking prior in `scan-prompt`; a dormant `--degree` flag holds the
graph-walk A/B for the helix phase-2 read. {#ppr-default}

## Doc–doc similarity: co-occurrence beats dense {#cooccurrence-vs-dense}

Scored against author-asserted `rel:` edges (138 linked pairs, 4 000 sampled
unlinked, one project): raw concept pair-overlap **AUC 0.929** vs dense
cosine **0.815**. Dense cosines compress into a 0.70–0.79 band inside one
project — same domain, same register, no range left to discriminate. Division
of labour: dense answers "is this about the query" (cross-domain); pair
overlap answers "which same-domain docs belong together". {#division-of-labour}

## LatticeDB, evaluated as a backend candidate {#latticedb}

Run as a fourth eval condition: index reachability fine (hit@500 0.722) but
its BM25 scored 0.0 across the board — ranking unusable as shipped. Not a
migration target; the DuckDB+Lance stack stays. {#latticedb-verdict}

## How `tldr` participates in performance {#how-tldr-participates-in-performance}

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

## Maintenance ops — keep the index lean {#maintenance-ops-keep-the-index-lean}

| Command            | What it does                                                                  | When to run                       |
|--------------------|-------------------------------------------------------------------------------|-----------------------------------|
| `rmx vacuum`       | Drop zero-linkage concepts, purge stale `tracked_files` rows                  | Weekly / after big deletions      |
| `rmx prune-noise`  | Mark/drop concepts with DF below `--min-df` or DF/N above `--max-df-ratio`    | After initial bulk ingest         |
| `rmx checkpoint`   | DuckDB WAL flush + index rebuild                                              | After write bursts (auto in daemon) |
| `rmx compact`      | DuckDB EXPORT to parquet then IMPORT back — reclaims fragmented space         | When `.refmatrix/catalog.duckdb` is >2x expected size |

## Profiling tips {#profiling-tips}

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

## Roadmap {#roadmap}

- **Helix phase 2 — edge time.** Phase 1 ships `[helix]` snapshot annotations
  on stale retrievals; the pre-registered criterion on `helix.log`
  (rendered-only rows) decides the storage fork: mutable edge-time columns vs
  versioned snapshots.
- **`scan-prompt --degree` hook flip.** The PPR-vs-degree A/B knob is wired in
  both eval harnesses; the flip is one settings edit once the criterion reads.
- **Recall tier for proactive retrieval.** MemAware's remaining gap is
  documents never retrieved at all; candidate-set work (not ranking priors)
  is the only lever left.
- **DuckDB+Lance fragment migration** (queued): bitmaps as DuckDB BLOBs →
  Lance columnar scan.
