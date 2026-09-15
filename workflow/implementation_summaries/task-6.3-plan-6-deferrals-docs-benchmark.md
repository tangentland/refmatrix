---
gmd: "0.1"
id: impl-task-6.3-plan-6-deferrals-docs-benchmark
title: "Task 6.3 — the headline benchmark number exists in a committed artifact"
tags: [implementation-summary, plan-6]
metadata:
  node_type: implementation-summary
  task: task-6.3-plan-6-deferrals-docs-benchmark
---

# Task 6.3 — 0.961 has a file now {#root}

rel: implements -> [[task-6.3-plan-6-deferrals-docs-benchmark]]

## What shipped {#shipped}

- `eval/production/csn_code.py --out PATH`: `write_artifact` records the harness, dataset, corpus/query counts (run and total), `full_run` (nothing capped), the sampling flags, every metric, per-phase timing, `refmatrix.__version__`, the git sha, the UTC timestamp and the exact command.
- `eval/production/results/csn_python/metrics.json`: the FULL corpus run (43827 docs, 14918 queries) made in this session at a965805 / 0.69.1 — MRR@10 0.9610, Recall@1 0.9440, Recall@10 0.9842, nDCG@10 0.9669; ingest 1913 s, retrieval 390 s (plan Q2's 60-minute box held: 39 min). `metrics.sample300.json`: the valid 300-query quick run (MRR@10 0.9836 on an easier haystack), kept as the fallback record and named as such in README.
- README and `docs/PERFORMANCE.md` cite the artifact path, sha, version and date next to the table.
- `tests/test_eval_artifact_cited.py` (4 tests): both docs name the path; the artifact exists with the harness's fields; the bold MRR@10 in both docs equals the artifact's to three decimals; a partial run must be described where it is cited (a full run must name the corpus size).

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-6.2-6.3-red.log` (the four artifact tests failed: no path cited, no artifact). GREEN `pytest-task-6.3-green.log`. Mutation `pytest-task-6.3-mutation.log`: README's `**0.961**` edited to `**0.962**` fails `test_cited_figure_matches_the_artifact`. Run logs: `csn-full-run.log`, `csn-sample-run.log`.

## Not in scope {#not}

`eval/production/REPORT.md` (the nobody/semantic docstring isolation on a 2000-doc subsample) is a different experiment and keeps its own numbers.
