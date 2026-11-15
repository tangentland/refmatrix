---
gmd: "0.1"
id: task-30.5-load-bitmap-row-read
title: "Task 30.5: load_bitmap reads the row, statelessly — a seek and a bounded read in place of a 65,536-container mask and a full cardinality count; no derived state, no invalidation"
tags: [task, plan-30, bitmap, roaring, load-bitmap, store, performance, stateless]
metadata:
  node_type: task
  status: pending
  plan: plan-30-materialisation
  created: 2026-11-14
  updated: 2026-11-15
---

# Task 30.5: `load_bitmap` reads the row, statelessly {#root}

> Plan: [[plan-30-materialisation]] ([[plan-30-materialisation#t5]])
> Status: Pending
> Depends on: plan-29 released (`Store.load_bitmap` is then in `store_fragments.py`,
> [[task-29.5-split-giant-modules#map-store]]). No plan-30 task.
> Runs beside 30.0, before or after the adjacency tasks. Ships alone, as release A. It edits no
> derive-pass file.
> User gates: none.
> Revised 2026-11-15 after ch-bsd r1 and ruling L116 ([[#rev-note-2]]).

rel: part-of -> [[plan-30-materialisation]]
rel: implements -> [[plan-30-materialisation#t5]]
rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[tdd-governance]]
rel: derives-from -> [[perf-bitmap-materialisation-2026-11-14#q3]]
rel: evidence-for -> [[plan-30-materialisation#deferred]]
rel: reinforces -> [[feedback_check_the_sibling_condition]]
rel: reinforces -> [[feedback_measure_the_outcome_not_the_wall]]
rel: reinforces -> [[feedback_causal_story_before_evidence]]

## Why {#why}

`Store.load_bitmap(linkage, concept_id)` returns the entity ids set under one (linkage,
concept) row of a fragment. It does it in three steps: `len(frag) == 0`; a mask
`BitMap64().add_range(c << 32, (c + 1) << 32)` ANDed with the fragment; a loop that strips the
high bits. On the `mentions` fragment a call takes 6.5 ms for a row of 317 entities. {#why-body}

## Measured {#measured}

On a read-only copy of the live read snapshot (partition `refmatrix`; `mentions` has 834,472
bits in 239,239 containers), clone at `6676f39`, two runs minutes apart at 1-minute loads of
5.1 and 12.0. Script and logs: `workflow/measurements/plan-30-load-bitmap-2026-11-14/`.

| Step | Run 1 median | Run 2 median |
|---|---|---|
| `load_bitmap` today, `mentions` row of 317 | 6514 µs | 6723 µs |
| `len(frag)` alone | 2903 µs | 2998 µs |
| the range mask, built and freed | 3346 µs | 3709 µs |
| `bool(frag)` | 0.08 µs | 0.08 µs |
| **seek and bounded read: no mask, no `len`** | **30.7 µs** | **29.7 µs** |
| the largest row (3,900 entities): today / new | 6660 µs / 304 µs | 6706 µs / 304 µs |
| 20 concepts × 34 linkages: today / new | 2224 ms / 2.56 ms | 2233 ms / 2.61 ms |
| rows identical to a full decode | 123,448 of 123,448 | 123,448 of 123,448 |
| sampled rows identical to today's `load_bitmap` | 407 of 407 | 407 of 407 |
{#measured-table}

- **`len()` of a `BitMap64` counts every container.** It is 2.9 ms on this fragment, on every
  call, to answer "is it empty".
- **The mask covers 2^32 values as 65,536 run containers**, built and freed per call
  ([[perf-bitmap-materialisation-2026-11-14#q3]]).
- **The report's "iterator: 2.80 ms" was the `len()` guard**, which its prototype kept
  (`q_loadbitmap.py::lb_iter`). On synthetic fragments of up to 642,133 containers the same
  read without the guard took 20-45 µs wherever the row sat (`synthetic_iter.out`).
- **A sibling.** `Store.link_many` calls `len(frag)` twice to compute a count it already holds
  as `len(newly_added)`. Its comment calls it hot in ingest; at `6676f39` its one caller in
  `src/` is the `import` command, so the cost is real per call and rare in practice.
{#measured-notes}

## Requirements {#requirements}

### R0: baseline {#r0}

1. Re-resolve symbols at the base sha. Re-run [[#census]].
2. Re-run `row_read.py` on a fresh throwaway copy of a read snapshot (the lead supplies it), and
   record the table above again.
3. Check that the deploy venv's pyroaring is the version measured (1.1.0 in `.venv-eval`) and
   that `BitMap64.iter_equal_or_larger` behaves the same there. A different version is measured
   before the task proceeds.
4. **Every `len()` of a fragment in `src/`**, by a census family on 29.3's kit. At `6676f39`:
   `Store.load_bitmap`; `Store.link_many` (two); `Store._flush_current_binding`;
   `Store._flush_fragments_duckdb`; `Store._migrate_legacy_bitmaps_if_needed`;
   `Store._write_all_fragment_rows` (two). The summary classifies each as per-call on a read
   path, per-call on a write path, or cold.
5. Confirm `link_many`'s callers (one at `6676f39`: the `import` command). If ingest reaches
   it at the base sha, count its calls in one production ingest of the fixture corpus.

### R1: the row read {#r1}

`Store.load_bitmap(linkage, concept_id) -> BitMap`: seek the fragment to
`concept_id << _CONCEPT_SHIFT` with `iter_equal_or_larger`, read values while they are below
the next row's start, and return a new `BitMap` of their low 32 bits.

- No range mask. No `len()` of the fragment. An empty fragment or an absent row yields an empty
  `BitMap` with no special case.
- **No state.** Nothing is kept between calls: no decoded array, no row cache, no attribute on
  the store. The value returned is read from the fragment object as it is at the call.
- The return is a new object the caller owns, as today.
- The signature and the name do not change. No caller is edited.

### R2: the siblings {#r2}

- `Store.link_many` returns `len(newly_added)`, the list it already builds, and calls `len()`
  on the fragment nowhere.
- The two flush functions test emptiness by truth (`not frag`), not by `len(frag) == 0`.
- The cold sites of R0 item 4 are left, and listed.

### R3: the old read becomes the oracle {#r3}

The base sha's `load_bitmap` body is copied verbatim to `tests/oracles/load_bitmap_mask.py` by
`ch-test-engineer`, in the RED commit, with the sha in its header. {#r3-body}

### R4: docs {#r4}

`docs/PERFORMANCE.md`, in its roaring-bitmap section: how a row is read, and the measured
numbers with their date. `Store.load_bitmap`'s docstring says why there is no mask and no
`len()`, with this task's numbers. {#r4-body}

### R5: the closing measurement {#r5}

On the R0 copy, after the change, with the report's `q3_presplit.py` method (a fresh
`QueryEngine` per call, results asserted identical to the base's): `neighbors` at depth 1 and 2
for the report's seed classes (in-degree 1; 4-33; 62-243; 496-2429), median and p90 with n of 5
or more; `topn` for a bitmap of 1 and of about 1,800, n of 3 or more; `match_concepts` on the
report's 40-prompt method, in memory, outputs compared. Two runs, minutes apart, loads printed.
The numbers go into the summary and into the deferral registry row of
[[plan-30-materialisation#deferred]], whose trigger they evaluate. {#r5-body}

## Acceptance criteria {#acceptance}

Each AC says what it is at the base sha: **RED** (the test fails there, and the red run is
recorded), **characterization** (green there, and proven able to fail by the mutations named
in [[#mutations]]), **gate**, or **measurement**. This is a performance fix to a method whose
results are already right, so the RED is in what the call does (AC-2, AC-3), not in what it
returns. {#acceptance-labels}

- **AC-1 (characterization, all four bullets): every row is identical, including a row just
  written.** The base method is correct and reads the live fragment, so each bullet passes at
  the base. Mutations 1-4 fail the boundary bullets; mutations 7 and 8, the two stateful
  variants, fail read-your-writes. On the fixture store
  ([[task-30.1-adjacency-mapping-adapter#fixture]]):
  - for every (linkage, concept) row of every fragment, enumerated by a full decode,
    `load_bitmap` equals the decode's row and equals the oracle's result;
  - for absent rows (concept 0; one above the largest; a concept present under another linkage
    only; an empty fragment; a linkage with no fragment) it returns an empty `BitMap`, as the
    oracle does;
  - **read-your-writes, with no flush between:** after `link`, `unlink`, `link_many`,
    `save_bitmap` and `purge_entity`, each followed at once by `load_bitmap` on the same store,
    the result equals a fresh full decode of the live fragment;
  - a row holding entity id 0, with the next concept's row also holding entity id 0, returns
    exactly its own.
  Recorded as rows equal of rows compared. Test: `tests/test_load_bitmap_row_read.py::test_rows_identical`. {#ac-1}
- **AC-2 (RED): no mask is built.** With the module's `BitMap64` name bound to a counting wrapper, a
  `load_bitmap` call constructs 0 `BitMap64` objects. RED at the base: 1 per call. Test:
  `test_no_bitmap64_is_constructed_per_call`. {#ac-2}
- **AC-3 (RED): no `len()` of a fragment on a per-call path.** R0 item 4's family passes with exactly
  the cold sites allow-listed, each with its reason; a planted `len(frag)` in a copy of
  `load_bitmap` fails it by name. RED at the base: five calls in four per-call functions. {#ac-3}
- **AC-4 (characterization): `link_many`'s count is unchanged.** For a batch of all-new ids, all-existing ids, a
  mix, a batch with a repeated id, and an empty batch, the return value and the store's state
  equal the base's. Mutation 9 fails it. Test: `test_link_many_counts`. {#ac-4}
- **AC-5 (characterization): callers' results are identical.** On the fixture, equal to the base sha's output:
  `neighbors` at depth 1 and 2 for seeds of in-degree 1, about 10, about 100 and the largest;
  `topn`; `co_occurrence`; PQL row terms; the context bundle for 10 anchors, byte-equal;
  `match_concepts` for 30.2's synthetic prompts. Recorded as cases equal of cases run.
  Mutations 1-4 fail it. Test: `test_callers_unchanged`. {#ac-5}
- **AC-6 (measurement): at production scale, twice.** R0 item 2's script after the change, two runs
  minutes apart with loads printed: rows identical N of N; the `mentions` row's median at most
  one twentieth of the base's median from the same session (the plan's probe: one two-hundredth);
  the 20 × 34 mix likewise. {#ac-6}
- **AC-7 (measurement): the closing measurement is recorded** ([[#r5]]), and the deferral row carries it. {#ac-7}
- **AC-8 (gate): nothing derived moved.** `scripts/derive-digest.py check` exits 0. The suite is equal
  by E line to the base run. No file named in `_DERIVE_PASS_MODULES` is edited. {#ac-8}

## Mutations that must fail {#mutations}

Each alone, seen RED on the named AC, reverted in its own command.

1. the read stops at `v > end`, not `v >= end` → AC-1 (the entity-0 row).
2. the seek starts at `(concept_id << shift) + 1` → AC-1 (the entity-0 row).
3. the read has no upper bound → AC-1.
4. the low bits are not masked → AC-1.
5. the `len(frag) == 0` guard returns → AC-3.
6. the mask returns → AC-2.
7. rows are memoised in a dict on the store → AC-1 (read-your-writes).
8. a decoded array per linkage is kept and searched → AC-1 (read-your-writes).
9. `link_many` returns `len(ids)` → AC-4 (existing and repeated ids).
10. a flush skips a fragment whose truth it reads inverted → AC-8 (the fragment suites).
{#mutations-list}

## Test strategy {#test-strategy}

- **RED first, by `ch-test-engineer`.** The tests named in [[#acceptance]] are written before
  any `src/` edit and run at the base sha; the red run is kept
  (`workflow/review-output/task-30.5/red.log`) with each test's E line. A test this spec marks
  characterization is recorded green at the base and says so. A test expected RED that passes
  at the base is a finding about the test.
- **GREEN by `ch-implementer`,** who writes no test.
- **Mutation gate.** The fix is committed before the first mutation. Each mutation of
  [[#mutations]] is applied alone, must FAIL its named test (a hang is not a failure), and is
  reverted in its own command; `__pycache__` is cleared after the batch; the fix is shown
  present after the last revert.
- **Test families are derived from imports** of the touched modules (29.4), and the merged dev
  tree runs them before the merge commit.
- **The oracle is test code** ([[#r3]]).
- **Mocks.** AC-2's counting `BitMap64` wrapper, bound to the module's name; classified in
  `workflow/test_mock_registry.md`. `load_bitmap` itself is never patched.
- **Measurements** ([[#ac-6]], [[#r5]]) are two runs minutes apart with loads printed.
- **All output to files** under `workflow/review-output/task-30.5/`.
{#test-strategy-list}

## Caller census {#census}

At `6676f39`. R0 re-runs it. No caller is edited; every one is covered by AC-5 or named here.

| Changed | Callers in `src/` | Tests that name it |
|---|---|---|
| `Store.load_bitmap` | `scan.py::_concept_signal` (per prompt); `assoc.py` (two); `context.py` (three bundle sites); `query.py::QueryEngine` (six: row terms, `neighbors`, `topn`, `co_occurrence`); `recall.py` (one); the export command in `cli/` (one) | `tests/test_duckdb_fragments.py`, `tests/test_duckdb_migrate.py`, `tests/test_flag_crud.py`, `tests/test_partitions.py`, `tests/test_refmatrix.py`, `tests/test_sync_and_extras.py`, `tests/test_verb_alias.py`, `tests/test_v2_features.py`, `tests/test_bug216_remedy_r2.py`, `tests/test_bug216_remedy_r3.py` |
| `Store.link_many` | the `import` command in `cli/` (one site) | R0 lists |
| `Store._flush_current_binding`, `Store._flush_fragments_duckdb` | `Store.flush_fragments` | the fragment and flush suites |
{#census-table}

## Invalidation {#invalidation}

There is nothing to invalidate, and that is the design. The fragment is the only copy; each call
reads it. A write is visible to the next read on the same store with no boundary in between
(AC-1). {#invalidation-body}

## Files {#files}

| File | Change |
|---|---|
| `src/refmatrix/store_fragments.py` | [[#r1]]; the flush functions of [[#r2]] |
| the module that holds `Store.link_many` after 29.5 (`store_links.py` in 29.5's map) | [[#r2]] |
| `tests/test_load_bitmap_row_read.py` | new |
| `tests/oracles/load_bitmap_mask.py` | new, in the RED commit |
| `tests/census/` | the `len()`-of-a-fragment family |
| `workflow/measurements/plan-30-load-bitmap-2026-11-14/` | R0's and R5's logs beside the plan's |
| `workflow/deferral_registry.md` | R5's numbers on the pre-split rows item |
| `docs/PERFORMANCE.md` | [[#r4]] |
| `workflow/test_mock_registry.md` | the counting `BitMap64` wrapper |
| `workflow/implementation_summaries/task-30.5-load-bitmap-row-read.md` | new |
{#files-table}

## Release {#release}

Release A. `store_fragments.py` and `store_links.py` are in no pass's module set, so no stamp
flips; the printed union `code_hash` changes, as it does with any store edit, and the deploy
note says so ([[task-29.5-split-giant-modules#r5]]). No store event. {#release-body}

## Risks {#risks}

- **A boundary error returns a neighbour row's bit.** AC-1 compares all rows and plants entity
  id 0 on both sides of a boundary; mutations 1-3.
- **Large rows cost time in proportion to their size** (304 µs for 3,900 entities). That is 22
  times faster than today for the largest row measured, and R5 reports the end-to-end effect.
- **A pyroaring upgrade changes the iterator.** R0 item 3 pins what was measured; AC-1 would
  fail on a behavioural change.
- **A read while another thread writes the fragment.** Not changed by this task: today's AND
  reads the same object. Reads run on the mirror or a read store with fragments of their own,
  and the writer's fragments are read under the store lock.
{#risks-list}

## Out of scope {#out-of-scope}

- Pre-split rows and filter bitmaps in daemon memory
  ([[plan-30-materialisation#deferred]]). R5 measures what is left for them to win.
- `QueryEngine`'s per-call SQL (`noise_concept_ids`, `_universe`), which the report measured at
  8.5 ms and 49.6 ms.
- Transposed fragments ([[plan-30-materialisation#not-transposed]]).
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **plan-30 D7: the stateless read, not a decoded array per linkage.** The report offered a
  sorted array per linkage with `searchsorted`: 24 µs a row, for 80 ms and 9.4 MB per process.
  Measured without the stray `len()`, the stateless read is 30 µs. The array's remaining
  advantage is 6 µs. Its cost is a second copy of a structure that is mutated in place at seven
  sites (at `6676f39`) and handed out mutable by `Store._load_fragment`: every one of those would have to drop
  it, on every binding, and a miss returns wrong rows without an error. The stateless read has
  no copy to go stale.
- **The siblings are fixed in the same task.** One cause (a cardinality count used as a truth
  test or a difference), found at the same time, each a one-line change with an equality test.
  Leaving them would leave the same trap for the next reader of `load_bitmap`'s history.
- **No caller is edited.** The method keeps its contract.
{#decisions-list}

## Revision note 2 (2026-11-15, ch-bsd r1 and ruling L116) {#rev-note-2}

| Finding ([[bsd-plan30-spec-r1]]) | Answered in |
|---|---|
| M1: AC-1's read-your-writes and entity-0 bullets pass at the base and were not marked | [[#acceptance-labels]]: every AC is labelled. All of AC-1 is characterization, with the mutations that fail each bullet named; the RED is AC-2 and AC-3 |
{#rev-note-2-table}
