---
gmd: "0.1"
id: plan-23-bounded-write-harness
title: "Plan 23: one durable queue, one bounded drain, one lock-hold probe — built once, used by every writer"
tags: [plan, daemon, queue, lock, harness, bug-085]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
---

# Plan 23: the bounded-write harness {#root}

**Date:** 2026-10-07
**Status:** Drafting. Task specs 23.1–23.2 are written. This is wave 1's FIRST build, because plans
17, 19, 16.6 and 22 consume it.
**Origin:** the plan review's C5, applied by the user on 2026-10-07.

rel: derives-from -> [[plan-review-2026-10-07]]
rel: derives-from -> [[project_daemon_wedge_per_entity_lance_delete]]
rel: related-to -> [[project_grep_learn_wall_and_queue]]

## Why {#why}

Every wedge today was the same shape: per-event writes, or one long hold of `_store_lock`.
- bug-085: one Lance delete per entity.
- bug-093: one upsert per concept.
- r9 #s-1: model calls under the lock.

Four new specs each re-derive the cure: a durable append-only queue, a bounded drain that yields
the writer, and a test that proves the lock is free.
- the 0.72.3 `learn_queue`;
- 16.6 R4's marks;
- 19.2 R4's usage events;
- 17.1 R3's per-dataset holds.

Built once, every writer uses the same tested mechanism, and a fix lands in one place.
{#why-body}

## Tasks {#tasks}

| task | what | acceptance (summary) |
|---|---|---|
| 23.1 | `refmatrix/bounded.py`: a generic durable JSONL queue (append without the lock, coalesce by key, cap with a counted overflow) + a bounded drain (batch size N, one `_store_lock` hold per batch, the writer yielded between batches, a per-batch time bound with a warning); `learn_queue` re-based on it with no behaviour change | `learn_queue`'s existing tests pass unchanged; a drain of 1,000 events takes ⌈1000/N⌉ holds, each ≤ the bound |
| 23.2 | the shared test fixture: a `lock_free_during(fn)` probe (a thread acquires the lock from inside the work), a hold-time recorder, and a pytest plugin marker that fails a test whose code path holds the lock past a bound | the probe catches the r8 #s-2 / r9 #s-1 shapes when the fix is reverted (mutation); adopted by the existing lock tests |

Consumers: 16.6 R4 (marks), 19.2 R4 (usage), 17.1 R3 (per-dataset holds), 22.2 R5 (repair and
removal writes), and the bug-093 follow-up (yield between files in the watch flush).
{#consumers}
