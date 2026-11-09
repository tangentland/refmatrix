---
gmd: "0.1"
id: task-26.8-refmatrix-live-rollout
title: "Task 26.8: deploy, measure the one-time refresh, back up, organise the refmatrix memory dir, re-compile its subjects, and prove it by recall"
tags: [task, plan-26, deploy, live, migration, verification]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
---

# Task 26.8: refmatrix live rollout {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: 26.0-26.7 merged to `master` and released. 26.9 is NOT a dependency.

rel: part-of -> [[plan-26-memory-organisation]]
rel: reinforces -> [[feedback_deploy_tree_is_the_runtime]]
rel: reinforces -> [[feedback_restart_daemon_after_promote]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]

## Requirements {#requirements}

This task applies the result to the refmatrix dir ONLY. Every other dir is
[[plan-27-memory-fleet-rollout]]. Every live step is announced to the user first and backed up
first.

0. **AC-0: pre-deploy fleet snapshot and measurement (r2 s2). Read-only, no new code.**
   - **Snapshot.** Before the deploy, tar every `~/.claude/projects/*/memory/MEMORY.md` and every
     `.memory_hooks.json` into `~/.refmatrix/backups/memory-organise/fleet-pre-26.8-<ts>.tar.gz`.
     Follow symlinked memdirs to their targets. Record the member count.
   - **Measure the refresh on copies.** With the DEV build (`.venv-eval`), for each live memdir:
     copy the memdir and its store's read snapshot into a sandbox under a short `mkdtemp()` root,
     then run `rmx ingest-gmd --as-memory --dry-run` (26.2 AC-3) against the copies. Record
     `refresh_pending` per store in `workflow/review-output/26.8-refresh-pending.log`. The live
     store and the live memdir are never touched by the dev build.
   - **What the deploy must and must not do.** Gated behaviours are marker-gated, so the deploy
     must change no file in any un-organised dir. Ungated, it must not refresh `source_path` in
     any un-organised dir. Spot-check after AC-1: cliquedb's and viascope's `MEMORY.md` are
     byte-identical to the snapshot after one save-state or bridge there.
1. **AC-1: deploy.**
   - Release on `master`.
   - Run `git -C ~/refmatrix pull --ff-only origin master`, then `rmx daemon restart --relaunch`.
   - `rmx version -v` must show the import path under `~/refmatrix`.
   - Restart the hub with `rmx hub stop`, then ONE `launchctl kickstart`.
2. **AC-2: confirm the measured refresh (ch-bsd r1 #s5; r2 s2).**
   - The refmatrix dir is not organised yet, so the deploy alone triggers no refresh here.
   - After AC-4's apply writes the marker, the first bridge runs the refresh. Its bridge report
     must show re-ingested rows equal to AC-0's measured `refresh_pending`, within ±5 (files
     edited in between).
   - Then run ONE `rmx memory sync-disk` and record two things from the bridge report: the number
     of rows re-ingested, and the store write counter. Record wall time only as context.
   - If `refresh_pending` is more than 50, or the sync holds `_store_lock` for more than 60 s,
     STOP. Log a bug row and report to the user before AC-4.
3. **AC-3: preview.**
   - Run `rmx memory organise <live memdir>` with the default `--store-from-memdir` (26.5 AC-1).
     The resolved store must be refmatrix's.
   - Save the plan to `workflow/review-output/26.8-organise-preview.log`.
   - The counts must match a fresh survey of the dir. Expected: 40 save-states to `savestates/`,
     and the 250 typed files to `feedback/`, `project/` and `reference/` (68, 170 and 12) per
     plan Q1. `unplaceable` must be 0, or every unplaceable file is named.
   - The preview must report `index: ok` (26.5 AC-2, r2 s5).
   - The preview must report `git_tracked: ~/.claude` for the two tracked files: `MEMORY.md` and
     `project_csn_production_harness.md`. It must also report the carried prose line count.
4. **AC-4: back up, then apply.**
   - Stop for the user's go-ahead, then run `--apply`.
   - The tarball must exist, and its member count must equal the full walk.
   - The two `~/.claude`-tracked moves must appear as staged `git mv`s.
   - The verb exits 3 with the exact `git -C ~/.claude commit -m '…' -- <paths>` command. Never
     `commit -a`: `~/.claude` carries 93 unrelated unstaged deletions. The user commits.
   - The bridge report must show zero `duplicate_ids` and zero errors.
