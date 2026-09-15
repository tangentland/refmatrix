---
gmd: "0.1"
id: task-6.1-plan-6-deferrals-docs-benchmark
title: "Task 6.1: Stale deferrals removed or registered"
tags: [task, plan-6]
metadata:
  node_type: task
  status: pending
  plan: plan-6-deferrals-docs-benchmark
---

# Task 6.1: Stale deferrals removed or registered {#root}

> Plan: [[plan-6-deferrals-docs-benchmark]]
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-6-deferrals-docs-benchmark]]

## Requirements {#requirements}

- `grep -rn "deferred to v1\|Phase 2 will\|Phase A stub\|unused for now" src/` → empty; suite green; deferral registry linted.

## Files to Create / Modify {#files}

- `src/refmatrix/ingest_gmd.py` module docstring; `src/refmatrix/store.py:646` → "facts.log is a verification/replay log; catalog is authoritative" + `rel` to the audit memory; `src/refmatrix/embedder.py:203` stub branch + comment; `src/refmatrix/sync.py:200` params removed from signature + callers; delete `src/refmatrix/duckdb_view.py` + `tests/test_duckdb_read_routing.py` (or the two tests that import it); `workflow/deferral_registry.md` row for launchctl Linux.

## Test Strategy (RED first) {#test-strategy}

Existing suite; a grep test in tests/test_deferrals_clean.py that fails on the banned phrases.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-6.1-plan-6-deferrals-docs-benchmark.md`.
- Committed on branch `task-6.1-plan-6-deferrals-docs-benchmark`; merged `--no-ff` to `master`.
