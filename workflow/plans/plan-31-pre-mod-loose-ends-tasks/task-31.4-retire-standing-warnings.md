---
gmd: "0.1"
id: task-31.4-retire-standing-warnings
title: "Task 31.4: zero standing lint warnings — each of the four warning classes fails the gate or is retired, by a table, so a new warning is read"
tags: [task, plan-31, gmd, lint, warnings, graph-correctness, freeze]
metadata:
  node_type: task
  status: drafting
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
---

# Task 31.4: retire the warnings nobody acts on {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t4]]).
> Status: Drafting. Written by ch-architect on Fable 5.2, 2026-11-15; ch-bsd spec review next.
> Depends on: `plan-31 D41`-`D43` ([[#decisions]]). D43 is consent to change the upstream GMD
> linter, which this repository vendors.
> Runs after [[task-31.3-ledger-anchor-guard]] (both edit `scripts/lint-gmd.sh`). Must not be
> in flight together with 31.6 (`task-31.6`, another author's spec, not on this branch): both
> change `tools/gmd/lint.py` and its upstream, and 31.6 decides how an ambiguous stem is
> refused ([[#overlap-31-6]]).

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t4]]
rel: depends-on -> [[task-bug179-lint-ingest-anchor-parity]]
rel: related-to -> [[task-31.3-ledger-anchor-guard]]
rel: related-to -> [[bug_registry#registry]]
rel: related-to -> [[orchestration#planning]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]

## Why {#why}

`./scripts/lint-gmd.sh` exits 0 and prints 89 warnings. Nobody reads them, so a ninetieth would
not be read either. The same thing happened to a missing `gmd:` key until it was made an error
(`tests/test_gmd_lint_requires_version.py`: "as a warning it was a gate that could not fail").
The plan's target is zero standing warnings, reached by deciding each **class**, not by
working through instances of a class nobody wants ([[plan-31-pre-mod-loose-ends#t4-body]]).
{#why-body}

## Measured at `f3a508f` (2026-11-15) {#baseline}

One run of `./scripts/lint-gmd.sh` in a clone, with the dev tree's memory dir in scope:
`1155 files, 1152 GMD docs, 0 errors, 89 warnings [phase 2 cross-doc]`; parity clean.
{#baseline-run}

| Class | Count | Files | Where | Example |
|---|---|---|---|---|
| `unknown-memory-type` | 47 | 47 | the memory dir: every `savestate_*.md` | `metadata.type` `session/recall-state` "not in known memory-type enum" |
| `rel-target-shape` | 28 | 19 | 27 in `workflow/bullshit/` reports, 1 in `docs/gmd-migration-guide.md` | a `rel:` line whose target is a code span (a doc id in backticks) or a bare path, "not a wikilink or URL" |
| `ambiguous-stem` | 9 | 5 | `docs/INDEX.md`, `docs/adr-format.md`, `docs/agent-doc-primer.md`, `docs/architecture/` (2 files) | a link written as the bare stem `adr-template` (6) or `INDEX` (3), which "matches several docs" |
| `unknown-verb` | 5 | 5 | the memory dir | `amended-by` (2), `superseded-by` (3): "not in recommended vocabulary" |
| **total** | **89** | | 37 in the repository, 52 in the memory dir | |
{#baseline-table}

These four are every always-warn class the linter has. Its other two warn-level findings
(`dangling-doc`, `dangling-anchor`) are warnings only when one file is linted alone, and are
errors at the repository gate. {#baseline-all-four}

Three things the count hides:

- **It moves.** Every save-state adds one `unknown-memory-type`. Step 0 of [[#r4]] recounts.
- **It depends on the machine.** Without the memory dir the count is 37.
- **The linter is not this repository's.** `tools/gmd/lint.py` is byte-identical to the
  upstream GMD linter, and `tests/test_bug179_anchor_parity.py` requires it to be a committed
  upstream blob. The user-level memory hook and other projects run the same file. A severity
  changed inside the linter changes for all of them. {#baseline-upstream}

## Requirements {#requirements}

### R1: at this repository's gate, a warning fails {#r1}

- The linter gains one opt-in flag, `--strict`: when any warning is reported the exit is 1, and
  the summary line ends `(strict: warnings fail)`. Without the flag nothing changes.
- `scripts/lint-gmd.sh` passes `--strict`.
- So "made an error" means: the class fails this repository's commit gate. The single-file
  lint that the memory hook runs, and every other project, keep today's behaviour.
{#r1-list}

**Why a flag, and not four severity edits.** The linter's own comment on the memory-type check
says it is warn-only "so it can't regress other projects". A flag keeps that true and still
gives this repository a gate with no warning tier. It also covers a fifth class the day one is
added: nothing has to remember to promote it. {#r1-why}

### R2: the disposition of each class {#r2}

| Class | Disposition | Why it is worth failing | How its instances reach zero | Edits |
|---|---|---|---|---|
| `unknown-memory-type` | **fails the gate** | the type decides which recalls hide a memory (`exclude_mtype`, default `session/*`). A mistyped type changes what is recalled, silently | the enum is wrong, not the files: `session/recall-state` is the type `handoff.py` writes on every save-state. The upstream enum gains it ([[#r3]]) | 1 line upstream; 0 files |
| `unknown-verb` | **fails the gate** | linkage types are an open set, so a mistyped verb (`depnds-on`) becomes its own linkage and the intended edge does not exist. A project's real custom verbs are declared in `.gmd/config.yml` `extra_verbs`, which the linter already honours | the 5 inverse edges, per `plan-31 D42` | 5 lines in 5 memory files; 1 forward edge added |
| `rel-target-shape` | **fails the gate** | a `rel:` line asserts an edge. One whose target is not a link lands nowhere: 28 authored edges are missing from the graph today | by bucket ([[#r4-rel]]) | 28 lines in 19 files |
| `ambiguous-stem` | **fails the gate** | the linter binds a shared stem to whichever doc it read first, so the link's target is arbitrary | each link is rewritten to the full frontmatter id of the doc meant ([[#r4-stem]]) | 9 lines in 5 files |
{#r2-table}

**No class is retired.** Each one, read once, turned out to name a real defect in the graph or
in the linter's own enum, and each reaches zero with a bounded edit: 42 lines in the
repository and memory dir, plus one enum line. Retiring a class would mean removing its check
upstream for every project. The table is the user's to change (`plan-31 D41`); a class the
user retires is removed upstream with its reason recorded there, and its instances are not
touched. {#r2-none-retired}

### R3: the linter's enum names what the product writes {#r3}

`KNOWN_MEMORY_TYPES` gains `session/recall-state`. The enum's comment says it mirrors
`~/.claude/MEMORY-RULES.md`; that file's type list is the user's, and the lead proposes the
matching line with D43. {#r3-body}

### R4: the procedure {#r4}

0. **Recount** at the task's base: the four counts, and the bucket counts of [[#r4-rel]]. The
   summary records what moved since `f3a508f`.
1. **Upstream first.** `--strict`, the enum line and their cases in the upstream gate test are
   committed in a clone of the GMD repository; the lead lands them. The vendored
   `tools/gmd/lint.py` is then replaced by that committed blob, never hand-edited.
2. **Fix the instances** ([[#r4-rel]], [[#r4-stem]], D42).
3. **Turn the flag on** in `scripts/lint-gmd.sh` last, in the commit that leaves the count at
   zero, so no intermediate commit has a red gate.
{#r4-steps}

**`rel-target-shape`, by bucket** (sized at `f3a508f` with a rough resolver; step 0 recounts):

| Bucket | Count | Fix |
|---|---|---|
| the target doc and anchor exist on `master` | 7 | the code span becomes the wikilink it stood for. This is the conversion [[orchestration#planning]] step 7 asks for at merge, which did not happen |
| the doc exists, the anchor does not (`task-bug185-bulk-gmd-ingest` `#r10` and `#open-finish-stop`, `plan-26-memory-organisation` `#user-gates`, `bug_registry` `#bug-212` and `#bug-214`) | 8 | a wikilink to the doc, or to its nearest existing anchor (`#registry` for a registry row); the cited name is kept in the line's attributes |
| the doc is not on `master` (`task-dq1-operational-content-out-of-graph`, `task-25.1b-hook-output-ladder-and-spill`) | 7 | the `rel:` line becomes a prose sentence with the id as a code span. It is not an edge until the doc exists |
| the target is not a GMD doc (`.claude/agents/ch-bsd.md#…` 5, `docs/` 1) | 6 | prose |
{#r4-rel}

From this task on, a citation of a doc that is not on the branch is written in prose, as
[[task-29.1-registry-triage]] does, never on a `rel:` line. {#r4-rel-rule}

**`ambiguous-stem`.** `adr-template` is the stem of `docs/templates/adr-template.md` (id
`refmatrix/adr-template`) and of `workflow/templates/adr-template.md`. `INDEX` is the stem of
`docs/INDEX.md` (id `refmatrix/INDEX`), `workflow/INDEX.md` and `workflow/bullshit/INDEX.md`.
Each of the 9 links is rewritten to the full id of the doc its sentence is about, and the
summary lists the nine with the doc chosen. {#r4-stem}

### R5: the instruction text follows {#r5}

- `CLAUDE.md` `#graph-markdown` and `#before-commit`: "zero errors" becomes "exit 0: zero errors
  and zero warnings".
- [[orchestration#reports]] step 4: "0 errors" becomes "exit 0".
- `.gmd/config.yml`: the `extra_verbs` comment says a custom verb is declared there or fails
  the gate.
{#r5-list}

### Overlap with 31.6 {#overlap-31-6}

31.6 makes lint and ingest resolve a link the same way and "decides how an ambiguous stem is
refused on both sides" ([[plan-31-pre-mod-loose-ends#t6]]). Whichever of the two tasks lands
second starts from the other's linter. If 31.6 lands first and already refuses a shared stem,
this task's `ambiguous-stem` row is done at step 0 and only its nine link fixes remain, if any.
If this task lands first, 31.6 inherits zero instances and a gate that fails on the class. The
nine fixes use the full frontmatter id, which is legal under every outcome 31.6 can choose.
{#overlap-31-6-body}

## Acceptance criteria {#acceptance}

Tests are in `tests/test_gmd_zero_warnings.py` unless named.

- **AC-1 (RED at base: 89 warnings): the real gate reports none.**
  `test_the_repo_gate_reports_zero_warnings` runs the real `scripts/lint-gmd.sh` the way
  `tests/test_gmd_lint_requires_version.py` does (a decoy home holding a copy of this
  checkout's memory dir) and asserts exit 0 and a summary line of `0 errors, 0 warnings`. In a
  checkout with no memory dir the same test runs on the 37 in the repository. {#ac-1}
- **AC-2 (RED at base: exit 0): each class fails the real gate.**
  `test_each_warning_class_fails_the_gate[<class>]`, parametrised over the four: a tmp gate
  tree (the layout `tests/test_bug216_scope_parity.py` builds) holding one doc with one
  instance of the class. `bash scripts/lint-gmd.sh` exits non-zero and prints that class's id.
  {#ac-2}
- **AC-3 (RED): no class without a must-fail case.**
  `test_every_warn_class_has_a_must_fail_fixture` reads out of `tools/gmd/lint.py` every rule
  id the linter emits with a literal warn severity (the four of [[#baseline-all-four]] today)
  and fails if one has no case in AC-2. A warning class added later cannot arrive unproven.
  {#ac-3}
- **AC-4 (RED): the flag.** `test_strict_exits_1_on_a_warning_and_says_so` and
  `test_without_strict_a_warning_still_exits_0` on one fixture doc. {#ac-4}
- **AC-5 (RED): the enum.** `test_a_save_state_memory_type_is_known` (a memory file with
  `metadata.type: session/recall-state` yields no finding) and
  `test_a_mistyped_memory_type_fails_strict` (`feedbak`). {#ac-5}
- **AC-6 (gate): vendored equals upstream.**
  `tests/test_bug179_anchor_parity.py::test_ac8_vendored_tool_is_a_committed_upstream_blob`
  stays green, and the upstream gate test carries a `--strict` case and the new type. {#ac-6}
- **AC-7 (characterization): the memory hook's contract holds.** A single memory file with an
  unknown verb, linted without `--strict`, exits 0 with one warning line, as today. {#ac-7}
- **AC-8 (measurement): the table, before and after.** The implementation summary holds
  [[#baseline-table]] recounted at the task's base and at its tip (four zeros), the bucket
  counts of [[#r4-rel]] with each line's fix, and the nine stem fixes. {#ac-8}

## Mutations {#mutations}

| Id | Mutation | Must fail |
|---|---|---|
| M1 | remove `--strict` from `scripts/lint-gmd.sh` | [[#ac-2]] (all four) |
| M2 | `--strict` returns 0 when there are warnings | [[#ac-4]], [[#ac-2]] |
| M3 | `--strict` exempts one class; run once per class | that class's [[#ac-2]] case and no other |
| M4 | the enum loses `session/recall-state` | [[#ac-5]], [[#ac-1]] |
| M5 | the memory-type check accepts any string | [[#ac-5]] (`feedbak`) |
| M6 | a fifth warn-level rule is added to the linter with no fixture | [[#ac-3]] |
| M7 | one instance fix is reverted (a code-span `rel:` target restored in one report) | [[#ac-1]] |
| M8 | `--strict` becomes the default | [[#ac-7]], [[#ac-4]] |
{#mutations-table}

## Caller census {#census}

| What | Callers at `f3a508f` | Effect |
|---|---|---|
| `tools/gmd/lint.py` through `scripts/lint-gmd.sh` | `CLAUDE.md` `#before-commit`, [[orchestration#reports]], `tests/test_gmd_lint_requires_version.py`, and the four tests that copy the wrapper into a fixture tree (`test_bug179_anchor_parity`, `test_bug216_rev4`, `test_bug216_scope_parity`, `test_bug230_repo_scope_gate`) | strict. A fixture tree that holds a warning today would start failing: step 0 runs those four files against the new wrapper and lists any that do |
| `tools/gmd/lint.py` called directly by tests | `tests/test_gmd_lint_requires_version.py` and the bug-179 tests | unchanged: no `--strict` |
| the upstream copy, `~/claude_tools/gmd/lint.py` | the user-level memory hook (one file, counts `error:` lines); `tools/gmd/lint-memory.sh`; the `gmd-curator` agent template; other projects | unchanged without the flag. The enum line removes a warning for every project whose save-states rmx writes |
| `src/refmatrix/` | comments only (`ingest_gmd.py`, `cli.py`); nothing runs the linter | none |
{#census-table}

## Files {#files}

| File | Change |
|---|---|
| upstream GMD repository: `lint.py`, its gate test | `--strict`; `session/recall-state`. Landed by the lead under D43 |
| `tools/gmd/lint.py` | re-vendored from the committed upstream blob |
| `scripts/lint-gmd.sh` | passes `--strict` |
| `tests/test_gmd_zero_warnings.py` | new |
| 19 files (18 `workflow/bullshit/` reports, `docs/gmd-migration-guide.md`) | 28 `rel:` lines ([[#r4-rel]]) |
| `docs/INDEX.md`, `docs/adr-format.md`, `docs/agent-doc-primer.md`, `docs/architecture/ARCHITECTURE_INDEX.md`, `docs/architecture/README.md` | 9 links ([[#r4-stem]]) |
| 5 memory files, and 1 more for the missing forward edge, outside the repository | the lead's edit under D42 |
| `CLAUDE.md`, `workflow/ORCHESTRATION.md`, `.gmd/config.yml` | [[#r5]] |
| `workflow/implementation_summaries/task-31.4-retire-standing-warnings.md` | new |
{#files-table}

`CLAUDE.md` is an instruction file. Its two edits are part of what the user approves with this
plan; the implementer makes exactly those and quotes the diff in the summary.
{#files-instruction-note}

## Risks {#risks}

1. **A memory written by any session can now turn the repository gate red** (an undeclared
   verb, a mistyped type). That is the intent: the memory dir is already in the gate's scope
   for errors. The memory hook shows the finding at write time, as a warning.
2. **The gate differs by machine.** With no memory dir, 52 of today's instances are out of
   scope, and so are the memory-dir fixes. AC-1 passes there on the repository's 37.
3. **Two repositories.** The upstream commit must exist before the vendored copy can pass
   AC-6. In development the upstream location is a clone (`GMD_UPSTREAM`); the merge to this
   repository's `master` waits for the upstream commit to be on the canonical checkout.
4. **Edits to persisted review reports.** 27 `rel:` lines in ch-bsd reports change. Only the
   `rel:` line is touched; the finding text is not. Seven become prose, so seven edges that
   never existed are no longer written as if they did.
5. **Prose citations of unmerged docs are tracked by nothing.** The code-span `rel:` line was
   not tracked either (seven such lines outlived their merge). Branch-aware lint is on the
   post-mod list ([[plan-of-plans#post-mod]]).
6. **A fixture tree elsewhere in the suite carries a warning** and starts failing under
   `--strict`. Step 0 finds them ([[#census-table]]).
7. **31.6 in flight at the same time** ([[#overlap-31-6]]).
{#risks-list}

## Out of scope {#out-of-scope}

- Making the memory hook strict, or changing it at all (it is user-level).
- Branch-aware lint; any new linter feature beyond the one flag.
- A lint/ingest resolver change: 31.6.
- Rewriting any review report beyond its `rel:` lines.
{#out-of-scope-list}

## Decisions for the user {#decisions}

- **plan-31 D41: the disposition table** ([[#r2-table]]): all four classes fail the gate; none
  is retired. **Recommended as written.** The user may retire any class; that class is then
  removed from the linter upstream, with the reason, and its instances are left alone.
  {#d41}
- **plan-31 D42: the inverse verbs** `amended-by` and `superseded-by` (5 lines on older
  memories, pointing at the memory that replaced them).
  - (a) Drop them. Four already have the forward edge (`amends` / `supersedes`) on the newer
    memory; the fifth (`project_daemon_ingest_hard_death_open`) gets its forward edge added
    there first. **Recommended:** one fact, one edge, in the direction MEMORY-RULES names.
  - (b) Admit both verbs to the vocabulary (`extra_verbs` here, or upstream). The graph then
    holds the same fact under two linkage types.
  {#d42}
- **plan-31 D43: changing the upstream linter.** The flag and the enum line land in the GMD
  repository (public; the user pushes), and one line in `~/.claude/MEMORY-RULES.md` names the
  save-state type.
  - (a) As specified. **Recommended.**
  - (b) No upstream change: the wrapper counts warning lines itself. That cannot clear the 47
    save-state warnings without filtering the linter's output, which is a gate editing its own
    findings.
  {#d43}

## Decisions taken in this spec {#spec-decisions}

- **One flag at the gate, not per-class severities** ([[#r1-why]]).
- **The flag is turned on last** ([[#r4-steps]]).
- **A `rel:` line is an edge or it is prose** ([[#r4-rel-rule]]).
{#spec-decisions-list}
