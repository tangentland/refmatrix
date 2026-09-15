---
gmd: "0.1"
id: task-6.2-plan-6-deferrals-docs-benchmark
title: "Task 6.2: Generated CLI tree + hooks table in docs"
tags: [task, plan-6]
metadata:
  node_type: task
  status: pending
  plan: plan-6-deferrals-docs-benchmark
---

# Task 6.2: Generated CLI tree + hooks table in docs {#root}

> Plan: [[plan-6-deferrals-docs-benchmark]]
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-6-deferrals-docs-benchmark]]

## Requirements {#requirements}

- `tests/test_docs_generated.py`: both sections equal their render (fails when a command is added without regenerating).

## Files to Create / Modify {#files}

- `scripts/gen-cli-tree.py`: walks `refmatrix.cli.main` (click) → markdown tree with one-line help; writes between `<!-- cli-tree:start/end -->` in `docs/ARCHITECTURE.md`; `--check` mode diff.
- README hooks table between `<!-- hooks-table:start/end -->` from `_claude_hook_block` defaults.

## Test Strategy (RED first) {#test-strategy}

tests/test_docs_generated.py.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-6.2-plan-6-deferrals-docs-benchmark.md`.
- Committed on branch `task-6.2-plan-6-deferrals-docs-benchmark`; merged `--no-ff` to `master`.
