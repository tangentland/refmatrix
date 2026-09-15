---
gmd: "0.1"
id: task-5.3-plan-5-memory-bridge-complete
title: "Task 5.3: Real tests replace mocks; widen + subject-filing loudness"
tags: [task, plan-5]
metadata:
  node_type: task
  status: pending
  plan: plan-5-memory-bridge-complete
---

# Task 5.3: Real tests replace mocks; widen + subject-filing loudness {#root}

> Plan: [[plan-5-memory-bridge-complete]]
> Status: Pending
> Depends on: 5.1

rel: part-of -> [[plan-5-memory-bridge-complete]]

## Requirements {#requirements}

- Mutation: break the partition argument in `_ingest_gmd_sync` → the bridge test fails. Widen test fails if the widen branch is removed.

## Files to Create / Modify {#files}

- Delete `test_finalize_runs_memory_bridge_over_the_handoff_dir`'s lambda; replace with a real tmp-store finalize test.
- `tests/test_memory_recall_widen.py`: `--session-start` with all memories older than 7d returns newest-k; explicit `--since 7d` returns none.
- `src/refmatrix/handoff.py:finalize_save_state`: subject filing failure → `out["filed_subject_error"]`, printed yellow by CLI/MCP.
- `workflow/test_mock_registry.md` graduation rows.

## Test Strategy (RED first) {#test-strategy}

tests/test_memory_bridge.py, tests/test_memory_recall_widen.py, tests/test_save_state.py.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-5.3-plan-5-memory-bridge-complete.md`.
- Committed on branch `task-5.3-plan-5-memory-bridge-complete`; merged `--no-ff` to `master`.
