---
gmd: "0.1"
id: task-26.6-compile-subject-hygiene
title: "Task 26.6: compiled subjects retire when the corpus stops producing them, say when they are stale, and get graded labels"
tags: [task, plan-26, compile, subjects, labels, derive-stamp, decay]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.6: compile subject hygiene {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: none (runs in parallel with 26.1-26.5)

rel: part-of -> [[plan-26-memory-organisation]]
rel: derives-from -> [[refmatrix/adr-0002-subject-memory-container]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_reuse_shared_stoplist]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: related-to -> [[task-12.4-derive-version-stamp]]
rel: related-to -> [[plan-22-audited-removal-and-repair]]

## Requirements {#requirements}

The junk live labels (`from`, `existing`, `feedback`, `unlabeled_N`) are NOT a regression of the
0.34.0 stoplist fix. They were compiled on 2026-07-31, before that fix, and nothing re-compiled
or retired them ([[plan-26-memory-organisation#measured]]). Three defects remain: no retirement,
no staleness signal, and case-split labels.

1. **AC-1: retire, do not accrete.** In a throwaway store, `rmx memory compile --apply` twice.
   The second run is over a corpus that no longer produces subject `S`. After it, `S` carries
   `metadata.retired_at` and `retired_by: memory-compile`, has zero leaves, and is still present
   as a row. `rmx memory list --type subject` hides it, and `--include-retired` shows it. At HEAD
   `S` stays listed with no mark (RED).
2. **AC-2: un-retire on return.** A third compile that produces `S` again clears `retired_at`.
   The subject keeps its entity id.
3. **AC-3: hand subjects are untouched.** A subject with no `compiled_by` (save-state's STM
   filing, `subject_explore_thiquet…`) is never retired. This extends the existing
   `test_hand_declared_subjects_are_never_pruned`.
4. **AC-4: staleness is visible.** `compile --apply` calls `stamp_derive("memory-compile")` in
   the memory partition. `derive_status` reads the stamp as stale when its version differs from
   the running one, or when compiled subjects exist with NO stamp (the 2026-07-31 case).
   `rmx daemon status` prints the one-line stale hint (`memory-compile: <v> (running <v>) —
   stale; rmx memory compile --apply`), and nothing when the stamp is current.
5. **AC-5: case-folded labels and evidence.** Concept names that differ only by case
   (`Guardrail`/`guardrail`, `Tandem`/`tandem`) are one candidate. The label takes the most
   frequent surface form. The evidence lists each term once.
6. **AC-6: the stoplist stays shared.** `_label_candidate_ok` keeps reading
   `scan._PROMPT_STOPWORDS`. A test asserts that the labels `from`, `existing` and `feedback`
   cannot be produced by any fixture cluster. This pins the 0.34.0 fix.
7. **AC-7: pre-registered label grade (no build unless the band says so).** Before any further
   label change, freeze the label and evidence list of a fresh `rmx memory compile` preview on the
   live store. Labels are derived terms, not raw text. Keep it in
   `workflow/review-output/26.6-labels.md`, uncommitted if the user says so. The user grades each
   label: `names a body of work` / `weak but findable` / `junk`. Bands, written now:

### Pre-registered bands {#bands}

| junk share of graded labels | action |
|---|---|
| ≤ 10% | ship AC-1..AC-6 only; labels are good enough; record the grade |
| 10–25% | add a two-term label (`top_bareword` + strongest identifier-shaped co-term at ≥ 0.5× its lift) for bare-word winners only; re-grade |
| 25–40% | as above, plus raise `--min-size` default to 3 and re-measure unclustered count |
| > 40% | stop; labels are a design problem (ADR-0002 open question), not a tweak — new task |

## Files to Create / Modify {#files}

- Modify `src/refmatrix/consolidate.py` (`apply_plan` retire/unretire, label casefold).
- Modify `src/refmatrix/store.py` (`list_subjects(include_retired=)`).
- Modify `src/refmatrix/cli.py` (`memory list --include-retired`, compile stamp, the status
  line).
- Modify `src/refmatrix/daemon.py` if the compile op owns the stamp.
- Extend `tests/test_memory_compile.py`.
- Extend `tests/test_derive_stamp.py`.

## Test Strategy {#test-strategy}

Run the real `rmx memory compile --apply` against a throwaway daemon store with a synthetic
memory corpus whose embeddings are deterministic. Use the existing compile test fixtures. Do not
mock `apply_plan`. Mutation checks: skip the retire stamp and AC-1 goes RED. Skip the stamp call
and AC-4 goes RED (the wiring test runs the real compile, not `stamp_derive` directly).
