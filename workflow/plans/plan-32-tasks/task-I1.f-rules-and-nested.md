---
gmd: "0.1"
id: task-I1.f-rules-and-nested
title: "Task I1.f: the first T2 path rules, three nested CLAUDE.md files, the memory-file skill and the ADR reminder"
tags: [task, plan-32, instructions, rules, paths, nested-claude-md, memory-rules, practice-tdd]
metadata:
  node_type: task
  status: approved-pending
  plan: plan-32-instruction-architecture
  created: 2026-11-25
  author: ch-architect (Fable 5.2)
---

# Task I1.f: rules and nested files {#root}

> Status: written 2026-11-25 for the spec window (L232), against I1.b1 as built (`87a599c4`)
> and the probe verdicts (L240: P3, P6, P7). The lead approves. Queue row I1.f.
> Size: **small** (files, fixtures and three guard tests; no `src/` code). One isolated agent;
> the lead reads the diff. Waits on I1.b1 for the format, on [[task-I1.b3-dispatcher]] for the
> two injects and on [[task-I1.b2-marker-and-ledger]] for AC-8's rows. The nested files name
> modules, so they are written after 29.5 or re-pointed by 29.6.

rel: implements -> [[refmatrix/adr-0007-instruction-architecture#contract]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#t2-backstop]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#practice-slots]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#always-on]]
rel: part-of -> [[plan-32-instruction-architecture]]
rel: depends-on -> [[task-I1.b1-units-and-check#d1]]
rel: depends-on -> [[plan-of-plans#queue]]

## Goal {#goal}

The conventions of an area load when a file of that area is read or changed, in the lead and
in every subagent, instead of sitting in always-on text or in a memory that a recall may not
surface. Each rule names what catches a violation when the rule did not load. {#goal-body}

## What is built {#design}

- **D1 A path rule is a unit.** One file: Claude Code's `paths:` beside a `unit:` map of kind
  `rule`, whose bind is PreToolUse on `Read|Edit|Write|MultiEdit` with a `file_path` pattern,
  and whose `fire` and `pass` envelopes are file paths. The body is at most 4,000 B (the
  compiler refuses more) and ends with `Backstop:` and a test file, a check unit, or
  `advisory` ([[refmatrix/adr-0007-instruction-architecture#t2-backstop]]). {#d1}
- **D2 Three guards, because a rule states its paths twice.** For every rule unit, packaged
  and local: each `fire` path matches a `paths:` glob and no `pass` path does; the `Backstop:`
  line names something that exists. For this checkout: every glob matches a tracked file, so
  a glob the 29.5 split kills fails instead of going quiet. {#d2}
- **D3 Three nested `CLAUDE.md` files** (T10), plain GMD files of at most 3,000 B:
  `src/refmatrix/CLAUDE.md` (layout, primitives and glossary, from the profile),
  `tests/CLAUDE.md` (the fixtures, the sandbox, where the lanes are stated),
  `eval/CLAUDE.md` (the benchmark path is the production path; `eval/datasets.py` shadows
  the HuggingFace package). {#d3}
- **D4 The memory-file rules are a skill with two gates.** A user-level rule does not match a
  file outside the project (P7), so R099 to R103 are a template skill, `memory-files`, with
  two trigger units: a Write or Edit of a file in a `memory/` directory under
  `.claude/projects/` delivers `#write` (the frontmatter shape, typed edges, the amend tree,
  the index rule); a Bash `rm` of one delivers `#forget`. Both are `context` with
  `fallback: gate`. Each ends by naming `~/.claude/MEMORY-RULES.md` for the rest. {#d4}
- **D5 `adr-gate.sh` becomes a unit** (L234): a template inject, `adr-first`, on PostToolUse
  for an Edit or Write of a source file whose new text defines a class (`context`,
  `fallback: post`): "check `docs/adr/` for a decision that names it". The script is deleted
  in the window commit. The unit has no command, so it no longer names the matching ADR.
  {#d5}
- **D6 Nothing leaves always-on here.** `CLAUDE.md`, the profile and the `MEMORY-RULES.md`
  import keep their text until I1.h
  ([[refmatrix/adr-0007-instruction-architecture#removal-order]]). Until then a rule repeats
  text the session already holds, once per context. A native rule has no window: it loads as
  soon as its file is in the tree, so the lead's diff read is the gate. Every packaged file
  carries `metadata.version: 1.0.0` (L241). {#d6}

## The rules {#rules}

Layer: **T** the template (`templates/rules/`); **P** `practice/tdd`
(`templates/practices/tdd/rules/`, slot `test-authoring`); **L** refmatrix's own
(`.claude/rules/`). {#rules-lead}

| Rule | Layer | `paths:` | Rows | Backstop |
|---|---|---|---|---|
| `test-authoring` | P | `tests/**` | R049 to R056 | `tests/test_suite_discipline.py` |
| `src-conventions` | L | `src/**` | R072, R073, R075, R076, R080, R081, R089 | `tests/test_deferrals_clean.py`, `tests/test_models_offline.py`; R073 and R081 advisory until P1 (c)'s lints |
| `verbs-and-ops` | L | `src/refmatrix/{cli,mcp,verbs,daemon}.py` | R063, R078, R079 | `tests/test_verb_parity.py`, `tests/test_docs_generated.py` |
| `hook-producers` | L | `src/refmatrix/{hooks,search_hooks,scan,hook_budget}.py`, `composite*.py` | R090, R091, R191 | `tests/test_repo_hooks_in_sync.py` |
| `gmd-docs` | T | `docs/**/*.md`, `workflow/**/*.md`, `CLAUDE.md` | R095, R096 | the check `gmd-lint` |
| `plans` | T | `workflow/plans/**` | R114, R123, R124, R204 | the check `pop-in-commit`; else advisory |
| `bug-registry` | T | `workflow/bug_registry.md` | R160 and the file's present text | the checks `registry-row`, `fixed-is-reachable` |
| `adr` | L | `docs/adr/**` | R110 | advisory |

The existing `.claude/rules/bug-registry.md` becomes the installed copy of the packaged
`bug-registry`; its `paths:` line arrived with [[task-I1.e-first-checks#checks-registry]].
Until a stack pack supplies the test paths (H1.d), `test-authoring` carries the literal.
{#rules-notes}

## Acceptance criteria {#acceptance}

- **AC-1 Every rule and both triggers compile and prove their binds.** Packaged units:
  `tests/test_instruction_units.py::test_packaged_unit_fixtures`; local units:
  `…::test_this_checkouts_local_units`. Each `fire` envelope is shown not matched before its
  unit exists. {#ac-1}
- **AC-2 The two statements of a rule's paths agree.** `…::test_rule_paths_match_binds[unit]`
  over every rule unit of both layers; a planted rule whose `paths:` was widened without its
  bind fails. {#ac-2}
- **AC-3 Every rule names its backstop.** `…::test_rule_names_a_backstop[unit]`: the last
  line is `Backstop:` with `advisory` or names that exist (a test file, a compiled check); a
  planted rule naming a missing test fails. {#ac-3}
- **AC-4 No glob is dead in this checkout.** `…::test_this_checkouts_rule_globs_match_files`:
  every `paths:` glob of an installed rule matches a file in `git ls-files`; a planted glob
  for a path that does not exist fails. {#ac-4}
- **AC-5 The nested files stay small and valid.** `…::test_nested_claude_md_budget[file]`:
  each of the three is at most 3,000 B; a planted 3,001 B file fails. The summary pastes
  `python3 tools/gmd/lint.py` on each. {#ac-5}
- **AC-6 A memory write gets its rules.** Fixtures: a Write to
  `~/.claude/projects/<slug>/memory/x.md` fires `#write`; a Write to `docs/memory/x.md` does
  not; a Bash `rm` of a memory file fires `#forget`; `rm` of another file does not. With
  `CONTEXT_VERIFIED` as committed both are delivered as gates. {#ac-6}
- **AC-7 The ADR reminder replaces the script.** Fixtures: an Edit of a `.py` under `src/`
  whose `new_string` holds `class Name` fires `adr-first`; the same under `tests/`, and one
  with no class, do not. No generated entry names `adr-gate.sh` once the window commit
  removes it (`tests/test_hooks_reproducible.py::test_enforce_entries_follow_scripts_on_disk`).
  {#ac-7}
- **AC-8 A rule is seen loading, in the lead and in a subagent.** P3's script, pointed at
  this branch's clone, reads a file under `tests/` in the main session and in a subagent:
  each quotes the marker line of `test-authoring`, and `rmx telemetry --context` shows the
  two `loaded` rows, the subagent's with its `agent_id`. {#ac-8}
- **AC-9 Nothing is removed, and the sizes are stated.** `git diff` shows no deletion in
  `CLAUDE.md`, `.claude/PROJECT_PROFILE.md` or an overlay; `./scripts/lint-gmd.sh` exits 0;
  `rmx install-hooks --check` is clean; the summary lists each rule's bytes and census rows.
  {#ac-9}

## Mutations {#mutations}

No `src/` code changes; the guards are proven by their planted cases and by these unit edits.
{#mutations-lead}

| # | Mutation | Must fail |
|---|---|---|
| M1 | a rule's `paths:` glob changed and its bind left | AC-2 |
| M2 | a rule's `Backstop:` line removed | AC-3 |
| M3 | a local rule's glob pointed at a file `git ls-files` does not hold | AC-4 |
| M4 | in any one binding, the token that separates its `fire` from a `pass` envelope is removed | that binding's `pass` envelope in AC-1 |

## Files {#files}

`src/refmatrix/templates/rules/{gmd-docs,plans,bug-registry}.md`;
`templates/practices/tdd/rules/test-authoring.md` and `practices/tdd/practice.md`;
`templates/skills/memory-files/SKILL.md`; `templates/triggers/{memory-write,memory-forget,adr-first}.md`;
`.claude/rules/{src-conventions,verbs-and-ops,hook-producers,adr}.md` and the installed
copies; `src/refmatrix/CLAUDE.md`, `tests/CLAUDE.md`, `eval/CLAUDE.md`;
`.claude/rmx-instructions.json` (regenerated); `tests/test_instruction_units.py`. In the
window commit: the removal of `.claude/hooks/adr-gate.sh`. {#files-list}

## Risks (self-audit) {#risks}

1. **Real:** AC-8 is the run in a real session; the lead repeats it once in the dev tree
   after the merge and pastes the `loaded` rows.
2. **Wiring:** a rule's delivery is Claude Code's own, so it is proven by a session (AC-8),
   not by `decide`; the triggers go through the generated command.
3. **Census:** a path rule loads on Read, Write and Edit, not on a Bash edit, Glob or Grep,
   which is why each names a backstop. R054's checker files outside `tests/` (`tools/gmd/`,
   `scripts/*lint*`) get its text only through `test-authoring`. Each rule's other statements
   are in its `census` field for I1.h. The memory gate reaches a project only where the
   dispatcher is enabled ([[#open]] 1).
4. **Bound:** a rule adds at most 4,000 B to a context that touches its paths; two rules can
   load on one file (`src-conventions` with `verbs-and-ops`): at most 8,000 B. The summary
   states the largest pair.
5. **Busy / down:** nothing here calls the daemon.
6. **Guard:** AC-2 to AC-5 each plant their failing input.
7. **Loud:** a rule that stops loading is silent; AC-4 and the `loaded` rows the context
   review reads are how it is seen.
8. **Handoff:** removing the always-on copies → I1.h. The un-import of `MEMORY-RULES.md` →
   [[#open]] 1. The test and source path literals → H1.d. The module names in the nested
   files → 29.6's re-point list.

## Open decisions {#open}

1. **How the memory-file rules reach a project without the dispatcher.** The ADR puts the
   trigger at user level, and P7 shows a user-level rule cannot do it. Recommended: ship the
   packaged skill and gates now (they work in every project whose dispatcher is enabled),
   keep the `MEMORY-RULES.md` import until H1.f has enabled the last fleet repository, then
   replace it with one pointer line in the user's `~/.claude/CLAUDE.md`. The alternative is
   to build a user-level layer now: a compiled file and a dispatcher entry in the user's own
   settings, which no spec has yet.
