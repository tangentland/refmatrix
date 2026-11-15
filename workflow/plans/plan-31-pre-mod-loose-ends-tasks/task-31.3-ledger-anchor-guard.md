---
gmd: "0.1"
id: task-31.3-ledger-anchor-guard
title: "Task 31.3: every dated ledger bullet ends with exactly one anchor — a third step in the lint gate that fails on a cut bullet (bug-242 guard)"
tags: [task, plan-31, gmd, lint, bsd, impressions, ledger, freeze]
metadata:
  node_type: task
  status: drafting
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
---

# Task 31.3: dated ledger bullets carry an anchor {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t3]]).
> Status: Drafting. Written by ch-architect on Fable 5.2, 2026-11-15; ch-bsd spec review next.
> Depends on: nothing in code. Its real-corpus criterion ([[#ac-7]]) depends on the proposed
> decision `plan-31 D7` ([[#decisions]]; entered in [[plan-of-plans#decisions]] by the lead
> before it is amended here).
> Runs before [[task-31.4-retire-standing-warnings]]: both edit `scripts/lint-gmd.sh` and rely
> on the same gate-tree test helpers ([[#census]]).
> Closes the guard half of bug-242 ([[bug_registry#registry]]; the repair landed in `e7f1c8e`).

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t3]]
rel: depends-on -> [[bug_registry#registry]]
rel: depends-on -> [[bsd-impressions]]
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

## Measured at `f3a508f` (2026-11-15) {#baseline}

A census of dated bullets (a line starting `- 20YY-MM-DD`, outside code fences, with its
indented continuation lines), read-only:

| Where | Docs | Dated bullets | End with exactly one `{#id}` | No anchor |
|---|---|---|---|---|
| `workflow/bullshit/IMPRESSIONS.md` (id `bsd-impressions`) | 1 | 44 | 44 | 0 |
| `memory/impressions/impression_bsd_ledger_*.md` (all tagged `ledger-archive`) | 16 | 265 | 250 | 15 |
| **total** | 17 | 309 | 294 | **15** |
{#baseline-table}

No bullet has two anchors, and none has its anchor anywhere but the end. {#baseline-none}

**The 15 are whole bullets, not cut ones.** Each ends in a full sentence; it was written before
ids were routine and never got one. They are in six folded ledgers:
`impression_bsd_ledger_2026_10_06` (3, lines 53, 55, 56), `…_2026_10_07` (2, lines 73, 75),
`…_2026_10_14` (3, lines 75-77), `…_2026_10_15_16` (2, lines 34, 35), `…_2026_11_09` (2, lines
21, 22) and `…_2026_11_09b` (3, lines 21-23). The rule as the plan states it fails on all 15.
What happens to them is `plan-31 D7`. {#baseline-15}

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
  renamed or moved stays covered.
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
already resolved. As with lint and parity, every step always runs, and the wrapper's exit is
the worst of the three. {#r2-body}

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

## Acceptance criteria {#acceptance}

Tests are in `tests/test_ledger_anchor_guard.py`. Fixture docs are written by the tests into a
tmp tree; their text is synthetic.

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
- **AC-5 (RED): the real gate fails on it.** `test_the_lint_gate_fails_on_a_cut_bullet`: a tmp
  tree holding copies of the gate's scripts and the linter (built by `_gate_root` of
  `tests/test_bug179_anchor_parity.py`) plus one cut bullet. `bash scripts/lint-gmd.sh`
  exits non-zero, prints the finding, and still prints the lint summary and the parity line.
  {#ac-5}
- **AC-6 (RED): no input is not clean.** `test_no_ledger_doc_exits_2` and
  `test_impressions_md_that_is_not_selected_exits_2`. {#ac-6}
- **AC-7 (gate; RED at base by 15 findings): the real corpus is clean.**
  `./scripts/lint-gmd.sh` exits 0 on merged `master` with the memory dir in scope, and its
  ledger line reads 17 docs and 0 findings (the bullet count is whatever the ledgers then
  hold). `tests/test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate`
  already runs the real wrapper against a copy of the memory dir, so it carries this
  criterion. It is green only after `plan-31 D7` is applied. {#ac-7}
- **AC-8 (characterization): the other gate fixtures still run.** The three helpers that build
  a gate tree ([[#census]]) copy the new script, and the four test files that use them stay
  green. Without the copy the wrapper
  exits 2 there, by design. {#ac-8}

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
| M8 | drop the step from `scripts/lint-gmd.sh`; then: keep it but discard its exit status | [[#ac-5]] |
| M9 | exit 0 when no ledger doc was found | [[#ac-6]] |
{#mutations-table}

## Caller census {#census}

| What | Callers at `f3a508f` | Effect |
|---|---|---|
| `scripts/lint-gmd.sh`, run on the real tree | `CLAUDE.md` `#before-commit`; [[orchestration#reports]] step 4; `tests/test_gmd_lint_requires_version.py` | gains a step; fails on the 15 until D7 |
| `scripts/lint-gmd.sh`, copied into a fixture tree | three helpers: `_gate_root` in `tests/test_bug179_anchor_parity.py` (also imported by `tests/test_bug230_repo_scope_gate.py`), `_tree` in `tests/test_bug216_rev4.py`, `_root` in `tests/test_bug216_scope_parity.py` | each must also place `scripts/check-ledger-anchors.py`, or the wrapper exits 2. T0.1' did the same for `scripts/gmd_memdir.py` (ruling L126, MEH-2, in [[plan-of-plans#rulings]]). Found by `grep -n "lint-gmd.sh" tests/*.py`, re-checked at `c4b44d0` |
| `tools/gmd/lint.py` | unchanged; `ID_RE` and `strip_inline_code` are imported, not edited | none; the vendored-blob test is unaffected |
| the user-level memory hook (`lint-memory-gmd.sh`) | lints one memory file with the upstream linter | does **not** run this check ([[#risks]]) |
{#census-table}

The new test does not build a fourth tree of its own: [[#ac-5]] uses `_gate_root`. Three
hand-built gate trees that each had to learn about `gmd_memdir.py`, and now about this script,
are one missing shared helper ([[feedback_converge_repeated_shapes]]); that is suggested to
29.3, not required here. {#census-fifth}

## Files {#files}

| File | Change |
|---|---|
| `scripts/check-ledger-anchors.py` | new: the checker ([[#r1]], [[#r3]]) |
| `scripts/lint-gmd.sh` | a third step; the exit is the worst of three |
| `tests/test_ledger_anchor_guard.py` | new |
| the three gate-tree helpers in [[#census-table]] | copy the new script |
| `workflow/ORCHESTRATION.md` | [[#r4]] |
| six ledger memories, outside the repository | the lead's edit under `plan-31 D7`: 15 ids |
| `workflow/bug_registry.md` | bug-242's status, by the lead |
| `workflow/implementation_summaries/task-31.3-ledger-anchor-guard.md` | new |
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
5. **The gate turns red in every clone** between this task's merge and D7's edit. The two land
   together: the lead applies D7 before the merge, and [[#ac-7]] is run on merged `master`.
{#risks-list}

## Out of scope {#out-of-scope}

- Any change to the vendored linter or to the upstream GMD repository.
- Checking the prose of a bullet for truncation.
- The fold script (it is not in the repository).
- A shared gate-tree test helper.
{#out-of-scope-list}

## Proposed decisions {#decisions}

Each is **proposed**, not decided. The lead enters it in [[plan-of-plans#decisions]] under its id
first; only a decision made there is amended into this spec (the user, 2026-11-15; ruling L125 in
[[plan-of-plans#rulings]]). The recommended option is listed first, and each item names the
anchors that depend on it. Until a decision is amended in, the text at those anchors is the
recommended option written as a draft. {#decisions-proposed}

- **plan-31 D7 (proposed, [[plan-of-plans#decisions]]): what happens to the 15 whole dated
  bullets that never had an id** ([[#baseline-15]])?
  - (a) **Recommended.** The lead appends an id to each, in the six ledger memories, by the
    convention the ledger's generated ids already follow (`imp-<date>-<run>-<first words>`, as
    in `imp-2026-10-14-p19-21-r2-measure-the-window-before-y`), unique across the scanned set,
    and bumps each file's `updated`. 15 one-line additions make 15 lessons addressable, and the
    rule carries no exception. Existing ids are untouched, so "folded verbatim, anchor ids
    unchanged" still holds.
  - (b) An allow-list of the 15 in the checker. The rule ships with a standing exception, and
    the 15 stay unaddressable.
  - Depends on it: [[#ac-7]], [[#risks]] item 5, the ledger row of [[#files-table]].
  {#d7}

D7 edits memory files, which reach the store through the bridge; it changes no catalog directly.
{#decisions-l125}

## Design choices in this draft {#spec-decisions}

These are how the draft is built, open to ch-bsd's challenge. They are not `plan-31 D<n>`
decisions and none is recorded as decided anywhere. {#spec-decisions-note}

- **A wrapper step, not a linter rule** ([[#r2-why]]).
- **Selection by frontmatter** ([[#r1-defs]]), with [[#r3]]'s exit 2 as the proof the selection
  still finds the ledger.
- **Three findings, not one.** The plan says "exactly one `{#id}`" and "ends with": two anchors
  and a misplaced anchor are the other ways a block stops being one addressable bullet.
{#spec-decisions-list}
