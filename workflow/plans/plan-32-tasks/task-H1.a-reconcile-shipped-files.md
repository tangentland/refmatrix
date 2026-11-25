---
gmd: "0.1"
id: task-H1.a-reconcile-shipped-files
title: "Task H1.a: the nine files both installers ship, reconciled to one project-neutral copy each in the template"
tags: [task, plan-32, h1, templates, cat-herder, install, parity]
metadata:
  node_type: task
  status: approved
  plan: plan-32-instruction-architecture
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# Task H1.a: reconcile the doubly-shipped files {#root}

> Status: drafted for the spec window (L232, L233); the lead approves. Queue row H1.a.
> Size: **small** (package data and two tests; no code). One agent in a littlebig clone, not
> an isolated `rmxtestN` user: it reads the cat-herder checkout, which another macOS user
> cannot. The lead reads the diff. Waits on nothing.

rel: implements -> [[refmatrix/cat-herder-merge-2026-11-24#ev-two-scaffolders]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#layers]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: derives-from -> [[plan-32-retriage-2026-11-24#h1-tasks]]
rel: depends-on -> [[plan-of-plans#queue]]

## Goal {#goal}

`rmx init` and cat-herder's `install.sh` each ship `gmd-curator.md` and eight session
commands, and all nine differ. After this task `src/refmatrix/templates/` holds the one copy
of each, project-neutral, and this repo's installed copies equal it. H1.b's cores and every
later parity check start from that. {#goal-body}

## Measured at `4f7d17b5`, against cat-herder `87f9d51` {#measured}

cat-herder is `~/github/atollogy/bdep/cat-herder`; its nine files are clean at that sha (other
files in its tree are modified, so read the sha, never the working copy). {#measured-lead}

| File | Template | cat-herder | Lines that differ | What differs |
|---|---|---|---|---|
| `agents/gmd-curator.md` | 725 lines | 757 | 80 | the template has the newer curator spool and token drains (task 3.7); cat-herder has GMD frontmatter and anchors, the overlay section, the raw-`git` and wrapped-read sections |
| `commands/save-state.md`, `recall-state.md` | 74, 65 | 39, 33 | 73, 58 | the template's are the 2026-11-10 user-level rewrite with the memory-dir rules; cat-herder's are the older per-project text |
| `commands/commit-state.md` | 33 | 43 | 14 | cat-herder adds frontmatter keys, a heading and a "requires `rmx`" note; **the template names `~/refmatrix` and `rmx daemon restart` in its deploy step** |
| `commands/detour.md`, `return.md`, `stash.md`, `stash-list.md`, `stash-pop.md` | 15 to 33 | 24 to 43 | 9 or 10 each | the same frontmatter keys, heading and note |

Two more copies of the curator exist: this repo's `.claude/agents/gmd-curator.md` (47 lines
from the template: GMD frontmatter, the read-only MCP tools of Q15, the overlay section) and
`~/.claude/agents/gmd-curator.md` (dated 2026-10-02, 78 lines from the template). The
template's curator also names `~/claude_tools/gmd/lint.py` four times, a path on one machine.
{#measured-more}

## What is built {#design}

- **D1 One rule per hunk.** For each differing hunk: the newer **mechanism** wins (the spool
  and token text, the user-level save and recall text); the **neutral** wording wins over a
  project's (the deploy sentence, the lint path becomes `tools/gmd/lint.py`); text only one
  side has is kept if it is neutral (the raw-`git` and wrapped-read sections) and dropped if
  it is moot (the "requires `rmx`" notes: the template now ships with rmx). {#d1}
- **D2 Command frontmatter.** A key cat-herder adds (`name`, `argument-hint`,
  `allowed-tools`, `model`, `enabled`) is kept only if the Claude Code docs list it for a
  command file; the summary cites the page. `allowed-tools` is kept only where the command's
  own steps fit inside it. {#d2}
- **D3 The curator is a GMD doc** in the template, as both live copies already are:
  frontmatter with `id: gmd-curator`, an anchor on every heading. It carries the read-only
  refmatrix MCP tools in `tools:` (Q15, L85) and keeps the overlay section, because I1.a's
  `gmd-curator.local.md` is read through it until H1.c delivers overlays by preload. Its
  backgrounded-ingest section is not changed (Q58 = b). {#d3}
- **D4 This repo is an instance.** `.claude/agents/gmd-curator.md` and the six project-level
  commands are re-installed from the template; the curator differs from it only in its `id:`
  line (`refmatrix/gmd-curator`). The two user-level commands are already equal. {#d4}
- **D5 Nothing else moves.** The installer's behaviour (skip an existing file, back up a
  user-level one on `--force`) is not changed; the other agents and commands are H1.b's; the
  nine consumers' copies are H1.f's. {#d5}

## Acceptance criteria {#acceptance}

- **AC-1 The packaged files are project-neutral, and the guard can fail.**
  `tests/test_hooks.py::test_packaged_templates_hold_no_project_specifics` reads every packaged
  agent and command for `~/claude_tools`, `~/refmatrix`, `.venv-eval` and the user's name; a
  planted line fails it. RED at base: five sites (`commit-state.md:24`, four
  in `gmd-curator.md`). {#ac-1}
- **AC-2 This checkout equals the template.** A new case in
  `tests/test_repo_hooks_in_sync.py` compares each installed file that has a packaged name
  with the package's bytes, the frontmatter `id:` line excepted; it runs in a clone. RED at
  base: `gmd-curator.md`. A planted one-line edit fails it. {#ac-2}
- **AC-3 Every hunk is accounted for.** The summary holds one row per differing hunk of the
  nine files at the two shas above: which side won, by which rule of D1 or D2. The lead reads
  it; no hunk is "merged" without a row. {#ac-3}
- **AC-4 The installer still behaves.** `tests/test_install_commands_user_level.py` and
  `tests/test_hooks.py` pass unchanged: the two session commands install at user level, a
  differing copy is kept unless `--force`, and `--force` backs it up. {#ac-4}
- **AC-5 Run for real.** `rmx init` (the dev `rmx`) in a throwaway project under a sandbox
  HOME installs seven project files and two user-level files; the summary pastes the list. {#ac-5}
- **AC-6 The gates.** `./scripts/lint-gmd.sh` exits 0; the verify set is the three test files
  above plus the nine repo guards. {#ac-6}

## Files {#files}

`src/refmatrix/templates/agents/gmd-curator.md`; `src/refmatrix/templates/commands/*.md`
(eight); `.claude/agents/gmd-curator.md`; `.claude/commands/{commit-state,detour,return,stash,stash-list,stash-pop}.md`;
`tests/test_hooks.py`, `tests/test_repo_hooks_in_sync.py`. No `src/**/*.py`. {#files-list}

## Risks (self-audit) {#risks}

1. **Real:** AC-5.
2. **Wiring:** AC-2 and AC-4 go through `install_agents` / `install_commands` and
   `rmx init`, the paths a project uses.
3. **Census:** the copies of each file: the template, cat-herder, this repo's `.claude/`,
   `~/.claude/commands/` (two), `~/.claude/agents/gmd-curator.md`, and the nine consumers
   (not compared here; F6 counted ten checksums for `ch-bsd.md`). Readers of the curator's
   anchors: `grep -rn "gmd-curator#"` over `workflow/` and `docs/`, listed in the summary.
4. **Bound:** not applicable: no call is added.
5. **Busy / down:** not applicable.
6. **Guard:** AC-1 and AC-2 each plant their failing input.
7. **Loud:** a neutral wording that drops a step a consumer relied on is the risk; AC-3's
   table is where the lead sees every dropped hunk.
8. **Handoff:** the template's curator is a second GMD doc beside this repo's installed copy;
   the one-node rule is [[task-I1.d-first-skills#ac-2]] and covers it when it lands (the lead
   adds "and packaged agents" to that AC). The overlay section leaves in H1.b; agent and
   command drift becomes a `--check` error in H1.c
   ([[task-I1.b1-units-and-check#agents-leg]]).

## For the user {#for-the-user}

1. **cat-herder's `install.sh` keeps shipping its nine copies** until that repo changes, so
   "one copy" holds in refmatrix only. Recommended: one commit in cat-herder, by the lead on
   the user's go, that removes the nine from `install.sh` and has it run `rmx init` for them.
   The alternative is to leave it until H1.g archives the repo; a project scaffolded in
   between still gets whichever installer ran first.
2. **`~/.claude/agents/gmd-curator.md`** is a fourth copy, dated 2026-10-02, used in any
   repo without a project copy. It is the user's file. Recommended: remove it once the
   reconciled template is released; `rmx init` gives each project its own.
