---
gmd: "0.1"
id: task-27.1-fleet-inventory
title: "Task 27.1: inventory every memory dir — dry-run plan, store mapping, bridge coverage — before anything moves"
tags: [task, plan-27, inventory, dry-run, mapping, bridge]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
---

# Task 27.1: fleet inventory {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: plan-26 deployed

rel: part-of -> [[plan-27-memory-fleet-rollout]]

## Requirements {#requirements}

This task is read-only. Output: `workflow/plans/plan-27-memory-fleet-rollout-tasks/inventory.md`
(GMD, lint-clean).

1. **AC-1: one row per `~/.claude/projects/*/memory`, empty dirs included.** Each row gives:
   - the resolved path, and whether it is a symlink;
   - the `organise` preview counts: moves, unplaceable, non-GMD (named), type_mismatch,
     mis-typed save-states, duplicate_ids;
   - `MEMORY.md` lines and characters;
   - the links in `MEMORY.md` that point at missing files.
2. **AC-2: the mapping is computed, not guessed.** For each known repo root, compute
   `handoff.default_memory_dir(root)` to get the slug. A memdir with no matching root is marked
   `orphan`. For each root record:
   - `.refmatrix/` present?
   - supervised? (`rmx daemon launchctl status` run in that root, plus `rmx hub status`)
   - the memory partition the bridge would use
   - does a SessionStart bridge hook exist? (read the generated hook commands in
     `.claude/settings*.json`)
   - `rmx install-hooks --check` result, as read-only drift.
3. **AC-3: bridge coverage is measured.** In each store-backed project: the memory-row count of
   its memory partition (daemon op, e.g. `rmx memory list`/`memory_stats`) versus the GMD files
   on disk. Also run `rmx memory recall` for one phrase unique to the newest file. viascope and
   cliquedb are the expected gaps, because they have no SessionStart bridge.
4. **AC-4: name the anomalies.**
   - viascope2: orphan, merged repo.
   - thiquet: memdir `-bdep-thiquet` maps to the unsupervised bdep/thiquet store; the supervised
     `~/enduris/thiquet` maps to no memdir.
   - viascope: symlink, plus a stray `.memory.db`.
   - ble-sniffer-mqtt: checkout not found.
   - home dir: maps to the global store.
5. **AC-5: no live change.** The commands run are the deployed `rmx` read paths and the
   `organise` preview. Nothing is written in any memdir or store. The inventory doc names each
   command it ran.

## Files to Create / Modify {#files}

- Create `workflow/plans/plan-27-memory-fleet-rollout-tasks/inventory.md`.
- Create `workflow/review-output/27.1-*.log`.

## Test Strategy {#test-strategy}

There is no code. The check is that rerunning the inventory gives the same counts (idempotent,
read-only). `@ch-bsd` spot-checks three rows against the disk.
