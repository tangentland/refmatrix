---
gmd: "0.1"
id: task-6.4-plan-6-deferrals-docs-benchmark
title: "Task 6.4: Loud verbs.py partition detect, perma-red test, mock registry"
tags: [task, plan-6]
metadata:
  node_type: task
  status: complete
  plan: plan-6-deferrals-docs-benchmark
---

# Task 6.4: Loud verbs.py partition detect, perma-red test, mock registry {#root}

> Plan: [[plan-6-deferrals-docs-benchmark]]
> Status: Complete (2026-09-16)
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

## Closing note (2026-09-16) {#closing}

Three of the four items were already satisfied by work done under other headings; only the mock
registry rows were outstanding.

- **`verbs.py` loud partition detect** — done. `memory_partition` logs a `debug` when the replica
  is unavailable during the bootstrap window and a `warning` when `partition_list` ANSWERS an
  error, naming the root, the error and the partition it falls back to. The silent guess is gone.
- **`tests/test_graph_landing.py` stub `_st`** — done, and the reason is recorded: the "perma-red"
  this task was written around was never a partition bug. It was a hand-rolled `class D` pinning
  `d.store` after the op moved to `d._st()`, i.e. a stale fake raising `AttributeError`.
- **`workflow/bug_registry.md` perma-red entry** — done as **bug-034**, which covers all five
  idle-machine failures. Worth re-reading: not one of the five was a product bug; each was a test
  left behind by a deliberate change, so four real contracts had no passing guard.
- **Mock registry rows** — DONE HERE. Three test files monkeypatched an external boundary without
  a row: `test_daemon_liveness.py` (OS socket + pid), `test_hub_plist_devtree.py` (launchd +
  subprocess), `test_sync_and_extras.py` (the `tldr` binary, `shutil.which`, launchd, daemon ping).
  `test_surface_parity.py` matched the scan but needs no row — it only sets env vars, which is
  configuration, not a mock.
