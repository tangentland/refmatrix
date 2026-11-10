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

Procedure:

1. Re-scan, because the list can change before the deploy:
   `find ~/github ~/enduris ~/claude_tools -maxdepth 6 -path '*/_frameworks_and_libraries' -prune
   -o -path '*/.claude/commands/*' \( -name save-state.md -o -name recall-state.md \) -print`
   (never from `/`; refmatrix and its littlebig clones are not in scope, they get the deletion
   by merge).
2. Back up every file to `~/.refmatrix/backups/commands/<project>/` before touching it.
3. Untracked copies: delete. Tracked copies: before any change, check for another session in that
   repo and do not switch its branch; then `git -C <repo> rm` the pair (staged; the user commits
   in their repos unless they say otherwise).
4. cat-herder: deleting its copies also stops new bootstrapped projects getting them; a project
   then relies on `rmx init` (user-level install). Say so when reporting.
5. Verify: `~/.claude/commands/{save,recall}-state.md` equal the deployed templates, and the
   re-scan prints nothing.
