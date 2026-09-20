---
gmd: "0.1"
id: task-13.5-gate-1-measurement
title: "Task 13.5: Gate 1 — does the built sweep beat the control, and can the win be attributed?"
tags: [task, plan-13, measurement, eval, harness]
metadata:
  node_type: task
  status: pending
  plan: plan-13-cross-partition-sweep
  gate: PASS/PARTIAL/FAIL
---

# Task 13.5: Gate 1 measurement {#root}

> Plan: [[plan-13-cross-partition-sweep]]
> Status: Pending
> Gate: **PASS / PARTIAL / FAIL for shipping the sweep**
> Depends on: [[task-13.1-sweep-verb]], [[task-13.2-canonical-dedupe]], [[task-13.3-surfaces-and-parity]]

rel: part-of -> [[plan-13-cross-partition-sweep]]
rel: depends-on -> [[task-13.1-sweep-verb]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_green_tests_are_not_a_working_command]]

## Requirements {#requirements}

- Same store, same question set, same metric definitions as [[task-13.0-two-partition-kill-shot]].
  A Gate 1 number that is not comparable to Gate 0's control is not a gate.
- **The harness must be changed, and that work is in THIS task's scope** (audit #s-2):
  `eval/memaware/retrieval_eval.py:75-111` (`_ids()`) keeps the first id-looking string per record
  and returns a flat `list[str]`; every `METHODS` entry is typed to that contract and `score()`
  consumes `dict[str, list[str]]`. A `leg` field on the sweep's output is walked past and dropped.
  Either the method contract becomes `list[tuple[id, leg]]` or a sidecar leg map is written — and
  `score()` changes with it.
- **Both attribution arms are mandatory**, because without them a PASS is unattributable:
  - `--no-rerank`: the memory leg inherits the cross-encoder that `scan-prompt` and `context` do
    NOT run (`eval/memaware/REPORT.md:202-203`), so an unarmed gain may be the reranker, not the
    union.
  - arm R (RRF over ranks) vs arm S (score-summed, min-max normalised per leg): the repo's recorded
    negative says RRF loses to score summation on code retrieval
    ([[plan-13-cross-partition-sweep#principle-rank]]).
- **Run each surface once against real data before believing the suite**
  ([[feedback_green_tests_are_not_a_working_command]]): every flag the report uses is invoked once
  through the real CLI, and the invocation is recorded in the report.
- Cost is measured on the path that ships: per-leg elapsed, sweep total, and the p95 on the hook
  path. The legs SERIALIZE, so the total is the sum — report it, do not model it.

## Acceptance criteria {#acceptance}

- **PASS** — sweep hit@20 ≥ (best single condition from 13.0) + 0.05 absolute, MRR@20 not below
  that condition's, AND the `--no-rerank` arm still shows a positive delta (else the win is the
  reranker and is recorded as such).
- **PARTIAL** — positive but < 0.05: ship behind a flag, no `scan-prompt` adoption.
- **FAIL** — no gain: close the plan, record the negative in `docs/PERFORMANCE.md#negatives`.
- The per-leg contribution table is in the report for every outcome. A "win" with 95% of winning
  candidates from one leg is reported as that leg plus latency.
- The winning fusion arm is named, and if arm S wins,
  [[plan-13-cross-partition-sweep#principle-rank]] is amended rather than quietly ignored.

## Files {#files}

- modify `eval/memaware/retrieval_eval.py` (leg-aware method contract + `score()`)
- create `eval/partition_sweep/run_gate1.py`
- modify `eval/partition_sweep/REPORT.md`
- modify `docs/PERFORMANCE.md` (result, whichever way it reads)
- modify `tests/test_partition_sweep_harness.py` (leg-aware scoring)

## Test strategy (RED first) {#test-strategy}

1. `test_score_consumes_leg_annotated_results` — the new contract; a leg-tagged list scores
   identically to the flat list it came from (the change must not move the metric).
2. `test_per_leg_contribution_counts_the_winning_candidate_only` — on a fixture where two legs both
   returned the gold at different ranks, exactly one leg is credited, and it is the one that
   produced the surviving row after dedupe.
3. `test_a_dropped_leg_is_visible_in_the_report` — a deadline-dropped leg appears with
   `dropped: true`, and is not silently scored as "contributed nothing".
4. `test_the_two_arms_are_scored_separately` — arm R and arm S produce two rows in the report, not
   one.
5. `test_report_records_the_store_version_and_question_set_hash` — the number describes a tree
   (`bsd-plan3-verbs-parity-r2-209270d#s-4`: a full-suite log that does not describe its commit).

**Mutations:** credit every leg that returned the gold (kills 2); score a dropped leg as empty
(kills 3); run one arm and copy its number into both rows (kills 4).
