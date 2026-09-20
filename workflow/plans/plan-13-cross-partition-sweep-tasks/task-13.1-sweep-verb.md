---
gmd: "0.1"
id: task-13.1-sweep-verb
title: "Task 13.1: the sweep verb — three legs, one deadline, counted drops"
tags: [task, plan-13, verbs, daemon, partitions]
metadata:
  node_type: task
  status: pending
  plan: plan-13-cross-partition-sweep
  gate: after GO
---

# Task 13.1: the sweep verb {#root}

> Plan: [[plan-13-cross-partition-sweep]]
> Status: Pending — blocked on [[task-13.0-two-partition-kill-shot]] returning GO
> Depends on: [[task-13.0-two-partition-kill-shot]]

rel: part-of -> [[plan-13-cross-partition-sweep]]
rel: depends-on -> [[task-13.0-two-partition-kill-shot]]
rel: reinforces -> [[project_verbs_layer_antidrift]]
rel: reinforces -> [[feedback_daemon_call_retries_multiply_timeouts]]

## Requirements {#requirements}

- One verb, `sweep`, in `verbs.py`. CLI and MCP are adapters ([[task-13.3-surfaces-and-parity]]);
  nothing implements this twice (constitution IX).
- **TWO legs, not three** (r2 #b-6): `project` — which HOLDS the memory rows, because
  `memory-<project>` was merged away post-0.5.0 (`cli.py:9736`) and `rmx partition list` on this
  store returns only `refmatrix` / `memory-viascope` / `sessions-refmatrix` — and `session`
  (`sessions-<project>`). A "memory leg" beside a "project leg" would query one partition twice.
- **The session leg is symbolic-only** and says so in its own result (`"dense": false`): that
  partition has no vectors (`.refmatrix/vectors` has no `sessions-*` entry) and `embed` walks
  `graph_parts` = project + memory (`cli.py:6873`). It runs `content_rank`, NOT
  `hybrid_memory_recall` — specifying a dense call that silently degrades is how a half-leg reports
  a healthy candidate count (r2 #b-7).
- Each leg addresses its partition through `Store.with_partition(name)` (`store.py:1590`), which is
  **not concurrency-safe on one Store** — so every non-default leg is a DAEMON OP under
  `d._store_lock`, never a replica read. `search.cached_replica(root)` is pinned to one partition
  (`search.py:38-55`) and cannot serve this.
- **One deadline for the whole sweep**, not one per leg. Legs are attempted in order; a leg with no
  budget left is DROPPED and COUNTED. Never silently awaited, never silently skipped
  ([[feedback_no_silent_failures]]).
- **`retries=0` on every leg RPC.** `daemon.call` defaults to `retries=2` and triples any timeout —
  the 30 s grep wall (bug-049) was exactly this ([[feedback_daemon_call_retries_multiply_timeouts]]).
- The legs serialize on `_store_lock`, so the wall clock is the SUM of the legs, not the max. The
  result carries the per-leg elapsed so the sum is visible rather than inferred.
- Result shape (stable, because 13.5's diagnostic consumes it):
  ```
  {"rows": [...], "legs": [{"name": "session", "candidates": 12, "elapsed_ms": 40,
                            "dropped": false, "error": null}, ...],
   "fusion": "rrf"|"score", "deadline_ms": 800, "spent_ms": 310}
  ```
- **A zero-candidate leg is an error line, not an empty list**: `candidates: 0` with `error` set
  when the call failed, `error: null` when the partition genuinely held nothing. The two are
  different facts and the caller can tell them apart.
- Both fusion arms are implemented behind one parameter (`fusion="rrf"|"score"`), because 13.5
  pre-registered them as arms ([[plan-13-cross-partition-sweep#principle-rank]]). `rrf` calls
  `query.fuse_rrf`; `score` min-max normalises per leg, then sums.
- Cross-STORE fusion is out of scope: `entities.id` collides across roots, so this verb unions
  partitions of ONE store only, and says so in its docstring
  ([[plan-13-cross-partition-sweep#cross-store]]).

## Acceptance criteria {#acceptance}

- `rmx sweep "<query>"` against a two-partition store returns rows from more than one partition,
  and `legs[]` accounts for every leg attempted — including the ones that returned nothing.
- With a deadline smaller than the first leg's cost, the result carries `dropped: true` for the
  later legs and STILL RETURNS the first leg's rows. A deadline never produces an exception.
- No leg RPC is issued with `retries` unset or > 0 (asserted, not reviewed).
- The default `rmx context` path is byte-identical before and after this task
  ([[plan-13-cross-partition-sweep#secondary]]).

## Files {#files}

- modify `src/refmatrix/verbs.py` (the `sweep` verb)
- modify `src/refmatrix/daemon.py` (`_op_sweep`: per-leg `with_partition` under `_store_lock`)
- create `tests/test_sweep_verb.py`
- modify `workflow/test_mock_registry.md` if any double is introduced (prefer none — a real
  two-partition tmp store is cheap)

## Test strategy (RED first) {#test-strategy}

Over a REAL tmp store carrying two populated partitions (build it with the shipped ingest paths —
a store built by hand-inserting rows tests the fixture, not the sweep):

1. `test_a_sweep_returns_rows_from_every_populated_partition` — the union, on a store where each
   partition holds a document only it can answer.
2. `test_each_leg_is_accounted_for_including_the_empty_one` — three legs in `legs[]`, one with
   `candidates: 0, error: null`.
3. `test_a_failed_leg_reports_its_error_and_the_sweep_still_answers` — patch ONE leg's op to raise;
   `error` is set, the other legs' rows come back.
4. `test_the_deadline_is_shared_not_per_leg` — a deadline of N ms with a first leg that sleeps N
   leaves the later legs `dropped: true`, and `spent_ms <= deadline_ms + slack`.
5. `test_no_leg_rpc_uses_retries` — record `daemon.call` kwargs; every call carries `retries=0`
   **AND the recorded call count equals the number of legs attempted**. "Every call carries
   retries=0" is vacuously true over zero calls, so an implementation issuing no leg RPCs passed the
   first version of this test (r2 #s-5).
6. `test_score_arm_and_rank_arm_differ_on_a_constructed_disagreement` — a fixture where min-max
   summation and RRF order two ids differently, so the arms are proven distinct rather than
   assumed.
7. `test_two_legs_never_draw_from_one_partition` — the legs' partition ids are distinct. The first
   version asserted that no id appears in two legs, which is FALSE on any real store now that memory
   rows live in the project partition, and could only pass on a fixture carrying a partition the
   product no longer produces (r2 #b-6).
9. `test_the_session_leg_reports_itself_as_symbolic` — `dense: false` on that leg, so a missing
   dense half is visible rather than absorbed.
8. `test_context_default_path_is_unchanged` — golden ranked ids for `rmx context` on the fixture
   store, before/after.

**Mutations that must kill a test:** `retries=0` → default (kills 5); issue zero leg RPCs (kills 5's
count assertion); per-leg deadline instead of shared (kills 4); swallow a leg exception and return
`[]` (kills 3); fuse the score arm with RRF (kills 6); point both legs at the active partition
(kills 7); call `hybrid_memory_recall` on the session partition and report `dense: true` (kills 9).

## Implementation notes {#notes}

- Read `with_partition`'s docstring before writing the op — it names the locking constraint.
- Per-leg caps are a parameter with a documented default; the default is set by 13.5's measurement,
  not chosen here. Until then the default is "equal caps", and the spec says so rather than
  pretending a tuned number exists.
