---
gmd: "0.1"
id: task-14.1-answered-by-telemetry
title: "Task 14.1: every grep telemetry row says WHAT answered it"
tags: [task, telemetry, grep]
metadata:
  node_type: task
  status: pending
  created: 2026-10-05
---

# Task 14.1: `answered_by` + `learn` on every grep telemetry row {#root}

> Plan: [plan-14-grep-learning-measurement](../plan-14-grep-learning-measurement.md)
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-14-grep-learning-measurement]]

## Requirements {#requirements}

Every `kind="grep"` row in `query.log` carries two new fields: {#req-lead}

- **`answered_by`** — one of `index`, `floor`, `dropin`, `stdin`, `none`:
  - `index` — index rows were rendered (`idx` or `idx-replica`).
  - `floor` — the index WAS eligible, returned zero rows, and `rg`/`grep` answered. **This is the
    event learning exists to prevent**, and the only one whose rate learning can move.
  - `dropin` — paths were named, so `_index_may_answer` was false and the tool answered by
    contract. Not a miss. See [[plan-14-grep-learning-measurement#eligibility]].
  - `stdin` — the filter path (`_grep_stdin`): a grep reading a pipe is byte-exact and consults
    nothing.
  - `none` — eligible, zero index rows, `--no-fallback`, so nothing answered (`SystemExit 1`).
- **`learn`** — the EFFECTIVE learning state for that invocation (the `--learn/--no-learn` flag AND
  the toggle from task 14.2), so a replayed log says which arm wrote the row without external
  bookkeeping.

Readers must keep working on rows written before these fields existed: `summarize` and any
`rmx telemetry` surface default a missing `answered_by` to `unknown` and MUST NOT count it as
`floor`. The historical rows cannot be re-scored
([[plan-14-grep-learning-measurement#no-backfill]]) and a reader that quietly folds them into a
bucket would manufacture a number. {#req-readers}

## Acceptance criteria {#acceptance}

1. `rmx grep PATTERN` against a store whose index holds the pattern logs `answered_by: "index"`.
2. The same call against a store that does NOT hold it logs `answered_by: "floor"`.
3. `rmx grep PATTERN file.py` logs `answered_by: "dropin"` **even when the index holds the
   pattern** — eligibility, not outcome, decides this one.
4. `cmd | rmx grep PATTERN` logs `answered_by: "stdin"`.
5. `rmx grep PATTERN --no-fallback` with an empty index logs `answered_by: "none"` and still
   exits 1.
6. A row written by the replica path and a row written by the daemon path agree on the field for
   the same scenario — the value is decided in ONE place, not per path
   ([[project_grep_output_shape_one_resolver]]).
7. `telemetry.summarize` over a log containing pre-field rows reports them as `unknown`.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/telemetry.py` | document + accept `answered_by` / `learn` on the record; `summarize` tolerates their absence |
| `src/refmatrix/cli.py` | set the field at the four render/exit points in `_grep_run`, `_grep_run_direct`, `_grep_rg_fallback`, `_grep_stdin` |

## Implementation notes {#implementation-notes}

The value is assigned where the ANSWER is produced, and `_grep_rg_fallback` is shared by both the
replica and daemon paths — so the floor-vs-dropin distinction belongs to a single helper that takes
`paths` and returns the label, called by the fallback, rather than two call sites each setting a
string. Four defects in this file came from per-path decisions
([[project_grep_surface_defect_family]]); this field must not become the fifth. {#one-place}

`_tlog` is the `log_query` context object already threaded through every one of these functions, so
no signature grows a new parameter. {#tlog}

## Test strategy {#test-strategy}

`tests/test_grep_answered_by.py`, real stores under `tmp_path`, no monkeypatching of the function
under test ([[feedback_red_test_must_fail_at_head]] — run the file at HEAD first and record which
assertions fail). One case per acceptance criterion; the `dropin` case must assert against an index
that DOES hold the pattern, because a test using an empty index passes against a two-valued
implementation and proves nothing. {#tests}
