---
gmd: "0.1"
id: task-7.3-summary
title: "Task 7.3 summary: LongMemEval Layer A scoring (written retroactively)"
tags: [implementation-summary, plan-7]
metadata:
  node_type: summary
  task: task-7.3-plan-7-longmemeval
  created: 2026-10-19
  retroactive: true
---

# Task 7.3 summary {#root}

rel: realizes -> [[task-7.3-plan-7-longmemeval]]
rel: part-of -> [[plan-7-longmemeval]]
rel: amends -> [[task-7.2-summary]]
rel: derives-from -> [[bsd-plan7-10-r1-399d0a3]]
rel: derives-from -> [[bsd-plan7-10-r2-a249877]]
rel: derives-from -> [[bsd-plan7-10-r3-4f451c5]]
rel: derives-from -> [[bsd-plan8-9-10-r5-e0b7df6#plan-7-notes]]
rel: depends-on -> [[plan-review-2026-10-14#t11-folded-waves]]

Written retroactively on 2026-10-19 in the W1-d bookkeeping sweep. The task spec's `#done` names
this file by exact path and it did not exist. The build itself was already written up, together
with task 7.2, in [[task-7.2-summary#scoring]] (committed in `71ee227`). This file adds the commit
trail, the ch-bsd rounds that changed `run.py` after it shipped, and what is still open. It does
not repeat the content of the 7.2 summary.

## What shipped {#shipped}

- **`5d5e9ba`** (2026-09-15), `feat(eval): LongMemEval Layer A scoring — two haystack modes,
  per-type slices`. Creates `eval/production/longmemeval/run.py` (372 lines) and
  `tests/test_longmemeval_scoring.py` (177 lines). Reachable from `origin/master`.
- Layer A only: Recall@k, MRR and hit@k with no API calls. Results are broken out per question type,
  for abstention, and overall. The `union` and `restricted` modes are both emitted on every run.
  `restricted` reports its own recall ceiling, and a test asserts it never scores above that
  ceiling. Every recall method passes an explicit `--rerank` or `--no-rerank`, and the MRR column is
  labelled `mrr@N`.
- From the commit message: 17 tests, pure functions, no store; "Six mutants all killed".

## Changes after ch-bsd {#post-bsd}

`run.py` was changed by three remediation commits, all on `origin/master`:

| Finding | Commit | Outcome |
|---|---|---|
| r1 `#b-6`: `--depth` was inert for `scan` / `scan-nocontent` | `9cb6c25` | depth was translated to `--max-tokens`. r2 `#b-6-r2` showed this was inert on `--format json` |
| r2 `#b-6-r2` | `4f451c5` | closed **as a label**. `scan` methods are `DEPTH_UNCONTROLLED`, `_meta.depth` is `null`, and the table header prints `depth=UNCONTROLLED`. r3 accepted this ("CLOSED as a label") |
| r1 `#s-13`: a dead surface scored 0 and left no trace in the artifact | `f3c23b1` | `_meta` carries `n_failed` and `failed_ids`, and `print_table` renders `FAILED=N`. Closed in r2 |
| r3 `#s-2-r3`: REPORT.md said b-6 "was fixed" | `6b6a610` | tense corrected at four sites. Closed in r4 |

## Definition-of-done record {#done-record}

- RED / GREEN runs: none recorded in a committed file. The 7.2 summary does not name a log for
  7.3, and `workflow/review-output/` is gitignored.
- Mutation check: the commit message says six mutants were killed. Which six is not recorded, and
  neither is whether the spec's two named mutations (remove the haystack filter; hard-code the
  ceiling to 1.0) were among them.
- Branch: no `task-7.3-plan-7-longmemeval` branch exists in this clone. Not recorded whether one
  ever existed.

## Still open {#open}

- **Dense and fused rows were never re-run.** The r5 ledger ([[bsd-plan8-9-10-r5-e0b7df6#plan-7-notes]])
  says bug-030 was fixed 2026-09-16 (`464485d`, an ancestor of master), so the named blocker is
  gone. It also says nothing verifies that the embed run now completes on the LongMemEval store.
  This harness's `recall*` methods have therefore produced no committed result. Owner: **W2-c**
  ([[plan-review-2026-10-14#t11-folded-waves]]).
- **The `scan` depth knob.** `4f451c5` labels the surface as uncontrolled instead of controlling
  it ("Finding the real knob is a measurement, not a constant"). The `t11-folded-waves` list does
  not name this item. W2-c ("REPORT.md completed") is the closest host. Not verified as assigned.
- **Deferrals (W4-a):** Layer B (`deferral_registry.md` row 40), the CLI candidate-set prefilter
  whose absence makes `restricted` an approximation with a reported ceiling (row 42),
  `longmemeval_m`, and a settled-store latency re-measure.
