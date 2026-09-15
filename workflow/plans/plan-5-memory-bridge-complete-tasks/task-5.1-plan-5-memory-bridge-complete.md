---
gmd: "0.1"
id: task-5.1-plan-5-memory-bridge-complete
title: "Task 5.1: Lenient bridge + skipped counters + sync-disk alias"
tags: [task, plan-5]
metadata:
  node_type: task
  status: complete
  plan: plan-5-memory-bridge-complete
---

# Task 5.1: Lenient bridge + skipped counters + sync-disk alias {#root}

> Plan: [[plan-5-memory-bridge-complete]]
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-5-memory-bridge-complete]]

## Requirements {#requirements}

- Bridge over a tmp memdir with one GMD + one plain `.md` → both `get_memory(name)` rows exist; report shows `skipped_non_gmd: 0`; an unparseable file (binary) → `skipped_unparseable: 1` and named.
- Live: after deploy, `rmx memory get feedback_no_silent_failures` resolves.

## Files to Create / Modify {#files}

- `src/refmatrix/ingest_gmd.py`: `parse_gmd(path, lenient=True)` returns a doc for frontmatter-less markdown when `as_memory`; `IngestStats.skipped_non_gmd/skipped_unparseable`; `report()` prints them.
- `src/refmatrix/cli.py:_sync_memory_dir` passes `lenient=True`; `memory sync-disk` → calls `_sync_memory_dir` + prints deprecation; README:150 + docs/ARCHITECTURE.md updated.

## Test Strategy (RED first) {#test-strategy}

tests/test_memory_bridge.py::test_bridge_ingests_gmd_and_plain_files (real tmp Store, no monkeypatch of the SUT).

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-5.1-plan-5-memory-bridge-complete.md`.
- Committed on branch `task-5.1-plan-5-memory-bridge-complete`; merged `--no-ff` to `master`.
