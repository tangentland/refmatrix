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
> clean); see [[#rev-round-8]].
> Depends on: 23.0 (sandbox), 23.2 (recorder), 23.1 (`_FairLock` owner, R1.6 item 1; the learn
> drain, R9; `_compact_factslog_locked`, R3.7). **bug-115/116 (0.78.2) merged to `master`:
> SATISFIED** (`607d759`, `1c86d9c` and bug-117's `391ffeb` are ancestors of `master` `b381b6d`;
> HEAD `23ad703`).
> Runs in parallel with 23.3 after 23.1. Blocks nothing in Wave 1; 17.3's hold bound
> ([[task-17.3-fleet-rollout#r2-measure]]) cites the same coupling.
> Cross-plan interface: the `_store_lock` + DuckDB maintenance + file swap shape is converged
> into ONE helper by plan-18 (d9bf): `Daemon._catalog_hold` over `catalog_maint.CatalogHold`,
> built by 18.2 (its R11, "the shared catalog-hold helper") and extended with the swap half by
> 18.3 (its R8, `#r8-one-helper`). This task adds no second mechanism for that shape ([[#r4]],
> [[#r5]]).

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
rel: depends-on -> [[task-18.2-catalog-maintain-step]]
rel: related-to -> [[task-18.3-offline-reclaim#r8-one-helper]]
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
      like `DeadlineExceeded`: `{"ok": false, "error": <message>}`, no `op … raised` line, and
      it never reaches `_fast_exit_if_invalidated`. The two refusals share ONE rate-limited
      counter and log path: `_note_expired_read` becomes `_note_refused(reason, op, detail)`
      (`reason` = `deadline` or `writer-busy`), one function, not a second one beside it.
      {#r1-helper}
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
      writer plus one refresh, the contract `memory_get` serves today. **Known exception,
      bug-112 (nm23-r8-3):** a private read that opens `catalog.read.duckdb` while another
      in-process connection to that path is still open gets that connection's database, so
      its freshness is bounded by the oldest overlapping private reader, not by the debounce.
      AC-7 pins both halves. {#r1-freshness}
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
   - **One registry.** `_inflight_ops` stays the one record of who is running. Its value grows
     from `(op, t0)` to `(op, t0, ident)`: the dispatcher still creates the entry with
     `ident = None`, and R2's worker-side wrapper sets `ident = threading.get_ident()` under
     `_inflight_lock` when the handler starts (the worker, not the dispatcher, is the thread
     that takes the lock). Ticks and threads that take `_store_lock` outside an op register an
     entry through one context manager, `Daemon._inflight(name)`, which the dispatcher path
     uses too: `learn`, `compact`, `snapshot`, `flush`, `watch`, `sync`. `_final_flush`'s
     reader is updated to the 3-field value, and its "nothing tracked — … check the watcher or a
     background tick" branch now names ticks as well. No second registry is added.
   - **The lock side.** 23.1's `_FairLock` owner field gains `_owner_since` (monotonic, set
     with `_owner` under `_mu`), and `_FairLock.holder() -> (ident, since) | None` reads both
     under `_mu`, without taking the lock. 23.2's `HoldRecorder` gets one explicit
     pass-through, `holder()`, in `tests/lockhold.py` (the same pattern as 23.1's
     `held_by_current_thread()`; 23.2's approved spec is not reopened).
   - **The name.** `writer_holder` = the `_inflight_ops` entry whose `ident` equals the owner's
     ident: `{op, held_s}`; an owner with no entry reports `{op: "untracked thread <name>",
     held_s}`, never null. `stats(include_health=True)` reports it, and R1's / R2's
     `WriterBusy` message uses it.
   - **The alarm.** At release, a hold longer than `RMX_HOLD_ALARM_S` (default 10 s) logs one
     `rmxd.log` line `lock hold: <op> <s>s`.
   - **Cross-plan interface (d9bf).** plan-18's `Daemon._catalog_hold` (18.2 R11; 18.3 R8)
     registers its holder through `Daemon._inflight(<step name>)`, so R4 names it like any
     tick, and R4's `lock hold:` alarm fires in `_FairLock`'s release for every holder, the
     helper's included; the helper's own hold ring is its measurement ledger, not a second
     alarm or holder registry. This task specifies no lock mechanism of its own for it.
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
   - **Cross-plan interface (d9bf).** `_snapshot_catalog`'s hold is the `_store_lock` +
     DuckDB maintenance (`CHECKPOINT`) + file swap shape that plan-18 converges into
     `Daemon._catalog_hold` (18.2 R11 ports the snapshot tick onto it; 18.3 R8 adds the swap
     half). This task adds only the `pin_to` capture to that existing hold: on the helper,
     `pin_to` (record `L0` inside the hold, hard-link before `_snapshot_lock` releases) is part
     of the snapshot port's contract. Hold 2 (append, rename, offset reset) is the same
     hold-and-swap shape: it goes through `_catalog_hold` when 18.2 is merged before 23.5 is
     implemented; otherwise it is today's plain `with self._store_lock:` under
     `Daemon._inflight("compact")`, and 18.2/18.3's port list gains the compaction site (18.3's
     Q-C already recommends compaction on the helper). No second hold-and-swap mechanism is
     specified here.
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
7. **R7 The rule is static and follows helpers to a fixpoint (nb23-r8-1).** An AST test over
   `daemon.py` resolves each `CLI_OPS` name through `OPS` to its handler, then follows every
   call to a same-module function and every `d.<m>(` / `self.<m>(` call to a `Daemon` method,
   to a fixpoint (nested lambdas and `def`s included). `_writer_lock` and `_read_with_fallback`
   are checked at the CALL, not entered. Any reachable occurrence of these FAILS:
   - `with <x>._store_lock` or `<x>._store_lock.acquire(` without a `timeout`;
   - `_writer_lock(` without a second argument, or with the literal `None`;
   - `_read_with_fallback(` anywhere except inside `_cli_read`'s body.
   At HEAD the walk flags 24 ops ([[#facts]]); after R1-R3 it flags none. The test also asserts
   that `_store_health` and `_memory_partition` contain no `_st()` call (R1.6), and that
   `CLI_OPS` contains none of `snapshot`, `partition_add`, `partition_rename`. {#r7}
8. **R8 Census of every holder and every read path.** One full-suite run with 23.2's recorder
   installed (and R4's alarm at 1 s) lists every `_store_lock` acquisition site in `daemon.py`
   and `store.py` with its holder name and its maximum recorded hold. Each site is assigned to
   the task that bounds it (23.1 harness, 23.3 sync/watch, this task's R2/R5, 17.1, 18.2/18.3)
   or gets a new `bug_registry.md` row. On a copy of the live read snapshot (835 MB) it also
   records, per cli read op, its p99 on the mirror path and on the private path over 200 calls;
   that table decides `MIRROR_OPS` (R1.7). It records the snapshot's hold (hold 1) and the
   compaction's tail hold on that copy. The implementation summary carries all three tables.
   This is a list of HOLD LENGTHS and read latencies; it is unrelated to 23.1 R1.6's
   lock-presence census. {#r8}

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
   Mutations, each must FAIL: `replica_audit` on a plain `with d._store_lock:` (no answer within
   1.5 s); `_cli_writer_wait` ignoring `_op_ctx.expires` (the 0.5 s case takes 1 s);
   `partition_add` left in `CLI_OPS` (the AST case, and with 4 concurrent calls the 8-client
   reads miss 1 s). {#ac-2}
3. **The rule is static and transitive (R7).** The AST test passes after R1-R3. Mutations, each
   must FAIL it: `with d._store_lock:` added to `_op_list_linkages`; a new module-level helper
   `_peek(d)` that does `with d._store_lock:` called from `_op_list_linkages` (the transitive
   case a direct-body rule missed); `_writer_lock(d, None)` in `_op_replica_audit`;
   `_read_with_fallback(…)` called directly from `_op_memory_search`; `snapshot` back in
   `CLI_OPS`; a `d._st()` call added to `_store_health`. {#ac-3}
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
   byte-identical to before). {#ac-5}
6. **Holders are named (R4) and health reads the read path (R1.6; ns23-r8-1, nm23-r8-2).**
   With `RMX_HOLD_ALARM_S=0.5`, a test-registered BG-pool op takes a 1 s hold (a cli op that
   took the lock would fail R7): `rmxd.log` has `lock hold: <that op> 1.…s`. During a second
   such hold, `stats(include_health=True)` answers within 1 s with `writer_holder.op` equal to
   the holder's op, `held_s` ≥ the elapsed time, and `memory_read_ok: true` (read from the
   snapshot, not the writer). A compaction tick's tail hold is reported as `compact`.
   Mutations, each must FAIL: no op name recorded (`writer_holder.op` is null or "untracked");
   the ident set on the dispatcher thread instead of the worker (`writer_holder.op` is
   "untracked thread rmxd-bg-…"); `_store_health` called inside the outer `stats` `fn` with
   `stats` in `MIRROR_OPS` (the op hangs on the mirror's non-re-entrant `_use_lock` and misses
   1 s). {#ac-6}
7. **Read freshness and `include_stale` (R1.5, R1.8; nm23-r8-3).**
   - A `link` through a daemon op, then `stats`: the new link count is visible within
     `RMX_SNAPSHOT_DEBOUNCE_MS` + 1 s.
   - On a fixture with one tracked file touched after its sync, `stats(include_stale=True)`
     (served off the snapshot) reports the same `stale_files` list as the writer's
     `stale_files()` read by the test under the lock, after one debounce. No branch: the spec
     decided the snapshot; a difference fails the case.
   - **Private reads across a forced snapshot.** A private reader A is held open inside its
     `fn` by a seam; a `link` and a forced `snapshot` follow; A is released and closes; then a
     private read B sees the new link. This half is REQUIRED; if it is RED at implementation
     time, 23.5 does not close and bug-112 is recorded as its dependency (the design does not
     change; only the gate moves).
   - **bug-112, pinned as the known exception.** A private read B' opened while A is still
     open returns A's database (the pre-link count), asserted with a message naming bug-112.
     bug-112's fix owns inverting this assertion. {#ac-7}
8. **The coupling bound (R6) and the census (R8).** `RMX_CLI_WRITER_WAIT_S=500` at daemon start
   logs the clamp line and the effective wait is `HEARTBEAT_STALE_S − 2 × HEARTBEAT_INTERVAL_S`.
   Mutation: no clamp FAILS. The census (R8) is in the implementation summary with every site
   assigned, the snapshot's measured hold and the compaction tail hold among them, and the
   per-op p99 table that justifies each `MIRROR_OPS` member. {#ac-8}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/daemon.py` | R1 (`_cli_read`; `WriterBusy`; `_note_expired_read` → `_note_refused`; the 11 read ops, the 10 `_read_with_fallback` sites and `_store_health`'s 2 on `_cli_read`; `writer_wait_s` required; `snapshot` out of `CLI_OPS`; `_op_stats` in three steps; `_store_health` and `_memory_partition` off the writer connection; `MIRROR_OPS`), R2 (`partition_add` / `partition_rename` out of `CLI_OPS`; `CLI_WRITE_OPS = {"stop"}`; the worker-side wrapper and `_op_ctx`; `_cli_writer_wait`; `_cli_writer_lock` in `replica_audit`), R3 (`context` enqueues), R4 (`_inflight_ops` 3-field value; `Daemon._inflight(name)`; `_FairLock._owner_since` + `holder()`; alarm; `writer_holder`), R5 (`_snapshot_catalog(pin_to=)`; two-hold compaction with the ts-order refusal), R6 (clamp) |
| `src/refmatrix/store.py` | the dump-to-path form of `dump_catalog_to_log` that also returns its largest `ts` (R5.2) |
| `tests/lockhold.py` | `HoldRecorder.holder()`, one explicit pass-through (R4; nm23-r8-2). 23.2's other surface is unchanged |
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
