---
gmd: "0.1"
id: task-23.2-lock-hold-fixture
title: "Task 23.2: one shared lock-hold test fixture that every writer's tests use"
tags: [task, tests, lock, fixture]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 23.2: the lock-hold fixture {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending
> Depends on: 23.1

rel: part-of -> [[plan-23-bounded-write-harness]]

## Requirements {#requirements}

1. **R1 `lock_free_during(lock)`.** A context manager that, from inside the code under test, has a
   probe thread try the lock (non-blocking, released by the thread that took it: the r8 RLock
   lesson). It records free/held.
2. **R2 `hold_recorder(lock)`.** It wraps a real lock and records every hold's duration (a
   pass-through, not a fake).
3. **R3 A marker.** `@pytest.mark.max_lock_hold(seconds)` fails a test whose recorded holds exceed
   the bound.
4. **R4 Adoption.** The existing lock tests use it:
   `test_context_rerank_off_the_writer_lock.py`, `test_read_path_partition_and_budget.py`, and the
   r9 #s-1 probes in `test_rerank_warning_routes.py`. The inline probe code they carry today is
   deleted.

## Acceptance criteria {#acceptance}

1. Reverting r8 #s-2's fix (the context rerank back under the writer lock) fails the adopted test
   through the fixture.
2. Reverting r9 #s-1's fix (memory_recall embedding under the lock) fails it too.
3. No test file keeps its own probe implementation (checked by grep).
