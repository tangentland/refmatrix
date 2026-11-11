---
gmd: "0.1"
id: impl-task-user-level-state-commands
title: "/save-state and /recall-state install at user level and carry the ADR-0005 memory-dir rules"
tags: [implementation-summary, commands, save-state, recall-state, init, memory, adr-0005, plan-26]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-10
---

# /save-state and /recall-state: user level, with the memory-dir rules {#root}

rel: derives-from -> [[refmatrix/adr-0005-memory-dir-layout#decision]]
rel: related-to -> [[task-26.3-savestate-subfolder]]
rel: related-to -> [[task-26.2-bridge-move-safety]]
rel: reinforces -> [[feedback_save_state_commit_adds_all]]

User request, 2026-11-10: delete this project's copies of the two commands (the user had written
new user-level versions), make the user-level versions reflect the memory changes, and change the
install templates to put them at user level instead of project local. Branch
`task-user-level-state-commands`. The lead wrote both the RED tests and the GREEN code in one
session (a small direct request, not a plan task); a ch-bsd round over the branch is still owed.

## What changed {#changed}

- **Deleted** `.claude/commands/save-state.md` and `.claude/commands/recall-state.md` (byte-equal
  to the old templates).
- **`init_agents.install_commands(project_root, force, *, user_dir=None, backup_dir=None)`**:
  `USER_LEVEL_COMMANDS = {save-state.md, recall-state.md}` install into `user_dir` (default
  `user_commands_dir()` = `~/.claude/commands/`); every other packaged command still goes to
  `<project>/.claude/commands/` (`_install_pkg_md` gained `skip=`). A user-level file is shared
  by every project, so one project's `rmx init` never replaces it silently:
  - identical copy: left alone, reported `ok … (current)`;
  - differing copy, no `--force`: kept, reported `skip … pass --force`;
  - `--force`: the old copy is written to `backup_dir` (default `command_backup_dir()` =
    `<user_home>/backups/commands/`, the bug-195 backup precedent) BEFORE the overwrite; a failed
    backup raises and replaces nothing;
  - a project-local copy of a user-level command is named in a `warn` line, never deleted.
- **`cli.py`**: the `rmx init` comment and the `--force` help say where the two commands go and
  that the user-level copy is backed up.
- **Templates** = the user's new user-level text (status file, `/goal` block, running-agent
  checks) plus the memory-dir rules the old project copies carried and ADR-0005 adds:
  - save-state: memory is written BEFORE `rmx save-state` (the bridge ingests the dir at that
    moment; the user-level draft had it after); type folders only where `.memory-layout` exists;
    never hand-write `savestates/`, never a topic folder, never a hand move (`rmx memory
    organise`); one `id` per file; `--commit` is `git add -A`, so commit by pathspec while agents
    edit the tree; bridge failures, duplicate-id refusals, skips and `remove_failed` are loose ends;
    the refmatrix deploy line keeps `rmx version -v` (pinned by `test_save_state.py`).
  - recall-state: `rmx recall-state` is back as the one-shot; the source is "newest save-state
    (`savestates/`, legacy top-level)" (26.3 AC-7's exact wording); ADR-0005's one "newest" order;
    the bridge-lag fallback; bridge refusals/skips are reported anomalies.
- **Installed**: both templates were written to `~/.claude/commands/` through
  `_install_user_level(force=True)`; the user's previous copies are in
  `~/.refmatrix/backups/commands/{recall,save}-state.md.20261110T123335*`.

## Tests {#tests}

- New `tests/test_install_commands_user_level.py` (12) and the amended
  `tests/test_hooks.py::test_install_commands_writes_stash_slash_commands` (passes an explicit
  `user_dir`, asserts the pair is not in the project).
- RED (`workflow/review-output/user-level-cmds-red.log`): 11 failed, 1 passed. The passing one,
  `test_save_state_writes_memory_before_the_bridge_runs`, holds at HEAD because the OLD template
  had the right order; it guards the merge with the user-level draft, which reversed it.
- GREEN (`user-level-cmds-green.log`, and `-green-post-mut.log` after the restore): installer,
  `test_hooks.py`, `test_save_state.py`: 36 passed.
