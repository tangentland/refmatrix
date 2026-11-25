---
gmd: "0.1"
id: impl-task-I1.b1-units-and-check
title: "I1.b1 GREEN: instruction units, the compiler, the fixture runner, --check over every instruction artifact, rules replay (bug-209)"
tags: [implementation-summary, plan-32, i1, instructions, units, install-hooks, bug-209]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-25
---

# I1.b1 GREEN: units and the parity gate {#root}

rel: implements -> [[task-I1.b1-units-and-check]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#units]]
rel: implements -> [[refmatrix/adr-0007-instruction-architecture#installed-equals-generated]]
rel: derives-from -> [[i1b1-red-notes]]

GREEN for [[task-I1.b1-units-and-check]] on branch `task-I1.b1-units-and-check`: `bf46f6c6`
(the build), `ddb461eb` (`hooks.check` stays the settings leg, see [[#deviation]]), `8d2d7578`
(replay's count line, see [[#m27a]]). `src/` only plus the docs and packaging the change needs;
no test was written or edited. {#lead}

## What changed {#changes}

- **`src/refmatrix/instructions.py` (new).** The unit model; the loader for both layers
  (packaged through `importlib.resources`, local under `.claude/{triggers,checks,rules,skills}/`;
  a file with no `unit:` map under `rules/` or `skills/` is native, trap 4); `compile_layers`
  (every unit sorted by id with bindings, text, sha; per-event prefilter from deny, ask and
  inject only, trap 5; refuses with the file and the rule, nothing written); `decide`;
  `run_fixtures` (`repo:` and `store:` built in a temp directory with real `git`, each call
  bounded by `GIT_TIMEOUT_S` = 2 s); `replay` and `format_replay`. YAML is read with 1.2
  booleans: under YAML 1.1 a check's `on: commit` key parsed as `True`. {#c-instructions}
- **`src/refmatrix/hooks.py`.** `install` compiles first, so a refusal writes nothing (not the
  settings, not the compiled file); `render_artifacts` + `_install_artifacts` write the packaged
  rules and skills and `.claude/rmx-instructions.json`. `check_artifacts(project_root)` holds the
  artifact legs: the compiled file against a fresh compile, packaged rules and skills
  (generated / drift / missing), local units listed with their fixtures run, agents and
  commands (and the two user-level commands) classed and printed only (D6), and every
  `.git/hooks/<name>` with the `# refmatrix:` marker compared with `GIT_HOOK_SCRIPTS`
  (bug-209). `check_all` = `check` + `check_artifacts` (a `CheckReport` per leg since the fold); `rmx install-hooks --check` runs it.
  {#c-hooks}
- **`src/refmatrix/init_agents.py`.** `without_frontmatter_id` and `template_copy_class`: the
  one src helper for H1.a's id-line rule, used by the agents and commands classifier, so this
  repo's `gmd-curator.md` is `generated`. `packaged_md`. {#c-init-agents}
- **`src/refmatrix/cli.py`, `verbs.py`.** `rmx rules replay <unit> [--days N] [--show]`
  (thin: `instructions.find_unit`, `replay`, `format_replay`); `verbs.INTERNAL_CLI` gains
  `("rules", "replay")` with `_INTERNAL_DECISION`. `install-hooks` and `init` turn a refusal
  into a `ClickException` (stderr, exit 1). `--check` prints its report when clean too.
  {#c-cli}
- **Packaging.** `templates/{triggers,checks,rules,skills,practices}/__init__.py`;
  `package-data` for the unit directories; `pyyaml>=6.0` declared (installed transitively
  already, `requirements.lock` pins 6.0.3: the unit map is nested YAML, which
  `ingest_gmd._parse_frontmatter` cannot read). {#c-packaging}
- **This repo.** `.claude/rmx-instructions.json` (no units, trap 12) written by
  `instructions.compile_layers(load_layers(...))` (`compile_project` was deleted by the fold, [[#fold]]); `docs/ARCHITECTURE.md`'s CLI tree regenerated
  (`scripts/gen-cli-tree.py`, trap 11). {#c-repo}

## Deviation: `hooks.check` keeps its contract {#deviation}

RED's notes say `check()` should compose `check_artifacts`. Doing that failed two existing
tests at `bf46f6c6`, `test_repo_hooks_in_sync.py::test_bug170_the_comparison_renders_with_the_home_the_hooks_were_installed_with`
and `…::test_bug170_ac21_one_changed_script_byte_is_the_only_drift`: they call `hooks.check`
on a tmp checkout with no compiled file and read every non-`?` line as drift
(`i1b1-green-red4-guards.log`). `hooks.check` is therefore unchanged (the settings leg) and
`check_all` composes both legs; the CLI `--check` (every AC-4 and AC-5 case, release step 3's
fleet check) runs `check_all`. No test was changed. {#deviation-body}

## Lane logs {#lanes}

| log (`workflow/review-output/`) | sha | files | result |
|---|---|---|---|
| `i1b1-green-red4-guards.log` | `bf46f6c6` | RED's four + the nine guards | 3 failed, 441 passed, 1 skipped (fixed in `ddb461eb`) |
| `i1b1-green-red4-guards-2.log` | `ddb461eb` | same | 444 passed, 1 skipped |
| `i1b1-green-red4-guards-3.log` | `8d2d7578` | same, after the mutation batch | 444 passed, 1 skipped |
| `i1b1-green-verify.log` | `ddb461eb` | 180 files: every importer of a changed module and of the three support modules that import one | 3316 passed, 1 skipped, 1 xpassed |

The one skip is the pinned clone-only `test_installed_hooks_match_generated`. RED's 53 tests
all pass. `./scripts/lint-gmd.sh`: 3 errors, all `dangling-doc [[bsd-impression-anchors]]` in
three files of the user-level memory dir (`impressions/impression_bsd_ledger_*`), which no doc
in the clone or the dev tree defines; none is in a file this branch touches. {#lanes-body}

## Verify set {#verify}

`i1b1-green-verify.log`, local lane slot rmxtest1 at `ddb461eb` (the mini was unreachable:
`mini-lane: mini unreachable — DID NOT RUN`): 180 files, 3318 tests collected
(`i1b1-verify-collect.log`), **3316 passed, 1 skipped, 1 xpassed**, exit 0. The xpass is one of
the two pre-existing `strict=False` xfails (`test_models_offline.py:249` bug-298,
`test_task25_1_recall_budget.py:973` bug-312); `-q` does not name which. The files are the
direct importers of `hooks`, `instructions`, `init_agents`, `cli`, `verbs` plus every
importer of `task21_1_support`, `task25_1_support` and `instruction_units_support`;
`conftest.py` also imports `cli`, which would make the set the full suite, so that transitive
edge was not followed. `8d2d7578` changes only `format_replay`; every importer of
`instructions` is in `i1b1-green-red4-guards-3.log` at that sha. {#verify-body}

## Mutations {#mutations}

Each applied to the committed fix (`ddb461eb` / `8d2d7578`), run with the named tests in the
clone (`timeout 400`, log `i1b1-mut-<id>.log`), restored with `git checkout -- src/` in its own
command and checked clean with `git diff --quiet -- src`; `__pycache__` cleared after the batch
and the set re-run green (`-3` above). `iu` = `test_instruction_units.py`, `hr` =
`test_hooks_reproducible.py`. {#mutations-lead}

| # | mutant | test | E line (first) | killed |
|---|---|---|---|---|
| M1 (AC-8) | runner skips the prefilter check | iu::test_planted_unit_fixture_fails | `planted-fire-noprefilter: failing envelopes []` | y |
| M2 | an unmatched fire is ok | iu::test_planted_unit_fixture_fails | `planted-fire-nomatch: failing envelopes []` | y |
| M3 | pass side unchecked | iu::test_planted_unit_fixture_fails | `planted-pass-fires: failing envelopes []` | y |
| M4a (AC-8) | 600 B limit dropped | iu::test_apply_refuses[size-deny] | `--apply accepted a bad unit (size-deny); exit 0` | y |
| M4b | 2,000 B dropped | iu::…[size-inject] | `--apply accepted a bad unit (size-inject)` | y |
| M4c | 4,000 B dropped | iu::…[size-rule] | `--apply accepted a bad unit (size-rule)` | y |
| M4d | 20,000 B dropped | iu::…[size-skill] | `--apply accepted a bad unit (size-skill)` | y |
| M4e | 1,000 B dropped | iu::…[size-check] | `--apply accepted a bad unit (size-check)` | y |
| M5 | `>=` for `>` | iu::test_apply_accepts_text_at_its_size_limit (5 failed) | `the check message is 1,000 B; the limit for check units is 1,000 B` | y |
| M5b | rule limit 3,999 | iu::…at_its_size_limit[rule] | `the rule is 4,000 B; the limit for rule units is 3,999 B` | y |
| M6a | unit-level unknown key | iu::…[unknown-key] | `--apply accepted a bad unit (unknown-key)` | y |
| M6b | bind-level unknown key | iu::…[unknown-bind-key] | `--apply accepted a bad unit (unknown-bind-key)` | y |
| M7 | missing fixture skipped | iu::…[no-fire-fixture], [no-pass-fixture] (2 failed) | `--apply accepted a bad unit (no-fire-fixture)` | y |
| M8 | `Instead:` check removed | iu::…[deny-without-instead] | `--apply accepted a bad unit (deny-without-instead)` | y |
| M9 | duplicate-id check removed | iu::…[duplicate-id] | `--apply accepted a bad unit (duplicate-id)` | y |
| M10a | `ASK_VERIFIED` gate removed | iu::…[ask-unverified] | `--apply accepted a bad unit (ask-unverified)` | y |
| M10b | context/fallback gate removed | iu::…[context-without-fallback] | `--apply accepted a bad unit (context-without-fallback)` | y |
| M11a | `errors="replace"` | iu::…[non-utf8] | `--apply accepted a bad unit (non-utf8)` | y |
| M11b | unreadable file skipped | iu::…[unreadable] | `--apply accepted a bad unit (unreadable)` | y |
| M12 | compiled file written on refusal | iu::test_apply_refuses (15 failed) | `a refused --apply changed the compiled file` | y |
| M13a | units reverse-sorted | iu::test_apply_compiles_local_units | `units are not sorted by id` | y |
| M13b | a time in the compiled file | iu::test_apply_compiles_local_units | `a second --apply wrote different bytes` | y |
| M14 | `from:` copies the whole skill | iu::test_apply_compiles_local_units | `copied more than the #checklist section` | y |
| M15 | prefilter omitted | iu::test_apply_compiles_local_units | `KeyError: 'PreToolUse'` | y |
| M16 | rule and skill units left out | iu::test_apply_compiles_local_units | `['sample-check', 'sample-context', 'sample-deny', 'sample-gate']` | y |
| M17 (AC-8) | drift classed as local | hr::test_check_classes[rule-drift] | `an edited generated rule did not fail --check` | y |
| M18 (AC-8) | stale compiled read as in sync | hr::…[local-edited] | `a stale compiled file read as in sync` | y |
| M19 | fixture leg skipped | hr::…[fire-broken] | `a failing fire fixture did not fail --check` | y |
| M20a | agent drift fails `--check` | hr::…[agent-drift] | `agent drift failed --check before H1.c` | y |
| M20b | agents not classed | hr::…[agent-drift] | `the edited packaged agent is not printed as drift` | y |
| M21 | local files not listed | hr::…[clean] | `sample-deny.md is not listed as local` | y |
| M22 | `--check` opens the store | hr::…[clean-beside-held-writer] | `IOException: … Could not set lock on file …catalog.duckdb` | y |
| M23 (AC-8) | git-hook leg skipped | hr::test_check_covers_git_hooks[marked-body-rewritten] | `a rewritten refmatrix git hook read as in sync` | y |
| M24a | unmarked hook fails | hr::…[unmarked-hook-listed] | `a hook without the marker failed --check` | y |
| M24b | unmarked hook not listed | hr::…[unmarked-hook-listed] | `the unmarked hook is not listed` | y |
| M25 (AC-8) | text printed without `--show` | iu::test_replay[hashes-only] | `replay printed command text without --show` | y |
| M26 | `--show` ignored | iu::test_replay[show] | `--show did not print the matched text` | y |
| M27a | every event a hit | iu::test_replay (2 failed) | `AssertionError: rules replay sample-deny …` (no `hits 1`) | y, after `8d2d7578` |
| M27b | replay drops `unless` | iu::test_replay | (2 passed) | **n** |
| M28 | limits line omitted | iu::test_replay | `the limits line does not name DETAIL_MAX` | y |
| M29 | `rules replay` not in INTERNAL_CLI | test_verb_parity::test_internal_cli_is_exactly_the_seeded_set_and_quotes_the_decision | `[('rules', 'replay')]` | y |
| M30 | M20a's mutant | test_repo_hooks_in_sync::test_repo_instruction_artifacts_match_their_render | (passed) | **n**, expected (lead ruling: no agent drift here) |

{#mutation-table}

- **M27a** first SURVIVED at `ddb461eb`: replay printed `scanned 3 tool events in 1 ring
  file(s); hits 3`, and RED's `\b1\b\D{0,20}hits?\b` matched "1 ring file(s); hits". The count
  of ring files now has its own line (`8d2d7578`); the mutant then failed both cases. The regex
  stays loose for any output that puts a lone `1` within 20 non-digits before "hit". {#m27a}
- **M27b** survives: no event in RED's ring carries the `unless` text (`--dry-run`), so a
  replay that ignores `unless` still counts 1. Replay and `decide` share `_input_matches`, and
  `decide`'s `unless` is pinned (AC-3, `sample-deny/pass[0]`), so only a replay-only bypass
  survives. A killing case is a fourth ring command `rmfoo --all x/ --dry-run` with hits still 1
  (the test-engineer's call). {#m27b}

## Real run (risk 1) {#real}

Throwaway git project under `/private/tmp/claude-501/rmx-real-*`, fresh `HOME`,
`REFMATRIX_ROOT` inside it, the dev `rmx` (`.venv-eval/bin/rmx`, `PYTHONPATH=<clone>/src`),
default flags; four local units (deny, gate, check, skill). Full output:
`workflow/review-output/i1b1-real-run.log`. {#real-lead}

```
$ rmx install-hooks --apply
write <T>/p/.git/hooks/post-commit … post-rewrite
write <T>/p/.claude/settings.json
…
write <T>/p/.claude/rmx-instructions.json
write <T>/p/.claude/rmx-hooks.json (flags)
exit 0
$ rmx install-hooks --check
hooks in sync <T>/p/.claude/settings.json
instruction artifacts:
  generated .claude/rmx-instructions.json (4 unit(s))
  local     .claude/checks/sample-check.md (check `sample-check`; fixtures 3/3 ok)
  local     .claude/skills/sample-skill/SKILL.md (skill `sample-skill`; fixtures 2/2 ok)
  local     .claude/triggers/sample-deny.md (deny `sample-deny`; fixtures 3/3 ok)
  local     .claude/triggers/sample-gate.md (inject `sample-gate`; fixtures 3/3 ok)
  not installed ~/.claude/commands/recall-state.md (user-level; `rmx init` installs it)
  not installed ~/.claude/commands/save-state.md (user-level; `rmx init` installs it)
  generated .git/hooks/post-checkout
  generated .git/hooks/post-commit
  generated .git/hooks/post-merge
  generated .git/hooks/post-rewrite
exit 0
second --apply: compiled bytes identical (sha256 c7cf7a75…)
post-merge rewritten to the pre-26.2 body, marker kept → `drift .git/hooks/post-merge` + diff, exit 1
$ rmx rules replay sample-deny → no STM ring directory; scanned 0 tool events; hits 0; limits line; exit 0
```

## Fold of bsd-i1b1 r1 {#fold}


RED `4bac1ce9` (12 cases failing at `2f392131`); GREEN `9c7394dd`, `src/` only:

- **b-1** `replay`: each tool bind's `match` keys against what the ring stores
  (`ring_unmeasurable_keys`, `RING_DROPPED_KEYS`; Bash keeps only `command`); such a bind prints
  `unmeasurable: bind[i].match.<key> is not stored in the ring` and is left out of the hit count.
- **b-2** `_parse(layer_dir=…)`: a unit whose `KIND_DIR` is not its directory is refused, both
  layers; `compile_project` deleted.
- **s-1** (ruling a): zero units and no compiled file is `generated`; `--apply` writes no compiled
  file into a project with no units (an existing one is kept current).
- **s-2**: `PREFILTER_FORBIDDEN` (`"`, `\`, `:`) refused at parse.
- **s-3**: a local file at a packaged trigger's or check's path is refused
  (`duplicate path with a packaged unit`); `--check` compares installed rules and skills only.
- **s-4**: `FIXTURE_MAX_COMMITS = 10`, refused above at parse.
- **m-1**: `check_all` returns `CheckReport(settings_ok, artifacts_ok, text)`; the CLI heads a
  failure `hooks drift …settings.json` only when the settings leg drifted, else
  `instruction artifacts out of sync`.

Fold mutations (logs `i1b1-fmut-<id>.log`, each restored by `git checkout -- src/` in its own
command, `__pycache__` cleared after the batch): F1-F10 killed; F11 (`--apply` writes a zero-unit
compiled file) survives, see the fold report. {#fold-body}

## Self-audit {#self-audit}

rel: implements -> [[self-audit#form]]

```
1 real:     rmx install-hooks --apply / --check / rules replay in a throwaway git project
            (above, i1b1-real-run.log) → exit 0, every unit local with fixtures ok, four git
            hooks generated; a rewritten post-merge → drift + diff, exit 1.
2 wiring:   iu::test_apply_compiles_local_units, test_apply_refuses[*], test_replay[*] and
            hr::test_check_classes[*], test_check_covers_git_hooks[*] enter through the dev
            `rmx` CLI (child process); run_fixtures / load_unit are called directly only in AC-3.
3 census:   grep `hooks_mod.check|check_all|check_artifacts|render_managed|hooks.install` in
            src/ scripts/ → cli.py:1071 (init → install), cli.py:10317 (--check → check_all),
            cli.py:10327 (--apply → install); ORCHESTRATION #release step 3 runs the CLI
            `--check`. render_managed unchanged. `hooks.check` (settings leg) keeps its callers
            (tests, check_all). Both outputs of --check (exit code, text) are asserted by AC-4/5.
4 bound:    no daemon call on any leg. git per call 2 s (GIT_TIMEOUT_S): a stateful envelope
            makes init + symbolic-ref + add + 1 commit per `commits` + 1 per `when` state
            (sample-check fire: 5 calls, worst 10 s); the fixture leg is linear in envelopes,
            with no overall budget (none was specified; the dispatcher's budget is I1.b3 AC-9).
5 busy:     --check beside a held writer lock: hr::test_check_classes[clean-beside-held-writer]
            passes (M22 proves the case can fail). Daemon down: every AC-4/5 case runs with no
            daemon; replay reads ring files only.
6 guard:    each D3 refusal is reached by a real file through the CLI (15 cases of
            test_apply_refuses + 5 at-limit cases); each --check class by a real edit
            (rule-drift, local-edited, fire-broken, agent-drift, git hooks). Mutations M4-M24.
7 loud:     forced an unreadable unit (chmod 0) and a non-UTF-8 unit in the real project →
            exit 1, stderr "Error: rmx install-hooks: refused 2 instruction unit problem(s);
            nothing was written: … not valid UTF-8 … / … cannot read the file: PermissionError:
            Permission denied"; compiled file and settings.json unchanged. A fixture temp dir
            that cannot be removed prints one stderr line.
8 handoff:  agent and command drift as an error with backup-before-replace → H1.c (the lead
            adds the clause, spec #risks 8); the packaged rule/skill seen twice under one GMD id
            → task-I1.d-first-skills#ac-2; `rmx rules fire` and the per-event sidecar →
            task-I1.b3-dispatcher #d1 #d2; ASK_VERIFIED / CONTEXT_VERIFIED flip → their probes
            (task-I1.b0 P2 / P1); bug-209's registry row closes at the merge (the lead).
```

{#self-audit-body}

## For the lead {#for-lead}

- [[#deviation]]: `hooks.check` stays the settings leg; `check_all` is new.
- [[#m27b]]: one surviving mutant with a one-line killing case for the test-engineer.
- `pyyaml` is now a declared dependency ([[#c-packaging]]).
- In the real HOME, `~/.claude/commands/save-state.md` and `recall-state.md` differ from the
  packaged templates (frontmatter and the deploy step), so `--check` in the dev tree prints two
  user-level drift lines (never a failure, D6). H1.a's rollout would clear them.
- No version bump (the release commit's). {#for-lead-body}
