---
gmd: "0.1"
id: task-7.3-plan-7-longmemeval
title: "Task 7.3: Layer A scoring: both haystack modes, per-type breakdown"
tags: [task, plan-7]
metadata:
  node_type: task
  status: pending
  plan: plan-7-longmemeval
---

# Task 7.3: Layer A scoring: both haystack modes, per-type breakdown {#root}

> Plan: [[plan-7-longmemeval]]
> Status: Pending
> Depends on: 7.1

rel: part-of -> [[plan-7-longmemeval]]

## Requirements {#requirements}

- Layer A only (Q2): deterministic Recall@{1,5,10,20}, MRR, hit@k. Zero LLM calls. Layer B is registered as a deferral, not built.
- Two scoring modes, both emitted every run, never conflated in output (Q1): `restricted` passes the question's own haystack as a candidate prefilter and is the mode comparable to published figures; `union` scores against the whole store and is comparable to nobody. Every printed table and every results file names its mode.
- `METHODS` covers the live read surfaces: `recall`, `recall-fuse`, `recall-rr`, `recall-fuse-rr`, `context`, `context-d2`, `scan`, `scan-nocontent`. `--rerank` / `--no-rerank` is passed EXPLICITLY on every recall method — the daemon default flipped ON at 0.42.0 and a method that passes no flag measures whatever the environment happened to be.
- Results break out per question type (single-session-user / -assistant / -preference, multi-session, temporal-reasoning, knowledge-update) as well as overall. Multi-session and temporal-reasoning are the two types the conceptual-memory thesis makes a claim about and the two where the published competitor is weakest; an overall-only number hides exactly the comparison this plan exists for.
- A surface that errors scores 0 for that question and the error is PRINTED with the question id. A dead surface must not be indistinguishable from a surface that found nothing.

## Files to Create / Modify {#files}

- create `eval/production/longmemeval/run.py`

## Test Strategy (RED first) {#test-strategy}

`tests/test_longmemeval_scoring.py` on hand-built rankings (no store, no rmx):
- Recall@k / MRR / hit@k match values computed by hand on a fixture with a known answer
- `restricted` mode drops candidates outside the question's haystack; `union` keeps them — asserted on one fixture where the modes MUST differ
- per-type aggregation partitions the question set exactly (sum of per-type n == scored n)
- abstention questions are scored and additionally reported as their own slice
- every recall method emits an explicit `--rerank` or `--no-rerank` (assert over the built argv, not the docstring)
- mutation check: removing the prefilter from `restricted` collapses it onto `union` and turns the mode-difference test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-7.3-plan-7-longmemeval.md`.
- Committed on branch `task-7.3-plan-7-longmemeval`; merged `--no-ff` to `master`.
