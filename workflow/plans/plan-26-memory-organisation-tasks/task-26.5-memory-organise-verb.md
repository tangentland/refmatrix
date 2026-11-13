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
  - Modify `src/refmatrix/ingest_gmd.py` (`collect_gmd_files`, `ingest_gmd_paths`) and `cli.py`
    (`ingest-gmd` output): the reroute, routed to the memdir's own store through
    `_sync_memory_dir(memdir, root=)`, and its counts. Create
    `tests/test_ingest_gmd_memdir_route.py`.
  - Only if R-202a finds bug-202's files: `--force-rebridge <id>` in `memory_organise.py` and the
    `memory organise` command ([[#r-202b]]).
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

- **R-208a (s-1) atomic write.** The save-state is written to a dot-named temp file in
  `target.parent` and `os.replace`d onto `target`, keeping the file mode
  (impression `imp-atomic-write-changes-mode`). It reuses the existing atomic-write shape
  (`memory_index._atomic_write_text`, bug-199) by calling one shared helper, never a second copy
  ([[feedback_converge_repeated_shapes]]). A leftover temp file is skipped and named by the walk,
  as today. {#r-208a}
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
    - letting the raw `OSError` through kills (d)'s MCP leg.
- Rows R-208b and R-208c are MEH findings that the bug-208 row names in its symptom but not in its
  fix column. They ride here because they touch the same function (kept by lead ruling
  2026-11-13, T2-O3; [[#lead-rulings-2026-11-13]]).

## bug-202's two anchor sets: check existence first (2026-11-13) {#bug202-restore}

The bug-202 row says two memories lost ALL their anchors: `guardrail-coordinator-lane-dispatch`
and `guardrail-two-writers-one-logical-db`. It says restoring them "needs a forced re-bridge
(26.5 AC-5's force input)". AC-5's force input covers save-states only (Ca-6).
[[bsd-pop-r1-c56782f#m4]] found no file with either id under `~/.claude/projects`,
`~/claude_tools` or `~/github`. The rows themselves still exist in refmatrix's store: on
2026-11-13, `rmx context guardrail-coordinator-lane-dispatch` returned its body. {#bug202-why}

- **R-202a: existence check, read-only, run first.** At the start of this task, for each id: {#r-202a}
  - read the row through refmatrix's daemon (`rmx memory get <id>`) and record its
    `metadata.source_path`;
  - test that path as written and as resolved;
  - if it is absent, run a scoped search for a GMD file whose frontmatter `id` equals the id. The
    search covers `~/.claude/projects/*/memory` and the repo roots in
    [[plan-27-memory-fleet-rollout#survey]], skips `_frameworks_and_libraries`, and never starts
    from `/` ([[feedback_never_search_from_root]]).

  Every command and result goes to `workflow/review-output/26.5-bug202-existence.log`.
- **R-202b: found → restore with a check.** The file is re-bridged past the content-hash gate
  into the store that holds the row, with `rmx memory organise <memdir> --apply --force-rebridge
  <id>` (lead ruling T2-O2). `--force-rebridge <id>` (repeatable) extends AC-5's force input: the
  named ids bypass the content-hash gate on that apply, alongside the save-states AC-5 already
  forces, and each forced id is counted under `forced` and named. An id that matches no file in the
  memdir exits non-zero naming it, before the backup. The flag is built only if R-202a finds the
  files; if R-202c applies, it is not built.
  - The check is read through the daemon: the memory's `x#…` anchor concepts equal the file's
    `{#anchor}` set, by name and by count. Before the restore the set is empty, which is the RED.
  - This is a live write. It runs with the deployed `rmx` after this task is released, and it is
    announced to the user first. {#r-202b}
- **R-202c: not found → no restore.** The bug-202 row's restore note is closed with the reason:
  the files are gone (see the R-202a log); the rows keep their bodies; and the anchors cannot be
  rebuilt from a file that does not exist. The rows are not forgotten
  ([[feedback_decay_never_loses_knowledge]]). {#r-202c}
- **AC-202.** {#ac-202}
  - The log exists. For each id it names the `source_path`, the existence result and the branch
    taken.
  - For R-202b, the anchor-set check passes.
  - For R-202c, the bug-202 row's note carries the reason and the log path.

## bug-220: a memory file is classified by where it lives (2026-11-13) {#bug220-route}

rel: depends-on -> [[task-bug216-rule-docs-in-graph#r2]]

bug-220: a doc walk lands every memory file as `kind=doc` in the project partition. The doc walk
can be `rmx ingest-gmd <memdir>` without `--as-memory`, or any walk whose root covers a memory
dir. The result is a second node per memory, of the wrong kind, invisible to recall's kind
filter, with its `rel:` edges bound to the twin. The user (2026-11-13): "we should have a way to
bridge memories into the graph as they are sometimes relevant". So the fix routes the file and
never refuses it ([[plan-review-2026-11-13#x1]]). L37 folds it here because this task owns the
memdir resolver (R-264a) and the marker reader. {#bug220-why}

- **R-220a: one memdir resolver.** `memory_layout.memdir_of(path) -> Path | None` returns: {#r-220a}
  - the nearest ancestor that holds a `.memory-layout` marker, read through `is_organised` (so a
    malformed marker is still a hard error, ADR-0005 `#marker-encoding`);
  - else the `~/.claude/projects/<slug>/memory` shape, tested on the unresolved path;
  - else `None`.

  R-264a's resolver IS this function plus its loud refusal on `None`. There is no second copy.
- **R-220b: classification follows location.** In `collect_gmd_files` / `ingest_gmd_paths` with
  `as_memory=False`, every file whose `memdir_of` is not `None` is taken out of the doc set and
  ingested through the memory path of the same call. That means: {#r-220b}
  - `kind=memory`, in the memory partition;
  - 26.4's save-state rule, evaluated against that memdir;
  - `iter_memory_files`' exclusions (dot-dirs, dotfiles, `MEMORY.md`, `README.md`).

  No caller flag can mint a `kind=doc` row for such a file. The memory path already purges a prior
  `kind=doc` row at the same path (`ingest_gmd.py:1376`). That purge runs on a rerouted file, so a
  twin left by an earlier doc walk is removed the next time the file is walked.
- **R-220c: counted and named.** The call's result carries `rerouted_to_memory: N` and lists the
  files (the first 20, plus the count). The CLI prints it. A daemon walk records the count on its
  op record. Nothing is silent ([[CLAUDE#no-silent-failures]]). {#r-220c}
- **R-220d: after bug-216's prune, never before.** The reroute runs AFTER `should_ignore`
  ([[task-bug216-rule-docs-in-graph#r2]]). A path the doc walk prunes, such as a dot-dir, is never
  reached and so is never rerouted. bug-216's X1 pins stay green: {#r-220d}
  - no entity under a dot-dir on a doc route;
  - `.claude/PROJECT_PROFILE.md` lands once, as `kind=doc`;
  - a memdir under `.claude` still lands as `kind=memory` through the bridge.
- **R-220e: the store is the memdir's own (lead ruling T2-O1).** Rerouted files land in the store
  their memdir resolves to (ADR-0005 `#store-resolution`), never in the caller's store because it
  is the caller's: {#r-220e}
  - the store comes from AC-1's resolver on the memdir `memdir_of` returned, and the files go
    through `_sync_memory_dir(memdir, root=<resolved>)`, the AC-1 bridge parameter: one bridge
    per memdir reached, not one per file (the bridge is hash-gated);
  - when the resolved store IS the store the walk is writing (an in-daemon walk of its own
    memdir), the files go through the in-process memory path of the same call, so a daemon never
    calls itself under its own lock;
  - a memdir with no resolvable store (a well-formed slug matching no root, or a marker dir
    outside the `~/.claude/projects/<slug>/memory` shape) is file-only, as ADR-0005 says: its files
    are taken out of the doc set, ingested nowhere, and counted and named as
    `rerouted_no_store` with the fix text. The walk continues; nothing is refused;
  - the calling store's own `kind=doc` row at a rerouted path (a twin from an earlier doc walk)
    is purged by the calling store with the existing purge (`ingest_gmd.py:1376`), wherever the
    memory lands.
- **Every dir.** The reroute writes no file, so it is not marker-gated. ADR-0005 `#marker` lists it
  among the behaviours that reach every dir (amended 2026-11-13). {#r-220-every-dir}
- **AC-220.** Each case starts RED at HEAD, in task 23.0's sandbox, with the real CLI, re-read
  against bug-216's merged walker before RED: {#ac-220}
  - (a) `rmx ingest-gmd <memdir>` without `--as-memory`, over a fixture memdir under
    `HOME/.claude/projects/<slug>/memory`. The fixture holds 2 feedback memories, 1 save-state,
    `MEMORY.md` and a dot-dir file. Expected:
    - 0 `kind=doc` rows with a path under the memdir;
    - 3 `kind=memory` rows, the save-state stored as `session/recall-state`;
    - `rerouted_to_memory: 3` printed, with the names;
    - no row for the dot-dir file or for `MEMORY.md`.
  - (b) The same on a FILE target and on a SUBDIR target (`feedback/`): the same classification.
    These share R-264a's fixtures.
  - (c) A marker-on dir outside the projects shape (a throwaway dir with a valid
    `.memory-layout`): recognised by the marker branch, so no `kind=doc` row is minted; no store
    resolves, so its files are counted and named under `rerouted_no_store` and no row lands
    anywhere (R-220e).
  - (d) A doc walk over a root that holds `docs/x.md` and a memdir: `docs/x.md` stays `kind=doc`,
    and only the memdir's files reroute.
  - (e) A store that holds a `kind=doc` twin from a HEAD-built doc walk: after the next walk there
    are 0 twins and one `kind=memory` row per file.
  - (f) bug-216's X1 pins re-run green.
  - (g) Cross-store (T2-O1): `rmx ingest-gmd <B's memdir>` run from root A, with no
    `--as-memory`: the memories land in B's store as `kind=memory`, and A holds no row for them
    (no `kind=doc` twin, no memory row). Mirrors AC-1 (a).
  - Mutations, each killed:
    - dropping the reroute kills (a);
    - rerouting before `should_ignore` kills (f) (an entity appears under a dot-dir);
    - a second resolver copy for R-264a that ignores the marker kills (c) and AC-264 (a);
    - dropping the printed count kills (a)'s count assertion;
    - landing rerouted files in the calling store kills (g);
    - ingesting a no-store memdir's files into the calling store kills (c).

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
- AC-2's file-side save-state type rewrites (26.4 AC-3) do NOT change: they are file edits.

## Lead rulings (2026-11-13) {#lead-rulings-2026-11-13}

The spec-wave report's open items, ruled by the lead on the user's pattern (correct first, reuse
existing infrastructure, route never refuse). Folded above; no hold remains.

| item | ruling | anchor |
|---|---|---|
| T2-O1 (bug-220's store when the memdir resolves elsewhere) | (b): the memdir's own store, through `_sync_memory_dir(memdir, root=)`; AC-220 (g) | [[#r-220e]], [[#ac-220]] |
| T2-O2 (per-file force input for bug-202) | (a): `organise --apply --force-rebridge <id>`, extending AC-5's force input; built only if R-202a finds the files | [[#r-202b]] |
| T2-O3 (bug-208 m-1/m-2 scope) | Keep R-208b and R-208c | [[#pre-bug208]] |
| T2-O4 ("same marker gate") | The reroute is ungated and reuses the marker reader inside `memdir_of`; the ADR-0005 amendment stands | [[#r-220a]], [[#r-220-every-dir]] |
| T2-O5 (forget step 5 vs the decay rule) | Unchanged: the user decides at 26.8 AC-8; ADR-0005 A.2 states the tension | [[task-26.8-refmatrix-live-rollout#requirements]] |
