---
gmd: "0.1"
id: task-6.1-plan-6-deferrals-docs-benchmark
title: "Task 6.1: Stale deferrals removed or registered"
tags: [task, plan-6]
metadata:
  node_type: task
  status: complete
  plan: plan-6-deferrals-docs-benchmark
---

# Task 6.1: Stale deferrals removed or registered {#root}

> Plan: [[plan-6-deferrals-docs-benchmark]]
> Status: Complete (2026-09-16)
> Depends on: —

rel: part-of -> [[plan-6-deferrals-docs-benchmark]]

## Requirements {#requirements}

- `grep -rn "deferred to v1\|Phase 2 will\|Phase A stub\|unused for now" src/` → empty; suite green; deferral registry linted.

## Files to Create / Modify {#files}

- `src/refmatrix/ingest_gmd.py` module docstring — body TF **is** indexed (weighted `mentions` via `bulk_link`, 0.35.0/0.36.1); the "deferred to v1" line was false, not merely stale.
- `src/refmatrix/store.py` `_log_event` docstring → facts.log is a verification/replay log, the catalog is authoritative and stays that way (the 2026-09 audit found no edge-time history to recover and three unlogged write paths).
- `src/refmatrix/embedder.py` `_extract_memory` — the "Phase A stub" comment was sitting on **two bare `except Exception: pass` branches on the production embed path**. Both now count and log through `_note_degraded`; `degraded_report()` / `reset_degraded()` expose the counters, `_op_embed` returns them, and `cli._degraded_embed_line` prints them. This is the CLAUDE.md#no-silent-failures rule, not cosmetics.
- `src/refmatrix/sync.py` — `yield_lock`/`yield_every` removed from **four** signatures (`sync_files`, `sync_since`, `flush_queue`, `_sync_paths`). Verified dead first: no caller anywhere passes them (the daemon passes them to `ingest_path`/`ingest_gmd_paths`, which do use them).
- `workflow/deferral_registry.md` — row added for launchctl Linux (`fail-closed-seam`); bug-008's row updated to GRADUATED LIVE after checking the live hook.

**Correction to this spec: `src/refmatrix/duckdb_view.py` is NOT deleted.** It is live — `store.py:1762` imports `DuckCatalogView` at runtime and `store.py:867`/`:1754` document `ReadConnection` as part of the cursor surface. `tests/test_duckdb_read_routing.py` does not exist; `tests/test_duckdb_parity.py` imports the module and passes. Deleting it would have broken the read path. The prescription was written when the module looked orphaned and was not re-checked.

## Test Strategy (RED first) {#test-strategy}

`tests/test_deferrals_clean.py` (14 tests): the banned-phrase grep guard (plus a meta-test so the
banned list cannot be emptied to get green), four signature tests + a caller scan for the dead sync
params, three extractor tests for the degraded-memory counters, two render tests for the CLI line,
and two `_op_embed` tests proving the count reaches the caller (embed runs daemon-side, so a
CLI-process counter would always read zero).

- RED: `workflow/review-output/pytest-task-6.1-RED.log` — 9 failed, 1 passed.
- GREEN: `workflow/review-output/pytest-task-6.1-GREEN2.log` — 14 passed.
- Affected files: `workflow/review-output/pytest-task-6.1-affected.log` — 87 passed.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-6.1-plan-6-deferrals-docs-benchmark.md`.
- Committed on branch `task-6.1-plan-6-deferrals-docs-benchmark`; merged `--no-ff` to `master`.
