---
gmd: "0.1"
id: task-13.2-canonical-dedupe
title: "Task 13.2: collapse the same answer to one slot, keep the provenance"
tags: [task, plan-13, dedupe, fusion]
metadata:
  node_type: task
  status: pending
  plan: plan-13-cross-partition-sweep
---

# Task 13.2: canonical-identity dedupe {#root}

> Plan: [[plan-13-cross-partition-sweep]]
> Status: Pending
> Depends on: [[task-13.1-sweep-verb]]

rel: part-of -> [[plan-13-cross-partition-sweep]]
rel: depends-on -> [[task-13.1-sweep-verb]]

## Requirements {#requirements}

- The harm is **slot-crowding, not rank inflation.** `query.py:45-49` sums per `entities.id`, and
  ids are store-global with `UNIQUE(partition_id, kind, name)`, so one decision written as a
  session card, a memory and an ADR is three DIFFERENT ids that TIE — they do not compound (audit
  #s-1 corrected the first draft's claim). What they do is spend three of twenty slots on one
  answer.
- Collapse candidates to a canonical identity BEFORE fusion; keep the best-ranked instance; record
  the collapsed ones as provenance on the surviving row (`also_in: [{partition, id, rank}]`).
- Canonical identity is by NAME first (the key `merge_scope` already uses), with a documented
  fallback: rows whose names differ but whose `source_path` resolves to the same file are the same
  answer. **Neither key collapses this task's own motivating example** (r2 #s-7): a decision written
  as `session-a1b2` in one partition, `project_foo` in another and an ADR heading in a third shares
  neither name nor path. So the requirement is stated honestly — name + path dedupe handles MIRRORS
  (the same document reachable twice), and the session/memory/ADR restatement case is **explicitly
  out of scope**, because collapsing it needs content similarity and a threshold nobody has
  measured. A test that "passes" on a mirror fixture while the motivating case goes unhandled is the
  failure this note exists to prevent. Anything beyond that (near-duplicate text) is OUT of scope and stated as such — a
  similarity threshold here would be an unmeasured calibration.
- `verbs.merge_scope` (`verbs.py:375-399`) is the shipped ancestor: it dedupes a two-source union by
  name with a round-robin that guarantees the smaller source representation. Reuse its rule; do not
  write a second one ([[bsd-impressions#imp-two-paths]]).

## Acceptance criteria {#acceptance}

- A query whose answer exists in all three partitions returns ONE row with two `also_in` entries,
  not three rows.
- The surviving row is the best-ranked instance, and its rank is the best of the three — collapsing
  never demotes an answer.
- Round-robin representation holds: a partition contributing few candidates still appears in the
  top-k rather than being crowded out by a larger partition's run.
- Provenance is never dropped silently: the count of collapsed candidates appears in the result.

## Files {#files}

- modify `src/refmatrix/verbs.py` (dedupe step inside `sweep`)
- create `tests/test_sweep_dedupe.py`

## Test strategy (RED first) {#test-strategy}

1. `test_one_document_reachable_from_two_legs_takes_one_slot` — a MIRROR (same name, two
   partitions): two ids, one row, one `also_in`. Named for what the key can actually do.
1b. `test_a_restatement_across_partitions_is_NOT_collapsed` — the session/memory/ADR case stays
   three rows, and the test asserts that deliberately so the scope boundary is executable rather
   than a sentence.
2. `test_the_surviving_row_carries_the_best_rank` — the collapse keeps rank 2 when instances sit at
   ranks 2, 7, 15.
3. `test_a_small_partition_still_reaches_the_top_k` — round-robin, modelled on `merge_scope`'s own
   guarantee; a 3-candidate partition is represented against a 200-candidate one.
4. `test_same_source_path_different_name_collapses` — the documented fallback.
5. `test_different_answers_with_similar_names_do_not_collapse` — the guard against an over-eager
   key (the `_endpoint` over-permissiveness of plan-8 r2 is the precedent).
6. `test_collapsed_count_is_reported` — [[feedback_no_silent_failures]].

**Mutations:** collapse by id instead of name (kills 1); keep the worst rank (kills 2); drop the
round-robin (kills 3).
