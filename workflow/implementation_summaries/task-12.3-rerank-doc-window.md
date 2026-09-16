---
gmd: "0.1"
id: task-12.3-rerank-doc-window-summary
title: "Implementation summary: the reranker reads where the query is — and keeps the head"
tags: [summary, plan-12, rerank, retrieval-quality]
metadata:
  node_type: summary
  task: task-12.3-rerank-doc-window
  created: 2026-09-16
---

# Implementation summary: task 12.3 (bug-032) {#root}

rel: implements -> [[task-12.3-rerank-doc-window]]
rel: part-of -> [[plan-12-open-bug-remediation]]
rel: evidence-for -> [[rerank-window-ab-0916]]

## What shipped {#shipped}

- `reranker.window_doc(text, query, limit=)` — half head, half query-anchored tail, with
  `WINDOW_MIN_CHARS` (1024) and `WINDOW_HEAD_FRAC` (0.5) knobs and `RMX_RERANK_WINDOW=0` to
  restore head truncation on a deployed binary.
- `reranker._anchor_window` — locating via `kwic.query_terms` + `kwic._first_hit`, filtered through
  the shared stoplist.
- Applied at BOTH cut points: `collect_rerank_docs(doc_chars=, query=)` and
  `Reranker.score` / `RemoteReranker.score`. `cli._replica_memory_recall` passes the query.

## The plan's hypothesis was wrong, and the measurement says so {#correction}

The spec proposed replacing head truncation with a KWIC window. On all 896 answer-bearing turns of
`longmemeval_oracle` at limit 2048 that measured **502 covered against 541 for the head it would
replace** — worse. 547 of the 896 answers are already in the first 2048 chars; anchoring away from
the head loses 158 to gain 119.

Keeping half the budget on the head and spending the rest where the query occurs: **672 (+24% over
head)**. And at the per-prompt hook's 700-char cap even that loses (500 vs 509), so the shipped
code falls back to byte-identical head truncation below 1024 chars. The always-on path is
unchanged; the gain lands on the 2048-char surfaces.

## RED / GREEN / mutation {#evidence}

- RED: `workflow/review-output/red-task-12.3.log` — 10 failed.
- GREEN: `workflow/review-output/green-task-12.3.log` / final run — 12 passed.
- Mutation (`window_doc` always returns the head): 6 tests RED.
- A/B: `workflow/measurements/rerank-window-ab-0916.md`.

## What is not claimed {#limits}

Coverage only. No end-to-end MRR/hit@5 claim: that run is ~2 h per arm on a surface whose reranker
usually does not answer under the load that matters, and bug-032's own attribution note (ch-bsd r2)
already limits its reach to `scan`.
