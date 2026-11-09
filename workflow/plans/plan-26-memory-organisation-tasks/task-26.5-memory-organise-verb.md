---
gmd: "0.1"
id: task-26.5-memory-organise-verb
title: "Task 26.5: rmx memory organise — memdir-resolved store, preview, backed-up apply (git mv where tracked), id-aware rollback, check"
tags: [task, plan-26, verb, migration, memory-dir, backup, rollback, git]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-09
---

# Task 26.5: the organise verb {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.1-layout-module-and-index-walk]], [[task-26.2-bridge-move-safety]],
> [[task-26.3-savestate-subfolder]], [[task-26.4-savestate-mtype-normalisation]]. Rebase on task
> 3.7's verb changes ([[plan-26-memory-organisation#overlap-37]]).

rel: part-of -> [[plan-26-memory-organisation]]
rel: reinforces -> [[feedback_dry_run_match_real_cost]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]
rel: reinforces -> [[feedback_store_calls_via_daemon]]
rel: depends-on -> [[task-26.2-bridge-move-safety]]

## Requirements {#requirements}

There is one migration mechanism, and it is a verb: `rmx_memory_organise` in `verbs.py`. The CLI
command `rmx memory organise [MEMDIR]` and the MCP tool are thin adapters over it, and the
verb-parity test covers both. No file is ever moved by hand, here or in plan-27.

1. **AC-1: the target store comes from the memdir, never from the cwd (B2).**
   - The verb resolves the store with `_root_from_projects_slug` (`cli.py:113`), applied to the
     UNRESOLVED memdir path. It must be the unresolved path because viascope's resolved path lies
     outside `~/.claude/projects`.
   - It resolves the partition from that root's own default.
   - If the cwd's store (`_root()`) differs from the resolved root, the verb refuses with a
     non-zero exit and names both roots. `--store-from-memdir` (the default in plan-27 runs) skips
     this check: the verb then uses the resolved root and ignores the cwd.
   - A memdir with no matching root is `no store`: file-only, the bridge is not run, and the
     output says so.
   - Every store write goes through `_sync_memory_dir`, run with that root's daemon. `_root()` is
     overridden for the call, the same way `REFMATRIX_ROOT` is honoured.
   - RED test: run the verb from root A on root B's memdir. Assert that no row lands in A and that
     the rows land in B. At HEAD there is no such verb, and `_sync_memory_dir` writes into the
     cwd's store.
2. **AC-2: preview by default.** With no flag, the verb moves nothing. It returns and prints a
   plan containing:
   - every move `(from, to)`, using `folder_for_type(metadata.type)` with a filename-prefix
     fallback;
   - `unplaceable` files: no type, an unknown type, or non-GMD, each named;
   - `type_mismatch` files;
   - the save-state type rewrites (26.4 AC-3);
   - `duplicate_ids`;
   - `refresh_pending` (26.2 AC-3);
   - the resolved store and partition, or `no store`;
   - whether the memdir is a symlink, and its resolved target;
   - `git_tracked: <toplevel>` with a count of tracked files, or `untracked` (S1);
   - `prose_lines` carried from `MEMORY.md` (26.1 AC-5).

   `--only <folder>` restricts the plan to one folder (plan Q1).
