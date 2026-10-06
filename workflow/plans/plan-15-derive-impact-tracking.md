---
gmd: "0.1"
id: plan-15-derive-impact-tracking
title: "Richer derive tracking: per-pass code identity, a history, and what each derive actually produced"
tags: [plan, derive, versioning, observability, store]
metadata:
  node_type: plan
  status: completed
  created: 2026-10-06
---

# Plan 15: make a derive say what it changed {#root}

**Date:** 2026-10-06
**Status:** Completed 2026-10-06 — all four tasks shipped (15.1-15.3 at 0.75.0; 15.4 on
`task-15.4-stamp-coverage`).

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[project_store_decays_behind_green_health]]
rel: related-to -> [[refmatrix/adr-0003-canonical-partition-layout]]
rel: related-to -> [[feedback_causal_story_before_evidence]]

## Why {#why}

bug-039 gave the store a way to say WHICH CODE built its graph, and that was the right first move: a
derived graph decays while every health surface reads green, and this project's own store sat at a
1-bundle retrieval floor for ten days because nothing recorded the deriving version. The stamp
closed that. {#history}

It cannot answer the next question, which is the one that actually gets asked: **what did a change
do?** Three concrete gaps, each observed on this store on 2026-10-06: {#gaps}

1. **The code identity is too coarse to attribute.** `derive_code_hash()` is one hash over
   `ingest.py`, `ingest_gmd.py` and `store.py`, shared by every pass. Adding `Store.grep_evidence` —
   a READ method, +80 lines, zero effect on extraction — flipped this partition to
   `behind_code: True`. The detector was right by its own rule and wrong about the graph, and it
   cannot say which pass is implicated because every pass shares the hash.
2. **There is no history.** `stamp_derive` upserts on `(partition_id, pass_name)`, deliberately:
   *"the question is always which code derived what is in the store NOW, never a history."* That is
   a defensible answer to bug-039's question and it makes impact unanswerable — there is nothing to
   compare a derive against.
3. **Nothing records what a derive PRODUCED.** bug-039's impact figures (31 → 63 bundles,
   206 → 466 nodes, 11,425 → 28,157 tokens) were taken by hand with an ad-hoc harness that no longer
   runs. A re-derive today reports no effect at all, so "should I re-derive?" is answered by
   intuition and "did it help?" is not answered.

## Decisions {#decisions}

Both forks were put to the user on 2026-10-06 with their costs; both landed on the recommendation.
{#decisions-lead}

| Q | Decision | Why |
|---|----------|-----|
| Q1 | **Structural counts per pass**, recorded at derive time, diffable between any two derives | ~6 COUNT queries at the end of a pass that already walked the corpus — negligible against the derive, and it is exactly the number bug-039 needed. A retrieval-level probe was offered and declined for now: it needs a fixed probe set someone owns, and it belongs behind this. |
| Q2 | **Per-pass module set** for the code hash | Fixes the false positive by construction (`store.py` leaves every pass's set) and attributes staleness to a pass. A per-function AST hash was offered and declined: it needs a maintained entry-point registry, and its failure mode is a hash that silently covers too little — a gate that cannot fire, which is the shape this project keeps getting bitten by. |
| Q3 | `derive_stamps` KEEPS its current-state contract; history is a NEW table | Four readers depend on the NOW semantics (`derive_status`, `rmx fingerprint`, the hub alert, the daemon status line). Widening that table would put a migration in front of every one of them for a question none of them asks. |
| Q4 | History is capped per `(partition, pass)` | `global:queues` grew to 3,196 rows unbounded (bug-061). An append-only table with no retention is the same defect with a different name. |
| Q5 | The stored hash carries its SCHEME (`p1:<digest>`) | **Found while building 15.1, not planned.** A pre-15.1 stamp holds a UNION hash over three modules; a per-pass hash covers one. They are not comparable, and the first cut compared them anyway — reporting every legacy stamp as `behind_code`, which is the same false positive the task set out to remove. Tagging makes the namespaces explicit, so a legacy row reads UNKNOWN ("re-derive to know") and a future scheme change cannot mis-compare either. |

## Tasks {#tasks}

| # | Task | Spec |
|---|------|------|
| 15.1 | Per-pass code identity; staleness attributable to a pass | `plan-15-derive-impact-tracking-tasks/task-15.1-per-pass-code-identity.md` |
| 15.2 | `derive_history` + the counts each derive produced | `plan-15-derive-impact-tracking-tasks/task-15.2-derive-history-and-counts.md` |
| 15.3 | `rmx derive log` / `rmx derive diff`, and honest status lines | `plan-15-derive-impact-tracking-tasks/task-15.3-derive-surface.md` |
| 15.4 | Coverage: the passes that never stamp | `plan-15-derive-impact-tracking-tasks/task-15.4-stamp-coverage.md` |

rel: specifies -> [[task-15.1-per-pass-code-identity]]
rel: specifies -> [[task-15.2-derive-history-and-counts]]
rel: specifies -> [[task-15.3-derive-surface]]
rel: specifies -> [[task-15.4-stamp-coverage]]

## What this plan must not do {#non-goals}

- **No new alert.** `impression_bsd_gate_firing_rate` measured version inequality at roughly 1-in-34
  signal and this project shipped 34 bumps in ten days; the hub alert stays gated on `behind_code`,
  which this plan makes *more* precise rather than louder. A richer record is not a licence to warn
  more often.
- **No retrieval claim.** Counts describe the GRAPH. "Retrieval got better" needs a probe set and an
  eval, and `project_concept_path_negatives_0903` is the standing reminder that a plausible
  graph-shape improvement can move retrieval zero. The report may not translate counts into quality.
- **No change to what any pass extracts.** This plan measures derives; it does not retune them.
- **No history migration of the existing stamp.** The rows we have carry no counts and no per-pass
  hash, and back-filling either would be invention. A pre-existing stamp reads as
  `counts: unknown`, and the first real derive after this ships is the first comparable row.

## Pre-registered: how we know this worked {#acceptance}

Stated before building, so it cannot be adjusted to whatever ships: {#acceptance-lead}

1. On THIS store, after 15.1, `behind_code` is **False** for the `gmd` pass with no re-derive — the
   `grep_evidence` edit is correctly no longer implicating a pass that never reads `store.py` for
   extraction. (The version-level `stale` may remain True; that is the human signal and is allowed
   to differ.)

   **MET, and by a mechanism this plan did not anticipate — recorded rather than smoothed over.**
   The live `gmd` stamp reads `behind_code: False` with `code_unknown: True`, because its hash was
   written under the legacy UNION scheme and is therefore not comparable to a per-pass hash (Q5).
   So the criterion holds, and it holds because the stamp is classified unknown — NOT because a
   per-pass comparison succeeded. The first real per-pass comparison cannot happen until the next
   derive runs under 15.1 code. Had the scheme tag not been added, this criterion would have FAILED:
   the first implementation reported the legacy stamp as behind, which is what sent me looking.
2. A forced re-derive of one pass produces a `derive_history` row whose counts differ from the
   previous row by a number the diff surface prints, and the same re-derive run twice in a row
   produces a diff of **all zeros** — a derive that changes nothing must be visibly a no-op.

   **MET for graph content, and WRONG as written about the rest.** Running the real pass twice over
   an unchanged tree leaves every graph count identical and moves `bitmap_fragments` **0 -> 3**,
   because the first pass had not flushed fragments yet. "All zeros" was an assumption about the
   system, not a requirement of it. Hiding the fragment delta would have been a lie and calling it
   "the derive changed something" would bury the question people actually ask, so counts are split:
   GRAPH content decides the verdict, and a `materialized cache:` line reports the rest beside it.
   The split was found by measuring, not designed.
3. The counts cost is measured, not asserted: the task records wall time for the counts query set
   against the duration of the pass it follows.
