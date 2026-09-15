---
gmd: "0.1"
id: impl-task-5.3-plan-5-memory-bridge-complete
title: "Task 5.3 — real tests replace mocks; widen + subject-filing loudness"
tags: [implementation-summary, plan-5]
metadata:
  node_type: implementation-summary
  task: task-5.3-plan-5-memory-bridge-complete
---

# Task 5.3 — the bridge is tested as the bridge {#root}

rel: implements -> [[task-5.3-plan-5-memory-bridge-complete]]

## What shipped {#shipped}

- `tests/test_save_state.py::test_finalize_runs_memory_bridge_over_the_handoff_dir` (a lambda in place of `_sync_memory_dir`) is gone; `tests/test_memory_bridge.py::test_finalize_save_state_bridges_the_handoff_dir_for_real` runs `finalize_save_state` against a real spawned daemon and reads the row back, and `::test_finalize_skips_the_bridge_on_sync_false_and_dry_run` proves the skip on the store (no row), not on a call list. Registry: `cli._sync_memory_dir` row graduated + graduation-log entry.
- `tests/test_memory_recall_widen.py`: the hook's own command line — `--session-start` on a store whose newest memory is 8 d old returns newest-k and says `widened` on stderr; `--session-start --since 7d` returns none and does not widen.
- Subject-filing loudness (`finalize_save_state` → `filed_subject_error`, carried by `verbs.save_state`, printed by the CLI) landed in the plan-2 r3/r4 remedies (`workflow/implementation_summaries/remedy-plan-2-hooks-reproducible.md`); nothing further to build here.

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-5.3-red.log` (the real finalize test passed on arrival — the 5.1/5.2 bridge already worked — the widen `--since 7d` case was red until its expectation matched Q6's include_session rule). GREEN `pytest-task-5.3-green.log` (29 passed: bridge, widen, save-state). Mutations `pytest-task-5.3-mutation.log`: (A) a wrong partition in `_ingest_gmd_sync` fails `test_bridge_ingests_gmd_and_plain_files`; (B) removing the widen branch in `verbs.recent_rows` fails `test_session_start_widens_to_newest_k_when_the_7d_window_is_empty`.