- Mutations (`user-level-cmds-mutations.log`), each restored from a scratchpad copy and
  `cmp`-verified: M1 no skip (3 failed), M2 no backup write (1), M3 no project-local warn (1),
  M4 no identical-copy check (1). All killed.
- `rmx init` family + sandbox files (`user-level-cmds-init-family.log`): 185 passed, 1 failed —
  `test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon`, DuckDB
  `Conflicting lock`: bug-127/168, the same E line as the bug-199/200 clone's at-red log.

## ch-bsd r1 remedy {#remedy-r1}

rel: derives-from -> [[bsd-user-level-state-commands-r1-c596a11]]

Round 1 (`fa38500`): DIRTY 6 (0B/3S/3M), merge GO, #deploy-cleanup NO-GO as written.

- **#s-1** `rmx init` → user level was untested (ch-bsd's mutation E, init passing the project's
  `.claude/commands` as `user_dir`, survived 283 tests). New
  `test_rmx_init_installs_the_pair_at_user_level` (CliRunner `init --path <tmp> --no-hooks`,
  `HOME` set to a tmp dir): passes on the branch, fails under mutation E
  (`user-level-cmds-r1-s1-mutE.log`), restored by `git checkout -- src/refmatrix/cli.py`.
- **#s-2** #deploy-cleanup rewritten: per-repo trunk inventory (cliquedb tracks the pair on
  `main`/`master`), worktrees, never a staged delete, per-repo trunk commands for the user,
  verification against trunk trees.
- **#s-3** user decision 2026-11-10, "fallback chain": both templates' status file is now
  "the one the project's CLAUDE.md names; else `handoff.md` if it exists; else
  `workflow/STATUS.md`", so /save-state no longer starts a `workflow/STATUS.md` beside an existing
  `handoff.md` (refmatrix and 9 of 10 fleet projects). Pinned by
  `test_the_status_file_falls_back_to_an_existing_handoff_md`. The carry-over step is in
  #deploy-cleanup step 2.
- **#m-1** accepted and anchored: the live user-level text describes 26.2/26.3 behaviour
  (duplicate-id refusal, `savestates/`, `remove_failed`, the ADR-0005 order) ahead of master and
  0.81.2. Harmless while no live dir has a `.memory-layout` marker or `savestates/`. **No release
  is cut between this merge and 26.2 + 26.3.**
- **#m-2** the warn line and docstring no longer claim which copy Claude Code runs; they say the
  command is defined twice and ask for the project copy's removal.
- **#m-3** `rmx init --agents` help now says commands go to `.claude/commands/` and the handoff
  pair to `~/.claude/commands/`.

## ch-bsd r2 {#r2}

rel: derives-from -> [[bsd-user-level-state-commands-r2-fd06517]]

Round 2 (`9cdee69`): MEH-only 3, all six r1 findings closed or anchored, merge GO. Fixed before
the merge: #m-1-r2 the `{#active-goal}` block goes at the top of the status file's BODY (after any
frontmatter and its H1; the status files are GMD); #m-2-r2 #deploy-cleanup's trunk rule resolves
`origin/HEAD`, else local `main`/`master`, else CLAUDE.md, else refuses, and the printed commit
carries the pathspec and is printed only for a clean tree; #m-3-r2 the project memory's #why and
its `MEMORY.md` hook no longer carry the rejected procedure or the precedence claim.

## Consequences for in-flight work {#in-flight}

The 26.3 branch (`/Volumes/littlebig/refmatrix-plan26-3`) edits both copies of recall-state.
Merging it after this lands needs:

- `.claude/commands/recall-state.md`: modify/delete conflict — keep the deletion.
- `src/refmatrix/templates/commands/recall-state.md`: take this branch's text (it already carries
  AC-7's wording).
- `tests/test_savestate_subfolder.py` AC-7: drop the `.claude/commands/recall-state.md`
  parameter and `test_ac7_the_installed_command_is_the_template` (the project copy no longer
  exists; "installed == template" is now
  `test_handoff_commands_go_to_the_user_dir_and_nowhere_else`). The 26.3 spec's AC-7 and its
  file table name the project copy too.

Other projects that ran `rmx init` before this still hold project-local copies; their next
`rmx init` names them (`warn`) and leaves them for the user to remove.

## Deploy step: remove the fleet's project-local copies {#deploy-cleanup}

