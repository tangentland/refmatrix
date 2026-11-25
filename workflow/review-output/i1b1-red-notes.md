---
gmd: "0.1"
id: i1b1-red-notes
title: "I1.b1 RED notes: the mutation list and what GREEN must know"
tags: [task, plan-32, instructions, red, mutations, task-I1.b1]
metadata:
  node_type: review-notes
  author: red-i1b1 (ch-test-engineer)
  created: 2026-11-25
  red_sha: a07a7b83
---

# I1.b1 RED notes {#root}

The RED tests for [[task-I1.b1-units-and-check]] are at `a07a7b83` (branch `i1b1-red`). On a
lane at that sha (rmxtest2): 53 failed, 185 passed, 1 skipped. The skip is the pinned clone-only
`test_installed_hooks_match_generated`. This page lists the mutations for the GREEN and
mutation step, and the decisions GREEN has to make. No test was changed for this page.
{#lead}

rel: derives-from -> [[task-I1.b1-units-and-check#acceptance]]

## Mutations, each with the test that must kill it {#mutations}

Every mutant applies to the expected `src/` change (`instructions.py`, `hooks.py`,
`cli.py`). Test paths are under `tests/`. `iu` = `test_instruction_units.py`;
`hr` = `test_hooks_reproducible.py`. {#mutations-lead}

| # | Mutant | Killing test |
|---|---|---|
| M1 | `run_fixtures` stops checking that a `fire` envelope's raw JSON holds the prefilter (AC-8) | `iu::test_planted_unit_fixture_fails[planted-fire-noprefilter]` |
| M2 | the `fire` side is not checked against `decide()` (every fire is ok) | `iu::test_planted_unit_fixture_fails[planted-fire-nomatch]` |
| M3 | the `pass` side is not checked (a firing pass is ok) | `iu::test_planted_unit_fixture_fails[planted-pass-fires]` |
| M4a | the 600 B reason limit dropped (AC-8) | `iu::test_apply_refuses[size-deny]` |
| M4b | the 2,000 B checklist limit dropped | `iu::test_apply_refuses[size-inject]` |
| M4c | the 4,000 B rule limit dropped | `iu::test_apply_refuses[size-rule]` |
| M4d | the 20,000 B skill limit dropped | `iu::test_apply_refuses[size-skill]` |
| M4e | the 1,000 B check-message limit dropped | `iu::test_apply_refuses[size-check]` |
| M5 | a limit made stricter or off by one (`>=` for `>`, or a kind using a smaller number) | `iu::test_apply_accepts_text_at_its_size_limit[<kind>]` |
| M6a | the unknown-key check removed at unit level | `iu::test_apply_refuses[unknown-key]` |
| M6b | the unknown-key check removed at bind level | `iu::test_apply_refuses[unknown-bind-key]` |
| M7 | the missing-fixture check removed (either side) | `iu::test_apply_refuses[no-fire-fixture]`, `[no-pass-fixture]` |
| M8 | the `Instead:` check removed | `iu::test_apply_refuses[deny-without-instead]` |
| M9 | the duplicate-id check removed | `iu::test_apply_refuses[duplicate-id]` |
| M10a | the `ASK_VERIFIED` gate removed | `iu::test_apply_refuses[ask-unverified]` |
| M10b | the `CONTEXT_VERIFIED` no-fallback gate removed | `iu::test_apply_refuses[context-without-fallback]` |
| M11a | the unit read with `errors="replace"` (non-UTF-8 accepted) | `iu::test_apply_refuses[non-utf8]` |
| M11b | an `OSError` on read swallowed (the file skipped) | `iu::test_apply_refuses[unreadable]` |
| M12 | the compiled file written before every unit is validated (a partial write on refusal) | any `iu::test_apply_refuses[*]` (compiled bytes must be unchanged) |
| M13 | units not sorted, or a timestamp or other per-run value in the compiled file | `iu::test_apply_compiles_local_units` (sort check; the second `--apply` writes identical bytes) |
| M14 | `from: <skill>#<anchor>` copies the whole skill body, not the anchored section | `iu::test_apply_compiles_local_units` (`SKILL-BACKGROUND-SENTINEL` must be absent) |
| M15 | the per-event `prefilter` omitted from the compiled file | `iu::test_apply_compiles_local_units` |
| M16 | rule and skill units left out of `units` | `iu::test_apply_compiles_local_units` (all six local ids) |
| M17 | drift classed as local (AC-8) | `hr::test_check_classes[rule-drift]` |
| M18 | a stale compiled file read as in sync (AC-8) | `hr::test_check_classes[local-edited]` |
| M19 | the fixture leg skipped in `--check` | `hr::test_check_classes[fire-broken]` |
| M20a | agent drift fails `--check` (exit 1) before H1.c | `hr::test_check_classes[agent-drift]` |
| M20b | agents not classed or printed | `hr::test_check_classes[agent-drift]` |
| M21 | local files not listed in the `--check` output | `hr::test_check_classes[clean]` |
| M22 | `--check` opens the store or calls the daemon | `hr::test_check_classes[clean-beside-held-writer]` (a lock error, or a wait past the 30 s timeout) |
| M23 | the git-hook leg skipped (AC-8) | `hr::test_check_covers_git_hooks[marked-body-rewritten]` |
| M24 | a hook without the marker fails `--check`, or is not listed | `hr::test_check_covers_git_hooks[unmarked-hook-listed]` |
| M25 | replay prints the matched text without `--show` (AC-8) | `iu::test_replay[hashes-only]` |
| M26 | `--show` ignored | `iu::test_replay[show]` |
| M27 | replay ignores `unless`, or counts every event as a hit | `iu::test_replay[*]` (`hits 1`) |
| M28 | replay omits the limits line (DETAIL_MAX, the `who` upper bound, `when`) | `iu::test_replay[*]` |
| M29 | `("rules", "replay")` not registered in `verbs.INTERNAL_CLI` | `test_verb_parity.py::test_internal_cli_is_exactly_the_seeded_set_and_quotes_the_decision` |
| M30 | `check_artifacts` returns not-ok on agent or command drift | `test_repo_hooks_in_sync.py::test_repo_instruction_artifacts_match_their_render` (this repo's `gmd-curator.md` differs from its template) |

{#mutation-table}

## Interfaces the tests rely on {#interfaces}

- `refmatrix.instructions.load_unit(path)` returns a unit with `.id` and `.kind`.
- `refmatrix.instructions.run_fixtures(unit)` returns one result per envelope with `.side`
  (`"fire"` or `"pass"`), `.index` (position in that list), `.ok`, `.outcome` (what `decide()`
  gave; `None` or falsy when nothing fires) and `.reason`. A prefilter miss's reason contains
  "prefilter". A firing deny gives `"deny"`, an ask `"ask"`, the gate sample `"gate"`, the
  context sample `"context"` or `"post"`. The other kinds need any truthy outcome.
- `refmatrix.instructions.ASK_VERIFIED` and `CONTEXT_VERIFIED`, both off. A refusal names the
  constant (for context, the constant or the word "fallback").
- `refmatrix.hooks.check_artifacts(project_root) -> (ok, text)`: the artifact legs of
  `check` (rules, skills, agents, commands, the user-level commands, the compiled file, git
  hooks, fixtures). AC-6 calls it directly, because the full `check` fails on the settings leg
  in a clone (absolute paths, bug-054). `check()` should compose it.
- `rmx rules replay <unit id> [--show]` resolves the unit from the layers by id. It does not
  read the compiled file: a deny is replayed before it ships.
- **Compiled file:** `{"units": [...], "prefilter": {event: ...}}`. `units` is sorted by `id`;
  each entry has `id`, `kind`, `bind`, `text` and `sha` (hex, 12 to 64 characters, distinct per
  unit). Each dispatchable unit's prefilter literal appears in its event's value.

{#interfaces-list}

## The unit format the fixtures pin {#format}

- GMD frontmatter plus a `unit:` map: `kind`, `bind` (a list), `priority`, `census`,
  `fixtures`, `from`, and for checks `on` and `run`.
- `mode` and `fallback` go inside each `bind` entry; `from` goes on the unit map.
- The text is the markdown body after the frontmatter, stripped, or the `from:` section. Its
  size is the UTF-8 byte length. The size tests use bodies with no heading, so dropping or
  keeping the H1 makes no difference to them.
- **Layers:** `.claude/triggers/` (deny, ask, inject), `.claude/checks/`, `.claude/rules/`,
  `.claude/skills/<id>/SKILL.md`. Packaged units go in the same names under
  `src/refmatrix/templates/`.
- **Stateful fixtures:**
  - `store: present` or `absent`.
  - `repo:` holds `files`, `commits: N`, `dirty` and `branch`. `dirty` means a tracked file
    modified after the commits.
  - The runner sets the envelope's `cwd` to the temp directory it builds;
    `when.git-dirty.repo: .` is relative to that.
- The patterns are ERE and Python `re` compatible (no `\s`, no `[[:space:]]`).

{#format-list}

## Traps and decisions for GREEN {#traps}

1. **The package-copy harness (packaged rule).** No unit ships in b1, but AC-4's `rule-drift`
   needs a generated rule. `tests/instruction_units_support.py::build_overlay_site` copies
   this checkout's `src/refmatrix`, adds `templates/rules/sample-packaged-rule.md` (from
   `tests/fixtures/instruction_units/packaged/rules/`, plus an `__init__.py` if GREEN has not
   made one), and puts the copy first on the child's PYTHONPATH. The fixture asserts that the
   child imports the copy.
   - Do not resolve the template root with `Path(__file__).resolve()` into another tree. Find
     templates through `importlib.resources` or relative to the imported package, or the
     copy is bypassed.
   - `test_check_classes` runs every case under the copy.
2. **`--apply` writes the packaged rules and skills** to `.claude/rules/<file>` and
   `.claude/skills/<id>/`. `rule-drift` asserts the file exists after `--apply`. Agents and
   commands stay with `rmx init`. The `agent-drift` and clean cases write `gmd-curator.md`
   from the template themselves, so its render must equal the template bytes in b1.
3. **`--apply` does not run fixtures.** `fire-broken` re-applies after breaking the envelope
   and expects exit 0; only `--check` then fails.
4. **Plain native rules.** This repo's `.claude/rules/bug-registry.md` has no `unit:` map.
   AC-6 needs it listed on a `local` line and needs `check_artifacts` to stay ok.
   Recommendation: a file with no `unit:` map is a native rule, local, listed, not compiled,
   not refused. Converting it into a unit would also pass, but it is not this task's change.
5. **The compiled file holds every kind,** rule and skill included (AC-1, "every unit").
   Recommendation: build the per-event `prefilter` only from dispatchable kinds (deny, ask,
   inject, and check if I1.e wants it). The tests check only the deny, gate and context
   literals.
6. **The clean `--check` must print no line containing "drift"** (except the existing
   "hooks drift" header). The two user-level commands are absent in the sandbox `HOME`; that
   must not print as drift.
7. **The refusal goes to stderr** and names the file by absolute or project-relative path.
   The tests remove the path before matching rule tokens, so a file name never satisfies a
   token. `settings.json` must also stay byte-identical on a refusal.
8. **`sample-ask` is not installed locally** while `ASK_VERIFIED` is off. The commit that
   flips a probe constant on its evidence turns `[ask-unverified]` or
   `[context-without-fallback]` into an acceptance case, and adds `sample-ask` to
   `LOCAL_SAMPLES`.
9. **Replay hashing.** The test accepts the first 12 hex characters of the sha256 of either
   the whole recorded command (`detail`) or the regex match span. It also requires the hit's
   ring `ts`, `DETAIL_MAX`'s number, the phrase "upper bound" and the word "when" in the output.
   The ring is written by the generated focus entries (tool-pre, then tool).
10. **The parity seed.** `tests/test_verb_parity.py::_INTERNAL_SEED` already holds
    `("rules", "replay")`. GREEN adds the same key to `verbs.INTERNAL_CLI` with a reason that
    quotes the user's decision (`_USER_QUOTE`), or the seed test fails on the reason check.
11. **Generated CLI tree.** A new `rules replay` command needs `scripts/gen-cli-tree.py` re-run,
    or `tests/test_docs_generated.py` fails. That check is not in this task's test files: add
    it to the verify set.
12. **This repo's compiled file.** GREEN commits `.claude/rmx-instructions.json` (no units
    here) so AC-6 passes in every clone.
13. **Real states only.** The held-writer case opens the sandbox store with
    `Store(root).init()` and proves the lock is held by a failed second `duckdb.connect`.
    Nothing in `src/` is patched, and no new boundary fake is used, so the mock registry has
    no new entry.

{#traps-list}
