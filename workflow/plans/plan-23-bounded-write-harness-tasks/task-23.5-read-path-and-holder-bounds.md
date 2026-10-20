---
gmd: "0.1"
id: task-23.5-read-path-and-holder-bounds
title: "Task 23.5: no cli-pool op waits on the writer lock without a bound — every cli read through one bounded helper, writes and the forced snapshot off the cli pool, compaction off the lock, holders named — so the heartbeat stops depending on the longest writer hold (d9az, d9bn)"
tags: [task, daemon, lock, read-path, heartbeat, watchdog, compaction, bug-112, bug-115, bug-116, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-15
  updated: 2026-10-15
---

# Task 23.5: the read path and the non-harness lock holders {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending. NEW in revision round 7 (2026-10-15) under d9az: plan-23 OWNS the
> non-harness `_store_lock` holders and the heartbeat's coupling to the cli pool
> ([[plan-23-bounded-write-harness#scope-d9az]]). Revision round 8 (2026-10-15): first review
> [[bsd-plan23-17-spec-rereview-r8-23ad703]] (nb23-r8-1, ns23-r8-1..3, nm23-r8-1..4) answered
> under d9bn ([[plan-review-2026-10-14#t12-approvals]], PROVISIONAL until its ch-bsd loop is
> clean); see [[#rev-round-8]]. Revision round 9 (2026-10-15): diff check
> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d]] (nb23-r9-1/2, ns23-r9-1/2, nm23-r9-1..3); see
> [[#rev-round-9]]. Revision round 10 (2026-10-15): diff check
> [[bsd-plan23-17-spec-diffcheck-r10-0dc2da3]] (nm23-r10-1..5, all MEH); see [[#rev-round-10]].
> Depends on: 23.0 (sandbox), 23.2 (recorder), 23.1 (`_FairLock` owner, R1.6 item 1; the learn
> drain, R9; `_compact_factslog_locked`, R3.7). **bug-115/116 (0.78.2) merged to `master`:
> SATISFIED** (`607d759`, `1c86d9c` and bug-117's `391ffeb` are ancestors of `master` `b381b6d`;
> HEAD `23ad703`). **bug-112 FIXED and reachable from `master`: OPEN, a HARD gate (nb23-r9-2;
> the same gate as 18.3's header).** The fix is in flight on branch `bugs-112-113-118`
> (`7c38c46`, `0fed0d5`, `462bd0b` so far; clone `/Volumes/littlebig/refmatrix-bugs112-118`),
> which is NOT an ancestor of `master` at `b84fd8d`. The branch will gain more commits before it
> merges (d9bw(d) adds `_writer_lost`), so the gate names no branch commit: it names **the merge
> commit that lands bugs-112-113-118 on master**. 23.5 is not implemented before `git merge-base
> --is-ancestor <the merge commit that lands bugs-112-113-118 on master> master` succeeds; that
> sha is read from `git log --merges master` at gate time, and the command and its output are
> recorded in the implementation summary.
> Runs in parallel with 23.3 after 23.1. Blocks nothing in Wave 1; 17.3's hold bound
> ([[task-17.3-fleet-rollout#r2-measure]]) cites the same coupling.
> **Stands alone (ns23-r9-1).** 23.5 is Wave 1; plan-18 is Wave 4. Nothing here waits on 18.2 or
> 18.3: compaction's tail hold is a plain `with self._store_lock:` under
> `Daemon._inflight("compact")`, and `pin_to` lives on `_snapshot_catalog`. When plan-18 later
> converges the `_store_lock` + DuckDB maintenance + file swap shape into `Daemon._catalog_hold`
> (d9bf; 18.2 R11, 18.3 R8), the obligations it must carry for this task's guarantees are listed
> in [[#cross-plan-18]] for the plan-18 reviser. This task adds no second mechanism for that
> shape ([[#r4]], [[#r5]]).

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: implements -> [[plan-review-2026-10-14#t12-approvals]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#live-evidence]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#needs-user]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: related-to -> [[task-23.3-sync-between-file-yield]]
rel: related-to -> [[task-17.3-fleet-rollout]]
rel: related-to -> [[plan-18-duckdb-store-maintenance]]
rel: related-to -> [[task-18.2-catalog-maintain-step]]
rel: related-to -> [[task-18.3-offline-reclaim#r8-one-helper]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d]]
rel: depends-on -> [[bug_registry]] {bug: "bug-112", gate: "fixed and reachable from master"}
rel: related-to -> [[feedback_causal_story_before_evidence]]
rel: related-to -> [[project_store_decays_behind_green_health]]

## Why {#why}

Two incidents on 2026-10-15 went through the same coupling
([[bsd-plan23-17-spec-rereview-r7-331b414#live-evidence]]):
- **00:11:15-00:13:18.** A `facts.log` compaction finished at 00:11:15; for two minutes no
  lock-taking line appears in `rmxd.log`; three `stats` ops were in flight at the 00:13:16 stop;
  the hub restarted the daemon at 00:13:18 ("not answering ping"). The logs hold no mechanism,
  and this spec names none (`feedback_causal_story_before_evidence`). R4 makes the next one
  name its holder.
- **00:16:52-00:17:44.** A heartbeat stall coincided with two concurrent post-commit
  `sync --since HEAD~1` runs (80,429 ms and 109,993 ms) and ended within a second of the second
  one. The syncs held `_store_lock` while all 4 cli workers waited on it.

The structural fact under both: interactive reads wait on the writer lock with no bound, on a
4-worker pool whose completions are the heartbeat. The longest writer hold anywhere in the
daemon therefore sets how long every read waits AND how long the liveness signal stops.
23.1 bounds harness writers and 23.3 bounds sync, but no task bounded what a READ waits for.
This task cuts the coupling at the reader: no cli-pool op waits on `_store_lock` without a
bound, whether it takes the lock in its own body or through a helper, so the cli pool keeps
completing (and beating) through any writer hold. {#why-body}

## Facts at HEAD `23ad703` {#facts}

Read at HEAD `23ad703` (0.78.3; bug-115/116 and bug-117 merged) in round 8, by symbol with the
HEAD line. Round 7's `77ac38f` numbers are superseded.
- **Pools.** `CLI_OPS` (`daemon.py:6355`) has 31 entries; `ping` is answered on the dispatcher
  thread in `Daemon._handle` (0.78.2), so 30 reach the cli pool. Everything else goes to the bg
  pool. Sizes on the live store: `pools cli=4 bg=12 disp=20` (`rmxd.log`
  2026-10-15T00:13:21); `disp_pool` is `cli + bg + 4` workers (`serve_forever`, `:1898-1901`),
  and each dispatcher thread blocks on its op's future (`fut.result()`, `:3262`).
- **`CLI_WRITE_OPS`** (`daemon.py:6352`) = `{partition_add, partition_rename, stop}`, added by
  `1c86d9c` after r7: for those ops `expires` is `None` (`Daemon._handle`, `:3235-3238`), so
  bug-116's deadline drop never applies to them ("a caller that timed out on a write has not
  withdrawn it"). The deadline wrapper `run` exists only when `expires` is set
  (`:3240-3248`), and it runs on the WORKER thread; `expires` lives only in its closure and
  never reaches the handler.
- **`_inflight_ops`** (`Daemon.__init__`, `:787`): the dispatcher thread records
  `token -> (op, time.time())` before it submits (`:3250-3253`) and pops it in a `finally`
  (`:3264-3267`). `_final_flush` already names in-flight ops from it when the lock is
  contended (`:1520-1541`, "final flush skipped: _store_lock contended …; in flight: …").
- **The 15 cli ops whose own body takes `_store_lock`**, each with its HEAD lock line:
  `ann_search` (`:6018`), `context` (`:4832`, a WRITE: `_learn_grep_hits` on a cli worker; its
  read already goes through `_read_with_fallback`), `derive_history` (`:4546`),
  `derive_status` (`:4454`, `:4474`), `grep_indexed` (`:4303`), `list_linkages` (`:4046`),
  `list_saved_queries` (`:4288`), `memory_recall` (`:6108`), `partition_add` (`:4113`, a
  write), `partition_audit` (`:4168`), `partition_list` (`:4267`), `partition_rename`
  (`:4130`, a write), `query` (`:4614`), `replica_audit` (`:5467`), `stats` (`_op_stats`,
  `:3817`). Every one is `with d._store_lock:` (unbounded).
  - `replica_relink` does NOT take the lock: its only `_store_lock` text is its docstring,
    "Deliberately does NOT take `_store_lock`" (`:5439`).
- **Cli ops that reach the lock through a HELPER (nb23-r8-1; round 7 missed these):**
  - `snapshot` is in `CLI_OPS`. `_op_snapshot` (`:4088`) calls
    `d._snapshot_catalog(force=True)` (`:2669`), which holds `with self._store_lock:` (`:2700`)
    across a `CHECKPOINT` and a child `cp -p` of the writer slot (`_copy_out_of_process`,
    `:208`) and the `os.replace` onto `catalog.read.duckdb`. The hold grows with the catalog.
    Its only callers are two tests (`tests/test_save_state_embeds_memories.py:89`, a call;
    `tests/test_snapshot_tier.py:179`, which asserts `snapshot` is in `CLI_OPS`).
  - Ten `_read_with_fallback` calls in cli handlers pass no `writer_wait_s`, so it is `None`
    (unbounded; signature `:4895-4897`): `context` `:4810`, `describe` `:4866`, `memory_get`
    `:5033`, `memory_iter` `:5047`, `memory_search` `:5063`, `memory_recent` `:5080`,
    `memory_score` `:5211`, `subject_list` `:5366`, `subject_leaves` `:5374`, and
    `memory_recall`'s prefilter `:6101`. They take `_store_lock` UNBOUNDED through
    `_read_with_fallback`'s writer fallback when the read stores lack the partition
    (`with _writer_lock(d, writer_wait_s)`, `:4957`) or no snapshot exists at all (`:4975`).
    The `missing="empty"` default exists because "a memory partition a fresh project never
    wrote is normal", so on such a project every memory read takes the writer lock unbounded.
  - `_writer_lock(d, None)` (`:4996`) is `d._store_lock.acquire()` with no timeout
    (`:5000-5001`).
  - A transitive AST walk at HEAD (round 8, scratchpad script; every `CLI_OPS` handler, calls
    followed into same-module functions and `d.`/`self.` `Daemon` methods) flags 24 of the 31
    ops: the 15 above, `snapshot`, and `describe`, `memory_get`, `memory_iter`,
    `memory_search`, `memory_recent`, `memory_score`, `subject_list`, `subject_leaves` (the
    bare `_read_with_fallback` calls; `context`, `memory_recall` and `stats` appear in both
    lists). The bg-pool callers of `_read_with_fallback` (`_op_top_concepts` `:4081`,
    `_op_memory_facets` `:5118`, `_op_memory_brief` `:5335`) are not cli ops.
- **The lock-free read path.** `_read_with_fallback(d, partition, fn, *, private, missing,
  writer_wait_s)` (`:4895`): the in-memory mirror, then the snapshot file
  `catalog.read.duckdb`, then the writer under `_store_lock` only when the read stores lack the
  partition, through `_writer_lock(d, wait_s)`, which raises `LookupError` on a bounded
  timeout. The mirror and snapshot lag the writer by `RMX_SNAPSHOT_DEBOUNCE_MS` (250 ms
  default, `_snapshot_catalog` `:2690`) plus one refresh.
- **The mirror is one reader at a time (ns23-r8-2).** `_MemMirror` (`:332`) is ONE shared Store
  and DuckDB connection; `acquire_use()` returns `_use_lock`, a plain `threading.Lock()` ("one
  reader at a time", `:365`), held for the whole of `fn`; its docstring says reads "must
  complete quickly so `_use_lock` doesn't gate everyone". It is NOT re-entrant: a
  `_read_with_fallback` nested inside a mirror `fn` on the same thread deadlocks.
  `private=True` skips the mirror and opens a snapshot-file Store for the call (`context`
  does this today, ch-bsd r9 #b-2).
- **`stats(include_health)` (ns23-r8-1).** `_store_health(d)` (`:3829`) calls
  `_read_with_fallback(…, writer_wait_s=0)` once for the partition list (`:3903`) and once per
  partition (`:3909`), so it must never run inside a mirror `fn`. It also reads the WRITER's
  connection without the lock: `d._st().recent_memories(limit=1)` (`:3855`),
  `d._st().db_path.name` (`:3878-3880`) and `d._st()._partition_name` (`:3902`). The first is
  a DuckDB query on the writer's connection concurrent with whatever holds the lock (bug-098's
  class); 23.1 R1.6's check guards writers only, so nothing raises. `_memory_partition(d, args)`
  (`:4869`) also falls back to `d._st()._partition_name`, the writer's CURRENT binding, which a
  write op's `with_partition` rebinds for its duration.
- **`_op_stats`'s `include_stale` comment is stale (nm23-r8-3).** "the replica/snapshot never
  refreshes" `tracked_files` dates from the rotation era; the snapshot is a full post-`CHECKPOINT`
  copy of the writer slot, so its `tracked_files` lags by one debounce like every other table.
- **bug-112 (open)** ([[bug_registry]]): DuckDB 1.5.2's `duckdb.connect()` instance cache
  returns an already-open database for a second in-process connect to the same path, so a
  private reader that opens `catalog.read.duckdb` while another in-process connection to that
  path is still open can get the replaced, unlinked snapshot.
  - **The bound is a CHAIN, not the oldest reader (nb23-r9-2, measured by the r9 diff check on
    DuckDB 1.5.2).** A opens; the file is replaced; B opens while A is open and reads A's
    database; A closes; the file is replaced again; C opens while B is open and still reads
    A's database; only a reader opened after EVERY overlapping reader closed reads the new
    file. Under hook load (4 cli workers) such a chain can last indefinitely.
  - **The fix in flight** (branch `bugs-112-113-118`, `7c38c46` + `0fed0d5`, not on `master`):
    `backend.open_duckdb(path, *, read_only)` is THE file-backed DuckDB opener; a read-only open
    is a private `:memory:` instance that `ATTACH`es the file `READ_ONLY` and `USE`s it, so each
    open reads the file at the path NOW; `release_duckdb(con)` closes one. The backend's
    `DuckDBConnection` opens through it, so `Store(…, read_only=True)` (what
    `_open_read_store` builds for a private read) does too. Its bypass check is
    `tests/test_bug112_duckdb_reopen.py::test_every_file_backed_duckdb_connect_goes_through_open_duckdb`
    (an AST walk of `src/` that fails on any file-backed `duckdb.connect` outside
    `open_duckdb`).
- **Dirty bitmap fragments never reach the snapshot by themselves (nb23-r9-1).** `Store.link`
  (`store.py:4622`) sets the bit in the in-memory fragment cache and marks the linkage in
  `_dirty_fragments`; it flushes nothing. `_op_link` (`daemon.py:6156`) runs it under
  `_store_lock` with no transaction, then `_request_snapshot()`. Fragments reach the catalog
  only at a transaction's COMMIT (`store.py:4562-4566`), the periodic flush (`_periodic_flush`,
  every `RMX_DAEMON_FLUSH_S` = 30 s; it requests no snapshot) and close. `_snapshot_catalog`
  (`:2700-2721`) runs `CHECKPOINT` + a file copy with no `flush_fragments()`. So the snapshot
  taken one debounce after a `link` holds the `entity_links` row but NOT the bit, and with no
  further write no later snapshot carries it. `QueryEngine` reads only bitmaps
  (`query.py:258-337`, `load_bitmap`): fresh today because `_op_query` reads the writer's
  cache; after R1 moves it to the read path, stale with no bound. `Store.stats` counts
  `entity_links` rows, which is why round 8's AC-7 could not see it. `Store.has_dirty_fragments()`
  (`store.py:1093`) and `Store.flush_fragments()` (`:4194`) exist.
- **Refusals are untyped on the wire (ns23-r9-2).** `Daemon._handle` answers a refusal as
  `{"ok": false, "error": <message>}`; `verbs._call` (`verbs.py:207-221`) raises plain
  `VerbError` for any `ok: false`. `VerbBusyError` (`verbs.py:37`) exists for "holding the
  writer lock" and must never be read as absent, but only `require_daemon` and the transport
  `except` raise it today.
- **`_inflight_ops` has two readers and five test sites (nm23-r9-1).** `_final_flush`
  (`:1520-1541`) and `_drain_pool`'s timeout log (`:1578-1579`, `for op, _t0 in
  self._inflight_ops.values()`), plus `tests/test_inflight_registry.py:67, :91, :169-170, :196`
  and `tests/test_daemon_shutdown_drain.py:148`, which build or unpack 2-tuples;
  `test_inflight_registry.py:151` asserts `_inflight_ops == {}` after an op.
- **The lock is passed as a value (nm23-r9-2).** `_periodic_flush(self.store, self._store_lock,
  self._log)` (`:232-238`) takes it as `lock` and does `with lock:`; a spelling-based rule never
  sees that hold.
- **The heartbeat constants are read at import (nm23-r9-3 c).** `HEARTBEAT_INTERVAL_S` (`:63`)
  and `HEARTBEAT_STALE_S` (`:66`) are module constants; the heartbeat thread re-reads
  `RMX_HEARTBEAT_S` at start (`:1331`).
- **The heartbeat** (`Daemon._start_heartbeat`, `:1323-1358`): each tick submits a no-op to the
  cli pool and touches the file when it completes; since 0.78.2 every cli-pool completion also
  touches it (`fut.add_done_callback(self._heartbeat_touch)` in `Daemon._handle`).
  `HEARTBEAT_INTERVAL_S` 5 (`:63`), `HEARTBEAT_STALE_S` 60 (`:66`, env
  `RMX_HUB_HEARTBEAT_STALE_S`).
- **The watchdog** (`hub.py`, unchanged since `77ac38f`): a ping that answers within
  `WATCHDOG_PING_TIMEOUT_S` (2 s, `:46`) resets the miss count (`:264-266`); a restart needs
  `WATCHDOG_GRACE_MISSES` (3, `:48`) consecutive missed ticks at `WATCHDOG_INTERVAL_S` (15 s,
  `:39`) AND a heartbeat older than `HEARTBEAT_STALE_S` (`:305-317`).
- **The compaction tick** (`Daemon._start_factslog_compact_tick`, `:2428`) wakes every
  `RMX_FACTSLOG_COMPACT_INTERVAL_S` (1800 s) and runs `_compact_factslog_if_needed` (`:2341`),
  whose `self.store.dump_catalog_to_log()` (`store.py:7526`) runs inside one
  `with self._store_lock:` (`:2380-2381`). On a copy of the live read snapshot (835 MB;
  114,469 entities) the dump took 6.1 s (the r7 re-review's run).
- **Replay sorts by `ts`, not file order (nm23-r8-1).** `Store.rebuild_index_from_log` does
  `events.sort(key=lambda e: e.get("ts", 0))` (`store.py:7941`), a stable sort. The dump's
  events carry catalog `created_at` / `updated_at` / `GREATEST(c.updated_at, e.updated_at)`
  timestamps. It also skips a non-JSON line without a count (`store.py:7936-7940`; bug-119).
- **What 0.78.2 already does:** `ping` on the dispatcher; a heartbeat on every cli completion;
  a queued cli READ whose `deadline_s` passed before a worker reached it raises
  `DeadlineExceeded` and is not run (counted, one log line a minute, `_note_expired_read`
  `:1362`); writes are never dropped (`CLI_WRITE_OPS`); `daemon.call` never re-sends a sent
  request.
- **What 0.78.2 does not do**, and so what this task must:
  1. An op ALREADY RUNNING on a cli worker that reaches `_store_lock` (in its body or through a
     helper) waits for the whole writer hold. Four such ops park all 4 workers; no cli op
     completes; the heartbeat stops for the rest of the hold.
  2. A restart also needs ping misses, which need every dispatcher thread busy (more than 20
     requests in flight). A hook storm reaches that, so a writer hold longer than
     `HEARTBEAT_STALE_S` + 3 ticks still restarts the daemon under load.
  3. Nothing bounds the compaction tick's hold, and no log line names a non-op holder.
{#facts-body}

## Scope (d9az, d9bn) {#scope}

In: every `CLI_OPS` op that reaches `_store_lock` (the 24 above) and every future `CLI_OPS`
op; the facts.log compaction tick and op; the snapshot's hold (measured and named; its shape is
plan-18's shared helper, [[#r5]]); the heartbeat's dependence on the cli pool; a holder name on
every long hold.
Out: harness writers (23.1), `_sync_paths` and the watch flush (23.3: one sync at a time, the
lock released between files, which bounds the 80-110 s shape of the second incident), plan-17's
maintenance holds (17.1 / 17.3), plan-18's catalog maintenance and its swap (18.2 / 18.3), and
`ping` (0.78.2). {#scope-body}

## Requirements {#requirements}

1. **R1 Every cli read goes through ONE bounded helper (d9bn ruling 1).** {#r1}
   1. **The helper.** `_cli_read(d, partition, fn, *, missing="empty", wait_s=None,
      private=None)` in `daemon.py` is the ONLY caller of `_read_with_fallback` reachable from
      a `CLI_OPS` handler. It always passes
      `writer_wait_s = _cli_writer_wait(d) if wait_s is None else wait_s` (R2's bound; `wait_s`
      exists only for `_store_health`'s `0`). On the `LookupError` of a bounded wait it raises
      `WriterBusy(_writer_busy_message(d))`, the message
      `writer busy: <holder> holding _store_lock for <s>s; not run` built from R4's holder.
      `private=None` resolves to `op not in MIRROR_OPS` for the current op ([[#r1-mirror]];
      the op name comes from R2's worker-thread context). `Daemon._handle` treats `WriterBusy`
      like `DeadlineExceeded`: `{"ok": false, "error": <message>, "code": <code>}`, no
      `op … raised` line, and it never reaches `_fast_exit_if_invalidated`. The two refusals
      share ONE rate-limited counter, log path and response builder: `_note_expired_read`
      becomes `_note_refused(reason, op, detail)` (`reason` = `deadline` or `writer-busy`), and
      it returns the response dict, so the `code` is set in one place, not at each raise site.
      {#r1-helper}
      - **The refusal is typed on the wire (ns23-r9-2).** `code` is `"writer_busy"` for
        `WriterBusy` and `"deadline"` for `DeadlineExceeded`. `verbs._call` raises
        `VerbBusyError(<error>)` when `r.get("code")` is one of them, and plain `VerbError`
        otherwise, so MCP tools and hooks retry or report a busy writer and never string-match
        the message or treat it as absent.
        - **One reader of the code (nm23-r10-3).** `verbs.BUSY_CODES` (one frozenset) is read
          by ONE helper, `verbs._raise_for_answer(r, op, root)`: it returns on `ok: true`,
          raises `VerbBusyError` when `r.get("code") in BUSY_CODES`, and raises `VerbError`
          otherwise. It has two callers: `verbs._call`, and `verbs.memory_partition`'s
          answered-error branch (`verbs.py` ~:261-278), which today logs and returns the
          project default for ANY `ok: false`. After this task that branch calls
          `_raise_for_answer`; a `VerbBusyError` propagates (a busy answer is never turned into
          a guessed partition, the split-brain family the function exists to prevent,
          bsd-plan3-r4 #s-4), and only a non-busy `VerbError` keeps the logged project
          default. No other site reads `code` or `BUSY_CODES`. {#r1-typed-refusal}
   2. **`_read_with_fallback`'s `writer_wait_s` becomes a REQUIRED keyword** (no default). The
      three bg-pool callers (`_op_top_concepts`, `_op_memory_facets`, `_op_memory_brief`) pass
      `writer_wait_s=None` explicitly; on the bg pool an unbounded wait parks no cli worker. A
      bare call is then a `TypeError`, not a silent unbounded wait.
   3. **The sites (nb23-r8-1).** Every one of these moves onto `_cli_read`:
      - the 11 read ops whose body takes `with d._store_lock:` today: `ann_search`,
        `derive_history`, `derive_status` (one `_cli_read` per partition), `grep_indexed`,
        `list_linkages`, `list_saved_queries`, `memory_recall` (its `:6108` body and its `:6101`
        prefilter), `partition_audit`, `partition_list`, `query`, `stats`;
      - the 10 bare `_read_with_fallback` calls: `context` `:4810` (keeps `private=True` and
        `missing="raise"`), `describe` `:4866`, `memory_get` `:5033`, `memory_iter` `:5047`,
        `memory_search` `:5063`, `memory_recent` `:5080`, `memory_score` `:5211`,
        `subject_list` `:5366`, `subject_leaves` `:5374`, `memory_recall` `:6101`;
      - `_store_health`'s two calls (`:3903`, `:3909`), with `wait_s=0` as today.
      {#r1-sites}
   4. **`snapshot` leaves the cli pool.** `"snapshot"` is removed from `CLI_OPS`, so
      `_op_snapshot` runs on the bg pool: it is a forced writer-side `CHECKPOINT` and copy, and
      no production caller exists. `tests/test_snapshot_tier.py::test_op_snapshot_registered_in_ops_and_cli_ops`
      is updated to assert `snapshot` is in `OPS` and NOT in `CLI_OPS`; the
      `test_save_state_embeds_memories.py:89` call is unchanged (it waits with `timeout=120`).
   5. **`stats` (ns23-r8-1, nm23-r8-3).** `_op_stats` is three steps, none inside another's
      `fn`: `out = _cli_read(d, d.partition, lambda rs: rs.stats())`; if `include_stale`,
      `out["stale_files"] = _cli_read(d, d.partition, lambda rs: rs.stale_files())` (the
      snapshot's `tracked_files`, at most one debounce behind; DECIDED, no writer path; the
      stale "never refreshes" comment is replaced by that sentence); if `include_health`,
      `out["health"] = _store_health(d)`, called after both reads return.
      {#r1-stats}
   6. **`_store_health` reads the READ path, never the writer's connection (ns23-r8-1; d9bn
      ruling 2).** `memory_read_ok` comes from
      `_cli_read(d, d.partition, lambda rs: rs.recent_memories(limit=1), wait_s=0)`: health
      checks the path that serves every memory read after R1; a `WriterBusy` there reports
      `memory_read_ok: null` with `memory_read_error: "writer busy"`, never `true`. `db_file`
      and `slot_bound` read `d.store.db_path` (an attribute; no connection); `own_name` is
      `d.partition`. `_memory_partition(d, args)` falls back to `d.partition`, not to the
      writer's current binding. An AST assertion: neither `_store_health` nor
      `_memory_partition` contains a `_st()` call. {#r1-health}
   7. **The mirror rule (ns23-r8-2; d9bn ruling 3).** `MIRROR_OPS: frozenset[str]`, beside
      `CLI_OPS`, lists the ops that read through the shared mirror. An op is in it ONLY if its
      measured p99 on a copy of the live read snapshot (835 MB, the r7 copy method) is under
      50 ms; every other cli read is `private=True`. Membership is the output of R8's census
      (each op's p99 and its path recorded in the implementation summary); before the census
      the set is EMPTY, so no op reaches the mirror on a guess. `context`, `memory_recall` and
      `ann_search` are private regardless (they run long inside `fn` by design). {#r1-mirror}
   8. **Freshness.** Mirror and snapshot reads are at most `RMX_SNAPSHOT_DEBOUNCE_MS` behind the
      writer plus one refresh, the contract `memory_get` serves today, for relational rows AND
      bitmaps alike. Two requirements make that true, R1.9 (the snapshot carries the dirty
      bits) and R1.10 (each private open reads the file at the path now). There is no known
      exception: round 8's bug-112 exception is withdrawn (nb23-r9-2), and bug-112's fix is a
      hard dependency ([[#root]] header). AC-7 checks both. {#r1-freshness}
   9. **The ONE snapshot path flushes dirty fragments inside its hold (nb23-r9-1).**
      `_snapshot_catalog`, inside its `_store_lock` hold and BEFORE `CHECKPOINT`, runs
      `if self.store.has_dirty_fragments(): self.store.flush_fragments()`. It runs under the
      lock, so 23.1 R1.6's lock-presence check holds. A flush error is handled like a
      `CHECKPOINT` error: one `snapshot flush failed: <exc>` line and
      `{"error": "flush", "detail": …}`, no copy, never a snapshot that silently lacks bits.
      This is the only snapshot path: the bg tick, `_request_snapshot()`, `_op_snapshot`
      (R1.4) and compaction's hold 1 (R5.1, `pin_to`) all go through `_snapshot_catalog`, and
      no second CHECKPOINT-and-copy is added. R7's AST test asserts that `_snapshot_catalog`'s
      `with self._store_lock:` body calls `flush_fragments` before the `CHECKPOINT` execute,
      and that no function other than `_snapshot_catalog` assigns or `os.replace`s onto
      `_snapshot_file()` (the other `_copy_out_of_process` call, the rotation bootstrap's
      slot copy at `:2930`, targets a writer slot, not the snapshot). When plan-18 ports the snapshot onto `CatalogHold.snapshot()`, that
      body carries the same line ([[#cross-plan-18]] item 4). {#r1-snapshot-flush}
   10. **Every private reader opens through ONE opener, `backend.open_duckdb` (nb23-r9-2).**
       `_read_with_fallback(private=True)` and the snapshot-file fallback open
       `catalog.read.duckdb` through `Store(…, read_only=True)`, whose backend opens through
       bug-112's `backend.open_duckdb(path, read_only=True)` (a private `:memory:` instance
       that `ATTACH`es the file `READ_ONLY`), so each open reads the file at the path NOW,
       whatever other reader is open. This task adds no opener of its own and no second
       bypass check: bug-112's AST test (`test_every_file_backed_duckdb_connect_goes_through_open_duckdb`)
       is THE check, and AC-7's mutation (a bare `duckdb.connect(path, read_only=True)` in the
       private open) must FAIL both it and AC-7's chain case. {#r1-opener}
2. **R2 The one cli op that needs the WRITER waits a bounded time and says so (ns23-r8-3; d9bn
   ruling 4).** {#r2}
   - **The writes leave the cli pool.** `partition_add` and `partition_rename` are removed from
     `CLI_OPS` and run on the bg pool, where writes are never dropped (0.78.2 as shipped by
     `1c86d9c`) and no write parks a cli worker. `CLI_WRITE_OPS` becomes `{"stop"}`. The cli
     pool is then read-only plus `stop`.
   - **`replica_audit`** (it pins the slot pair) takes the lock through
     `with _cli_writer_lock(d):`, which is `_writer_lock(d, _cli_writer_wait(d))` with the same
     `LookupError` → `WriterBusy` translation as `_cli_read` (one translation function shared
     by both).
   - **The deadline reaches the handler.** `Daemon._handle` wraps EVERY pool submission (cli
     and bg) in one worker-side wrapper, not only the deadline case. On the worker thread, before
     the handler runs, it sets a thread-local `_op_ctx` = `(op, token, expires)` (`expires` is
     `None` for a bg op, a cli write, or a request without `deadline_s`), runs 0.78.2's
     `DeadlineExceeded` check, and clears `_op_ctx` in a `finally`.
     `_cli_writer_wait(d)` returns `max(0, min(_op_ctx.expires − now, RMX_CLI_WRITER_WAIT_S))`,
     or `RMX_CLI_WRITER_WAIT_S` (default 5 s, after R6's clamp) when `expires` is `None`.
3. **R3 `context`'s learn write leaves the cli worker.** The learn-on-hit write in `_op_context`
   (`daemon.py:4832`, `_learn_grep_hits` under `with d._store_lock:`) becomes one
   `learn_queue.enqueue(root, pattern, hits)` (a lock-free `O_APPEND` line); 23.1's learn drain
   (R9, `idempotent=True`, insert-if-absent evidence) applies it on the next tick. The op keeps
   its "never fail a read" rule: an enqueue error is logged and the read still answers. {#r3}
4. **R4 Every long hold names its holder, from the EXISTING `_inflight_ops` registry
   (nm23-r8-2).** {#r4}
   - **One registry.** `_inflight_ops` stays the one record of who is running. Its value
     becomes a `NamedTuple` `InflightEntry(op, t0, ident, kind)` (nm23-r9-1), read by
     attribute everywhere, never unpacked: `kind` is `"op"` for a dispatched request and
     `"tick"` for a tick or thread. The dispatcher still creates an op's entry with
     `ident = None`, and R2's worker-side wrapper sets `ident = threading.get_ident()` under
     `_inflight_lock` when the handler starts (the worker, not the dispatcher, is the thread
     that takes the lock). Ticks and threads that take `_store_lock` outside an op register an
     entry (`kind="tick"`) through one context manager, `Daemon._inflight(name)`, which the
     dispatcher path uses too: `learn`, `compact`, `snapshot`, `flush`, `watch`, `sync`. BOTH
     readers move to the named value: `_final_flush` (`:1520-1541`; its "nothing tracked — …
     check the watcher or a background tick" branch now names ticks as well) and
     `_drain_pool`'s timeout log (`:1578-1579`, which unpacks 2-tuples today and would raise
     `ValueError` mid-shutdown). The tests that build or unpack the 2-tuple
     (`tests/test_inflight_registry.py:67, :91, :169-170, :196`;
     `tests/test_daemon_shutdown_drain.py:148`) move to `InflightEntry`, and
     `test_inflight_registry.py:151`'s `_inflight_ops == {}` filters to `kind == "op"` (a
     snapshot tick entering `Daemon._inflight` after the op's write would otherwise make it
     flaky). No second registry is added.
   - **The lock side.** 23.1's `_FairLock` owner field gains `_owner_since` (monotonic, set
     with `_owner` under `_mu`), and `_FairLock.holder() -> (ident, since) | None` reads both
     under `_mu`, without taking the lock. 23.2's `HoldRecorder` gets one explicit
     pass-through, `holder()`, in `tests/lockhold.py` (the same pattern as 23.1's
     `held_by_current_thread()`; 23.2's approved spec is not reopened).
     - **No hand-off window (nm23-r9-3 a).** 23.1's waiter sets `_owner` after `ev.wait`
       returns, outside `_mu`, so between `_pass_or_release_locked` clearing the owner and the
       waiter setting it, `holder()` would read `_held=True, _owner=None`. Instead `_waiters`
       holds `(ev, ident)` pairs, and `_pass_or_release_locked` sets `_owner, _owner_since` to
       the chosen waiter's ident under `_mu` before it sets `ev`; the woken waiter does not
       write `_owner`. `holder()` is therefore never `(None, …)` while `_held` is true. This
       amends 23.1 R1.6 item 1's owner write (one site, in `_FairLock`).
   - **The name.** `writer_holder` = the `_inflight_ops` entry whose `ident` equals the owner's
     ident: `{op, held_s}`; an owner with no entry reports `{op: "untracked thread <name>",
     held_s}`, never null. **One thread can carry several entries (nm23-r10-1)**: a bg op
     (`kind="op"`) that enters `Daemon._inflight(<name>)` (`snapshot` → `_snapshot_catalog`,
     `compact_factslog` → `compact`, and later plan-18's `_catalog_hold(<label>)`) has two
     entries with the same ident. Then `writer_holder` names the MOST RECENTLY REGISTERED one
     (the innermost `Daemon._inflight`, by registration order, never dict iteration order);
     `held_s` comes from the lock's `_owner_since`; the `lock hold:` alarm's label, and any
     per-label threshold ([[#cross-plan-18]] item 2), use the same entry. `stats(include_health=True)` reports it, and R1's / R2's
     `WriterBusy` message uses it.
   - **The alarm.** At release, a hold longer than `RMX_HOLD_ALARM_S` (default 10 s) logs one
     `rmxd.log` line `lock hold: <op> <s>s`.
   - **Cross-plan interface (d9bf; ns23-r9-1).** R4's `lock hold:` alarm fires in
     `_FairLock`'s release for EVERY holder, so a later holder needs only to register its name
     through `Daemon._inflight(<label>)` to be named. plan-18's `Daemon._catalog_hold` does not
     exist when 23.5 lands; what it must do to keep this guarantee is [[#cross-plan-18]] items
     1 and 2. This task specifies no lock mechanism of its own for it.
5. **R5 Compaction reuses the snapshot's hold; the dump runs off the lock (nm23-r8-1).** The
   periodic compaction and the `compact_factslog` op (`_compact_factslog_if_needed`, forced and
   size-gated) become ONE existing hold, an unlocked dump, and one short tail hold: {#r5}
   1. **Hold 1 is the snapshot's own hold, not a second copy.**
      `_snapshot_catalog(force=True, pin_to=<root>/.refmatrix/compact.src.duckdb)`. Inside its
      `_store_lock` hold, after the copy and the `os.replace` onto `catalog.read.duckdb`, it
      records the live log's size `L0`; before it releases `_snapshot_lock` it hard-links the
      fresh snapshot to `pin_to` (`os.link`, after unlinking a stale `pin_to`). The result
      carries `log_size` (L0) and `pinned`. A later snapshot's `os.replace` cannot change the
      dump's input, the link costs no disk, and `pin_to` is a NEW path, so bug-112's instance
      cache cannot hand the dump another database. Compaction adds no `CHECKPOINT` + copy hold
      of its own (the slot is 835 MB live; a 41 GB catalog is on record).
   2. **Unlocked:** open `pin_to` read-only and dump it to `facts.log.compact.tmp` with the same
      event form `dump_catalog_to_log` writes today (a `Store` method that takes a target
      path; the existing method keeps its signature for its other callers), recording the
      largest event `ts` written, `T_dump`.
   3. **Hold 2**, registered as `compact` (R4): append the live log's bytes `[L0, EOF)` to the
      tmp file; check the ORDER INVARIANT below; `fsync`; rename over `facts.log`; reset the
      slot offsets. Release; unlink `pin_to`; then the floor bookkeeping and log lines, as
      today.
   - **The order invariant.** Replay sorts by `ts` (`store.py:7941`), so correctness rests on
     every tail event's `ts` being at least `T_dump`, not on byte order. A stable sort keeps an
     equal-`ts` tail event after the dump's. Hold 2 reads each appended event's `ts`; if any is
     below `T_dump` (a caller-supplied timestamp, a clock step), it REFUSES the swap: the old
     log stays, the tmp file is deleted, one line `facts.log compaction refused: tail event ts
     <t> precedes dump ts <T_dump>` is logged, and the result is
     `{"compacted": false, "refused": "ts-order"}`. Nothing is silent.
   - **The L0 invariant.** Every `facts.log` append happens under `_store_lock` (23.1 writes
     events after `COMMIT` inside the hold), so `L0` read inside the snapshot's hold is the
     log position of the snapshot's state.
   - **Stands alone; plan-18 carries the port (d9bf; ns23-r9-1).** `_snapshot_catalog`'s hold
     is the `_store_lock` + DuckDB maintenance (`CHECKPOINT`) + file swap shape that plan-18
     later converges into `Daemon._catalog_hold`. This task adds only the dirty-fragment flush
     (R1.9) and the `pin_to` capture to that existing hold, both on `_snapshot_catalog`. Hold 2
     (append, rename, offset reset) is a plain `with self._store_lock:` under
     `Daemon._inflight("compact")`, unconditionally; there is no "when 18.2 is merged first"
     branch. Moving the snapshot and hold 2 onto the helper is plan-18's port, with the
     obligations in [[#cross-plan-18]] items 3-5. No second hold-and-swap mechanism is
     specified here.
   - **Refusals are counted, never silent across ticks (nm23-r9-3 d).** One catalog row whose
     `updated_at` lies past every tail event's `ts` (an import, a clock step back) would refuse
     every compaction while the tail is non-empty, which under load is always. The daemon
     counts CONSECUTIVE `ts-order` refusals (reset by a successful compaction) and reports
     `factslog_compaction_refused: <n>` in `stats(include_health)["health"]` (the dict
     `_store_health` returns). The hub carries only health keys it names into a queue row
     (`hub.py` ~:640-700), so it copies `factslog_compaction_refused` into the store's row when
     `>= 1`, and both `_queue_row_is_hot` and `_hot_signature` (`hub.py:1211`, `:1231`) name the
     key, so the row is hot with that reason and a change in the count is a new signature
     (nm23-r10-4; the pattern 18.2 R7 spells out). A refusal never retries in a loop: the next
     attempt is the next tick.
   - 23.1's BOOT check (before the socket binds, no cli pool yet) keeps
     `_compact_factslog_locked()` in one hold (23.1 R3.7); this task changes only the paths
     that run while clients are served.
6. **R6 The heartbeat no longer depends on the longest writer hold.** With R1 and R2, no cli op
   waits on `_store_lock` longer than `RMX_CLI_WRITER_WAIT_S`, in its body or through a helper
   (R7 proves the "through a helper" half), so cli completions and the tick's no-op continue
   through any writer hold. The daemon REFUSES a configured `RMX_CLI_WRITER_WAIT_S` above
   `HEARTBEAT_STALE_S − 2 × HEARTBEAT_INTERVAL_S` (50 s at the defaults, the same margin as
   [[task-17.3-fleet-rollout#r2-measure]]): it clamps to that value and logs
   `RMX_CLI_WRITER_WAIT_S=<v> clamped to <c>s (heartbeat stale window)`. {#r6}
   - **One reader of the inputs (nm23-r9-3 c).** The clamp and the heartbeat thread read
     `RMX_HEARTBEAT_S`, `RMX_HUB_HEARTBEAT_STALE_S` and `RMX_CLI_WRITER_WAIT_S` through ONE
     function, `_heartbeat_params() -> (interval_s, stale_s, cli_writer_wait_s)`, called at
     daemon start (env read at call time, not at import); the module constants
     `HEARTBEAT_INTERVAL_S` / `HEARTBEAT_STALE_S` stay only as its defaults. AC-8 checks the
     clamp against the TEST env's values, so a clamp computed from import-time constants
     fails it.
7. **R7 The rule is static and follows helpers to a fixpoint (nb23-r8-1).** An AST test over
   `daemon.py` resolves each `CLI_OPS` name through `OPS` to its handler, then follows every
   call to a same-module function and every `d.<m>(` / `self.<m>(` call to a `Daemon` method,
   to a fixpoint (nested lambdas and `def`s included). `_writer_lock` and `_read_with_fallback`
   are checked at the CALL, not entered. Any reachable occurrence of these FAILS:
   - `with <x>._store_lock` or `<x>._store_lock.acquire(` without a `timeout`;
   - **any reachable call that passes `<x>._store_lock` as an argument** (positional or
     keyword; `_writer_lock` takes `d`, not the lock, so the bounded path needs no exemption;
     nm23-r9-2: HEAD's
     `_periodic_flush(self.store, self._store_lock, self._log)` → `with lock:` is a hold the
     spelling rule cannot see; 23.1's `bounded.py` front-ends take the lock the same way);
   - `_writer_lock(` without a second argument, or with the literal `None`;
   - `_read_with_fallback(` anywhere except inside `_cli_read`'s body.
   At HEAD the walk flags 24 ops ([[#facts]]); after R1-R3 it flags none. The test also asserts
   that `_store_health` and `_memory_partition` contain no `_st()` call (R1.6), that
   `CLI_OPS` contains none of `snapshot`, `partition_add`, `partition_rename`, and R1.9's
   flush-before-`CHECKPOINT` order in `_snapshot_catalog`. {#r7}
8. **R8 Census of every holder and every read path.** One full-suite run with 23.2's recorder
   installed (and R4's alarm at 1 s) lists every `_store_lock` acquisition site in `daemon.py`
   and `store.py` with its holder name and its maximum recorded hold. Each site is assigned to
   the task that bounds it (23.1 harness, 23.3 sync/watch, this task's R2/R5, 17.1, 18.2/18.3)
   or gets a new `bug_registry.md` row. On a copy of the live read snapshot (835 MB) it also
   records, per cli read op, its p99 on the mirror path and on the private path over 200 calls;
   that table decides `MIRROR_OPS` (R1.7). The same table records, per cli read op, whether
   it reads BITMAPS (`load_bitmap` reachable from its `fn`) or only relational rows
   (nb23-r9-1), so each op's freshness AC is chosen by what it reads. It records the
   snapshot's hold (hold 1, flush included) and the
   compaction's tail hold on that copy. The implementation summary carries all three tables.
   This is a list of HOLD LENGTHS and read latencies; it is unrelated to 23.1 R1.6's
   lock-presence census. {#r8}

## Cross-plan obligations for plan-18 (ns23-r9-1) {#cross-plan-18}

23.5 lands in Wave 1 without plan-18 (Wave 4) and depends on nothing in it. When plan-18's
`Daemon._catalog_hold` / `catalog_maint.CatalogHold` (18.2 R11, R8; 18.3 R8) absorbs the
snapshot and the compaction, it must carry these, written into 18.2 / 18.3's own text by the
plan-18 reviser. This task does not edit plan-18's files; this list is the hand-off.

1. **Register the holder through `Daemon._inflight(<label>)`.** `_catalog_hold` enters
   `Daemon._inflight(label)` (an `InflightEntry` with `kind="tick"`) for its whole hold, so
   23.5 R4's `writer_holder` and `WriterBusy` message name it. It keeps no holder registry of
   its own. Called from an op (`catalog_maintain`), its thread carries two entries; R4 names
   the most recently registered one, so the helper's label (not the op's) is the holder and
   the key of any per-label threshold (nm23-r10-1). (18.2 R11 at `b84fd8d` does not mention `_inflight`.)
2. **No second hold alarm.** 23.5 R4's `lock hold: <label> <s>s` line, fired in
   `_FairLock`'s release, is the one alarm for every holder. 18.2 R11's own "one `rmxd.log`
   line for any hold over D1's 2 s edge" is withdrawn; if plan-18 needs its 2 s edge, it is a
   per-label threshold on that ONE alarm (a label → seconds map read by the same release
   path), not a second line. The helper's hold ring stays a measurement ledger.
3. **`CatalogHold.snapshot()` keeps `pin_to` and L0 inside the body.** With `pin_to`, the
   live log's size `L0` is read inside the `_store_lock` body after the copy and `os.replace`,
   and the `os.link` onto `pin_to` is made before `_snapshot_lock` releases (not in an `after`
   callback that runs after the release); the result carries `log_size` and `pinned`. 18.2
   R8's "The snapshot's behaviour does not change" names these as part of the behaviour.
4. **`CatalogHold.snapshot()` flushes dirty fragments before `CHECKPOINT`.** Its body runs
   `if store.has_dirty_fragments(): store.flush_fragments()` inside the hold, before
   `CHECKPOINT`, and a flush error returns `{"error": "flush"}` with one log line (23.5
   R1.9). 23.5 R7's flush-order AST assertion moves to that body with the port.
5. **18.3 R8 owns the compaction port.** 23.5 R5's hold 2 (append `[L0, EOF)`, ts-order check,
   `fsync`, rename, offset reset) moves onto `_catalog_hold` in 18.3, which lands later. 18.3
   R8's "**Not ported** … 23.1 owns it" becomes "ported by 18.3: 23.5 R5's compaction (hold 2)
   moves onto the helper", and 18.3 Q-C is closed. 23.5 AC-5 (two holds, nothing lost, the
   ts-order refusal and its counter) stays green after the port.
{#cross-plan-18-body}

rel: related-to -> [[task-18.2-catalog-maintain-step]]
rel: related-to -> [[task-18.3-offline-reclaim#r8-one-helper]]

## Acceptance criteria {#acceptance}

Every case runs in 23.0's sandbox on a recorded daemon (23.2's `recorded_daemon`) serving a short
tmp socket, with `RMX_HEARTBEAT_S=0.2` and `RMX_HUB_HEARTBEAT_STALE_S=3` unless stated.

1. **Reads answer through a long writer hold (R1, R6).** A test thread holds `_store_lock` for
   10 s (more than 3× the stale window), with `RMX_CLI_WRITER_WAIT_S=1`. During the hold:
   - each R1 read op (the 11 and the 10 sites), called through `daemon.call(…, timeout=2)` from
     8 concurrent client threads against partitions the snapshot holds, answers `ok` within 1 s;
   - `memory_search` against a partition absent from the snapshot (nb23-r8-1: its writer
     fallback needs the lock) answers within `RMX_CLI_WRITER_WAIT_S` + 0.5 s with an error that
     starts `writer busy:`;
   - `snapshot`, now on the bg pool, is accepted and completes after the release, and while it
     waits the 8-client reads above still answer within 1 s (no cli worker is occupied);
   - the heartbeat file's age, sampled every 0.1 s, never exceeds 1 s.
   Mutations, each must FAIL: `_op_stats` back on `with d._store_lock:` (its calls time out;
   with 4 in flight the workers park and the sampled age passes 3 s); the same for
   `_op_query`; `_op_memory_search` calling `_read_with_fallback(…, writer_wait_s=None)`
   directly (the absent-partition call parks for the whole hold); `snapshot` back in `CLI_OPS`
   (four concurrent `snapshot` calls park the 4 workers and the age passes 3 s). {#ac-1}
   - **AC-1b A stalled read does not park the mirror (R1.7; ns23-r8-2).** A test seam stalls
     one `query` call's `fn` for 3 s. With `MIRROR_OPS` set by the test to `{"stats"}` and
     `query` private (its R1.7 default): during the stall, 4 concurrent `stats` calls each
     answer within 1 s, and the heartbeat age stays under 1 s. Mutation: `query` added to
     `MIRROR_OPS` with the seam FAILS (the `stats` calls wait on `_use_lock` for the 3 s).
     {#ac-1b}
2. **The writes are on the bg pool and `replica_audit` is bounded and named (R2, R4).** During
   the same hold, with `RMX_CLI_WRITER_WAIT_S=1`:
   - `partition_add` is accepted on the bg pool; no cli worker is occupied (the 8-client reads
     still answer within 1 s); after the release it completes and the `partitions` row exists;
   - `replica_audit` answers within 1.5 s with an error that starts `writer busy:` and names
     the holder op the test registered;
   - `replica_audit` sent with `deadline_s=0.5` answers `writer busy:` within 1.0 s (the
     remaining deadline, not the 1 s wait, bounds it).
   - **The refusal is typed through the verb layer (R1.1; ns23-r9-2).** During the hold,
     `rmx_memory_search` called through the MCP adapter (the `verbs` path, not
     `daemon.call`) on a partition absent from the snapshot raises `VerbBusyError` (asserted
     by class, not by message), and the raw response carries `code: "writer_busy"`; the same
     A spy on `Store.__init__` in the client process records no client-side `Store(` open.
   - **The deadline code, observed on the raw wire (nm23-r10-3).** `daemon.call` sends
     `deadline_s = timeout` and uses the same value as its socket timeout, so a `deadline`
     answer can never reach `_call` before its own transport timeout; the verb path cannot see
     it. The case therefore sends a RAW request (the test's own socket client) with
     `deadline_s=0.2` and a 5 s read timeout, behind a cli pool blocked for 0.5 s by a seam,
     and asserts the answer carries `code: "deadline"`. Its mapping is asserted on
     `verbs._raise_for_answer` directly: a `{"ok": false, "code": "deadline", …}` dict raises
     `VerbBusyError`.
   - **`memory_partition` never guesses on a busy answer (nm23-r10-3).** With no replica
     reachable (the bootstrap branch) and a daemon that answers `partition_list` with
     `code: "writer_busy"` (the `_open_read_store`-returns-None seam, so `partition_list`
     reaches the writer fallback during the hold), `verbs.memory_partition(root, timeout=5)`
     raises `VerbBusyError` and returns no name. With a non-busy answered error (an unknown-op
     answer, no `code`), it still returns the project default and logs the warning.
   Mutations, each must FAIL: `replica_audit` on a plain `with d._store_lock:` (no answer within
   1.5 s); `_cli_writer_wait` ignoring `_op_ctx.expires` (the 0.5 s case takes 1 s);
   `partition_add` left in `CLI_OPS` (the AST case, and with 4 concurrent calls the 8-client
   reads miss 1 s); `code` dropped from the refusal response (the MCP case gets a plain
   `VerbError`, and the raw-deadline case finds no `code`); `memory_partition`'s answered
   branch left returning the project default for every `ok: false` instead of calling
   `_raise_for_answer` (the `writer_busy` case returns a name). {#ac-2}
3. **The rule is static and transitive (R7).** The AST test passes after R1-R3. Mutations, each
   must FAIL it: `with d._store_lock:` added to `_op_list_linkages`; a new module-level helper
   `_peek(d)` that does `with d._store_lock:` called from `_op_list_linkages` (the transitive
   case a direct-body rule missed); `_writer_lock(d, None)` in `_op_replica_audit`;
   `_read_with_fallback(…)` called directly from `_op_memory_search`; `snapshot` back in
   `CLI_OPS`; a `d._st()` call added to `_store_health`; `_periodic_flush(d.store,
   d._store_lock, d._log)` added to `_op_list_linkages` (the lock passed as an argument,
   nm23-r9-2); the `flush_fragments` call removed from, or moved after the `CHECKPOINT` in,
   `_snapshot_catalog` (R1.9). {#ac-3}
4. **`context` learns without the lock (R3).** With the lock held by a test thread, a `context`
   op whose answer has grep hits answers within 1 s and appends one `learn_queue` line; after
   the release, one tick's drain applies it (the `mentions` link and its evidence rows exist,
   counted once). Mutation: `_learn_grep_hits` called directly under `with d._store_lock:` as
   at HEAD FAILS (the op does not answer within 1 s). {#ac-4}
5. **Compaction off the lock, nothing lost, nothing reordered (R5; nm23-r8-1).** A store with
   2,000 entities and 5,000 links and a `facts.log` above the threshold. A seam pauses the
   unlocked dump; meanwhile, through daemon ops, a competitor `link`, one `memory_add`, an
   `unlink` of an edge the dump contains and a tombstone of an entity the dump contains each
   complete within 1 s; the seam releases. Then:
   - the recorder shows exactly two holds for the compaction (the snapshot's, with `L0`
     recorded inside it, and `compact`'s tail hold), neither containing the dump (the dump runs
     with `held_by_current_thread()` False), and each at most `RMX_HOLD_ALARM_S`;
   - a throwaway `rebuild --from-log` of the new `facts.log` equals the live catalog BY NAME
     (entities, links, evidence and memory content): it HAS the competitor's link and memory,
     and LACKS the unlinked edge and the tombstoned entity.
   Mutations, each must FAIL: the dump inside the lock (the competitors do not complete within
   1 s); hold 2 without the `[L0, EOF)` append (the rebuild lacks the competitor's link and still
   has the unlinked edge); `L0` read after the snapshot's hold releases (a seam appends one
   event between the copy and the read; the rebuild lacks it); the ts-order check removed (a
   seam appends a tail `link` event whose `ts` is below `T_dump` for an edge the dump holds as
   unlinked: without the check the swap happens and the rebuild disagrees with the catalog;
   with it, the result is `refused: ts-order`, the line is logged and `facts.log` is
   byte-identical to before).
   - **Refusals are counted (nm23-r9-3 d).** A catalog row whose `updated_at` is set 1 h in the
     future, then three compaction attempts with a non-empty tail: each is refused, and
     `stats(include_health=True)` reports `factslog_compaction_refused: 3`; after the row is
     corrected, the next compaction succeeds and the counter is 0. After the three refusals the
     hub's queue row for the store (one hub poll against the sandbox daemon) is hot, and its
     reason names `factslog_compaction_refused` (nm23-r10-4). Mutations, each must FAIL: the
     counter not incremented (it reads 0 after three refusals); the hub not copying the key into
     the row (the row is not hot). {#ac-5}
6. **Holders are named (R4) and health reads the read path (R1.6; ns23-r8-1, nm23-r8-2).**
   With `RMX_HOLD_ALARM_S=0.5`, a test-registered BG-pool op takes a 1 s hold (a cli op that
   took the lock would fail R7): `rmxd.log` has `lock hold: <that op> 1.…s`. During a second
   such hold, `stats(include_health=True)` answers within 1 s with `writer_holder.op` equal to
   the holder's op, `held_s` ≥ the elapsed time, and `memory_read_ok: true` (read from the
   snapshot, not the writer). A compaction tick's tail hold is reported as `compact`.
   - **The innermost entry names the holder (nm23-r10-1).** A test-registered bg op takes the
     lock and, inside the hold, enters `Daemon._inflight("inner")` (its thread then has two
     entries); during that hold `stats(include_health=True)` reports
     `writer_holder.op == "inner"`, and with `RMX_HOLD_ALARM_S=0.5` the release logs
     `lock hold: inner …`. Mutation: the FIRST matching entry instead of the last FAILS
     (`writer_holder.op` is the outer op's name).
   Mutations, each must FAIL: no op name recorded (`writer_holder.op` is null or "untracked");
   the ident set on the dispatcher thread instead of the worker (`writer_holder.op` is
   "untracked thread rmxd-bg-…"); `_store_health` called inside the outer `stats` `fn` with
   `stats` in `MIRROR_OPS`. That last mutation must FAIL, not hang (nm23-r9-3 b;
   `feedback_mutation_must_fail_not_hang`): the test sets a seam that makes the mirror's
   `acquire_use()` a BOUNDED acquire (2 s, then it raises `TimeoutError("mirror use-lock")`),
   so the nested call raises inside the op, `stats` answers an error naming the use-lock, and
   the case asserts on that answer; no worker stays parked and teardown completes.
   - **No hand-off window in `holder()` (R4; nm23-r9-3 a; nm23-r10-2).** Two threads contend
     `_FairLock` 2,000 times; each acquire HOLDS the lock at least 100 µs
     (`time.sleep(0.0001)` inside) so the other thread is queued at release; a sampler thread
     calls `holder()` in a tight loop throughout. The test counts hand-offs (a waiter woken by
     `_pass_or_release_locked`, through a test seam counter on `_FairLock`) and requires at
     least 1,000; fewer FAILS the case as vacuous (the r10 measurement: a tight
     acquire/release loop under the GIL hands off almost never, and the old order then shows
     0 null-owner samples). No sample returns `(None, …)` while `_held` is true. Mutation: the
     owner set by the woken waiter after `ev.wait` (23.1's original order) FAILS (samples see a
     null owner).
   - **Both `_inflight_ops` readers use the new value (nm23-r9-1).** `_drain_pool` times out
     with one op and one tick in flight: its log line names both and raises nothing; the
     updated `tests/test_inflight_registry.py` and `tests/test_daemon_shutdown_drain.py` pass.
     Mutation: `_drain_pool` left unpacking 2-tuples FAILS (`ValueError` in the drain). {#ac-6}
7. **Read freshness and `include_stale` (R1.5, R1.8-R1.10; nm23-r8-3, nb23-r9-1, nb23-r9-2).**
   Runs on a fixed bug-112 base (the [[#root]] header gate); no part of it is pinned as an
   exception.
   - A `link` through a daemon op, then `stats`: the new link count is visible within
     `RMX_SNAPSHOT_DEBOUNCE_MS` + 1 s.
   - **Bitmap freshness (nb23-r9-1).** With `RMX_DAEMON_FLUSH_S=3600` (no periodic flush in
     the window) and no other write after it, a `link` op of entity E under
     `<linkage>:<concept>`, then `query "<linkage>:<concept>"` through the daemon returns E
     within `RMX_SNAPSHOT_DEBOUNCE_MS` + 1 s. Then an `unlink` op of E under the same pair
     (`_op_unlink`, also non-transactional), and `query` no longer returns E within the same
     bound. Mutation: `_snapshot_catalog` without R1.9's flush FAILS (E is absent from the
     `query` answer after the link, and still present after the unlink).
   - **Regression coverage, not R1.9 coverage (nm23-r10-4).** `grep_indexed` returns a hit
     learned by one `learn` op (its bitmap bit) within the same bound. The learn drain applies
     the hit inside 23.1's `batch_transaction`, whose COMMIT flushes fragments, so this case
     passes with or without R1.9; it guards the learn path's freshness only. R1.9's
     discriminating cases are the non-transactional `link` and `unlink` above.
   - On a fixture with one tracked file touched after its sync, `stats(include_stale=True)`
     (served off the snapshot) reports the same `stale_files` list as the writer's
     `stale_files()` read by the test under the lock, after one debounce. No branch: the spec
     decided the snapshot; a difference fails the case.
   - **Private reads across a forced snapshot, sequential.** A private reader A is held open
     inside its `fn` by a seam; a `link` and a forced `snapshot` follow; A is released and
     closes; then a private read B sees the new link.
   - **Overlapping readers (nb23-r9-2, positive).** A is held open as above; a `link` and a
     forced `snapshot` follow; a private read B', opened WHILE A is still open, sees the new
     link.
   - **The overlapping chain (nb23-r9-2, the measured sequence).** A opens (held); `link` 1 +
     forced snapshot; B opens while A is open (held) and sees link 1; A closes; `link` 2 +
     forced snapshot; C opens while B is still open and sees link 2 (the newest file), not
     B's or A's database.
   - Mutation: the private open made through a bare `duckdb.connect(path, read_only=True)`
     instead of `backend.open_duckdb` FAILS twice: the chain case (C reads the pre-link-2
     count) and bug-112's AST bypass test (R1.10). {#ac-7}
8. **The coupling bound (R6) and the census (R8).** `RMX_CLI_WRITER_WAIT_S=500` at daemon start
   logs the clamp line and the effective wait is `stale_s − 2 × interval_s` as returned by
   `_heartbeat_params()` for the TEST env (`RMX_HUB_HEARTBEAT_STALE_S=3`, `RMX_HEARTBEAT_S=0.2`,
   so 2.6 s), set after `refmatrix.daemon` is imported. Mutations, each must FAIL: no clamp;
   a clamp computed from the import-time constants (it yields 50 s; nm23-r9-3 c). The census (R8) is in the implementation summary with every site
   assigned, the snapshot's measured hold and the compaction tail hold among them, and the
   per-op p99 table that justifies each `MIRROR_OPS` member. {#ac-8}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/daemon.py` | R1 (`_cli_read`; `WriterBusy`; `_note_expired_read` → `_note_refused`; the 11 read ops, the 10 `_read_with_fallback` sites and `_store_health`'s 2 on `_cli_read`; `writer_wait_s` required; `snapshot` out of `CLI_OPS`; `_op_stats` in three steps; `_store_health` and `_memory_partition` off the writer connection; `MIRROR_OPS`), R2 (`partition_add` / `partition_rename` out of `CLI_OPS`; `CLI_WRITE_OPS = {"stop"}`; the worker-side wrapper and `_op_ctx`; `_cli_writer_wait`; `_cli_writer_lock` in `replica_audit`), R3 (`context` enqueues), R4 (`_inflight_ops` 3-field value; `Daemon._inflight(name)`; `_FairLock._owner_since` + `holder()`; alarm; `writer_holder`), R5 (`_snapshot_catalog(pin_to=)`; two-hold compaction with the ts-order refusal), R6 (clamp) |
| `src/refmatrix/daemon.py` (round 9) | R1.1 `code` on the refusal from `_note_refused`; R1.9 the flush in `_snapshot_catalog`'s hold; R4 `InflightEntry` read by `_final_flush` AND `_drain_pool`, `_FairLock` hand-off sets the owner under `_mu`; R5 `factslog_compaction_refused` counter in `stats(include_health)`; R6 `_heartbeat_params()` |
| `src/refmatrix/verbs.py` | `BUSY_CODES`; ONE `_raise_for_answer(r, op, root)` read by `_call` and by `memory_partition`'s answered branch (R1.1; ns23-r9-2, nm23-r10-3) |
| `src/refmatrix/hub.py` | copy `factslog_compaction_refused` into the store's queue row when `>= 1`; `_queue_row_is_hot` and `_hot_signature` name it (R5; nm23-r9-3 d, nm23-r10-4) |
| `src/refmatrix/store.py` | the dump-to-path form of `dump_catalog_to_log` that also returns its largest `ts` (R5.2) |
| `tests/lockhold.py` | `HoldRecorder.holder()`, one explicit pass-through (R4; nm23-r8-2). 23.2's other surface is unchanged |
| `tests/test_inflight_registry.py`, `tests/test_daemon_shutdown_drain.py` | 2-tuples → `InflightEntry`; the `== {}` assertion filters `kind == "op"` (R4; nm23-r9-1) |
| `tests/test_snapshot_tier.py` | `test_op_snapshot_registered_in_ops_and_cli_ops` asserts `snapshot` is NOT in `CLI_OPS` (R1.4) |
| `tests/` | AC-1..AC-8 and AC-1b in a new `tests/test_read_path_holder_bounds.py`; the transitive AST test (R7) |

## Test strategy {#test-strategy}

- 23.0's sandbox; 23.2's recorder is `_store_lock` from the first op; short `mkdtemp` roots
  (macOS `sun_path`).
- Time bounds use the shortened heartbeat and stale env values above, never the production 60 s.
- Logs: `workflow/review-output/pytest-read-path.log`.

## Revision round 7 (2026-10-15) {#rev-round-7}

Created in revision round 7 for d9az ([[plan-review-2026-10-14#t12-approvals]]) and the r7
re-review's `#needs-user` item 2 ([[bsd-plan23-17-spec-rereview-r7-331b414#needs-user]]). Code
facts read at HEAD `77ac38f` and, for 0.78.2, at `607d759` on its branch.

| finding / decision | answered at |
|---|---|
| d9az (plan-23 owns `_op_stats` and the other lock-taking cli reads, the compaction tick, and the heartbeat's cli-pool coupling) | [[#scope]], [[#facts]] (the 15 ops; `replica_relink` corrected; what 0.78.2 does and does not do), [[#r1]]-[[#r8]], [[#acceptance]] |
| r7 `#live-evidence` item 4 ("no plan bounds the non-harness holders") | [[#why]], [[#r5]], [[#r8]] |

## Revision round 8 (2026-10-15) {#rev-round-8}

Source: [[bsd-plan23-17-spec-rereview-r8-23ad703]] (the first review of this task) and d9bn's
four rulings ([[plan-review-2026-10-14#t12-approvals]]). Code facts re-read at HEAD `23ad703`
and cited by symbol + HEAD line; [[#facts]] is rewritten to HEAD. The round-7 table above is
unchanged history; its anchors are kept, and AC-1b ([[#ac-1b]], inside AC-1) is new.

| finding / decision | answered at |
|---|---|
| nb23-r8-1 (`snapshot` and 10 bare `_read_with_fallback` calls in cli handlers wait on `_store_lock` unbounded; #facts said they "take no lock"; R7 sees only a handler's body) | [[#facts]] (the helper-reached sites; the 24-op AST walk at HEAD), [[#r1-helper]] (ONE helper `_cli_read`, d9bn ruling 1), [[#r1-sites]] (all 10 sites listed), [[#r1]] item 2 (`writer_wait_s` required), item 4 (`snapshot` to the bg pool), [[#r7]] (transitive to a fixpoint; `_read_with_fallback` only inside `_cli_read`), [[#ac-1]] (absent-partition `memory_search`; `snapshot` on bg; two mutations), [[#ac-3]] (helper-indirection and `snapshot` mutations), [[#files]] |
| ns23-r8-1 (`_store_health` nests the mirror's non-re-entrant use-lock and reads the writer's connection) | [[#facts]], [[#r1-stats]] (three steps, health outside any `fn`), [[#r1-health]] (d9bn ruling 2: `memory_read_ok` from the read path, `db_file` from `d.store.db_path`, `own_name` = `d.partition`; `_memory_partition` too; AST: no `_st()`), [[#ac-6]] (health during a hold, `memory_read_ok: true` within 1 s; the nested-call mutation), [[#ac-3]] |
| ns23-r8-2 (long reads move the coupling to the mirror's single `_use_lock`) | [[#facts]], [[#r1-mirror]] (d9bn ruling 3: `MIRROR_OPS` only for p99 < 50 ms on a snapshot copy, empty until the census), [[#r8]] (per-op p99 table), [[#ac-1b]] (3 s stalled `query`, 4× `stats` < 1 s; mutation) |
| ns23-r8-3 (R2's `min(deadline, …)` had no plumbing; its writes reversed 0.78.2's "writes are never dropped") | [[#facts]] (`CLI_WRITE_OPS`, the closure-only `expires`; round 7's item 3 rewritten), [[#r2]] (d9bn ruling 4: `partition_add` / `partition_rename` to the bg pool, `CLI_WRITE_OPS = {"stop"}`; R2 covers `replica_audit` only; `_op_ctx` set on the worker thread), [[#ac-2]] (rewritten; deadline case; three mutations) |
| nm23-r8-1 (replay sorts by `ts`, not order; hold 1 copied the whole slot; no AC bounded a hold) | [[#facts]], [[#r5]] (hold 1 IS the snapshot's hold, `L0` recorded inside it, the snapshot hard-linked before `_snapshot_lock` releases; the ts-order invariant stated and enforced by a logged refusal; "folds events in order" withdrawn; cross-plan interface to 18.3's helper, d9bf), [[#ac-5]] (unlink and tombstone competitors; each hold ≤ `RMX_HOLD_ALARM_S`; the ts-order mutation), [[#r8]] (both holds on the 835 MB copy) |
| nm23-r8-2 (R4's thread-local on the dispatcher; recorder accessor; AC-6's cli-op hold violates R7; `_inflight_ops` ignored) | [[#r4]] (the existing `_inflight_ops` extended with the worker's ident; `Daemon._inflight(name)` for ticks; `_FairLock.holder()`; no second registry), [[#files]] (`tests/lockhold.py` `holder()`), [[#ac-6]] (a test-registered bg-pool op; the dispatcher-thread mutation) |
| nm23-r8-3 (AC-7 branched on its own result; bug-112) | [[#facts]] (the stale comment; bug-112), [[#r1-stats]] (`include_stale` decided: the snapshot), [[#r1-freshness]] (bug-112 cited as the exception for private reads), [[#ac-7]] (branch deleted; the forced-snapshot private case; bug-112 pinned) |
| nm23-r8-4 (line drift; dependency satisfied; 30 of 31 `CLI_OPS` reach the pool) | [[#root]] header, [[#facts]] (rewritten at `23ad703`) |
| d9bn (four rulings) | (1) [[#r1-helper]], [[#r1-sites]], [[#r7]]; (2) [[#r1-health]]; (3) [[#r1-mirror]], [[#ac-1b]]; (4) [[#r2]], [[#r1-freshness]] |
| user rule: converge repeated shapes into one function | `_cli_read` (every cli read), `_cli_writer_lock` + one `LookupError` → `WriterBusy` translation, `_note_refused` (one refusal counter for deadline and writer-busy), `_inflight_ops` + `Daemon._inflight` (one holder registry), `_snapshot_catalog(pin_to=)` instead of a second copy hold, and plan-18's `Daemon._catalog_hold` (18.2 R11, 18.3 R8; d9bf) named as the interface for the hold-and-swap shape ([[#root]] header, [[#r4]], [[#r5]]) |

rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703#nb23-r8-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703#ns23-r8-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703#ns23-r8-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703#ns23-r8-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703#nm23-r8-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703#nm23-r8-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703#nm23-r8-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r8-23ad703#nm23-r8-4]]

## Revision round 9 (2026-10-15) {#rev-round-9}

Source: [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d]] (diff check of round 8 at `9dd923c`; HEAD
`b84fd8d`). The bug-112 fix branch `bugs-112-113-118` (`7c38c46`, `0fed0d5`) was read, not
run. The round-8 table above is unchanged history; R1.9, R1.10, [[#cross-plan-18]] and the
new AC bullets are new.

| finding | answered at |
|---|---|
| nb23-r9-1 (the snapshot drops dirty bitmap bits; R1.8's freshness false for bitmap reads; AC-7 counted rows) | [[#facts]] (dirty fragments), [[#r1-snapshot-flush]] (flush inside the ONE snapshot path's hold, before `CHECKPOINT`; error not silent; AST order check), [[#r1-freshness]], [[#r7]], [[#r8]] (bitmap-reader column), [[#cross-plan-18]] item 4, [[#ac-7]] (`RMX_DAEMON_FLUSH_S=3600`; `query` and `grep_indexed` within debounce + 1 s; the no-flush mutation), [[#ac-3]] |
| nb23-r9-2 (the bug-112 gate pinned the bug; the overlapping-reader bound is a chain) | [[#root]] header (bug-112 FIXED and reachable from `master`, a hard gate, as 18.3), [[#facts]] (the chain; `backend.open_duckdb`), [[#r1-freshness]] ("known exception" deleted), [[#r1-opener]] (one opener; bug-112's AST test is the bypass check), [[#ac-7]] (positive overlap, chain case, bare-`duckdb.connect` mutation; the pinned bullet deleted); plan-23 [[plan-23-bounded-write-harness#dependencies]] |
| ns23-r9-1 (one-sided cross-plan interface; compaction ownership bounced; a Wave 4 `depends-on`) | [[#root]] header (stands alone), `rel:` 18.2 `depends-on` → `related-to`, [[#r4]], [[#r5]] (hold 2 unconditionally a plain hold under `Daemon._inflight("compact")`), [[#cross-plan-18]] (five obligations for the plan-18 reviser) |
| ns23-r9-2 (`writer busy` untyped on the wire) | [[#facts]], [[#r1-typed-refusal]] (`code: writer_busy` / `deadline` from `_note_refused`; `verbs._call` → `VerbBusyError`), [[#ac-2]] (MCP-path case; the dropped-code mutation), [[#files]] |
| nm23-r9-1 (`_inflight_ops` 3-field value: a second reader, tests, a flaky `== {}`) | [[#facts]], [[#r4]] (`InflightEntry(op, t0, ident, kind)`; both readers; tests; `kind == "op"` filter), [[#ac-6]], [[#files]] |
| nm23-r9-2 (R7 recognised the lock by spelling) | [[#facts]], [[#r7]] (a call passing `<x>._store_lock` fails), [[#ac-3]] (`_periodic_flush` mutation) |
| nm23-r9-3 (a: `holder()` hand-off window; b: AC-6 mutation hangs; c: clamp inputs read at import; d: refusal liveness) | (a) [[#r4]], [[#ac-6]]; (b) [[#ac-6]] (bounded use-lock seam: FAILS, not hangs); (c) [[#r6]] (`_heartbeat_params()`), [[#ac-8]]; (d) [[#r5]] (consecutive-refusal counter, hub hot row), [[#ac-5]] |
| user rule: converge repeated shapes into one function, with bypass checks that can fail | one snapshot path (R1.9, AST order check), one opener `backend.open_duckdb` (bug-112's AST check), one refusal builder `_note_refused` setting `code`, one `BUSY_CODES` read by `_call`, one `InflightEntry` registry, one heartbeat-params reader, one hold alarm ([[#cross-plan-18]] item 2) |

rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d#nb23-r9-1]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d#nb23-r9-2]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d#ns23-r9-1]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d#ns23-r9-2]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d#nm23-r9-1]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d#nm23-r9-2]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d#nm23-r9-3]]

## Revision round 10 (2026-10-15) {#rev-round-10}

Source: [[bsd-plan23-17-spec-diffcheck-r10-0dc2da3]] (diff check of round 9 at `0dc2da3`; HEAD
`c8ff69d`; APPROVAL-READY, 7 MEH). Spec-text edits only; no design change. The round-9 table
above is unchanged history.

| finding | answered at |
|---|---|
| nm23-r10-1 (`writer_holder` ambiguous when one thread carries two entries) | [[#r4]] ("The name": the most recently registered entry; `held_s` from `_owner_since`; the alarm label and per-label threshold use it), [[#ac-6]] (the `inner` case; first-match mutation) |
| nm23-r10-2 (the hand-off mutation passes vacuously without forced contention) | [[#ac-6]] (each acquire holds ≥ 100 µs; ≥ 1,000 counted hand-offs through a seam counter, fewer fails as vacuous) |
| nm23-r10-3 (`memory_partition` turns a busy answer into a guessed partition; the `deadline` code unobservable through the verb path) | [[#r1-typed-refusal]] (ONE `verbs._raise_for_answer` used by `_call` and `memory_partition`), [[#ac-2]] (`memory_partition` `writer_busy` case; raw-request `deadline` case; two mutations), [[#files]] |
| nm23-r10-4 (AC-7's `grep_indexed` half cannot fail under R1.9's mutation; the hub row has no AC or key path) | [[#ac-7]] (`grep_indexed` marked regression coverage; an `unlink` case added to the discriminating `link` case), [[#r5]] (the counter in the `health` dict; the hub copies it; `_queue_row_is_hot` / `_hot_signature` name it), [[#ac-5]] (hot-row case; key-not-copied mutation), [[#files]] |
| nm23-r10-5 (23.1's body states the old owner order) | [[task-23.1-queue-and-drain#rev-round-10]] (R1.6 item 1 and its mutation synced to [[#r4]]'s order) |
| r10 approval note (the gate must name the MERGE sha) | [[#root]] header (the merge commit that lands bugs-112-113-118 on master, read from `git log --merges master`) |

rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r10-0dc2da3#nm23-r10-1]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r10-0dc2da3#nm23-r10-2]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r10-0dc2da3#nm23-r10-3]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r10-0dc2da3#nm23-r10-4]]
rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r10-0dc2da3#approval]]

## Folded rider: plan-2 r9 #s-3 (2026-10-19) {#w1c-rider}

Folded in by [[plan-review-2026-10-14#t11-folded-waves]] (W1-c). Plan-2's r9 audit found that a
memory WRITE resolves its partition through `_search.cached_replica(root)` unconditionally
(`verbs.py:246`, `memory_partition`), so a lagging replica can route a write to the wrong
partition (split-brain). This task already bounds `memory_partition`'s busy branch
(nm23-r10-3); the rider extends it to the write path.

rel: derives-from -> [[bsd-plan2-hooks-reproducible-r9-ffed3df#s-3]]

- **R-rider.** A write-intent partition resolution reads the writer (daemon op), never the
  replica; the replica stays the read-path source. A write that cannot reach the writer within
  its bound fails loudly (the existing busy/unreachable error), never falls back to the replica.
  {#w1c-rider-req}
- **AC-rider.** With a replica whose partition binding lags the writer's (planted in a tmp
  store), `memory add` lands in the writer's partition; a mutation that restores the
  unconditional `cached_replica` read for writes fails the test. {#w1c-rider-ac}

## Folded rider: the read-only fallback onto the writer's catalog (2026-10-19) {#bug136-rider}

Found by plan-3 ch-bsd r10 (S1/Q2): `Store(read_only=True)` resolves to the writer's own
`catalog.duckdb` when no snapshot exists, so any long-lived read-only holder in a process that
later writes reproduces bug-135 (`StaleDuckDBInstanceError … already attached by database
"rmx_ro"`). Plan-3 task 3.6 fixed the one holder that did it (`search.cached_replica`); the
enabler stays. This task owns it because it owns the read path.

- **R-bug136.** A read-only open never attaches the writer's primary catalog for longer than one
  bounded read; a store with no snapshot is read through a closed-after-use open or reports "no
  replica yet". {#bug136-req}
- **AC-bug136.** In one process: a read-only read of a snapshot-less store, then an in-process
  write, succeeds; a mutation that caches the read-only attach fails the test. {#bug136-ac}
