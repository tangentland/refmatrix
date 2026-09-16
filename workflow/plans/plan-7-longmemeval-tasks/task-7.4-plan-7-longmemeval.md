---
gmd: "0.1"
id: task-7.4-plan-7-longmemeval
title: "Task 7.4: REPORT.md, committed results artifact, README citation"
tags: [task, plan-7]
metadata:
  node_type: task
  status: complete (symbolic only; dense blocked on bug-030)
  plan: plan-7-longmemeval
---

# Task 7.4: REPORT.md, committed results artifact, README citation {#root}

> Plan: [[plan-7-longmemeval]]
> Status: Complete — symbolic surfaces reported; dense rows blocked on bug-030
> Depends on: 7.2, 7.3

rel: part-of -> [[plan-7-longmemeval]]

## Requirements {#requirements}

- `REPORT.md` records, for every number: the harness command, the corpus size, the scoring mode, the rmx version, and the date. A figure missing any of those does not ship ([[project_csn_production_harness]] set this bar; plan 6 task 6.3 enforced it for CSN).
- Two published systems are quoted as EXTERNAL reference rows, clearly attributed, with an explicit note that their harness, embedding model, and chunking are not ours. These are landmarks, NOT controlled comparisons:
  - **mcp-memory-service** (doobidoo) — 80.4% R@5, 89.1% MRR; per-type gaps multi-session 70.7%, temporal-reasoning 72.0%.
  - **agentmemory** (rohitg00, 28.5k stars) — **95.2% R@5 on LongMemEval-S, 500 questions**; BM25 + vector + graph fused by RRF (k=60), 14ms p50.
- Neither reference states its haystack scoping. Both figures are almost certainly per-question (gold among ~50 sessions), which is our `restricted` mode — so `restricted` is the row they sit beside and `union` is labelled as comparable to neither. If a source later states its scoping explicitly, the REPORT records which mode it matched rather than silently re-anchoring.
- agentmemory's own docs say **graph extraction is off by default**, so its headline is presumably BM25+vector. Where our per-type table shows the graph carrying multi-session / temporal-reasoning, say so explicitly — that is the claim neither reference is making, and it is the only part of this comparison that is about the thesis rather than the leaderboard.
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
