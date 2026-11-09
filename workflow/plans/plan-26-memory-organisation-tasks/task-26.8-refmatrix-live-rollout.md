---
gmd: "0.1"
id: task-26.8-refmatrix-live-rollout
title: "Task 26.8: deploy, back up, organise the refmatrix memory dir, re-compile its subjects, and prove it by recall"
tags: [task, plan-26, deploy, live, migration, verification]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.8: refmatrix live rollout {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: 26.0-26.7 merged to `master` and released

rel: part-of -> [[plan-26-memory-organisation]]
rel: reinforces -> [[feedback_deploy_tree_is_the_runtime]]
rel: reinforces -> [[feedback_restart_daemon_after_promote]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]

## Requirements {#requirements}

This task applies the result to the refmatrix dir ONLY. Every other dir is
[[plan-27-memory-fleet-rollout]]. Every live step is announced to the user first and backed up
first.

1. **AC-1: deploy.** Release on `master`. Then
   `git -C ~/refmatrix pull --ff-only origin master`, `rmx daemon restart --relaunch`, and
   `rmx version -v`, which must show the import path under `~/refmatrix`. Restart the hub with
   `rmx hub stop` followed by ONE `launchctl kickstart`.
2. **AC-2: preview.** Run `rmx memory organise` on the live dir. Save the plan to
   `workflow/review-output/26.8-organise-preview.log`. Its counts must match a fresh survey of the
   dir (the expected order of magnitude: 40 save-states; 290 other files placed by type; 0
   unplaceable or every one named).
3. **AC-3: back up, then apply.** Stop for the user's go-ahead. Then run `--apply`. The tarball
   exists, and its member count equals the walk. The bridge report has zero `duplicate_ids` and
   zero errors.
4. **AC-4: prove it.** Each check is captured to a log.
   - `rmx recall-state` shows the newest save-state from `savestates/`.
   - `rmx memory recall "<phrase unique to one moved save-state>"` returns it.
   - The same check passes for one moved feedback memory.
   - `rmx context <a moved memory's anchor>` shows a `path` under its new folder (26.2).
   - `rmx memory organise --check` is clean.
5. **AC-5: re-compile.** Run `rmx memory compile --apply` through the daemon. The 20 stale
   rows read `retired_at`. `rmx daemon status` shows no `memory-compile` stale line. Do the
   26.6 AC-7 grade and record the band and the action taken.
6. **AC-6: the index.** `MEMORY.md` is regenerated grouped by subject and is under budget, and
   `--check` reads in sync. Spot-check that curated hooks survive.
7. **AC-7: rollback rehearsal (dry).** Name the backup path in the implementation summary.
   `--rollback` is NOT run live unless AC-4 fails.

## Files to Create / Modify {#files}

- Modify `workflow/implementation_summaries/task-26.8-refmatrix-live-rollout.md`.
- Modify `handoff.md`.
- Modify `workflow/bug_registry.md` (rows for anything found).

## Test Strategy {#test-strategy}

This is a live verification, not new tests. Every command runs the deployed `rmx` against the
live store only through daemon ops. No `Store()` opens. No dev-venv `rmx` against the live store.
