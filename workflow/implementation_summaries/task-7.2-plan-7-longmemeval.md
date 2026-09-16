---
gmd: "0.1"
id: task-7.2-summary
title: "Task 7.2/7.3 summary: LongMemEval store build and Layer A scoring"
tags: [implementation-summary, plan-7]
metadata:
  node_type: summary
  task: task-7.2-plan-7-longmemeval
  created: 2026-09-15
---

# Task 7.2 + 7.3 summary {#root}

rel: realizes -> [[task-7.2-plan-7-longmemeval]]
rel: realizes -> [[task-7.3-plan-7-longmemeval]]
rel: part-of -> [[plan-7-longmemeval]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]

## 7.2 — the build {#build}

`eval/production/longmemeval/ingest.py`. Four passes through the `rmx` CLI against an isolated
store on a separate volume: `init --no-hooks --no-agents --no-memory-hooks`, `ingest-gmd
--as-memory --memory-mtype longmemeval/session`, `embed --kinds memory`, `memory compile`. No
adapter class, no direct `Store()` open.

`ingest-gmd`, never plain `rmx ingest`, is the load-bearing argument and a test asserts the argv
because the argv is the only place it is visible. Measured on MemAware, plain ingest over chat
prose produced 1309 doc entities, **0 `mentions` rows and 3 concepts** — every symbolic surface
then degrades to the grep backstop and the harness reports a number for an index that was never
built.

A failing pass names itself and its exit code and stops the build. Continuing past a failed embed
leaves an empty vector table, which scores as "rmx is bad at dense recall" rather than as a broken
build — the same class of misattribution `feedback_no_silent_failures` exists to prevent.

9 tests against a recording runner; five mutants killed.

## 7.3 — the scoring {#scoring}

`eval/production/longmemeval/run.py`. Layer A only: deterministic Recall@k / MRR / hit@k, zero API
calls, per question type plus abstention plus overall.

Two modes emitted every run and never conflated. `union` scores against the whole 19,829-doc
store — harder than anything published, comparable to nobody, and what rmx faces in production.
`restricted` retrieves deep through the same CLI call, filters to the question's own haystack, and
cuts to k; that is the mode comparable to published figures.

### The correction that mattered {#correction}

The plan claimed `rmx memory recall` supports a candidate prefilter, citing
`test_dense_recall_respects_candidate_prefilter`. That test covers the **Python API** —
`ann_search(candidate_ids=...)` — and **no CLI flag exposes it**. Reaching past the CLI to use it
would have made this harness the bespoke path `eval/production/` exists to replace, which is how
four "declared but never populated" ingest defects survived behind a 0.982 MRR.

So `restricted` stays on the CLI and pays for it with depth, and the harness reports the cost
instead of hiding it: the **recall ceiling** — the fraction of questions whose gold appeared
anywhere in the deep pool. `restricted` cannot score above it, a low ceiling indicts the depth
rather than rmx, and a test asserts the invariant. A CLI candidate-set flag is registered as the
follow-up that removes the approximation.

Every recall method states `--rerank` or `--no-rerank` explicitly; a parametrized test reads the
argv. The daemon default flipped ON at 0.42.0 and a method passing no flag measures the
environment, silently voiding comparability with every earlier row.

17 tests, pure functions, no store. Six mutants killed. One first-run failure was a TEST bug, not
a code bug: `mrr` is reciprocal rank at `max(ks)` and the fixture passed `ks=[1]`, making MRR
identical to hit@1. The fixture was corrected and the table column is now labelled `mrr@N` so no
reader has to guess the cutoff.
