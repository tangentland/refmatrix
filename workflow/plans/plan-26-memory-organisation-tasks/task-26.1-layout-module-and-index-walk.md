---
gmd: "0.1"
id: task-26.1-layout-module-and-index-walk
title: "Task 26.1: one memory-layout module that IS the bridge's walk, and an index generator that walks every folder without losing prose or hooks"
tags: [task, plan-26, memory-dir, memory-index, layout, hooks, bridge]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
---

# Task 26.1: memory_layout.py, one walk, a lossless index {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.0-adr-memory-dir-layout]]

rel: part-of -> [[plan-26-memory-organisation]]
rel: implements -> [[task-26.0-adr-memory-dir-layout]]
rel: amends -> [[task-19.3-subject-tiered-index]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]

## Requirements {#requirements}

The memory dir's layout lives in one module, and that module's walk is the only memory walk.
Regenerating `MEMORY.md` must never render from a partial view of the dir. It must never drop
hand-written prose or curated hooks either. ch-bsd r1 reproduced viascope's 157 lines turning
into 1. It also measured the non-entry lines that regeneration drops: viascope 62, cliquedb 29,
viascope2 12, cliquet 8.

1. **AC-1: the layout table and THE walk.** A new `src/refmatrix/memory_layout.py` exports:
   - `FOLDERS`, which maps each folder to its `metadata.type` (ADR-0005);
   - `folder_for_type(mtype)`;
   - `savestate_dir(memdir)`;
   - `iter_memory_files(memdir)`, which walks recursively and yields only `.md` files. It
     excludes `MEMORY.md`, `README.md`, every dotfile, and everything under a dot-directory;
   - `iter_savestates(memdir)`, which yields `savestates/*.md` plus legacy top-level
     `savestate_*.md`. They are ordered newest-first by ONE key: frontmatter `updated`, parsed as
     a datetime when it carries a time of day and as a date otherwise, then mtime. `created` is
     NOT part of the key (r2 s3: a session created earlier but saved later must win).
   - `is_organised(memdir)`, which reads `<memdir>/.memory-layout` ([[#marker-gate]]).
2. **AC-2: the bridge uses that walk (ch-bsd r1 #s3).**
   - `ingest_gmd.collect_gmd_files(targets, *, as_memory=False)` gains the keyword. With
     `as_memory=True` it expands each directory target with `iter_memory_files`.
   - All four memory call sites pass it (r2 m1): `cli.py:10478` (in-process), `daemon.py:3772`
     (the sync op), `daemon.py:3789` (the detached op behind the SessionStart hook) and
     `daemon.py:3898` (prestage).
   - The test below runs three ways: in-process, through the daemon sync op, and through the
     detached op. Test: put a `.organise-rollback-1/x.md` and a `.hidden/y.md` inside a
   throwaway memdir, then run `rmx ingest-gmd --as-memory <dir>`. The store must have no `x` row
   and no `y` row. At HEAD both are ingested, so this is RED. Doc ingest (without `as_memory`)
   keeps its own walk.
3. **AC-3: the index sees type folders.** `memory_index.collect` uses `iter_memory_files`. Test
   on a throwaway dir laid out like viascope: `feedback/` with 3 files, `project/` with 3,
   `impressions/` with 1, and 1 file at the top level. `memory_index.collect(dir)` returns 8
   entries; at HEAD it returns 2 (RED). Assert on `collect()`, not on rendered lines, because
   `render` collapses impressions into one pointer line (ch-bsd r1 #m1).
4. **AC-4: curated hooks are keyed by memory id (B4).**
   - `load_hooks` and `parse_hooks` map every curated hook to the frontmatter `id` of the file
     its link points at. Links that are already dead are kept under their path and reported.
   - `save_hooks` writes `.memory_hooks.json` keyed by id.
   - A legacy path-keyed sidecar is read and converted on first write.
   - Applies to EVERY dir: a dir with no sidecar takes its hooks from its index lines.
   - Test: an index-only dir (no sidecar) has a curated hook on `project_x.md`. Move the file to
     `project/project_x.md` and regenerate. The hook is still there verbatim. At HEAD it falls
     back to `_first_prose` (RED).
5. **AC-5: hand-written prose is carried, never dropped (B4).**
   - Every non-blank line of the existing `MEMORY.md` that is neither an entry line
     (`- [...](...)`) nor a generated pointer or fold line is "prose". Headers, session logs and
     "Active Campaign" blocks all count.
   - `render` carries all prose verbatim, in its original order, inside a block that starts
     `<!-- carried from the hand-written index; edit freely -->`. The block is placed before the
     generated entries, and its characters count against `MAX_INDEX_CHARS`.
   - If the carried prose alone leaves less than 25% of the budget for entries, `write` refuses
     (index untouched, reason printed, return 0). It names the prose line count so the user can
     move the prose into a memory.
   - Idempotence: re-rendering a carried block re-carries it once. It never duplicates.
   - Test: a fixture copied from viascope's index shape (17 headers plus a session log) keeps
     every prose line. At HEAD all of them are dropped (RED).
6. **AC-6: the shrink guard counts content (B4).** Before replacing the index, `write` compares
   the old index's CONTENT lines (entry lines plus prose lines) with the new render's (entries
   named, inline or folded, plus carried prose). It refuses when fewer than 50% would remain, or
   when ANY prose line would be lost. The file is left untouched, the reason is printed on the
   `out` stream, and it returns 0. Test the viascope-copy case: links-only counting passes it,
   content counting refuses it.
7. **AC-7: `Entry.kind` reads the folder first.** The stem is the fallback for flat dirs.
8. **AC-8: no regression.** `tests/test_memory_index.py` and
   `tests/test_memory_index_char_budget.py` pass unchanged. A flat dir with no prose renders
   byte-identically to HEAD.


### The layout-marker gate (r2 s2) {#marker-gate}

9. **AC-9: un-organised dirs keep HEAD's index behaviour.**
   - `memory_index.write` uses the new render only when `is_organised(memdir)`. That covers the
     id-keyed sidecar, the carried prose block, and later 26.7's 19.3 blocks.
   - In a dir without `.memory-layout`, it renders exactly as at HEAD, byte-identically on the
     flat fixture, and it writes no new sidecar.
   - The AC-6 content-shrink guard applies in EVERY dir. It only refuses a write, so it changes
     no file and closes the viascope wipe in un-organised dirs too.
   - Test: in the same fixture, run once without the marker and once with it. Without the marker,
     the output is HEAD bytes and no `.memory_hooks.json` is created. With the marker, prose is
     carried and the sidecar is keyed by id.

## Files to Create / Modify {#files}

- Create `src/refmatrix/memory_layout.py`.
- Modify `src/refmatrix/memory_index.py`: `collect`, `Entry.kind`, the hook keying, the carried
  block, the shrink guard.
- Modify `src/refmatrix/ingest_gmd.py`: `collect_gmd_files` uses `iter_memory_files` on the
  as-memory path.
- Modify `src/refmatrix/cli.py` (`:10478`) and `src/refmatrix/daemon.py` (`:3772`, `:3789`, `:3898`):
  pass `as_memory=True` (r2 m1).
- Create `tests/test_memory_layout.py`.
- Extend `tests/test_memory_index.py` and `tests/test_memory_bridge.py`.

## Key Decisions {#key-decisions}

- **Prose:** carrying it into the generated index is the lossless default. Prose that blows the
  budget makes the write refuse, never silently drop. Moving the prose into a memory is the
  user's call.
- **Hook keying:** id-keying is an amendment to 19.3 R6, which preserves hooks keyed by path. It
  is built here because 26.5 moves files before 26.7 lands.

## Test Strategy {#test-strategy}

- Real files in a `mkdtemp()` dir, the real `python3 -m refmatrix.memory_index` entry point, and
  the real `rmx ingest-gmd --as-memory` against a throwaway store in task 23.0's sandbox.
- Nothing mocked.
- Mutation checks, each of which must turn a test RED:

| mutation | test that goes RED |
|---|---|
| revert `collect` to the old glob | AC-3 |
| the bridge walking with `rglob` | AC-2 |
| key hooks by path | AC-4 |
| drop the carried block | AC-5 |
| count links only | AC-6 |

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| S3 (the bridge walk is not the layout module; it walks dot-dirs) | `iter_memory_files` IS the bridge's memory walk | AC-1, AC-2 |
| S2 (two definitions of "newest") | `iter_savestates` defines it once | AC-1 |
| B4 (prose and hooks dropped; guard counts links) | Id-keyed hooks for every dir, carried prose, content-line guard | AC-4, AC-5, AC-6 |
| M1 (AC-2 count) | Assert on `collect()`: 8 vs 2 | AC-3 |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s3 ("newest" key regresses on same-day saves) | `updated` (datetime when present), then mtime; `created` dropped | AC-1 |
| s2 (new on-disk behaviour reaches un-organised dirs) | Marker gate; the HEAD render is kept for un-organised dirs; guards that only refuse apply everywhere | [[#marker-gate]] |
| m1 (four call sites; one pinned) | Keyword on `collect_gmd_files`; four sites named; AC-2 runs three ways; `daemon.py`/`cli.py` added to Files | AC-2, [[#files]] |
