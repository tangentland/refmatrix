---
gmd: "0.1"
id: task-8.4-plan-8-derived-coverage-notes
title: "Task 8.4: The `unanswered` detector, behind a pre-registered confound check"
tags: [task, plan-8]
metadata:
  node_type: task
  status: pending
  plan: plan-8-derived-coverage-notes
---

# Task 8.4: The `unanswered` detector, behind a pre-registered confound check {#root}

> Plan: [[plan-8-derived-coverage-notes]]
> Status: Pending
> Depends on: 8.1

rel: part-of -> [[plan-8-derived-coverage-notes]]

## Requirements {#requirements}

- `brief/unanswered` groups queries that fell to the grep backstop or returned an empty/shape-0 bundle, by term, from `query.log` / `cli.log` telemetry.
- **Gate (Q3).** This detector does NOT ship until a written confound check passes, recorded in the implementation summary BEFORE the detector is enabled. [[project_helix_log_confounded]] is the precedent and the exact shape of the failure: a log written by a path that suppresses its own signal, read afterwards as if it measured demand. The check must answer, with evidence from the logs themselves:
  1. Does the surface that writes these lines also suppress the condition it records (does a backstop hit prevent the next one being logged)?
  2. What fraction of lines come from hook-driven calls vs. user-driven ones? A log dominated by the machine's own polling measures the machine.
  3. Is the volume sufficient to distinguish a real term from a one-off typo at the chosen threshold?
- Criteria and thresholds are written down BEFORE the numbers are read ([[project_helix_phase2_decision_criterion]]). If the check fails, the detector is NOT shipped and the failure is recorded — a negative result is the deliverable.
- `RMX_INVOCATION_SOURCE` already distinguishes call origins; question 2 is answerable from it.

## Files to Create / Modify {#files}

- modify `src/refmatrix/brief.py`
- create `workflow/review-output/brief-unanswered-confound.md` (the pre-registered check + its result)

## Test Strategy (RED first) {#test-strategy}

`tests/test_brief_unanswered.py`:
- the detector groups by term and attaches the log lines as evidence
- a term whose only hits are hook-sourced (`RMX_INVOCATION_SOURCE=hook`) is excluded at default settings
- a synthetic self-suppressing log fixture is DETECTED as such by the confound check and the detector refuses to emit
- thresholds are parameters, asserted by driving the same fixture to two different outcomes

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-8.4-plan-8-derived-coverage-notes.md`.
- Committed on branch `task-8.4-plan-8-derived-coverage-notes`; merged `--no-ff` to `master`.
