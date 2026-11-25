---
gmd: "0.1"
id: agent-brief-fold-i1b1
title: "Brief: I1.b1 fold of bsd-i1b1 r1: b-1 replay unmeasurable keys, b-2 KIND_DIR enforced, g-1..g-4 killing tests, s-1..s-5"
tags: [agent-brief, fold, i1, instructions]
metadata:
  node_type: brief
  created: 2026-11-25
---

# I1.b1 fold (bsd-i1b1 r1) {#root}

rel: implements -> [[bsd-i1b1-r1-2f392131]]
rel: part-of -> [[task-I1.b1-units-and-check]]

Two hands, in this order, in one clone: `/Volumes/littlebig/refmatrix-i1b1-green`, branch
`task-I1.b1-units-and-check` at `2f392131`. Read the report first:
`/Volumes/littlebig/refmatrix-i1b1-green/workflow/review-output/bsd-i1b1-r1-report.md`
(`#b-1`, `#b-2`, `#gate`, `#s-1`..`#s-5`). Spec:
`workflow/plans/plan-32-tasks/task-I1.b1-units-and-check.md`. {#lead}

## Lead's rulings on the open choices {#rulings}

- **s-1 = (a).** A missing `.claude/rmx-instructions.json` when the compile yields zero units is
  `generated` (in sync), not drift. This keeps spec risk 3 true; no file is dropped into a
  consumer repo that has no units. With one or more units, a missing file stays drift.
- **s-2: refuse at compile.** A prefilter string containing `"`, `\` or `:` is refused (AC-2
  class, named). The dispatcher (I1.b3) tests raw bytes; a structural prefilter cannot be
  checked the same way in both places.
- **s-4: cap `commits` at 10 at parse** (refused above, named). No total budget on the leg in
  this task; I1.b3 AC-9 owns the dispatcher's.
- **m-1:** the failure line names the leg that drifted, not settings.json when settings is in sync.
- m-2, m-3, m-5, m-6 are not folded (MEH; m-3 goes to I1.b3).

## Stage 1: RED (ch-test-engineer) {#red}

Extend the existing files (`tests/test_instruction_units.py` and the `--check` class tests);
parametrize; no new file. Each case below must FAIL at `2f392131` for its stated reason; record
the E line.

1. **b-1:** replay of a Write unit bound to `content` (and an Edit unit bound to `new_string`)
   over a real ring event written by `cli._tool_event_fields`: output names the bind as
   unmeasurable (`unmeasurable: bind[0].match.content is not stored in the ring`) and the hit
   count leaves it out. Use the real ring writer, not a hand-built detail.
2. **b-2:** AC-2 case: a deny unit placed under `.claude/rules/` (kind dir mismatch) makes
   `--apply` exit 1 naming the kind/dir; nothing written.
3. **g-1:** `test_replay` gains a 4th ring command `rmfoo --all x/ --dry-run`; hits stay 1.
4. **g-2:** AC-2 case: a plain `.md` with no `unit:` map (and one with `units:` misspelt) in
   `.claude/triggers/` and `.claude/checks/`: `--apply` exits 1 naming "not a unit".
5. **g-3:** hand-edit the installed packaged rule, run `--apply` WITHOUT `--force`: file
   unchanged, output has a `skip` line. (Note `APPLY_ARGS` passes `--force`; this case must not.)
6. **g-4:** AC-5 case: `.git/hooks/pre-push` carrying the `# refmatrix:` marker with no generated
   counterpart: `--check` exit 1, the hook named.
7. **s-1:** a unit-less git project: `--check` with no compiled file exits 0 and classes it
   generated; with one local unit and no compiled file, exit 1 `missing`.
8. **s-2:** AC-2 cases: prefilters containing `"`, `\`, `:` each refused, named.
9. **s-3:** a local trigger (and check) at the same path as a packaged trigger: `--apply` exits 1
   with "duplicate path with a packaged unit". Build the packaged layer the way the existing
   overlay test does (a real copied package, no monkeypatch).
10. **s-4:** `commits: 11` refused at parse, named; `commits: 10` accepted.
11. **s-5:** tighten the replay assertions: parse `hits (\d+)` == 1 and `scanned (\d+)` == 4
    (after g-1), not the loose `\b1\b\D{0,20}hits?\b`.
12. **m-1:** a git-hook-only drift: the failure output does not say `hooks drift …settings.json`.

Commit, run the touched files on a lane in the clone (you run as an isolated agent only if the
lead said so; otherwise `scripts/lane-local.sh /Volumes/littlebig/refmatrix-i1b1-green <sha>
i1b1-fold-red <files>`), read the log yourself, report the E lines per case.

## Stage 2: GREEN (ch-implementer, separate hand) {#green}

Make RED's fold cases pass; write no test. Fixes per the report and the rulings above:
`replay` unmeasurable keys (compare each bind's `match` keys with what the ring stores per tool);
`load_layers` refuses a kind/dir mismatch (`KIND_DIR`) and a not-a-unit file under
triggers/checks, and refuses (not skips) a local path equal to a non-installed packaged path;
delete `compile_project`; s-1 (a); s-2 refusal; s-4 cap; m-1 message. Then:

- Mutations on the `src/` change, one at a time, restored with `git checkout -- src/` in its own
  command, `__pycache__` cleared after the batch: drop the unmeasurable check; drop the KIND_DIR
  check; drop the not-a-unit refusal; drop the `not force` guard (X1); drop the `want is None`
  branch (X3); drop the s-1 zero-unit case; drop each s-2 character; drop the s-4 cap; restore the
  s-3 skip. Each must fail a test.
- Verify on a lane: RED's four files + the fold files, every importer of a changed module, and
  the nine repo guards (`test_tmp_root_census`, `test_suite_discipline`, `test_docs_generated`,
  `test_mock_registry_coverage`, `test_deferrals_clean`, `test_wallclock_census`,
  `test_budget_outcome_census`, `test_verb_parity`, `test_bug212_r4_red`). Run
  `./scripts/lint-gmd.sh`. Update the implementation summary.

## Rules for both {#rules}

Read-only against every live store. Look things up with
`/Users/tholley/claude_tools/refmatrix/scripts/rmx-master` or the read-only MCP tools. Never
`find /`, never export `REFMATRIX_ROOT`, never push, never touch the dev tree (it is running the
release gate). Every background wait has a deadline. Report as text, and if it is long write it
to `workflow/review-output/i1b1-fold-<red|green>-report.md` in the clone (uncommitted) and reply
with the path: shas, lane logs with counts, E lines, the mutation table.
