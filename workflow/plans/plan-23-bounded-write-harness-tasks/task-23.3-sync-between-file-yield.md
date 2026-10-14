---
gmd: "0.1"
id: task-23.3-sync-between-file-yield
title: "Task 23.3: _sync_paths yields the writer between files, through transaction boundaries and the bind seam (bug-093's open half)"
tags: [task, sync, watch, lock, yield, bug-093, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-14
---

# Task 23.3: the between-file yield in `_sync_paths` {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 23.1 (`bounded_steps`, `bind`), 23.2 (recorder), 23.0 (sandbox)

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: implements -> [[plan-review-2026-10-14#t2]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81#s-3]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2#s-3]]
rel: evidence-for -> [[bug_registry#registry]]

## Why {#why}

bug-093 (fixed 0.76.3) batched the watch flush's semantic pass, but its row still lists an open
half: "yield the writer BETWEEN files (one flush holds `_store_lock` across all its files)". d2c
makes that this task: a transaction boundary inside `_sync_paths`, the `bind` seam, and write-count
tests. The decision-log review (#s-3) fixes the API: it is a `bounded_steps` consumer, not a queue.

Facts at HEAD `b1c4324`:
- `_sync_paths` (`sync.py:147`) wraps ALL its files in one `with s.transaction(),
  s.deferred_links():` (`sync.py:191`) and deliberately never yields: releasing `_store_lock`
  mid-transaction would expose a half-open connection (the comment at `sync.py:182-190`). Yielding
  is safe only BETWEEN transactions.
- Its phases: the per-file pass (purge / skip-unchanged by mtime / ingest); then, over the touched
  files, `.pseudo` semantics, `.md` semantics with an ADR number → entity map built from the
  touched files plus a DB query, and the bulk Python semantic pass (`_build_python_semantic_record`
  builds each record OFF the store; `bulk_apply_records` applies them).
- The daemon holds `_store_lock` around the whole call at three sites: the watcher's `_flush`
  (`daemon.py:3000`, one hold across every owner root's files and the pre-flush repair),
  `_op_sync_files` (`:3338`) and `_op_sync_since` (`:3707`). None binds a partition.
- Non-daemon callers: `watch.py:170` (standalone watch), `cli.py:8439`, `cli.py:8459`.
{#why-body}

## Requirements {#requirements}

1. **R1 One transaction per step.** `_sync_paths` takes a REQUIRED `bind` and runs through 23.1's
   `bounded_steps`:
   - per-file pass: one file per step (`batch=1`), each step its own `bind` hold, transaction,
     `deferred_links` scope and in-transaction fragment flush (23.1 R1.3);
   - the ADR map build: one step;
   - `.pseudo` and `.md` semantics: one file per step;
   - Python semantics: records built in `prepare` (off the lock), applied by `bulk_apply_records`
     in steps of `RMX_SYNC_SEMANTIC_BATCH` records (default 50).
   The lock is released only between steps, so never inside a transaction. {#r1}
2. **R2 Partition bound per step.** Each step binds the owner store's project partition by NAME
   through `bind`; no step relies on the binding at rest. {#r2}
3. **R3 Callers.** The three daemon sites drop their outer `with d._store_lock:` and pass
   `daemon_bind(d)`; the watcher's pre-flush repair keeps its own single hold. Non-daemon callers
   pass `serial_bind(store)`, which binds the same way with a process-local lock. The parameter is
   required; there is no default that skips binding (`feedback_main_path_must_exercise_core_mechanisms`).
   {#r3}
4. **R4 Cancel and crash.** `cancel_check` is `bounded_steps`' `cancel`. A cancelled or crashed
   sync leaves every committed step committed; the uncommitted files are re-synced next time
   because their mtime stamp was not written (the stamp commits in the file's own step). The
   docstring states that a reader between steps can see some files of one sync updated and others
   not, and that each file is consistent on its own. {#r4}
5. **R5 Report unchanged.** The returned report keys (`added`, `updated`, `purged`, `touched`,
   `cancelled`, `vector_delete_failed`) and the `append_sync_log` line keep their meaning; the run's
   `holds` and `max_hold_s` are added. {#r5}
6. **R6 The comment at `sync.py:182-190` is rewritten** to state the new rule: one transaction per
   step, the lock released only between steps. {#r6}

## Acceptance criteria {#acceptance}

1. **Yields between files.** A sync of 5 changed files through `daemon_bind` on a real recorded
   `_FairLock`: ≥ 5 holds, and a queued competitor wins between every consecutive pair of per-file
   steps (4 ordered wins). Mutation: restore the single outer `s.transaction()` FAILS (1 hold, 0
   wins); restore the outer `with d._store_lock:` in `_op_sync_files` FAILS through 23.2's
   `LockDeadlock` (the lock is not reentrant), not a hang. {#ac-1}
2. **Never released inside a transaction.** The recorder's `on_release` asserts
   `st._in_transaction is False` at every release over the AC-1 run. {#ac-2}
3. **Partition.** Between two steps a competitor binds `sessions-<project>` and releases while still
   bound (the bug-098 shape); every row of the sync lands in the project partition. Mutation: bind
   once before the loop FAILS. {#ac-3}
4. **Write counts (bug-093's detector).** Re-syncing a fixture `.py` file with 10 and with 100
   docstring keywords executes the same number of statements per hold (± 2) and 0 single-row
   concept upserts (23.2 R3). Mutation: the per-row `_ingest_python_semantics` path FAILS. {#ac-4}
5. **Crash leaves a consistent, resumable state.** A spawned child syncing 5 files `os._exit`s after
   step 3 commits; a fresh store shows 3 files synced and stamped; the next sync processes exactly
   the other 2. {#ac-5}
6. **Same graph.** The 5-file sync's entities, links and fragments equal those of the HEAD code on
   the same fixture (row diff), so chunking changed holds, not results. {#ac-6}
7. **Existing sync tests** (`tests/test_sync_semantic_bulk.py` and every test that calls
   `sync_files` / `sync_since` / `flush_queue`) pass with `serial_bind` or `daemon_bind` passed.
   {#ac-7}

## Test strategy {#test-strategy}

Every test runs inside task 23.0's sandbox (d1a/d1b). In-process `Daemon` + real `Store` on a short
`mkdtemp` root built through 23.2's `recorded_daemon`; real files in the tmp project; AC-5's crash
runs in a spawned Python child that opens its own `Store` (no `rmx`, no fork of a DuckDB holder).
Logs: `workflow/review-output/pytest-sync-yield.log`.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| d2c (task 23.3; transaction boundary in `_sync_paths`; `bind`; write-count tests) | [[#r1]], [[#r2]], [[#ac-1]], [[#ac-4]] |
| 23 #s-3 (bug-093 yield unowned, not queue-shaped) | this task; [[#r1]] on `bounded_steps` |
| decision-log #s-3 (23.3 on `bounded_steps`) | [[#r1]] |
| 23 #b-1 (binding across yields) applied to sync | [[#r2]], [[#ac-3]] |
| 23 #b-3 (count writes, not seconds) | [[#ac-4]] |
| d1a/d1b (sandboxed tests) | [[#test-strategy]] |
