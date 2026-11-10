---
gmd: "0.1"
id: impl-task-26.3-savestate-subfolder
title: "Task 26.3: save-states live in savestates/ in organised dirs; one newest in every dir; the moved-file hook id fallback"
tags: [implementation-summary, plan-26, save-state, recall-state, handoff, memory-dir, memory-index]
metadata:
  node_type: implementation-summary
  status: in-progress
  created: 2026-11-10
---

# Task 26.3: save-states live in savestates/ {#root}

rel: implements -> [[task-26.3-savestate-subfolder]]
rel: part-of -> [[plan-26-memory-organisation]]
rel: implements -> [[refmatrix/adr-0005-memory-dir-layout#newest]]
rel: implements -> [[refmatrix/adr-0005-memory-dir-layout#legacy]]
rel: implements -> [[refmatrix/adr-0005-memory-dir-layout#marker-encoding]]
rel: implements -> [[task-26.3-savestate-subfolder#inherit-261-r4]]
rel: implements -> [[task-26.3-savestate-subfolder#red-decisions]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: related-to -> [[task-26.2-bridge-move-safety]]

TDD GREEN over the RED commits `4349154` (26 failing, 10 guards) and `474b569` (6 failing),
on branch `task-26.3-savestate-subfolder` in the clone `/Volumes/littlebig/refmatrix-plan26-3`.
No test was written or edited in this step. GREEN commits: `3733dab` (the change) and
`640e32d` (flat-dir index replace kept HEAD's, plus the mutation logs).

## What shipped {#shipped}

- `handoff.compose_save_state`: in an organised dir (`memory_layout.is_organised`) the target
  is `memory_layout.savestate_dir(memdir)/<id>.md`. A legacy top-level copy is MOVED in with
  `os.replace` (mtime kept) before the write, and `created:` is read from the authoritative
  copy (`savestates/` when present, else the legacy file). When both copies exist (a crash
  mid-move), the `savestates/` copy is written first and the top-level copy is unlinked after,
  returned as `removed_duplicate`. The CLI prints `removed duplicate top-level <name>` (and
  `moved legacy top-level <name> into savestates/`). A dir with no marker is written as at HEAD.
- `_ss_updated_stamp(today)`: `updated:` is `today` plus the wall clock's time of day and offset
  (`2026-11-10T11:42:07-08:00`). `created:` stays a frozen date.
- `_latest_savestate` is `memory_layout.iter_savestates(memdir)[0]`.
- `_ss_recent_memories` walks `iter_memory_files` and drops save-states
  (`memory_layout.is_savestate_path`) and the `impressions/` folder.
- `_ss_update_index`: organised dirs link `](savestates/<id>.md)`, and the needle also matches
  the legacy `](<id>.md)` line; all matches collapse into one entry. Flat dirs keep HEAD's
  link, needle and per-line replace.
- `memory_layout.iter_memory_files`: skips a top-level `savestate_<x>.md` when
  `savestates/savestate_<x>.md` exists (`is_shadowed_savestate`). The skipped copy goes on
  `skipped=`, so the bridge counts and names it. `is_savestate_path` is now the one save-state
  predicate, and `iter_savestates` uses it.
- `memory_index`: the save-state pointer uses `sort_savestates` in every dir
  (#rd-one-newest), so the unused `organised` flag on `_render_entries` is gone.
  `load_hooks` → `_link_identity(memdir, rel, moved)` handles an index link whose path no
  longer exists: it looks the id (stem) up in one `{id: [rel]}` map, built once per call from
  `iter_memory_files`. One hit means it reads that file's id and derived hook. Two hits are
  reported on stderr and get no derived hook.
- `ingest_gmd.render_memory_skip_line` adds the shadowed save-state to its list of skip reasons.
- `templates/commands/recall-state.md` and `.claude/commands/recall-state.md` (identical):
  "the newest save-state (`savestates/`, legacy top-level)".

## Per acceptance criterion {#per-ac}

| AC | where | test evidence |
|---|---|---|
| AC-1 | `handoff.compose_save_state`, `_ss_updated_stamp`, `_ss_render(updated=)` | `test_ac1_*` (compose / CLI / MCP x organised, unorganised; dry run; datetime `updated`) and `test_save_state.py::test_compose_save_state_writes_updated_with_time_of_day` pass |
| AC-2 | `compose_save_state` move branch + `created` source | `test_ac2_*` pass |
| AC-3 | `_latest_savestate` → `iter_savestates` | `test_ac3_*` (only new/legacy, mixed both ways, cliquedb x2, same-day x4, mixed formats, CLI==MCP) pass |
| AC-4 | `_ss_recent_memories` | `test_ac4_*` pass |
| AC-5 | `_ss_update_index`, `memory_index._render_entries` pointer | `test_ac5_*`, `test_rd_one_newest_*` pass |
| AC-6 | target path flows to `finalize_save_state`'s lint and the bridge | `test_ac6_*` passes with a real daemon and the real model |
| AC-7 | both `recall-state.md` copies | `test_ac7_*` pass; `install-hooks --check` [[#ac7-check]] |
| #inherit-261-r4 | `memory_index._link_identity` id fallback | `test_r4_*` pass |
| #rd-duplicate | walk shadow rule + post-write unlink | `test_rd_duplicate_*` (reader x2, next save, bridge) pass |

## Results {#results}

| log | result |
|---|---|
| `workflow/review-output/plan26/26.3-green.log` | RED files: 61 passed |
| `workflow/review-output/plan26/26.3-green-family.log` (at `3733dab`) | family: 617 passed |
| `workflow/review-output/plan26/26.3-green-adjacent.log` | 16 adjacent files (hooks, ingest, plan remedies, pointer, verbs): 309 passed |
| `workflow/review-output/plan26/26.3-green-post-mutation.log` | after restore: 202 passed |
| `workflow/review-output/plan26/26.3-green-r2-index.log` (after `640e32d`'s change) | 174 passed |
| `workflow/review-output/plan26/26.3-green-family-640e32d.log` | family at the final sha |

**AC-7 check {#ac7-check}.** I ran `install-hooks --check --scope project` with the dev
interpreter, `PYTHONPATH=<clone>/src`, and `REFMATRIX_ROOT=<clone>/.refmatrix`. That directory
does not exist and was not created, so no store was involved. The check exits 1, both at GREEN
and with `src` stashed back to HEAD, and the two outputs are byte-identical. The only drift is
the two entries the check itself flags as "generated for another checkout … differ by path
prefix": the clone's path is not the dev tree's. GREEN adds no drift. The notes are in
`26.3-green-install-hooks-check.log`.

## Mutations {#mutations}

Each mutation was applied by a script to the committed `3733dab`, with `__pycache__` cleared
first. Each was run over `tests/test_savestate_subfolder.py tests/test_save_state.py` and then
restored in its own command: `git checkout -- src`, clear `__pycache__`, grep the fix back,
confirm `git status --short src` is empty.

| id | mutation | killed by | log |
|---|---|---|---|
| G1 | writer ignores the marker (`organised = False`) | 9 failed (AC-1 organised x4, AC-2 x2, AC-5 top-level link, AC-6, rd next-save) | `26.3-green-mut-G1.log` |
| G2 | reader drops the `savestates/` glob (`sort_savestates(memdir.glob("savestate_*.md"))`) | 10 failed (AC-3 x7, AC-5 pointer==reader, rd reader x2) | `26.3-green-mut-G2.log` |
| G3 | pointer uses its own ordering (HEAD's `(created, mtime)`) | 3 failed (AC-5 pointer, rd one-newest x2) | `26.3-green-mut-G3.log` |
| G4 | id fallback removed | 2 failed (both `test_r4_*`) | `26.3-green-mut-G4.log` |
| G5 | duplicate top-level copy not removed | 1 failed (rd next-save) | `26.3-green-mut-G5.log` |
| G6 (extra) | walk keeps the shadowed top-level copy | 3 failed (rd reader x2, rd bridge) | `26.3-green-mut-G6.log` |

## Interpretations and flags for the review lenses {#flags}

1. **Where the mid-move rule lives {#flag-walk}.** I put the shadowed-copy skip in
   `iter_memory_files`, not in the bridge. That way the reader, the pointer, recents and both
   bridge paths (daemon and in-process) cannot disagree, and 26.2's duplicate-id refusal never
   sees the pair. That is #rd-duplicate-vs-262's exception, enforced in one place. Whichever
   of 26.2 and 26.3 merges second carries the combined test.
2. **`updated:` format {#flag-updated}.** The stamp is `today` plus the wall-clock time of day
   and offset. The spec's example has no offset. The test regex accepts both, and ADR-0005
   reads the date in its own offset, so ordering does not change.
3. **Gap: a flat dir that has a `savestates/` folder {#flag-flat-shadow}.** This can happen
   if a rollback moves the marker aside and leaves `savestates/<id>.md` in place. A save then
   writes the top level exactly as at HEAD (AC-1), and the walk treats that fresh file as
   shadowed by the stale `savestates/` copy, so recall-state would resume from the older copy.
   I did not build around this. The fix belongs with 26.5's rollback (move `savestates/` back
   to the top level) or with an AC that defines the writer's behaviour in this shape.
4. **Recents exclude impressions by folder.** A top-level file typed `impression` is still
   listed, as it was at HEAD. Flat dirs keep impressions in `impressions/`.
5. **Mutation G2's shape.** "Reader drops the savestates/ glob" is the reader going back to a
   top-level glob through the same `sort_savestates` key, so G2 isolates the folder and not
   the ordering.

No ADR or pseudocode discrepancy found: plan-26 has no `pseudocode/` node for 26.3. ADR-0005
#newest, #legacy and #marker are followed as written.
