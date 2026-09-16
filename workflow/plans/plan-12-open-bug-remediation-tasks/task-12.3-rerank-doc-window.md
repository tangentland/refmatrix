---
gmd: "0.1"
id: task-12.3-rerank-doc-window
title: "Task 12.3: the reranker reads the part of the document the query is in"
tags: [task, plan-12, rerank, retrieval-quality]
metadata:
  node_type: task
  status: pending
  plan: plan-12-open-bug-remediation
---

# Task 12.3: the reranker reads the part of the document the query is in {#root}

> Plan: [[plan-12-open-bug-remediation]]
> Status: Pending
> Bug: bug-032
> Depends on: [[task-12.2-rerank-cost-budget]]

rel: part-of -> [[plan-12-open-bug-remediation]]

## Requirements {#requirements}

- bug-032: the cross-encoder scores only the first `MAX_DOC_CHARS` (2048) of a document. On
  `longmemeval_oracle` (896 answer-bearing turns) the median answer offset is 0, p75 3,268,
  p90 8,117, and **331/896 = 36.9% sit past 2048** — invisible to the reranker.
- The BOUND is sound: a cross-encoder truncates at ~512 tokens anyway, so a longer pair costs the
  same and adds nothing. The STRATEGY is what is wrong. Head truncation assumes "a document's head
  is what the cross-encoder needs to rank it" — true for a curated GMD memory with a title and a
  lead, false for a chat transcript that has neither.
- Replace head truncation with a **query-anchored window** built by the EXISTING `kwic` windower:
  the text handed to the model is the region around the query-term hits, not the first N chars.
  `kwic.query_terms` + `kwic._first_hit` already do the locating; this task does not write a second
  windower ([[feedback_reuse_shared_stoplist]]).
- Contract: the windowed text is never longer than the existing bound, so **the per-pair cost is
  unchanged** — this is a quality change at fixed cost, and the task must show that, not assert it.
- A document with NO query-term hit falls back to the head, which is exactly today's behaviour. The
  change can only differ where a hit exists past the head.
- Both the in-process `Reranker.score` and `RemoteReranker.score` truncate today. The windowing
  moves to ONE place that both call, because two truncation sites drifting apart is how the
  `[:2048]` ended up applied at three offsets in the first place.
- `RMX_RERANK_WINDOW=0` restores head truncation, because the A/B has to be runnable on the
  deployed binary without a redeploy.

## Measurement (REQUIRED, and it may come back zero) {#measurement}

- The headline effect may be ZERO. After the ch-bsd r2 attribution correction, truncation can only
  reach `scan` (single-session-preference 0.150) — `rmx context` never constructs a reranker — and
  only if the hub's shared worker answered during the run at all.
- So the task ships an A/B on the production harness (`eval/production/longmemeval/`), reports
  windowed vs head-truncated on the SAME candidate pools, and states the result whatever it is.
- The pre-registered read: report MRR@20 and hit@5 on the `scan` surface for both arms, plus the
  per-pair latency for both. **No claim of improvement without that table.**

## Files to Create / Modify {#files}

- modify `src/refmatrix/reranker.py` (one windowing helper; both `score` paths use it)
- modify `src/refmatrix/cli.py` if `RERANK_DOC_CHARS` interacts with the window
- create `tests/test_rerank_window.py`
- create `workflow/measurements/rerank-window-ab-0916.md`
- modify `workflow/bug_registry.md` (bug-032 -> fixed or measured-no-effect, whichever the A/B says)

## Test Strategy (RED first) {#test-strategy}

`tests/test_rerank_window.py`:
- a doc whose only query term sits at char 6,000 yields a window CONTAINING that term; head
  truncation yields text that does not — the two are asserted against each other
- the window never exceeds the bound (length assertion at several doc sizes)
- a doc with no query term returns the head, byte-identical to today's `[:N]`
- a doc SHORTER than the bound is returned whole, unwindowed
- multi-term queries anchor on the first hit and the window is stable under term order
- both `Reranker.score` and `RemoteReranker.score` go through the same helper (asserted by patching
  the helper and observing both paths call it — [[impression_bsd_tests_bypass_wiring]])
- `RMX_RERANK_WINDOW=0` restores byte-identical head truncation
- mutation check: making the windower always return the head turns the 6,000-char test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation noted.
- The A/B table exists and is quoted in the summary, including a null result if that is the answer.
- `workflow/implementation_summaries/task-12.3-rerank-doc-window.md`.
- Branch `task-12.3-rerank-doc-window`, merged `--no-ff` to `master`.
