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

1. **AC-1: the target store comes from the memdir, never from the cwd (B2; r2 m2, m3, m8).**
   - **Memdir to store.** A non-absolute memdir argument is REJECTED first, before any
     normalisation, with exit 2 (r3 m10). `.absolute()` of a relative `memory`, run from the slug
     dir, would land under `projects/` and slip through. The accepted absolute path is passed
     unchanged to `_root_from_projects_slug` (`cli.py:113`). It is never `.resolve()`d, because
     resolving a symlinked memdir leaves `projects/` and the lookup returns `None`. The partition
     comes from the resolved root's own default.
   - **Bad input is a hard error.** A memdir path that does not lie under
     `~/.claude/projects/<slug>/` exits 2 and names the fix: "pass the `~/.claude/projects/<slug>/memory` path,
     not its symlink target or a relative path". This covers resolved symlink targets and relative
     paths. It never silently becomes `no store` (r2 m2).
   - **One default (r2 m3).** `--store-from-memdir` is THE default for every caller: CLI, MCP,
     plan-27 and 26.8. The resolved root is used, and the cwd is ignored.
     `--require-cwd-match` is the opt-in strict mode. In that mode the verb exits non-zero, naming
     both roots, when the cwd's store (`_root()`) differs.
   - **No store.** `no store` (file-only, bridge not run, said in the output) happens ONLY when a
     well-formed projects slug matches no root.
   - **One bridge parameter.** Every store write goes through `_sync_memory_dir(memdir, root=)`,
     a new parameter that is passed to that root's daemon. The MCP save-state bridge gets the same
     fix: `verbs.save_state(root=…)` → `finalize_save_state` passes its `root` to
     `_sync_memory_dir` (`handoff.py:435`) instead of resolving through `_root()` (r2 m8).
   - **Tests.** Each starts RED at HEAD:
     - (a) default mode, run from root A on root B's memdir: the rows land in B and none in A;
     - (b) `--require-cwd-match` in the same setup: refused, and no rows anywhere;
     - (c) a resolved symlink target outside `projects/`: exit 2 with the fix named;
     - (d) a relative path: exit 2;
     - (e) MCP `rmx_save_state` with `root=B`, called from a process whose cwd store is A: the
       bridge writes B.
   - **Mutations.** "Resolve before lookup" turns (c) into a silent `no store` and goes RED.
     "`_root()` in the bridge" turns (a) and (e) RED.
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
   - `prose_lines` and `prose_chars` carried from `MEMORY.md` (26.1 AC-5);
   - **`index: ok | refuse(<reason>)` (r2 s5).** The preview renders the would-be `MEMORY.md` in
     full, as it would look after the moves and with the marker set, so it uses the new renderer.
     It runs every 26.1 refusal check against that render: the prose budget share and the
     content-shrink guard. The rendered text is written to the backups dir as
     `preview-<slug>-<ts>.md` for review. It is never written into the memdir.

   `--only <folder>` restricts the plan to one folder (plan Q1).
3. **AC-3: the index check, then the backup, then anything else (r2 s5).**
   - **`--apply` refuses BEFORE the backup and before the first move** when the AC-2 render
     would refuse. It exits 4, names the reason (for example `prose 94% of budget`), and changes
     nothing. Fixing the cause (27.2a for viascope) comes first.
   - Test: a fixture whose prose is 94% of the budget. `--apply` exits 4 and the dir is
     byte-identical. Mutation: apply-then-render leaves an index of dead links, and the test goes
     RED.
   - **Then the backup:**
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
     owning repo. A tracked dir runs this sequence (r2 m5):
     1. the moves are staged;
     2. the index is written and staged;
     3. the marker is written and staged;
     4. the bridge runs, and its report is printed;
     5. the verb prints the staged summary and the exact commit command
        (`git -C <toplevel> commit -m '<message>' -- <paths>`). It never suggests `commit -a`.
        Any pre-existing dirt in that repo is named; `~/.claude` has 93 unstaged deletions under
        the gone `-enduris-cliquedb` dir;
     6. the verb exits 3 ("staged; awaiting your commit").

     The user commits. `--apply` in a tracked dir never leaves a delete-plus-untracked pair.
   - **Conflicts.** If the target exists with DIFFERENT bytes, the verb does not overwrite it. It
     lists the pair as a `conflict` and both files stay.
   - **Hooks.** No sidecar key rewrite is needed, because 26.1 keys hooks by id.
   - **Marker.** After the moves, `<memdir>/.memory-layout` is written (r2 s2). It records the
     ADR-0005 version, the date and the backup path. From then on, the new on-disk behaviours
     apply to this dir (26.1 `#marker-gate`).
   - **Index.** `MEMORY.md` is regenerated through `memory_index.write` (now marker-on), which
     carries prose (26.1 AC-5). It cannot refuse at this point, because AC-3 already ran the same
     checks on the same render. A refusal here is a bug: the verb reports it loudly and the
     rollback path applies.
5. **AC-5: the bridge runs through the resolved store's daemon.** The result includes the 26.2
   refresh counts, `duplicate_ids`, `mtype_normalised`, and the embed counts.
   - **One-time forced re-bridge of save-states (r3 m8).** `--apply` re-ingests EVERY save-state
     file in the dir, bypassing the hash gate for those paths only. 26.4's mtype rule therefore
     reaches unchanged mis-typed save-states too. `mtype_normalised` must list them.
