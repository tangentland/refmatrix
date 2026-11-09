---
gmd: "0.1"
id: task-26.7-memory-index-by-subject
title: "Task 26.7: MEMORY.md grouped by derived subject, within the same character budget"
tags: [task, plan-26, memory-index, subjects, budget]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.7: MEMORY.md grouped by subject {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.1-layout-module-and-index-walk]], [[task-26.6-compile-subject-hygiene]]

rel: part-of -> [[plan-26-memory-organisation]]
rel: depends-on -> [[task-26.6-compile-subject-hygiene]]

## Requirements {#requirements}

Today `memory_index.render` groups by kind (feedback, reference, project, then the pointer
lines). A subject-grouped index needs good, non-stale subjects first. That is why this task
depends on 26.6.

1. **AC-1: where the subjects come from.** `memory_index.write(memdir, subjects=...)` takes a
   `{memory_id: subject_label}` map. The caller supplies it. `_ss_update_index` gets it through
   the existing read path: a daemon `memory_subjects` read op, or the snapshot when there is no
   daemon. Retired subjects are excluded. `memory_index` itself never opens a store, so it stays
   runnable as `python3 -m refmatrix.memory_index` with no store. With no map it renders exactly
   today's kind-grouped index (no regression).
2. **AC-2: the shape (plan Q6).**
   - One `## <label> (N)` header line per subject, ordered by size.
   - Inside a group: feedback, then reference, then project.
   - Each memory appears once, under its compiled subject, or under its largest hand subject when
     it has no compiled one.
   - An `## unfiled (N)` group comes last.
   - The impressions and save-state pointer lines stay at the end.
3. **AC-3: the budgets still hold.** The rendered text fits `MAX_INDEX_CHARS`, with header
   lines counted. The fold still takes the oldest project notes first and never feedback. The fold
   line names the count. The existing char-budget tests pass, plus a grouped fixture with 300
   entries.
4. **AC-4: idempotent on its own output.** `render` of the written file plus the same map is a
   no-op (`--check` reads in sync). Header lines are not parsed as hooks.
5. **AC-5: the end-to-end path.** `rmx save-state` over a throwaway store that holds compiled
   subjects writes a grouped `MEMORY.md`. Without a daemon or store it writes the kind-grouped
   form and prints one stderr line saying why.

## Files to Create / Modify {#files}

- Modify `src/refmatrix/memory_index.py`.
- Modify `src/refmatrix/handoff.py` (`_ss_update_index` passes the map).
- Modify `src/refmatrix/daemon.py` (the `memory_subjects` read op, if `subject_leaves` per subject
  is too chatty) and `verbs.py` (if the op is agent-facing).
- Extend `tests/test_memory_index.py` and `tests/test_save_state.py`.

## Test Strategy {#test-strategy}

Use a real throwaway store with compiled subjects (26.6's fixture corpus), the real save-state
CLI, and a real memdir. The map provider is exercised through the daemon op, not stubbed.
Mutation check: ignore the map and AC-5 goes RED.
