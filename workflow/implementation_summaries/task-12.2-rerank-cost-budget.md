---
gmd: "0.1"
id: task-12.2-rerank-cost-budget-summary
title: "Implementation summary: the rerank worker reports what it costs"
tags: [summary, plan-12, rerank, model-workers]
metadata:
  node_type: summary
  task: task-12.2-rerank-cost-budget
  created: 2026-09-16
---

# Implementation summary: task 12.2 (bug-025, bug-019, G13) {#root}

rel: implements -> [[task-12.2-rerank-cost-budget]]
rel: part-of -> [[plan-12-open-bug-remediation]]
rel: evidence-for -> [[rerank-cost-budget-0916]]

## What shipped {#shipped}

- `embed_worker._RerankRole`: `_observe` + `_ema` + `_scored_docs`; `info` returns
  `cost_s_per_doc` / `scored_docs`. Seeded ONLY by real scoring calls.
- `embed_worker.main`: a frame whose `deadline` has passed is answered
  `deadline expired N.NNs ago; not scored`, before the model is touched.
- `modelsrv.ModelServer`: `_pending` per role, `_augment_info` adds `queue_depth`;
  `SharedWorkerClient.call` stamps a deadline from its own timeout.
- `reranker`: `RerankSkipped`, `estimate_rerank_s`, `RemoteReranker(budget_s=)` holding a DEADLINE,
  `shared_reranker` passing its timeout as the budget.
- `cli._replica_memory_recall` and `context._rerank_bodied` catch `RerankSkipped`, keep retrieval
  order, and say the arithmetic. `content_only_bundle`'s bare `except Exception: pass` around the
  rerank now prints the reason to stderr instead of swallowing it.

## The decision lives in ONE place {#one-place}

The first design put the budget check in both call sites. It went into `RemoteReranker` instead —
the object that already holds the caller's timeout — so `memory recall` and `scan-prompt` get the
same arithmetic without either implementing it. That is the lesson of
[[feedback_reuse_shared_stoplist]] applied before the second copy existed.

## RED / GREEN / mutation / live {#evidence}

- RED: `workflow/review-output/red-task-12.2.log` — 13 failed.
- GREEN: `workflow/review-output/green-task-12.2.log` — 18 passed.
- Mutation A (`estimate_rerank_s` ignores `queue_depth`): the queue test RED.
- Mutation B (the worker stops honouring an expired deadline):
  `test_a_frame_whose_deadline_passed_is_never_scored` RED.
- Regression: `test_plan2_remedy_r7` (the previous rerank-budget remedy) — 30 passed together.
- Live, real cross-encoder on a private socket: EMA `null` -> `0.0098 s/doc` after one 10-doc call,
  `queue_depth` on the same handshake, and a past-deadline frame refused without scoring.

## The honest state {#honest}

**bug-025's live acceptance is NOT met yet, and the measurement says so.** Two runs of the exact
deployed hook argv today still returned `rerank failed (TimeoutError: timed out)` with 0 of 5 rows
reranked under load 4.00 — because the worker answering is the DEPLOYED hub's, whose `info` carries
no cost, and a missing cost is treated as unknown rather than guessed. The skip can only fire once
the hub runs this code. Acceptance stays: two runs, minutes apart, under ordinary load, counting
RERANKED ROWS, after deploy.
