---
gmd: "0.1"
id: task-26.4-savestate-mtype-normalisation
title: "Task 26.4: a save-state's type is session/recall-state wherever it came from, and a disagreement is said"
tags: [task, plan-26, save-state, mtype, bridge, recall, bug-164]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.4: save-state mtype normalisation {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.1-layout-module-and-index-walk]], [[task-26.2-bridge-move-safety]]

rel: part-of -> [[plan-26-memory-organisation]]
rel: related-to -> [[plan-25-cliquedb-field-report]]

## Requirements {#requirements}

Four cliquedb save-states that an agent wrote by hand carry `type: project`. The bridge copies
that into `memory_content.mtype`, so hook-mode recall's `session/*` exclusion does not hide them
and they inflate the recall payload (bug-164's symptom; bug-164 keeps the budget fix).

1. **AC-1: the bridge rule.** For a file under `savestates/`, or whose `id` starts with
   `savestate_`, the bridge stores `mtype = session/recall-state`. The frontmatter `type` is
   ignored for that file. The override is counted in `stats.mtype_normalised: [(id, from, to)]`,
   printed in the bridge report and carried by `_sync_memory_dir`. At HEAD the store reads
   `project` (RED).
2. **AC-2: the recall consequence.** After AC-1, `rmx memory recall --stdin-json ... --json` (the
   hook-mode call) over the throwaway store no longer returns the hand-typed save-state. It still
   returns it with `--include-session`. Assert both.
3. **AC-3: the file is corrected, not only the row.** `rmx memory organise --apply` (task 26.5)
   rewrites `metadata.type` in each mismatched file to `session/recall-state`, bumps `updated:`
   and leaves `created:` and `originSessionId` frozen. Disk and store then agree. The next bridge
   run counts zero normalisations.
4. **AC-4: other folders are report-only.** A `project`-typed file in `feedback/` is NOT
   re-typed. `organise --check` reports it as `folder/type mismatch`. Plan Q3.

## Files to Create / Modify {#files}

- Modify `src/refmatrix/ingest_gmd.py` (the mtype resolution at about line 943, using
  `memory_layout`).
- Modify `src/refmatrix/cli.py` (`_bridge_stats`).
- Create `tests/test_savestate_mtype.py`.

## Test Strategy {#test-strategy}

Fixture: a synthetic copy of the cliquedb shape (frontmatter only, made-up body; no raw session
text in the public repo). Run the real bridge CLI and the real recall CLI against a throwaway
store. Mutation check: remove the override and AC-1 and AC-2 go RED.
