---
gmd: "0.1"
id: task-27.4-quiet-dir-migrations
title: "Task 27.4: organise every remaining memory dir, one at a time, backed up, with a recall check per store-backed dir"
tags: [task, plan-27, migration, memory-dir, rollback]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
  updated: 2026-11-09
---

# Task 27.4: quiet-dir migrations {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: [[task-27.1-fleet-inventory]]; for the thiquet dir, also
> [[task-27.3-thiquet-store-repoint]]

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]

## Requirements {#requirements}

Scope: every non-empty dir in [[plan-27-memory-fleet-rollout#survey]] except refmatrix (26.8),
viascope and viascope2 (27.2) and cliquedb (27.5). Order: smallest first. The home dir
(`-Users-tholley`, global store) goes last (plan Q4).

1. **AC-1: one dir at a time.** For each dir:
   1. announce it;
   2. run the `organise` preview and save it to `workflow/review-output/27.4-<slug>.log`;
   3. `--apply`, which takes the backup first;
   4. `--check` must be clean;
   5. only then start the next dir.
   A failure stops the sequence. It does not get skipped.
2. **AC-2: store-backed dirs prove it by recall.** For cliquet, thiquet (after 27.3), atldb,
   orderly, cat-herder, atlftpd and home: `rmx memory recall "<phrase unique to one moved
   memory>"` in that project's root returns it. Where the dir has save-states,
   `rmx recall-state` shows the newest from `savestates/`.
3. **AC-3: no-store dirs are file-only, and the output says so.** For the no-store dirs
   (portal, intropretor, enduris-*, evolution, gmd, ble-sniffer-mqtt), the verb reports
   `no store` and the bridge is not run. `MEMORY.md` is regenerated (kind-grouped).
4. **AC-4: non-GMD and unplaceable files are left where they are and named.** For example the
   home dir's 1 non-GMD file stays at the top level, and it is listed in the summary with a
   proposed fix for the user.
5. **AC-5: rollback is per dir.** Name each tarball in the summary. If any AC-2 check fails, run
   `--rollback` for that dir only, log a bug row, and stop.

6. **AC-6: round-1 rules, per dir.**
   - **B2.** Every run passes `--store-from-memdir`. The preview's resolved store must equal the
     27.1 mapping for that dir, or the dir stops.
   - **B4.** Prose (cliquet: 8 lines) is carried, and hooks are kept by id. A refusal stops the
     sequence for a user decision.
   - **S1.** Tracked files (`~/.claude`) are staged with `git mv`, and the user commits before the
     next dir.
   - **S8.** A dir whose project has a live session waits for that session's acknowledgement.

## Files to Create / Modify {#files}

- Modify the live dirs through the verb only.
- Create `workflow/implementation_summaries/task-27.4-quiet-dir-migrations.md`.

## Test Strategy {#test-strategy}

Live verification. All store work goes through each project's daemon. Where a project has no
daemon, the bridge's `require_daemon` rule applies: in-process only when there is no daemon, and
never on a busy one.

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan26-27-spec-review-r1-96feccd]].

| finding | change | anchor |
|---|---|---|
| B2 (wrong store) | `--store-from-memdir`; the preview must name the expected root | AC-6 |
| B4 (prose and hooks) | Carried prose and id-keyed hooks; refusal stops the sequence | AC-6 |
| S1 (tracked memdirs) | Staged in `~/.claude`; the user commits per dir | AC-6 |
| S8 (live sessions) | The project's acknowledgement first; no idle timer | AC-6 |
