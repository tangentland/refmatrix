---
gmd: "0.1"
id: task-23.3-sync-between-file-yield
title: "Task 23.3: _sync_paths yields the writer between files, through transaction boundaries and the bind seam (bug-093's open half)"
tags: [task, sync, watch, lock, yield, bug-093, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-11-09
---

# Task 23.3: the between-file yield in `_sync_paths` {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending (**revision round 6, 2026-11-09**: freshness fold of
> [[bsd-plan23-3-5-freshness-62a2465]] (b1, s1, m1, m4): each GMD document is its own
> `bounded_steps` step and AC-4b counts its writes; all FIVE daemon sync sites plus `cli.py`'s
> `flush_queue` caller; facts re-stamped at HEAD `2a4448b`; R9 measures the per-file batch
> against pre-registered bands; see [[#rev-round-6]]. Earlier: revision round 5, 2026-10-14: nm23-r4-3, see [[#rev-round-5]]; round 3:
> ns23-r3-3, see [[#rev-round-3]]; round 2: nb23-3 and nb23-4, see [[#rev-round-2]])
> Depends on: 23.1 (`bounded_steps`, `bind`), 23.2 (recorder), 23.0 (sandbox), and bug-185's
> bulk GMD ingest ([[task-bug185-bulk-gmd-ingest]], merged after plan-26; AC-4b needs it).
> Build order (round 6): 3.7 → bug-178 → plan-26 → bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5.

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
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns23-r3-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#nm23-r4-3]]
rel: depends-on -> [[task-bug185-bulk-gmd-ingest]]
rel: derives-from -> [[bsd-plan23-3-5-freshness-62a2465]]

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

Added in revision round 3, re-read at HEAD `5a8bf29`:
- **The outer lock is today's only sync serializer** (ns23-r3-3). The watcher's `_flush`
  (`daemon.py:3000`), `_op_sync_files` (`:3338`) and `_op_sync_since` (`:3707`) each hold
  `_store_lock` for the whole sync, so two syncs never interleave. `daemon.py` has no other sync
  mutex (its other plain lock, `_async_lock` at `:700`, guards async-op bookkeeping). Once R3
  drops the outer hold, a watch flush and a git post-commit `sync_since` over the same
  just-edited file would interleave at step granularity: both purge and re-ingest it, then both
  apply its semantics.
- **Semantic evidence is a plain INSERT.** `ingest_records.apply_record` (`ingest_records.py:323`)
  and `bulk_apply_records` (`:461`) write evidence through `Store.add_evidence` (`store.py:5267`,
  a plain `INSERT INTO linkage_evidence`; the table has no unique key). A semantic step applied
  twice therefore duplicates its evidence rows (bug-106's shape on the sync path).

Re-stamped in revision round 6 (m1) at HEAD `2a4448b` (`src/` unchanged since `9f09e89`, 0.80.3;
[[bsd-plan23-3-5-freshness-62a2465#drift]]). The line numbers above, from `b1c4324` / `3357c44` /
`5a8bf29`, are superseded by this table. Every symbol still exists, and `_sync_paths`' body has
the same shape.

| symbol | HEAD line |
|---|---|
| `_sync_paths`; outer `transaction()+deferred_links()`; purge + `mark_tracked`; GMD batch; `bulk_apply_records` | `sync.py:147`; `:191`; `:241-244`; `:254`; `:330` (unchanged) |
| the "does not yield" comment; mtime gate; `.md` semantics | `sync.py:176-190`; `:215-224`; `:309-311` |
| watch `_flush` (its hold) | `daemon.py:3158` (`:3177`) |
| `_op_flush_queue` (hold); `_op_flush_queue_async`'s runner (hold) | `daemon.py:3453` (`:3457`); `:3466-3497` (`:3482`) |
| `_op_sync_files` (hold); `_op_sync_since` (holds) | `daemon.py:3537` (`:3543`); `:3906` (`:3916`, `:3926`) |
| `_watch_flush_line`; `_async_lock` | `daemon.py:4806`; `:773` |
| non-daemon callers | `watch.py:170`; `cli.py:8727` (`sync_since`), `:8743` (`flush_queue`), `:8747` (`sync_files`) |
| `apply_record` / `bulk_apply_records` evidence writes; `Store.add_evidence`; `bulk_mark_tracked` | `ingest_records.py:323` / `:461`; `store.py:5577`; `:6447` |

- **Five daemon sites, not three (s1).** `_op_flush_queue` (reached by the Stop hook through
  `rmx sync --flush-queue`) and `_op_flush_queue_async`'s runner thread `rmxd-async-flush`
  (reached by every PostToolUse edit through `--async`) also call `flush_queue → _sync_paths`
  under an outer `with d._store_lock:`. Both date from 2026-05-16. The runner is a bare thread
  with no `_inflight_ops` entry, so after 23.5 R4 it would be reported as "untracked thread
  rmxd-async-flush".
- **The GMD batch is the measured holder (b1).** One `ingest_gmd_paths` call on one document
  holds 19-40 s live (`IMPRESSIONS.md`, 219 anchors: 39.5 s; the 23.5 spec: 19.2 s). The per-file
  pass that rounds 1-5 split is ≤ 3 s per `.py` file
  ([[bsd-plan23-3-5-freshness-62a2465#p-gmd-cost]]). Each of 2026-11-09's four longest windows
  was one GMD re-ingest, with the other syncs waiting behind it
  ([[bsd-plan23-3-5-freshness-62a2465#p-holder]]; bug-185).
{#why-body}

## Requirements {#requirements}

1. **R1 One transaction per step.** `_sync_paths` takes a REQUIRED `bind` and runs through 23.1's
   `bounded_steps` (23.1 [[task-23.1-queue-and-drain#r10-contract]]):
   - per-file pass: `RMX_SYNC_FILE_BATCH` files per step (the default is chosen by [[#r9]]'s
     measurement, not fixed at `1` by fiat), each step its own `bind` hold,
     `batch_transaction`, `deferred_links` scope and in-transaction fragment flush (23.1 R1.3);
   - the GMD batch (round 6, b1): ONE DOCUMENT PER STEP, not one step for the whole batch.
     `prepare` (off the lock) parses every touched GMD path and builds the batch's name table.
     Then one step per document runs pass 1 (doc row + bulk node rows), and one step per
     document runs pass 2 (bulk anchor concepts + links, then the `gmd_content_hash` stamp). The
     in-memory `eid_by_name` table carries ids already committed by earlier steps, so a
     `[[doc-id#anchor]]` between two documents of the same sync resolves exactly as HEAD's
     two-pass call does. A stop between steps leaves a document without its hash, so the next
     sync's resume gate re-ingests it, as a crash does today. `_sync_paths` still stamps no GMD
     path. Each step's write count is flat in the document's anchor count because bug-185
     ([[task-bug185-bulk-gmd-ingest]]) makes the writes bulk. AC-4b asserts both;
   - tldr: one step;
   - the ADR map build: one step;
   - `.pseudo` and `.md` semantics: one file per step;
   - Python semantics: records built in `prepare` (off the lock), applied by `bulk_apply_records`
     in steps of `RMX_SYNC_SEMANTIC_BATCH` records (default 50);
   - the stamp step(s): R4.
   The lock is released only between steps, so never inside a transaction. {#r1}
2. **R2 Partition bound per step.** Each step binds the owner store's project partition by NAME
   through `bind`; no step relies on the binding at rest. {#r2}
3. **R3 Callers (round 6, s1: five daemon sites).** {#r3}
   - **The five daemon sites:** the watch `_flush` (`daemon.py:3158`), `_op_flush_queue`
     (`:3453`), `_op_flush_queue_async`'s runner (`:3466-3497`), `_op_sync_files` (`:3537`) and
     `_op_sync_since` (`:3906`). Each one:
     - DROPS its outer `with d._store_lock:`;
     - takes `_sync_mutex` (R8);
     - passes `daemon_bind(d)`;
     - logs its R7 start line.
     The watcher's pre-flush repair keeps its own single hold.
   - **Why the outer hold must go, not wrap the new call.** `_FairLock` is not re-entrant. A site
     that keeps `with d._store_lock:` and passes `daemon_bind(d)` inside it deadlocks on the
     first step's `bind`: 23.2's `LockDeadlock` in tests, a hang on the live store. Binding
     outside `_sync_mutex` is not allowed either: a flush would then interleave step by step with
     a watch flush, which is ns23-r3-3's duplicate-evidence hazard. There is no third option, so
     the spec names this one. AC-10 asserts it per site.
   - **The async runner is a named holder.** `rmxd-async-flush` runs its whole flush inside
     `Daemon._inflight("sync")`, 23.5 R4's context manager, whose name list already has `sync`.
     So 23.5 R4's `writer_holder` names it and never reports "untracked thread". 23.3 and 23.5
     run in parallel: whichever lands first adds `Daemon._inflight` over `_inflight_ops`, and
     the other uses it. No second registry is added.
   - **Non-daemon callers** (`watch.py:170`; `cli.py:8727`, `:8743` (`flush_queue`), `:8747`)
     pass `serial_bind(store)`, which binds the same way with a process-local lock.
   - The parameter is required. There is no default that skips binding
     (`feedback_main_path_must_exercise_core_mechanisms`).
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
6. **R6 The comment at `sync.py:176-190` (HEAD `2a4448b`) is rewritten** to state the new rule: one transaction per
   step, the lock released only between steps, the stamp written in the file's last step. {#r6}
7. **R7 bug-093's op-start log line (nb23-4).** The watch `_flush` logs `watch flush start: N
   files, roots=[<owner roots>]` through `Daemon._log` BEFORE the first hold of the flush (before
   the pre-flush repair's hold too). The existing completion line is unchanged. `_op_sync_files`
   and `_op_sync_since` log the same shape (`sync_files start: …`, `sync_since start: …`). After
   this task the bug-093 row's open items are both closed by 23.3 (the docs step updates the row).
   Round 6 (s1): `_op_flush_queue` and the async runner log `flush_queue start: …` and
   `flush_queue_async start: …` in the same shape, before their first hold.
   {#r7}
8. **R8 One sync at a time per store, and idempotent semantic evidence (ns23-r3-3).** {#r8}
   - **`sync_mutex`.** `Daemon._sync_mutex` is a plain `threading.Lock`, NOT `_store_lock`. The
     five daemon sites (watch `_flush`, `_op_flush_queue`, `_op_flush_queue_async`'s runner,
     `_op_sync_files`, `_op_sync_since`; round 6, s1) hold it across ONE
     whole `_sync_paths` run (every `bounded_steps` step of it). A second sync waits for it; it
     does not coalesce (a waiting sync re-stats its own paths when it starts, and the mtime gate
     skips what the first one already applied and stamped). `serial_bind(store)` callers get the
     same guarantee from a process-local mutex owned by `serial_bind`.
   - **Lock order.** `_sync_mutex` is taken BEFORE any `bind` hold and is never acquired while
     `_store_lock` is held, so it cannot deadlock against the writer. Between steps the writer is
     still released to every NON-sync op (AC-1 is unchanged); only another sync waits.
   - **R7's start line** is logged before the mutex is taken, so a sync blocked behind another
     sync also leaves its `start` line.
   - **Evidence insert-if-absent.** `apply_record` and `bulk_apply_records` write evidence through
     23.1's `Store.add_evidence_if_absent` ([[task-23.1-queue-and-drain#r10-contract]], same
     signature and `facts.log` rule), not the plain `add_evidence`. With the mutex this is a
     second guard: a semantic step that is re-applied (a re-sync after a stop, R4) adds no
     duplicate evidence row. `add_evidence` itself is unchanged for its other callers.
9. **R9 The per-file batch is measured before it is fixed (round 6, m4).** At 23.1 R1.3, every
   per-file step commits and flushes fragments inside its own transaction, so a 100-file
   post-commit diff at `batch=1` costs ≥ 100 commits on a ~920 MB catalog. Before GREEN is
   accepted:
   - sync a 100-file fixture (60 `.py` with docstring keywords, 30 `.md`, 10 GMD documents of
     20-200 anchors) at HEAD and at `RMX_SYNC_FILE_BATCH` ∈ {1, 5, 10, 25};
   - record for each run: the hold count, `max_hold_s`, and the total wall time (median of 3) in
     the implementation summary.

   The bands below are pre-registered here, before the run
   ([[feedback_go_no_go_ranges_not_predrop]]). `ratio` = new total wall ÷ HEAD total wall.
   - **`batch=1` with ratio ≤ 1.25:** the default is 1.
   - **`batch=1` with ratio over 1.25:** the default is the smallest batch in {5, 10, 25} whose
     ratio is ≤ 1.25 and whose `max_hold_s` is ≤ 3 s.
   - **No batch ≤ 25 meets both:** STOP and report to the user with the table. The bands are
     not widened.

   The GMD steps are one document each in every band ([[#r1]]). The batch setting applies to
   the per-file pass only.
   {#r9}

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
   - **AC-4b GMD documents (round 6, b1).** Fixture: GMD documents with 50 and with 200 anchors,
     both carrying the SAME number of `rel:` lines (round 7: 10, as bug-185's AC-3 fixtures).
     - Re-syncing each executes the same number of statements per hold (± 2), counted by 23.2's
       recorder, and 0 single-row entity / concept upserts (23.2 R3's counter).
     - Each document is its own pass-1 step and its own pass-2 step: the recorder's hold count
       is `2 × documents` for the GMD phase.
     - Two GMD documents that link each other, both new in the same sync, resolve the links in
       both directions (AC-6's row diff against HEAD).
     - Mutations, each must FAIL: the GMD batch back to one step for all documents (hold count
       1); the per-row pass-1 `upsert_entity` loop restored (statements scale with anchors,
       single-row counter > 0).
     - RED at HEAD: the single-row upsert counter is > 0 and scales with the anchor count (200
       vs 50 anchors; the exact count depends on the fixture's anchor naming, since each
       multi-part name adds variant upserts, round 7). Needs bug-185 merged to go GREEN
       ([[task-bug185-bulk-gmd-ingest#ac-3]]); the steps wrap bug-185's per-document entry
       points ([[task-bug185-bulk-gmd-ingest#r7]]).
     {#ac-4b}
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
   the same fixture (row diff), so chunking changed holds, not results. The same diff also runs
   on [[#r9]]'s 100-file fixture at the chosen batch. The summary records R9's holds and wall
   table (round 6, m4). {#ac-6}
7. **Existing sync tests** (`tests/test_sync_semantic_bulk.py` and every test that calls
   `sync_files` / `sync_since` / `flush_queue`) pass with `serial_bind` or `daemon_bind` passed.
   The flush-queue tests are named here (round 6, s1):
   - `tests/test_sync_and_extras.py::test_queue_enqueue_and_flush`;
   - `tests/test_memory_only_guard.py::test_sync_empty_flush_stays_quiet_on_the_global_store`;
   - `tests/test_deferrals_clean.py`'s `flush_queue` parametrization (no `yield_lock` /
     `yield_every` parameter; `bind` is not one of those).

   HEAD has no daemon-level test of `_op_flush_queue` / `_op_flush_queue_async`. AC-10 adds
   them. {#ac-7}
8. **Op-start line (nb23-4).** A watch flush on a sandboxed daemon whose first `bind` hold is
   blocked by a competitor holding `_store_lock`: while the flush waits, the daemon's `rmxd.log`
   (in the tmp root) already holds `watch flush start: 5 files, roots=[…]`, and the completion
   line follows after the competitor releases. Mutation: log the start line after the first hold
   is taken FAILS (the line is absent while blocked). {#ac-8}
9. **Two concurrent syncs (ns23-r3-3).** The same 3 changed files (2 `.py` with docstring
   keywords, 1 ADR `.md`) synced twice at once on a recorded daemon: a watch `_flush` and an
   `_op_sync_files` started from two threads, with the race FORCED, not hoped for (nm23-r4-3):
   - **The barrier.** Sync A's first step's `apply` (through a test seam on the step) blocks on
     an event until sync B is visibly waiting at its first contention point, then proceeds; a
     10 s deadline turns a missed barrier into a test failure, never a hang. "Visibly waiting"
     is read from the real objects, not from timing: with `_sync_mutex` present, B's thread is
     inside the mutex's `acquire` (the mutex is wrapped in a pass-through that sets an event on
     `acquire` entry); without it (the mutant), B's `bind` has a ticket in the recorder's
     `_FairLock` waiter queue (`len(lock._waiters) >= 1` while A holds the lock). Either
     signal releases A. So B is queued before A's first release in every run, and if the
     mutex is gone B wins the lock at that release.
   Afterwards the catalog's entities, links,
   evidence and fragment rows equal ONE sync's (AC-6's row diff), with no duplicate
   `linkage_evidence` row (`SELECT entity_id, linkage_id, concept_id, file, line, count(*) …
   HAVING count(*) > 1` returns 0). The recorder shows the two syncs' steps never interleave
   (every step of one precedes every step of the other), while a third, non-sync competitor still
   wins between consecutive steps. Mutations, each must FAIL: no `_sync_mutex` (steps interleave;
   duplicate evidence rows); `_sync_mutex` taken inside the first `bind` hold (23.2's
   `LockDeadlock`, or the competitor never wins); `bulk_apply_records` back on the plain
   `add_evidence` together with the mutex removed (duplicate rows).
   - **Second pair (round 6, s1).** The same barrier and assertions, with a
     `flush_queue_async` runner as sync A and a watch `_flush` as sync B, over the same 3 files
     (enqueued for the flush). The steps of the two syncs never interleave, and there are no
     duplicate evidence rows. Mutation: the runner bound outside `_sync_mutex` FAILS (its steps
     interleave with the watch flush's).
   {#ac-9}
10. **AC-10 Every daemon sync site drops its outer hold (round 6, s1).** For each of the five
    sites ([[#r3]]), on a recorded daemon: the site runs a 3-file sync to completion, and a
    competitor wins between its steps.
    - The `flush_queue_async` runner's thread has an `_inflight_ops` entry named `sync` for the
      whole flush.
    - With 23.5 R4 merged, `writer_holder` names it `sync`, never "untracked thread
      rmxd-async-flush".
    - An AST check over `daemon.py`: no `with <x>._store_lock` encloses a call to
      `flush_queue` / `sync_files` / `sync_since` / `_sync_paths`.
    - Mutations, each must FAIL: the outer `with d._store_lock:` kept in `_op_flush_queue` (23.2's
      `LockDeadlock` on the first `bind`, not a hang); the same in the async runner; the
      runner's `Daemon._inflight("sync")` removed (no `sync` entry while it holds).
    {#ac-10}

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

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]].

| finding / decision | answered at |
|---|---|
| ns23-r3-3 (two `_sync_paths` runs interleave per step; plain `add_evidence` in `bulk_apply_records`) | [[#why]] (round-3 facts), [[#r8]] (`_sync_mutex`, lock order, insert-if-absent evidence), [[#ac-9]] |
| 23.1 contract names (`add_evidence_if_absent`) | [[#r8]]; [[task-23.1-queue-and-drain#r10-contract]] |

## Revision round 5 (2026-10-14) {#rev-round-5}

Source: [[bsd-plan23-17-spec-rereview-r4-878647c]].

| finding / decision | answered at |
|---|---|
| nm23-r4-3 (AC-9 does not force the race; the no-mutex mutant can pass if A drains first) | [[#ac-9]] (a barrier: A's first step waits until B is in `_sync_mutex.acquire` or holds a `_FairLock` waiter ticket) |

## Revision round 6 (2026-11-09) {#rev-round-6}

Source: [[bsd-plan23-3-5-freshness-62a2465]], the pre-implementation freshness review of 23.3 and
23.5 at `62a2465` (DIRTY 1B/2S/4M; this spec's findings are b1, s1, m1, m4; s2, m2, m3 are
23.5's, [[task-23.5-read-path-and-holder-bounds#rev-round-13]]). Code re-read at HEAD `2a4448b`.
No user decision remained: the report's fixes are adopted. The round-5 table above is unchanged
history.

| finding | answered at | rationale |
|---|---|---|
| b1 (23.3 left the measured bug-177 holder, the GMD batch, as one unbounded step) | [[#why]] (round-6 facts), [[#r1]] (one document per step: pass 1 and pass 2 each one step per document, name table built in `prepare`), [[#ac-4b]]; bulk writes in [[task-bug185-bulk-gmd-ingest]] (bug-185) | per-file yields bounded work that already took ≤ 3 s; the 19-40 s document stayed one hold. Bounding it needs both the step boundary (this task) and flat writes per step (bug-185) |
| s1 (three daemon `_sync_paths` sites named, HEAD has five; two are hook-driven) | [[#why]] (round-6 facts), [[#r3]] (five sites + `cli.py:8743`; outer hold dropped; the deadlock and the interleave both named; the async runner under `Daemon._inflight("sync")`), [[#r7]], [[#r8]], [[#ac-7]], [[#ac-9]] (second pair), [[#ac-10]] | with `bind` required and `_FairLock` not re-entrant, an unnamed site either deadlocks or interleaves; the spec now picks the one safe shape |
| m1 (facts a month stale) | [[#why]] (re-stamp table at `2a4448b`), [[#r6]] | line drift only; symbols and shape unchanged |
| m4 (`batch=1` per-file commit cost unmeasured) | [[#r9]] (100-file fixture, holds + wall, pre-registered bands), [[#r1]] (`RMX_SYNC_FILE_BATCH`), [[#ac-6]] | the batch is chosen from bands written before the run, not fixed at 1 by fiat |

rel: derives-from -> [[bsd-plan23-3-5-freshness-62a2465]]
rel: derives-from -> [[bsd-plan23-3-5-freshness-62a2465#b1]]
rel: derives-from -> [[bsd-plan23-3-5-freshness-62a2465#s1]]
rel: derives-from -> [[bsd-plan23-3-5-freshness-62a2465#m1]]
rel: derives-from -> [[bsd-plan23-3-5-freshness-62a2465#m4]]

## Revision round 7 (2026-11-09) {#rev-round-7}

Source: [[bsd-bug185-spec-r1-da67220#m5]], the bug-185 spec review r1 (its m5 is about this
spec's composition with bug-185). Only [[#ac-4b]] changed; the round-6 table above is unchanged
history.

| finding | answered at | rationale |
|---|---|---|
| m5 (b) AC-4b quoted the live file's "854" for a synthetic fixture | [[#ac-4b]] ("> 0, scaling with anchors") | 854 is the live `IMPRESSIONS.md`'s call count including `add_concept`'s variant upserts; a generated fixture's count depends on its anchor naming |
| m5 (c) AC-4b inherits the rel-count condition | [[#ac-4b]] (both fixtures carry the same 10 `rel:` lines) | bug-185 makes rel edges bulk too ([[task-bug185-bulk-gmd-ingest#r2]] step 5), but an equal rel count keeps the flatness claim independent of that choice |
| m5 (a) which task cuts the per-document pass-1 / pass-2 seam | [[#ac-4b]]; [[task-bug185-bulk-gmd-ingest#r7]] | bug-185 provides `gmd_prepare` / `gmd_pass1_document` / `gmd_pass2_document`; [[#r1]]'s per-document steps wrap them and add nothing inside |

rel: derives-from -> [[bsd-bug185-spec-r1-da67220#m5]]
