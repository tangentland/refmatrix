---
gmd: "0.1"
id: plan-11-helix-phase2-versioned-graph
title: "Helix phase 2, Option B — a versioned edge store so the graph has a past tense"
tags: [plan, helix, storage, versioning]
metadata:
  node_type: plan
  status: drafting
  created: 2026-09-16
---

# Proposed Plan: helix phase 2 on a versioned (prolly) edge store {#root}

**Date:** 2026-09-16
**Status:** Drafting. Q1-Q4 TENTATIVELY APPROVED 2026-09-16. Held at `drafting` deliberately:
the user gated forward movement on the 62.9 s profiling result, which may change the shape of this
plan or its priority. Task specs are NOT written yet.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[project_helix_phase2_storage_fork]]
rel: derives-from -> [[project_stm_ltm_helix_design]]
rel: depends-on -> [[project_helix_phase1_shipped]]
rel: related-to -> [[project_slot_rotation_drift]]
rel: related-to -> [[project_replica_merge_shipped]]

## The decision, and the evidence it did NOT rest on {#decision}

User chose **Option B** (2026-09-16): a content-addressed, history-independent versioned store
(prolly / Merkle search tree) rather than mutable `last_seen` / `touch_count` columns.

**State this carefully, because a later reader will check.** `project_helix_phase1_shipped` records
the fork signal as "empty across real sessions → Option A". That signal is VOID:
[[project_helix_log_confounded]] established the emptiness was an artifact of a self-suppressing
hook path, not evidence of absent demand. So B is not chosen *against* data — the experiment that
was meant to decide this never produced a usable result, and B is chosen on grounds it never
addressed:

1. Only B delivers the claim the word *helix* makes — "what did this concept's neighbourhood look
   like in June". A carries one overwritable timestamp and loses every earlier value.
2. B's primitive is "diff two versions of a database", which is exactly
   [[project_slot_rotation_drift]] (A/B counts diverge, no principled reconciliation) and
   [[project_replica_merge_shipped]]'s hand-rolled id-remap union.

## What this costs, stated up front {#cost}

[[project_helix_phase2_storage_fork]] is explicit and the plan does not soften it:

> No mature Python implementation exists (Dolt's is Go, Noms archived), **so Option B means
> writing one.**

This plan is therefore "implement a prolly tree", not "adopt a library". That is the dominant risk
and the reason task 11.1 is a property-tested primitive with no callers.

## NON-GOAL: the retrieval path does not change {#non-goal}

The fork doc's `#not-retrieval` section governs. The hot path stays roaring-bitmap set algebra +
BM25 over the relational table. A Merkle map is WORSE for the doclen `SUM ... GROUP BY`, and
0.38.0 already measured that `content_rank`'s cost was never storage — 260 ms → 21 ms came from
caching three re-derived constants, with the postings scan at 4.9 ms throughout.

**Nothing in this plan may touch `context`, `recall`, `scan-prompt`, or `content_rank`.** A test
asserts the retrieval modules are unimported by the versioned-store path.

This also means the 62.9 s `context` latency is NOT addressed here. That is profiling work, ordered
before benchmarks and tracked separately.

## Open Questions {#open-questions}

### Q1: What is versioned — edges only, or entities too? {#q1}
**TENTATIVELY APPROVED 2026-09-16: `entity_links` only.**
[[project_stm_ltm_helix_design]] names the gap precisely: "`entity_links` has `weight` but no
timestamp". Entities have stable integer ids and their own lifecycle; edges carry the associative
dimension that decays. Versioning entities too doubles the surface for no stated need.

### Q2: Commit cadence? {#q2}
**TENTATIVELY APPROVED 2026-09-16: one version per SNAPSHOT TICK**, reusing `_request_snapshot` / `_snapshot_catalog`.
A version per write would mean a commit per link — the GMD ingest alone emits ~608k. The snapshot
tick is already the system's checkpoint boundary and already fires on the write paths that matter.

### Q3: Does this plan cut over slot-drift and replica-merge? {#q3}
**TENTATIVELY APPROVED 2026-09-16: NO — build the primitive and its read surface; adoption is a follow-up plan.**
Coupling a brand-new datastructure's first landing to two live recovery paths is how a correctness
bug becomes a data-loss bug. Those two are the JUSTIFICATION for B, not its first customer.

### Q4: Does phase 3 (typed decay in ranking) land here? {#q4}
**TENTATIVELY APPROVED 2026-09-16: NO — separate.** Phase 3 needs only a recency scalar, which it can read once
edge-time exists. Bundling it would put a ranking change inside a storage plan and make a
regression unattributable.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Fork | A or B | **B**, on the two grounds above; the phase-1 signal is void, not overruled. | 2026-09-16 |
| Q1 | Versioned surface | `entity_links` only. TENTATIVE. | 2026-09-16 |
| Q2 | Commit cadence | One version per snapshot tick (`_request_snapshot`). TENTATIVE. | 2026-09-16 |
| Q3 | Drift/merge cutover | NOT in this plan; adoption is a follow-up. TENTATIVE. | 2026-09-16 |
| Q4 | Phase 3 scope | Separate plan; needs only a recency scalar. TENTATIVE. | 2026-09-16 |

## GATE: profiling first {#gate}

The user gated this plan on the 62.9 s `context` profiling (2026-09-16): **"I want the profiling
done before moving forward."** Task specs are not written and no code starts until that result
lands. The profile could plausibly reshape this plan — if the 62.9 s turns out to be dominated by
something the versioned store touches, the ordering changes.

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 11.1 | The prolly tree primitive — property-tested, NO callers | — |
| 11.2 | Edge-version store: commit at the snapshot tick, read a version | 11.1 |
| 11.3 | `helix` reads the versioned store instead of the STM rings | 11.2 |
| 11.4 | Read surface: `rmx graph at <when>` / diff two versions | 11.2 |

## Execution contract {#execution}

TDD per [[tdd-governance]]. Plan-specific gates:

- **History independence is THE invariant** and gets property-based tests, not examples: the same
  content must yield the same tree regardless of insertion order. A prolly tree that fails this is
  not a prolly tree, and every downstream claim (O(changes) diff, structural sharing) is void with
  it.
- **11.1 ships with zero callers.** The primitive is proven in isolation before anything depends on
  it; that is the only way a correctness bug stays a bug instead of becoming corruption.
- **No retrieval module may be imported** by this path — asserted by test, per [[#non-goal]].
- **Migration is additive and reversible.** The existing `entity_links` table is not dropped,
  altered, or read differently by anything else. If the versioned store is wrong, deleting it is
  the rollback.
