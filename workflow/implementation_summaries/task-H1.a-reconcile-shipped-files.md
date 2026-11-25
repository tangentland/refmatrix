---
gmd: "0.1"
id: impl-task-H1.a-reconcile-shipped-files
title: "H1.a: the nine doubly-shipped files reconciled to one project-neutral template copy each"
tags: [implementation-summary, plan-32, h1, templates, cat-herder, install, gmd-curator, bug-319]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-25
---

# H1.a: one project-neutral copy of the nine doubly-shipped files {#root}

rel: implements -> [[task-H1.a-reconcile-shipped-files]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#layers]]
rel: related-to -> [[bug_registry]]
rel: depends-on -> [[self-audit]]

Branch `task-H1.a-reconcile` in the littlebig clone `refmatrix-h1a`, base `8c4c9eb3`. Small path
(L165, L237): one agent wrote the tests and the change, each test seen failing first. Commits:
`79493883` (RED tests), `8735f00b` (the reconcile), then this summary. No `src/**/*.py` changed.
bug-319 (`open`) is the reason it was built now; its fleet roll-out is H1.f's, not this task's. {#lead}

## What changed {#changed}

- **`src/refmatrix/templates/agents/gmd-curator.md`** is now a GMD doc: frontmatter `gmd`,
  `id: gmd-curator`, `title`, `tags`, `metadata.node_type: agent`; an anchor on every heading
  (`#root`, `#project-profile`, `#git-raw-reads` kept from the live copies, 30 new ones such as
  `#memory-layer`, `#curator-queue`, `#iron-rules`); `tools:` carries the seven read-only refmatrix
  MCP tools (Q15, L85); the overlay section ("Project profile") and the raw-`git` / wrapped-read
  section are in; the spool and `--token` drain contract and `rmx primer` stay (task 3.7); the
  lint command is `python3 tools/gmd/lint.py` (was `~/claude_tools/gmd/lint.py`, four lines);
  the file-back example's `[[#some-node]]` is in backticks. The backgrounded-ingest section is
  unchanged (Q58 = b). {#changed-curator}
- **The eight packaged commands** gain `argument-hint` (all but `stash-list`), `allowed-tools`
  (all but `recall-state`), `model: inherit` and a `# Title` heading. `commit-state` step 1 says
  deploy neutrally ("Deploy (promote dev → the live venv) only if code that other instances run
  changed."); `save-state` step 4 says to promote the way the project's CLAUDE.md says and keeps
  the no-`pip install -e` rule and the `rmx version -v` check for rmx itself, without
  `~/refmatrix`. The bodies of `save-state` and `recall-state` are otherwise the template's
  (the 2026-11-10 user-level rewrite). {#changed-commands}
- **This checkout** (D4): `.claude/agents/gmd-curator.md` equals the template except its
  `id: refmatrix/gmd-curator` line; `.claude/commands/{commit-state,detour,return,stash,stash-list,stash-pop}.md`
  equal the template byte for byte (copied from it; the AC-2 test compares them with what the
  installer writes). {#changed-instance}
- **Tests.** `tests/test_hooks.py`: `test_packaged_templates_hold_no_project_specifics` and its
  planted case `test_project_specifics_guard_fails_on_a_planted_line` (one per form).
  `tests/test_repo_hooks_in_sync.py`: `test_installed_agents_and_commands_equal_the_packaged_templates`
  and its planted case `test_installed_template_drift_fails_on_a_planted_one_line_edit`
  (curator and `commit-state`; also proves a differing `id:` line is not drift). {#changed-tests}

### Correction to the spec's count {#count-correction}

The spec's AC-1 measured five non-neutral sites at base. The guard found six: the sixth is
`commands/save-state.md:66` (`git -C ~/refmatrix pull --ff-only origin master` in step 4). It is
fixed with the other five. `tests/test_save_state.py::test_save_state_templates_never_install_the_dev_tree_into_deploy`
pins `rmx version -v` in that template, so the neutral step 4 keeps it as rmx's own check rather
than editing a test outside this task's file list. {#count-correction-body}

## RED at base (commit `79493883`, the tests on `8c4c9eb3`) {#red}

Lane `rmxtest1`, log `workflow/review-output/h1a-red.log` (clone): 2 failed, 18 passed, 1 skipped
(the clone skip of `test_installed_hooks_match_generated`, which is unrelated). {#red-lead}

- `test_packaged_templates_hold_no_project_specifics`:
  `E AssertionError: packaged agent/command text names one workstation; …
  agents/gmd-curator.md:100: ~/claude_tools`, `…:579`, `…:619`, `…:692`,
  `commands/commit-state.md:24: ~/refmatrix`, `commands/save-state.md:66: ~/refmatrix`.
- `test_installed_agents_and_commands_equal_the_packaged_templates`:
  `E AssertionError: installed copies drifted from src/refmatrix/templates/ … .claude/agents/gmd-curator.md differs from the packaged copy (first at line 2)`.
- The planted cases pass at base and after: they test the guards, and each asserts the guard
  reports its planted line (AC-1: every one of the seven forms; AC-2: a one-line body edit
  reported, an `id:` difference not reported). {#red-list}

## AC-3: every differing hunk, template `4f7d17b5` vs cat-herder `87f9d51` {#ac-3}

The template did not change between `4f7d17b5` and `8c4c9eb3` (`git diff --stat` empty). Hunks are
`diff template cat-herder` hunks (normal format, 55 in all). "T" = template side, "C" =
cat-herder side. Rules: D1-mech (newer mechanism wins), D1-neutral (neutral wording wins), D1-keep
(one side only, neutral: kept), D1-moot (one side only, moot: dropped), D2 (command frontmatter).
Command-key source for D2: <https://code.claude.com/docs/en/skills#frontmatter-reference>
("Frontmatter reference"; the "Command files" bullet: a `.claude/commands/` file "supports the
same frontmatter except `name` and `paths`"). `allowed-tools` there pre-approves tools for the
invoking turn; it does not restrict them. `model` accepts "`inherit` for the active model".
`enabled` is not listed. {#ac-3-lead}

### `agents/gmd-curator.md` (14 hunks) {#ac-3-curator}

| # | Hunk | Winner | Rule |
|---|---|---|---|
| 1 | `1a2,7` GMD frontmatter (`gmd`, `id`, `title`, `tags`, `metadata`) | C, with `id: gmd-curator` | D3 |
| 2 | `15c21` `tools:` list | neither: the live copy's string with the 7 read-only MCP tools | D3 (Q15, L85) |
| 3 | `18c24` H1 heading | C (`## Project profile {#project-profile}` before it) | D1-keep, D3 |
| 4 | `19a26,40` overlay section + `---` + H1 `{#root}` | C | D1-keep, D3 (I1.a overlay read through it) |
| 5 | `30a52,67` `#git-raw-reads` section | C | D1-keep |
| 6 | `31a69,72` wrapped-read paragraph | C | D1-keep |
| 7 | `126,128c167,168` watcher writes the spool vs `curator.queue` | T | D1-mech |
| 8 | `137,140c177,179` `status` / `status --json` / `drain --token` block | T | D1-mech |
| 9 | `143,147d181` "drain deletes only the token's files" paragraph | T | D1-mech |
| 10 | `155,157c189,191` crash-safe snapshot + `drain --token @…` | T | D1-mech |
| 11 | `297c331` `rmx primer --top 30` vs `rmx top mentions -k 30` | T | D1-mech |
| 12 | `493c527` `[[#some-node]]` bare vs backticked | C | D1-neutral (a bare wikilink dangles in a GMD doc) |
| 13 | `518c552` `rmx primer --top 20` vs `rmx top mentions -k 20` | T | D1-mech |
| 14 | `699,702c733,734` iron rule 14, drain by token | T | D1-mech |

Not a cat-herder hunk but in the same file: the four `~/claude_tools/gmd/lint.py` lines (both
sides) become `tools/gmd/lint.py` (D1-neutral); 30 heading anchors added (D3). {#ac-3-curator-extra}

### `commands/save-state.md` (7 hunks) {#ac-3-save}

| # | Hunk | Winner | Rule |
|---|---|---|---|
| 1 | `1a2` `name: save-state` | dropped | D2 (not supported in a command file) |
| 2 | `2a4,7` `argument-hint`, `allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]`, `model: inherit`, `enabled: true` | C's `argument-hint` (quoted), `allowed-tools` (steps: git and rmx via Bash, memory files and the status file via Write/Edit, reads), `model`; `enabled` dropped | D2 |
| 3 | `4a10,11` `# Save State` | C | D1-keep |
| 4 | `9,13c16,17` Project conventions vs "Requires `rmx`" note | T; the note dropped | D1-mech, D1-moot |
| 5 | `15c19` "Do all of this, in this order:" | T | D1-mech |
| 6 | `19,33c23,24` memory FIRST + layout rules vs old order | T | D1-mech |
| 7 | `37,69c28,34` bridge, `--commit` caveat, active goal, deploy, report vs old steps | T, except the deploy step's refmatrix sentence: rewritten neutral (see #count-correction) | D1-mech, D1-neutral |

### `commands/recall-state.md` (9 hunks) {#ac-3-recall}

| # | Hunk | Winner | Rule |
|---|---|---|---|
| 1 | `1a2` `name` | dropped | D2 |
| 2 | `2a4,7` `argument-hint`, `allowed-tools: [Bash, Read, Grep, Glob]`, `model`, `enabled` | `argument-hint` (quoted), `model` kept; `allowed-tools` dropped (step 3b uses `ListAgents`, outside the list); `enabled` dropped | D2 |
| 3 | `4a10,11` `# Recall State` | C | D1-keep |
| 4 | `9,14c16` Project conventions vs "Requires `rmx`" note | T; note dropped | D1-mech, D1-moot |
| 5 | `16,18c18,19` latest handoff: status file + newest save-state | T | D1-mech |
| 6 | `20d20` `rmx recall-state` one-shot | T | D1-mech |
| 7 | `24,36c24,25` "newest" order, bridge-lag fallback; trunk resolution | T | D1-mech |
| 8 | `39,58d27` 3a active goal, 3b running agents | T | D1-mech |
| 9 | `61,62c30` anomalies list (worktrees, bridge refusals) | T | D1-mech |

### The six project commands (25 hunks) {#ac-3-project}

| File | Hunk | Winner | Rule |
|---|---|---|---|
| commit-state | `1a2` `name` | dropped | D2 |
| commit-state | `2a4,7` `argument-hint`, `allowed-tools: [Bash, Read, Grep, Glob]`, `model`, `enabled` | first three kept (git + `rmx focus summarize` via Bash, diff review via reads); `enabled` dropped | D2 |
| commit-state | `4a10,11` `# Commit State` | C | D1-keep |
| commit-state | `7a15,17` "Requires `rmx`" note | dropped | D1-moot |
| commit-state | `24,25c34,35` deploy sentence (`~/refmatrix`, `rmx daemon restart`) | C | D1-neutral |
| detour | `1a2` / `2a4,7` / `4a10,11` / `7a15,17` | `name`, `enabled` dropped; `argument-hint`, `allowed-tools: [Bash]` (one `rmx focus detour`), `model` kept; heading kept; note dropped | D2, D1-keep, D1-moot |
| return | `1a2` / `2a4,7` / `4a10,11` / `7a15,17` | same; `allowed-tools: [Bash]` fits (`rmx focus return`, `rmx focus detours`) | D2, D1-keep, D1-moot |
| stash | `1a2` / `2a4,7` / `4a10,11` / `7a15,17` | same; `[Bash]` fits (`git stash`, `git switch`, `rmx task push`, `rmx focus context`) | D2, D1-keep, D1-moot |
| stash-list | `1a2` / `2a4,6` / `4a9,10` / `7a14,16` (no `argument-hint` on either side) | `name`, `enabled` dropped; `[Bash]` and `model` kept; heading kept; note dropped | D2, D1-keep, D1-moot |
| stash-pop | `1a2` / `2a4,7` / `4a10,11` / `8a16,18` | same; `[Bash]` fits (`rmx task pop`, `git stash list/pop/branch`) | D2, D1-keep, D1-moot |

Every `argument-hint` value is quoted. cat-herder's unquoted `[description] [--branch <name>]`
(stash) and `[desc substring or index] [--branch <name>]` (stash-pop) are YAML parse errors
(`yaml.safe_load`: `ParserError while parsing a block mapping`), so a strict parser loses the
whole frontmatter, `description` included; quoted, each is the string Claude Code shows. {#ac-3-quoting}

## AC-5: `rmx init` for real {#ac-5}

Dev code (`PYTHONPATH=<clone>/src`, `8735f00b`) as local user `rmxtest3` under its slot lock, a
`git init` throwaway project, `HOME` a fresh dir (log `workflow/review-output/h1a-ac5-rmx-init.log`,
clone): exit 0, `initialized …/proj/.refmatrix`, and these nine files, each `cmp`-equal to the
package:

```
h/.claude/commands/recall-state.md
h/.claude/commands/save-state.md
proj/.claude/agents/gmd-curator.md
proj/.claude/commands/commit-state.md
proj/.claude/commands/detour.md
proj/.claude/commands/return.md
proj/.claude/commands/stash-list.md
proj/.claude/commands/stash-pop.md
proj/.claude/commands/stash.md
```

Seven project files, two user-level files. {#ac-5-body}

## Verify set (AC-4, AC-6) {#verify}

Lane `rmxtest1` on `8735f00b`, log `workflow/review-output/h1a-verify.log` (clone, read by the
author): **630 passed, 1 skipped, exit 0** in 211 s. No failure, so no base comparison was needed.
The skip is the clone skip of `test_installed_hooks_match_generated` (hooks belong to the dev
tree's checkout; skipped at base too, in [[#red]]); it needs the dev tree, not this clone.
22 files: the two task files (`test_hooks.py`, `test_repo_hooks_in_sync.py`); the readers of
`src/refmatrix/templates/` or the installed `.claude/` copies (`test_install_commands_user_level.py`,
`test_save_state.py`, `test_savestate_subfolder.py`, `test_task3_7_curator.py`,
`test_task3_7_graph.py`, `test_task3_7_refine.py`, `test_task3_7_remedy_r2_meh.py`,
`test_bug216_scope_parity.py`, `test_bug230_repo_scope_gate.py`, `test_plan5_remedy.py`);
`test_hooks_reproducible.py`; and the nine repo guards (`test_tmp_root_census.py`,
`test_suite_discipline.py`, `test_docs_generated.py`, `test_mock_registry_coverage.py`,
`test_deferrals_clean.py`, `test_wallclock_census.py`, `test_budget_outcome_census.py`,
`test_verb_parity.py`, `test_bug212_r4_red.py`). The other `test_bug216_*` / `test_bug241_*`
hits of the grep build their own tmp `.claude/agents/x.md` and read no shipped copy.
`./scripts/lint-gmd.sh` (with `RMX_DEV_PYTHON` set): 1290 files, 0 errors, parity 0 divergent. {#verify-body}

## Self-audit {#self-audit}

1. **Ran it for real.** [[#ac-5]]: `rmx init` in a throwaway project wrote the seven project and
   two user-level files, each byte-equal to the package. {#sa-1}
2. **The test reaches the wiring.** AC-2's test calls `install_agents` and `install_commands`
   (what `rmx init` calls, `cli.py` `init`) into a tmp project and compares their output with this
   checkout. `test_install_commands_user_level.py` (unchanged, green) covers the user-level
   placement, keep-unless-`--force` and the backup. Nothing is patched. {#sa-2}
3. **Census.** Copies of each file: the template (changed); this repo's `.claude/` (reinstalled);
   cat-herder `87f9d51` (not touched; still the old nine, spec "For the user" 1);
   `~/.claude/commands/save-state.md` and `recall-state.md` (not touched; they equalled the old
   template and now differ by 3 and 2 hunks: the frontmatter keys and heading, and save-state's
   deploy step, so the next `rmx init` prints `skip … differs` for them until `rmx init --force`,
   which backs them up); `~/.claude/agents/gmd-curator.md` (not touched; 757 lines, the pre-3.7
   copy, 6 lines with `curator.queue` / bare drain / `top mentions`; Q71); the nine consumers'
   copies (not compared; H1.f). Readers of the curator's anchors: `grep -rn "gmd-curator#"
   workflow/ docs/` finds only the spec's own instruction line, so no reader depends on an anchor;
   the three anchors the live copy had are kept. Readers of the template text: the seven test files
   in the verify set that read `src/refmatrix/templates/` or `.claude/` copies, all green. {#sa-3}
4. **Bound.** N/A: no call, timeout or budget is added; package data and tests only. {#sa-4}
5. **Busy / down.** N/A: `install_agents` / `install_commands` touch no daemon or worker. {#sa-5}
6. **The guard can fire.** AC-1: the real state is a packaged file with a workstation path, which
   it fired on at base (six sites, [[#red]]); the planted case fires it for each of the seven
   forms. AC-2: it fired at base on this checkout's curator; the planted case fires it on a
   one-line body edit and shows the `id:` exception does not hide one. {#sa-6}
7. **Loud.** The failure is a test failure naming file and line ([[#red]]). The dropped-step risk
   is in [[#ac-3]]: dropped text is cat-herder's `name`/`enabled` keys, the moot "requires `rmx`"
   notes, its pre-3.7 curator queue text, and the refmatrix-specific deploy sentences (the
   refmatrix deploy procedure stays in this repo's CLAUDE.md and PROJECT_PROFILE). A project
   without `tools/gmd/lint.py` gets a "no such file" from the curator's lint line, not a silent
   pass; `rmx init` does not ship `tools/gmd/` (cat-herder's installer does). {#sa-7}
8. **Nothing handed off on paper.** The template curator as a second GMD doc beside this repo's
   copy is [[task-H1.a-reconcile-shipped-files#risks]] item 8 (the lead adds "and packaged agents"
   to I1.d AC-2). The two `~/.claude` copies and cat-herder's `install.sh` are the spec's
   "For the user" items 1 and 2 and Q71, the user's decisions; bug-319's fleet roll-out is H1.f.
   No new deferral. {#sa-8}
