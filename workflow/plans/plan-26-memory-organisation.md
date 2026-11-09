---
gmd: "0.1"
id: plan-26-memory-organisation
title: "Plan 26: the curated memory dir is organised by type in folders; topic comes from derived subjects"
tags: [plan, memory, memory-dir, save-state, recall-state, bridge, compile, subjects, memory-index]
metadata:
  node_type: plan
  status: drafting
  created: 2026-11-08
---

# Plan 26: memory-layer organisation {#root}

**Date:** 2026-11-08
**Status:** Drafting
**Location:** `workflow/plans/plan-26-memory-organisation.md`. This file stays here; its stage is
`metadata.status`.
**Sequencing:** task 3.7, then plan-26 (this plan), then plan-25 (the cliquedb bugs), then plan-24
(the mod). Set by the user on 2026-11-08 (plan-of-plans `#override-2026-11-08b`).
**Successor:** [[plan-27-memory-fleet-rollout]] applies the deployed result to every other
project's memory dir.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[refmatrix/adr-0002-subject-memory-container]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]
rel: reinforces -> [[feedback_reuse_shared_stoplist]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: related-to -> [[plan-25-cliquedb-field-report]]
rel: motivates -> [[plan-27-memory-fleet-rollout]]
rel: specifies -> [[task-26.0-adr-memory-dir-layout]]
rel: specifies -> [[task-26.1-layout-module-and-index-walk]]
rel: specifies -> [[task-26.2-bridge-move-safety]]
rel: specifies -> [[task-26.3-savestate-subfolder]]
rel: specifies -> [[task-26.4-savestate-mtype-normalisation]]
rel: specifies -> [[task-26.5-memory-organise-verb]]
rel: specifies -> [[task-26.6-compile-subject-hygiene]]
rel: specifies -> [[task-26.7-memory-index-by-subject]]
rel: specifies -> [[task-26.8-refmatrix-live-rollout]]
rel: specifies -> [[task-26.9-impression-patterns]]

## Context {#context}

**User decisions (2026-11-08).** The memory dir is organised by TYPE (lifecycle) in folders,
never by topic. Topics come from derived subjects: `rmx memory compile`, the ADR-0002 subject
container and `part-of` edges. One memory can belong to several subjects, so subjects cannot be
folders. The first concrete ask is to move save-states into a `savestates/` subfolder.

**A precedent exists, and it settles the folder names.** viascope's memory dir
(`~/.claude/projects/-Users-tholley-github-atollogy-bdep-viascope/memory`, a symlink into
`~/at/bdep/viascope/.claude/projects/...`) already holds 146 memories in `feedback/` (65),
`project/` (68), `reference/` (9) and `impressions/` (3), with one file at the top level. This plan
adopts that layout as THE convention and adds one folder:

```text
memory/
├── MEMORY.md            # flat index, not GMD (MEMORY-RULES)
├── .memory_hooks.json   # curated-hook sidecar (memory_index)
├── feedback/            # metadata.type = feedback
├── project/             # metadata.type = project
├── reference/           # metadata.type = reference
├── user/                # metadata.type = user        (created on first use)
├── guardrail/           # metadata.type = guardrail   (created on first use)
├── impressions/         # metadata.type = impression  (already exists here, cliquedb, cliquet)
└── savestates/          # metadata.type = session/recall-state  (NEW)
```

Type folders use singular names because they name a `metadata.type` value (viascope's
precedent). Lifecycle collections use plural names because they are machine-written series
(`impressions/` already exists in three dirs). Nothing in this list is a topic.

### What was measured before drafting (2026-11-08) {#measured}

- **The refmatrix dir has 291 `.md` files at the top level:** 170 `project_`, 68 `feedback_`, 40
  `savestate_` and 12 `reference_`. `impressions/` holds 67. `MEMORY.md` is 128 lines and folds
  125 older project notes.
- **Store identity is the frontmatter `id`, not the path.** The bridge calls
  `store.add_memory(name=doc.doc_id, ...)` (`ingest_gmd.py:955`). The memory entity's `path` is
  NULL, and `source_path` is metadata that nothing in `src/` reads. The walk is recursive
  (`collect_gmd_files`, `rglob`). Moving a file therefore never changes which row it is.
- **No path in the code forgets a moved memory.** `Store.vacuum` purges dead `tracked_files`,
  but the bridge never calls `mark_tracked`. `sync.purge_path` comes from the watcher, and the
  watcher drops every hidden segment (`watch.is_relevant`, `.claude`). No daemon plist sets
  `--watch-root` on a memory dir (all 8 checked). The load-bearing risk is therefore not loss.
  It is stale state, described next.
- **A moved file whose content is unchanged keeps its OLD path in the store.** The resume hash
  gate is keyed by NAME (`_existing_hash_for(store, doc.doc_id, ...)`, `ingest_gmd.py:44,860`).
  When the hash matches, both passes are skipped. The per-anchor `kind=concept` entities
  (`savestate_x#session`, written with `path=str(path)` at `ingest_gmd.py:1033`) and the memory
  row's `source_path` keep pointing at a file that no longer exists. `rmx context` provenance
  and `--hit-lines` read `entities.path`, so they would then point at nothing. This is the
  defect task 26.2 fixes before anything moves.
- **The save-state paths are top-level only.** The writer is `handoff.py:371-373`
  (`memdir / f"savestate_{slug}.md"`). The reader is `handoff.py:491`
  (`memdir.glob("savestate_*.md")`). Both `_ss_recent_memories` (`handoff.py:104`) and
  `memory_index.collect` (`memory_index.py:232`) glob `*.md` plus `impressions/*.md`. The index
  link is `]({mem_id}.md)` (`handoff.py:228`). Moving the files without changing this code breaks
  the deployed `rmx recall-state`.
- **Latent index wipe in viascope.** `memory_index.collect` would see one file in viascope's
  dir, because its memories live in type folders that `collect` does not walk. The first
  `rmx save-state` there would run `_ss_update_index`, then `_mi.check` would fail and `_mi.write`
  would render a one-entry index over the 33 KB hand-built one. The guard `if not entries`
  (`memory_index.py:312`) does not fire, because one entry is not zero. Nothing has triggered this
  yet only because viascope has never run a save-state (0 savestates). Task 26.1 closes it.
- **Save-state types across the fleet:** 126 of 130 are `session/recall-state`. The other 4 are
  cliquedb files that an agent wrote by hand with `type: project` (`savestate_7c4e19d2a8f3`,
  `_5b83f0c71ae4`, `_06e3e57bf65a`, `_3f1c8a2b95de`). The bridge trusts the frontmatter
  (`ingest_gmd.py:943`), so hook-mode recall's `session/*` exclusion misses them, which adds to
  bug-164's payload.
- **The live compiled subjects predate the label fix and were never re-compiled.** Every
  `compiled_by: memory-compile` row carries `compiled_at` 1785547502, which is 2026-07-31. The
  stoplist and `_LABEL_GENERIC` fix shipped in 0.34.0 on 2026-08-25 (`f96fda8`). So this is not a
  regression. 20 of the 40 live subject rows are names the current code can no longer produce:
  15 `unlabeled_N`, plus `from`, `existing`, `feedback`, `fixes` and `memory`. `apply_plan` only
  UNLINKS a prior compile's leaves (`consolidate.py:633-645`). It never retires a subject the new
  plan does not produce, so these rows sit there with zero leaves forever. Subjects are
  `protected=True` (`store.py:2718`).
- **A preview compile today (`rmx memory compile`, read-only)** gives 63 subjects over 341
  embedded memories, with 22 unclustered. Most labels are real handles (`save_state`,
  `index_corruption`, `daemon_ops`, `csn_typescript`, `RMXGREP_MODE`). Some are weak English
  words (`separate`, `quiet`, `errors`, `allowed`, `gate`, `plan`, `store`, `dev`). Case variants
  split one term (`Guardrail`/`guardrail`, `Tandem`). Ten singleton-concept clusters fall back to
  member-derived names (`daemon_signal_hang`).

## Proposed Approach {#approach}

### One convention, one module {#one-module}

Every place that knows where a memory file lives reads one table. A new module,
`src/refmatrix/memory_layout.py`, holds the folder-to-type table, `savestate_dir(memdir)`,
`iter_memory_files(memdir)` and `iter_savestates(memdir)`. The last one yields `savestates/`
first, then legacy top-level `savestate_*.md`. Today four sites hand-roll globs (`handoff.py`
×3, `memory_index.py`). They become callers of this module. This is the "two ways to do X"
collapse the review overlay asks for.

### Make moving safe before moving anything {#safe-first}

Task 26.2 changes the bridge so that a file whose PATH changed is re-ingested even when its
content hash matches. Store identity stays keyed by `id`, so the row, its links, its vector and
its decay record are untouched. Only the stale `path` and `source_path` are refreshed. The same
task makes two files that claim one `id` a counted, named refusal instead of a silent
last-writer-wins flip. A copy-then-delete migration would otherwise flap.

### The migration is a verb, never a hand-move {#verb}

Task 26.5 adds `rmx memory organise`: a verb, with a CLI command and an MCP tool, covered by the
parity test. It previews by default. `--apply` writes a backup tarball first, then moves files
with `os.replace` on the same filesystem, rewrites the hook sidecar keys, regenerates `MEMORY.md`
and runs the bridge through the daemon. `--rollback <backup>` restores. `--check` reports drift
and changes nothing. Plan 27 runs this same verb on every other dir.

### Save-states first, then every type {#scope-order}

The user's first ask (save-states) ships first and alone in task 26.3. The verb in 26.5 handles
every type folder. Task 26.8 applies the full convention to the refmatrix dir, unless the user
answers Q1 the other way.

### Subjects: retire, do not delete; re-compile when the code changed {#subjects}

Task 26.6 makes `apply_plan` DEMOTE any compiled subject the new plan does not produce. It stamps
`retired_at`/`retired_by`, and listings and the index hide the row. It is not purged: decay may
demote, never lose (`feedback_decay_never_loses_knowledge`). Physical removal waits for plan-22's
audited path. A compile also stamps `derive_stamps('memory-compile')` (task 12.4's primitive), so
`rmx daemon status` shows a compile older than the running code, which is exactly how the
2026-07-31 rows went unnoticed. Label work beyond case-folding is gated on a pre-registered grade
(see [[task-26.6-compile-subject-hygiene#bands]]).

### What this plan will NOT do {#non-goals}

- No topic folders. Subjects never become directories.
- No physical deletion of any memory file or memory row. Subjects are demoted, not purged.
- No change to store identity. A memory's id stays its frontmatter `id`.
- No edits to other projects' memory dirs or stores. That is [[plan-27-memory-fleet-rollout]].
- No hook-payload budgeting. That is plan-25 bug-164. This plan only makes the save-state TYPE
  correct, which is a memory-layer fact (see Q4).

## Task list {#tasks}

| task | what | depends on |
|------|------|------------|
| [[task-26.0-adr-memory-dir-layout]] | ADR: type/lifecycle folders; topic via subjects | none |
| [[task-26.1-layout-module-and-index-walk]] | `memory_layout.py`; the index walks every folder (closes the viascope wipe) | 26.0 |
| [[task-26.2-bridge-move-safety]] | moved file is re-ingested; duplicate id refused and counted | 26.1 |
| [[task-26.3-savestate-subfolder]] | writer → `savestates/`; reader + recents + index with legacy fallback | 26.1 |
| [[task-26.4-savestate-mtype-normalisation]] | a save-state's type comes from its folder/prefix; mismatches said | 26.1, 26.2 |
| [[task-26.5-memory-organise-verb]] | `rmx memory organise` preview / apply / rollback / check | 26.2, 26.3, 26.4 |
| [[task-26.6-compile-subject-hygiene]] | retire stale compiled subjects; derive stamp; casefold; graded labels | none (parallel) |
| [[task-26.7-memory-index-by-subject]] | `MEMORY.md` grouped by subject | 26.1, 26.6 |
| [[task-26.8-refmatrix-live-rollout]] | deploy; back up; organise the refmatrix dir; re-compile; verify | all |
| [[task-26.9-impression-patterns]] | ch-bsd impressions: compile-derived pattern layer, curated rule text, IMPRESSIONS.md folded to a rolling window, ch-bsd step 0b reads patterns first (user, 2026-11-08) | 26.6, 26.1, 26.8 for live |

## Acceptance for the plan {#acceptance}

- Every task: RED recorded at HEAD on the production path (the real CLI or MCP verb over a
  throwaway memory dir and a throwaway store under a short `mkdtemp()` root, never the live store
  or live memory dir). GREEN recorded. One mutation per new guard. Implementation summary written.
- `rmx recall-state` after the live migration shows the newest save-state, now read from
  `savestates/`. `rmx memory recall "<phrase unique to a moved save-state>"` returns it.
- `rmx memory organise --check` on the live refmatrix dir reports zero drift.
- `rmx install-hooks --check` is clean, the verb parity test is green, and GMD lint shows zero
  errors.
- `@ch-bsd` over the plan's commit range is remedied to CLEAN.

## Open questions (phrased as decisions) {#open-questions}

- **Q1: apply the full type-folder convention to the refmatrix dir in this plan, or only
  `savestates/`?** Recommend the full convention. viascope proves it works. One convention across
  the fleet beats a half-moved dir. The verb is the same either way, and the move is
  identity-safe once 26.2 lands. If you choose save-states only, 26.8 passes
  `--only savestates`.
- **Q2: should `rmx save-state` file NEW top-level memories into their type folder?** Claude
  Code's auto-memory writes at the top level. Recommend yes, but only when `metadata.type` maps
  unambiguously to a folder. Anything else is reported by `organise --check` in the save-state
  output and never guessed.
- **Q3: is the folder authoritative for type?** Recommend that it is authoritative for
  `savestates/` only: the bridge stores `session/recall-state` and counts and prints the
  override. In every other folder a frontmatter/folder mismatch is reported, not overridden. A
  hand-written `project` note filed in `feedback/` is a filing error for a human to resolve.
- **Q4: which plan owns save-state mtype normalisation, 26 or 25 (bug-164)?** Recommend plan-26
  (task 26.4). The type of a save-state is a memory-layer fact. bug-164 keeps the payload budget.
- **Q5: what happens to stale subjects?** Recommend demoting them in place (`retired_at`) now and
  purging them through plan-22's audited path once it is built. This loses nothing, and
  `upsert_subject` un-retires a subject if a later compile produces it again.
- **Q6: how is `MEMORY.md` shaped by subject?** Recommend one header line per subject
  (`## <label> (N)`). Under each header: feedback first, then reference, then project. Each
  memory is listed once, under its compiled subject (a hand-declared subject only if it has no
  compiled one). An `unfiled` group comes last. The fold rule is unchanged (oldest project notes,
  never feedback).
- **Q7: should the folder convention ship as an ADR first?** Recommend yes. Task 26.0 is authored
  by `@ch-architect` before approval, because it is a cross-project on-disk contract that plan-27
  and every cat-herder project inherit.
