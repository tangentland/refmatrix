---
gmd: "0.1"
id: task-26.4-savestate-mtype-normalisation
title: "Task 26.4: a save-state's type is session/recall-state wherever it came from, a disagreement is said, and the file fix does not move 'newest'"
tags: [task, plan-26, save-state, mtype, bridge, recall, bug-164]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
---

# Task 26.4: save-state mtype normalisation {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.1-layout-module-and-index-walk]], [[task-26.2-bridge-move-safety]]

rel: part-of -> [[plan-26-memory-organisation]]
rel: related-to -> [[plan-25-cliquedb-field-report]]

## Requirements {#requirements}

Four cliquedb save-states were written by hand and carry `type: project`. The bridge copies that
type into `memory_content.mtype`. As a result, hook-mode recall's `session/*` exclusion does not
hide them, and they inflate the recall payload. That inflation is bug-164's symptom. The budget
fix for bug-164 stays with plan-25.

1. **AC-1: the bridge rule.**
   - Applies to a file under `savestates/`, or a file whose `id` starts with `savestate_`.
   - The bridge stores `mtype = session/recall-state`. The frontmatter `type` is ignored for that
     file.
   - Every override is counted in `stats.mtype_normalised: [(id, from, to)]`.
   - The count is printed in the bridge report and carried by both `_bridge_stats` and
     `_bridge_wait_for_active_job` (ch-bsd r1 #m5).
   - At HEAD the store reads `project`, so this AC is RED.
2. **AC-2: the recall consequence.** After AC-1, the hook-mode call
   `rmx memory recall --stdin-json ... --json` no longer returns the hand-typed save-state. The
   same call with `--include-session` still returns it. Assert both.
3. **AC-3: the file is corrected, and "newest" stays where it was (ch-bsd r1 #s2).**
   - `rmx memory organise --apply` (26.5) rewrites `metadata.type` to `session/recall-state` in
     each mismatched file.
   - The rewrite is a metadata correction, not a content update. It preserves the file's mtime
     (`os.utime` to the prior value) and its `updated:`, `created:` and `originSessionId` fields.
   - The correction is listed in the organise report.
   - After the rewrite, disk and store agree, and the next bridge run counts zero normalisations.
   - Fixture: four cliquedb-shaped save-states with June/July mtimes and `updated:`, plus a newer
     August one. Run organise. `rmx recall-state` still resumes from the August one. If the
     rewrite bumped mtime or `updated:`, it would resume from July (RED).
4. **AC-3b: scope of the two halves (r2 s2).**
   - The AC-1 bridge rule is a store-row correction. It applies in every dir, organised or not,
     and writes no file. It reaches a file ONLY when the bridge re-ingests that file (r3 m8). The
     resume gate is hash-keyed, so an unchanged mis-typed save-state is skipped and keeps its
     wrong mtype.
     - **Organised dirs:** `organise --apply` forces a one-time re-bridge of every save-state file
       in the dir, whether it was moved, rewritten or untouched. The rule therefore reaches all of
       them at once. Test: an unchanged, mis-typed save-state reads `session/recall-state` after
       apply.
     - **Un-organised dirs:** the fix lands on the file's next touch (an edit or a re-save), or
       when plan-27 organises the dir. This is accepted and stated. cliquedb's four keep `project`
       in the store until 27.5.
   - The AC-3 file rewrite happens only through `organise --apply`, which writes the marker.
   - Under r2 s3, `updated:` is the ordering key. AC-3 preserves it, so the rewrite cannot change
     which save-state is newest.
5. **AC-4: other folders are report-only.** A `project`-typed file in `feedback/` is NOT
   re-typed. `organise --check` reports it as `folder/type mismatch` (plan Q3).

## Files to Create / Modify {#files}

| file | change |
|---|---|
| `src/refmatrix/ingest_gmd.py` | mtype resolution (around line 943), using `memory_layout` |
| `src/refmatrix/cli.py` | `_bridge_stats`, `_bridge_wait_for_active_job` |
| `tests/test_savestate_mtype.py` | create |

## Test Strategy {#test-strategy}

- The fixture is a synthetic copy of the cliquedb shape: frontmatter only, made-up body. No raw
  session text goes into the public repo.
- Run the real bridge, recall, organise and recall-state CLIs against a throwaway store in task
  23.0's sandbox.
- Mutation checks:

| mutation | RED |
|---|---|
| remove the override | AC-1, AC-2 |
| let the rewrite touch mtime | AC-3 |

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| S2 (rewrite resumes from the wrong save-state) | Rewrite preserves mtime and `updated:`; recall-state assertion | AC-3 |
| M5 (waited-job branch) | `mtype_normalised` carried there too | AC-1 |
| Q4 verdict | Sound; unchanged | [[#requirements]] |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s2 (fleet effect of the deploy) | The store rule applies everywhere (no file write); the file rewrite only via organise | AC-3b |
| s3 (ordering key) | AC-3's preservation of `updated:` is what keeps the newest stable under the new key | AC-3b |

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| m8 (the store rule reaches only re-ingested files) | `organise --apply` forces a one-time re-bridge of all save-states; un-organised dirs are fixed on next touch, accepted and stated | AC-3b |