User, 2026-11-10: "remove the other projects save-state and recall-state versions when we deploy
the new version of rmx". Not done now: until the release that carries this branch is deployed,
nothing installs or enforces the user-level pair. Do it right after that deploy is verified.

Inventory taken 2026-11-10 (18 files, 9 projects under `~/github/atollogy/bdep/`; every one
differs from the old template, in four content groups):

| project | tracked | content |
|---|---|---|
| `cat-herder` | yes | cat-herder baseline (the bootstrap source: its `SETUP.md` copies `.claude/commands/*.md` into new projects) |
| `orderly` | no | cat-herder baseline |
| `prep_prolific` | yes | cat-herder baseline |
| `thiquet` | yes | cat-herder baseline |
| `portal` | yes | baseline save-state; recall-state names trunk `origin/release` (portal `CLAUDE.md:184` already says there is no `main`) |
| `atldb` | yes | atldb variant |
| `atlftpd` | no | atldb variant |
| `viascope` | no | atldb variant |
| `cliquet` | yes | baseline + GMD frontmatter/anchor only |

Missed by the working-tree scan above (ch-bsd r1 #s-2): **cliquedb** tracks the pair on `main`
and `master` (only its `debitmap-finish` branch dropped it, `4f0f7bc`) and has 5 worktrees, 2
holding copies at depth 8. All 6 tracked fleet repos were on feature branches on 2026-11-10
(atldb `cycle_query_5.0`, portal `datamart`, cat-herder/cliquet/prep_prolific
`gmd-conformance-sweep`, thiquet `nr-native-recast`), so a `git rm` in place would only drop the
pair from those branches.

Procedure (revised after ch-bsd r1 #s-2/#s-3):

1. **Inventory per repo, not per working tree.** For every git repo under `~/github`,
   `~/enduris`, `~/claude_tools` (never from `/`; refmatrix and its littlebig clones are out of
   scope, they get the deletion by merge): its trunk — `origin/HEAD`; else the local `main` or
   `master` that exists; else the line its CLAUDE.md names; refuse that repo if none resolves
   (ch-bsd r2 #m-2-r2: cat-herder, cliquet, prep_prolific and thiquet have no `origin/HEAD`,
   prep_prolific's CLAUDE.md says `main` but only `master` exists, portal's `origin/HEAD` is
   `origin/master`) — `git ls-tree --name-only <trunk> -- .claude/commands/` for the pair, the
   current branch's `git ls-files`, and each `git worktree list` entry's copies. Untracked copies
   come from the `find` scan (`-maxdepth 9` reaches cliquedb's worktrees).
2. **Carry over before deleting (#s-3).** Diff each content group against the user-level pair and
   list every project-specific line. Known on 2026-11-10: "refresh/read `handoff.md`" (covered by
   the status-file chain: CLAUDE.md's file, else `handoff.md`, else `workflow/STATUS.md`, user
   decision 2026-11-10); portal's `origin/release` trunk (already in portal `CLAUDE.md:184`); the
   atldb group's `~/.gstack` checkpoint read (obsolete: gstack checkpoints are gone since
   2026-09-14). Anything else goes into that project's CLAUDE.md, shown to the user first.
3. **Back up** every file to `~/.refmatrix/backups/commands/<project>/` before touching it.
4. **Untracked copies: delete.** **Tracked copies: never stage a delete from here** — a staged
   delete is swept into another session's next pathspec-less commit, and it would land on a
   feature branch. Print per-repo commands for the user to run on each repo's trunk
   (`git -C <repo> switch <trunk> && git rm .claude/commands/{save,recall}-state.md &&
   git commit -m ... -- .claude/commands/{save,recall}-state.md`, plus `git worktree` copies),
   printed only for a repo whose tree is clean, and never switch another repo's branch.
5. **Verify against the trunk trees**, not the working trees: `git ls-tree <trunk>` shows no pair
   in every repo the user has committed, the `find` re-scan shows no untracked copy, and
   `~/.claude/commands/{save,recall}-state.md` equal the deployed templates. Report what is still
   pending the user's commits.
6. cat-herder is the bootstrap source: once its trunk drops the pair, new projects rely on
   `rmx init`'s user-level install. Say so when reporting.
