---
gmd: "0.1"
id: task-31.3-ledger-anchor-guard
title: "Task 31.3: every dated ledger bullet ends with exactly one anchor — a third step in the lint gate that fails on a cut bullet (bug-242 guard), and one shared helper for the gate's test trees"
tags: [task, plan-31, gmd, lint, bsd, impressions, ledger, freeze]
metadata:
  node_type: task
  status: approved
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
  revision: 3
---

# Task 31.3: dated ledger bullets carry an anchor {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t3]]).
> Status: **Approved** by ruling L140 in [[plan-of-plans#rulings]] (ch-bsd confirm-lite r2,
> MEH-only GO; L125), revision 3. Written by ch-architect on Fable 5.2, 2026-11-15. Revision 2
> folded ch-bsd spec review r1 per ruling L133 ([[#rev-r1]]); revision 3 folds r2's `M5`
> ([[#rev-r2]]).
> Depends on: nothing in code. **Precondition of GREEN:** the lead's `plan-31 D7` edit to six
> ledger memories ([[#d7-ids]]), recorded before GREEN starts ([[#r5]]). The lead applied it on
> 2026-11-15 (POP; the census then reads 312 dated bullets, 312 with one end anchor).
> Queue: row 5 of [[plan-of-plans#queue]], after 31.5's capture release and before 31.4.
> Runs before [[task-31.4-retire-standing-warnings]]: both edit `scripts/lint-gmd.sh`, and 31.4
> and 31.6 build on the helper this task adds ([[#r6]]).
> Closes the guard half of bug-242 ([[bug_registry#registry]]; the repair landed in `e7f1c8e`).

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t3]]
rel: depends-on -> [[bug_registry#registry]]
rel: depends-on -> [[bsd-impressions]]
rel: depends-on -> [[plan-of-plans#decisions]]
rel: derives-from -> [[task-bug179-lint-ingest-anchor-parity]]
rel: related-to -> [[task-31.4-retire-standing-warnings]]
rel: related-to -> [[orchestration#reports]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]

## Why {#why}

On 2026-11-13 three ch-bsd ledger bullets were committed cut to their first line, with no body
and no `{#id}`. Each was a lesson another run was meant to recall, and none was addressable.
The lint passed, because a bullet without an anchor is legal GMD (bug-242). The bullets were
restored; nothing stops the next cut. [[orchestration#reports]] step 3 now tells the lead to
copy whole blocks "each ending in exactly one `{#id}`", and nothing checks that either.
{#why-body}

## Measured (2026-11-15) {#baseline}

A census of dated bullets (a line starting `- 20YY-MM-DD`, outside code fences, with its
indented continuation lines), read-only, by
`workflow/measurements/task-31.3-ledger-census/ledger_census.py` (committed with this spec).
First counted at `f3a508f`; the table is the recount on the merged base `c96a0b1`. ch-bsd
re-counted the 15 with its own parser in r1 and got the same split.

| Where | Docs | Dated bullets | End with exactly one `{#id}` | No anchor |
|---|---|---|---|---|
| `workflow/bullshit/IMPRESSIONS.md` (id `bsd-impressions`) | 1 | 47 | 47 | 0 |
| `memory/impressions/impression_bsd_ledger_*.md` (all tagged `ledger-archive`) | 16 | 265 | 250 | 15 |
| **total** | 17 | 312 | 297 | **15** |
{#baseline-table}

No bullet has two anchors, and none has its anchor anywhere but the end. {#baseline-none}

**The 15 are whole bullets, not cut ones.** Each ends in a full sentence; it was written before
ids were routine and never got one. They are in six folded ledgers, listed with their ids in
[[#d7-ids]]. The rule as the plan states it fails on all 15. {#baseline-15}

Two more facts the rule has to respect:

- The ledgers also hold 19 undated top-level bullets (in `…_2026_10_07` and `…_2026_10_14`),
  and `IMPRESSIONS.md` holds 42 (its former-anchors list). The plan's rule is about dated
  bullets; these are counted and printed, not checked. {#baseline-undated}
- The ledgers live in the memory dir, outside the repository. `scripts/lint-gmd.sh` adds that
  dir to its scope when its resolver (`scripts/gmd_memdir.py`, T0.1') finds one. Where it finds
  none, only `IMPRESSIONS.md` is checked, and the summary line shows one ledger doc.
  {#baseline-memdir}

## Requirements {#requirements}

### R1: the rule {#r1}

In a **ledger doc**, every **dated bullet** ends with exactly one `{#id}`.

- **Ledger doc:** a GMD doc whose frontmatter `id` is `bsd-impressions`, or whose `tags`
  include `ledger-archive`. Selection is by frontmatter, not by path, so a ledger that is
  renamed or moved stays covered. ch-bsd checked the selection in r1: all 16 ledger files carry
  the tag, and the only other docs with dated bullets are ch-bsd reports, whose impression
  sections are staging copies the rule rightly skips.
- **Dated bullet:** a line matching `- 20YY-MM-DD` at column 0, outside a code fence, plus the
  lines that follow it indented by two or more spaces. A blank line or a line at column 0 ends
  the block.
- **Anchor:** matched with the linter's own `ID_RE`, after the linter's own
  `strip_inline_code`. An id inside a code span is not an anchor. The checker imports both from
  `tools/gmd/lint.py`; it does not carry a regex of its own
  ([[task-bug179-lint-ingest-anchor-parity]]: two parsers of one syntax drift).
{#r1-defs}

| Finding | When |
|---|---|
| `ledger-no-anchor` | the block holds no anchor. This is the bug-242 shape: a bullet cut to its first line loses the anchor at its end |
| `ledger-multi-anchor` | the block holds two or more anchors (on one line the linter already fails this; across lines nothing does) |
| `ledger-anchor-not-last` | the block's one anchor is not the last token of its last non-blank line: text follows the id, so the block was joined or cut mid-way |
{#r1-findings}

Each finding prints `path:line: error: [<finding>] <first 60 characters of the bullet>`. The
checker never stops at the first one. {#r1-output}

### R2: where it runs {#r2}

A new script, `scripts/check-ledger-anchors.py`, standard library plus the vendored linter's
two names. `scripts/lint-gmd.sh` runs it as a third step over `workflow/` and the memory dir it
already resolved, with `python3`, not the dev interpreter: the checker imports nothing from
`refmatrix`, so a clone with no `.venv-eval` still runs this step (bug-253). As with lint and
parity, every step always runs, and the wrapper's exit is the worst of the three. {#r2-body}

**Why a step in the wrapper, and not a rule in `tools/gmd/lint.py`.** The linter is vendored:
`tests/test_bug179_anchor_parity.py` requires it to be a committed blob of the upstream GMD
repository, which every other project and the user-level memory hook also run. "A dated bullet
in a ch-bsd ledger carries an id" is this workflow's convention, not GMD's. The wrapper is where
this repository already adds its own checks to the gate (anchor parity for bug-179, scope
parity for bug-216). {#r2-why}

### R3: the gate cannot pass by checking nothing {#r3}

- The checker prints one summary line on stderr:
  `ledger anchors: <D> ledger doc(s), <B> dated bullet(s), <F> finding(s), <U> undated bullet(s) not checked`.
- It exits 2, not 0, when it found no ledger doc among its targets, or when
  `workflow/bullshit/IMPRESSIONS.md` exists under the root and was not selected as one (its id
  or tags changed). A check whose input vanished must not read as clean.
- Exit codes: 0 clean, 1 findings, 2 could not check.
{#r3-list}

### R4: the procedure says what checks it {#r4}

[[orchestration#reports]] step 3 gains: "checked by step 4's gate". No other process text
changes. {#r4-body}

### R5: the ledger edit comes before GREEN {#r5}

The memory dir is outside the repository, so the 15 ids and the checker cannot land in one
commit. The order is the guarantee:

1. The lead applies `plan-31 D7` to the six ledger memories: the 15 ids of [[#d7-ids]], each
   appended to its bullet's last line, and each file's `updated` bumped.
2. The lead records the proof on the task's branch: the census script's output for the memory
   dir, reading `none=0` on every ledger.
3. Only then does GREEN start. From that point
   `tests/test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate`
   runs the new step against a copy of the memory dir, and it fails on any of the 15 still
   without an id.
{#r5-steps}

RED may be written before step 1: its fixtures are synthetic. {#r5-red}

### R6: one helper builds the gate's test tree {#r6}

Three test helpers each build a throwaway checkout holding the gate's scripts by hand:
`_gate_root` in `tests/test_bug179_anchor_parity.py` (also imported by
`tests/test_bug230_repo_scope_gate.py`), `_gate_root` in `tests/test_bug216_rev4.py`, and
`_root` in `tests/test_bug216_scope_parity.py`. Each had to learn about `scripts/gmd_memdir.py`
in T0.1' (ruling L126, MEH-2). Each would have to learn about this task's checker now, and
about `tools/gmd/resolve.py` when 31.6 lands. That is the same edit three times in a week
across the same three places; this task makes it once (ruling L133, B2).

- **The wrapper declares its file set.** `scripts/lint-gmd.sh` gains a block of
  `# gate-file: <path relative to the checkout root>` lines naming every file the gate runs or
  imports: itself, `scripts/gmd_memdir.py`, `scripts/check-gmd-parity.py`,
  `scripts/check-ledger-anchors.py`, `tools/gmd/lint.py`.
- **One helper places it.** `tests/gmd_gate_tree.py` exposes one function that makes a root
  under a short `mkdtemp()`, copies exactly the declared files from the checkout, and adds the
  `.git` marker, the `src` symlink and, on request, the `.venv-eval` symlink. It takes
  per-file text overrides (the bug-179 tests plant a mutated linter) and returns the root.
  Fixture docs stay each caller's business.
- **The three helpers become thin callers** of it, keeping their names and signatures, so no
  test body changes.
- **A later task adds one line.** 31.6 adds `# gate-file: tools/gmd/resolve.py`; 31.4 adds
  nothing.
{#r6-list}

**The bypass check.** A test scans `tests/**/*.py`, subdirectories included, for any line
outside `tests/gmd_gate_tree.py` that copies or writes `lint-gmd.sh` into a tree, or that
`copytree`s `scripts/` or `tools/gmd/` (which would carry the gate along unseen). It fails
naming the file and line. Its own "sees" guard: the scan must find the helper's copy, or the
scan itself is broken. {#r6-bypass}

**Imports are declared too.** The wrapper names the scripts it runs, not what they import.
31.6's `tools/gmd/resolve.py` is imported by `lint.py` and named nowhere in the wrapper, so a
check of the wrapper's paths alone would pass with its `gate-file` line missing, and every
copied tree would then fail at a distance. The declared-file check therefore also reads each
declared Python file and requires every sibling module it imports from its own directory to be
declared. {#r6-imports}

## Acceptance criteria {#acceptance}

Tests are in `tests/test_ledger_anchor_guard.py` unless named. Fixture docs are written by the
tests into a tmp tree; their text is synthetic.

- **AC-1 (RED at base): a cut bullet fails.** `test_a_bullet_cut_to_its_first_line_fails`: a
  ledger doc (tag `ledger-archive`, an arbitrary filename) holding
  `- 2026-11-13 (fixture r1, abc1234): A DEFAULT CHANGED IN ONE PREDICATE CHANGES EVERY CALLER, SO`
  and nothing more gives exit 1 and `[ledger-no-anchor]` with the file and line. At base the
  script does not exist. {#ac-1}
- **AC-2 (RED): whole bullets pass.** `test_whole_bullets_pass`, three shapes taken from the
  real ledger: one line ending in its id; four wrapped lines with the id ending the last; the
  id alone on its own continuation line. {#ac-2}
- **AC-3 (RED): the other two findings.** `test_two_anchors_across_lines_fail` and
  `test_an_anchor_followed_by_text_fails`, each naming its finding and no other. {#ac-3}
- **AC-4 (RED): only ledger bullets are judged.** `test_non_ledger_docs_are_not_judged` (a
  changelog-shaped doc with dated, anchorless bullets passes), `test_fenced_bullets_are_ignored`
  and `test_an_id_inside_a_code_span_is_not_the_anchor` (a bullet whose only `{#id}` is in
  backticks fails `ledger-no-anchor`). {#ac-4}
- **AC-5 (RED): the real gate fails on it.** `test_the_lint_gate_fails_on_a_cut_bullet`: a tree
  built by `tests/gmd_gate_tree.py` plus one cut bullet. `bash scripts/lint-gmd.sh` exits
  non-zero, prints the finding, and still prints the lint summary and the parity line.
  `test_the_ledger_step_does_not_need_the_dev_interpreter` runs the checker's own command line,
  as the wrapper spells it, with the system `python3` in a tree that has no `.venv-eval`, and
  gets the finding. {#ac-5}
- **AC-6 (RED): no input is not clean.** `test_no_ledger_doc_exits_2` and
  `test_impressions_md_that_is_not_selected_exits_2`. {#ac-6}
- **AC-7 (gate): the real corpus is clean.** `./scripts/lint-gmd.sh` exits 0 on merged
  `master` with the memory dir in scope, and its ledger line reads 17 docs and 0 findings (the
  bullet count is whatever the ledgers then hold).
  `tests/test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate`
  already runs the real wrapper against a copy of the memory dir, so it carries this
  criterion. It would be red by 15 findings without [[#r5]]; with [[#r5]] done first it is
  green from GREEN's first run. {#ac-7}
- **AC-8 (characterization): the converted helpers change no test.** The four files that use
  the three helpers (`test_bug179_anchor_parity`, `test_bug216_rev4`,
  `test_bug216_scope_parity`, `test_bug230_repo_scope_gate`) and
  `tests/test_lint_gmd_memdir_fallback.py` pass with the same collected count and the same
  outcomes as at base; the summary quotes both runs' counts. {#ac-8}
- **AC-9 (RED at base): the helper places what the wrapper declares, and the wrapper declares
  what it runs.** `tests/test_gmd_gate_tree.py`:
  `test_the_helper_places_exactly_the_declared_files` (given a copy of the wrapper with one
  more `gate-file` line, the helper places that file too);
  `test_every_file_the_gate_runs_is_declared` (every `"$ROOT/…"` script or tool path the
  wrapper assigns is in the declared list, and every declared file exists);
  `test_every_sibling_import_of_a_declared_file_is_declared` ([[#r6-imports]]: for each
  declared Python file, each module it imports that exists beside it must be declared; proven
  on a copy of the tree where a declared file gains `import sibling_fixture` with no
  `gate-file` line);
  `test_a_helper_tree_runs_every_step` (a tree of clean mini-docs passes
  `assert_gate_ran_clean`, the shared verdict in `tests/test_gmd_lint_requires_version.py`).
  At base there is no helper and no declared list. {#ac-9}
- **AC-10 (RED at base): no gate tree is built by hand.**
  `tests/test_gmd_gate_tree.py::test_no_test_builds_a_gate_tree_by_hand` ([[#r6-bypass]]). At
  base it names the three helpers. Its fixture cases, on planted files in a tmp `tests/`
  tree: a copy of `lint-gmd.sh` in `tests/sub/test_x.py`, and a `copytree` of `scripts/` and
  of `tools/gmd/`; each is named. {#ac-10}
- **AC-11 (gate, before GREEN): the precondition is recorded.** The implementation summary
  quotes the census output of [[#r5-steps]] step 2, with the date of the lead's edit, ahead of
  GREEN's first commit. {#ac-11}

## Mutations {#mutations}

| Id | Mutation | Must fail |
|---|---|---|
| M1 | judge only the bullet's first line (the bug's own shape) | [[#ac-2]]: a wrapped whole bullet is reported |
| M2 | remove `ledger-no-anchor` | [[#ac-1]] |
| M3 | accept one or more anchors | [[#ac-3]] (multi) |
| M4 | accept the anchor anywhere in the block | [[#ac-3]] (not last) |
| M5 | treat every doc as a ledger doc | [[#ac-4]] |
| M6 | count an id inside a code span | [[#ac-4]] |
| M7 | select ledger docs by filename instead of frontmatter | [[#ac-1]]: its fixture has an arbitrary name |
| M8 | drop the step from `scripts/lint-gmd.sh`; then: keep it but discard its exit status | [[#ac-5]] (the gate test) |
| M9 | exit 0 when no ledger doc was found | [[#ac-6]] (`test_no_ledger_doc_exits_2`) |
| M10 | exit 0 when `IMPRESSIONS.md` is present but not selected | [[#ac-6]] (`test_impressions_md_that_is_not_selected_exits_2`) |
| M11 | the checker imports `refmatrix` (so it needs the dev interpreter) | [[#ac-5]] (`test_the_ledger_step_does_not_need_the_dev_interpreter`) |
| M12 | remove the checker's `gate-file` line from the wrapper | [[#ac-9]] (`test_every_file_the_gate_runs_is_declared`), [[#ac-5]] |
| M13 | the helper hard-codes its file set instead of reading the wrapper | [[#ac-9]] (`test_the_helper_places_exactly_the_declared_files`) |
| M14 | one helper goes back to copying `lint-gmd.sh` itself | [[#ac-10]] |
| M15 | the bypass scan's pattern is broken so it matches nothing | [[#ac-10]] (its "sees" assertion) |
| M16 | the bypass scan reads only `tests/*.py`; then: it ignores `copytree` | [[#ac-10]] (the subdirectory case; the `copytree` cases) |
| M17 | the sibling-import check is removed | [[#ac-9]] (`test_every_sibling_import_of_a_declared_file_is_declared`) |
{#mutations-table}

## Caller census {#census}

Re-checked at `c96a0b1`.

| What | Callers | Effect |
|---|---|---|
| `scripts/lint-gmd.sh`, run on the real tree | `CLAUDE.md` `#before-commit`; [[orchestration#reports]] step 4; `tests/test_gmd_lint_requires_version.py`; `tests/test_lint_gmd_memdir_fallback.py` | gains a step and the `gate-file` block |
| `scripts/lint-gmd.sh`, copied into a fixture tree | three helpers: `_gate_root` in `tests/test_bug179_anchor_parity.py` (also imported by `tests/test_bug230_repo_scope_gate.py`), `_gate_root` in `tests/test_bug216_rev4.py`, `_root` in `tests/test_bug216_scope_parity.py`. Found by `grep -n "lint-gmd.sh" tests/*.py` | all three become callers of `tests/gmd_gate_tree.py` ([[#r6]]); [[#ac-10]] keeps it that way |
| `tools/gmd/lint.py` | unchanged; `ID_RE` and `strip_inline_code` are imported, not edited | none; the vendored-blob test is unaffected. After 31.6 the linter imports `resolve.py`, which that task declares as a `gate-file` |
| the user-level memory hook (`lint-memory-gmd.sh`) | lints one memory file with the upstream linter | does **not** run this check ([[#risks]]) |
{#census-table}

## Files {#files}

| File | Change |
|---|---|
| `scripts/check-ledger-anchors.py` | new: the checker ([[#r1]], [[#r3]]) |
| `scripts/lint-gmd.sh` | a third step, run with `python3`; the `gate-file` block; the exit is the worst of three |
| `tests/gmd_gate_tree.py` | new: the shared helper ([[#r6]]) |
| `tests/test_gmd_gate_tree.py` | new: [[#ac-9]], [[#ac-10]] |
| `tests/test_ledger_anchor_guard.py` | new |
| `tests/test_bug179_anchor_parity.py`, `tests/test_bug216_rev4.py`, `tests/test_bug216_scope_parity.py` | their helpers call the shared one |
| `workflow/ORCHESTRATION.md` | [[#r4]] |
| six ledger memories, outside the repository | the lead's edit, before GREEN ([[#r5]], [[#d7-ids]]) |
| `workflow/bug_registry.md` | bug-242's status, by the lead |
| `workflow/implementation_summaries/task-31.3-ledger-anchor-guard.md` | new |
| `workflow/measurements/task-31.3-ledger-census/ledger_census.py` | committed with this spec |
{#files-table}

## Risks {#risks}

1. **The memory dir is absent** on a machine or in a decoy home: 16 of the 17 ledger docs are
   then unchecked. The wrapper says which dir it used; the summary line shows the doc count, so
   "1 ledger doc" is visible.
2. **A fold writes straight into the memory dir,** where the per-file hook does not run this
   check. The cut is caught at the next `./scripts/lint-gmd.sh`, which every commit of a
   persisted report requires, not at the write.
3. **A cut that keeps the bullet's last line** (the middle lost, the id kept) passes. The rule
   guards the anchor, not the prose. Out of scope.
4. **Undated bullets** are not checked ([[#baseline-undated]]). A run bullet written without a
   date escapes; the count is printed so a jump is visible.
5. **The lead's edit is skipped or partial.** GREEN's first verify run then fails AC-7 by the
   bullets still without an id, which is the intended stop; [[#ac-11]] makes the skipped step
   visible before that.
6. **Converting three helpers changes five test files' setup at once.** AC-8 compares collected
   counts and outcomes with base, so a test that silently stopped running is seen.
{#risks-list}

## Out of scope {#out-of-scope}

- Any change to the vendored linter or to the upstream GMD repository.
- Checking the prose of a bullet for truncation.
- The fold script (it is not in the repository).
- The fixture docs each gate-tree caller plants; only the gate's own file set is shared.
{#out-of-scope-list}

## Decisions {#decisions}

**plan-31 D7 is decided in [[plan-of-plans#decisions]]** (ruling L125: the architect's
recommendation; memory edits are the lead's) and amended in here: the lead appends an id to
each of the 15 whole dated bullets that never had one, in the six ledger memories. Not taken:
an allow-list in the checker. Ruling L133 (M3) fixes the order: the edit lands before GREEN
starts ([[#r5]]). Amended into [[#r5]], [[#ac-7]], [[#ac-11]], [[#files-table]]. {#d7}

### The 15 bullets and their ids {#d7-ids}

Each id is appended to the end of its bullet's last line, after one space. The ids follow the
style the ledgers already use (a short hand-written slug of the lesson, `imp-…`); none collides
with an anchor in `workflow/`, `docs/` or the memory dir at `c96a0b1`. Line numbers are those
of the census above. The opening quoted is the bullet's own first words, as folded from the
public `IMPRESSIONS.md`. The ids are written here as code so that this table registers no
anchors of its own.

| Ledger memory | Line | Bullet opens | Id to append |
|---|---|---|---|
| `impression_bsd_ledger_2026_10_06` | 53 | `2026-10-06 (plan-16 spec review) — A "FAITHFUL" RE-RUN IS ITS OWN ORACLE` | `imp-faithful-rerun-is-its-own-oracle` |
| `impression_bsd_ledger_2026_10_06` | 55 | `2026-10-06 (plan-16 spec review) — SWAPPING THE ENGINE SWAPS THE CORPUS` | `imp-swapping-the-engine-swaps-the-corpus` |
| `impression_bsd_ledger_2026_10_06` | 56 | `2026-10-06 (plan-16 spec review) — root IS TWO DIFFERENT DIRECTORIES IN THIS CODEBASE` | `imp-root-is-two-directories` |
| `impression_bsd_ledger_2026_10_07` | 73 | `2026-10-07 (r10 remedy r11): A COLD GATE IS ONLY AS LIVE AS WHATEVER REFILLS IT` | `imp-cold-gate-needs-its-refiller` |
| `impression_bsd_ledger_2026_10_07` | 75 | `2026-10-07 (r11): A MUTATION SUMMARY IS A COUNT OF LOG LINES` | `imp-mutation-summary-is-a-log-line-count` |
| `impression_bsd_ledger_2026_10_14` | 75 | `2026-10-14 (p19/21 r4): "Before it changes anything" must be checked against the CALLER, not the method` | `imp-first-claim-checked-against-the-caller` |
| `impression_bsd_ledger_2026_10_14` | 76 | `2026-10-14 (p19/21 r4): To retire a fallback, list its callers with a scan, not from memory` | `imp-retire-a-fallback-by-scan` |
| `impression_bsd_ledger_2026_10_14` | 77 | `2026-10-14 (p19/21 r4): A hotfix that lands mid-review becomes the spec's baseline` | `imp-mid-review-hotfix-is-the-baseline` |
| `impression_bsd_ledger_2026_10_15_16` | 34 | `2026-10-15 (plan-20 r1): CO-OCCURRENCE ACROSS TWO INGEST PATHS IS ZERO BY CONSTRUCTION` | `imp-cooccurrence-zero-across-ingest-paths` |
| `impression_bsd_ledger_2026_10_15_16` | 35 | `2026-10-15 (plan-20 r1): A PRECISION GATE NEEDS A SAMPLE THAT CAN REACH IT` | `imp-precision-gate-needs-a-reachable-sample` |
| `impression_bsd_ledger_2026_11_09` | 21 | `2026-11-09 (plan-26/27 spec r1, 96feccd): A NEW PLAN CAN RE-SPECIFY AN APPROVED ONE WITHOUT A SINGLE EDGE` | `imp-new-plan-respecifies-without-an-edge` |
| `impression_bsd_ledger_2026_11_09` | 22 | `2026-11-09 (plan-26/27 spec r1): A VERB THAT TAKES A PATH BUT WRITES THROUGH A CWD RESOLVER WRITES TO THE WRONG STORE` | `imp-path-verb-writes-through-cwd-resolver` |
| `impression_bsd_ledger_2026_11_09b` | 21 | `2026-11-09 (plan-25 spec r2, 5b8ed15): MOVING A LEG INTO A SHARED VERB CHANGES EVERY OTHER CALLER OF THAT VERB` | `imp-shared-verb-leg-changes-every-caller` |
| `impression_bsd_ledger_2026_11_09b` | 22 | `2026-11-09 (plan-25 spec r2): A BUDGET SPLIT MUST BE KEYED BY THE UNIT THE CAP APPLIES TO` | `imp-budget-split-keyed-by-the-capped-unit` |
| `impression_bsd_ledger_2026_11_09b` | 23 | `2026-11-09 (plan-25 spec r2): A TRANSLATION RULE NEEDS A DEFINED OUTCOME FOR ITS OWN COMPILE FAILURE` | `imp-translation-rule-needs-a-compile-failure-outcome` |
{#d7-table}

In the file, each id is written in the usual anchor form: an opening brace, `#`, the id, a
closing brace. {#d7-form}

Each of these bullets is followed in its file by `rel:` lines. A `rel:` attaches to the nearest
enclosing block with an id, so today those edges hang on the previous anchored bullet; with the
id appended they attach to their own. That is a change to 15 bullets' edges in the store at the
next bridge run, and it is the correction, not a side effect. {#d7-rel}

## Design choices in this draft {#spec-decisions}

These are how the draft is built, open to ch-bsd's challenge. They are not `plan-31 D<n>`
decisions. {#spec-decisions-note}

- **A wrapper step, not a linter rule** ([[#r2-why]]).
- **Selection by frontmatter** ([[#r1-defs]]), with [[#r3]]'s exit 2 as the proof the selection
  still finds the ledger.
- **Three findings, not one.** The plan says "exactly one `{#id}`" and "ends with": two anchors
  and a misplaced anchor are the other ways a block stops being one addressable bullet.
- **The wrapper is the source of the gate's file set,** read by the helper, so the list cannot
  drift from the script that uses it ([[#r6-list]]).
{#spec-decisions-list}

## Revision 2: the ch-bsd r1 fold (2026-11-15, ruling L133) {#rev-r1}

The report is held with this branch until its merge, so its finding ids are written as code.

| Finding | Change here |
|---|---|
| `B2`: the shared gate-tree helper was deferred to 29.3, which has no slice for it | [[#r6]]: this task builds `tests/gmd_gate_tree.py`, the wrapper declares its file set, the three helpers become callers; [[#ac-8]], [[#ac-9]], [[#ac-10]]; mutations M12 to M15; the "suggested to 29.3" text and the out-of-scope line are gone |
| `M1`: the census named `_tree` for `test_bug216_rev4` | [[#census-table]] and [[#r6]] name `_gate_root` |
| `M3`: D7's edit must land before GREEN, not only before the merge | [[#r5]], [[#ac-11]]; the 15 bullets and their exact ids are in [[#d7-table]]; the census script is committed as the precondition check |
| `M4`: no mutation for the IMPRESSIONS-not-selected exit; the interpreter was not named | mutation M10; [[#r2-body]] names `python3`; a second test in [[#ac-5]] and mutation M11 |
| `B2`'s third instance (31.6's `resolve.py`) | [[#r6-list]]: 31.6 adds one `gate-file` line |
| D7 decided (L125), ordered by L133 | [[#d7]] |
{#rev-r1-table}

## Revision 3: the ch-bsd r2 fold (2026-11-15, ruling L140) {#rev-r2}

ch-bsd confirm-lite r2 was a MEH-only GO; ruling L140 approves the spec once its share folds.

| Finding | Change here |
|---|---|
| `M5`: the bypass scan missed subdirectories and `copytree`; the declared-file check missed imports | [[#r6-bypass]]: `tests/**/*.py`, and `copytree` of `scripts/` or `tools/gmd/`; [[#r6-imports]] and a third test in [[#ac-9]]; fixture cases in [[#ac-10]]; mutations M16, M17 |
| the D7 precondition | met: the lead applied the 15 ids on 2026-11-15 (header) |
{#rev-r2-table}
