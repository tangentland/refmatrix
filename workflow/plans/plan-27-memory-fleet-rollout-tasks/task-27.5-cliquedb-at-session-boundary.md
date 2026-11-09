---
gmd: "0.1"
id: task-27.5-cliquedb-at-session-boundary
title: "Task 27.5: cliquedb's memory dir is organised at its session boundary, announced on its bus channel"
tags: [task, plan-27, cliquedb, migration, bus, session-boundary]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
---

# Task 27.5: cliquedb, staged {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: [[task-27.1-fleet-inventory]], [[task-27.4-quiet-dir-migrations]]

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: related-to -> [[task-26.4-savestate-mtype-normalisation]]

## Requirements {#requirements}

cliquedb has 248 memories, 63 save-states (4 typed `project` by hand) and 6 non-GMD files, and
it has an ACTIVE session. Moving files under a running session could race its own memory
writes. It would also race its `rmx save-state`, which, once deployed, writes `savestates/`
itself.

1. **AC-1: stage.** Save the `organise` preview to `workflow/review-output/27.5-cliquedb.log`
   and post a bus message on `proj:cliquedb:*`. The message gives what will move, the 4
   type rewrites, the 6 non-GMD files left in place, the backup location, and the request to
   apply at the next session end.
2. **AC-2: apply only at a boundary.** Apply only after the cliquedb session acknowledges on the
   bus, or after there has been no session activity for 30 minutes. Activity is measured as no
   new STM events in its store and no file under its memdir modified in that window. Back up
   first, then `--apply`.
3. **AC-3: verify.**
   - `--check` is clean.
   - In cliquedb's root, `rmx memory recall "<phrase unique to savestate_7c4e19d2a8f3>"` returns
     it with `--include-session` and NOT in hook mode. This shows the type rewrite reached the
     store, which matters to bug-164.
   - `rmx recall-state` resumes.
4. **AC-4: report back on the bus** with the counts and the tarball path.

## Files to Create / Modify {#files}

- Modify the live dir through the verb only.
- Create `workflow/implementation_summaries/task-27.5-cliquedb-at-session-boundary.md`.

## Test Strategy {#test-strategy}

Live verification through cliquedb's daemon only.
