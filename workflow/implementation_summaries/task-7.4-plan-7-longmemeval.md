---
gmd: "0.1"
id: task-7.4-summary
title: "Task 7.4 summary: the first LongMemEval numbers, and the latency claim that had to be retracted"
tags: [implementation-summary, plan-7]
metadata:
  node_type: summary
  task: task-7.4-plan-7-longmemeval
  created: 2026-09-16
---

# Task 7.4 summary {#root}

rel: realizes -> [[task-7.4-plan-7-longmemeval]]
rel: part-of -> [[plan-7-longmemeval]]
rel: evidence-for -> [[longmemeval-latency]]

## What shipped {#shipped}

`eval/production/longmemeval/REPORT.md` + `results/summary-symbolic-120.json`: 120 type-stratified
questions, `context` and `scan`, both haystack modes, on a 19,829-doc / 406,885-concept store.

`context` restricted: MRR@20 **0.679**, R@5 **0.605**, hit@5 0.683 — against a recall ceiling of
**0.683**. Saturated: every gold session that entered the depth-50 pool was ranked into the top 5,
so the figure measures retrieval DEPTH, not ranking.

## Three things this task got wrong {#wrong}

Recorded because the corrections are the durable part.

**1. The latency headline was measured in a storm window.** I reported `context` at 62.9 s and
`scan-prompt` at 75.9 s as "daemon warm, store resident", and framed rmx as ~4,500x slower than
agentmemory's 14 ms. The reranker was warm; the STORE was not — the daemon was building a 432 MB
`adjacency.cache.npz` (mtime 20:50, TEN MINUTES after the measurement) and replicating three 2.4 GB
catalog slots. Profiled on a quiet machine: `build_context` warm is **0.45 s**, of which BM25 over
406,885 concepts plus the graph walk is **0.37 s**. Retracted in full;
`workflow/measurements/longmemeval-latency.md` carries the decomposition. bug-031.

**2. Two causal stories, both wrong, both told before profiling.** First the graph walk (0.37 s
total). Then oversized memory bodies flooding the reranker (`MAX_DOC_CHARS = 2048` truncates
everything). Only the profile settled it, and what it settled is that the real open question is an
unattributed ~8.5 s gap between `build_context` (0.45 s) and the full daemonless CLI (9.0 s), of
which only 2.8 s is CPU.

**3. `--depth` never reached `scan`.** `_scan_argv` accepted `k` and dropped it while `_meta`
recorded depth=50, the table printed it, and REPORT.md's #1 next step was "re-run at --depth 200"
— which would have moved `context` and left `scan` byte-identical. ch-bsd r1 #b-6. So the committed
`scan` ceiling of 0.642 is scan-prompt's DEFAULT pool, and a reader comparing the two ceilings was
comparing different things.

## What the numbers cannot yet be used for {#limits}

- **Not comparable to agentmemory's 95.2% or mcp-memory-service's 80.4%.** Saturated; `restricted`
  is a post-hoc filter not a per-question index; neither published figure states its scoping.
- **`single-session-preference` at 0.200 is suspect.** bug-032: the cross-encoder scores only a
  document's first 2048 chars and **36.9%** of this corpus's answer-bearing turns sit beyond that.
  A preference stated once mid-transcript is exactly that artifact's shape.
- **The dense half is absent** — embed blocked on bug-030.

## The rule this task earned {#rule}

Before quoting a latency taken after any restart, rebuild, or first run of a store: diff the
store's own cache and slot file mtimes against the measurement time. A file written AFTER the
measurement means the measurement was taken during its construction. Recorded as bug-031.
