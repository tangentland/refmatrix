---
gmd: "0.1"
id: plan-20-concept-similarity-eval
title: "Plan 20: which signal may merge two concepts — a read-only, labelled evaluation"
tags: [plan, concepts, similarity, evaluation, helix, merge]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
---

# Plan 20: concept-similarity evaluation {#root}

**Date:** 2026-10-07
**Status:** Drafting. Task specs 20.1–20.3 are written.
**Origin:** the user, 2026-10-07: "explore concept similarity evaluation to assess
culling/merging", and later "free culls + eval, reconcile later". The merge target was decided the
same day: ADR-0004's term-space alias map, with plan-11 superseded.

rel: derives-from -> [[exploration-concept-similarity-cull-merge]]
rel: depends-on -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: related-to -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]

## Why {#why}

This store holds 75,276 concepts.
- Name normalization collapses 25,324 of them into **5,363 clusters**; 4,771 span namespaces.
- Some clusters are true merges (`launchctl` / `keyword/launchctl`). Others are traps (`__file__`
  vs `files`, the class `Store` vs the word "store").
- Merges are only safe when a signal can tell those apart.
- Prior measurement: co-occurrence beat dense embeddings for doc relatedness (AUC **0.929** vs
  **0.815**). Concept vectors embed little more than a concept's name. Name normalization cannot
  see synonyms (the phrase layer's 82% residual).

{#why-body}

## Scope {#scope}

**Evaluation only.** This plan writes NOTHING to any store. It produces a labelled pair set,
measured signals, and a recommended merge rule with its threshold. Writing merges into the alias
map belongs to ADR-0004's helix plan.

The free culls (9,182 orphan aliases, 747 empty protected `query/*` rows) go through
[[plan-22-audited-removal-and-repair]] (the ONE audited path, which repairs first and gates
concept culls on an ablation check), not this plan's. Merge writes were plan-22 task 22.4; since 2026-10-14 (d9j) they belong to the future ADR-0004 helix plan, and 22.4 is closed into it. No concept is removed on a similarity score: decay and similarity
may demote, never delete. {#scope-body}

## Tasks {#tasks}

| task | what | acceptance (summary) |
|---|---|---|
| 20.1 | labelled pairs: silver (alias→canonical, df ≥ 2 name clusters) + a ~200-pair gold sample incl. the symbol-vs-word traps; df-matched negatives | the set is frozen and committed before any signal runs; label agreement reported |
| 20.2 | signals: co-occurrence Jaccard / lift / NPMI (support as a gate), concept-vector cosine (percentile), name normalization, a fusion; AUC + precision@k on gold, across ≥ 3 stores | the table per store; a recommended rule + threshold, or "no signal is safe" |
| 20.3 | conditional synonym search (dense mutual-kNN pairs the names don't collapse): runs only if the concept-vector band is wide enough | the band measured first; if p95 − median < 0.1 it stops and says so |

## Decisions {#decisions}

| # | decision | source |
|---|---|---|
| d-1 | merges target ADR-0004's term-space alias map | user, 2026-10-07 |
| d-2 | free culls via plan-22 (originally "via 16.6"; moved by plan review C1) | user, 2026-10-07 |
| d-3 | gold labels: the gmd-curator agent proposes, the user reviews a 50-pair sample before the set freezes | default taken (exploration d-3 unanswered); revisable at spec review |
| d-4 | distributions measured on more than one project (cliquedb, viascope, cliquet, atldb, orderly, refmatrix) | user, 2026-10-07 ("use more than refmatrix's project") |

## Drift notes (2026-10-14) {#drift-2026-10-14}

- Every test and evaluation in this plan runs inside plan-23 task 23.0's sandbox (d1a/d1b); the
  labelled pair set (20.1) is built from a COPY of a store's read snapshot, never a live catalog.
- Raw labelled pairs drawn from real stores stay local; only their hash and a redacted fixture are
  committed (d8f).
- Usage counters referenced here are 19.2's raw per-evidence counts with weights and floors applied
  at read time (d9e; ADR-0004 `#a14-floor`).
- Wave placement: [[plan-review-2026-10-14#t10-waves]] (Wave 4).

rel: depends-on -> [[plan-review-2026-10-14#t10-waves]]
