---
gmd: "0.1"
id: plan-26-memory-organisation
title: "Plan 26: the curated memory dir is organised by type in folders; topic comes from derived subjects"
tags: [plan, memory, memory-dir, save-state, recall-state, bridge, compile, subjects, memory-index]
metadata:
  node_type: plan
  status: drafting
  created: 2026-11-08
  updated: 2026-11-09
---

# Plan 26: memory-layer organisation {#root}

**Date:** 2026-11-08. Revised 2026-11-09, rounds 1 ([[#rev-round-1]]) and 2 ([[#rev-round-2]]).
**Status:** Drafting.
**Location:** `workflow/plans/plan-26-memory-organisation.md`. This file stays here; its stage is
`metadata.status`.
**Sequencing:** task 3.7 → plan-26 (this plan) → plan-25 (the cliquedb bugs) → plan-24 (the mod).
Set by the user on 2026-11-08 (plan-of-plans `#override-2026-11-08b`).
**Successor:** [[plan-27-memory-fleet-rollout]] applies the deployed result to every other
project's memory dir.
**Builds approved work:** tasks 26.6 and 26.7 BUILD the approved plan-19 tasks 19.4 and 19.3.
They do not re-specify them ([[#plan-19]]).

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[refmatrix/adr-0002-subject-memory-container]]
rel: realizes -> [[task-19.3-subject-tiered-index]]
rel: realizes -> [[task-19.4-keep-derived-layers-current]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[task-22.1a-provenance-free-classes]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]
rel: reinforces -> [[feedback_reuse_shared_stoplist]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]
rel: derives-from -> [[bsd-plan26-27-spec-review-r1-96feccd]]
rel: derives-from -> [[bsd-plan26-27-spec-review-r2-8af766a]]
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

**User decisions (2026-11-08):**
- The memory dir is organised by TYPE (lifecycle) in folders, never by topic.
- Topics come from derived subjects: `rmx memory compile`, the ADR-0002 subject container, and
  `part-of` edges.
- A memory can belong to several subjects, so subjects cannot be folders.
- The first concrete ask is to move save-states into a `savestates/` subfolder.

**A precedent exists, and it settles the folder names.** viascope's memory dir
(`~/.claude/projects/-Users-tholley-github-atollogy-bdep-viascope/memory`) is a symlink into
`~/at/bdep/viascope/.claude/projects/...`, and git tracks it in the viascope repo: 147 files
([[#git-tracked]]). It already holds 146 memories:

| folder | memories |
|---|---|
| `feedback/` | 65 |
| `project/` | 68 |
| `reference/` | 9 |
| `impressions/` | 3 |
| top level | 1 |

This plan adopts that layout as THE convention and adds one folder:

```text
memory/
├── MEMORY.md            # flat index, not GMD (MEMORY-RULES)
├── .memory_hooks.json   # curated-hook sidecar, keyed by memory id after 26.1
├── feedback/            # metadata.type = feedback
├── project/             # metadata.type = project
├── reference/           # metadata.type = reference
├── user/                # metadata.type = user        (created on first use)
├── guardrail/           # metadata.type = guardrail   (created on first use)
├── impressions/         # metadata.type = impression  (already exists here, cliquedb, cliquet)
└── savestates/          # metadata.type = session/recall-state  (NEW)
```

Naming rules:
- Type folders use singular names, because each names one `metadata.type` value (viascope's
  precedent).
- Lifecycle collections use plural names, because they are machine-written series.
  `impressions/` already exists in three dirs.
- Nothing in this list is a topic.

### What was measured before drafting (2026-11-08) {#measured}

**The refmatrix memory dir.**
- 291 `.md` files sit at the top level: 170 `project_`, 68 `feedback_`, 40 `savestate_`, 12
  `reference_`. In other words, 40 save-states plus 250 typed files.
- `impressions/` holds 67.
- `MEMORY.md` is 128 lines and folds 125 older project notes.

**Store identity is the frontmatter `id`, not the file path.**
- The bridge calls `store.add_memory(name=doc.doc_id, ...)` at `ingest_gmd.py:956`.
- The memory entity's `path` is NULL.
- The walk is recursive: `collect_gmd_files` uses `rglob`, `ingest_gmd.py:1386`.
- So moving a file never changes which store row it is.

**No code path forgets a moved memory.**
- `Store.vacuum` purges dead `tracked_files` rows, but the bridge never calls `mark_tracked`.
- `sync.purge_path` comes from the watcher, and the watcher drops every hidden segment
  (`watch.is_relevant`, which excludes `.claude`).
- No daemon plist points a watch root at a memory dir (all 8 checked).
- So the load-bearing risk is stale state, described next, not loss.

**The bridge itself walks dot-dirs.** `collect_gmd_files` excludes only `MEMORY.md`. ch-bsd
probe r1 #s3: a `.organise-rollback-1/x.md` inside the memdir was ingested.

**A moved file whose content is unchanged keeps its OLD path in the store.**
- The resume hash gate is keyed by NAME: `_existing_hash_for(store, doc.doc_id, ...)`,
  `ingest_gmd.py:44,860`.
- When the hash matches, both passes are skipped.
- The per-anchor `kind=concept` entities keep the old path. They are written with
  `path=str(path)` at `ingest_gmd.py:1033`.
- The memory row's `source_path` also keeps the old path.
- ch-bsd r1 reproduced this on the production CLI.

**The save-state paths are top-level only.**

| site | location | what it does |
|---|---|---|
| writer | `handoff.py:371-373` | writes `memdir / f"savestate_{slug}.md"` |
| reader | `handoff.py:491` | `memdir.glob("savestate_*.md")`, newest by mtime |
| `_ss_recent_memories` | `handoff.py:104` | globs top-level `*.md` ONLY (not `impressions/`) |
| `memory_index.collect` | `memory_index.py:232` | globs `*.md` plus `impressions/*.md` |
| index link | `handoff.py:228` | writes `]({mem_id}.md)` |

- `memory_index` orders save-states by `created`, then mtime. That makes two definitions of
  "newest" ([[task-26.1-layout-module-and-index-walk]] makes it one).

**Latent index wipe in viascope (reproduced by ch-bsd r1).**
- On a copy of viascope's dir, `memory_index.write` turned 157 lines / 61 links into 1 line.
- Nothing has triggered this yet only because viascope has never run a save-state.

**Regeneration drops hand-written index prose.**
- `render` emits only entry lines and pointer lines.
- Non-entry lines that would be lost: viascope 62, cliquedb 29, viascope2 12, cliquet 8.
- Curated hooks are keyed by relative path, so a moved file loses its hook.
- Only refmatrix and the home dir have a `.memory_hooks.json` sidecar.

**Save-state types across the fleet.**
- 126 of 130 are `session/recall-state`.
- The other 4 are cliquedb files an agent wrote by hand with `type: project`.
- Their mtimes are Jun 30 and Jul 26. The real newest cliquedb save-state is Aug 4.

**The live compiled subjects predate the label fix and were never re-compiled.**
- Every `compiled_at` is 1785547502, which is 2026-07-31.
- The stoplist fix shipped in 0.34.0 on 2026-08-25 (`f96fda8`).
- 20 of the 40 live subject rows are names current code cannot produce: 15 `unlabeled_N`,
  plus `from`, `existing`, `feedback`, `fixes`, `memory`.
- `apply_plan` only UNLINKS leaves (`consolidate.py:630-645`).
- Plan-19 already owns the fix (19.4 R5/R6), so this plan builds it ([[#plan-19]]).

**A read-only preview compile today** gives 63 subjects over 341 embedded memories, with 22 left
unclustered.
- Most labels are real handles: `save_state`, `index_corruption`, `daemon_ops`.
- Some are weak words: `separate`, `quiet`, `errors`, `allowed`, `gate`.
- Some are case-split: `Guardrail`/`guardrail`.

### Git-tracked memory dirs (ch-bsd r1 #s1) {#git-tracked}

| memdir | tracked by | files |
|---|---|---|
| viascope (resolved under `~/at/bdep/viascope/.claude/projects/...`) | the viascope repo | 147, including `MEMORY.md` |
| refmatrix | `~/.claude` (a git repo) | 2: `MEMORY.md` and `project_csn_production_harness.md` |
| others | `~/.claude` | Besides the 2 refmatrix files, 93 files are tracked under the deleted `-Users-tholley-enduris-cliquedb` memdir. git shows them as unstaged deletions; all 93 names exist in the bdep-cliquedb memdir. That is pre-existing dirt, and the staged summary names it (26.5 AC-4). |

What tracked status means for this plan:
- A move inside a tracked dir is a `git mv`, staged in the owning repo.
- The user makes the commit. It is never a delete plus an untracked file.
- Rollback in a tracked dir is `git restore`/`git mv` back, not a tarball overwrite.

## Relationship to plan-19 (B1) {#plan-19}

Plan-19 is APPROVED. Its tasks 19.3 ("MEMORY.md grouped by compiled subject, folded by value")
and 19.4 ("scheduled compile, stable unlabeled names, stale subjects marked never reaped") are
unbuilt. None of their markers exist in `src/`: no `cluster_cid`, no `stale_since`, no
`.memory_scores.json`, no `MaintenanceStep`. Plan-26 BUILDS them; it does not restate them.
- [[task-26.6-compile-subject-hygiene]] realizes 19.4.
- [[task-26.7-memory-index-by-subject]] realizes 19.3.

The ONE stale mark is 19.4 R5's `metadata.stale` + `stale_since`. Plan-22's `stale-subject`
audit class ([[task-22.1a-provenance-free-classes#r1]]) keys on it, so stale rows stay visible to
the audit.

| plan-19 requirement | built by | what differs in plan-26 |
|---|---|---|
| 19.4 R1 scheduled compile | 26.6 builds the `memory_compile` op + verb (plan + apply, single-flight, `retries=0`) | Registering the step on 17.2's tick stays with plan-17/19. Task 17.2 is unbuilt, and plan-26 does not wait for it ([[task-26.6-compile-subject-hygiene#plan-19-delta]]). |
| 19.4 R2 index on bridge write | 26.6 | none |
| 19.4 R3 compile regenerates the index | 26.6 (after 26.7) | none |
| 19.4 R4 compile never loses | 26.6 | none |
| 19.4 R5 stale mark, never reaped | 26.6 | The `stale`/`stale_since` mark is used; round 0's `retired_at` is withdrawn. **19.4 AC-4's recall leg** ("absent from `rmx memory recall`, with and without `--include-subjects`") is NOT built here. It needs 19.1 R2, which is built by 25.1 R2/AC-6 after plan-26. 26.6 asserts the mark, `memory get`, the list mark and the index. The recall leg lands with 25.1 (r2 s1). |
| 19.4 R6 stable unlabeled names (`cluster_cid`) | 26.6 | none (built here or by 19.6, whichever merges first, per 19.4) |
| 19.4 R7 loud | 26.6 | none |
| (new) compile scope | 26.6 | Subjects carry `compiled_scope`, and prune/stale are scope-local. This is B3's fix, needed by 26.9. |
| (new) case-folded labels, pre-registered label grade | 26.6 | not in plan-19 |
| (new) code-hash staleness of the compile | 26.6 | not in plan-19 (S6) |
| 19.3 R1-R8 | 26.7 | Scores: until 19.2 lands, 26.7 runs on 19.3 R7's virtual scores (files only). 19.2 swaps in real scores without touching 26.7. |
| (new) id-keyed hooks, carried prose, content-line shrink guard | 26.1 | 19.3 R6 preserves hooks keyed by path. 26.1 re-keys them by id, so they survive moves (B4). |

**Note for plan-25 (r2 s1).** This is text only; plan-25 files are not edited here. 25.1's
delta must name 19.4 AC-4's recall leg (a stale subject is absent from recall, even with
`--include-subjects`) as its own acceptance. 26.6 deliberately leaves that leg to 25.1, because
recall excludes only `session/*` today (`verbs.py:983`) and `--include-subjects` does not exist
yet.

**What plan-19 must record when these land** (by plan-19's owner; plan-19 files are not edited
here):
- 19.3 status `realized by task-26.7`. Residual: the 19.2 score source.
- 19.4 status `realized by task-26.6`. Residual: 17.2 step registration (R1) and AC-2, plus AC-4's recall leg (lands with 25.1).
- The plan-of-plans row 19 note.

## Proposed Approach {#approach}

### One convention, one module, one walk {#one-module}

`src/refmatrix/memory_layout.py` holds:
- the folder-to-type table;
- `savestate_dir(memdir)`;
- `iter_memory_files(memdir)`;
- `iter_savestates(memdir)`, with ONE "newest" ordering: frontmatter `updated`, then `created`,
  then mtime.

The bridge's memory walk IS `iter_memory_files`. This was ch-bsd r1 #s3: round 0 left the bridge
on its own `rglob`. The other callers are `handoff.py` ×3 and `memory_index.py`. Dot-dirs, dotfiles
and `README.md` are never memories.

### Only organised dirs see new on-disk behaviour (r2 s2) {#layout-marker}

After 26.8 deploys, every project runs the new `rmx`, but plan-27 backs up the other memdirs
later. So every NEW on-disk behaviour is gated on a marker file, `<memdir>/.memory-layout`. Only
`rmx memory organise --apply` writes that file. It records the ADR-0005 layout version, the
organise date, and the backup tarball. The marker is a dotfile, so it is never a memory.

**Gated behaviours (organised dirs only):**
- save-state writes into `savestates/` and moves a legacy file into it (26.3);
- the new `MEMORY.md` renderer: 19.3 blocks, the carried-prose block, the id-keyed
  `.memory_hooks.json` (26.1, 26.7);
- index regeneration on every bridge write (19.4 R2, 26.6);
- the `source_path`-aware resume gate and its refresh writes (26.2).

**In a dir without the marker, all of these behave exactly as at HEAD.** Two kinds of change
still apply everywhere:
- **Readers stay dual.** `iter_savestates` and recall-state read legacy plus `savestates/`,
  which changes no file.
- **Guards that only REFUSE a write apply everywhere.** 26.1's content-shrink guard leaves the
  index untouched; that is strictly more conservative than HEAD, and it closes the viascope wipe
  in un-organised dirs too.

The 26.4 bridge mtype rule is a store-row correction, not a disk write. It applies everywhere,
because it is what keeps mis-typed save-states out of hook recall.

### Make moving safe before moving anything {#safe-first}

Task 26.2 makes the resume gate compare the stored resolved `source_path` (memories) or
`entities.path` (docs) as well as the hash. A path change re-ingests:
- the row, its links, its vector and its decay record keep their identity;
- only `path`/`source_path` are refreshed;
- no new key is stored (ch-bsd r1 #s5).

Two files claiming one `id` are a counted, named refusal.

### The migration is a verb, never a hand-move {#verb}

Task 26.5 adds `rmx memory organise`, as a verb, a CLI command and an MCP tool.
- **Target store.** Resolved from the memdir's projects slug (`_root_from_projects_slug`,
  `cli.py:113`, on the UNRESOLVED path). The verb refuses when the cwd's store disagrees (B2).
- **Default is preview.**
- **`--apply`:**
  1. backs up first;
  2. moves with `os.replace`, or `git mv` in a tracked dir and then stops for the user's commit;
  3. preserves mtimes;
  4. regenerates `MEMORY.md` without losing prose or hooks (26.1, B4);
  5. bridges into the resolved store through its daemon.
- **`--rollback`** is id-aware and never overwrites a post-backup edit.
- **`--check`** reports and never moves.

Plan 27 runs this same verb on every other dir.

### Save-states first, then every type {#scope-order}

Task 26.3 ships the save-state change. The 26.5 verb handles every type folder. Task 26.8 applies
the full convention to the refmatrix dir, per Q1 (sound for refmatrix per ch-bsd r1).

### Subjects: one compile path, scope-aware; stale is marked, never reaped {#subjects}

Task 26.6 builds 19.4.
- A compile only prunes and marks stale within its own `compiled_scope`, so the memory compile
  and 26.9's pattern compile cannot destroy each other (B3).
- Pattern subjects live in a `pattern_` slug namespace.
- The compile's staleness is a per-pass CODE HASH (`_DERIVE_PASS_MODULES`, `consolidate.py`), not
  the release version. It is kept out of the project partition's derive verdict (S6).

### Ordering against the unmerged task 3.7 (ch-bsd r1 #m9) {#overlap-37}

Task 3.7 lives in a clone at `d02739e`: 54 commits, `cli.py` ±1675, `verbs.py` +1290, still DIRTY
at its r3 at the time of review. It merges first. Re-read the overlap at 26.5's start.

| file | plan-26 tasks | 3.7 touches? | consequence |
|---|---|---|---|
| `src/refmatrix/verbs.py` | 26.5 (organise verb + parity map), 26.6 (`memory_compile` verb, `rmx_memory` stale listing) | yes (verb backlog) | rebase 26.5/26.6 on 3.7 |
| `src/refmatrix/cli.py` | 26.2 (`_bridge_stats`, `_bridge_wait_for_active_job`), 26.5, 26.6 | yes (not `_sync_memory_dir`/`_bridge_stats`/compile, per ch-bsd r1) | small conflict surface |
| `src/refmatrix/mcp.py` | 26.5 if not generated | possibly | rebase |
| `src/refmatrix/handoff.py`, `memory_index.py`, `ingest_gmd.py`, `consolidate.py`, `memory_layout.py` | 26.1-26.7 | no (per ch-bsd r1) | none |

Further ordering rules:
- 26.9's live step (AC-5) does NOT gate plan-26's close. Plan-25 follows plan-26, and its
  consumer bugs must not wait on a ch-bsd run.
- 25.1 reads the index 26.7 writes, so 26.7 (19.3) closes before 25.1 starts.

### What this plan will NOT do {#non-goals}

- No topic folders. Subjects never become directories.
- No deletion of any memory file, memory row or subject. Stale subjects are marked, and removal
  is only through plan-22's audited path.
- No change to store identity. A memory's id stays its frontmatter `id`.
- No commit in another repo. Tracked moves are staged, and the user commits.
- No change to other projects' memory dirs when 26.8 deploys. Every new on-disk behaviour is
  gated on the `.memory-layout` marker ([[#layout-marker]]), and un-organised dirs keep HEAD
  behaviour until plan-27 organises them. Two kinds of change still reach every dir: the dual
  readers and the refuse-only guards. The one store-side change that does reach other projects'
  stores is the 26.4 mtype correction. 26.8 also takes a read-only fleet snapshot (every
  memdir's `MEMORY.md` + sidecar) BEFORE the deploy.
- No hook-payload budgeting (plan-25 bug-164).
- No registration on 17.2's nightly tick (stays with plan-17/19).

## Task list {#tasks}

| task | what | depends on |
|------|------|------------|
| [[task-26.0-adr-memory-dir-layout]] | ADR-0005: type/lifecycle folders; topic via subjects; memdir→store resolution; id-keyed hooks; tracked dirs; the aside location. Proposed MEMORY-RULES text. | none |
| [[task-26.1-layout-module-and-index-walk]] | `memory_layout.py` (also the bridge's walk); index walks every folder; hooks keyed by id; prose carried; content-line shrink guard; one "newest" | 26.0 |
| [[task-26.2-bridge-move-safety]] | moved file refreshed via the existing `source_path`; duplicate id refused and counted | 26.1 |
| [[task-26.3-savestate-subfolder]] | writer → `savestates/`; reader, recents and index with legacy fallback | 26.1 |
| [[task-26.4-savestate-mtype-normalisation]] | a save-state's type comes from its folder/prefix; the rewrite preserves mtime and `updated:` | 26.1, 26.2 |
| [[task-26.5-memory-organise-verb]] | `rmx memory organise`: memdir-resolved store, backup, `git mv` in tracked dirs, id-aware rollback, check | 26.1-26.4 |
| [[task-26.6-compile-subject-hygiene]] | BUILDS 19.4, plus compile scope, casefold, label grade, code-hash staleness | 23.0 (done); 19.6's `cluster_cid` if it merges first |
| [[task-26.7-memory-index-by-subject]] | BUILDS 19.3 on virtual scores until 19.2 | 26.1, 26.6 |
| [[task-26.8-refmatrix-live-rollout]] | deploy; measure the one-time re-ingest; back up; organise; re-compile; verify | 26.0-26.7 |
| [[task-26.9-impression-patterns]] | ch-bsd pattern layer on the scoped compile; the R4 procedure goes in the overlay, independently reviewed | 26.6, 26.1 (26.8 for live; does not gate the plan close) |

## Acceptance for the plan {#acceptance}

- **Every task:** RED recorded at HEAD on the production path, using the real CLI or MCP verb in
  task 23.0's sandbox, over a throwaway memory dir and store under a short `mkdtemp()` root (never
  the live store or live memory dir). GREEN recorded. One mutation per new guard. Implementation
  summary written.
- **Save-states after the live migration:**
  - `rmx recall-state` shows the newest save-state, which is now read from `savestates/`;
  - `rmx memory recall "<phrase unique to a moved save-state>"` returns it.
- **Live refmatrix dir:** `rmx memory organise --check` reports zero drift. The two
  `~/.claude`-tracked moves are staged for the user's commit.
- **Repo gates:** `rmx install-hooks --check` is clean, the verb parity test is green, and GMD lint
  shows zero errors.
- **Review:** `@ch-bsd` over the plan's commit range is remedied to CLEAN. Plan-19's owner has
  recorded [[#plan-19]]'s status lines.

## Open questions (decisions) {#open-questions}

- **Q1: full type-folder convention for refmatrix?** Recommend yes (ch-bsd r1: sound for
  refmatrix). Fleet-wide only after B2/B4/S1 land, which they do in 26.1/26.5.
- **Q2: does `rmx save-state` move new strays?** Settled by ch-bsd r1: **report-only**. Moving
  files under a live session races its writes. Strays are filed by an explicit `organise --apply`.
- **Q3: is the folder authoritative for type?** For `savestates/` only (sound).
- **Q4: who owns save-state type normalisation?** Plan-26 (26.4). Plan-25 already defers to it.
- **Q5: what is the stale mark?** Settled: 19.4 R5's `metadata.stale` + `stale_since`, so
  plan-22's audit sees it.
- **Q6: what shape does the index take?** Settled: defer to 19.3 (live-subject blocks, fold by
  value, hooks preserved), built by 26.7. Round 0's "one header per subject" is withdrawn: 63
  headers would spend a third of the 200-line cap.
- **Q7: ADR first?** Yes (26.0), carrying B2/B4/S1/S3.
- **Q8: who applies the edit to the user-global `~/.claude/MEMORY-RULES.md`?** RECORDED
  (orchestrator, r2; ch-bsd r2 agrees): the user authorises it at 26.8, and 26.0 proposes the
  text. The edit is load-bearing. Until it lands, agents keep writing at the memdir top level,
  which keeps `organise --check` non-zero and can trip 26.2's duplicate-id refusal (26.8 AC-8).

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan26-27-spec-review-r1-96feccd]] (DIRTY 4B/10S/9M). Orchestrator decisions for B1,
B2, B3, B4, S1, and R4 (26.9) were relayed 2026-11-09.

| finding | change | anchor |
|---|---|---|
| B1 (26.6/26.7 re-specify 19.4/19.3) | Plan-26 builds 19.4 and 19.3; `realizes` edges; delta table; plan-19 record list; one `stale` mark | [[#plan-19]], [[#subjects]], [[#tasks]] |
| B2 (verb bridges into the cwd's store) | Store resolved from the memdir slug; mismatch refused | [[#verb]] |
| B3 (scoped compile destroys the other scope) | `compiled_scope`; scope-local prune/stale; `pattern_` namespace | [[#subjects]] |
| B4 (regeneration drops prose and hooks) | Id-keyed hooks, carried prose, content-line guard (26.1) | [[#measured]], [[#tasks]] |
| S1 (git-tracked memdirs) | Tracked dirs inventoried; `git mv`, user commits | [[#git-tracked]], [[#verb]], [[#non-goals]] |
| S2 (rewrite changes "newest") | One "newest" ordering; mtime preserved | [[#one-module]] |
| S3 (bridge walks dot-dirs) | The bridge's walk is `iter_memory_files` | [[#measured]], [[#one-module]] |
| S4 (rollback overwrites edits) | Id-aware rollback | [[#verb]] |
| S5 (second path record; hidden re-ingest) | Gate on the existing `source_path`; one-time cost measured in 26.8 | [[#safe-first]] |
| S6 (version staleness nags; partition verdict) | Code-hash staleness kept out of the partition verdict | [[#subjects]] |
| S9, S10 (26.9) | Fixed in 26.9 | [[task-26.9-impression-patterns#rev-round-1]] |
| M2 (26.8 arithmetic) | "40 save-states plus 250 typed" | [[#measured]] |
| M3 (recents glob misstated) | `handoff.py:104` is top-level only | [[#measured]] |
| M6 (MEMORY-RULES not updated) | Q8; 26.0 proposes the text | [[#open-questions]] |
| M9 (ordering vs 3.7, 26.9, 25.1) | Overlap table; 26.9 live step does not gate close; 26.7 before 25.1 | [[#overlap-37]] |
| Q2/Q5/Q6 verdicts | Taken as written | [[#open-questions]] |
| S7, S8 (plan-27) | Fixed in plan-27 | [[plan-27-memory-fleet-rollout#rev-round-1]] |
| M1, M4, M5, M7, M8 | Per-task | task revision tables |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]] (DIRTY 0B/7S/8M). Orchestrator decisions were
relayed on 2026-11-09.

| finding | change | anchor |
|---|---|---|
| s1 (19.4 AC-4's recall leg needs 19.1 R2 = 25.1) | Dropped from 26.6/26.8; recorded as landing with 25.1; note for plan-25 | [[#plan-19]] |
| s2 (the deploy reaches fleet dirs before plan-27's backups) | `.memory-layout` marker gates every new on-disk behaviour; readers dual; non-goal reworded; pre-deploy fleet snapshot | [[#layout-marker]], [[#non-goals]], [[task-26.8-refmatrix-live-rollout#rev-round-2]] |
| s3 ("newest" key) | `updated` (with time of day) then mtime; `created` dropped | [[task-26.1-layout-module-and-index-walk#rev-round-2]], [[task-26.3-savestate-subfolder#rev-round-2]] |
| s4 (rollback contradicts itself) | One per-id rule | [[task-26.5-memory-organise-verb#rev-round-2]] |
| s5 (apply moves, then the index refuses) | Preview renders; apply refuses before the first move | [[task-26.5-memory-organise-verb#rev-round-2]] |
| s7 (26.9 window) | Window in runs; pointer bullets; pre-measured cap | [[task-26.9-impression-patterns#rev-round-2]] |
| s6 (viascope prose) | Plan-27 task 27.2a | [[plan-27-memory-fleet-rollout#rev-round-2]] |
| m1, m2, m3, m4, m5, m7, m8 | Per-task tables | task revision tables |
| m5 (`~/.claude` count) | "2 live + 93 deleted" | [[#git-tracked]] |
| m6 | Plan-27 (27.0) | [[plan-27-memory-fleet-rollout#rev-round-2]] |
| Q8 verdict | Recorded: the user authorises at 26.8, with the reason | [[#open-questions]] |
