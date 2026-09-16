---
gmd: "0.1"
id: task-12.2-rerank-cost-budget
title: "Task 12.2: the rerank worker reports what it costs, and an expired frame is dropped"
tags: [task, plan-12, rerank, model-workers, hook-budget]
metadata:
  node_type: task
  status: complete
  plan: plan-12-open-bug-remediation
---

# Task 12.2: the rerank worker reports what it costs, and an expired frame is dropped {#root}

> Plan: [[plan-12-open-bug-remediation]]
> Status: Complete
> Bugs: bug-025 (todo G13), bug-019 (recurring)
> Depends on: [[task-12.1-shared-worker-readoption]]

rel: part-of -> [[plan-12-open-bug-remediation]]
rel: depends-on -> [[task-12.1-shared-worker-readoption]]

## Requirements {#requirements}

- bug-025: 7/7 runs of the exact deployed hook argv burned the full 5 s budget with
  `rerank failed (TimeoutError: timed out)` and 0 of 5 rows reranked, returning exactly what
  `--no-rerank` returns in 0.79 s. bug-019's fix capped the pool until ONE measurement fit; the
  cost was never made knowable to the caller. The same capped 10 x 700 pool took 9.26 / 14.08 /
  3.72 s on three consecutive tries.
- Two halves, and BOTH are required — a caller that skips politely while abandoned work still
  starves the socket has fixed nothing.

### Half 1: cost is knowable {#cost}

- `_RerankRole` keeps an EMA of **seconds per doc** over the scoring calls it actually ran
  (`alpha` 0.3, seeded on the first real call, never from a synthetic warmup), and `info()` returns
  `cost_s_per_doc` plus `scored_docs` (the sample count behind it). An EMA with no samples reports
  `null`, not a guess.
- `ModelServer` adds `queue_depth` per role to the `info` response: how many requests are waiting
  on that role's `WorkerClient` lock plus the one in flight. The hub knows this and nobody has ever
  asked it.
- `reranker.estimate_rerank_s(info, n_docs)` is the single place the arithmetic lives:
  `(1 + queue_depth) * n_docs * cost_s_per_doc`. One function, called by every budgeted caller —
  the four-copies failure [[feedback_reuse_shared_stoplist]] records is the thing to avoid here.

### Half 2: an expired frame is dropped {#deadline}

- The `rerank` request frame carries `deadline` (absolute unix time). The worker checks it **when
  it dequeues the frame**, before loading pairs into the model, and answers
  `ok:false, error:"deadline expired N.NNs ago"` without scoring. That is the case that matters:
  the abandoned request is not the one in flight, it is the one QUEUED behind it that the client
  already gave up on.
- The worker never checks a deadline mid-forward-pass. Interrupting torch is out of scope and
  pretending otherwise would be a lie in the docstring.
- `SharedWorkerClient.call` sets `deadline` from its own socket timeout when the caller does not
  pass one, so a bounded client cannot forget.

### The caller {#caller}

- `cli._replica_memory_recall` and the `scan.py` rerank leg probe `info` (already bounded by
  `RERANK_PROBE_S`), compute `estimate_rerank_s(info, len(docs))`, and when the estimate exceeds
  the remaining budget they SKIP with a reason that names the numbers:
  `rerank skipped: 10 docs x 0.42 s/doc x (1+2 queued) = 12.6 s > 3.8 s left; hits unreranked`.
- When the estimate fits, the call carries the deadline.
- Acceptance is measured **under ordinary load, two runs minutes apart, counting RERANKED ROWS** —
  never wall time in the quiet minute after a relaunch. That mistake is what made bug-019's fix
  look like it worked ([[impression_bsd_cost_measured_idle]]).

## Files to Create / Modify {#files}

- modify `src/refmatrix/embed_worker.py` (`_RerankRole`: EMA, deadline check)
- modify `src/refmatrix/modelsrv.py` (`queue_depth` in `info`, `deadline` default in `call`)
- modify `src/refmatrix/reranker.py` (`estimate_rerank_s`)
- modify `src/refmatrix/cli.py` (`_replica_memory_recall` rerank leg)
- modify `src/refmatrix/scan.py` (the scan-prompt rerank leg)
- modify `docs/architecture/todo.md` (G13 -> done)
- create `tests/test_rerank_cost_budget.py`
- modify `workflow/bug_registry.md` (bug-025 -> fixed; bug-019 -> fixed, superseded by this)

## Test Strategy (RED first) {#test-strategy}

`tests/test_rerank_cost_budget.py`, against a stub worker (no torch):
- the EMA is `null` before any real scoring call and a number after; a warmup `info` does NOT seed it
- the EMA moves toward a slow call and is not reset by a fast one (alpha behaviour, asserted
  numerically)
- `estimate_rerank_s` multiplies by `1 + queue_depth`; queue_depth 0 is the single-caller case
- a frame whose `deadline` has passed is answered WITHOUT scoring — asserted by the score call
  never happening (a counter on the stub), not by timing
- a frame with a future deadline scores normally
- `SharedWorkerClient.call` injects a deadline derived from its timeout when none is passed
- **the incident replay**: a stub reporting 0.42 s/doc with 2 queued, a 10-doc pool and 3.8 s left
  -> the leg SKIPS, the warning names docs, per-doc cost, queue depth and the remaining budget, and
  `reranked` is False on every row
- the same stub with 30 s left -> the leg RUNS and rows come back `reranked: True`
- both call sites are covered (`_replica_memory_recall` AND `scan.py`) — one passing surface does
  not prove the other ([[impression_bsd_existence_check_tests]])
- mutation check: making `estimate_rerank_s` ignore `queue_depth` turns the skip test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation noted.
- A LIVE measurement in `workflow/measurements/rerank-cost-budget-0916.md`: two runs of the exact
  deployed hook argv, minutes apart, under ordinary load, counting reranked rows.
- `workflow/implementation_summaries/task-12.2-rerank-cost-budget.md`.
- Branch `task-12.2-rerank-cost-budget`, merged `--no-ff` to `master`.
