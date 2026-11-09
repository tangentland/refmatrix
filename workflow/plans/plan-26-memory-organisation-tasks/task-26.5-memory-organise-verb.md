---
gmd: "0.1"
id: task-26.5-memory-organise-verb
title: "Task 26.5: rmx memory organise — preview, backed-up apply, rollback and check, as one verb"
tags: [task, plan-26, verb, migration, memory-dir, backup, rollback]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.5: the organise verb {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.2-bridge-move-safety]], [[task-26.3-savestate-subfolder]],
> [[task-26.4-savestate-mtype-normalisation]]

rel: part-of -> [[plan-26-memory-organisation]]
rel: reinforces -> [[feedback_dry_run_match_real_cost]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]
rel: depends-on -> [[task-26.2-bridge-move-safety]]

## Requirements {#requirements}

There is one migration mechanism and it is a verb: `rmx_memory_organise` in `verbs.py`, with
the CLI `rmx memory organise [MEMDIR]` and the MCP tool as thin adapters (the verb-parity test).
No hand-moves, here or in plan-27.

1. **AC-1: preview by default.** With no flag it moves nothing. It returns and prints a plan
   containing:
   - every move `(from, to)`, using `memory_layout.folder_for_type(metadata.type)` with a
     filename-prefix fallback;
   - `unplaceable` files: no type, an unknown type, or non-GMD, all listed by name;
   - `type_mismatch` files;
   - the save-state type rewrites (26.4 AC-3);
   - `duplicate_ids`;
   - the resolved store and partition the bridge would write to, or `no store` (plan-27 needs
     this);
   - whether `memdir` is a symlink, and its resolved target.
   `--only <folder>` restricts the plan to one folder (plan Q1).
2. **AC-2: the backup happens first, and failure stops the apply.** `--apply` writes
   `~/.refmatrix/backups/memory-organise/<slug>-<UTC ts>.tar.gz` containing every file under the
   RESOLVED memdir, including `MEMORY.md`, `.memory_hooks.json` and dotfiles. It verifies the
   member count against the walk. Only then does it move anything. If the backup fails, nothing
   moves and the exit is non-zero.
3. **AC-3: the moves are atomic and identity-safe.** Each move is an `os.replace` within the
   resolved memdir. A target that already exists with DIFFERENT bytes is not overwritten: it is
   listed as a `conflict` and both files stay. After the moves, `.memory_hooks.json` keys are
   rewritten from old to new relative paths so curated hooks survive. `MEMORY.md` is regenerated
   through `memory_index.write`, and its curated hooks are preserved (the existing
   `test_memory_index` idempotence holds).
4. **AC-4: the bridge runs through the daemon.** `--apply` ends with `_sync_memory_dir`. The
   report includes the 26.2 refresh counts. The verb returns the bridge's `duplicate_ids`,
   `mtype_normalised` and embed counts.
5. **AC-5: recall proves it.** In the throwaway end-to-end test, after `--apply`,
   `rmx memory recall "<phrase unique to a moved save-state>"` returns that memory and
   `rmx recall-state` shows the newest save-state from `savestates/`. A `memory get` alone is not
   accepted as proof.
6. **AC-6: rollback.** `--rollback <tarball>` restores the memdir to the archive's state. Files
   created after the backup are moved aside to `.organise-rollback-<ts>/`, never deleted. Then it
   re-runs the bridge. Afterwards recall still finds the AC-5 phrase (identity is the id, so
   nothing re-keys).
7. **AC-7: check mode.** `--check` exits non-zero when any file is out of place, a save-state is
   mis-typed, or a duplicate id exists. It changes nothing. `rmx save-state` prints its one-line
   summary (plan Q2). If the user accepts Q2, save-state files unambiguous strays with the same
   code path as `--apply` on only those files, and backs them up first.
8. **AC-8: fail closed on a live store.** The verb never opens `Store()` itself. All store work
   goes through `_sync_memory_dir` (daemon op, or in-process only when there is no daemon, per
   `require_daemon`).

## Files to Create / Modify {#files}

- Create `src/refmatrix/memory_organise.py` (plan, apply, rollback, check).
- Modify `src/refmatrix/verbs.py` (the verb and the parity map).
- Modify `src/refmatrix/cli.py` (the `memory organise` command).
- Modify `src/refmatrix/mcp.py` if the tool table is not generated from verbs.
- Regenerate the CLI tree doc if one is generated
  ([[feedback_family_list_misses_generated_checks]]).
- Create `tests/test_memory_organise.py`.

## Test Strategy {#test-strategy}

The end-to-end test uses a short `mkdtemp()` root holding `HOME/.claude/projects/<slug>/memory`
(a refmatrix-shaped flat dir with 2 feedback, 2 project, 3 savestates and 1 non-GMD file), a
throwaway project with its own daemon, and the real CLI plus the MCP verb. Cases:
- a symlinked memdir (viascope's shape): the backup and the moves operate on the target;
- a conflict;
- a failed backup (make the backup dir read-only): nothing moves;
- the rollback round trip.

Mutation checks: skip the backup verification and the failed-backup case goes RED. Overwrite on
conflict and the conflict case goes RED.
