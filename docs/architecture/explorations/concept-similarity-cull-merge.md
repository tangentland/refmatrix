---
gmd: "0.1"
id: exploration-concept-similarity-cull-merge
title: "Exploration: concept similarity as the evidence for culling and merging concepts (helix)"
tags: [exploration, helix, concepts, dedup, cull, merge, evaluation]
metadata:
  node_type: exploration
  status: in-progress
  created: 2026-10-07
---

# Exploration: concept similarity for cull/merge {#root}

**Date:** 2026-10-07
**Status:** Research Complete. Decisions are pending with the user ([[#decisions]]).
**Motivation:** The user, 2026-10-07: "in regards to the helix plan we should explore concept
similarity evaluation to assess culling/merging". The question is which similarity signal can
safely decide that two concepts are one (merge), or that a concept carries nothing (cull), and how
we would KNOW, measured rather than assumed.

rel: related-to -> [[plan-11-helix-phase2-versioned-graph]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: related-to -> [[task-16.6-learned-row-validation]]
rel: derives-from -> [[project_cooccurrence_beats_dense_for_doc_similarity]]
rel: derives-from -> [[project_phrase_layer_closed]]
rel: derives-from -> [[project_concept_path_negatives_0903]]

## Background {#background}

**Helix.** Phase 1 (0.55.0) annotates a stale retrieval with a `[helix]` block. Its usage signal
is confounded: the scan-prompt hook gates itself off (`helix.py:256`), and only anchors are
annotated, never neighbours (`project_helix_log_confounded`).

Phase 2 (`plan-11`, drafting) chose Option B on 2026-09-16: a from-scratch versioned prolly
store. Q1–Q4 are tentatively approved and tasks 11.1–11.4 are unwritten.

**ADR-0004 contradicts plan-11.** It declares `supersedes -> project_helix_phase2_storage_fork` and
replaces that fork with:
- snapshot manifests plus age-tiered bitmaps;
- a term-space alias map in place of the ~36k `same_as` rows;
- deletion of `phrase/*`;
- an L3 "promoted concepts" layer.

plan-11 still treats the fork as live. **This must be reconciled before either is built.**
Wherever helix lands, it is the natural source of a *cold concept* signal (when an edge to a concept
was last touched) and of *neighbourhood drift* (version diffs). These are cull and merge inputs that
no current code has. {#helix}

**What exists today** (file:line from `src/refmatrix/`):
- **`_concept_variants` / `add_concept`** (`store.py:176`, `:2369-2391`): space and dash spellings
  become alias rows with `same_as` → the underscore canonical. Query time unifies on
  `canonical_name`.
- **`same_as_audit`** (`store.py:3309`): read-only tripwire.
- **`fold_concept_dups`** (`store.py:5803`): folds a concept only into a memory with the same name.
  It is not a general merge.
- **`prune_noise`** (`store.py:6974`): df thresholds on `keyword/*`; skips protected; marks or
  drops.
- **`memory compile`** (`consolidate.py`): dense⊕concept fusion, mutual kNN, p95 threshold. It
  works on MEMORIES only.
- **Concept vectors** (`embedder.py:313-349`) embed name + `canonical_name` + `tldr`. A bare concept
  embeds little more than its name.

{#exists}

**Prior measurements that constrain this:**

| finding | numbers | consequence here |
|---|---|---|
| co-occurrence beats dense for doc relatedness | AUC **0.929** vs **0.815**; dense cosines bunch in 0.70–0.79 | co-occurrence is the first-class merge signal |
| memory compile thresholds | median cosine 0.733, p95 0.823; an absolute 0.55 gave one blob | percentile + mutual-kNN, never an absolute cosine |
| concept-path association | lift **0.007** vs PPR **0.069** MRR; support as a multiplier was a trap | lift with support as a GATE |
| phrase layer closed | 42k → 549k concepts, zero hit@20 gain; 82% hapax is synonymy | name normalization cannot find synonyms |
| variant expansion | isolated MRR 0.043 → 0.065, masked negative in the full pipeline | evaluate on the ISOLATED path |
| structural signals | `protected` changed 0/400 queries | protection carries no ranking value |

{#prior}

## Findings: this repo's store (catalog copy, partition `refmatrix`) {#findings}

- **75,276 concepts.** No prefix 33,518; `phrase/` 29,051; `keyword/` 7,945; `query/` 2,284;
  `gf/` 1,929; others under 600. `sessions-refmatrix` holds another 25,441.
- **Noise:** 28,285 rows, all `phrase/*`.
- **Protected:** 868 rows, all `query/*`. **747 of them have df ≤ 1**: protected and nearly empty.
  That is grep-learning's accretion, which task 16.6 targets.
- **Alias rows:** 39,030.
  - **9,182 are orphans**, with no `same_as` edge and no other edge. They are pure cull
    candidates with no similarity question at all.
- **Real concepts (36,246).** df percentiles p25/50/75/90/95/99 are 1/1/4/14/32/135.
  **58% have df ≤ 1.** Excluding phrases, 14,399 of 29,619 do.
- **Name-normalized clusters** (case, `_-` and space, simple plural, namespace dropped):
  - **5,363 clusters** cover 14,653 rows, 9,290 of them excess.
  - **4,771 span namespaces** (e.g. `launchctl` / `keyword/launchctl`).
  - Only 272 already share a `canonical_name`.
  - 2,832 have at least two members with df ≥ 2.
  - Examples: `Store`(424) `_store`(264) `keyword/store`(189) `stores`(116);
    `kind/function`(1990) `function`(140) `functions`(25); `also`(251) `Also`(10) `ALSO`(2).
  - Some are true merges and some are traps: `__file__` vs `files`, and a class `Store` vs the
    word "store".
- **Vectors:** `concept.lance` holds 64,763 vectors; **10,513 concepts are unembedded**.

{#data}

The shape is clear. Two classes need NO similarity model: the orphan aliases and the empty protected
`query/*` rows. A third class, the cross-namespace name collisions, is large, and the cheap signal
there (the name) is known to be both incomplete (it misses synonyms) and unsafe (it conflates a
symbol with an English word). {#shape}

## Option A: merge evidence by co-occurrence, labelled against silver pairs {#option-a}

**Positives:**
- the 29,848 alias→canonical `same_as` pairs (trivial; a sanity floor);
- normalized-name cluster pairs where both members have df ≥ 2 (silver);
- a hand-labelled sample of ~200 cluster pairs (gold), including the symbol-vs-word traps.

**Negatives:** random pairs with matched df.

**Signals:**
- Jaccard and lift of the two concepts' entity sets, with support as a gate;
- concept-vector cosine (percentile-normalized);
- name normalization;
- a fused score.

**Metrics:** AUC, plus precision@k on the gold sample.

**Decision it drives:** which pairs enter the alias map (ADR-0004's term-space map, or today's
`same_as`).

**Cost:** reads only; a script over a catalog copy plus Lance.

**Risk:** the silver labels are name-derived, so they favour the name signal. Only the gold sample
can rank the name signal honestly. {#option-a-body}

## Option B: cull by measured usefulness, not by df {#option-b}

**Candidate set:**
- df ≤ 1 concepts;
- orphan aliases;
- empty protected `query/*` rows;
- later, helix age tiers.

**Test:** ablate the set on the production eval path (`eval/production`, MemAware, CSN, cliquedb).
That means paired per-query deltas on the ISOLATED concept path, because the full pipeline masked
variant expansion before, plus hit@k on the full path.

**Decision it drives:** `noise=1` versus drop, and the default `prune_noise` scope. Today that scope
is `keyword/*` only.

**Cost:** one ablation flag in the existing harness.

**Risk:** a concept with no retrieval value may still carry curation value (`rel:` anchors,
subjects). Exclude `#`-anchored GMD nodes and any concept with a non-`mentions` edge. {#option-b-body}

## Option C: synonyms the names cannot see {#option-c}

**Method:** mutual-kNN pairs above a percentile on concept vectors, whose names do NOT normalize
together. A curator judges the top-k.

**Metric:** curator acceptance rate, the Apriori standard.

**Decision it drives:** synonym merges, the phrase-layer's 82% residual.

**Risk:** bare concepts embed little more than their names, so the dense band may be as compressed
as it was for docs. Measure the band first, and stop if p95 − median is below about 0.1. {#option-c-body}

## Recommendation {#recommendation}

Run **B's free part first**, then **A**, and treat **C** as conditional.

1. **Cull what needs no model.** Orphan aliases (9,182) and empty protected `query/*` rows (747)
   go, behind a dry run and an ablation check. This overlaps task 16.6's prune, so build it there.
2. **A's evaluation**, as a read-only script on a catalog copy. It decides whether co-occurrence
   (expected), names, or a fusion drive merges, and at what threshold.
3. **C only if** the concept-vector band is wide enough to separate (measure first).
4. **Reconcile plan-11 with ADR-0004 before any of it writes**, because merges should land in
   whichever alias structure survives.

{#rec-body}

## Decisions for the user {#decisions}

- **d-1. Merge target: DECIDED (user, 2026-10-07): ADR-0004's term-space alias map** (plan-11 superseded). Was: `same_as` rows, or the alias map. The second
  means reconciling plan-11 first.
- **d-2. Cull scope:** start with the model-free classes (orphan aliases, empty learned rows), or
  also run the df ≤ 1 ablation now?
- **d-3. Gold labels:** may I hand-label ~200 cluster pairs, with you reviewing a sample? Or should
  the curator agent label them?
- **d-4. Where it lives:** an evaluation task under plan-11 (helix), or its own plan (it reads
  helix signals but does not need phase 2 to start)?

## Transition Summary {#transition-summary}

**Status:** IN PROGRESS. User decision, 2026-10-07: **free culls + evaluation now; reconcile
plan-11 / ADR-0004 later, before any merge writes.**

- **Free culls:** the 9,182 orphan aliases and 747 empty protected `query/*` rows go through task
  16.6's prune (dry run + ablation).
- **Evaluation:** the read-only merge-signal evaluation (Option A) is **plan-20**.
- **Not decided yet:** d-1 (merge target) waits on the reconciliation; d-3 (gold labels) is settled
  in plan-20's spec.
