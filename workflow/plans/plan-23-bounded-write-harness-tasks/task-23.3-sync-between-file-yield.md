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
> Status: Pending (revision round 2, 2026-10-14: re-review findings nb23-3 and nb23-4; see
> [[#rev-round-2]])
> Depends on: 23.1 (`bounded_steps`, `bind`), 23.2 (recorder), 23.0 (sandbox)

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: implements -> [[plan-review-2026-10-14#t2]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81#s-3]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2#s-3]]
rel: evidence-for -> [[bug_registry#registry]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#nb23-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#nb23-4]]
rel: implements -> [[plan-review-2026-10-14#t9-fixes]]
rel: related-to -> [[project_sync_mtime_gate_strands_docs]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]

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

Added in revision round 2, re-read at HEAD `3357c44`:
- **Where the "done" stamp is written.** In the per-file pass, a changed file is purged together
  with its old semantic links (`s.purge_path`, `sync.py:241-242`) and stamped at once
  (`s.mark_tracked(str(ap), ap.stat().st_mtime)`, `sync.py:244`). The GMD batch (`:254`), tldr,
  `.pseudo`, ADR / markdown semantics (`:312`) and the bulk Python semantic pass (`:330`) run
  AFTER it, over `touched_existing`. The mtime gate (`sync.py:217-227`) then skips any file whose
  stamp equals its disk mtime. GMD paths are not stamped by `_sync_paths` at all.
- So a split that commits the per-file step and then stops before the semantic steps leaves files
  stamped with their semantic links purged, and the next sync skips them: silent semantic loss
  (nb23-3; the same shape as `project_sync_mtime_gate_strands_docs`). At HEAD a crash rolls the
  whole sync back, but a CANCEL already commits stamped files without semantics, because the
  `with` block exits normally. R4 closes both.
- **bug-093's op-start log line.** The watch `_flush` (`daemon.py:3000`) logs only AFTER the sync,
  through `_watch_flush_line` (`daemon.py:4666`). A wedged flush therefore leaves no line saying
  what it started. The bug-093 row lists this as still open, and no task owned it (nb23-4).
{#why-body}

## Requirements {#requirements}

1. **R1 One transaction per step.** `_sync_paths` takes a REQUIRED `bind` and runs through 23.1's
   `bounded_steps` (23.1 [[task-23.1-queue-and-drain#r10-contract]]):
   - per-file pass: one file per step (`batch=1`), each step its own `bind` hold,
     `batch_transaction`, `deferred_links` scope and in-transaction fragment flush (23.1 R1.3);
   - the GMD batch: one step (unchanged behaviour, it stamps nothing in `_sync_paths`);
   - tldr: one step;
   - the ADR map build: one step;
   - `.pseudo` and `.md` semantics: one file per step;
   - Python semantics: records built in `prepare` (off the lock), applied by `bulk_apply_records`
     in steps of `RMX_SYNC_SEMANTIC_BATCH` records (default 50);
   - the stamp step(s): R4.
   The lock is released only between steps, so never inside a transaction. {#r1}
2. **R2 Partition bound per step.** Each step binds the owner store's project partition by NAME
   through `bind`; no step relies on the binding at rest. {#r2}
3. **R3 Callers.** The three daemon sites drop their outer `with d._store_lock:` and pass
   `daemon_bind(d)`; the watcher's pre-flush repair keeps its own single hold. Non-daemon callers
   pass `serial_bind(store)`, which binds the same way with a process-local lock. The parameter is
   required; there is no default that skips binding (`feedback_main_path_must_exercise_core_mechanisms`).
   {#r3}
4. **R4 The stamp is written in the file's LAST step (nb23-3, #t9-fixes).** {#r4}
   - The per-file step does NOT call `mark_tracked`. It records the disk mtime it read in an
     in-memory `pending_stamps: dict[path, mtime]` for that sync.
   - A file's stamp is written in the same transaction as the LAST step that still owes it work:
     for a `.py` file with `semantic=True`, the Python-semantics step whose chunk holds its record;
     for an `.md` / ADR / `.pseudo` file, its semantics step; for any other file (no later step
     owes it anything), a stamp step right after the per-file pass, one `bulk_mark_tracked`
     (`store.py:6118`) per chunk of `RMX_SYNC_SEMANTIC_BATCH` paths.
   - So a crash, a `cancel` or a `budget_s` stop at ANY point leaves every file whose semantics
     did not commit UNSTAMPED, and the next sync re-ingests and re-applies it in full (its stamp
     differs from its disk mtime). Nothing is stamped "done" while a later step still owes it work.
   - `cancel_check` is `bounded_steps`' `cancel`. The docstring states the visibility rule: between
     a file's per-file step and its last step, a reader can see the file re-ingested without its
     semantic links. That window closes when the last step commits, or on the next sync after a
     crash; it is never permanent.
5. **R5 Report unchanged.** The returned report keys (`added`, `updated`, `purged`, `touched`,
   `cancelled`, `vector_delete_failed`) and the `append_sync_log` line keep their meaning; the run's
   `holds` and `max_hold_s` are added. {#r5}
6. **R6 The comment at `sync.py:182-190` is rewritten** to state the new rule: one transaction per
   step, the lock released only between steps, the stamp written in the file's last step. {#r6}
7. **R7 bug-093's op-start log line (nb23-4).** The watch `_flush` logs `watch flush start: N
   files, roots=[<owner roots>]` through `Daemon._log` BEFORE the first hold of the flush (before
   the pre-flush repair's hold too). The existing completion line is unchanged. `_op_sync_files`
   and `_op_sync_since` log the same shape (`sync_files start: …`, `sync_since start: …`). After
   this task the bug-093 row's open items are both closed by 23.3 (the docs step updates the row).
   {#r7}

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
5. **A stop before the semantic steps loses nothing (nb23-3).** Fixture: 5 changed files with
   semantics (3 `.py` with docstring keywords, 1 ADR `.md`, 1 `.pseudo`), all previously synced.
   Three runs, each from the same starting copy:
   - (a) a spawned child `os._exit(137)`s after the 5 per-file steps commit and before any
     semantic step;
   - (b) `cancel()` turns true at the same point, in-process;
   - (c) `budget_s` runs out at the same point.
   After each, a fresh `Store` shows none of the 5 files stamped at its new mtime, and the next
   full sync re-applies the semantics of all 5: the catalog's entities, links, evidence and
   fragment rows then equal those of an uninterrupted sync of the same fixture (AC-6's row diff).
   Mutation: `mark_tracked` back in the per-file step FAILS (the next sync skips the 5 files and
   their semantic links are missing from the diff). {#ac-5}
6. **Same graph.** The 5-file sync's entities, links and fragments equal those of the HEAD code on
   the same fixture (row diff), so chunking changed holds, not results. {#ac-6}
7. **Existing sync tests** (`tests/test_sync_semantic_bulk.py` and every test that calls
   `sync_files` / `sync_since` / `flush_queue`) pass with `serial_bind` or `daemon_bind` passed.
   {#ac-7}
8. **Op-start line (nb23-4).** A watch flush on a sandboxed daemon whose first `bind` hold is
   blocked by a competitor holding `_store_lock`: while the flush waits, the daemon's `rmxd.log`
   (in the tmp root) already holds `watch flush start: 5 files, roots=[…]`, and the completion
   line follows after the competitor releases. Mutation: log the start line after the first hold
   is taken FAILS (the line is absent while blocked). {#ac-8}

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

## Revision round 2 (2026-10-14) {#rev-round-2}

| finding / decision | answered at |
|---|---|
| nb23-3 (stamp before semantics; AC-5 asserted the loss), #t9-fixes "23.3 stamps a file only after its semantic pass" | [[#why]] (round-2 facts), [[#r1]], [[#r4]], [[#ac-5]] |
| nb23-4 (bug-093 op-start line unowned), #t9-fixes "takes bug-093's op-start log line" | [[#r7]], [[#ac-8]] |
| ns17-2 / 23.1 contract names (`bounded_steps`, `batch_transaction`) | [[#r1]] |
