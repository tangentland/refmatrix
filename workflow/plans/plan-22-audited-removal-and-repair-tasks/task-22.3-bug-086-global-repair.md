---
gmd: "0.1"
id: task-22.3-bug-086-global-repair
title: "Task 22.3: bug-086 as the first apply — repair the global store's relative learned rows, remove only the unrecoverable"
tags: [task, repair, global-store, bug-086]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 22.3: the global-store repair {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending
> Depends on: 22.1, 22.2; the remedy merge deployed

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: related-to -> [[project_global_relative_rows_repair]]

## Why {#why}

The global store (`~/.refmatrix`) holds 1,087 relative learned entities with 5,159 evidence rows.
About 700 read as unreadable on every global grep (bug-086). The user decided on 2026-10-07: after
the new code deploys, recover the 476 that verify uniquely and forget the 611 that cannot. That
decision becomes this plan's first apply, replacing the standalone daemon op. {#why-body}

## Requirements {#requirements}

1. **R1** Run `audit` (22.1) on a COPY of the global catalog. The `orphan-root` rows with a unique
   verifying root become repair candidates (expected ≈ 476 entities); the rest are removal
   candidates (≈ 611).
2. **R2** Back up the global store (an APFS clone) before the apply. The user confirms the dry-run
   counts first.
3. **R3** Apply through 22.2. Repairs rewrite to absolute paths, removals are tombstoned, and the
   manifest is kept.
4. **R4** Verify: a global grep over the repaired concepts reports 0 unreadable for them, and the
   memory rows of the global store are untouched (count before == after).

## Acceptance criteria {#acceptance}

1. The dry-run counts on the copy are reported, and the user confirms them before the apply.
2. After the apply: the repaired rows verify; the removed rows are in the manifest; the memory
   count is unchanged; bug-086 is `fixed`.