6. **AC-6: recall proves it.** In the throwaway end-to-end test, after `--apply`:
   - `rmx memory recall "<phrase unique to a moved save-state>"`, run in the resolved root,
     returns it;
   - `rmx recall-state` shows the newest save-state by 26.1's ordering;
   - the mtimes of the moved files equal their pre-move values.

   `memory get` alone is not proof.
7. **AC-7: rollback is ONE per-id rule (S4; r2 s4).** `--rollback <tarball>` compares, per
   memory id, the current file (wherever it now lives) with the archive's copy:

   | current vs archive (same id) | action |
   |---|---|
   | same bytes | move it back to its archive path, keeping mtime (`os.replace`, or `git mv` in a tracked dir) |
   | different bytes (edited or re-saved after the backup) | KEEP the current file at its current path. Write the archive copy to `~/.refmatrix/backups/memory-organise/aside-<slug>-<ts>/<archive path>` (never inside the memdir, S3). Print one report line `kept current <path>; archive copy set aside at <aside path>`. `--prefer-archive <id>` swaps the two for that id. |
   | present only in the archive | restore it to its archive path |
   | present only now (new after the backup) | keep it, and list it |
   | same id at two paths now (a duplicate) | list it as a conflict; touch neither |

   - Non-memory files from the archive (`MEMORY.md`, the sidecar) are restored only when they are
     unchanged since apply. Otherwise they go to the aside dir, with a report line.
   - **The marker (r3 m6).** The archive predates the marker, so `.memory-layout` is "present
     only now". When the rollback restores the pre-organise state, the marker is MOVED to the
     aside dir. It is never kept in place, so the dir really returns to HEAD behaviour: no
     `savestates/` writes, HEAD's render and sidecar. The rollback test asserts
     `memory_layout.is_organised(memdir)` is False afterwards. Mutation: keep the marker, and the
     next save-state writes into `savestates/` of a flat dir (RED).
   - The index is then regenerated and the bridge re-run.
   - Test: after `--apply`, re-save a save-state, which writes `savestates/<id>.md`, and edit one
     feedback memory. Then roll back. Assert:
     - both edited files are still at their current paths with their new bytes;
     - their archive copies are in the aside dir;
     - every untouched file is back at its archive path;
     - `rmx recall-state` resumes from the RE-SAVED handoff.
   - Mutation: a path-keyed rollback restores the old top-level copy, recall-state resumes the
     old handoff, and the test goes RED.
8. **AC-8: check mode, report-only.**
   - `--check` exits non-zero when any file is out of place, a save-state is mis-typed, a
     duplicate id exists, `refresh_pending > 0`, or `index: refuse`. It changes nothing.
     `refresh_pending` is 26.2's bridge `--dry-run` stat, re-exported here (r2 m4).
   - `rmx save-state` prints a one-line `organise --check` summary but never moves a file (plan
     Q2, ch-bsd r1 verdict: report-only).
9. **AC-9: fail closed on a live store.** The verb never opens `Store()` itself.

## Files to Create / Modify {#files}

- Create `src/refmatrix/memory_organise.py`: plan, apply, rollback, check, store resolution.
- Modify `src/refmatrix/verbs.py`: the verb and its parity-map entry.
- Modify `src/refmatrix/cli.py`: the `memory organise` command; a `_sync_memory_dir(memdir,
  root=)` parameter.
- Modify `src/refmatrix/handoff.py` (`finalize_save_state`, `:435`) and `verbs.save_state`: pass
  `root` through to the bridge (r2 m8).
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

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s4 (rollback steps contradict; the test fails either way) | One per-id table: unchanged → restored; changed after backup → kept in place, archive copy set aside with a report line; same-id pairs listed; the test asserts the re-saved handoff wins | AC-7 |
| s5 (apply moves, then the index refuses) | The preview renders the index and runs every refusal check; `--apply` exits 4 before the backup and the first move; mutation | AC-2, AC-3, AC-4 |
| s2 (marker) | `--apply` writes `.memory-layout` | AC-4 |
| m2 (resolved or relative memdir means silent `no store`) | Hard error (exit 2) naming the fix; `.absolute()`, never `.resolve()`; mutation | AC-1 |
| m3 (one flag, two meanings) | `--store-from-memdir` is THE default everywhere; `--require-cwd-match` opt-in; both tested | AC-1 |
| m5 ("stops" undefined; `~/.claude` dirty) | Defined sequence ending in exit 3; exact commit command; never `commit -a`; pre-existing dirt named | AC-4 |
| m8 (MCP save-state bridge resolves through `_root()`) | `_sync_memory_dir(memdir, root=)` passed from `verbs.save_state` via `handoff.py:435`; test (e) | AC-1 |
| m4 (field of a later command) | `refresh_pending` comes from 26.2's bridge dry-run; re-exported | AC-8 |

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| m10 (`.absolute()` is a no-op on accepted input; relative input slips through) | Reject non-absolute first; pass unchanged; never `.resolve()` | AC-1 |
| m6 (rollback leaves `.memory-layout` behind) | Marker moved aside on rollback; `is_organised` False asserted; mutation | AC-7 |
| m8 (mtype rule reaches only re-ingested files) | `--apply` forces a one-time re-bridge of all save-states | AC-5 |
