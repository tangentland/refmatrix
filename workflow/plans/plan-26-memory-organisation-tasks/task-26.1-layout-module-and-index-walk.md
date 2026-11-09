---
gmd: "0.1"
id: task-26.1-layout-module-and-index-walk
title: "Task 26.1: one memory-layout module, and an index generator that walks every folder"
tags: [task, plan-26, memory-dir, memory-index, layout]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.1: memory_layout.py + the index walks every folder {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.0-adr-memory-dir-layout]]

rel: part-of -> [[plan-26-memory-organisation]]
rel: implements -> [[task-26.0-adr-memory-dir-layout]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]

## Requirements {#requirements}

The memory dir's layout lives in one module. `MEMORY.md` generation must never render from a
partial view of the dir. Today viascope's first save-state would overwrite its 33 KB index with
one entry, as described in [[plan-26-memory-organisation#measured]].

1. **AC-1: the layout table.** New `src/refmatrix/memory_layout.py` exports `FOLDERS`, a
   folder → `metadata.type` map with the seven folders of ADR-0005. It also exports
   `folder_for_type(mtype)` (or None), `savestate_dir(memdir)`, and
   `iter_memory_files(memdir)`. The last walks the top level plus every subfolder, recursively.
   It excludes `MEMORY.md`, `README.md`, dotfiles and dot-directories. It yields only `.md`.
2. **AC-2: the index sees type folders.** `memory_index.collect` uses `iter_memory_files`. On a
   throwaway dir laid out like viascope (`feedback/` 3, `project/` 3, `impressions/` 1, 1
   top-level), `python3 -m refmatrix.memory_index <dir>` lists all 8. At HEAD it lists 2, so the
   test is RED.
3. **AC-3: a partial view refuses to shrink the index.** `memory_index.write` refuses to render
   when the new entry count is below 50% of the links in the existing `MEMORY.md`. It leaves the
   file untouched, prints why on the `out` stream, and returns 0. An index losing half its
   entries in one write is the incident shape, not curation. The refusal is said, never mute.
4. **AC-4: `Entry.kind` reads the folder first.** A file under `feedback/` is `feedback` even if
   its stem lacks the prefix. The stem is the fallback for flat dirs.
5. **AC-5: no regression for flat dirs.** The existing `tests/test_memory_index.py` and
   `tests/test_memory_index_char_budget.py` pass unchanged.

## Files to Create / Modify {#files}

- Create `src/refmatrix/memory_layout.py`.
- Modify `src/refmatrix/memory_index.py` (`collect`, `Entry.kind`, the `write` shrink guard).
- Create `tests/test_memory_layout.py`.
- Extend `tests/test_memory_index.py`.

## Key Decisions {#key-decisions}

- The 50% shrink threshold is a guard against a wrong view, not a cap. A deliberate mass removal
  goes through `rmx memory organise` or a hand edit (plan Q2).

## Test Strategy {#test-strategy}

Use real files in a `mkdtemp()` dir and the real `python3 -m refmatrix.memory_index` entry
point. Nothing is mocked. Mutation check: revert `collect` to the old glob and AC-2 goes RED.
Remove the shrink guard and AC-3 goes RED.
