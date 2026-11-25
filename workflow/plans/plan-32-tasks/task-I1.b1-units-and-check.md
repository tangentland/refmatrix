---
gmd: "0.1"
id: task-I1.b1-units-and-check
title: "Task I1.b1: units, the compiler and compiled file, the fixture runner, replay, and install-hooks --check over every instruction artifact (bug-209)"
tags: [task, plan-32, instructions, units, compiler, fixtures, install-hooks, parity, bug-209]
metadata:
  node_type: task
  status: approved
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task I1.b1: units and the parity gate {#root}

> Status: drafted for the spec window (L232); the lead approves. Part of queue row I1.b
> ([[task-I1.b-substrate#split]]). **Large** (`install-hooks` is a shared path): RED and GREEN
> in separate hands, mutations, one ch-bsd pass. Waits on nothing. It changes no generated hook
> entry, so it needs no install window.

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#units]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#binding]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#fixtures]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#installed-equals-generated]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#layers]]
rel: part-of -> [[task-I1.b-substrate]]
rel: depends-on -> [[bug_registry]]

## Goal {#goal}

A rule has one source file, a **unit**, that carries its binding and the envelopes that prove
it fires. `rmx install-hooks --apply` compiles the units into one file the hooks read;
`--check` proves that every installed instruction artifact equals its render and that every
local unit can fire. {#goal-body}

## What is built {#design}

- **D1 The unit.** One markdown file: GMD frontmatter plus a `unit:` map. {#d1}

  | Key | Values |
  |---|---|
  | `kind` | `deny`, `ask`, `inject`, `check`, `rule`, `skill` |
  | `bind` (a list; one or more) | `event`; `tool`; `match` (one or more pairs of a `tool_input` key, such as `command`, `file_path`, `new_string`, `content`, `subagent_type`, and an ERE; all must match) and `unless` (an ERE that cancels the match); `prefilter` (a literal every matching raw envelope contains); `who` (`any`, `main`, `subagent`, `agent:<type>`); `where` (`any`, `store`, `no-store`, `path:<glob>`); `when` (state: `git-dirty`, `git-head`, each naming its repo and paths); for `inject`, `mode` (`gate`, `context`, `post`) and, for `context`, its `fallback` |
  | `priority`, `census` | packing order; the census rows the unit carries |
  | text | the body, or `from: <skill id>#<anchor>` (copied in at compile) |
  | `fixtures` | `fire` and `pass`, at least one each: an envelope, with optional `repo:` (files, commits, dirty paths, branch) and `store: present \| absent` |
  | `check` only | `on` (`commit`, `merge`, `release`, `stop`, `subagent-stop`) and `run` (a command) |

- **D2 Two layers, one schema.** Packaged units under
  `src/refmatrix/templates/{triggers,checks,rules,skills,practices/<name>}/`; a project's own
  under `.claude/{triggers,checks,rules,skills}/`. {#d2}
- **D3 The compiler.** `--apply` writes `.claude/rmx-instructions.json`: every unit with its
  bindings, text and sha, sorted, and the per-event prefilter. The bytes are the same on every
  run. A unit is **refused**, with the file and the rule named and nothing written, for: an
  unknown key; a missing fixture; text over its type's size
  ([[refmatrix/adr-0007-instruction-architecture#contract]]: reason 600 B, checklist 2,000 B,
  rule 4,000 B, skill body 20,000 B, check message 1,000 B); a `deny` or `ask` whose text
  has no `Instead:` line (the command to run); an id used twice; `ask`, or `context` with no
  fallback, while its probe constant is off; a file it cannot read. {#d3}
- **D4 The fixture runner.** Each envelope goes through the one `decide()` the dispatcher
  calls. `fire` must give the unit's outcome and its raw JSON must contain the unit's
  prefilter; `pass` must give nothing. `repo:` and `store:` states are built in a temp
  directory with real `git`; nothing is patched. {#d4}
- **D5 `--check`, every artifact.** For `.claude/{rules,skills,agents,commands}`, the two
  user-level commands, the compiled file and each `.git/hooks/<name>` that carries the
  refmatrix marker, a file is **generated** (equal to its render), **drift** (a template name
  whose content differs; shown as a diff) or **local** (listed; its fixtures run). The check
  fails on drift in rules, skills and the git hooks (bug-209), on a compiled file that
  differs from a fresh compile (the file is tracked in git, so a clone carries the table),
  and on a failed fixture. {#d5}
- **D6 Agents and commands are classed and printed, not yet failed.** This repo's
  `gmd-curator.md` differs from the template by 56 lines; the nine consumers' copies have not
  been compared, and F6 found ten checksums for `ch-bsd.md`. `--force` still overwrites
  without a backup, so failing on agent drift now would send release step 3 to overwrite
  files in other repos. H1.c turns that drift into an error in the commit that adds
  backup-before-replace. {#agents-leg}
- **D7 `rmx rules replay <unit> [--days 30] [--show]`.** Read-only over `<store>/stm/*.jsonl`
  as files: events scanned, hits, and per hit the session hash, the time and the sha256 of
  the matched text. `--show` prints the text to the terminal only. It prints its limits:
  `detail` is cut at `stm.DETAIL_MAX`; ring events carry no agent id, so a `who`-bound unit's
  count is an upper bound; `when` is not evaluated. Hook plumbing: `verbs.INTERNAL_CLI`. {#d7}

## Acceptance criteria {#acceptance}

Through `rmx install-hooks` and `rmx rules replay` (the dev `rmx`, `tests/devbin.py`), in a
sandbox project under a short `mkdtemp()` root with local units of each kind. New feature, so
one new file named for it, `tests/test_instruction_units.py`; the parity cases extend
`tests/test_hooks_reproducible.py`. {#acceptance-lead}

- **AC-1 Compile.** After `--apply`, the compiled file holds each unit's bindings, text and
  sha and each event's prefilter; a second `--apply` writes identical bytes.
  `test_instruction_units.py::test_apply_compiles_local_units`. {#ac-1}
- **AC-2 A bad unit is refused, loudly.** One parametrized test, a case per refusal in D3
  (a non-UTF-8 file included): `--apply` exits non-zero, stderr names the file and the rule,
  and the compiled file is unchanged. `…::test_apply_refuses[case]`. {#ac-2}
- **AC-3 Every unit proves it can fire.** `…::test_packaged_unit_fixtures[unit/envelope]` is
  parametrized over every packaged unit and a sample directory of one unit per kind, one of
  them stateful. Three planted units must fail: a `fire` envelope its pattern does not match,
  a `fire` envelope missing its own prefilter, a `pass` envelope that fires. {#ac-3}
- **AC-4 The three classes.** After `--apply`: `--check` exits 0 and lists the local files.
  Then, one case each: a generated rule edited → `drift`, the diff, exit 1; a local unit
  edited → the compiled file is out of sync and the line names `--apply`; a local unit's
  `fire` envelope broken → exit 1 naming the unit and the envelope; a packaged agent edited →
  printed as drift, exit 0 (D6). `test_hooks_reproducible.py::test_check_classes[case]`. {#ac-4}
- **AC-5 Git hooks (bug-209).** Install, rewrite one hook body keeping the marker: `--check`
  exits 1 and names it; a hook without the marker is listed, not failed.
  `test_hooks_reproducible.py::test_check_covers_git_hooks`. {#ac-5}
- **AC-6 This repo.** `tests/test_repo_hooks_in_sync.py` compares this checkout's rules,
  skills and compiled file with their render, and prints the agents and commands classes.
  {#ac-6}
- **AC-7 Replay.** On a sandbox store whose ring was written by the generated focus entries
  (three Bash events, one matching): scanned 3, hits 1, a hash and no command text; `--show`
  adds the text; the limits line is printed. `…::test_replay[case]`.
  `tests/test_verb_parity.py`'s `_INTERNAL_SEED` gains `("rules", "replay")`. {#ac-7}
- **AC-8 Mutations that must each fail a test:** the prefilter test dropped from the runner
  (AC-3); a size rule dropped (AC-2); drift classed as local (AC-4); a stale compiled file
  read as in sync (AC-4); the git-hook leg skipped (AC-5); replay printing text without
  `--show` (AC-7). {#ac-8}

## Files {#files}

| File | Change |
|---|---|
| `src/refmatrix/instructions.py` (new) | the unit model, the loader for both layers, `compile`, `decide`, `run_fixtures`, replay |
| `src/refmatrix/hooks.py` | `render_managed` and `check` gain the artifact legs and the git-hook leg; `install` writes the compiled file |
| `src/refmatrix/cli.py`, `src/refmatrix/verbs.py` | a thin `rules` group registration; `INTERNAL_CLI` |
| `src/refmatrix/templates/{triggers,checks,rules,skills,practices}/` | empty packages |
| `tests/test_instruction_units.py` (new), `tests/test_hooks_reproducible.py`, `tests/test_repo_hooks_in_sync.py`, `tests/test_verb_parity.py`; `tests/fixtures/instruction_units/` | the ACs |

## Risks (self-audit) {#risks}

1. **Real:** `--apply` then `--check` in a throwaway project with the dev `rmx`, output
   pasted; the lead runs `rules replay` once against a copy of a live ring directory.
2. **Wiring:** every AC enters through the CLI; `compile` and `decide` are called directly
   only in addition.
3. **Census:** callers of `hooks.check`, `render_managed` and `install`: `rmx install-hooks`,
   `rmx init`, release step 3's fleet check, `tests/test_repo_hooks_in_sync.py`. The nine
   consumers hold no unit: `--check` there stays clean except for a stale git hook body, which
   is bug-209's point and is re-installed with backups ([[orchestration#release]] step 3).
   Both outputs of `--check` (exit code and text) are covered.
4. **Bound:** file reads, plus `git` in temp directories for stateful fixtures, each call
   with a 2 s timeout; the fixture leg is linear in envelopes. No daemon call.
5. **Busy / down:** these legs never call the daemon; AC-4 runs with no daemon up, and RED
   adds one run beside a held writer to show `--check` does not wait on it.
6. **Guard:** each refusal and each class in AC-2 and AC-4 is reached with a real file on
   disk through the CLI.
7. **Loud:** AC-2's exit code and stderr; the non-UTF-8 case is the failure outside the
   parser's own error class.
8. **Handoff:** agent and command drift as an error, with backup-before-replace → H1.c (the
   lead adds the clause to that row). A packaged rule or skill exists twice in this repo
   (source and installed copy) under one GMD id: the graph must see it once →
   [[task-I1.d-first-skills#ac-2]]. bug-209's registry row closes at this merge.

## For the user {#for-the-user}

None. For the lead: D6 narrows the POP row's "`--check` over … agents, commands" to
"classed and printed" until H1.c; say so in the I1.b and H1.c rows.
