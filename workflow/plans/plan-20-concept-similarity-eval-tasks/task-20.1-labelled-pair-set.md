---
gmd: "0.1"
id: task-20.1-labelled-pair-set
title: "Task 20.1: a frozen, labelled set of concept pairs — silver, gold, and df-matched negatives"
tags: [task, concepts, evaluation, labels]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 20.1: the labelled pair set {#root}

> Plan: [plan-20-concept-similarity-eval](../plan-20-concept-similarity-eval.md)
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-20-concept-similarity-eval]]

## Why {#why}

Every signal in 20.2 is judged against this set. The ch-bsd impression "who builds the sample"
applies: a set built by whoever tunes the threshold is a set that favours the tuning. It is
therefore frozen and committed before any signal is computed. {#why-body}

## Requirements {#requirements}

1. **R1 Silver positives.** Taken from a catalog COPY per store:
   - (a) alias → canonical `same_as` pairs (a sanity floor, expected trivially high);
   - (b) name-normalized cluster pairs where both members have df ≥ 2.

   Normalization: lowercase, strip `_`, `-` and spaces, simple plural, namespace dropped.
2. **R2 Gold.** ~200 cluster pairs, stratified:
   - at least 50 cross-namespace (`x` / `keyword/x`);
   - at least 40 symbol-vs-word candidates (one side a code identifier with a `defines` edge, the
     other a prose term);
   - at least 40 case-only variants;
   - the rest random.

   The gmd-curator agent labels each as `merge | distinct | unsure`, citing the evidence it
   looked at (definitions, top co-occurring entities). The user reviews a random 50 before the set
   freezes. Agreement is reported, and disagreements are resolved by the user.
3. **R3 Negatives.** Random concept pairs with df matched to the positives' df distribution
   (stratified by df bucket), so df alone cannot separate the classes.
4. **R4 Stores.** refmatrix, cliquedb, viascope, cliquet; atldb and orderly for silver only (they
   are small).
5. **R5 Frozen.** The set lives at `eval/production/concept_pairs/` as JSONL with a manifest
   (source store, catalog snapshot hash, seed). It is committed in its own commit BEFORE 20.2's
   first run.

## Acceptance criteria {#acceptance}

1. The manifest's catalog hashes match the copies used, and the seed reproduces the negatives.
2. Gold has the stratification above, and the user-reviewed sample's agreement rate is reported.
3. The commit order shows the set frozen before any signal output exists.

## Files {#files}

`eval/production/concept_pairs/build.py`, `pairs-<store>.jsonl`, `gold.jsonl`, `MANIFEST.json`.
