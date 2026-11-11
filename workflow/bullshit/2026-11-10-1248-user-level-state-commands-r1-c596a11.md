---
gmd: "0.1"
id: bsd-user-level-state-commands-r1-c596a11
title: "ch-bsd r1 — /save-state + /recall-state at user level (master..c596a11): DIRTY 6 (0B/3S/3M); merge GO, deploy-cleanup NO-GO as written"
tags: [ch-bsd, commands, save-state, recall-state, init, adr-0005, plan-26, deploy]
severity: SKETCHY
plan: none (direct user request 2026-11-10)
task: task-user-level-state-commands
---

# ch-bsd findings — /save-state and /recall-state install at user level, r1 {#root}

**Range:** `master..c596a11` (`28ef102` feat, `c596a11` docs). Branch
`task-user-level-state-commands`, main dev tree `/Users/tholley/claude_tools/refmatrix`.
**Written:** 2026-11-10T12:48:50-0800
**Author:** Todd Holley / Opus 5.5 / orchestrator (the lead wrote tests and code in one session)
**Files changed:** 15 (2 src, 2 templates, 2 tests, 2 deleted project commands, summary, handoff, 5 logs)

rel: derives-from -> [[impl-task-user-level-state-commands]]
rel: related-to -> [[refmatrix/adr-0005-memory-dir-layout#newest]]
rel: related-to -> [[task-26.3-savestate-subfolder]]

## What was verified {#verified}

- **Reachability.** `rmx init` (cli.py:892-899, `--agents` default on) is the only production
  caller of `install_commands`; it passes no `user_dir`, so the default `user_commands_dir()` =
  `~/.claude/commands/` applies. No other src path assumes the pair lives in
  `<project>/.claude/commands/` (`git grep` over src/tests/scripts/eval at c596a11); the one
  template-path test (`tests/test_save_state.py:244`) reads `src/.../templates/commands/`.
- **RED is honest.** The branch's new test file + amended `test_hooks` test run against a
  `git archive master` copy of `src/` (PYTHONPATH, import path printed): 11 failed, 1 passed,
  same set as the lead's log (`workflow/review-output/bsd-user-level-cmds-r1-red-at-master.log`).
  Ten of the eleven fail on the missing API (TypeError/AttributeError), so the behaviour is
  proven by the mutations, not the RED.
- **Mutations (auditor's own, `bsd-user-level-cmds-r1-mutations.log`).** A no-force gate,
  B overwrite-before-backup, F backup holds the new text, D project-local copy deleted,
  G wrong default dir: all killed (1 test each). **E (rmx init passes the project dir as
  `user_dir`) survived 283 tests** — see [[#s-1]]. Each mutation restored by its own
  `git checkout -- src/...`, `__pycache__` cleared, fix lines grepped back, `git status --short
  src` empty; 36/36 green after (`bsd-user-level-cmds-r1-post-mut.log`).
- **The installed copies.** `~/.claude/commands/{save,recall}-state.md` are byte-equal to the
  c596a11 templates; the user's previous copies sit in `~/.refmatrix/backups/commands/` and a diff
  shows every one of their lines kept (additions plus the memory-before-bridge reorder only).
  The deleted project copies were byte-equal to master's templates.
- **26.3 merge note (#in-flight) is correct.** Merge-sim of `task-26.3-savestate-subfolder`
  onto c596a11 in a scratch clone: exactly two conflicts (DU `.claude/commands/recall-state.md`,
  UU the template). Resolved as the note prescribes (keep the deletion, take ours), exactly the
  two named AC-7 tests fail with `FileNotFoundError` on the deleted copy and the other 18 selected
  pass (`bsd-user-level-cmds-r1-merge-sim-263.log`). 26.3 touches no other command path; 26.2
  touches none.
- **Template vs in-flight code.** 26.2 (`b5a6b0e`): `duplicate_ids: N (neither file written`
  — matches "refused by the bridge, and neither is written". 26.3 (`39bfc4a`): `moved_legacy`,
  `removed_duplicate`, `remove_failed` are printed by cli.py:13683-13699 — matches "moved in or
  removed, and the output says which". On master: `.memory-layout`, the type folders and
  `rmx memory organise` exist (26.1); see [[#m-1]] for the rest.
- GMD lint on the summary and handoff: 0 errors (dangling-doc warnings only, single-file lint).
- Deferral sweep (hard + soft) over the changed files: one hit, the summary's "Not done now"
  for the fleet cleanup; anchored to the user's own timing and to the handoff's "At the next
  deploy" open item.

## Findings {#findings}

### SKETCHY: the only production path, `rmx init` → user level, is untested {#s-1}

**File:** `src/refmatrix/cli.py:898`
**What:** every new test calls `install_commands(..., user_dir=tmp, backup_dir=tmp)` directly.
No test runs `rmx init` and looks at `$HOME/.claude/commands/`.
**Evidence:** mutation E rewrites the call to
`install_commands(project_root=project_root, force=force, user_dir=project_root / '.claude' / 'commands')`
— the pair goes back into the project, which is the exact behaviour the user asked to remove.
283 tests pass (the three files plus every test file that invokes `init`: test_bug178_r2,
test_reingest, test_daemon_restart_cli, test_embed_partition_routing, test_derive_coverage,
test_session_cli, test_verb_parity).
**Fix:** one CliRunner test: `init --path <tmp> --no-hooks` under the sandbox HOME, assert both
files are in `Path.home()/.claude/commands/`, not in `<tmp>/.claude/commands/`, and that the
other packaged commands are in the project. Prove it RED with mutation E.
**Pattern match:** YES — [[bsd-impressions#imp-tests-bypass-wiring]]: tests exercise the
function with injected seams, nothing exercises the call site.

### SKETCHY: the fleet inventory and the `git rm` step miss trunk copies and land on feature branches {#s-2}

**File:** `workflow/implementation_summaries/task-user-level-state-commands.md` `#deploy-cleanup`
**What:** the scan is a working-tree `find` (maxdepth 6), and step 3 `git -C <repo> rm`s the pair
"without switching branches"; step 5 declares done when the re-scan prints nothing.
**Evidence (read-only, 2026-11-10 12:4x):**
- `cliquedb` is not in the 9-project list, yet its `main` and `master` both still track
  `.claude/commands/{save,recall}-state.md`. Only its checked-out `debitmap-finish` dropped them
  (`4f0f7bc`). Its two agent worktrees (`.claude/worktrees/agent-a3a65e4bbd8ed41b7`
  `hotfix-null-caller`, `agent-a7702e3d06af4861a` `hotfix-spawn-adopt`, locked) carry the
  pair at depth 8, which is past the maxdepth.
- All 6 tracked repos are on non-trunk branches right now: atldb `cycle_query_5.0`, portal
  `datamart`, cat-herder / cliquet / prep_prolific `gmd-conformance-sweep`, thiquet
  `nr-native-recast`. For cat-herder, cliquet, prep_prolific, thiquet and cliquedb, the trunk
  (`main`/`master`) tracks the pair. A `git rm` there deletes from a feature branch only. The
  trunk keeps both files, and the next checkout of the trunk brings them back. The working-tree
  re-scan still prints nothing and reports success.
- A staged deletion in a repo another session works in is committed by that session's next
  `git commit` that has no pathspec, inside an unrelated commit
  ([[feedback_save_state_commit_adds_all]]: `rmx save-state --commit` is `git add -A`).
**Fix:** inventory per repo with `git ls-tree <default-branch>` as well as the working tree
(list the worktrees too). Do not stage in a repo you do not own: emit a per-repo command list
for the user, `git rm` + commit on the trunk, after the trunk is checked out by its owner. Make
the verify step check the trunk tree, not the working tree.
**Pattern match:** YES — [[bsd-impressions#imp-deploy-reaches-fleet]] (a fleet action checked
on the checked-out state only).

### SKETCHY: deleting the fleet copies drops project instructions the user-level text does not carry {#s-3}

**File:** `src/refmatrix/templates/commands/{save,recall}-state.md` "Project conventions"; summary `#deploy-cleanup`
**What:** the summary sorts the 18 copies into four content groups, then backs up and deletes all
of them. It never compares what each group says against the user-level text.
**Evidence:** cat-herder baseline group, plus portal and cliquet: save-state says "Also refresh
`handoff.md` (this project's session-context file)", and recall-state says "read `handoff.md`". The
atldb group (atldb, atlftpd, viascope): recall-state reads "the newest checkpoint in
`~/.gstack/projects/<project>/checkpoints/`". The user-level text names neither. Its default
"Status file — `workflow/STATUS.md`" exists in 1 of the 11 projects checked (cliquedb, where the
text came from). refmatrix and all 9 fleet projects have `handoff.md` and no `workflow/STATUS.md`.
Step 3a then says "If the project has no status file yet, create it". So after the cleanup, the
first `/save-state` in each of those projects creates a second session file next to the
`handoff.md` that its CLAUDE.md names. That already applies to refmatrix on this branch.
**Fix (user decision):** either the conventions line names the fallback ("`workflow/STATUS.md`;
if absent, the handoff file the CLAUDE.md names, e.g. `handoff.md`"), or the cleanup adds a
"Status file:" line to each project's CLAUDE.md before the delete. Either way the procedure gets
a step: diff each group's copy against the user-level text and carry over every
project-specific line (or record why it is dropped) before the delete.
**Pattern match:** YES — [[bsd-impressions#imp-copy-measures-the-copy]] (the inventory counted
the files, not what they say).

### MEH: the template already describes 26.2/26.3 behaviour, live, ahead of master and the deploy {#m-1}

**What:** these claims are not on master or the deployed 0.81.2:
- the duplicate-id refusal (26.2);
- "the handoff lands in `savestates/<id>.md`", the moved/removed output and `remove_failed` (26.3);
- "the newest save-state (`savestates/`, legacy top-level)" (26.3);
- "Resume from the handoff `rmx recall-state` names" under the ADR-0005 `updated → mtime → name`
  order. Master `handoff.py:491` globs top-level `savestate_*.md` and sorts by mtime only.

The lead's 12:33 `force=True` install made this text live in `~/.claude/commands/` for every
project. The summary does not say which claims are in flight.
**Risk now:** low. No live memory dir has a `.memory-layout` marker or a `savestates/` folder,
so no live run hits the divergent paths.
**Anchor:** the handoff lists 26.2 and 26.3 under "Before the next release". The text is only
coherent if this branch ships in the same release as both. Note that in the summary, and do not
cut a release from master between this merge and 26.2/26.3.

### MEH: the "project copy runs instead of the user copy" precedence is asserted, not measured {#m-2}

**File:** `src/refmatrix/init_agents.py` docstring + the `warn` line; summary `#changed`
**What:** the warn says to remove the project copy "so `~/.claude/commands/<name>` is the one that
runs here". The docstring says the project copy "would run instead of the user-level one". Nobody
probed Claude Code's precedence for a same-named user and project command (`/help` with both
present). If the user copy wins, the warn's reason is wrong, though removing the copy is still
right.
**Fix:** probe it once and cite the probe, or word it neutrally ("two copies of /save-state; the
project one shadows or duplicates the user-level one — remove it").

### MEH: `rmx init` now writes outside the project, and its help does not say so {#m-3}

**File:** `src/refmatrix/cli.py:844-846`
**What:** `--agents/--no-agents` is the only opt-out from the `~/.claude/commands/` write. Its help
still reads "Place packaged subagent descriptions … into .claude/agents/". Only `--force`'s help
mentions the user-level files. Someone running `rmx init` in a scratch directory has no signal that
it touches their home directory (the yellow `skip` line prints only when a copy differs).
**Fix:** one help-text clause on `--agents` ("and slash commands: the project's, plus
`/save-state` and `/recall-state` in `~/.claude/commands/`").

## Verdict {#verdict}

DIRTY, 6 findings (0 BULLSHIT, 3 SKETCHY, 3 MEH).

- **Merge: GO.** The code is live from `rmx init`, the contracts hold under 5 of 6 auditor
  mutations, the RED is honest and the 26.3 note checks out. S-1 is a single CliRunner test that
  closes the wiring gap; doing it before merging is recommended (cheap), not required.
- **#deploy-cleanup as written: NO-GO.** S-2 (trunk copies and feature-branch staging) and S-3
  (instructions lost, a status-file default that matches 1 of 11 projects) need the procedure
  amended and a user decision on the status-file fallback, before the deploy that runs it.

rel: contradicts -> [[feedback_shared_tree_no_branch_switch]]
rel: evidence-for -> [[impression_bsd_tests_bypass_wiring]]
