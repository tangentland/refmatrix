---
gmd: "0.1"
id: task-26.5-memory-organise-verb
title: "Task 26.5: rmx memory organise — memdir-resolved store, preview, backed-up apply (git mv where tracked), id-aware rollback, check"
tags: [task, plan-26, verb, migration, memory-dir, backup, rollback, git]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-13
---

# Task 26.5: the organise verb {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.1-layout-module-and-index-walk]], [[task-26.2-bridge-move-safety]],
> [[task-26.3-savestate-subfolder]], [[task-26.4-savestate-mtype-normalisation]]. Rebase on task
> 3.7's verb changes ([[plan-26-memory-organisation#overlap-37]]). Since rev 6 (2026-11-13):
> [[task-bug216-rule-docs-in-graph]] merged (bug-220's reroute sits on its walker,
> [[#bug220-route]]); bug-208 is fixed inside this task before the marker writer
> ([[#pre-bug208]]).

rel: part-of -> [[plan-26-memory-organisation]]
rel: reinforces -> [[feedback_dry_run_match_real_cost]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]
rel: reinforces -> [[feedback_store_calls_via_daemon]]
rel: depends-on -> [[task-26.2-bridge-move-safety]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]

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
   - `moved_legacy` projected over THIS plan's moves (r5 s1): the rows, other than a file's id
     row, whose resolved `source_path` equals a planned move's from-path (26.2 AC-1b). Read via
     the resolved store's daemon; `no store` reports `n/a`;
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
     reaches unchanged mis-typed save-states too. `mtype_normalised` must list them. The result
     reports re-ingested rows split into `moved` / `stale_before` / `forced` (26.2 AC-3; r4 s3),
     plus `moved_legacy` (26.2 AC-1b; r5 s1), which must equal the preview's projected count.
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
   - **Index after rollback (r4 m1).**
     - If the archive's `MEMORY.md` was restored (unchanged since apply), the index is NOT
       regenerated; the restored file is final.
     - Otherwise the index is regenerated BEFORE the marker is moved aside, still with the
       marker-on renderer. Carried prose therefore survives. A marker-off regeneration would be
       HEAD's prose-dropping render.
     - Then the marker is moved aside, and the bridge is re-run.
   - The fixture includes one hand-written prose line in `MEMORY.md`. The test asserts that the
     prose line is in the live `MEMORY.md` after the rollback.
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
     `refresh_pending` is 26.2's bridge `--dry-run` stat, re-exported here (r2 m4). It
     includes the `moved_legacy` term (26.2 AC-1b; r5 s1), and `--check` prints it on its own
     line, so a legacy row left on a dead path keeps `--check` non-zero.
   - Test (r5 s1): a marker-on fixture with a legacy row on `a/x.md` (26.2's AC-1b fixture), the
     file moved by hand to `b/x.md` with no bridge. `--check` exits non-zero and reports
     `moved_legacy: 1`. After one bridge it exits 0. At HEAD there is no such term and the
     legacy row is invisible (RED).
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
- Rev 6 (2026-11-13):
  - Modify `src/refmatrix/handoff.py` (`compose_save_state`, ~:428-483): bug-208's atomic write,
    its error text and the `created:` source ([[#pre-bug208]]). Extend
    `tests/test_savestate_subfolder.py`; register the part-way-failure monkeypatch in
    `workflow/test_mock_registry.md`.
  - Modify `src/refmatrix/memory_layout.py`: `memdir_of(path)`, the one memdir resolver shared by
    R-264a and bug-220 ([[#bug220-route]]).
  - Modify `src/refmatrix/ingest_gmd.py` (`collect_gmd_files`, `ingest_gmd_paths`: collect the
    `rerouted` groups) and `cli.py`:
    - `ingest-gmd` keeps each target's as-given form;
    - the root group `main` opens the invocation and registers the drain with
      `ctx.call_on_close`. The drain prints the five R-220d counts and sets the exit code.
      `_store()` / `_store_rw()` register their Store on the context object, and the drain's
      same-store leg reuses it (rev 11, x2, x4);
    - a daemon route prints the counts and `job_id`s from the op result;
    - prestage gets its `rerouted` line.

    Create `src/refmatrix/memory_reroute.py` (queue and drain, R-220c) and
    `tests/test_ingest_gmd_memdir_route.py` (rev 10).
  - Modify `src/refmatrix/daemon.py`:
    - the op/job boundaries (`Daemon._handle`'s OPS dispatch, `_run_detached_job`, the
      `ingest_gmd_start` / `ingest_path_start` runners, the `flush_queue_async` runner thread,
      the watcher flush iteration) open `memory_reroute.invocation()` and drain it in
      `try/finally`. Job runners flip to `done` after their drain. No drain at a lock yield or
      release (rev 11, x1);
    - the internal same-store memory-job start that takes the parent job object, with its
      single-use guard exemption;
    - `_op_ingest_gmd_start` ignores parent/exempt keys;
    - `call` raises `ReplyTimeout` after the send (rev 10, w1, w2, w4).
  - Modify `src/refmatrix/ingest.py`: `_ingest_path_inner` needs no dispatch code, because
    `ingest_gmd_paths` queues (rev 10). Its `ingest_gmd_paths` fallback (`ingest.py:1356-1368`
    at `4b4b96e`) skips memdir files through `memdir_of` and counts and names its own per-file
    failures, with no bare `except: pass` (rev 9, u2). Modify `src/refmatrix/sync.py` only to pass
    the `rerouted` result up.
  - Only if R-202a finds bug-202's files: `ingest-gmd --as-memory --force-rebridge <file>` on the
    single-file bridge ([[#r-202b]]); the live restore is 27.5's.
  - Create `workflow/review-output/26.5-bug202-existence.log` ([[#bug202-restore]]).

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

## Revision round 4 (2026-11-09) {#rev-round-4}

Answers [[bsd-plan26-27-spec-review-r4-f89e640]].

| finding | change | anchor |
|---|---|---|
| m1 (rollback regenerated the index marker-off and dropped prose) | Skip the rebuild when the archive's `MEMORY.md` is restored; otherwise rebuild before the marker is moved aside; prose line asserted | AC-7 |
| s3 (stats split) | `moved` / `stale_before` / `forced` reported | AC-5 |

## Implementation notes (r5) {#impl-notes-r5}

- **m5, the rollback restore branch.** AC-7 restores the archive's `MEMORY.md` only when it is
  unchanged since apply AND no file was kept at a moved path (no "different bytes → KEEP" row
  fired for a file whose current path differs from its archive path). Otherwise the restored
  index would link the archive path of a file that still lives at `feedback/x.md`, so the index
  is regenerated (marker-on, before the marker goes aside), as in AC-7's second branch. The
  AC-7 test already edits a feedback memory, so it takes the regenerate branch; it also asserts
  every link in the post-rollback `MEMORY.md` resolves to a file. Raised by
  [[bsd-plan26-27-spec-review-r5-3ded49e]].

## Revision round 5 (2026-11-09) {#rev-round-5}

Answers [[bsd-plan26-27-spec-review-r5-3ded49e]].

rel: derives-from -> [[bsd-plan26-27-spec-review-r5-3ded49e]]

| finding | change | anchor |
|---|---|---|
| s1 (legacy rows on the old path uncounted; `--check` clean over them) | Preview projects `moved_legacy`; apply reports it and must match; `--check` includes it, with a RED case | AC-2, AC-5, AC-8 |
| m5 (restore branch can restore a dead link) | Restore only when no file was kept at a moved path; else regenerate | [[#impl-notes-r5]] |

## Inherited from ch-bsd 26.1 r4 (2026-11-10) {#inherit-261-r4}

rel: depends-on -> [[task-26.3-savestate-subfolder#inherit-moved-derived]]

The organiser's moves rely on 26.3's id fallback for derived hooks of moved files; 26.5's move
tests include a no-sidecar dir with a cut index hook and assert no `…`-ended sidecar value.
{#inherit-moved-derived-265}

## Inherited from 26.3 GREEN (2026-11-10) {#inherit-263-green}

rel: derives-from -> [[impl-task-26.3-savestate-subfolder]]

**Rollback moves `savestates/` back.** A dir whose marker is moved aside but which still holds
`savestates/<id>.md` would make a fresh top-level save look "shadowed" by the stale subfolder
copy (26.3's walk rule), so `recall-state` would resume from the older copy. **AC:** after
`memory organise --rollback`, no `savestates/` folder remains (its files are back at the top
level, byte-identical), and a following save + `recall-state` reads the new save. Mutation:
rollback leaves `savestates/` in place — killed. {#inherit-rollback-savestates}

## Inherited from ch-bsd 26.4 r1 (2026-11-13) {#inherit-264-r1}

[[bsd-task-26.4-r1-savestate-mtype-1caf3df#b-1]] found two 26.4 hand-offs to this task with no
acceptance criterion here; they are anchored now (lead decision, as the user would: anchor the
deferral rather than widen 26.4).

rel: derives-from -> [[bsd-task-26.4-r1-savestate-mtype-1caf3df]]

- **R-264a (bug-213, file/subdir targets).** `rmx ingest-gmd --as-memory <target>` where the target is
  a FILE or a SUBDIR inside a memory dir resolves the memory dir first — the nearest ancestor with a
  `.memory-layout` marker, else the `~/.claude/projects/<slug>/memory` shape, else ONE loud refusal
  naming the target — and applies the save-state predicate relative to that memory dir, exactly as a
  memdir bridge would. {#r-264a}
- **R-264b (sticky rows).** Rows already mis-typed by a pre-fix file/subdir ingest are repaired:
  `organise --apply` (and the forced re-bridge) re-evaluate the stored mtype of every memory row
  whose file is a `savestate_*` stem OUTSIDE the top level and `savestates/`, bypassing the
  content-hash gate for those rows only; repairs are counted and printed. {#r-264b}
- **R-264c (misfiled stems).** `organise --check` names every `savestate_*` stem outside the top level
  and `savestates/` as misfiled, whatever its type (`project/savestate_x.md` typed project included).
  {#r-264c}
- **R-264d (sequence).** In AC-4's apply sequence, 26.4's `normalise_savestate_types(apply=True)`
  runs after the backup and before the forced re-bridge, and the backup covers the files it rewrites.
  {#r-264d}
- **AC-264.** (a) RED both directions: a file target and a subdir target holding a misfiled
  `feedback/savestate_x.md` (typed project) store `project`; a real `savestates/` file via a subdir
  target stores `session/recall-state`; an unresolvable target refuses in one `Error:` line. (b) A
  store holding the sticky wrong row (built at 26.4's head) is repaired by `organise --apply`; a
  second run repairs nothing. (c) `--check` lists `project/savestate_x.md`. (d) The apply log shows
  the rewrite between backup and bridge. (e) 26.4's s-1 pins ride here: symlink refusal, a bare file
  with no frontmatter (error entry, never a silent skip), a file with no type line (insert happens,
  `error` stays None only when it did). {#ac-264}

## Revision round 6 (2026-11-13): plan-review folds {#rev-round-6}

Answers [[plan-review-2026-11-13#lead]] rows L9 and L37, spec gaps G4 and G15
([[plan-review-2026-11-13#spec-gaps]]). Evidence: `workflow/review-output/pop-2026-11-13/contra-a.md`
Ca-5 and Ca-6, [[bsd-pop-r1-c56782f#m4]], and the bug-202, bug-208 and bug-220 rows of
`workflow/bug_registry.md`. Status is unchanged (`pending`); the lead sets `approved` after a clean
ch-bsd round.

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: derives-from -> [[bsd-pop-r1-c56782f]]

| row | change | anchor |
|---|---|---|
| L9 / Ca-5 (bug-208 has no AC anywhere) | bug-208 is a precondition inside this task, with its own requirements and AC, recorded GREEN before AC-4's marker write | [[#pre-bug208]] |
| L9 / Ca-6, bsd-pop-r1 M4 (bug-202's restore points at files nobody found) | Existence check first. If found: restore with an anchor-set check. If not: bug-202's restore note closes with the reason | [[#bug202-restore]] |
| L37 / X1 (bug-220, doc walk mints `kind=doc` memories) | Classification by location, route never refuse, one resolver shared with R-264a; own requirement and AC | [[#bug220-route]] |
| Q8 open (brief rule) | Lines that change under Q8 b named | [[#q8-b]] |

## Precondition: bug-208, the atomic save-state write (2026-11-13) {#pre-bug208}

rel: derives-from -> [[bsd-task-26.3-r2-remedy-39bfc4a]]

bug-208 ([[bsd-task-26.3-r2-remedy-39bfc4a#s-1]]): `handoff.compose_save_state` writes
`savestates/<id>.md` with `Path.write_text` (`handoff.py:471` at `1cf3b9f`), which truncates
first. A write that fails part-way (ENOSPC, EIO) leaves a truncated folder copy with a fresh
mtime. The walk ranks that copy newest and skips the intact top-level copy that the error message
says was kept. The row's status reads "fix before 26.5 ships the marker writer": no live dir
takes the `savestates/` branch until this task's `--apply` writes `.memory-layout`. So AC-208 is
RED and GREEN before AC-4's marker write is recorded GREEN, and the commit order shows it.
{#pre-bug208-why}

- **R-208a (s-1) atomic write.** The save-state is written to a temp file in `target.parent` and
  `os.replace`d onto `target`, keeping the file mode (impression `imp-atomic-write-changes-mode`).
  It calls the existing atomic-write helper (`memory_index._atomic_write_text`, bug-199), moved to
  one shared place if needed, never a second copy ([[feedback_converge_repeated_shapes]]). That
  helper's temp is `tempfile.mkstemp(prefix=f"{name}.", suffix=".tmp")`, and the helper unlinks it
  on failure. A temp left by a hard crash ends in `.tmp`, not `.md`, so the memory walk never reads
  it as a memory (rev 7, bsd-spec-t2 m2). {#r-208a}
- **R-208b (m-2) the error tells the truth.** When the legacy top-level file was moved into
  `savestates/` before the write failed, the error says so (the legacy file was moved to
  `savestates/<id>.md` with its content intact). The CLI prints it, and the MCP verb raises it as a
  `VerbError`. {#r-208b}
- **R-208c (m-1) `created:` from the kept copy.** In a flat dir that holds `savestates/`, the
  writer takes `created:` from the copy the walk keeps: the `savestate_pair` lookup is no longer
  guarded by the marker (`handoff.py:432`). {#r-208c}
- **R-208d (m-3) killing tests** for the three remedy behaviours that are unpinned at HEAD. Each
  message branch of the newer-copy removal gets its own test. The `SaveStateWriteError` →
  `VerbError` conversion is tested through the MCP verb, not only through the CLI. The
  `remove_failed` catch is tested with the unlink made to fail. {#r-208d}
- **AC-208.** Each part starts RED at HEAD, in task 23.0's sandbox: {#ac-208}
  - (a) **Part-way failure.** A write that raises after some bytes are written (the monkeypatch
    is registered in the mock registry):
    - fresh-top pair: `rmx recall-state` returns the kept top-level copy byte-identical, and no
      truncated `savestates/<id>.md` exists;
    - fresh-folder pair: the folder copy is byte-identical to its pre-save bytes.
  - (b) The error after a moved-legacy failure names the move (R-208b), on the CLI and on the MCP
    verb.
  - (c) A flat fresh-folder pair: the next save's `created:` equals the kept copy's (R-208c).
  - (d) The three R-208d tests.
  - Mutations, each killed:
    - an in-place `write_text` kills (a);
    - dropping the move clause kills (b);
    - restoring the `if organised` guard kills (c);
    - letting the raw `OSError` through kills (d)'s MCP leg;
    - collapsing the newer-copy removal's two message branches into one kills (d)'s message
      tests (rev 7, m3);
    - deleting the `remove_failed` catch, so the failed unlink raises, kills (d)'s unlink test
      (rev 7, m3).
- Rows R-208b and R-208c are MEH findings that the bug-208 row names in its symptom but not in its
  fix column. They ride here because they touch the same function (kept by lead ruling
  2026-11-13, T2-O3; [[#lead-rulings-2026-11-13]]).

## bug-202's two anchor sets: check existence first (2026-11-13) {#bug202-restore}

The bug-202 row says two memories lost ALL their anchors: `guardrail-coordinator-lane-dispatch`
and `guardrail-two-writers-one-logical-db`. It says restoring them "needs a forced re-bridge
(26.5 AC-5's force input)". AC-5's force input covers save-states only (Ca-6).
[[bsd-pop-r1-c56782f#m4]] found no file with either id under `~/.claude/projects`,
`~/claude_tools` or `~/github`. The rows themselves still exist in refmatrix's store: on
2026-11-13, `rmx context guardrail-coordinator-lane-dispatch` returned its body. The only
`guardrail-*` memory files on disk are in cliquedb's memdir, and neither id is among them. That
memdir's `MEMORY-process.md` still links both ids at
`~/enduris/cliquedb/.claude/projects/-Users-tholley-enduris-cliquedb/memory/guardrails/<id>.md`, a
path that no longer exists (read 2026-11-13). {#bug202-why}

- **R-202a: existence check, read-only, run first.** At the start of this task, for each id: {#r-202a}
  - read the row through refmatrix's daemon (`rmx memory get <id>`) and record its
    `metadata.source_path`;
  - test that path as written and as resolved;
  - if it is absent, run a scoped search for a GMD file whose frontmatter `id` equals the id. The
    search covers `~/.claude/projects/*/memory` and the repo roots in
    [[plan-27-memory-fleet-rollout#survey]], skips `_frameworks_and_libraries`, and never starts
    from `/` ([[feedback_never_search_from_root]]).

  Every command and result goes to `workflow/review-output/26.5-bug202-existence.log`.
- **R-202b: found → the restore moves to 27.5 (rev 7, lead ruling on bsd-spec-t2 s4).** This task
  runs no live restore and no organise apply for bug-202. If R-202a finds the files, 26.5 builds
  only the single-file force: `rmx ingest-gmd --as-memory --force-rebridge <file>` passes the named
  file through AC-5's hash-gate bypass on the bridge's single-file path (R-264a resolution), counts
  it under `forced` and names it. It is tested in task 23.0's sandbox: an unchanged file with its
  anchor concepts removed regains them, by name and count (RED without the flag). The live
  restore, of those two named files only, is
  [[task-27.5-cliquedb-at-session-boundary#r-202b-live]]. If R-202c applies, nothing is built.
  {#r-202b}
- **R-202c: not found → no restore.** The bug-202 row's restore note is closed with the reason:
  the files are gone (see the R-202a log); the rows keep their bodies; and the anchors cannot be
  rebuilt from a file that does not exist. The rows are not forgotten
  ([[feedback_decay_never_loses_knowledge]]). {#r-202c}
- **AC-202.** {#ac-202}
  - The log exists. For each id it names the `source_path`, the existence result and the branch
    taken.
  - For R-202b, the sandbox anchor-set test passes; the live check is 27.5's.
  - For R-202c, the bug-202 row's note carries the reason and the log path.

## bug-220: a memory file is classified by where it lives (2026-11-13; rev 7) {#bug220-route}

rel: depends-on -> [[task-bug216-rule-docs-in-graph#r2]]

bug-220: a doc walk lands every memory file as `kind=doc` in the project partition. The doc walk
can be `rmx ingest-gmd <memdir>` without `--as-memory`, or any walk whose root covers a memory
dir. The result is a second node per memory, of the wrong kind, invisible to recall's kind
filter, with its `rel:` edges bound to the twin. The user (2026-11-13): "we should have a way to
bridge memories into the graph as they are sometimes relevant". So the fix routes the file and
never refuses it ([[plan-review-2026-11-13#x1]]). L37 folds it here because this task owns the
memdir resolver (R-264a) and the marker reader. Rev 7 answers [[bsd-spec-t2-b5fe2d3]] s1, s2, s3,
m3, m6 and m7. {#bug220-why}

- **R-220a: one memdir resolver, both path forms (rev 7, s1).**
  `memory_layout.memdir_of(path, *, as_given=None) -> MemdirRef | None`. `as_given` is the path as
  the caller received it, before any `.resolve()`. It returns the memdir and its UNRESOLVED form,
  found by the first of these that matches: {#r-220a}
  - the `~/.claude/projects/<slug>/memory` shape on the as-given path;
  - the nearest ancestor that holds a `.memory-layout` marker, on either form, read through
    `is_organised` (so a malformed marker is still a hard error, ADR-0005 `#marker-encoding`);
  - the resolved path matched back to a `~/.claude/projects/*/memory` symlink whose target is that
    memdir (one listing of `~/.claude/projects` per walk). This is how a walk that only sees
    resolved paths (sync, the watcher, `ingest-gmd`'s `resolved = [Path(t).resolve() …]`) still
    finds viascope's symlinked memdir under its slug;
  - else `None`.

  Whichever branch matched, the marker branch included, the memdir's UNRESOLVED form comes from
  the as-given path when there is one, else from the symlink map (rev 8, bsd-spec-t2-r2 n1). The
  CLI keeps each target's as-given form beside its resolved form and passes it in. The
  unresolved form is the only one ever given to the store resolver (ADR-0005
  `#store-resolution`: never `.resolve()`). A memdir with no unresolved form (no as-given
  projects path, no symlink to it) has no slug, so it is no-store (R-220c). R-264a's resolver IS this function plus its loud
  refusal on `None`. There is no second copy.
- **R-220b: classification follows location; collect, never ingest in place.** In
  `collect_gmd_files` / `ingest_gmd_paths` with `as_memory=False`, every file whose `memdir_of`
  is not `None` is taken out of the doc set and COLLECTED, grouped by memdir, into the call's
  `rerouted` result. It is never ingested inside the doc ingest. No caller flag can mint a
  `kind=doc` row for such a file. The memory-side exclusions apply when the group is bridged
  (`iter_memory_files`: dot-dirs, dotfiles, `MEMORY.md`, `README.md`).
  `ingest-gmd --prestage` (without `--as-memory`) uses the same walk. Its result and its CLI line
  carry a `rerouted` count with the names, in the same shape as bug-216 R6b's `ignored` /
  `ignored_paths`. Prestage dispatches nothing (rev 8, n4). {#r-220b}
- **R-220c: queue during the walk, drain at one place per context, outside the writer lock,
  never waiting on another store (rev 7 s3; rev 8 t1; rev 10 w1, lead rulings).** The `rerouted`
  groups are dispatched only AFTER the walking store's ingest has returned and its writer lock
  (`d._store_lock`) is released. Each dispatch is a separate op, never nested under a held lock
  (the bug-085 class), and no dispatch waits for another store's ingest. {#r-220c}
  - **One queue per invocation, drained at the op/job boundary (rev 10 w1; rev 11 x1-x4, lead
    rulings; replaces rev 9's per-route dispatcher list and rev 10's lock-exit drain).** No route
    dispatches by itself, so a route list can never go stale:
    - **Queue.** `ingest_gmd_paths` (with `as_memory=False`) splits out the memdir files and
      calls `memory_reroute.enqueue(groups, *, walking_root)` as soon as they are collected,
      before the doc ingest, so a later raise cannot lose them. It never dispatches.
      `collect_gmd_files` drops nothing: prestage counts its `rerouted` files by `memdir_of`.
      Every caller of `ingest_gmd_paths` is covered by that one call.
    - **Per invocation, never global (x1).** The queue lives in a `contextvar`-scoped context
      that the op or job boundary opens (`memory_reroute.invocation()`). `enqueue` with no open
      invocation RAISES loudly, naming the caller. There is no silent process-wide queue, and an
      unwrapped new route fails at runtime.
    - **Daemon boundaries (x1).** Each boundary opens the invocation and drains it in
      `try/finally`, in the thread where the work runs. `contextvars` do not cross into
      `bg_pool` or new threads, so each threaded body opens its own. The boundaries are:
      - the request handler that runs every `OPS` entry (`Daemon._handle` → `OPS.get(op)`,
        `daemon.py:3332`), for synchronous ops;
      - `_run_detached_job`, plus the `ingest_gmd_start` and `ingest_path_start` runners, for
        detached jobs;
      - the `flush_queue_async` runner thread (`rmxd-async-flush`, `daemon.py:3536`);
      - each flush iteration of the daemon's watcher loop (`Daemon._start_watcher`,
        `daemon.py:3095`).

      The drain NEVER runs at a lock yield or release. `d._store_lock` is a `_FairLock` with no
      depth or owner, and `ingest_gmd_paths` yields it between files
      (`_partition_keeping_yield`, `RMX_INGEST_YIELD_EVERY`). The drain result goes on that op's
      reply, that job's record and the daemon log. Because the drain sits in `finally`, an op
      that raises after its enqueue still dispatches and counts its groups, and the error stays
      loud.
    - **CLI boundary (x2).** The root click group (`main`, `cli.py:859`) opens the invocation in
      its callback and registers the drain with `ctx.call_on_close`. Click runs that on every
      exit: normal return, `ClickException`, `ctx.exit(n)`, `sys.exit(n)`, and under `CliRunner`.
      The drain prints the R-220d counts on stderr, and on `rerouted_failed` /
      `rerouted_unconfirmed` makes the exit non-zero unless the command is already exiting
      non-zero. In-process routes are covered by construction: `_sync_in_process` (all three
      branches), the standalone `rmx watch` flush, `rmx ingest`, `tldr-warm` / `graphify-warm`
      (`cli._ingest`) and `rmx ingest-gmd`. The standalone `rmx watch` loop may never exit, so,
      like the daemon watcher, it also opens and drains an invocation for each flush iteration.
    - **The CLI reuses its own Store (x4).** A Store the invocation opens (`_store()` /
      `_store_rw()`) is registered on the click context object. The drain's same-store leg uses
      THAT Store. It never opens a second Store on the same root in one process (the bug-105
      class). The invocation context closes the registered Store after the drain (the drain's
      callback runs first). A CLI route that only talked to a daemon opened no Store and enqueued
      nothing, so its queue is empty by construction.
    - **The job reads `done` only after its own drain (rev 9 v1, kept).** A job's runner flips its
      record to `done` only after its boundary drain has written the result onto the record. The
      drain is synchronous and never waits on another store, so this stays bounded. A
      `--detach` / `--progress` client, or `ingest-status`, that sees `done` also sees the
      reroute result.
    - **Informative only.** The routes that reach `ingest_gmd_paths` at `4b4b96e` are tabled in
      [[#reroute-routes]]. The table is not a dispatcher list. AC-220 (n) runs every row.
  - **The library module.** `src/refmatrix/memory_reroute.py` holds `invocation()`, `enqueue`,
    `drain(*, same_store) -> counts`, the store resolution (below), the held/no-store branches
    and the cross-store leg. The boundary supplies the same-store leg (`same_store`): the daemon
    passes its internal memory-job start (below), and the CLI passes
    `_ingest_gmd_in_process(<the invocation's open Store>, …, as_memory=True)`. The library never
    imports `cli.py`.
  - **The `ingest_path` fallback (rev 9, u2).** When `ingest_gmd_paths` raises inside
    `_ingest_path_inner`, the existing fallback (`ingest.py:1356-1368` at `4b4b96e`) upserts every
    GMD path as `kind=doc`. It now skips every file for which `memdir_of` is not `None` (no twin is
    minted), and it keeps the `rerouted` groups collected before the raise. Its per-file failures
    are counted and named on the result, and its bare `except: pass` goes
    ([[CLAUDE#no-silent-failures]]).
  - **The store is the memdir's own** (lead ruling T2-O1). It is resolved from the memdir's
    unresolved form (R-220a) by a NON-raising variant of AC-1's resolver, which returns
    `store | no_store | held`. AC-1's raising resolver stays the organise verb's.
  - **Cross-store (memdir → store B, the walk wrote A).** One detached job per memdir: the
    `ingest_gmd_start` op on B's daemon (`daemon.py:3858`), with `as_memory=True` and
    `partition` = B's memory partition, taken from B's resolved root's own default (AC-1; rev 9,
    v3: without it the rows land in B's bound code partition). It uses `daemon.call(…,
    retries=0)` with a short timeout (a named constant, at most 2 s). B's `job_id` goes on A's
    result and op record.
    - **The mechanism (rev 10, w4).** `daemon.call` raises a typed `ReplyTimeout` when the request
      was SENT and the reply did not arrive in time. Connect and send failures keep their existing
      exceptions. `ReplyTimeout` subclasses the exception `daemon.call` raises for a timeout
      today, so every existing `except` clause behaves as before. The helper maps `ReplyTimeout`
      to `rerouted_unconfirmed` and everything else to `rerouted_failed`.
    - A failure BEFORE the request is sent (no socket, refused, connect timeout) is
      `rerouted_failed`.
    - A timeout AFTER the request is sent, waiting for the start reply, is `rerouted_unconfirmed`:
      B may have registered the job (rev 9, v2). It is named with the memdir, B's root and B's
      `job_id` when the reply carried one, plus the text "job may be running on B; check
      `rmx ingest-status` in B's root". The helper tells the two apart by the exception type
      (`ReplyTimeout`), never by guessing. Nothing waits for B's job: there is no
    synchronous `ingest_gmd` call, no `ingest_gmd_status` polling and no
    `_bridge_wait_for_active_job`. The same rule holds on every route, CLI included. B's own job
    runs the full `--as-memory` body: drain, index regeneration, marker-gated writes. This
    replaces rev 6's `_sync_memory_dir(memdir, root=B)` route, which waited on B
    (bsd-spec-t2-r2 t1); the T2-O1 ruling (B is the memdir's own store) stands.
  - **Same store (memdir → A).** The group goes through A's FULL `--as-memory` path as its own
    job: at the parent's boundary, so after the parent's doc ingest has returned, and before the
    parent job flips to `done` (rev 10 w3; rev 11 x1). That includes the memory-vector drain and the index regeneration,
    which `daemon.py:3790`/`:3805` gate on `args.get("as_memory")` (bug-065: without the drain,
    rows are durable but invisible to recall). On the CLI's no-daemon route it is
    `_ingest_gmd_in_process(…, as_memory=True)`, the CLI's own store, as today.
  - **The daemon's same-store start is internal (rev 10, w2; lead ruling).** In the daemon, the
    drain starts the memory job by an in-process FUNCTION CALL into the job runner (the same body
    `_op_ingest_gmd_start` registers), passing the parent job OBJECT. It is never an OPS socket
    op, and never an `args` key.
    - The parent job object carries a single-use exemption from A's single-active-ingest guard.
      It applies only after the parent's doc ingest has returned: it is armed at the parent's
      boundary drain, never before (rev 11, x1). The call consumes it, and a second use is
      refused.
    - Nothing a socket client sends can reach the exemption: `_op_ingest_gmd_start` ignores any
      parent or exempt key and applies the guard as today.
    - A drain with no parent job (an op that runs no job) has no exemption. If another job is
      active, the group is `rerouted_failed` with the reason.
  - **B absent, busy or refusing.** This is never a silent drop ([[CLAUDE#no-silent-failures]]):
    - A's ingest still completes and its result stands;
    - each such memdir is counted under `rerouted_failed` and named with B's root and the reason:
      `ingest already active` (busy), the refusal text, or "no daemon for <B root>: start B's
      daemon (`rmx daemon start`)" (absent, rev 8, n5);
    - on the CLI this goes to stderr and the exit is non-zero after A's result is printed. A
      `rerouted_unconfirmed` group is printed the same way, and also makes the exit non-zero,
      because its outcome is unknown;
    - in the daemon it goes onto the op record and the daemon log.
    - No route ever opens B's store in-process, CLI included (store access routes through
      daemons, rev 8, n5). The CLI's OWN store keeps today's no-daemon behaviour. The memdir's own
      bridge (SessionStart, save-state) is the next route for a failed group.
    - A same-store job that cannot start because A already has an active ingest is counted the
      same way, with the reason.
  - **No store.** A well-formed slug that matches no root, or a marker dir with no slug form, is
    file-only (ADR-0005 `#store-resolution`, amended 2026-11-13 for this walk only). Its files are
    taken out of the doc set, ingested nowhere, and counted and named as `rerouted_no_store` with
    the fix text. The walk continues.
  - **The home memdir is held (rev 7, m7).** A memdir whose slug maps to HOME's `~/.refmatrix`
    (`-Users-tholley`, the hub's global store) is NOT dispatched. It is counted and named as
    `rerouted_held` with the reason "plan-27 Q4: what the home dir bridges into is unchanged until
    27.1 reports" ([[plan-27-memory-fleet-rollout#open-questions]]). 27.1's answer lifts the hold.
  - **The calling store's own twin.** A `kind=doc` row in the WALKING store at a rerouted path
    (left by an earlier doc walk) is purged by the walking store's ingest with the existing purge
    (`ingest_gmd.py:1376`), on every branch: same-store, cross-store, no-store, held and failed.
- **R-220d: counted and named.** The result carries `rerouted_to_memory`, `rerouted_no_store`,
  `rerouted_held`, `rerouted_failed` and `rerouted_unconfirmed` (rev 9), each listing its files or memdirs (the first 20, plus
  the count). The CLI prints them. A daemon walk records them on its op record. {#r-220d}
- **R-220e: after bug-216's prune, never before.** The reroute runs AFTER `should_ignore`
  ([[task-bug216-rule-docs-in-graph#r2]]). A path the doc walk prunes, such as a dot-dir, is never
  reached and so is never rerouted. bug-216's X1 pins stay green: {#r-220e}
  - no entity under a dot-dir on a doc route;
  - `.claude/PROJECT_PROFILE.md` lands once, as `kind=doc`;
  - a memdir under `.claude` still lands as `kind=memory` through the bridge.
- **Every dir (rev 7, s2).** The reroute is store-side and is not marker-gated. The only file
  write it can cause is the memory path's `MEMORY.md` regeneration in an organised dir, and that
  write is already marker-gated. ADR-0005 `#marker` lists the reroute among the every-dir
  behaviours, scoped to walks without `--as-memory`. An explicit `--as-memory` call keeps its
  current store behaviour and its refusals (R-264a). {#r-220-every-dir}
- **AC-220.** Each case starts RED at HEAD, in task 23.0's sandbox, with the real CLI, re-read
  against bug-216's merged walker before RED. Cases (a), (g) and (h) each run on two routes: A's
  daemon up (the daemon body dispatches; the test waits for the dispatched job ids through
  `ingest_gmd_status` before asserting), and A's daemon down (the CLI's no-daemon route
  dispatches). B's state is per case. {#ac-220}
  - **Bounds (rev 9, u1; [[feedback_mutation_must_fail_not_hang]]).** No case may hang:
    - every call from the test to A, CLI or op, has a timeout of at most 10 s;
    - every job-id wait has a stated deadline (30 s) and fails with the job's last status;
    - every gate auto-releases at its own deadline (at most 20 s) and in `finally`;
    - teardown stops each daemon with a timeout, and kills one that does not stop within it;
    - a mutation that makes A wait on B must FAIL by A's call timing out within 10 s, never by
      deadlock;
    - before any bounded call, the fixture pre-warms the embedding model, or uses the sandbox's
      cached model worker, so the bounds measure the dispatch and not a cold model load (rev 10,
      w5).
  - (a) `rmx ingest-gmd <memdir>` without `--as-memory`, over a fixture memdir under
    `HOME/.claude/projects/<slug>/memory`. The fixture holds 2 feedback memories, 1 save-state,
    `MEMORY.md` and a dot-dir file. Expected:
    - 0 `kind=doc` rows with a path under the memdir;
    - 3 `kind=memory` rows, the save-state stored as `session/recall-state`;
    - `rerouted_to_memory: 3` printed, with the names;
    - no row for the dot-dir file or for `MEMORY.md`;
    - on the daemon-up route, run once more as `rmx ingest-gmd --detach`: the first status that
      reads `done` already carries the reroute counts and job ids (rev 9, v1);
    - `rmx memory recall "<phrase unique to a rerouted feedback memory>"` returns it, so the
      vectors are present (s3).
  - (b) The same on a FILE target and on a SUBDIR target (`feedback/`): the same classification.
    These share R-264a's fixtures.
  - (c) A marker-on dir outside the projects shape (a throwaway dir with a valid
    `.memory-layout`, not a symlink target of any projects memdir). The walking store A is seeded
    with a HEAD-built `kind=doc` twin of one of its files. It is recognised by the marker branch,
    so no `kind=doc` row is minted. No store resolves, so its files are counted and named under
    `rerouted_no_store`, no memory row lands anywhere, and A's twin is purged.
  - (d) A doc walk over a root that holds `docs/x.md` and a memdir: `docs/x.md` stays `kind=doc`,
    and only the memdir's files reroute.
  - (e) A store that holds a `kind=doc` twin from a HEAD-built doc walk: after the next walk there
    are 0 twins and one `kind=memory` row per file.
  - (f) bug-216's X1 pins re-run green.
  - (g) Cross-store (T2-O1): `rmx ingest-gmd <B's memdir>` run from root A, with no
    `--as-memory`, A seeded with a HEAD-built twin, and B's daemon up. The result carries B's
    `job_id`. After that job completes, the memories are in B as `kind=memory`, in B's memory
    partition (read through B's daemon; rev 9, v3), and recall in B returns one. A holds no row for them (the twin is purged), and the CLI's exit is 0. On A's
    daemon-up route the CLI makes no dispatch call of its own: B's job registry shows exactly one
    job.
  - (g2) The same, with B faulted deterministically (rev 8, n2), on both of A's routes:
    - B busy: B holds an active ingest job, so `ingest already active`;
    - B absent: B has no daemon, so the reason carries the `rmx daemon start` remedy, and B's
      catalog files are not opened (their mtimes are unchanged).

    In both: A's doc ingest completes, `rerouted_failed: 1` names B's root and the reason, the
    CLI exits non-zero with the reason on stderr, and A still holds no twin.
  - (h) A symlinked memdir (viascope's shape: `HOME/.claude/projects/<slug>/memory` → a target
    outside `projects/`), marker-off and marker-on, passed as the symlink path. The memories land
    in the slug's store. A sync walk that reaches the resolved target also finds the slug, through
    the symlink map.
  - (i) The sync and ingest_path routes (m6; rev 8, t2; rev 9, u2). The fixture memdir is a plain dir inside A's project tree,
    outside any dot-dir, so the walker reaches it. It is the TARGET of a
    `HOME/.claude/projects/<slug>/memory` symlink, so the sync walk finds its slug through the
    symlink map. It runs twice:
    - slug → A (the same-store branch);
    - slug → B (the cross-store branch, B up).

    Each run goes through A's daemon twice: once as `_sync_paths` (the sync op), and once as
    `rmx ingest <project root>` (`_op_ingest_path`). On both, the files reroute as in (a) and the
    counts land on the op record. An `ingest_path` leg with `ingest_gmd_paths` made to raise (a
    registered test-side fault) mints no `kind=doc` twin for the memdir files, keeps the
    `rerouted` groups and counts the fallback's failures. An audit hook on `d._store_lock` and on the dispatcher records each dispatch
    and the lock state at that moment. It asserts at least one dispatch was observed per run and
    that the lock was not held at any of them.
  - (k) In-daemon cross-store (rev 8, t1; rev 9, u1). A sync-op walk in A reaches the (i)
    fixture mapped to B. B is served IN THE TEST PROCESS (a threaded `serve_forever`), so its gate
    is a test-side monkeypatch of B's job body, registered in `workflow/test_mock_registry.md`,
    never a `src/` flag. A is a real daemon.
    - B up: B's job is held at its start by the gate. A's op returns within the 10 s call bound,
      with B's `job_id` on its record, while B's job is still gated. After the gate opens, the
      rows appear in B within the 30 s job deadline.
    - B slow to reply (rev 9, v2): B's start reply is held past the 2 s budget by a second gate on
      the reply. The group is `rerouted_unconfirmed`, not `rerouted_failed`, and is named with
      the "job may be running on B" text.
    - B absent: `rerouted_failed` with the remedy on A's op record and daemon log, and B's catalog
      files are not opened (their mtimes are unchanged).
    - B busy (an active ingest job on B): `rerouted_failed` with `ingest already active`, and A's
      op returns without waiting.
  - (j) The home memdir (m7): a walk that reaches `HOME/.claude/projects/-<home-slug>/memory`
    dispatches nothing and reports `rerouted_held` with the plan-27 Q4 reason.
  - (m) The exemption is internal and single-use (rev 10, w2). While a job is active on A:
    - a socket `ingest_gmd_start` carrying that job's id under any parent or exempt key
      (`parent_job`, `exempt`, `parent`) is refused with `ingest already active`;
    - in-process, a second exempt start from the same parent job object is refused.
  - (n) Every route drains exactly once (rev 10, w1). The test is parametrized over every OPS name
    and every CLI in-process entry point that reaches `ingest_gmd_paths`:
    - OPS: `sync_files`, `sync_since`, `flush_queue`, `flush_queue_async`, `ingest_path`,
      `ingest_path_start`, `ingest_gmd`, `ingest_gmd_start`;
    - CLI in-process: `rmx sync` (the `sync_since`, `flush_queue` and `sync_files` branches of
      `_sync_in_process`), the standalone `rmx watch` flush, `rmx ingest`, `tldr-warm`,
      `graphify-warm` and `rmx ingest-gmd`.

    Each runs on a fixture with one rerouted file and asserts exactly one dispatch, observed
    through the drain's audit hook. The daemon rows also include the daemon watcher thread's
    flush and the `flush_queue_async` runner thread (rev 11, x3).

    A second check asserts the list is complete. It runs a call-graph walk (AST or `tldr`, as
    bug-216 R2 enumerates its walkers) seeded from `daemon.OPS`, the CLI command tree, and every
    `threading.Thread(target=…)` and `_bg_pool.submit(…)` site, following lambda bodies. It fails
    on any path to `ingest_gmd_paths` whose entry is missing from the parametrization. **It must
    be shown to fail (x3):**
    - a fixture plants an OPS entry that reaches `ingest_gmd_paths` and is missing from the
      parametrization, and the scan fails on it;
    - a fixture plants a route that enqueues outside any open invocation, and `enqueue` raises
      ([[feedback_clean_corpus_hides_a_dead_gate]]).
  - (o) `ReplyTimeout` (rev 10, w4), against a test socket server:
    - one that accepts, reads the request and never replies raises `ReplyTimeout`;
    - a refused connection does not;
    - a connect that times out does not.
  - (p) Interleaving (rev 11, x1). Two ops X and Y each walk their own rerouted files through A's
    daemon, with `RMX_INGEST_YIELD_EVERY=1` and a gate on X's second file, so Y runs inside X's
    yield window. Then:
    - each op's reply (and job record) carries exactly its own groups;
    - each group is dispatched once;
    - an audit hook timestamps the starts: no same-store memory job starts before its parent's
      doc ingest has returned.
  - (q) Raise after enqueue (rev 11, x2):
    - CLI: a command whose walk enqueued a group, then raises `ClickException` (and, as a second
      run, calls `ctx.exit(2)`), run under `CliRunner`. The group is still dispatched and its
      count printed on stderr, the original error is printed, and the exit is non-zero.
    - Daemon: a synchronous op and a detached job that each raise after the enqueue. The
      boundary's `finally` dispatches the group, and the reply / job record carries both the
      error and the reroute result.
  - (l) Prestage (n4): `rmx ingest-gmd --prestage <root>` over a root holding the (a) memdir
    reports `rerouted: 3` with the names on its result and its CLI line, dispatches nothing, and
    stages no `kind=doc` row for them.
  - Mutations, each killed:
    - dropping the reroute kills (a);
    - rerouting before `should_ignore` kills (f) (an entity appears under a dot-dir);
    - a second resolver copy for R-264a that ignores the marker kills (c) and AC-264 (a);
    - dropping the printed count kills (a)'s count assertion;
    - landing rerouted files in the calling store kills (g);
    - ingesting a no-store memdir's files into the calling store kills (c);
    - passing the resolved form to the store resolver kills (h) (marker-on) and (i) (rev 8, n1);
    - dropping the symlink map kills (h)'s sync leg and (i) (rev 8, n1);
    - skipping the memory-vector drain on the same-store branch kills (a)'s recall leg;
    - running the reroute only on the in-process path kills the daemon-up run of (a);
    - dispatching under the writer lock kills (i)'s audit assertion;
    - swallowing B's error kills (g2);
    - waiting on B's ingest (a synchronous `ingest_gmd` call, status polling, or
      `_bridge_wait_for_active_job`) kills (k)'s B-up leg, which fails by A's call timing out
      within 10 s while the gate is still closed; the gate's own deadline then frees B (rev 8, t1;
      rev 9, u1);
    - dropping the `rerouted` result on the `ingest_path` route kills (i)'s `ingest_path` leg
      (rev 9, u2);
    - letting the `ingest_path` fallback upsert memdir files kills (i)'s fallback leg (rev 9, u2);
    - flipping the job to `done` before writing the dispatch result kills (a)'s daemon-up
      `--detach` check, which reads the counts from the first `done` status (rev 9, v1);
    - counting a post-send timeout as `rerouted_failed` kills (k)'s slow-reply leg (rev 9, v2);
    - omitting B's memory partition kills (g)'s partition assertion (rev 9, v3);
    - opening B's store in-process when B has no daemon kills (k)'s and (g2)'s B-absent legs (the
      mtimes change) (rev 8, t1, n5);
    - the CLI dispatching again on A's daemon-up route kills (g)'s one-job assertion (rev 8, t1);
    - dropping prestage's `rerouted` count kills (l) (rev 8, n4);
    - draining on lock release or yield (rev 10's design) kills (p) (rev 11, x1);
    - skipping the drain at the op/job boundary kills (n)'s OPS rows and (i) (rev 10, w1);
    - draining only on success kills (q) (rev 11, x2);
    - a global process-wide queue, or a silent no-op `enqueue` without an invocation, kills
      (n)'s must-fail fixture and (p) (rev 11, x1, x3);
    - opening a second Store in the CLI drain kills (q)'s CLI leg, through a guard in the test
      that counts Store opens per root (rev 11, x4);
    - skipping the drain on CLI exit (a result-callback drain) kills (n)'s CLI rows, the
      no-daemon runs of (a) and (g), and (q) (rev 10 w1; rev 11 x2);
    - dropping dispatch from `_op_flush_queue_async` (its runner thread opens no invocation)
      kills (n)'s `flush_queue_async` row, because `enqueue` raises (rev 10 w1; rev 11 x1);
    - reading the exemption from `args` kills (m)'s socket leg (rev 10, w2);
    - not consuming the exemption kills (m)'s second-start leg (rev 10, w2);
    - raising `ReplyTimeout` on a connect timeout kills (o) (rev 10, w4).
    - skipping the twin purge on the cross-store or no-store branch kills (g) and (c);
    - dropping the twin purge entirely kills (e);
    - dispatching the home memdir kills (j).

## Lines that change under Q8 b (2026-11-13) {#q8-b}

Q8 is open ([[open-questions]]). This spec holds under Q8 a or c, where save-states stay bridged
as `session/recall-state` rows. Under Q8 b (save-states and digests kept out at ingest), these
lines change:

- AC-5's one-time forced re-bridge of save-states, and its `forced` stat, are no longer a
  re-ingest. What replaces them (removing the existing save-state rows) belongs to the held G22
  spec, and any live purge goes through plan-22's audited path (D-Q1).
- R-264b's sticky-row repair has no save-state rows left to repair.
- AC-6's first bullet (`rmx memory recall` returns a moved save-state) is replaced by
  `rmx recall-state` alone.
- R-220b: a rerouted save-state is skipped and counted, not ingested.
- AC-220 (a): "the save-state stored as `session/recall-state`" becomes "the save-state is
  skipped and counted" (rev 7, m1).
- AC-264 (a): the `savestates/` leg ("stores `session/recall-state`") becomes "stores no row"
  (rev 7, m1).
- AC-2's file-side save-state type rewrites (26.4 AC-3) do NOT change: they are file edits.

## Lead rulings (2026-11-13) {#lead-rulings-2026-11-13}

The spec-wave report's open items, ruled by the lead on the user's pattern (correct first, reuse
existing infrastructure, route never refuse). Folded above; no hold remains.

| item | ruling | anchor |
|---|---|---|
| T2-O1 (bug-220's store when the memdir resolves elsewhere) | (b): the memdir's own store; AC-220 (g). Rev 7: dispatched after the lock is released. Rev 8: reached by a detached `ingest_gmd_start` on B, not `_sync_memory_dir`'s synchronous call | [[#r-220c]], [[#ac-220]] |
| T2-O2 (per-file force input for bug-202) | (a): `--force-rebridge`, extending AC-5's force input; built only if R-202a finds the files. **Superseded in rev 7** (lead, bsd-spec-t2 s4): it rides the single-file bridge (`ingest-gmd --as-memory --force-rebridge <file>`), not an organise apply, and the live restore is 27.5's | [[#r-202b]] |
| T2-O3 (bug-208 m-1/m-2 scope) | Keep R-208b and R-208c | [[#pre-bug208]] |
| T2-O4 ("same marker gate") | The reroute is ungated and reuses the marker reader inside `memdir_of`; the ADR-0005 amendment stands | [[#r-220a]], [[#r-220-every-dir]] |
| T2-O5 (forget step 5 vs the decay rule) | Unchanged: the user decides at 26.8 AC-8; ADR-0005 A.2 states the tension | [[task-26.8-refmatrix-live-rollout#requirements]] |

## Revision round 7 (2026-11-13): bsd-spec-t2 {#rev-round-7}

Answers [[bsd-spec-t2-b5fe2d3]] (DIRTY 0B/4S/7M), with the lead's rulings on s1-s4 and m7. Status
is unchanged (`pending`).

rel: derives-from -> [[bsd-spec-t2-b5fe2d3]]

| finding | change | anchor |
|---|---|---|
| s1 (the walk sees only resolved paths; viascope's symlinked memdir keeps bug-220) | `memdir_of` matches both forms: the as-given path, and a resolved path mapped back through the `~/.claude/projects/*/memory` symlinks; the store resolver only ever gets the unresolved form; AC-220 (h) symlinked memdir, marker-off and marker-on; mutation "resolve before `memdir_of`" | [[#r-220a]], [[#ac-220]] |
| s2 (ADR-0005 holds two rules for one input; "writes no file" is false) | Non-raising resolver variant for the walk only; the file-only carve-out is scoped to the flagless walk; `--as-memory` keeps its behaviour and refusals; the every-dir reason is restated as "store-side; its only file write is marker-gated" | [[#r-220c]], [[#r-220-every-dir]], [[refmatrix/adr-0005-memory-dir-layout#amendments]] |
| s3 (cross-store call under the writer lock; same-store rows get no vectors; no failure branch) | Rerouted files are collected, then dispatched after the doc ingest returns and the lock is released, each as a separate op; same-store goes through the full `--as-memory` path (drain, index); B busy/unreachable counted, named, non-zero, A completes; daemon-up and daemon-down runs; recall leg; lock-audit case; `daemon.py` in Files | [[#r-220c]], [[#r-220d]], [[#ac-220]], [[#files]] |
| s4 (the restore was a full organise apply, out of order, maybe in another project's dir) | 26.5 keeps R-202a/R-202c; the found branch builds only the single-file `--force-rebridge <file>` (sandbox-tested); the live restore of the two named files moves to 27.5 | [[#r-202b]], [[task-27.5-cliquedb-at-session-boundary#r-202b-live]] |
| m1 (Q8 b misses AC-220 (a), AC-264 (a)) | Added | [[#q8-b]] |
| m2 (R-208a contradicted the reused helper's temp naming) | Restated to the helper's `<name>.*.tmp`, unlinked on failure, never read by the walk | [[#r-208a]] |
| m3 (mutation gaps) | AC-208 (d) gains two mutations; AC-220 (c)/(g) are seeded with a HEAD-built twin; twin-purge mutations named | [[#ac-208]], [[#ac-220]] |
| m6 (no sync-route case) | AC-220 (i) through `_sync_paths` on a marker memdir | [[#ac-220]] |
| m7 (the home memdir would reroute into the hub's global store) | Held per plan-27 Q4 (`rerouted_held`) until 27.1 reports; AC-220 (j) | [[#r-220c]], [[#ac-220]] |

## Revision round 8 (2026-11-13): bsd-spec-t2 r2 {#rev-round-8}

Answers [[bsd-spec-t2-r2-091dec9]] (DIRTY 0B/2S/6M; all r1 findings closed) with the lead's
rulings. Status is unchanged (`pending`).

rel: derives-from -> [[bsd-spec-t2-r2-091dec9]]

| finding | change | anchor |
|---|---|---|
| t1 (in-daemon cross-store still waited on B; two dispatch owners; helper module unnamed; no in-daemon AC) | Cross-store starts a detached `ingest_gmd_start` on B with `retries=0` and a short connect timeout, and never waits. The daemon body is the one dispatcher on every daemon route, and the CLI dispatches only on its no-daemon route. New `memory_reroute.py`. AC-220 (k) covers B up/absent/busy; mutations "waits on B" and "opens B in-process" | [[#r-220c]], [[#ac-220]], [[#files]] |
| t2 (case (i) was vacuous: a slugless marker dir is no-store) | (i)'s memdir is the target of a projects symlink; it runs same-store and cross-store; at least one dispatch observed; no dispatch under the lock | [[#ac-220]] |
| n1 (the (h) mutation survived; the marker branch's unresolved form) | Every branch takes its unresolved form through the as-given path or the symlink map; mutations "resolved form to the store resolver" and "drop the map" | [[#r-220a]], [[#ac-220]] |
| n2 (the chmod fault may not fault) | (g2) faults B by a held ingest job (busy) or no daemon (absent), on both of A's routes | [[#ac-220]] |
| n4 (prestage dropped rerouted files uncounted) | Prestage carries `rerouted` with names (the bug-216 R6b shape); AC-220 (l) | [[#r-220b]], [[#ac-220]] |
| n5 (the CLI's no-daemon leg opened B in-process) | No route opens B in-process. B absent is `rerouted_failed` with the `rmx daemon start` remedy. The CLI's own store keeps today's behaviour | [[#r-220c]] |

## Revision round 9 (2026-11-13): bsd-spec-t2 r3 {#rev-round-9}

Answers [[bsd-spec-t2-r3-abbe45f]] (DIRTY 0B/2S/3M; all r2 findings closed) with the lead's
rulings, which take the reviewer's recommendations. Status is unchanged (`pending`).

rel: derives-from -> [[bsd-spec-t2-r3-abbe45f]]

| finding | change | anchor |
|---|---|---|
| u1 (unbounded waits; the "waits on B" mutation deadlocked) | AC-220 bounds: test calls to A at most 10 s, job waits 30 s with the last status, gates auto-release at most 20 s and in `finally`, bounded teardown. (k)'s B served in the test process with a registered test-side gate. The mutation fails by timeout | [[#ac-220]] |
| u2 (the `ingest_path` route collected rerouted files with no dispatcher; its fallback minted twins) | Every dispatcher named, `ingest_path` and the sync ops included. `_ingest_path_inner` returns the groups. The fallback skips memdir files and counts its failures. (i) gains `ingest_path` and fallback legs | [[#r-220c]], [[#ac-220]], [[#files]] |
| v1 (`done` before the dispatch result) | The dispatch result is written before the job flips to `done`. The job's own same-store start is exempt from the single-active guard | [[#r-220c]], [[#ac-220]] |
| v2 (a slow reply read as a failure) | A post-send timeout is `rerouted_unconfirmed` (named, with the job id when known, exit non-zero); a pre-send failure stays `rerouted_failed`. (k) slow-reply leg | [[#r-220c]], [[#ac-220]] |
| v3 (B's memory partition not passed) | The cross-store start passes B's memory partition; (g) asserts the rows land there | [[#r-220c]], [[#ac-220]] |

## Routes that reach `ingest_gmd_paths` (informative, at `4b4b96e`) {#reroute-routes}

This table is not a dispatcher list. Every route below is covered by the queue and its drain
([[#r-220c]]), and AC-220 (n) runs each one. Source: [[bsd-spec-t2-r4-15b2f25#w1]].

| context | route | reaches `ingest_gmd_paths` via | drained at |
|---|---|---|---|
| daemon | `sync_files`, `sync_since` | `sync._sync_paths` (`sync.py:308`) | the OPS handler's `finally` |
| daemon | the daemon's own watcher (`Daemon._start_watcher` → `sync_files`, `daemon.py:3095`) | `_sync_paths` | each flush iteration's `finally` |
| daemon | `flush_queue` | `syncmod.flush_queue` → `_sync_paths` | the OPS handler's `finally` |
| daemon | `flush_queue_async` (the Stop/SubagentStop hook route; runner thread `rmxd-async-flush`, `daemon.py:3536`) | `syncmod.flush_queue` → `_sync_paths` | the runner thread's `finally` |
| daemon | `ingest_path` | `_ingest_path_inner` (`ingest.py:1354`) | the OPS handler's `finally` |
| daemon | `ingest_path_start` (its runner IS `_op_ingest_path` under `_run_detached_job`, `daemon.py:3950`) | `_ingest_path_inner` | `_run_detached_job`'s `finally` |
| daemon | `ingest_gmd` | `_run_ingest_gmd_body` | the OPS handler's `finally` |
| daemon | `ingest_gmd_start` | `_run_ingest_gmd_body` on `bg_pool` | the runner's `finally` |
| CLI in-process | `_sync_in_process`: the `sync_since`, `flush_queue` and `sync_files` branches (`cli.py:8763-8808`) | `_sync_paths` | root `ctx.call_on_close` |
| CLI in-process | standalone `rmx watch` (`watch.run_watcher` → `sync_files`) | `_sync_paths` | root `ctx.call_on_close`, plus each flush iteration if the watch loop is long-lived (it opens its own invocation per flush) |
| CLI in-process | `rmx ingest`, `tldr-warm`, `graphify-warm` (shared `cli._ingest`, `cli.py:510-525`) | `ingest_path` | root `ctx.call_on_close` |
| CLI in-process | `rmx ingest-gmd` (no daemon) | `_ingest_gmd_in_process` | root `ctx.call_on_close` |

## Revision round 10 (2026-11-13): bsd-spec-t2 r4 {#rev-round-10}

Answers [[bsd-spec-t2-r4-15b2f25]] (DIRTY 0B/2S/3M; U1, V2 and V3 closed) with the lead's
rulings. Status is unchanged (`pending`).

rel: derives-from -> [[bsd-spec-t2-r4-15b2f25]]

| finding | change | anchor |
|---|---|---|
| w1 (the dispatcher list missed `flush_queue`, `flush_queue_async` and the CLI in-process sync/watch/warm routes) | Design change: `ingest_gmd_paths` queues on one per-process queue. It is drained at the outermost `d._store_lock` exit (daemon) and at the top-level command wrapper's exit (CLI). The per-route list becomes an informative table. AC-220 (n) runs every route and checks the list is complete; three mutations | [[#r-220c]], [[#reroute-routes]], [[#ac-220]] |
| w2 (the V1 exemption was untested and socket-reachable) | The same-store start is an in-process function call with the parent job object, carrying a single-use exemption; socket keys are ignored. AC-220 (m); mutations "read from args" and "not consumed" | [[#r-220c]], [[#ac-220]] |
| w3 (stale "after the doc op's job has closed") | Now "after the lock is released, before the parent flips to `done`" | [[#r-220c]] |
| w4 (failed vs unconfirmed needed an unnamed `daemon.call` change) | `daemon.call` raises a typed `ReplyTimeout` after the send, subclassing today's timeout; listed in Files; AC-220 (o) | [[#r-220c]], [[#files]], [[#ac-220]] |
| w5 (cold model load inside the bounds) | The fixture pre-warms the model, or uses the sandbox's cached worker, before any bounded call | [[#ac-220]] |

The lead's ruling says the daemon drain runs "after the job record closes". Read literally, that
contradicts V1 (`done` only after the dispatch result). This text kept V1: the drain ran at the
lock exit, and the runner flipped the job to `done` after the drain had written its result. That
was flagged to the lead. **Superseded by rev 11:** the lock-exit drain point was itself wrong
(x1). V1 is kept at the op/job boundary.

## Revision round 11 (2026-11-13): bsd-spec-t2 r5 {#rev-round-11}

Answers [[bsd-spec-t2-r5-e05f3a1]] (DIRTY 0B/2S/2M; W2-W5 closed) with the lead's corrected
rulings. The lead records x1 as its own error in the W1 ruling. Status is unchanged (`pending`).

rel: derives-from -> [[bsd-spec-t2-r5-e05f3a1]]

| finding | change | anchor |
|---|---|---|
| x1 (the lock-exit drain fired at every cooperative yield, on a queue every holder shared) | The queue is per invocation (a `contextvar` opened at the boundary), and `enqueue` outside one raises. The drain runs in `try/finally` at the op/job boundary (OPS handler, `_run_detached_job` and the start runners, the `flush_queue_async` runner thread, the watcher flush iteration), never at a yield or release. `done` comes after the job's own drain. The exemption is armed only after the parent's doc ingest returns. New AC-220 (p) interleaves two ops; mutation "drain on lock release" | [[#r-220c]], [[#reroute-routes]], [[#ac-220]] |
| x2 (no exception-path drain; the result callback skips exceptions) | The CLI drain is a root `ctx.call_on_close`, which runs on every exit and under `CliRunner`. New AC-220 (q): raise-after-enqueue on the CLI and in the daemon; mutation "drain only on success" | [[#r-220c]], [[#ac-220]] |
| x3 ((n)'s scan was unproven and missed non-OPS threads) | Seeds include `Thread(target=…)` and `_bg_pool.submit(…)` sites, following lambdas; rows for the watcher and the async-flush runner; must-fail fixtures (a planted OPS route, and a planted enqueue outside an invocation) | [[#ac-220]] |
| x4 (the CLI same-store leg had no Store, or would open a second one) | The drain reuses the invocation's registered Store, and never opens a second Store on one root in one process. A daemon-only CLI route has an empty queue | [[#r-220c]], [[#files]] |

Also removed: a stale duplicate "library helper" bullet left over from rev 8.
