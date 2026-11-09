---
gmd: "0.1"
id: task-26.0-adr-memory-dir-layout
title: "Task 26.0: ADR-0005 — the curated memory dir is laid out by type and lifecycle; topic is a derived subject"
tags: [task, plan-26, adr, memory-dir, layout]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
---

# Task 26.0: ADR-0005 memory-dir layout {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: nothing. Author: `@ch-architect` (dispatched by `/ch-crucible`).

rel: part-of -> [[plan-26-memory-organisation]]
rel: depends-on -> [[refmatrix/adr-0002-subject-memory-container]]
rel: related-to -> [[refmatrix/adr-0003-canonical-partition-layout]]
rel: related-to -> [[task-19.4-keep-derived-layers-current]]

## Requirements {#requirements}

1. Write `docs/adr/0005-memory-dir-layout.md`. It must be GMD, have status Proposed, and lint
   clean. It states the following.
   - **The folder table.** Use the table in [[plan-26-memory-organisation#context]]: `feedback/`,
     `project/`, `reference/`, `user/`, `guardrail/`, `impressions/`, `savestates/`. Say why type
     folders are singular and lifecycle folders are plural.
   - **Identity.** A memory's store identity is its frontmatter `id`. Its folder is never part of
     that identity.
   - **Topics.** A topic is a subject: a `part-of` edge to an ADR-0002 subject. A memory can have
     many. A topic is never a folder. Compiled subjects carry a `compiled_scope`. Stale subjects
     are marked per 19.4 R5 and are never deleted.
   - **Folder authority.** Use the rule from plan Q3: the folder is authoritative for
     `savestates/`; for every other folder a mismatch is only reported.
   - **One walk.** `memory_layout.py` is the single place the table lives. Its
     `iter_memory_files` is the ONLY memory walk. The bridge, the index and handoff all use it.
     Dot-directories, dotfiles and `README.md` are never memories (ch-bsd r1 #s3).
   - **Memdir→store resolution (B2).** The store a memdir belongs to is resolved from its
     `~/.claude/projects/<slug>` (the unresolved path). It is never resolved from the cwd. A
     memdir with no matching store is file-only.
   - **Hooks are keyed by memory id, not by path (B4).** Hand-written `MEMORY.md` prose is carried
     across a regeneration. It is never dropped.
   - **Git-tracked memdirs (S1).** Moves are `git mv`, staged in the owning repo. The user commits.
   - **Asides and backups (S3).** Backups and moved-aside files live under
     `~/.refmatrix/backups/memory-organise/`, never inside a memdir.
   - **Legacy dirs.** Flat legacy dirs stay readable forever: the code falls back to them; there
     is never a hard cut.
   - **The layout marker (r2 s2).** `<memdir>/.memory-layout` records the layout version, the
     organise date and the backup path. Only `rmx memory organise --apply` writes it. Every NEW
     on-disk behaviour applies only where the marker is present:
     - `savestates/` writes;
     - the new index renderer and the id-keyed hooks sidecar;
     - index-on-bridge;
     - `source_path`-aware refresh writes.

     A dir without the marker keeps the pre-ADR behaviour. Readers are dual everywhere. Guards
     that only refuse a write apply everywhere.
   - **"Newest" save-state (r2 s3).** Ordered by frontmatter `updated` (a datetime when present),
     then by mtime. `created` is never a tie-breaker.
2. Add a `rel: catalogs` row to `docs/adr/0000-adr-overview.md` and a row to `docs/INDEX.md`.
3. Add edges `rel: depends-on -> ADR-0002` and `rel: related-to -> ADR-0003`. The ADR must not
   contradict either one.
4. **Proposed MEMORY-RULES text (ch-bsd r1 #m6).** The ADR has an appendix containing the exact
   paragraph to add to the user-global `~/.claude/MEMORY-RULES.md`: "write a new memory into its
   type folder; save-states are written by `rmx save-state`; never hand-write into
   `savestates/`". This task does NOT edit that file. The user applies or authorises the edit at
   26.8 (plan Q8).

## Files to Create / Modify {#files}

- Create `docs/adr/0005-memory-dir-layout.md`.
- Modify `docs/adr/0000-adr-overview.md` and `docs/INDEX.md`.

## Test Strategy {#test-strategy}

Documentation only. `./scripts/lint-gmd.sh` must report zero errors. `@ch-alignment` derives the
`memory_layout` pseudocode from the ADR before 26.1 goes RED.

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| Q7 verdict (ADR must also fix B2, B4, S1, S3) | Five statements added | [[#requirements]] item 1 |
| B3 / B1 | ADR states `compiled_scope` and the 19.4 stale mark | [[#requirements]] item 1 |
| M6 (MEMORY-RULES not updated) | Proposed paragraph in an appendix; the user applies it | [[#requirements]] item 4 |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s2 (the deploy reaches un-backed-up dirs) | The ADR states the marker and its gate | [[#requirements]] item 1 |
| s3 ("newest" key) | The ADR states `updated` then mtime | [[#requirements]] item 1 |
