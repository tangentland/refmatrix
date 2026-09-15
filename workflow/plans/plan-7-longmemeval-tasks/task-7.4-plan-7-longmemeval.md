---
gmd: "0.1"
id: task-7.4-plan-7-longmemeval
title: "Task 7.4: REPORT.md, committed results artifact, README citation"
tags: [task, plan-7]
metadata:
  node_type: task
  status: pending
  plan: plan-7-longmemeval
---

# Task 7.4: REPORT.md, committed results artifact, README citation {#root}

> Plan: [[plan-7-longmemeval]]
> Status: Pending
> Depends on: 7.2, 7.3

rel: part-of -> [[plan-7-longmemeval]]

## Requirements {#requirements}

- `REPORT.md` records, for every number: the harness command, the corpus size, the scoring mode, the rmx version, and the date. A figure missing any of those does not ship ([[project_csn_production_harness]] set this bar; plan 6 task 6.3 enforced it for CSN).
- The published `mcp-memory-service` figures (80.4% R@5, 89.1% MRR, multi-session 70.7%, temporal-reasoning 72.0%) are quoted as an EXTERNAL reference row, clearly attributed, with an explicit note that their harness, embedding model, and chunking are not ours — the row is a landmark, not a controlled comparison.
- Results JSON committed under `eval/production/longmemeval/results/`; README and `docs/PERFORMANCE.md` cite the committed path, never a remembered number.

## Files to Create / Modify {#files}

- create `eval/production/longmemeval/REPORT.md`, `eval/production/longmemeval/results/`
- modify `README.md`, `docs/PERFORMANCE.md`, `docs/INDEX.md`
- modify `workflow/deferral_registry.md` (Layer B; `longmemeval_m`)

## Test Strategy (RED first) {#test-strategy}

`tests/test_eval_artifact_cited.py` extended: every LongMemEval figure cited in README/PERFORMANCE resolves to a committed results file whose value matches, and the citation names a scoring mode.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-7.4-plan-7-longmemeval.md`.
- Committed on branch `task-7.4-plan-7-longmemeval`; merged `--no-ff` to `master`.
