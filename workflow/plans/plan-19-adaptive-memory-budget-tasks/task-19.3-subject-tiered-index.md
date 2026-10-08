---
gmd: "0.1"
id: task-19.3-subject-tiered-index
title: "Task 19.3: MEMORY.md is grouped by compiled subject and folded by value, and every memory stays reachable"
tags: [task, memory, memory-index, subjects, budget]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 19.3: subject-tiered, value-ranked MEMORY.md {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending
> Depends on: 19.2 (scores), 19.4 (subjects kept current)

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[task-19.2-memory-usage-record]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]

## Why {#why}

`memory_index.render` (`memory_index.py:239`) lists entries in a fixed type order, alphabetically
within each type, and folds the oldest projects **by file mtime** (`:275`) to stay under
`MAX_INDEX_CHARS=24000` (`:63`). Today it holds 22,812 chars and 137 lines, with 86 projects folded
into one line. mtime moves on edit, not on use. Feedback never folds, so an all-feedback index would
end in `STILL OVER` (`:349`). The 39 compiled subjects (`mtype=subject`, `part-of` edges) are
unused by the index. {#why-body}

## Requirements {#requirements}

1. **R1 A subject block.** For each compiled subject: one line
   `- **<subject>** (<n> memories): <top hooks …> — rmx memory recall --subject <slug>`,
   followed by its top members inline (by 19.2's effective score) while the budget allows.
   Memories in no subject render in the existing type sections.
2. **R2 Value order.** Within each section the order is by effective score (recency with floor,
   plus lifetime), not alphabetical. Ties break by name, so the output is deterministic.
3. **R3 Fold by value.** When over budget, the lowest-scoring entries fold first into their
   subject line or the type's fold line.
   - Feedback and other asserted memories fold only after every non-asserted entry has folded,
     and only behind the asserted floor. They may fold; they may never disappear (the user's
     rule).
   - `STILL OVER` stays the loud last resort.
4. **R4 Reachability.** Every memory file on disk is reachable from the rendered index by one of:
   an inline line, a subject line with `--subject`, or a type fold line naming the recall command.
   A check lists any memory reachable by none, and the check FAILS on one.
5. **R5 Subjects source.** The subjects are read through the daemon (a read op over the replica),
   never by opening `Store()` on the live catalog. With no daemon, the fallback renders today's
   layout plus a one-line note. It never crashes save-state.
6. **R6 Hooks preserved.** Curated hooks (`.memory_hooks.json`, bug-050) are reused verbatim for
   any entry or folded member.

## Acceptance criteria {#acceptance}

1. On a copy of this project's memory dir plus a catalog copy carrying 39 subjects, the rendered
   index is ≤ `MAX_INDEX_CHARS`, and the number of memories **named** (inline or in a subject line)
   is ≥ 1.5x today's inline count (134).
2. R4's check passes, and deleting any one subject line makes it fail on exactly that subject's
   members.
3. With every feedback memory forced cold, feedback still renders inline until the non-asserted
   entries are exhausted.
4. Without a daemon, the render equals today's layout plus the note, and save-state succeeds.
5. Mutations that must FAIL a test:
   - mtime order restored;
   - the asserted floor removed;
   - the reachability check made vacuous (an empty memory set);
   - subjects read from a direct `Store()`.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/memory_index.py` | the subject block, value order, fold by score, the reachability check |
| `src/refmatrix/daemon.py` | a read op returning subjects + members + scores for a memory dir's partition |
| `src/refmatrix/handoff.py` (`_ss_update_index`) | pass scores/subjects through |

## Test strategy {#test-strategy}

- **RED:** AC-1 on fixtures fails today, because the index uses the mtime fold and no subjects.
- The reachability check runs over a fixture with 300 memories under a 24k budget.
- The char-budget assertion counts **characters** with a multibyte fixture (the bug-045 lesson).