3. **AC-3: the backup comes first, and a failed backup stops the apply.**
   - `--apply` writes `~/.refmatrix/backups/memory-organise/<slug>-<UTC ts>.tar.gz`.
   - The archive holds every file under the RESOLVED memdir: `MEMORY.md`, `.memory_hooks.json`,
     dotfiles and dot-dirs included.
   - The archive's member count is checked against a FULL `os.walk` of the dir that includes
     dotfiles. It is not checked against `iter_memory_files` (ch-bsd r1 #m7).
   - Only after that check passes does anything move. A failed backup moves nothing and exits
     non-zero.
4. **AC-4: moves are atomic, identity-safe, keep mtimes, and respect git (S1).**
   - **Untracked dir.** Each move is an `os.replace` inside the resolved memdir. The mtime is
     preserved (`os.utime` to the prior value).
   - **Tracked dir** (`git -C <memdir> ls-files` lists the file). Each move is a `git mv` in the
     owning repo. After all moves the verb STOPS: it prints the staged summary and the suggested
     commit message, and does not commit. The user commits. `--apply` in a tracked dir never
     leaves a delete-plus-untracked pair.
   - **Conflicts.** If the target exists with DIFFERENT bytes, the verb does not overwrite it. It
     lists the pair as a `conflict` and both files stay.
   - **Hooks.** No sidecar key rewrite is needed, because 26.1 keys hooks by id.
   - **Index.** `MEMORY.md` is regenerated through `memory_index.write`, which carries prose
     (26.1 AC-5) and refuses if content would be lost (26.1 AC-6).
5. **AC-5: the bridge runs through the resolved store's daemon.** The result includes the 26.2
   refresh counts, `duplicate_ids`, `mtype_normalised`, and the embed counts.
6. **AC-6: recall proves it.** In the throwaway end-to-end test, after `--apply`:
   - `rmx memory recall "<phrase unique to a moved save-state>"`, run in the resolved root,
     returns it;
   - `rmx recall-state` shows the newest save-state by 26.1's ordering;
   - the mtimes of the moved files equal their pre-move values.

   `memory get` alone is not proof.
7. **AC-7: rollback is id-aware and never overwrites later edits (S4).** `--rollback <tarball>`:
   1. For each file currently in the memdir whose bytes differ from its archived copy, or which
      is absent from the archive, moves it aside to
      `~/.refmatrix/backups/memory-organise/aside-<slug>-<ts>/`. Asides are never written inside
      the memdir (S3).
   2. Lists every same-id pair, archive copy vs. current copy, as a `conflict`. It does not
      resolve them silently. Default: keep the current file and do not restore the archive copy
      of that id. `--prefer-archive <id>` overrides this per id.
   3. Restores the remaining archived files, then re-runs the bridge.
   4. In a tracked dir, it instead reverses the `git mv`s and stops for the user.

   Test: after `--apply`, re-save a save-state into `savestates/` and edit one feedback memory,
   then roll back. Both edits survive (as current or aside) and are named in the report, and
   recall-state still resumes from the re-saved handoff.
8. **AC-8: check mode, report-only.**
   - `--check` exits non-zero when any file is out of place, a save-state is mis-typed, a
     duplicate id exists, or `refresh_pending > 0`. It changes nothing.
   - `rmx save-state` prints a one-line `organise --check` summary but never moves a file (plan
     Q2, ch-bsd r1 verdict: report-only).
9. **AC-9: fail closed on a live store.** The verb never opens `Store()` itself.

## Files to Create / Modify {#files}

- Create `src/refmatrix/memory_organise.py`: plan, apply, rollback, check, store resolution.
- Modify `src/refmatrix/verbs.py`: the verb and its parity-map entry.
- Modify `src/refmatrix/cli.py`: the `memory organise` command; a `_sync_memory_dir(memdir,
  root=)` parameter.
- Modify `src/refmatrix/mcp.py`, if its tool table is not generated from verbs.
- Regenerate the generated CLI-tree doc, if there is one
  ([[feedback_family_list_misses_generated_checks]]).
- Create `tests/test_memory_organise.py`.

## Test Strategy {#test-strategy}

The end-to-end harness runs in task 23.0's sandbox. A short `mkdtemp()` root holds:
- `HOME/.claude/projects/<slug-A>/memory` and `<slug-B>/memory`, each a refmatrix-shaped flat dir
  with 2 feedback, 2 project and 3 savestate memories, plus 1 non-GMD file;
- two throwaway projects, each with its own daemon;
- the real CLI and the MCP verb.

Cases:
- the wrong-cwd case (AC-1);
- a symlinked memdir;
- a git-tracked memdir (a `git init` in the sandbox), where the verb stops before the commit;
- a conflict;
- a failed backup (backup dir made read-only);
- the rollback with post-backup edits.

Mutation checks:

| mutation | test that goes RED |
|---|---|
| resolve the store with `_root()` | AC-1 |
| overwrite on conflict | the conflict case |
| restore without the aside step | AC-7 |
| `shutil.move` without `utime` | the AC-6 mtime assertion |

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| B2 (bridges into the cwd's store) | Store resolved from the memdir slug; mismatch refused; RED from root A on B's memdir | AC-1 |
| B4 (regeneration drops prose and hooks) | Relies on 26.1's id-keyed hooks, carried prose and content guard | AC-4 |
| S1 (git-tracked memdirs) | Preview reports `git_tracked`; `git mv`; stop for the user's commit | AC-2, AC-4, AC-7 |
| S2 (mtime) | Moves and rewrites preserve mtime; asserted | AC-4, AC-6 |
| S3 (aside inside the memdir) | Asides under `~/.refmatrix/backups/` | AC-7 |
| S4 (rollback overwrites edits) | Id-aware rollback | AC-7 |
| M7 (member count) | Counted against a full walk including dotfiles | AC-3 |
| Q2 verdict (report-only) | save-state prints the check and never moves | AC-8 |
| M9 (rebase on 3.7) | Header dependency | header |
