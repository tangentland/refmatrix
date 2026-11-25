---
gmd: "0.1"
id: task-I1.c-first-denies
title: "Task I1.c: the first T1 units: seventeen denies and gates, each with fixtures and a 30-day replay"
tags: [task, plan-32, instructions, deny, units, practice-tdd, local-units]
metadata:
  node_type: task
  status: drafting
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task I1.c: the first denies {#root}

> Status: drafted for the spec window (L232); the lead approves. Queue row I1.c.
> Size: **small each** (a unit file and its fixtures; package data and `.claude/`, no code).
> One isolated agent writes the units; the lead runs the replays (they read the live STM
> rings) and reads the diff. Waits on [[task-I1.b3-dispatcher]]. The units are inert until
> install window 1 ([[task-I1.b-substrate#c-window]]).

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#contract]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#layers-l219]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#practice-slots]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#r007-q57]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: derives-from -> [[instruction-census-2026-11-24#build-list]]
rel: depends-on -> [[plan-of-plans#queue]]

## Goal {#goal}

The prohibitions whose violation costs the most stop depending on recall: the call is denied
with the rule and the command to run instead. Each unit proves it fires, proves its
near-misses pass, and is replayed over 30 days of real tool events before it ships. {#goal-body}

## The units {#units}

Layer: **L** a refmatrix local unit under `.claude/triggers/` (Q58 = b, Q61 = a); **T** the
template, `src/refmatrix/templates/triggers/`; **P** `practice/tdd`,
`src/refmatrix/templates/practices/tdd/`. All are `deny` on PreToolUse unless marked gate.
{#units-lead}

| Unit | Layer | Rows | Fires on | Must pass |
|---|---|---|---|---|
| `dev-rmx-live-store` | L | R001 | Bash: `.venv-eval/bin/rmx` or `python -m refmatrix.cli`, target a store tree | the same with `--root <mkdtemp>`; `.venv-eval/bin/python -m pytest` |
| `subagent-store-write` | L | R003 | Bash from a subagent: `rmx` with a write or lifecycle verb (`sync`, `ingest`, `ingest-gmd`, `reingest`, `memory add\|forget\|organise`, `memory compile --apply`, `protect`, `noise`, `forget`, `partition`, `daemon`, `hub`), target a store tree | `scripts/rmx-master context …`; the verb under a `mkdtemp()` root; the main session |
| `no-store-export` | L | R004 | Bash: `export REFMATRIX_ROOT`; `ln -s`, `cp -r` of a `.refmatrix` directory | `cp .refmatrix/catalog.read.duckdb <scratch>` (R005's copy) |
| `deploy-tree-edit` | L | R007 | Edit, Write, MultiEdit: a path under `~/refmatrix/` | a path under the dev tree; a Bash `cp` (Q57 = b) |
| `deploy-venv-editable` | L | R008 | Bash: `~/refmatrix/.venv/bin/pip install` naming the dev tree | `pip install -e ~/refmatrix` |
| `push-from-deploy` | L | R010 | Bash: `git push`, target `~/refmatrix` | a push from the dev tree |
| `deploy-from-master` | L | R011 | Bash: a ref-changing `git` in `~/refmatrix` other than `pull --ff-only origin master`; that pull while the dev tree's `src/` holds uncommitted changes | the pull with a clean `src/`; `git -C ~/refmatrix status` |
| `release-branch-commit` | L | R012 | Bash: `git commit` with HEAD on `release`; a push to `release` | a commit on `master` or a task branch |
| `find-from-root` | T | R021 | Bash: `find`, `fd` or `bfs` with `/` as a root | `find /Volumes/littlebig/x`; `find . -name` |
| `save-state-commit` | L, **gate** | R029 | Bash: `rmx save-state … --commit` | `rmx save-state` |
| `add-all-shared-tree` | L | R030 | Bash: `git add -A`, `--all` or `.`; `git commit -a`; target a store tree | the same in a clone; `git add <path>`; `git commit --amend` |
| `hub-start` | T | R037 | Bash: `rmx hub start` | `rmx hub stop`; `rmx hub status`; `rmx hub relaunch-fleet` |
| `lead-writes-src` | L, **gate** | R134 | Edit, Write from the main session: the project's `src/` or `tests/`, in a store tree | a subagent's edit; `workflow/`; the main session of a clone |
| `version-edit` | L | C7 | Edit, Write of a `version` line in `pyproject.toml` or `src/refmatrix/__init__.py`, from a subagent or in a tree with no store | the main session in the store tree; another line of `pyproject.toml` |
| `test-output-to-file` | P, slot `test-run` | R047 | Bash: a test run with no `tee <file>` and no redirect to a file | `… 2>&1 \| tee <log>`; `--collect-only -q \| tail -1`; `git log \| grep pytest` |
| `no-skipped-groups` | P, slot `test-run` | R048 | Bash: a test run with `--ignore`, `--deselect` or `-k` holding `not` | `-k test_name` |
| `commit-before-mutation` | P, slot `proof` | R065 | Bash: `git checkout -- <path>`, `git restore`, `git stash` while more than one tracked file outside the test paths is modified | the same with one modified file; `git checkout <branch>` |

- **The practice manifest is created here**: `practices/tdd/practice.md`, id `practice-tdd`,
  one anchor per unit, the slots it does not yet fill marked with the task that fills them.
  Until a stack pack supplies `test-runner` and `test-paths` (H1.d), the manifest carries the
  defaults the hand-written script used. {#units-manifest}
- **`hub-start`'s second pattern** (a repeated `launchctl kickstart -k` of the hub) ships
  only if the replay shows its hits are the orphan pile-up form. {#units-hub}
- **`enforce-test-to-file.sh` is deleted in the window-1 commit**, not on this branch: until
  the dispatcher is enabled it is R047's only enforcement
  ([[refmatrix/adr-0007-instruction-architecture#removal-order]]). {#units-script}

## Acceptance criteria {#acceptance}

- **AC-1 Every unit compiles in its layer and proves itself.** Each has at least one `fire`
  envelope and the `pass` envelopes of the table. Packaged units:
  `tests/test_instruction_units.py::test_packaged_unit_fixtures[unit/envelope]`, through the
  generated command. Local units: a new case in the same file,
  `test_this_checkouts_local_units`, compiles `.claude/triggers/` of the checkout and runs
  their fixtures the same way (it runs in a clone). {#ac-1}
- **AC-2 Seen failing first.** Before a unit is written, its `fire` envelope goes through the
  generated command and is not denied; the summary lists the seventeen results. {#ac-2}
- **AC-3 State, not text.** `commit-before-mutation`, `deploy-from-master` and
  `release-branch-commit` carry `repo:` fixtures (two modified files against one; a dirty
  `src/` against a clean one; HEAD on `release` against `master`), built with real `git`.
  {#ac-3}
- **AC-4 Who and where, with the target read from the command.** `subagent-store-write`,
  `add-all-shared-tree`, `lead-writes-src` and `version-edit` each carry a `fire` and a
  `pass` envelope whose `cwd` is the store tree while the command starts `cd <clone> &&`.
  {#ac-4}
- **AC-5 The gap the script had is closed.** `test-output-to-file` denies
  `pytest … 2>&1 | tail -5` and passes the `tee` form and `--collect-only`; no generated
  entry names `enforce-test-to-file.sh` once the window-1 commit removes it
  (`tests/test_hooks_reproducible.py::test_enforce_entries_follow_scripts_on_disk`, which
  already covers a missing script). {#ac-5}
- **AC-6 The two gates pass on the retry.** `lead-writes-src` and `save-state-commit`: the
  first envelope is denied with the rule, the second passes, and the ledger shows `gated`
  then `suppressed_once`. {#ac-6}
- **AC-7 Replayed before it ships.** `workflow/measurements/instruction-replay.md` holds, per
  unit, the events scanned, the hits, their hashes, and a verdict for each hit class: a real
  violation, or a pattern bug that was fixed and replayed again. No unit has an unexplained
  hit at window 1. {#ac-7}
- **AC-8 Every denial says what to run.** Each unit's text is the rule and an `Instead:`
  line, at most 600 B (the compiler refuses otherwise); the lead reads the seventeen texts.
  {#ac-8}
- **AC-9 Nothing else changes.** `rmx install-hooks --check` is clean; no rule text is
  removed from `CLAUDE.md`, the profile, an overlay or a memory (that is I1.h, after the
  units are installed). {#ac-9}

## Files {#files}

`.claude/triggers/<unit>.md` (twelve); `src/refmatrix/templates/triggers/{find-from-root,hub-start}.md`;
`src/refmatrix/templates/practices/tdd/{practice,test-output-to-file,no-skipped-groups,commit-before-mutation}.md`;
`.claude/rmx-instructions.json` (regenerated); `tests/test_instruction_units.py` (one case);
`workflow/measurements/instruction-replay.md`. At window 1, the lead's commit: the option,
`.claude/settings.json`, and the removal of `.claude/hooks/enforce-test-to-file.sh`.
{#files-list}

## Risks (self-audit) {#risks}

1. **Real:** AC-7's replay is the real data; at window 1 the lead provokes one denial of
   each layer in the dev tree and pastes the three reasons.
2. **Wiring:** fixtures go through the generated command, prefilter included.
3. **Census:** each rule's other statements (the census's "stated in" column) are listed in
   the unit's `census` field for I1.h; the sibling forms of each pattern are its `pass`
   envelopes; `git commit -a` and `--all` are both covered.
4. **Bound:** a unit adds a pattern and at most one `git` call under b3's budget.
5. **Busy / down:** units read no daemon; nothing to try.
6. **Guard:** every `where`, `who` and `when` clause has a `fire` and a `pass` envelope that
   differ only in that state (AC-3, AC-4).
7. **Loud:** a deny has no escape hatch, so a bad pattern blocks real work: the replay, the
   near-miss fixtures and AC-8's `Instead:` line are the defence, and a wrong denial after
   window 1 is fixed in the unit, never worked around.
8. **Handoff:** the replay cannot see `who` (ring events carry no agent id) or state, so the
   counts for `subagent-store-write`, `lead-writes-src` and the three stateful units are
   upper bounds, read by hand. `release-branch-commit` is promoted to the template if H1.a
   finds the rule in the consumers' `CLAUDE.md`. The stack parameters move to the python
   pack in H1.d.

## For the user {#for-the-user}

1. **R134 and R029 as gates, not denies.** The lead may make a one-line literal change, and
   `save-state --commit` is only wrong while an agent edits the tree; a hook can see neither.
   A gate denies once with the rule and lets the retry through, and the ledger counts the
   retries. Recommended: gates. The alternative is a hard deny that blocks both allowed
   cases.
2. **R001 denies every dev-venv `rmx` aimed at a live store,** not only one "with a bumped
   version": the hook cannot tell which code the dev tree holds, and the rule's remedy
   (pytest, or a throwaway root) is the same either way. Recommended: deny all. The
   alternative compares the two version strings and lets an equal-version dev `rmx` through.
