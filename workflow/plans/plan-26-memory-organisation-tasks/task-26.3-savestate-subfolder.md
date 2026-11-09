---
gmd: "0.1"
id: task-26.3-savestate-subfolder
title: "Task 26.3: save-state writes savestates/<id>.md; recall-state, recents and the index read it, with a legacy top-level fallback"
tags: [task, plan-26, save-state, recall-state, handoff, memory-dir]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.3: save-states live in savestates/ {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.1-layout-module-and-index-walk]]

rel: part-of -> [[plan-26-memory-organisation]]
rel: realizes -> [[feedback_save_state_means_handoff]]
rel: reinforces -> [[feedback_recall_state_means_resume]]

## Requirements {#requirements}

1. **AC-1: the writer.** `rmx save-state` (CLI) and `rmx_save_state` (MCP) write
   `<memdir>/savestates/savestate_<slug>.md` and create the folder. The returned `target` names
   that path. At HEAD the file is written at the top level (RED).
2. **AC-2: the frozen `created:` survives a move.** If `savestate_<slug>.md` exists at the top
   level (legacy) and the same session saves again, `_ss_frozen_created` reads the legacy file's
   `created:`. The new file goes under `savestates/`. The legacy file is MOVED (`os.replace`) into
   place before the write, never left as a duplicate. 26.2's duplicate-id refusal would otherwise
   fire.
3. **AC-3: the reader with legacy fallback.** `_latest_savestate` reads
   `memory_layout.iter_savestates(memdir)`: `savestates/` plus top-level `savestate_*.md`. It
   picks the newest by mtime across both. A dir with only legacy files (every other project
   today) still resumes. Test it three ways: only-new, only-legacy, and mixed where the newest is
   legacy, then mixed where the newest is new. `rmx recall-state` and `rmx_recall_state` both
   return it (parity).
4. **AC-4: recents.** `_ss_recent_memories` uses `iter_memory_files`, excluding save-states and
   impressions. Save-states are recalled through AC-3, not listed as "recent memories". This is a
   stated change: at HEAD a top-level save-state shows up in recents.
5. **AC-5: the index link.** `_ss_update_index` writes `](savestates/<id>.md)`. Its needle also
   matches a legacy `](<id>.md)` line and replaces it. `memory_index`'s save-state pointer line
   links `savestates/<newest>.md`.
6. **AC-6: the GMD lint target.** `finalize_save_state` lints the file at its new path, and the
   bridge ingests it (memory recall for a phrase unique to the handoff finds it).
7. **AC-7: the command docs.** `templates/commands/recall-state.md` and
   `.claude/commands/recall-state.md` say "newest save-state (`savestates/`, legacy top-level)".
   `rmx install-hooks --check` stays clean.

## Files to Create / Modify {#files}

- Modify `src/refmatrix/handoff.py` (`compose_save_state`, `_ss_frozen_created` call site,
  `_latest_savestate`, `_ss_recent_memories`, `_ss_update_index`).
- Modify `src/refmatrix/memory_index.py` (the pointer line).
- Modify `src/refmatrix/templates/commands/recall-state.md` and
  `.claude/commands/recall-state.md`.
- Extend `tests/test_save_state.py`.
- Create `tests/test_savestate_subfolder.py`.

## Test Strategy {#test-strategy}

Run the real `rmx save-state` and `rmx recall-state` CLI plus the MCP verbs (through the verb
registry, as `test_verb_parity` does). Use `HOME` pointed at a short `mkdtemp()` root, so
`default_memory_dir` resolves inside it, and a throwaway daemon store. Nothing in `handoff` is
mocked. Mutation check: revert the reader glob and the only-new case of AC-3 goes RED.
