---
gmd: "0.1"
id: task-I1.e-first-checks
title: "Task I1.e: the check runner, its two triggers, and the first eleven T4 checks at commit, merge and release"
tags: [task, plan-32, instructions, checks, git-hooks, commit, merge, release, practice-tdd]
metadata:
  node_type: task
  status: approved
  plan: plan-32-instruction-architecture
  created: 2026-11-25
  author: ch-architect (Fable 5.2)
---

# Task I1.e: the first checks {#root}

> Status: written 2026-11-25 for the spec window (L232), against I1.b1 as built (`87a599c4`).
> The lead approves. Queue row I1.e; this is its next task, and [[#later]] lists the rest of
> the row. **Large** (git hooks, hook output and a new verb are shared paths): RED and GREEN
> in separate hands, mutations, one ch-bsd pass. Waits on [[task-I1.b3-dispatcher]]. Its
> triggers go live at install window 2.

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#contract]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#t4-two-triggers]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#practice-slots]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#amend-8]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: depends-on -> [[task-I1.b1-units-and-check#d1]]
rel: depends-on -> [[task-I1.b2-marker-and-ledger#d7]]
rel: depends-on -> [[bsd-open-findings]]
rel: depends-on -> [[plan-of-plans#queue]]

## Goal {#goal}

An obligation that falls due at a commit, a merge or a release is checked there by a
command, not remembered. In the dev tree a failed check stops the commit; in a clone it is
reported on the commit just made, and the merge runs it again, so nothing unfixed merges.
{#goal-body}

## What is built {#design}

- **D1 The runner.** `rmx rules check --on <commit|merge|release>` is a verb (`rules_check`)
  with CLI and MCP adapters. It runs every compiled `check` unit of that event, each `run:`
  from the repository root with `RMX_CHECK_ON`, `RMX_CHECK_FILES` (the files of the commit or
  range, one per line), `RMX_CHECK_RANGE` and `RMX_CHECK_MESSAGE` (a path). Exit 0 passes.
  Any other exit fails with the unit's text and the command's last stderr lines. `merge` also
  runs the `commit` checks over the range's files; `release` runs `commit` and `release`.
  Each failure writes a `check_failed` row and each run one `check_run` row. {#d1}
- **D2 A check never passes by not running.** A command that cannot start, or that outlives
  `CHECK_TIMEOUT_S` (60; a test knob), fails as `could not run`, named. {#d2}
- **D3 Trigger one, the hard stop: a generated `commit-msg` git hook.** It joins
  `hooks.GIT_HOOK_SCRIPTS` (so bug-209's parity leg covers it) and is rendered only when
  `instructions` is enabled and the compiled file holds a check. It reads the event from the
  repository: `merge` when `MERGE_HEAD` exists, `release` when the staged diff changes the
  version line of `pyproject.toml`, else `commit`. A failure prints each failed check and
  exits non-zero. {#d3}
- **D4 Trigger two, for clones: PostToolUse, on `HEAD`.** Git hooks are not cloned. When a
  Bash call matches a check's bind (`git commit`, `git merge`) in a repository with no
  generated `commit-msg` hook, the dispatcher runs the checks on `HEAD` and returns the
  failures as `additionalContext` under `instruction_post`, naming the commit and "amend
  before the lead merges". It is not PreToolUse: `git add … && git commit` and `commit -a`
  stage inside the call, so the index before the call is not the commit
  ([[refmatrix/adr-0007-instruction-architecture#amend-8]]). {#d4}
- **D5 Packaged checks call builtins; local checks call the project's scripts.**
  `rmx rules builtin <name>` (hook plumbing, `verbs.INTERNAL_CLI`) holds the packaged checks'
  logic over git state and files. No builtin calls the daemon. {#d5}
- **D6 Measured before it ships.** Each commit check is run over the commits of the last 90
  days on `master`, and each merge check over its merges; every failure is read as a real
  miss or a check bug. {#d6}

## The first checks {#checks}

Layer: **T** the template (`templates/checks/`); **P** `practice/tdd`
(`templates/practices/tdd/checks/`, slot `completion`); **L** refmatrix's own
(`.claude/checks/`). {#checks-lead}

| Check | Layer | On | Rows | Fails when |
|---|---|---|---|---|
| `gmd-lint` | L | commit | R097, R098 | a `.md` in the lint scope is in the commit and `./scripts/lint-gmd.sh` exits non-zero |
| `pop-in-commit` | T | commit | R113 | the commit is a merge, changes the version line, or changes a plan's `metadata.status`, and `workflow/plan-of-plans.md` is not in it |
| `registry-row` | T | commit | R158 | the message names `bug-NNN` and the registry at this commit has no row for it |
| `fixed-is-reachable` | L | commit | R162 | a registry row newly reads `fixed` with a sha that is not an ancestor of the commit being made, or the commit is not on `master` |
| `no-local-mcp` | L | commit | R033 | `.mcp.json` is in the commit and names `.venv-eval` |
| `impressions-cap` | L | commit | L234; F7 | `IMPRESSIONS.md` is in the commit and is over 50 lines |
| `question-cell` | L | commit | L234; F4 | `OPEN.md` or `CLOSED.md` is in the commit and `scripts/bsd-tally.py` exits non-zero |
| `open-findings` | T | release | L216, L217 | an open BULLSHIT or GATE row of `OPEN.md` is not named in the release message with `ruled L<n>` or `not shipped` |
| `self-audit-section` | T | merge | R144 | neither a summary file added in the range nor the merge message holds the eight self-audit lines |
| `seen-failing` | P | merge | R057; L229, L230 | a test added in the range is not named with its E line in the summary or the merge message (a renamed or strict-xfail test: with its reason) |
| `never-red` | P | merge | R058 | an `xfail` added in the range lacks `strict=True` or a `reason` naming a registry row |

`.claude/rules/bug-registry.md` takes `paths: workflow/bug_registry.md` in the window-2
commit, when `registry-row` goes live, and not before
([[refmatrix/adr-0007-instruction-architecture#removal-order]], L234). Every packaged check
carries `metadata.version: 1.0.0` (L241). {#checks-registry}

## Not in this task {#later}

The rest of the row gets its own spec: the Stop and SubagentStop legs with R144's early form
(it needs one probe of where the SubagentStop envelope holds the agent's last message);
`no-raw-logs` (R044) and P1 (c)'s lints, each measured on real data first. {#later-body}

## Acceptance criteria {#acceptance}

Through the generated `commit-msg` hook in a sandbox git repository with local check units,
through `rmx rules check`, and through the generated PostToolUse command. New feature, one
new file, `tests/test_instruction_checks.py`; hook-config cases extend the existing files.
{#acceptance-lead}

- **AC-1 The hook stops a bad commit.** After `--apply` with a local check that fails when a
  named file is staged: `git commit` with that file exits non-zero and prints the unit's
  text; without it the commit is made. `test_instruction_checks.py::test_commit_msg_hook[case]`.
  {#ac-1}
- **AC-2 The event comes from the repository.** A `--no-ff` merge runs the `merge` checks and
  the `commit` checks over the range; a commit that changes the version line runs `release`
  and `commit`; any other commit runs `commit` only. `…::test_hook_event[case]`. {#ac-2}
- **AC-3 Not running is failing.** A check whose command does not exist, and one that
  outlives the knob-sized timeout, each fail as `could not run`, named, and the commit is
  stopped. `…::test_unrunnable_check_fails[case]`. {#ac-3}
- **AC-4 The hook exists only where a check does.** A project with no check unit renders no
  `commit-msg` hook and `--check` is clean; with one, the hook is rendered, and an edited hook
  body is drift. `tests/test_hooks_reproducible.py::test_check_covers_git_hooks` extended.
  {#ac-4}
- **AC-5 A clone's commit is judged after it is made.** The generated PostToolUse command,
  given a `git commit -am …` envelope in a repository with no generated hook whose `HEAD`
  breaks a check, returns `additionalContext` naming the check and the short sha, and the
  ledger holds `check_failed` and `check_run`. In a repository with the generated hook it
  returns nothing. `tests/test_instruction_dispatch.py::test_post_commit_check[case]`. {#ac-5}
- **AC-6 The command sees the right files.** A local check that prints its environment sees
  the commit's files on `commit`, the range's files and the range on `merge`, and the message
  path. `…::test_check_environment[event]`. {#ac-6}
- **AC-7 Each builtin fails on its state and passes without it.** One parametrized test,
  through `rmx rules check` on a sandbox repository built with real `git`: a failing and a
  passing state for `pop-in-commit`, `registry-row`, `fixed-is-reachable`, `open-findings`,
  `self-audit-section`, `seen-failing` and `never-red`. `…::test_builtin[check/state]`. {#ac-7}
- **AC-8 The packaged and local checks compile and prove their binds.** Each has `fire` and
  `pass` envelopes (`test_packaged_unit_fixtures`, `test_this_checkouts_local_units`); each
  local check's `run:` names a file that exists in this checkout. {#ac-8}
- **AC-9 Measured before window 2.** `workflow/measurements/instruction-check-replay.md`
  holds, per check, the commits or merges scanned, the failures, and a verdict for each: a
  real miss, or a check bug that was fixed and run again. No check has an unexplained
  failure. {#ac-9}
- **AC-10 One verb, two adapters.** `rules_check` is in `verbs.CLI_MAP` with its MCP tool;
  `("rules", "builtin")` is in `INTERNAL_CLI`. `tests/test_verb_parity.py`. {#ac-10}
- **AC-11 Nothing to check, and a broken table.** With no check unit the runner exits 0 and
  says so; with a compiled file it cannot read it exits non-zero and names the file.
  `…::test_runner_edges[case]`. {#ac-11}
- **AC-12 The rows carry no content.** A `check_failed` row holds the unit id, the event and
  the outcome, and no file name or message text. `…::test_check_rows`. {#ac-12}
- **AC-13 The registry rule changes with its check.** The window-2 commit carries the
  `paths:` line on `bug-registry.md`; this branch does not. {#ac-13}

## Mutations {#mutations}

| # | Mutation | Must fail |
|---|---|---|
| M1 | the hook exits 0 after a failed check | AC-1 |
| M2 | `MERGE_HEAD` is not read: a merge runs as a commit | AC-2 |
| M3 | a merge skips the `commit` checks | AC-2 |
| M4 | a command that cannot start counts as passed | AC-3 |
| M5 | no timeout on a check's command | AC-3 |
| M6 | the hook is rendered for a project with no check | AC-4 |
| M7 | the PostToolUse leg runs although the generated hook is installed | AC-5 |
| M8 | the PostToolUse leg reads the index instead of `HEAD` | AC-5 |
| M9 | `RMX_CHECK_FILES` is empty on a merge | AC-6 |
| M10 | each builtin in turn: its condition dropped | AC-7, that builtin's failing state |
| M11 | an unreadable compiled file reads as "no checks" | AC-11 |
| M12 | a file name written to a `check_failed` row | AC-12 |

## Files {#files}

| File | Change |
|---|---|
| a new module beside `instructions.py` | the runner, the event detection, the builtins |
| `src/refmatrix/hooks.py` | the `commit-msg` hook in `GIT_HOOK_SCRIPTS`, rendered by D3's rule |
| `src/refmatrix/instructions.py` or the dispatcher module | D4's PostToolUse leg |
| `src/refmatrix/verbs.py`, `mcp.py`, `cli.py` | `rules_check` and its adapters; `rules builtin` |
| `src/refmatrix/templates/checks/`, `templates/practices/tdd/checks/`, `.claude/checks/` | the eleven units |
| `tests/test_instruction_checks.py` (new), `test_instruction_dispatch.py`, `test_instruction_units.py`, `test_hooks_reproducible.py`, `test_verb_parity.py` | the ACs |
| `workflow/measurements/instruction-check-replay.md` | AC-9 |

## Risks (self-audit) {#risks}

1. **Real:** in a throwaway clone with the dev `rmx`: `--apply`, then a merge commit that
   leaves the POP out; paste the hook's output. AC-9 is the run on real history.
2. **Wiring:** every AC enters through the git hook, the CLI or the generated command.
3. **Census:** every way a commit is made here: `git commit`, `commit -a`, `git add … &&
   git commit` in one call, `--amend`, `git merge --no-ff`, `rmx save-state --commit` (its
   own `git commit` runs the hook). Not covered: `git commit --no-verify` (the merge check
   is its backstop; no deny on the flag is built) and a fast-forward merge (it makes no
   commit; the repository's rule is `--no-ff`). Both outputs of the runner, text and JSON.
4. **Bound:** each command under `CHECK_TIMEOUT_S`; the hook's worst case is that times the
   checks of the event, and AC-9's record gives each check's measured time (`gmd-lint` is
   the long one). The PostToolUse leg stops inside its entry's `timeout` and reports what it
   did not run. No daemon call, no retry.
5. **Busy / down:** the runner and the builtins never call the daemon. RED runs AC-1 with no
   daemon up and once beside C2's held writer: the commit is neither slowed nor stopped.
6. **Guard:** every builtin's failing state is a real repository state (AC-7); D3's two
   event branches are reached by a real merge and a real version edit (AC-2).
7. **Loud:** the hook prints to the terminal and exits non-zero; `could not run` is named;
   the clone leg's text reaches the agent and the ledger. A missing `rmx` in a repository
   that has checks stops the commit with one line naming it.
8. **Handoff:** [[#later]] is the row's next spec. A project's own trunk name or summary
   path changes a packaged check through `amends`, which H1.c builds; until then
   `fixed-is-reachable` is local. The review's two checks are [[#open]] 2.

## Open decisions {#open}

**Answered:** Q80 = a, Q81 = a (the recommendations; L249, 2026-11-25). {#answered}

1. **Where an open finding is refused (L216).** `OPEN.md` rows do not say which branch or
   files they are on, so a merge check could only make every merge name every open row.
   Recommended: enforce at release only, as `open-findings` above, and add a `branch` cell
   to `OPEN.md` if a merge-level refusal is still wanted after a month of rows. The
   alternative is the every-merge form now.
2. **The context review's two checks (L225).** They parse the review record, whose format
   I1.i defines. Recommended: they are units written in I1.i's spec, on this runner. The
   alternative is to fix the record's format here, before I1.i.
