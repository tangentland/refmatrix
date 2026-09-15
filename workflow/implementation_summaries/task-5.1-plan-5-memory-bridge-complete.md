---
gmd: "0.1"
id: impl-task-5.1-plan-5-memory-bridge-complete
title: "Task 5.1 — lenient bridge + skipped counters + sync-disk alias"
tags: [implementation-summary, plan-5]
metadata:
  node_type: implementation-summary
  task: task-5.1-plan-5-memory-bridge-complete
---

# Task 5.1 — one bridge, one identity rule, one report {#root}

rel: implements -> [[task-5.1-plan-5-memory-bridge-complete]]

## What shipped {#shipped}

- `IngestStats.skipped_non_gmd` / `skipped_unparseable: [(path, error)]`, printed by `report()` (`skipped_non_gmd: N`, `skipped_unparseable: N` + one line per file). The pass-1 loop counts both instead of a bare `continue`.
- `parse_gmd(..., memory_ids=True)`: a memory file is named by its frontmatter `id`, else its STEM (the memory-file rule), never the path-shaped lenient id. `ingest_gmd_paths(as_memory=True)` parses leniently with memory ids; the daemon's ingest body and the in-process `_ingest_gmd_sync` pass `lenient=as_memory` (plan Q1).
- `_sync_memory_dir` returns `skipped_non_gmd`, `skipped_unparseable: [{path, error}]` (parsed from the report by `_parse_bridge_report`) alongside `report`/`error`.
- `rmx memory sync-disk` is a deprecated alias of the bridge (prints the deprecation, runs `_sync_memory_dir` per path, `--dry-run` refused); the 4.8 KB hand-rolled walker is deleted, not kept dead (plan Q2). README and `docs/ARCHITECTURE.md` teach `ingest-gmd --as-memory`.

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-5.1-red.log` (3 failed on a real spawned daemon). GREEN `pytest-task-5.1-green.log` (3 passed); neighbours `pytest-task-5.1-neighbours.log`. Mutation `pytest-task-5.1-mutation.log`: dropping the `skipped_unparseable` append fails `test_bridge_counts_and_names_an_unparseable_file`.
