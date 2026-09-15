---
gmd: "0.1"
id: task-6.4-plan-6-deferrals-docs-benchmark
title: "Task 6.4: Loud verbs.py partition detect, perma-red test, mock registry"
tags: [task, plan-6]
metadata:
  node_type: task
  status: pending
  plan: plan-6-deferrals-docs-benchmark
---

# Task 6.4: Loud verbs.py partition detect, perma-red test, mock registry {#root}

> Plan: [[plan-6-deferrals-docs-benchmark]]
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-6-deferrals-docs-benchmark]]

## Requirements {#requirements}

- Full suite 0 failures; registry lists every file that monkeypatches an external boundary.

## Files to Create / Modify {#files}

- `src/refmatrix/verbs.py:148` → log via daemon/hub logger and fall back explicitly; `tests/test_graph_landing.py` stub daemon gains `_st`; `workflow/test_mock_registry.md` rows per test file for external mocks (launchctl, subprocess, sockets); `workflow/bug_registry.md` entry for the perma-red test.

## Test Strategy (RED first) {#test-strategy}

Existing suite + registry lint.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-6.4-plan-6-deferrals-docs-benchmark.md`.
- Committed on branch `task-6.4-plan-6-deferrals-docs-benchmark`; merged `--no-ff` to `master`.
