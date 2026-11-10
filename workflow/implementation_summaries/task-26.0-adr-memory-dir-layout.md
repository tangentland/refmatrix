---
gmd: "0.1"
id: impl-task-26.0-adr-memory-dir-layout
title: "Task 26.0: ADR-0005 authored — memory dir by type and lifecycle; topic is a derived subject"
tags: [implementation-summary, plan-26, adr, adr-0005, memory-dir, layout]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-09
---

# Task 26.0: ADR-0005 memory-dir layout {#root}

rel: implements -> [[task-26.0-adr-memory-dir-layout]]
rel: part-of -> [[plan-26-memory-organisation]]
rel: related-to -> [[refmatrix/adr-0005-memory-dir-layout]]

## What shipped {#shipped}

| file | change |
|---|---|
| `docs/adr/0005-memory-dir-layout.md` | NEW. ADR-0005, status Proposed, GMD, lint 0 errors |
| `docs/adr/0000-adr-overview.md` | `rel: catalogs` edge + index row for ADR-0005; Last Updated bumped |
| `docs/INDEX.md` | `rel: catalogs` edge + ADRs-table row for ADR-0005 |
| `workflow/plans/plan-26-memory-organisation-tasks/task-26.0-adr-memory-dir-layout.md` | status → complete |

Documentation only; no `src/` or test change. Authored by `@ch-architect` (ADR-layer owner).

## How each requirement is met {#requirements-met}

| spec requirement | ADR anchor |
|---|---|
| R1 folder table; singular type / plural lifecycle | `#folders`, `#naming` |
| R1 identity = frontmatter `id`, never the folder | `#identity` |
| R1 topics = `part-of` subjects, many per memory, never folders; `compiled_scope`; 19.4 R5 stale mark, never deleted | `#topics` |
| R1 folder authority (Q3): `savestates/` authoritative, others report-only | `#authority` |
| R1 one walk: `memory_layout.iter_memory_files`, used by bridge/index/handoff; dot-dirs, dotfiles, `README.md` excluded | `#one-walk` |
| R1 B2 memdir→store from the unresolved projects slug, never cwd; no match = file-only | `#store-resolution` |
| R1 B4 hooks keyed by id; prose carried | `#hooks` |
| R1 S1 git-tracked: `git mv`, staged, user commits | `#git-tracked` |
| R1 S3 asides/backups under `~/.refmatrix/backups/memory-organise/` | `#asides` |
| R1 legacy flat dirs readable forever | `#legacy` |
| R1 layout marker, its four gated behaviours, un-organised = pre-ADR exactly, dual readers, compile index gated, r2 clause withdrawn | `#marker` |
| R1 "newest" = `updated`, then mtime; date-only tie → mtime; never `created` | `#newest` |
| R2 overview `rel: catalogs` row + `docs/INDEX.md` row | both files |
| R3 `depends-on` ADR-0002, `related-to` ADR-0003, no contradiction | header edges; `#topics` wording note; `#store-resolution` partition note |
| R4 MEMORY-RULES proposed paragraph, file not edited | `#appendix-memory-rules` |

## Decisions recorded in the ADR that the spec left implicit {#decisions}

- **Layout version value `1`.** The spec requires the marker to record "the layout version"; the
  ADR names this layout version 1 and says a folder-table change needs an amending ADR.
- **Marker serialisation** is left to 26.1/26.5 (recorded as an ADR open question).
- **Hooks/prose scope.** Spec R1 says prose is "never dropped"; the same spec's marker clause
  keeps the old prose-dropping compaction in un-organised dirs. The ADR states the B4 guarantees
  as part of the layout-1 renderer (marker-gated) and states the trade, per
  [[plan-26-memory-organisation#layout-marker]].
- **"Topic" wording vs ADR-0002.** ADR-0002 reserves "topic" for emergent `focus topics`; ADR-0005
  says its "topic" is the user's "what is this about", realised as an ADR-0002 subject, and
  redefines no ADR-0002 term.
- **MEMORY-RULES placement**: a new `## Where a memory file goes {#placement}` section after
  `#frontmatter`. The appendix also records that the bug-183 lint hook's `*/memory/*.md` case
  pattern already matches nested files, so `#validation` needs no change.

## Verification {#verification}

- `python3 tools/gmd/lint.py docs/adr/0005-memory-dir-layout.md`: 0 errors (warnings are
  cross-doc targets outside the single-file scan).
- Repo-scope lint with the curated memdir present (the dev-tree `scripts/lint-gmd.sh` scope):
  43 errors at HEAD, 43 after, identical set modulo line shifts.
- Clone-scope `./scripts/lint-gmd.sh` (no memdir for the littlebig slug): 986 → 989; the 3 are the
  ADR's memory-id edges (`feedback_decay_never_loses_knowledge` ×2,
  `feedback_converge_repeated_shapes`), the same dangling-doc class as the 986 at HEAD, which the
  script documents as the honest answer on a machine without the memories.

## Follow-ups {#follow-ups}

- `@ch-alignment` derives the `memory_layout` pseudocode from ADR-0005 before 26.1 goes RED.
- Pre-existing ARCH-DRIFT, not touched here: ADR ids carry a `refmatrix/` prefix, so every bare
  `[[adr-000N-...]]` link in the overview, `docs/INDEX.md` and `ARCHITECTURE_INDEX.md` dangles;
  `ARCHITECTURE_INDEX.md` also lists only ADR-0000..0002.
