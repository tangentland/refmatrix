---
gmd: "0.1"
id: task-26.3-savestate-subfolder
title: "Task 26.3: save-state writes savestates/<id>.md; recall-state, recents and the index read it, with a legacy top-level fallback"
tags: [task, plan-26, save-state, recall-state, handoff, memory-dir]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
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
   `<memdir>/savestates/savestate_<slug>.md`, creating the folder if needed. The returned
   `target` names that path. At HEAD the file is written at the top level, so this is RED.
2. **AC-2: the frozen `created:` survives a move.**
   - Case: `savestate_<slug>.md` exists at the top level (legacy), and the same session saves
     again.
   - `_ss_frozen_created` reads the legacy file's `created:`.
   - The legacy file is MOVED into `savestates/` with `os.replace`, keeping its mtime, before the
     write. It is never left behind as a duplicate, because 26.2's duplicate-id refusal would then
     fire.
3. **AC-3: the reader, with legacy fallback.**
   - `_latest_savestate` takes the first item of `memory_layout.iter_savestates(memdir)`. That
     iterator applies ONE ordering (26.1 AC-1: `updated`, then `created`, then mtime) across
     `savestates/` and the legacy top level.
   - A dir that has only legacy files still resumes. That is every other project today.
   - Cases to test:
     - only new files;
     - only legacy files;
     - mixed, with the newest file legacy;
     - mixed, with the newest file new;
     - a legacy file whose mtime is NEWER but whose `updated:` is OLDER. The newer `updated:`
       must win. This is ch-bsd r1 #s2's cliquedb shape.
   - `rmx recall-state` and `rmx_recall_state` both return the same result (parity).
4. **AC-4: recents.**
   - `_ss_recent_memories` uses `iter_memory_files`, excluding save-states and impressions.
   - Save-states are recalled through AC-3 and are not listed as "recent memories".
   - Stated change: at HEAD, a top-level save-state shows up in recents, and recents globs only
     top-level `*.md` (`handoff.py:104`).
5. **AC-5: the index link.**
   - `_ss_update_index` writes `](savestates/<id>.md)`.
   - Its needle also matches a legacy `](<id>.md)` line and replaces it.
   - The pointer line in `memory_index` links the newest save-state by the AC-3 ordering, so there
     is ONE definition of "newest".
6. **AC-6: the GMD lint target.** `finalize_save_state` lints the file at its new path. The bridge
   ingests it: a memory recall for a phrase unique to the handoff finds it.
7. **AC-7: the command docs.**
   - `templates/commands/recall-state.md` and `.claude/commands/recall-state.md` describe the
     source as "newest save-state (`savestates/`, legacy top-level)".
   - `rmx install-hooks --check` stays clean.

## Files to Create / Modify {#files}

| file | change |
|---|---|
| `src/refmatrix/handoff.py` | `compose_save_state`, `_ss_frozen_created` call site, `_latest_savestate`, `_ss_recent_memories`, `_ss_update_index` |
| `src/refmatrix/memory_index.py` | the pointer line |
| `src/refmatrix/templates/commands/recall-state.md` | the AC-7 wording |
| `.claude/commands/recall-state.md` | the AC-7 wording |
| `tests/test_save_state.py` | extend |
| `tests/test_savestate_subfolder.py` | create |

## Test Strategy {#test-strategy}

- Use the real `rmx save-state` and `rmx recall-state` CLI, plus the MCP verbs through the verb
  registry.
- Run in task 23.0's sandbox: `HOME` under a short `mkdtemp()` root, and a throwaway daemon store.
- Nothing in `handoff` is mocked.
- Mutation checks:
  - Revert the reader's glob: the only-new case of AC-3 goes RED.
  - Order by mtime alone: the AC-3 cliquedb-shape case goes RED.

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| S2 (newest by mtime; two definitions) | Reader and pointer line use `iter_savestates`' one ordering; cliquedb-shape case | AC-3, AC-5 |
| M3 (recents glob) | States that `handoff.py:104` is top-level only | AC-4 |
