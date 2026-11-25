---
gmd: "0.1"
id: task-I1.c-first-denies
title: "Task I1.c: the first T1 units: fifteen denies and one gate, each with fixtures and a 30-day replay"
tags: [task, plan-32, instructions, deny, units, practice-tdd, local-units]
metadata:
  node_type: task
  status: approved
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  updated: 2026-11-25
  author: ch-architect (Fable 5.2)
---

# Task I1.c: the first denies {#root}

> Status: rewritten 2026-11-25 for the spec window (L232) against I1.b1 as built (`87a599c4`),
> the probe verdicts (L240) and the user's answers (L242, L243). The lead approves.
> Queue row I1.c. Size: **small each** (a unit file and its fixtures; package data and
> `.claude/`), with one `src/` clause ([[#d3]]). One isolated agent writes the units; the lead
> runs the replays (they read the live STM rings) and reads the diff. Waits on
> [[task-I1.b3-dispatcher]]. The units are inert until install window 1
> ([[task-I1.b-substrate#c-window]]).

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#contract]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#layers-l219]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#practice-slots]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#r007-q57]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: derives-from -> [[instruction-census-2026-11-24#build-list]]
rel: depends-on -> [[task-I1.b1-units-and-check#d1]]
rel: depends-on -> [[plan-of-plans#queue]]

## Goal {#goal}

The prohibitions whose violation costs the most stop depending on recall: the call is denied
with the rule and the command to run instead. Each unit proves it fires, proves its
near-misses pass, and is replayed over 30 days of real tool events before it ships. {#goal-body}

## The units {#units}

Layer: **L** a refmatrix local unit, `.claude/triggers/` (Q58 = b, Q61 = a); **T** the
template, `src/refmatrix/templates/triggers/`; **P** `practice/tdd`,
`src/refmatrix/templates/practices/tdd/triggers/`. All are `deny` on PreToolUse except the
gate. R029 is gone: `save-state --commit` now stages only its own paths (L242, bug-320).
{#units-lead}

| Unit | Layer | Rows | Fires on | Must pass |
|---|---|---|---|---|
| `dev-rmx-live-store` | L | R001 | Bash: `.venv-eval/bin/rmx` or `python -m refmatrix.cli`, in a store tree, bumped or not (L243) | the same with `--root <mkdtemp>`; `.venv-eval/bin/python -m pytest` |
| `subagent-store-write` | L | R003 | Bash from a subagent: `rmx` with a write or lifecycle verb (`sync`, `ingest`, `ingest-gmd`, `reingest`, `memory add\|forget\|organise`, `memory compile --apply`, `protect`, `noise`, `forget`, `partition`, `daemon`, `hub`), in a store tree | `scripts/rmx-master context …`; the verb under a `mkdtemp()` root; the main session |
| `no-store-export` | L | R004 | Bash: `export REFMATRIX_ROOT`; `ln -s`, `cp -r` of a `.refmatrix` directory | `cp .refmatrix/catalog.read.duckdb <scratch>` (R005's copy) |
| `deploy-tree-edit` | L | R007 | Edit, Write, MultiEdit: a `file_path` under the home-level `refmatrix/` | a path under the dev tree; a Bash `cp` (Q57 = b) |
| `deploy-venv-editable` | L | R008 | Bash: the deploy venv's `pip install` naming the dev tree | `pip install -e ~/refmatrix` |
| `push-from-deploy` | L | R010 | Bash: `git push` in a command that names the deploy tree (`-C`, `cd`) | a push from the dev tree |
| `deploy-from-master` | L | R011 | Bash: a ref-changing `git` in the deploy tree other than `pull --ff-only origin master` | that pull; `git -C ~/refmatrix status` |
| `release-branch-commit` | L | R012 | Bash: `git checkout` or `switch` to `release`; a push whose target is `release` | `git checkout master`; a branch named `release-notes` |
| `find-from-root` | T | R021 | Bash: `find`, `fd` or `bfs` with `/` as a root | `find /Volumes/littlebig/x`; `find . -name` |
| `add-all-shared-tree` | L | R030 | Bash: `git add -A`, `--all` or `.`; `git commit -a`; in a store tree | the same in a clone; `git add <path>`; `git commit --amend` |
| `hub-start` | T | R037 | Bash: `rmx hub start` | `rmx hub stop`; `rmx hub status`; `rmx hub relaunch-fleet` |
| `lead-writes-src` | L, **gate** | R134 | Edit, Write from the main session: the project's `src/` or `tests/`, in a store tree (L243) | a subagent's edit; `workflow/`; the main session of a clone |
| `version-edit` | L | C7 | Edit or Write of a `version` line in `pyproject.toml` or `src/refmatrix/__init__.py`, from a subagent or in a tree with no store | the main session in the store tree; another line of `pyproject.toml` |
| `test-output-to-file` | P, slot `test-run` | R047 | Bash: a test run with no `tee <file>` and no redirect to a file | `… 2>&1 \| tee <log>`; `--collect-only -q \| tail -1`; `git log \| grep pytest` |
| `no-skipped-groups` | P, slot `test-run` | R048 | Bash: a test run with `--ignore`, `--deselect` or `-k` holding `not` | `-k test_name` |
| `commit-before-mutation` | P, slot `proof` | R065 | `ch-test-engineer` changing a tracked file outside the test paths (Edit, Write, or a Bash in-place edit) while such a file already differs from HEAD | the same with a clean tree; an edit under `tests/`; another agent type |

- **D1 State is kept out where text will do.** As built, `when:` has two states, and neither
  reads a branch name or a count; `where: path:` matches the envelope's `cwd` with a glob
  that cannot tell `~/refmatrix` from `~/claude_tools/refmatrix`. So the deploy-tree and
  `release` units match the command or the file path, and only `commit-before-mutation`
  carries a state (`git-dirty` outside the test paths). No change to the unit format. {#d1}
- **D2 The practice pack starts here.** `practices/tdd/practice.md` (id `practice-tdd`, one
  anchor per unit, each unfilled slot marked with the task that fills it) and three units.
  Until a stack pack supplies the test runner and test paths (H1.d), the units carry the
  literals the hand-written script used. Every packaged unit carries
  `metadata.version: 1.0.0` (L241). {#d2}
- **D3 One clause for the dispatcher.** For a file tool, `where` and `when` are judged in the
  directory of `file_path`: a subagent's envelope carries the dev tree's `cwd` while it edits
  a clone. It is built in I1.b3 if that has not merged, else here, on the small path. {#d3}
- **D4 `hub-start`'s second pattern** (a repeated `launchctl kickstart -k` of the hub) ships
  only if the replay shows its hits are the orphan pile-up form. {#d4}
- **D5 `enforce-test-to-file.sh` is deleted in the window-1 commit**, not on this branch:
  until the dispatcher is enabled it is R047's only enforcement
  ([[refmatrix/adr-0007-instruction-architecture#removal-order]]). {#d5}

## Acceptance criteria {#acceptance}

- **AC-1 Every unit compiles in its layer and proves itself.** Each has at least one `fire`
  envelope and the `pass` envelopes of the table. Packaged units:
  `tests/test_instruction_units.py::test_packaged_unit_fixtures[unit/envelope]`, through the
  generated command. Local units: a new case in the same file,
  `test_this_checkouts_local_units`, compiles `.claude/triggers/` of the checkout and runs
  their fixtures the same way (it runs in a clone). {#ac-1}
- **AC-2 Seen failing first.** Before a unit is written, its `fire` envelope goes through the
  generated command and is not denied; the summary lists the sixteen results. {#ac-2}
- **AC-3 State, not text.** `commit-before-mutation` carries `repo:` fixtures built with real
  `git`: a `fire` with one tracked non-test file already modified, a `pass` with a clean
  tree, and a `pass` with only a file under `tests/` modified. {#ac-3}
- **AC-4 Who and where, with the target read from the call.** `subagent-store-write` and
  `add-all-shared-tree` each carry a `fire` and a `pass` envelope whose `cwd` is the store
  tree while the command starts `cd <clone> &&`; `lead-writes-src`, `version-edit` and
  `commit-before-mutation` each carry a pair whose `cwd` is the store tree while `file_path`
  is in a clone. {#ac-4}
- **AC-5 The gap the script had is closed.** `test-output-to-file` denies
  `pytest … 2>&1 | tail -5` and passes the `tee` form and `--collect-only`; no generated
  entry names `enforce-test-to-file.sh` once the window-1 commit removes it
  (`tests/test_hooks_reproducible.py::test_enforce_entries_follow_scripts_on_disk`, which
  already covers a missing script). {#ac-5}
- **AC-6 The gate passes on the retry.** `lead-writes-src`: the first envelope is denied with
  the rule, the second passes, and the ledger shows `gated` then `suppressed_once`. {#ac-6}
- **AC-7 Replayed before it ships.** `workflow/measurements/instruction-replay.md` holds, per
  unit, the events scanned, the hits, their hashes, and a verdict for each hit class: a real
  violation, or a pattern bug that was fixed and replayed again. No unit has an unexplained
  hit at window 1. {#ac-7}
- **AC-8 Every denial says what to run.** Each unit's text is the rule and an `Instead:`
  line, at most 600 B (the compiler refuses otherwise); the lead reads the sixteen texts.
  {#ac-8}
- **AC-9 Nothing else changes.** `rmx install-hooks --check` is clean; no rule text is
  removed from `CLAUDE.md`, the profile, an overlay or a memory (that is I1.h, after the
  units are installed). {#ac-9}
- **AC-10 A file tool is judged where its file is.** A unit bound `where: no-store` on Edit:
  an envelope whose `cwd` is a store tree and whose `file_path` is in a directory with no
  store fires; the reverse does not.
  `tests/test_instruction_dispatch.py::test_deny_who_where[file-tool]`. {#ac-10}
- **AC-11 What the replay cannot see is said.** For `version-edit` the replay names its
  `new_string` and `content` binds as unmeasurable (bsd-i1b1 r1 b-1); the record then holds
  every Edit and Write of the two files in the window, read by hand. For every `who`-bound
  and stateful unit the record says its count is an upper bound. {#ac-11}

## Mutations {#mutations}

| # | Mutation | Must fail |
|---|---|---|
| M1 | the file-tool clause removed: `where` and `when` read the envelope's `cwd` | AC-10 |
| M2 | in any one unit, the token that separates its `fire` from a `pass` envelope is removed from `match` or `unless` | that unit's `pass` envelope in AC-1 |

## Files {#files}

`.claude/triggers/<unit>.md` (eleven); `src/refmatrix/templates/triggers/{find-from-root,hub-start}.md`;
`src/refmatrix/templates/practices/tdd/practice.md` and
`practices/tdd/triggers/{test-output-to-file,no-skipped-groups,commit-before-mutation}.md`;
`.claude/rmx-instructions.json` (regenerated); `tests/test_instruction_units.py` (one case);
`src/refmatrix/instructions.py` and `tests/test_instruction_dispatch.py` (D3, if not in
I1.b3); `workflow/measurements/instruction-replay.md`. At window 1, the lead's commit: the
option, `.claude/settings.json`, and the removal of `.claude/hooks/enforce-test-to-file.sh`.
{#files-list}

## Risks (self-audit) {#risks}

1. **Real:** AC-7's replay is the real data; at window 1 the lead provokes one denial of
   each layer in the dev tree and pastes the three reasons.
2. **Wiring:** fixtures go through the generated command, prefilter included.
3. **Census:** each rule's other statements (the census's "stated in" column) are listed in
   the unit's `census` field for I1.h; the sibling forms of each pattern are its `pass`
   envelopes; `git commit -a` and `--all` are both covered. A session started inside the
   deploy tree is not covered by the text patterns: a bare `git push` there passes.
4. **Bound:** a unit adds a pattern; only `commit-before-mutation` adds one `git` call, under
   I1.b1's 2 s bound and I1.b3's budget.
5. **Busy / down:** units read no daemon; nothing to try.
6. **Guard:** every `where`, `who` and `when` clause has a `fire` and a `pass` envelope that
   differ only in that state (AC-3, AC-4).
7. **Loud:** a deny has no escape hatch, so a bad pattern blocks real work: the replay, the
   near-miss fixtures and AC-8's `Instead:` line are the defence, and a wrong denial after
   window 1 is fixed in the unit, never worked around.
8. **Handoff:** `release-branch-commit` is promoted to the template if the consumers'
   `CLAUDE.md` carry the rule (H1.b reads them). The runner and path literals move to the
   python pack in H1.d. A commit made on `release` by a route that never checks it out is
   not caught until `when:` can read a branch.

## Open decisions {#open}

None. L242 and L243 decide R029, R134 and R001.