5. **AC-5: prove it.** Capture each check to a log.
   - `rmx recall-state` shows the newest save-state by `updated`, read from `savestates/`. The
     moved files' mtimes are unchanged (spot-check 5).
   - `rmx memory recall "<phrase unique to one moved save-state>"` returns that save-state.
   - The same recall check passes for one moved feedback memory.
   - `rmx context <a moved memory's anchor>` shows a `path` under the new folder (26.2).
   - `rmx memory organise --check` is clean.
6. **AC-6: re-compile (26.6 builds 19.4).**
   - Run `memory_compile --apply` (scope `memory`) through the daemon.
   - The 20 pre-0.34 rows (15 `unlabeled_N`; `from`, `existing`, `feedback`, `fixes`, `memory`)
     must read `stale = true` with a `stale_since`. They must still be present, be returned by
     `rmx memory get`, show their mark in `rmx memory list --type subject`, and be absent from
     `MEMORY.md`. Recall absence is NOT asserted here: it lands with 25.1 AC-6 (r2 s1).
   - The run summary must report `stale_new`.
   - `rmx daemon status` must show no `memory-compile` line.
   - Grade the labels per 26.6 AC-E. Record the band and the action taken.
7. **AC-7: the index (26.7 builds 19.3).**
   - `MEMORY.md` is regenerated with live-subject blocks, under budget.
   - `rmx memory index --check-reach` passes.
   - `--check` reads in sync.
   - Curated hooks survive (spot-check 5).
   - Hand-written prose is carried.
8. **AC-8: MEMORY-RULES (plan Q8, recorded: the user authorises it here).**
   - Show the user the ADR-0005 appendix paragraph, and apply it to `~/.claude/MEMORY-RULES.md`
     with their authorisation.
   - **Why it matters.** Until the paragraph lands, every agent writes new memories at the memdir
     TOP level. Each one keeps `organise --check` non-zero. If an agent re-creates a top-level
     file whose id already lives in a type folder, that also trips 26.2's duplicate-id refusal:
     the row freezes until a human resolves it.
   - After the edit, the next `rmx save-state` reports zero strays.
9. **AC-9: rollback rehearsal (dry).**
   - Name the backup path in the implementation summary.
   - Do NOT run `--rollback` live unless AC-5 fails.

## Files to Create / Modify {#files}

| file | change |
|---|---|
| `workflow/implementation_summaries/task-26.8-refmatrix-live-rollout.md` | create |
| `handoff.md` | update |
| `workflow/bug_registry.md` | a row for anything found |

## Test Strategy {#test-strategy}

This task is a live verification, not new tests.
- Every command runs the deployed `rmx`.
- The live store is touched only through daemon ops.
- No `Store()` opens.
- No dev-venv `rmx` against the live store.

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| S5 (unstated one-time full re-ingest) | Measured before it happens, with a stop threshold | AC-2 |
| M2 (arithmetic) | "40 save-states plus 250 typed (68+170+12)" | AC-3 |
| S1 (`~/.claude` tracks 2 refmatrix memory files) | Staged `git mv`, user commits | AC-3, AC-4 |
| B2 | `--store-from-memdir`; resolved store checked | AC-3 |
| B1 / Q5 | `stale`/`stale_since` replaces `retired_at`; 19.3 index | AC-6, AC-7 |
| M6 | MEMORY-RULES paragraph applied with the user's go-ahead | AC-8 |
| M9 (26.9 must not gate) | Header | header |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s1 (the AC-6 recall assertion needs 25.1) | Recall leg removed; the mark, `get`, the list and the index are asserted | AC-6 |
| s2 (the deploy reaches fleet dirs before plan-27's backups; "measure before deploy" impossible) | Pre-deploy fleet snapshot; dev-build measurement on copies; post-deploy byte-identity spot-check; AC-2 confirms the measured count at the first marker-on bridge | AC-0, AC-2 |
| m5 (`~/.claude` stop and dirt) | Exit 3, exact commit command, never `commit -a` | AC-4 |
| Q8 (recorded) | The user authorises at 26.8; reason stated | AC-8 |
