---
gmd: "0.1"
id: longmemeval-latency
title: "Profiling the 62.9 s: the retrieval core is 0.45 s — the headline number was measured in a storm window"
tags: [plan-7, measurement, performance, correction]
metadata:
  node_type: measurement
  task: task-7.4-plan-7-longmemeval
  created: 2026-09-15
  updated: 2026-09-16
  supersedes_own_earlier_claim: true
---

# Profiling the LongMemEval query cost {#root}

rel: evidence-for -> [[task-7.4-plan-7-longmemeval]]
rel: part-of -> [[plan-7-longmemeval]]
rel: reinforces -> [[impression_bsd_cost_measured_idle]]

**This file previously claimed rmx retrieval costs 62.9 s per query and is ~4,500x slower than
agentmemory's published 14 ms. That claim was wrong and is retracted here.** The profile is the
correction, and the correction is larger than the original finding.

## What the earlier version got wrong {#retraction}

Two errors, both mine:

1. **The number was measured in a storm window, and reported as steady state.** I wrote "daemon
   warm, store resident". The RERANKER was warm. The STORE was not: at the measurement time
   (~20:35–20:40) the daemon was building a **432 MB `adjacency.cache.npz`** (file mtime 20:50 —
   ten minutes AFTER the measurement) and replicating 2.4 GB catalogs across the A/B/read slots
   (`catalog.read.duckdb` 20:37, `catalog.A/B.offset` 20:28). The query was queued behind that.

   This is the exact mirror of [[impression_bsd_cost_measured_idle]] — that impression is about
   measuring in the quiet window and UNDER-reporting; this is measuring in the storm and
   OVER-reporting. Same class of error, opposite sign.

2. **The stated cause was wrong twice.** The earlier text pointed at "BM25 over 406,885 concepts,
   the graph walk, and the cross-encoder rerank". Profiled: BM25 + walk is **0.37 s**. A later
   hypothesis that oversized memory bodies were flooding the reranker is ALSO wrong —
   `reranker.MAX_DOC_CHARS = 2048` truncates every doc, and the recorded shared-worker cost is
   ~4.8 s for 10 docs at 28.7k chars.

## What the profile establishes {#measured}

Corpus: 19,829 session docs, 406,885 concepts, 2.44 GB catalog. 2026-09-16, load ~2.4.

| path | time | note |
|---|---:|---|
| `build_context` in-process, WARM | **0.45 s** | the retrieval core |
| ↳ `store.content_rank` (BM25 over 406,885 concepts) | **0.37 s** | 84 DuckDB executes, 0.14 s in the driver |
| `build_context` in-process, COLD | 3.30 s | first call, caches unbuilt |
| `Store._connect()` on the 2.44 GB catalog | 0.96 s | once per process |
| full CLI, daemonless, big store | 9.0 s | only 2.8 s CPU — ~6 s is wait |
| project store (small), daemon UP | 0.36–0.88 s | the daemon is not inherently slow |
| big store, daemon, DURING cache build | 62.9 s | **NOT steady state — retracted** |

**BM25 across 406,885 concepts costs 370 ms.** The retrieval algorithm is not the problem, and the
"different product category" framing the earlier version reached for is not supported.

## What is still unexplained, and is the real finding {#open}

Daemonless full-CLI on the big store is **9.0 s** while `build_context` inside it is **0.45 s**.
That ~8.5 s gap is process startup + imports + a 0.96 s store connect + cold caches. And only 2.8 s
of the 9.0 s is CPU, so roughly 6 s is waiting on something.

That gap — not the 62.9 s — is the honest performance question, and it is NOT yet attributed.

## What would settle the steady-state number {#next}

Restart the benchmark daemon, let it settle (the adjacency cache and all three catalog slots are
now BUILT, so a restart should not repeat the storm), confirm the store is quiet, then re-measure.
Cost: ~9 min to bind plus settle time. NOT run here — the user gated new benchmark runs behind the
open `@ch-bsd` findings.

Until that runs, **no per-query latency figure for the big store should be quoted**, including the
ones in this file's own table beyond the in-process rows.

## Rule this earns {#rule}

Before quoting a latency taken after any restart, rebuild, or first-run of a store: check the
mtimes of the store's own cache and slot files against the measurement time. A file written AFTER
the measurement means the measurement was taken during its construction.
