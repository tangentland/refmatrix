---
gmd: "0.1"
id: task-23.1-queue-and-drain
title: "Task 23.1: one bind/recorder core with three front-ends (durable queue drain, non-consuming tail, bounded steps), offsets committed in the batch transaction, and one tick registry; learn_queue re-based on it"
tags: [task, queue, drain, tail, lock, partition, exactly-once, tick, bug-098, bug-099, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-14
---

# Task 23.1: queue, tail, bounded steps, and the tick registry {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 23.0 (test sandbox), 23.2 (hold + write-count recorder)
> Blocks: 23.3; 16.6's Wave 1 slice; 22.2 (and so 22.5, 22.3); 17.1; 19.2
> Not gated on 23.4: the `bind` seam serves either verdict (decision-log #s-2).

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: implements -> [[plan-review-2026-10-14#t2-fixes]]
rel: implements -> [[plan-review-2026-10-14#t8-amendments-body]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81#findings]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2#s-1]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2#s-3]]
rel: related-to -> [[project_bug098_writer_partition_race]]
rel: related-to -> [[exploration-storage-concurrency-redesign#option-a]]

## Facts at HEAD `b1c4324` this spec builds on {#facts}

- `daemon._drain_learn_queue` (`daemon.py:2079`) takes `_store_lock` ONCE PER coalesced entry
  (`test_the_drain_yields_the_writer_lock_between_entries` pins it), with a whole-tick deadline
  `LEARN_DRAIN_BUDGET_S` (5 s, `:647`), a shutdown stop, fatal-invalidation handling (mark repair,
  arm deferred exit, stop) and a re-append `requeue` of the remainder.
- `learn_queue.read_rotated` (`learn_queue.py:92`) parses, coalesces (UNION of hits per pattern),
  bounds (newest `MAX_QUEUE_LINES` win, overflow counted) and UNLINKS the rotated file BEFORE any
  entry is applied. Nothing reads an orphaned `*.draining` file. bug-099 is this silent loss.
- `_runner` (`daemon.py:2035`) drains only learn, then flushes fragments under the lock.
- `Store.with_partition` (`store.py:1911`) mutates the ONE writer Store's binding;
  `_partition_keeping_yield` (`daemon.py:3313`) is the only yield that restores it (bug-098).
  `_learn_grep_hits` (`daemon.py:4295`) writes into whatever is bound at rest.
- `Store.transaction` (`store.py:4233`) flushes dirty fragments AFTER `COMMIT` and only prints a
  failure. On the DuckDB backend fragments are rows of the `bitmap_fragments` table
  (`_flush_fragments_duckdb`), keyed by the BOUND `partition_id`, so they can be written inside the
  batch's own transaction.
- `replica_merge` keeps the A-side row on conflict for tables without `updated_at`.
- `rmx learn status` (`cli.py:7292`) runs in the CLI and shows the queue depth only when learning is
  OFF; the overflow reaches only the daemon's `rmxd.log` line.
{#facts-body}

## Requirements {#requirements}

### R1 One core: `bind`, the batch transaction, the recorder hook {#r1}

`src/refmatrix/bounded.py` holds one core that all three front-ends (R3, R4, R5) run through.

1. **`bind(partition_name) -> ContextManager[Handle]`** is supplied by the store's owner, never
   built by a consumer (23 #b-1, d2b). The daemon's implementation, `daemon_bind(d)`:
   `with d._store_lock:` then, INSIDE that hold, `with st.with_partition(name):` and yield the
   store. The binding is entered after the lock is taken and exited before it is released, in one
   `with`; no binding is ever held across a release. Under Option A (23.4 GO) `bind` returns a
   per-op cursor handle and no consumer's `apply` changes.
2. **Batches carry partition NAMES, never ids** (r10 #s-1's id-1 fallback). `bind` resolves the
   name and raises on an unknown one; there is no fallback to partition 1. A batch never spans two
   partitions: the front-end cuts a batch at every partition change.
3. **One transaction per hold.** Inside the bound handle the core runs `with handle.transaction():`
   → `apply(handle, batch)` → the dirty fragments are flushed INSIDE the transaction (DuckDB
   `bitmap_fragments`) → the front-end's offset row is written (R3, R4) → `COMMIT`. Relational
   rows, bitmap fragments and the offset are atomic (d2a + its amendment). If anything raises, the
   transaction rolls back, AND the in-memory fragment cache entries the batch dirtied are dropped so
   they reload from the database (a rolled-back batch must not leave bits in `_fragments` that the
   catalog does not hold). The harness refuses the SQLite backend with an error naming it.
4. **`prepare(batch)`** (optional) runs OFF the lock before each hold: re-stats, file reads, record
   building (16.6 R4's pre-step; 23.3's semantic records). It must not touch the writer
   connection.
5. **Every run returns** `RunResult{applied, batches, holds, max_hold_s, alarms, stopped, failed,
   dead_lettered, overflow, malformed, pending, fragment_flush_failures}`, where
   `stopped ∈ {"", "budget", "shutdown", "store-invalid", "error"}`.

### R2 Stop paths, error policy, and the hold alarm (23 #s-1) {#r2}

Every front-end takes the same keyword set, all named:
- `batch` (default **1** event per hold; a consumer raises it explicitly);
- `budget_s` (whole-run budget, checked before each hold; the remainder stays pending);
- `cancel()` (checked before each hold; the daemon passes `d._shutdown_event.is_set`);
- `on_error(exc, batch) -> "dead-letter" | "stop" | "fatal"`. `fatal` is the daemon's classifier
  for `Daemon._is_fatal_invalidation`: mark repair, arm the deferred exit, stop; the failed batch's
  transaction is rolled back and its offset NOT advanced. `dead-letter` appends the batch's raw
  lines and the error to `<queue>.deadletter.jsonl`, counts it (`dead_lettered`, persisted in R6),
  and advances the offset in its own transaction: no batch is silently skipped and none blocks the
  queue forever. `stop` leaves the batch pending. Default: `stop`;
- `hold_alarm_s`: a hold longer than this logs a warning with the batch size and the R3 counts of
  23.2's recorder when installed. It is an ALARM, never a stop and never a guarantee (23 #s-5);
  consumers assert write counts through 23.2;
- `finalize(handle, summary)` (optional): run ONCE after the last batch, under its own hold through
  `bind`, inside its own transaction (23 #b-3: 22.2's one Lance delete per kind, not per batch). For
  R3/R4, every batch transaction sets `finalize_pending=true` on its offset row and finalize's
  transaction clears it; a run that starts with the flag set runs finalize FIRST. For R5 (no
  durability), finalize runs in a `finally` after any stop.
- **Requeue is resume-from-offset.** The remainder of a stopped run stays in its segment past the
  committed offset; nothing is re-appended (a re-append doubles the remainder on a crash between the
  append and the unlink).

### R3 `BoundedQueue` + `drain(queue, …)`: the durable, coalescing, consuming front-end {#r3}

1. `BoundedQueue(path, *, key_fn, merge_fn, max_lines)`: `key_fn` and `merge_fn` are REQUIRED
   (23 #s-2). `merge_fn(acc, ev) -> acc` states the merge: UNION (learn), SUM (counts), MAX (times).
   There is no last-wins default. The key always includes the event's partition name.
2. **Append** is one `O_APPEND` JSON line with no lock and no socket (today's `enqueue`).
3. **Segments.** A drain rotates the live file to a NEW segment `<name>.<seq>.seg` (never
   overwritten) and keeps it until its LAST offset commits; only then is it unlinked. At daemon boot
   every segment, and any legacy `*.draining` file left by pre-23.1 code, is adopted and resumed
   from its committed offset (bug-099, d2d).
4. **Offsets (d2a).** A catalog table `queue_offsets(queue, segment, offset_bytes,
   finalize_pending, PRIMARY KEY(queue, segment))`; each batch writes its row inside R1's
   transaction. The committed offset is the byte position after the last raw line the committed
   batches fully cover.
5. **Coalesce scope.**
   - `scope="window"` (default): a batch coalesces only the raw lines in its own window; the offset
     after the window commits with it. Effects are exactly-once: required for any non-idempotent
     merge (SUM, MAX-with-count).
   - `scope="segment"`: the whole segment is coalesced first (today's learn shape: N greps → M
     patterns), entries are applied per hold, and each hold commits the covered prefix. A crash can
     re-apply an entry whose lines lie past the prefix, so the harness REFUSES `scope="segment"`
     unless the queue is declared `idempotent=True`. Learn's writes are set-bit and
     insert-if-absent evidence, so learn declares it.
6. **Overflow** past `max_lines` drops the OLDEST lines (newest win, today's rule), counts them in
   the run result and in the persisted counter of R6. Never silent.
7. **Exactly-once boundary, stated** (#t8-amendments d2a): it covers what commits in the one DuckDB
   transaction: relational rows, `bitmap_fragments` rows, the offset. Lance writes are not in it;
   a consumer that writes Lance does it in `finalize`, which is re-run while `finalize_pending` is
   set and must be idempotent.

### R4 `TailLog` + `tail(log, …)`: the non-consuming reader (d4a) {#r4}

1. `TailLog(path, *, key_fn, merge_fn)` reads by `(file, offset_bytes)` from the committed offset
   to the LAST COMPLETE NEWLINE; a torn tail from a lock-free appender is left for the next run.
2. It NEVER rotates, unlinks, truncates or rewrites the file (the file is shared with plan-21's
   measurement and is the retained replay source, #t8-amendments d2a). Its offset is a
   `queue_offsets` row (segment = the file name) committed in the batch transaction (R1.3).
3. There is no overflow: a backlog is read in `batch`-line windows until the budget ends.
4. Any future rotation of a tailed log must be segment-aware `(segment, offset)` and must retain
   every segment past the lowest committed offset; plan-23 rotates none.
5. Rows are returned raw. Filtering (for example d8d's pytest-temp-dir predicate) is the
   consumer's `prepare`/`apply`.

### R5 `bounded_steps(items, …)`: in-memory steps with no durability claim {#r5}

For loops over an in-memory list that are not queues (23 #s-3): 17.1's datasets, 22.2's apply plan,
23.3's file chunks. Each step goes through R1 (`bind` per step with the step's partition name, one
transaction, the recorder hook) and R2 (budget, cancel, error policy, alarm, finalize in a
`finally`). Crash recovery is the consumer's (22.2's manifest, 23.3's mtime gate); the docstring
says so.

### R6 The tick registry: one registry, one shared budget (d4a, 23 #s-3) {#r6}

1. `Daemon.tick_registry.register(name, runner, *, kind)`, `kind ∈ {"drain", "tail",
   "bounded_steps"}`, in a fixed registration order. `_runner` calls `tick_registry.run()` where it
   calls `_drain_learn_queue()` today; the periodic fragment flush stays after it, every tick.
2. ONE budget for all registrants together: `LEARN_DRAIN_BUDGET_S` (default 5 s) keeps its name so
   existing tests that patch it still work; each registrant gets what the ones before it left.
3. Start rotates round-robin: a tick starts at the registrant after the one that exhausted the
   previous tick's budget, so no registrant starves.
4. Registrants at the end of 23.1: `learn` (drain). Later: 19.2's fold (tail), 16.6's marks
   (drain). 17.1, 22.2 and 23.3 use `bounded_steps` from their own ops, not the tick.
5. **Persisted counters + a daemon op (23 #s-6).** A catalog table
   `queue_counters(queue, overflow_total, malformed_total, dead_lettered_total, failed_total)` is
   updated in the batch transaction. Daemon op `queue_status` returns, per registrant: pending lines
   (live file + every segment past its committed offset), the four totals, `last_run_at`,
   `last_stopped`, and the store's `fragment_flush_failures` total. `_store_health` keeps
   `learn_queue_pending` and adds `learn_queue_overflow_total`.
6. `rmx learn status` calls `queue_status` through the daemon UNCONDITIONALLY (learning on or off)
   and prints `queued: N`, `overflow (dropped, total): N`, `dead-lettered: N`. With the daemon
   unreachable it prints `queue counters unknown (daemon unreachable)`, never `0`.

### R7 Fragment flush failures are surfaced and retried (#t8-amendments d2a) {#r7}

Inside the harness a fragment flush failure rolls the batch back (R1.3) and is retried with it.
Outside the harness, `Store.transaction`'s post-`COMMIT` flush failure stops being a bare `print`:
it increments `Store.fragment_flush_failures`, keeps the fragments dirty for the periodic flush to
retry, logs to `rmxd.log`, and is reported by `queue_status` and `_store_health`.

### R8 `replica_merge` cannot roll an offset back (#t8-amendments d2a) {#r8}

`replica_merge` merges `queue_offsets` by taking, per `(queue, segment)`, the larger
`offset_bytes` (and `finalize_pending` from that row), and `queue_counters` by elementwise max.
Folded tables carry their own monotone rule (19.2 R6 `memory_usage`, 16.6 R1c sidecar); 23.1 does
not edit them.

### R9 Re-base `learn_queue` on R3, and correct its docstrings {#r9}

1. Learn becomes `BoundedQueue(…, key_fn=pattern+partition, merge_fn=UNION by (file, line),
   max_lines=MAX_QUEUE_LINES, idempotent=True)` drained with `scope="segment"`, `batch=1` (one
   coalesced pattern per hold, the contract `test_the_drain_yields_the_writer_lock_between_entries`
   pins), `budget_s=LEARN_DRAIN_BUDGET_S`, the daemon's fatal classifier, registered as `learn` in
   R6. Its partition is the store's project partition, bound explicitly through `bind`, not
   "whatever is bound at rest".
2. Behaviour that changes, each with its own RED test: the bug-099 loss (R3.3); the remainder is
   left in its segment instead of re-appended (R2); a non-fatal failure is dead-lettered instead of
   dropped after a log line (R2).
3. Every other existing test in `tests/test_learn_queue.py`, `tests/test_learn_broker_bounded.py`
   and `tests/test_learn_toggle_sites.py` passes unchanged. A test whose assertion encodes the old
   behaviour is listed in the implementation summary with its old and new assertion (known:
   `test_the_drain_stops_at_its_budget_and_requeues_the_rest` asserts the log word `requeued`; its
   `pending_lines == 10` assertion stays).
4. The superseded "ONE lock acquisition" text is corrected in the `learn_queue.py` module
   docstring, the `_drain_learn_queue` docstring, the `_runner` comment, and the
   `tests/test_learn_queue.py` module docstring and section header (23 #m-3).

## Acceptance criteria {#acceptance}

Holds and writes are counted by 23.2's `HoldRecorder` on a REAL `_FairLock` installed through
`recorded_daemon`, never by the drain's own return value (23 #s-4).

1. **Holds and yields.** 1,000 events with 1,000 DISTINCT keys, `batch=200`: the recorder counts
   exactly 5 holds, and a competitor queued on the lock before each release wins between EVERY
   consecutive pair (4 ordered wins recorded by the recorder's thread names). Mutation: one hold
   around all batches FAILS. {#ac-1}
2. **SUM coalesce.** 1,000 events over 10 keys with a SUM `merge_fn`, `scope="window"`: the 10
   totals equal the per-key event counts. Constructing a `BoundedQueue` or `TailLog` without
   `merge_fn` raises `TypeError`. Mutation: a last-wins merge FAILS. {#ac-2}
3. **Partition binding (23 #b-1).** Two batches for partition `pa`. Between them a competitor takes
   the lock, enters `with_partition("pb")`, writes one row, and releases WHILE STILL BOUND (the
   bug-098 shape). After the drain, 0 rows of the drain's batches are in `pb` and all are in `pa`.
   An event naming an unknown partition raises; nothing is written to partition 1. Mutation: hoist
   the bind outside the batch loop FAILS. {#ac-3}
4. **Exactly-once across the windows (d2a, 23 #b-2).** A COUNTING `apply` (adds the event count to
   one counter row) over 600 events, `batch=100`. A fault is injected at each of: (a) after
   `apply`, before the offset write; (b) after the offset write, before `COMMIT`; (c) after
   `COMMIT`, before the segment bookkeeping; (d) inside the in-transaction fragment flush; (e) a
   SIGKILL-shaped `os._exit(137)` mid-`apply`. (a), (b), (d) raise in-process; (c) and (e) run the
   drain in a spawned child process (not `rmx`, not a fork of a process holding DuckDB) on the same
   tmp root. After each, a fresh `Daemon` + `Store` drains to completion: the counter equals 600
   exactly, and the fragment cache equals the database's `bitmap_fragments` rows. Mutations, each
   must FAIL: the offset written in its own autocommit after `COMMIT` (double count at (c)); the
   offset written before the batch (loss at (a)); fragments flushed after `COMMIT` (loss at (d));
   the cache not dropped on rollback. {#ac-4}
5. **bug-099 (RED at HEAD).** Enqueue 3 learn records; drain in a spawned child that `os._exit`s
   after the rotate, before any apply; restart. At HEAD: 0 learned rows and 0 pending (the loss).
   After 23.1: 3 patterns applied, 0 pending, no pattern applied twice. A legacy `*.draining` file
   present at boot is adopted and applied. {#ac-5}
6. **Segment scope is refused for non-idempotent queues.** `scope="segment"` on a queue without
   `idempotent=True` raises at construction. {#ac-6}
7. **Stop paths.** Budget: remainder pending, `stopped="budget"`. Shutdown: `cancel()` true →
   nothing applied, all pending. Fatal invalidation: repair marked, deferred exit armed, the failed
   batch not applied and still pending. Non-fatal error: the batch is in the dead-letter file,
   `dead_lettered_total` is 1, the queue moves on. Hold alarm: a hold over `hold_alarm_s` logs the
   alarm with its counts and the run continues. {#ac-7}
8. **Finalize once (23 #b-3).** A 22.2-shaped apply over 5 batches that collects Lance deletes and
   issues them in `finalize`: 23.2's `max_writes_per_run(lance_versions=<kinds>)` passes. A crash
   after the last batch and before finalize: the next run runs finalize first, once. Mutation: the
   delete issued per batch FAILS the per-run count. {#ac-8}
9. **O(1) statements per batch.** A batch of 10 and a batch of 100 events through a bulk `apply`
   execute the same number of statements per hold (± 2, 23.2 R3). A consumer `apply` that loops one
   upsert per event FAILS `max_writes_per_hold`. {#ac-9}
10. **Tail.** A concurrent appender writes 1,000 lines, the last one torn (no newline). The fold
    reads exactly the complete lines; the file's inode, size and bytes are unchanged afterwards;
    the next run picks up the torn line once it is completed. Drop the folded table and reset the
    offset: a re-fold yields identical rows (the drop-and-replay property 19.2 relies on). {#ac-10}
11. **Tick registry.** Three registrants (a drain, a tail, a `bounded_steps` runner), each able to
    use the whole budget: one tick's total registrant time ≤ `LEARN_DRAIN_BUDGET_S` + one hold;
    over 3 ticks every registrant runs at least once; the fragment flush runs every tick. Mutation:
    a per-registrant budget FAILS (the tick takes ~3× the budget). {#ac-11}
12. **Overflow surface.** On a sandboxed daemon (23.0) serving a short tmp socket, overflow the
    learn queue by 7 with learning ON: `rmx learn status` prints `overflow (dropped, total): 7`.
    With the daemon stopped it prints `queue counters unknown (daemon unreachable)`. Mutation:
    print only when learning is off FAILS. {#ac-12}
13. **`replica_merge`.** Two slots whose `queue_offsets` rows differ: the merged row carries the
    larger offset; `queue_counters` carries the elementwise max. Mutation: keep the A-side row
    FAILS when A is older. {#ac-13}
14. **Fragment flush failure is surfaced.** A failing post-`COMMIT` flush in `Store.transaction`
    increments `fragment_flush_failures`, keeps the fragment dirty, and the next periodic flush
    writes it; `queue_status` reports the count. {#ac-14}
15. **Learn tests.** The R9.3 test files pass; the docstrings named in R9.4 no longer say "ONE lock
    acquisition" (`rmx grep -n 'ONE lock acquisition'` on those files returns nothing). {#ac-15}

## Test strategy {#test-strategy}

- Every test runs inside task 23.0's sandbox (d1a/d1b): redirected `$HOME`, global root and
  registry, injected store roots, the refuse guard on, children refused outside the tmp dir.
- In-process `Daemon(root)` + real `Store` on a short `mkdtemp` root (the `test_learn_queue.py`
  `_daemon_with_store` shape), built through 23.2's `recorded_daemon` so the recorder IS
  `_store_lock` from the first op; `daemon.ping` False.
- Faults (c) and (e) run in a spawned Python child that opens its own `Store` after the parent has
  closed its handle; the parent never forks while holding a DuckDB connection.
- Only AC-12 runs `rmx`, against a daemon on the sandbox's tmp socket.
- The 23.0 touches log gains 0 lines for this task's files.
- Logs: `workflow/review-output/pytest-bounded.log`.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 23 #b-1 (no partition rule across yields; bug-098) | [[#r1]] 1-2, [[#ac-3]] |
| 23 #b-2 (marker outside the transaction; AC kills at a boundary) | [[#r3]] 3-5, [[#ac-4]], [[#ac-5]] |
| 23 #b-3 (per-row writes invisible; no finalize) | [[#r2]] finalize, [[#ac-8]], [[#ac-9]]; 23.2 R3 |
| 23 #s-1 (N per hold vs learn's contract; four stop paths) | [[#r2]], [[#r9]] 1, [[#ac-7]] |
| 23 #s-2 (key-only coalesce) | [[#r3]] 1, [[#ac-2]] |
| 23 #s-3 (not queue-shaped consumers; tick registry; plan-21) | [[#r4]], [[#r5]], [[#r6]], [[#ac-11]]; plan [[plan-23-bounded-write-harness#consumers]] |
| 23 #s-4 (holds counted by the drain; `_FairLock`; 23.2 first) | [[#acceptance]] preamble, [[#ac-1]] |
| 23 #s-5 (bound is a warning) | [[#r2]] `hold_alarm_s` |
| 23 #s-6 (overflow has no route to `learn status`) | [[#r6]] 5-6, [[#ac-12]] |
| 23 #s-7 (kill / sandbox undefined) | [[#test-strategy]], [[#ac-4]] |
| 23 #m-3 (stale ONE-acquisition docstrings) | [[#r9]] 4, [[#ac-15]] |
| d2a (offset in the batch's DuckDB transaction) | [[#r1]] 3, [[#r3]] 4, [[#ac-4]] |
| #t8-amendments d2a (fragments; `replica_merge`; retained replay source) | [[#r7]], [[#r8]], [[#r4]] 2 and 4, [[#ac-13]], [[#ac-14]] |
| d2b (`bind` seam, Option A not folded in) | [[#r1]] 1 |
| d2d (bug-099 fixed by 23.1) | [[#r3]] 3, [[#ac-5]] |
| d4a + #t8-amendments d4a (non-consuming tail reader; tick registry; one budget) | [[#r4]], [[#r6]], [[#ac-10]], [[#ac-11]] |
| #t2-fixes (`bind` per batch inside the hold + two-partition AC; recorder + finalize; one event per hold, budget/shutdown/error/requeue; required `merge_fn`; real `_FairLock`; every batch released; overflow through a daemon op) | [[#r1]], [[#r2]], [[#r3]], [[#r6]], [[#ac-1]], [[#ac-3]] |
| decision-log #s-1 (exactly-once boundary, fragments, `replica_merge`, retention) | [[#r3]] 7, [[#r7]], [[#r8]], [[#r4]] |
| decision-log #s-3 (tail mode, tick registry, 23.3 on `bounded_steps`) | [[#r4]], [[#r5]], [[#r6]] |
| decision-log #m-3 (16.6 rides the overflow-dropping queue) | [[#r3]] 6 (counted, persisted, printed); 16.6's lower-bound reading is 16.6's |
| d1a/d1b (sandboxed tests) | [[#test-strategy]] |
