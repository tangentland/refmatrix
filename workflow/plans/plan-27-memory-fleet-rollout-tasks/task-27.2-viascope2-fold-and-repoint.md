---
gmd: "0.1"
id: task-27.2-viascope2-fold-and-repoint
title: "Task 27.2: fold viascope2's memories into viascope, point everything at viascope, retire the viascope2 dir"
tags: [task, plan-27, viascope, viascope2, merge, repoint, retire]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
  updated: 2026-11-09
---

# Task 27.2: viascope2 → viascope {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: [[task-27.0-organise-merge-from]], [[task-27.1-fleet-inventory]], [[task-27.2a-index-prose-to-memories]]

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: depends-on -> [[task-27.0-organise-merge-from]]
rel: depends-on -> [[task-27.2a-index-prose-to-memories]]

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
   `rmx memory organise <viascope memdir> --merge-from <viascope2 memdir> --store-from-memdir`.
   The preview must name viascope's store as the target (B2). Show the preview
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
   - `MEMORY.md` is regenerated. Its 62 hand-written prose lines (17 headers, a session log,
     "Active Campaign") take 22,643 chars, 94% of the budget, so the refusal is certain, not
     conditional (r2 s6). [[task-27.2a-index-prose-to-memories]] therefore runs FIRST: it
     converts the prose into approved `project/` memories, so the carried prose is at most 25%
     of the budget. Only then does this task's merge preview report `index: ok`. 26.5 AC-3
     refuses the apply otherwise, before any move (r2 s5). It is grouped by subject after 27.6.
     The 33 KB file is in the backup either way.
   - The stray `.memory.db` is reported and stays in place, covered by the backup. Deleting it
     is the user's decision.
   - If 27.1 shows the viascope store is missing memories, the apply's bridge run fills it, and
     the row counts before and after are recorded.
5. **AC-5: recall proves it.** In viascope's store, `rmx memory recall "<phrase unique to a
   migrated viascope2 memory>"` returns that memory. The same check passes for one
   viascope-native memory, as a control.
6. **AC-6: the viascope2 dir is retired, not deleted.** The backup tarball exists. The tombstone
   `README.md` names viascope's dir and the tarball. No `.md` memory remains there apart from the
   README. Deleting the dir needs a further explicit go from the user; it is not done here. The
   `~/github/atollogy/bdep/viascope2` checkout IS archived, by AC-8, after AC-5 passes (plan
   Q2, decided by the user 2026-11-09: archive, no delete).

7. **AC-7: git (S1).**
   - viascope's memdir is tracked by the viascope repo: 147 files at review time.
   - The fold's moves and imports are staged in that repo with `git mv`/`git add` (27.0 AC-8).
   - The verb stops, and the user commits in the viascope repo.
   - The viascope2 memdir is not tracked by a product repo. Check `~/.claude`: if it tracks the
     viascope2 memdir there, stage there too.

8. **AC-8: archive the viascope2 checkout; move and delete nothing (plan Q2; r5 m6).** Runs
   only after AC-2..AC-5 pass and AC-3 shows no viascope2 path left in viascope's store.
   - **Announce first.** Tell the user the target path and the tarball path before writing.
   - **Record before archiving**, into `workflow/review-output/27.2-viascope2-archive.log`:
     `du -sk` of the checkout; free space on the backups volume (stop and report if under twice
     the size); `git -C ~/github/atollogy/bdep/viascope2 status --porcelain`; unpushed commits
     (`git log --branches --not --remotes --oneline`); its remotes. Dirt or unpushed commits are
     reported to the user and archived as they are, never committed, reset or pushed.
   - **Backup.** `~/.refmatrix/backups/memory-organise/checkout-viascope2-<UTC ts>.tar.gz`,
     beside this plan's other backups. It holds the WHOLE checkout, `.git` and dotfiles
     included, so it restores to a working repo. Its member count must equal a full `os.walk`
     of the checkout that includes dotfiles (the 26.5 AC-3 rule), and `tar -tzf` must read it
     back. A failed or short backup stops here and writes no tombstone.
   - **Tombstone.** Write `RETIRED.md` at the checkout root, never over the repo's own
     `README.md`. If `RETIRED.md` already exists, stop and report. It names: the merge into
     viascope (`git subtree add`, `98df0696`, 2026-04-17), viascope's checkout, the tarball path
     and its member count, and "moving or deleting this checkout needs an explicit go from the
     user". It is left untracked: no commit in another repo.
   - **Nothing else.** The checkout is not moved, renamed or deleted, and no hub registry or
     launchd entry is changed by this AC (AC-3 owns repoints). The implementation summary names
     the tarball and the tombstone.

## Files to Create / Modify {#files}

- Modify the live dirs only through the verb.
- Create `workflow/implementation_summaries/task-27.2-viascope2-fold-and-repoint.md`.
- Create `workflow/review-output/27.2-*.log`, including `27.2-viascope2-archive.log` (AC-8).
- Create `~/github/atollogy/bdep/viascope2/RETIRED.md` (untracked tombstone, AC-8) and the
  checkout tarball under `~/.refmatrix/backups/memory-organise/`.

## Test Strategy {#test-strategy}

Live verification only; the code was tested in 27.0. Every store read and write goes through
viascope's daemon. No `Store()` opens.

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan26-27-spec-review-r1-96feccd]].

| finding | change | anchor |
|---|---|---|
| B2 (wrong store) | `--store-from-memdir`; the preview must name viascope's store | AC-2 |
| B4 (viascope's 62 prose lines) | Carried, or refused for a user decision; never dropped | AC-4 |
| S1 (the viascope repo tracks 147 memory files) | The fold is staged in the viascope repo; the user commits | AC-7 |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s6 (viascope prose migration anchored to no task) | 27.2a runs first; the preview must report `index: ok` before apply | AC-4 |
| s5 (apply-then-refuse) | Relies on 26.5 AC-3's refusal before the first move | AC-4 |

## Revision round 5 (2026-11-09) {#rev-round-5}

Answers [[bsd-plan26-27-spec-review-r5-3ded49e]].

rel: derives-from -> [[bsd-plan26-27-spec-review-r5-3ded49e]]

| finding | change | anchor |
|---|---|---|
| m6 (Q2 decided at 3ded49e but AC-6 said "neither is done here"; no archive step) | AC-6 reworded; new AC-8 archives the checkout as a whole-repo tarball in `~/.refmatrix/backups/memory-organise/` plus an untracked `RETIRED.md` tombstone, after the fold verifies; nothing moved or deleted without a further go | AC-6, AC-8, [[#files]] |
