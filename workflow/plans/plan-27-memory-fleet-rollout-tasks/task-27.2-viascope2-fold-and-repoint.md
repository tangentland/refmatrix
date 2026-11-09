---
gmd: "0.1"
id: task-27.2-viascope2-fold-and-repoint
title: "Task 27.2: fold viascope2's memories into viascope, point everything at viascope, retire the viascope2 dir"
tags: [task, plan-27, viascope, viascope2, merge, repoint, retire]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
---

# Task 27.2: viascope2 → viascope {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: [[task-27.0-organise-merge-from]], [[task-27.1-fleet-inventory]]

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: depends-on -> [[task-27.0-organise-merge-from]]

## Requirements {#requirements}

User (2026-11-08): "if viascope points to viascope2, it needs to point to viascope." The
viascope2 design repo was merged into viascope on 2026-04-17 (`git subtree add`, `98df0696`).
Its memory `project_viascope2_merged` says the dir is archivable. Its 32 memories were never
carried over: 31 exist only there, and 1 (`reference_atleps01_deploy_target`) overlaps by
filename.

1. **AC-1: inventory every viascope2 reference before the fold.** Record each of these as a
   table row with its repoint action:
   - hook and bridge paths naming `viascope2` in both checkouts' `.claude/settings*.json`;
   - `CLAUDE.md` in both checkouts;
   - viascope's store rows whose `memory_content.metadata.source_path` sits under viascope2's
     memdir (daemon read);
   - viascope's and viascope2's `MEMORY.md` links;
   - any `[[id]]` in viascope's memories that names a viascope2-only id;
   - any hub registry or launchd entry naming viascope2.
2. **AC-2: the fold goes through the verb.** Run
   `rmx memory organise <viascope memdir> --merge-from <viascope2 memdir>`. Show the preview
   to the user, including the overlap's diff and the Q1 resolution. Then `--apply`. Both
   tarballs are named. Every imported file lands in viascope's type folders, which on the symlink
   means the resolved target under `~/at/bdep/viascope/.claude/projects/…`. `created:` and
   `originSessionId` are byte-identical (spot-check 5). Rewritten edges are listed.
3. **AC-3: everything points at viascope.** Every AC-1 row is repointed or recorded as "no
   change needed". Hook or settings edits in either checkout are announced first, backed up, and
   diffed. No viascope2 path remains in viascope's store `source_path` after the bridge (26.2
   refresh), checked with a daemon read.
4. **AC-4: viascope's own dir is put in order.**
   - `organise --check` reads clean.
   - `MEMORY.md` is regenerated: it was 33 KB and must come in under budget, grouped by subject
     after 27.6.
   - The stray `.memory.db` is reported and stays in place, covered by the backup. Deleting it
     is the user's decision.
   - If 27.1 shows the viascope store is missing memories, the apply's bridge run fills it, and
     the row counts before and after are recorded.
5. **AC-5: recall proves it.** In viascope's store, `rmx memory recall "<phrase unique to a
   migrated viascope2 memory>"` returns that memory. The same check passes for one
   viascope-native memory, as a control.
6. **AC-6: the viascope2 dir is retired, not deleted.** The backup tarball exists. The tombstone
   `README.md` names viascope's dir and the tarball. No `.md` memory remains there apart from the
   README. Deleting the dir, and archiving the `~/github/atollogy/bdep/viascope2` checkout, are
   flagged for the user (plan Q2). Neither is done here.

## Files to Create / Modify {#files}

- Modify the live dirs only through the verb.
- Create `workflow/implementation_summaries/task-27.2-viascope2-fold-and-repoint.md`.
- Create `workflow/review-output/27.2-*.log`.

## Test Strategy {#test-strategy}

Live verification only; the code was tested in 27.0. Every store read and write goes through
viascope's daemon. No `Store()` opens.
