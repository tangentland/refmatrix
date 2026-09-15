---
gmd: "0.1"
id: task-6.3-plan-6-deferrals-docs-benchmark
title: "Task 6.3: Benchmark artifact"
tags: [task, plan-6]
metadata:
  node_type: task
  status: complete
  plan: plan-6-deferrals-docs-benchmark
---

# Task 6.3: Benchmark artifact {#root}

> Plan: [[plan-6-deferrals-docs-benchmark]]
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-6-deferrals-docs-benchmark]]

## Requirements {#requirements}

- The number in README exists in a committed `metrics.json`; if the full run is not completed, README says which run the number comes from.

## Files to Create / Modify {#files}

- `eval/production/csn_code.py --out eval/production/results/csn_python/metrics.json` (+ `REPORT.md` regeneration); README + docs/PERFORMANCE.md cite the committed path.

## Test Strategy (RED first) {#test-strategy}

tests/test_eval_artifact_cited.py: README's cited path exists and its MRR matches the README figure.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-6.3-plan-6-deferrals-docs-benchmark.md`.
- Committed on branch `task-6.3-plan-6-deferrals-docs-benchmark`; merged `--no-ff` to `master`.
