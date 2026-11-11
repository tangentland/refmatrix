---
gmd: "0.1"
id: bsd-user-level-state-commands-r2-fd06517
title: "ch-bsd r2 — user-level state commands remedy (fa38500..fd06517): MEH-only 3 (0B/0S/3M); r1 6/6 closed; merge GO"
tags: [ch-bsd, commands, save-state, recall-state, init, deploy, remedy]
severity: MEH
plan: none (direct user request 2026-11-10)
task: task-user-level-state-commands
---

# ch-bsd findings — user-level state commands, r2 (remedy) {#root}

**Range:** `fa38500..fd06517` (one remedy commit). Branch `task-user-level-state-commands`,
main dev tree `/Users/tholley/claude_tools/refmatrix`.
**Written:** 2026-11-10T16:39:19-0800
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 10 (cli.py, init_agents.py, 2 templates, 1 test file, summary, 4 logs)

rel: derives-from -> [[bsd-user-level-state-commands-r1-c596a11]]
rel: related-to -> [[impl-task-user-level-state-commands#remedy-r1]]

## r1 closure {#closure}

| r1 | status | evidence |
|----|--------|----------|
| [[bsd-user-level-state-commands-r1-c596a11#s-1]] | closed | `test_rmx_init_installs_the_pair_at_user_level` (CliRunner `init --path`, `HOME` monkeypatched) is green. **My own mutation E** (init passes the project's `.claude/commands` as `user_dir`) now fails it with `FileNotFoundError` on `<home>/.claude/commands/save-state.md` (`bsd-user-level-cmds-r2-mutations.log`). |
| [[bsd-user-level-state-commands-r1-c596a11#s-2]] | closed | `#deploy-cleanup` now inventories trunk trees and worktrees, never stages a delete, prints commands for the user, and verifies trunk trees. The cliquedb facts match my r1 read (main/master track the pair, `4f0f7bc`). Residue in [[#m-2-r2]]. |
| [[bsd-user-level-state-commands-r1-c596a11#s-3]] | closed | Both templates now use the status-file chain "CLAUDE.md's file → `handoff.md` if it exists → `workflow/STATUS.md`". Every fleet project and refmatrix has `handoff.md`, so none gets a second session file. Pinned by the parametrized test; my mutation (swap the chain to STATUS.md before handoff.md) fails it. Carry-over is step 2. The gstack claim holds: `~/.gstack` does not exist. Residue in [[#m-1-r2]]. |
| [[bsd-user-level-state-commands-r1-c596a11#m-1]] | anchored | summary `#remedy-r1`: "No release is cut between this merge and 26.2 + 26.3". |
| [[bsd-user-level-state-commands-r1-c596a11#m-2]] | closed | The warn line ("remove it so the command is defined once") and the docstring ("was not probed") no longer claim a precedence. The memory's `#why` still does — see [[#m-3-r2]]. |
| [[bsd-user-level-state-commands-r1-c596a11#m-3]] | closed | `--agents` help names `.claude/commands/` and `~/.claude/commands/`. No generated artifact copies the help string (`git grep`). |

Also verified:
- 205 passed across the installer, test_hooks, test_save_state and test_verb_parity files
  (`bsd-user-level-cmds-r2-green.log`).
- The installed `~/.claude/commands/` pair is byte-equal to the fd06517 templates. The 16:36
  backups are byte-equal to the c596a11 templates, i.e. the previous install.
- Both mutations were restored in their own commands, `__pycache__` cleared and the fix lines
  grepped back. `git status --short src tests` is empty, and 39/39 pass after
  (`bsd-user-level-cmds-r2-post-mut.log`).
- Summary lint: 0 errors.

## Findings {#findings}

### MEH: "at the top of the status file" now means the top of a GMD file {#m-1-r2}

**File:** `src/refmatrix/templates/commands/save-state.md:48,62`, `recall-state.md:33`
**What:** under the new chain, the status file is `handoff.md` in refmatrix and in every fleet
project. Five of the six heads I read open with GMD frontmatter (refmatrix, cat-herder, cliquet,
prep_prolific, portal, atldb; thiquet does not). Step 3a still says "Write/refresh the
`{#active-goal}` block at the top of the status file". Read literally, the block goes before
`---`, and the frontmatter is no longer first in the file. refmatrix's Handoff Rotation also
archives `handoff.md` each session, so the block moves with it unless save-state rewrites it.
**Fix:** "at the top of the body (after any frontmatter and the H1)". The rotation needs no
change: save-state already re-writes the block every session.

### MEH: the revised procedure's trunk rule does not resolve 4 of the 6 tracked repos as written {#m-2-r2}

**File:** `workflow/implementation_summaries/task-user-level-state-commands.md` `#deploy-cleanup` steps 1 and 4
**What:** the rule is "trunk = `origin/HEAD`, else the line its CLAUDE.md names".
- cat-herder, cliquet, prep_prolific and thiquet have no `origin/HEAD`.
- prep_prolific's CLAUDE.md:165 says "Merge to main", but the repo has only `master`. So
  `git ls-tree main` errors there.
- The rule's own example, "e.g. portal's", points at `origin/release`, but portal has
  `origin/HEAD = origin/master`, which wins under the stated order.
- Step 4's command for the user is `switch <trunk> && git rm … && git commit -m …`. That commit has
  no pathspec, so it sweeps in anything the user already had staged.

All of these fail loudly or are run by the user, so none is silent.
**Fix:** resolve the trunk as `origin/HEAD`, else the local `main`/`master` that exists, else the
CLAUDE.md line. Refuse when none resolves, and drop the portal example or state the order it
assumes. Use `git commit -m … -- .claude/commands/save-state.md .claude/commands/recall-state.md`,
and print the command only for a repo whose tree is clean.

### MEH: the project memory and its index line still carry the r1 wording {#m-3-r2}

**File:** `~/.claude/projects/-Users-tholley-claude-tools-refmatrix/memory/MEMORY.md:125`;
`project_deploy_removes_fleet_handoff_commands.md` `#why` (read-only for the auditor)
**What:**
- The index hook still reads "back up, git rm tracked, user commits". That is the r1 procedure
  #s-2 rejected, and it loads into every session.
- `#why` says a project-local copy "keeps that project on its own stale text instead of the
  user-level version". That is the precedence claim #m-2 removed from the code as unprobed.

`#how` matches the new procedure.
**Fix:** hook → "back up; per-repo trunk commands for the user; never stage". In `#why`, say the
project then defines the command twice.

## Verdict {#verdict}

MEH-only, 3 findings (0 BULLSHIT, 0 SKETCHY, 3 MEH). r1: 6 of 6 closed or anchored.

- **Merge: GO.**
- **#deploy-cleanup: GO** once [[#m-2-r2]]'s trunk rule is fixed. The procedure runs at the next
  deploy, not at merge, so this does not block the merge.

rel: evidence-for -> [[impression_bsd_tests_bypass_wiring]]
