---
gmd: "0.1"
id: task-20.3-dense-synonym-search
title: "Task 20.3 (conditional): synonyms the names cannot see — run only if the concept-vector band can separate"
tags: [task, concepts, dense, synonyms, evaluation]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 20.3: dense synonym candidates (conditional) {#root}

> Plan: [plan-20-concept-similarity-eval](../plan-20-concept-similarity-eval.md)
> Status: Pending
> Depends on: 20.2

rel: part-of -> [[plan-20-concept-similarity-eval]]
rel: derives-from -> [[project_phrase_layer_closed]]

## Why {#why}

The phrase layer's residual was 82% hapax synonymy, "the dense channel's job". But a concept vector
embeds name + `canonical_name` + `tldr` (`embedder.py:313-349`), which is close to just the name.
The dense band may be too compressed to separate pairs, as it was for docs (0.70–0.79). {#why-body}

## Requirements {#requirements}

1. **R1 Band first.** Per store, measure the concept-vector cosine distribution over random pairs
   (median, p95, p99). **If p95 − median < 0.1, stop**, and record the band as the result.
2. **R2 Candidates.** Mutual-kNN pairs (k = 8) above the store's p99 whose names do NOT normalize
   together, top 200 per store.
3. **R3 Judged.** The gmd-curator agent labels each candidate `synonym | related | unrelated`, and
   the user reviews a sample of 30. The result is the curator acceptance rate (the Apriori
   standard).
4. **R4 No writes.** The candidates are a report, not merges.

## Acceptance criteria {#acceptance}

1. The band table per store, and the stop/go decision it implies.
2. If go: acceptance rate with a 95% interval; the top accepted pairs are listed for ADR-0004's
   alias-map plan.

## Files {#files}

`eval/production/concept_pairs/dense_synonyms.py`, a section in `REPORT.md`.
