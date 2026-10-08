---
gmd: "0.1"
id: task-23.1-queue-and-drain
title: "Task 23.1: a generic durable queue and bounded drain; learn_queue re-based on it"
tags: [task, queue, drain, lock]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 23.1: queue + bounded drain {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending
> Depends on: —

rel: part-of -> [[plan-23-bounded-write-harness]]

## Requirements {#requirements}

1. **R1 Queue.** `BoundedQueue(path, key_fn, max_lines)`:
   - append one JSON line with no lock and no socket;
   - read and coalesce by key at drain;
   - an overflow past `max_lines` is COUNTED and reported, never silently dropped (the
     memory-path rule).
2. **R2 Drain.** `drain(queue, apply_batch, lock, batch=N, hold_s=T)`:
   - apply in batches of N, each under one lock acquisition;
   - release between batches;
   - a batch whose hold exceeds T logs a warning with the count;
   - returns `{applied, batches, max_hold_s, overflow}`.
3. **R3 Crash safety.** A drain that dies mid-batch leaves the unapplied events in the queue;
   applied events are not re-applied (an applied-offset marker).
4. **R4 Re-base `learn_queue`** on it, with identical behaviour. Its existing tests pass unchanged.

## Acceptance criteria {#acceptance}

1. 1,000 events with N=200 drain in exactly 5 holds. A probe thread acquires the lock between
   batches.
2. A drain killed after batch 2 resumes at batch 3 with no double apply.
3. The existing `learn_queue` tests pass unchanged; the overflow is counted in `rmx learn status`.
