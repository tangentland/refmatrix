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

1. **AC-1: the writer, in organised dirs only (r2 s2).**
   - In a memdir that has `.memory-layout` (26.1 `is_organised`): `rmx save-state` (CLI) and
     `rmx_save_state` (MCP) write `<memdir>/savestates/savestate_<slug>.md`, creating the folder
     if needed.
   - In a dir WITHOUT the marker, both write the top-level file exactly as at HEAD. Test both
     branches.
   - Going forward, `_ss_render` writes `updated:` as a full ISO datetime with time of day
     (`2026-11-09T14:03:22`; r2 s3). `created:` stays a frozen date.
   - The returned `target` names the path actually written. At HEAD the file is written at the top level, so this is RED.
2. **AC-2: the frozen `created:` survives a move (organised dirs only).**
   - Case: `savestate_<slug>.md` exists at the top level (legacy), and the same session saves
     again.
   - `_ss_frozen_created` reads the legacy file's `created:`.
   - The legacy file is MOVED into `savestates/` with `os.replace`, keeping its mtime, before the
     write. It is never left behind as a duplicate, because 26.2's duplicate-id refusal would then
     fire.
3. **AC-3: the reader, with legacy fallback.**
   - `_latest_savestate` takes the first item of `memory_layout.iter_savestates(memdir)`. That
     iterator applies ONE ordering (26.1 AC-1: `updated`, then mtime; same date with either side
     date-only → mtime) across `savestates/` and the legacy top level.
   - A dir that has only legacy files still resumes. That is every other project today.
   - The ordering is `updated` (datetime when present), then mtime. `created` is not a key
     (r2 s3).
   - Cases to test:
     - only new files;
     - only legacy files;
     - mixed, with the newest file legacy;
     - mixed, with the newest file new;
     - a legacy file whose mtime is NEWER but whose `updated:` is OLDER. The newer `updated:`
       must win. This is ch-bsd r1 #s2's cliquedb shape.
     - **same day, two sessions (r2 s3):**
       - session A: created 11-07, re-saved 11-08 at 23:00;
       - session B: created and saved 11-08 at 15:00.

       A must win, both with date-only `updated:` (decided by mtime) and with datetime
       `updated:`. Mutation: putting `created` before mtime turns this case RED.
     - **mixed formats, same date (r3 m2):** one save-state has `updated: 2026-11-08` (written by
       an old MCP server) and a later mtime; the other has `updated: 2026-11-08T15:00:00` and an
       earlier mtime. The later mtime must win. Mutation: treating a date-only value as midnight
       turns this case RED.
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
   - In an un-organised dir, `_ss_update_index` and the index write behave as at HEAD (26.1 AC-9).
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

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s2 (save-state rewrites fleet dirs before plan-27) | `savestates/` writing and the legacy move happen only in organised dirs; HEAD behaviour otherwise; readers dual | AC-1, AC-2, AC-5 |
| s3 ("newest" picks the session started last) | `_ss_render` writes `updated` with time of day; ordering is `updated` then mtime; same-day-two-sessions case plus mutation | AC-1, AC-3 |

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| m1 (stale "`updated`, then `created`" text) | Fixed to `updated`, then mtime | AC-3 |
| m2 (mixed date-only/datetime on the same date) | Mixed case added, decided by mtime; midnight mutation | AC-3 |

## Inherited from ch-bsd 26.1 r4 (2026-11-10) {#inherit-261-r4}

rel: derives-from -> [[bsd-task-26.1-r4-followup-705dbae#m-1]]

26.3 is the first task that moves memory files, so it owns this edge. **R:** when an index link's
path no longer exists, `memory_index.load_hooks` resolves the memory's derived hook by id through
one `{id: path}` map built from `memory_layout.iter_memory_files(memdir)`, so a cut of derived
prose on a moved file is never frozen into the sidecar. **AC:** the r4 probe shape (organised dir,
no sidecar, index line at `feedback_a.md`, file at `feedback/feedback_a.md`, a cut `prefix…` hook)
writes no `…`-ended sidecar value and renders the derived hook; mutation "no id fallback" is
killed. 26.5 inherits the fix (it moves files too). {#inherit-moved-derived}

## RED-round decisions (orchestrator, 2026-11-10) {#red-decisions}

Taken as the user would (correct first), answering the RED author's ambiguities at `4349154`:

1. **Ordering stays the 26.1 key.** `_SaveKey` = (updated DATE, mtime, name, path); the
   time of day that AC-1 writes into `updated:` is informational and never orders saves. ADR-0005
   `#newest` stands. {#rd-key}
2. **One "newest" in every dir.** The `MEMORY.md` save-state pointer and the reader both use
   `memory_layout.sort_savestates`, organised or not. Where HEAD's pointer ordering (created,
   mtime) disagrees with it (the cliquedb mixed-format shape), the flat-dir pointer changes: an
   accepted, named exception to 26.1 AC-9's byte-identity, because two answers to "newest" is the
   defect. Test: a flat cliquedb-shaped dir, pointer == reader. {#rd-one-newest}
3. **The r4 id fallback is ungated.** It applies only when an index link's path is gone, which a
   flat dir reaches only by hand; behaviour there is the same fix. {#rd-fallback-ungated}
4. **A crash mid-move (both a top-level and a `savestates/` copy of one id):** the reader takes
   the `savestates/` copy; the next save of that id writes `savestates/` and removes the top-level
   copy, printing `removed duplicate top-level <name>`; the bridge counts and names the duplicate
   in its skip line until then. Test both. {#rd-duplicate}
5. **AC-7's `install-hooks --check` clean** is verified by GREEN (the hook config carries no
   command docs, so it cannot fail RED). {#rd-ac7}

**#rd-duplicate vs 26.2 AC-4 (orchestrator, 2026-11-10).** 26.2 AC-4 refuses BOTH files of a
duplicate id and keeps the stored row. The one pair this task produces on purpose — a
`savestate_*` id with one copy at the memdir top level and one under `savestates/` — is the
exception: the `savestates/` copy is ingested, the top-level copy is skipped, counted and named.
Every other duplicate id follows 26.2 AC-4. Whichever of 26.2 / 26.3 merges second carries the
combined test. {#rd-duplicate-vs-262}

## Remedy after ch-bsd 26.3 r1 (2026-11-10) {#remedy-r1}

rel: derives-from -> [[bsd-task-26.3-r1-savestate-subfolder]]
rel: supersedes -> [[#rd-duplicate]]

**s-1: a pair keeps the NEWER copy, not the folder copy.** `#rd-duplicate` assumed a crash
mid-move, which the writer's replace-first order cannot produce. A real pair forms only when
another writer (an MCP server not yet respawned after the deploy, or a flat dir that still has
`savestates/`) puts a fresh top-level copy beside an older folder copy. Rule, in the one walk
(`memory_layout`): of the two copies of one save-state id, keep the one that sorts newest under
ADR-0005's key (`sort_savestates`); on a full tie keep `savestates/`. The other copy is skipped,
counted and named; the next save in an organised dir writes `savestates/` with the kept copy's
`created:` and removes the top-level copy, printing which one it removed. **ACs:** (a) fresh
top-level + stale folder copy → reader, pointer and recall-state use the top-level copy;
(b) fresh folder + stale top-level → the folder copy; (c) a full tie → the folder copy; each in
an organised and a flat dir. **Mutation:** always prefer `savestates/` — killed by (a).
{#rm-newer-copy}

**m-2:** `updated:` carries an ISO timestamp for save-states; `~/.claude/MEMORY-RULES.md`
`#frontmatter` is amended to say so (orchestrator, 2026-11-10). {#rm-updated-rule}
