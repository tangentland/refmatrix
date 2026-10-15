---
gmd: "0.1"
id: task-23.5-read-path-and-holder-bounds
title: "Task 23.5: no cli-pool op waits on the writer lock without a bound — reads off _store_lock, bounded writer waits, the compaction tick's hold bounded, holders named — so the heartbeat stops depending on the longest writer hold (d9az)"
tags: [task, daemon, lock, read-path, heartbeat, watchdog, compaction, bug-115, bug-116, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-15
  updated: 2026-10-15
---

# Task 23.5: the read path and the non-harness lock holders {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending, NEW in revision round 7 (2026-10-15) under d9az: plan-23 OWNS the
> non-harness `_store_lock` holders and the heartbeat's coupling to the cli pool
> ([[plan-23-bounded-write-harness#scope-d9az]]). Not yet reviewed.
> Depends on: **bug-115/116 (0.78.2) MERGED TO `master`** (branch `bug-115-daemon-liveness`,
> commit `607d759` at the time of writing; the same merged-not-sha rule as 23.1's hotfix
> dependency), 23.0 (sandbox), 23.2 (recorder), 23.1 (`_FairLock` owner, R1.6 item 1; the learn
> drain, R9; `_compact_factslog_locked`, R3.7).
> Runs in parallel with 23.3 after 23.1. Blocks nothing in Wave 1; 17.3's hold bound
> ([[task-17.3-fleet-rollout#r2-measure]]) cites the same coupling.

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: implements -> [[plan-review-2026-10-14#t12-approvals]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#live-evidence]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#needs-user]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: related-to -> [[task-23.3-sync-between-file-yield]]
rel: related-to -> [[task-17.3-fleet-rollout]]
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
bound, so the cli pool keeps completing (and beating) through any writer hold. {#why-body}

## Facts at HEAD `77ac38f`, and on the 0.78.2 branch {#facts}

Read at HEAD `77ac38f` (`src/` unchanged since `0e77da3`, 0.78.1) unless marked 0.78.2.
- **Pools.** `CLI_OPS` (`daemon.py:6264`) routes 31 ops to the cli pool; everything else goes
  to the bg pool (`_handle`, `:3173`). Sizes on the live store: `pools cli=4 bg=12 disp=20`
  (`rmxd.log` 2026-10-15T00:13:21); `disp_pool` is `cli + bg + 4` workers (`:1864-1865`), and
  each dispatcher thread blocks on its op's future (`fut.result()`, `:3181`).
- **The 15 cli ops that take `_store_lock`**, each at HEAD with its first lock line:
  `ann_search` (`:5933`), `context` (`:4747`, a WRITE: `_learn_grep_hits` on a cli worker;
  its read already goes through `_read_with_fallback`), `derive_history` (`:4461`),
  `derive_status` (`:4369`, `:4389`), `grep_indexed` (`:4218`), `list_linkages` (`:3961`),
  `list_saved_queries` (`:4203`), `memory_recall` (`:6023`), `partition_add` (`:4028`, a
  write), `partition_audit` (`:4083`), `partition_list` (`:4182`), `partition_rename`
  (`:4045`, a write), `query` (`:4529`), `replica_audit` (`:5382`), `stats` (`:3732`). Every
  one is `with d._store_lock:` (unbounded).
  - **Correction to d9az's list:** `replica_relink` does NOT take the lock at HEAD. Its only
    `_store_lock` text is its docstring, "Deliberately does NOT take `_store_lock`"
    (`:5354`); its body re-points a symlink. It is listed here as checked, not as a holder.
- **The heartbeat** (`_start_heartbeat`, `:1305-1342`): once the cli pool exists, each tick
  submits a no-op to it and touches the file when the no-op completes (`:1330-1337`).
  `HEARTBEAT_INTERVAL_S` 5 (`:63`), `HEARTBEAT_STALE_S` 60 (`:66`, env
  `RMX_HUB_HEARTBEAT_STALE_S`).
- **The watchdog** (`hub.py`): a ping that answers within `WATCHDOG_PING_TIMEOUT_S` (2 s,
  `:46`) resets the miss count (`:264-266`); a restart needs `WATCHDOG_GRACE_MISSES` (3,
  `:48`) consecutive missed ticks at `WATCHDOG_INTERVAL_S` (15 s, `:39`) AND a heartbeat older
  than `HEARTBEAT_STALE_S` (`:305-317`).
- **The lock-free read path exists.** `_read_with_fallback(d, partition, fn, *, private,
  missing, writer_wait_s)` (`:4810`): the in-memory mirror, then the snapshot file
  `catalog.read.duckdb`, then the writer under `_store_lock` only when the read stores lack the
  partition, waiting at most `writer_wait_s` through `_writer_lock(d, wait_s)` (`:4911`), which
  raises `LookupError` on timeout. The mirror and snapshot lag the writer by
  `RMX_SNAPSHOT_DEBOUNCE_MS` (250 ms default, `:2642`). `memory_get`, `memory_search` and the
  other memory reads already use it and take no lock.
- **The compaction tick** (`_start_factslog_compact_tick`, `:2380-2400`) wakes every
  `RMX_FACTSLOG_COMPACT_INTERVAL_S` (1800 s) and runs `_compact_factslog_if_needed`, whose
  `dump_catalog_to_log()` runs inside one `with self._store_lock:` (`:2346`). On a copy of the
  live read snapshot (835 MB; 114,469 entities) the dump took 6.1 s (the r7 re-review's run).
- **The snapshot** (`_snapshot_catalog`, `:2652-2670`) holds `_store_lock` across a
  `CHECKPOINT` and an out-of-process `cp -p` of the writer slot (`_copy_out_of_process`,
  `:203`). Its hold grows with the catalog file; it is a non-harness holder too.
- **What 0.78.2 already does** (branch `bug-115-daemon-liveness`, `607d759`, read with
  `git show` in `/Volumes/littlebig/refmatrix-bug115`; NOT on `master` at `77ac38f`):
  1. `ping` is answered on the dispatcher thread, never from a work pool.
  2. Every cli-pool completion touches the heartbeat (`fut.add_done_callback`), besides the
     tick's own no-op.
  3. `daemon.call` sends `deadline_s` = its `timeout`; a cli-pool op whose deadline passed
     before a worker REACHED it raises `DeadlineExceeded` and is not run (counted; one log line
     a minute). The check is at op start only. It applies to every `CLI_OPS` op, so it also
     covers the two cli-pool writes `partition_add` / `partition_rename` (the caller is told
     "not run"; nothing is silent), although the code comment says "Writes are never dropped"
     (true of the bg pool).
  4. `daemon.call` never re-sends a request after it was sent.
- **What 0.78.2 does not do**, and so what this task must:
  1. An op ALREADY RUNNING on a cli worker that enters `with d._store_lock:` waits for the
     whole writer hold. Four such ops park all 4 workers; no cli op completes; the heartbeat
     (tick no-op and completions alike) stops for the rest of the hold.
  2. A restart now also needs ping misses, which need every dispatcher thread busy: more than
     `disp` (20) requests in flight, each blocked on a parked or queued cli future. A hook
     storm reaches that. So a writer hold longer than `HEARTBEAT_STALE_S` + 3 ticks still
     restarts the daemon under load, and without load every read still waits for the hold.
  3. Nothing bounds the compaction tick's hold or the snapshot's, and no log line names a
     holder, so the 00:11-00:13 stall cannot be attributed after the fact.
{#facts-body}

## Scope (d9az) {#scope}

In: the 15 lock-taking cli ops above and every future `CLI_OPS` op; the facts.log compaction
tick; the snapshot's hold (measured and named, bounded by R5's same rule); the heartbeat's
dependence on the cli pool; a holder name on every long hold.
Out: harness writers (23.1), `_sync_paths` and the watch flush (23.3: one sync at a time, the
lock released between files, which bounds the 80-110 s shape of the second incident), plan-17's
maintenance holds (17.1 / 17.3), and `ping` (0.78.2). {#scope-body}

## Requirements {#requirements}

1. **R1 Reads do not take `_store_lock` (the read-path rule).** Each READ op in `CLI_OPS` runs
   through `_read_with_fallback` (the mirror, then the snapshot), never through
   `with d._store_lock:`. Its writer fallback, used only when the read stores lack the
   partition, passes a bounded `writer_wait_s` (R2's wait), never `None`. Ops that may run long
   inside `fn` (`memory_recall`, `ann_search`) pass `private=True`, as `context` does today, so
   they do not hold the mirror's single use-lock. The ops: `ann_search`, `derive_history`,
   `derive_status` (one `_read_with_fallback` call per partition), `grep_indexed`,
   `list_linkages`, `list_saved_queries`, `memory_recall`, `partition_audit`,
   `partition_list`, `query`, `stats` (including `include_stale` and `include_health`, see
   AC-7). Their freshness is the snapshot's: at most `RMX_SNAPSHOT_DEBOUNCE_MS` behind the
   writer plus one refresh, the same contract `memory_get` already serves. {#r1}
2. **R2 A cli op that needs the WRITER waits a bounded time and says so.** `partition_add`,
   `partition_rename` (writes) and `replica_audit` (it pins the slot pair) take the lock
   through `_writer_lock(d, wait_s)` with
   `wait_s = min(<the request's remaining deadline_s>, RMX_CLI_WRITER_WAIT_S)`
   (`RMX_CLI_WRITER_WAIT_S` default 5 s). On a timeout the op answers
   `{"ok": false, "error": "writer busy: <holder> holding _store_lock for <s>s; not run"}`,
   using R4's holder name. It never parks a worker past that wait. {#r2}
3. **R3 `context`'s learn write leaves the cli worker.** The learn-on-hit write in `_op_context`
   (`daemon.py:4746-4748`, `_learn_grep_hits` under `with d._store_lock:`) becomes one
   `learn_queue.enqueue(root, pattern, hits)` (a lock-free `O_APPEND` line); 23.1's learn drain
   (R9, `idempotent=True`, insert-if-absent evidence) applies it on the next tick. The op keeps
   its "never fail a read" rule: an enqueue error is logged and the read still answers. {#r3}
4. **R4 Every long hold names its holder.** The daemon records, for each `_store_lock`
   acquisition, the holder's op name (the dispatcher sets a thread-local op name before it runs
   a handler; ticks and threads set their own: `learn`, `compact`, `snapshot`, `flush`,
   `watch`, `sync`) and the acquire time, beside 23.1's `_owner`. At release, a hold longer than
   `RMX_HOLD_ALARM_S` (default 10 s) logs one `rmxd.log` line `lock hold: <op> <s>s`. The
   current holder and its age are readable WITHOUT the lock (under `_FairLock._mu`) and are
   reported by `stats(include_health=True)` as `writer_holder: {op, held_s}` and used in R2's
   error. {#r4}
5. **R5 The compaction tick's hold is bounded; the dump runs off the lock.** The periodic
   compaction and the `compact_factslog` op (`_compact_factslog_if_needed`, both forced and
   size-gated) become two short holds around an unlocked dump:
   1. **Hold 1:** `CHECKPOINT`; `_copy_out_of_process(<writer slot>, <tmp>)`; record the live
      log's size `L0`. Release.
   2. **Unlocked:** open the tmp copy read-only and dump it to `facts.log.compact.tmp` with
      the same event form `dump_catalog_to_log` writes today (a `Store` method that takes a
      target path; the existing method keeps its signature for its other callers).
   3. **Hold 2:** append the live log's bytes `[L0, EOF)` (every event written during the dump,
      in order) to the tmp file, `fsync`, rename it over `facts.log`, reset the slot offsets.
      Release; then the floor bookkeeping and log lines, as today.
   Replay folds events in order, so "the state at `L0`" followed by the events after `L0` is the
   current state. 23.1's BOOT check (before the socket binds, no cli pool yet) keeps
   `_compact_factslog_locked()` in one hold (23.1 R3.7); this task changes only the paths that
   run while clients are served. The snapshot's own hold (CHECKPOINT + copy) is the same
   shape as hold 1 and is measured, not changed, by AC-8. {#r5}
6. **R6 The heartbeat no longer depends on the longest writer hold.** With R1-R3, no cli op
   waits on `_store_lock` longer than `RMX_CLI_WRITER_WAIT_S`, so cli completions (0.78.2 item 2)
   and the tick's no-op continue through any writer hold. The daemon REFUSES a configured
   `RMX_CLI_WRITER_WAIT_S` above `HEARTBEAT_STALE_S − 2 × HEARTBEAT_INTERVAL_S` (50 s at the
   defaults, the same margin as [[task-17.3-fleet-rollout#r2-measure]]): it clamps to that value
   and logs `RMX_CLI_WRITER_WAIT_S=<v> clamped to <c>s (heartbeat stale window)`. {#r6}
7. **R7 The rule is static, not a convention.** An AST test over `daemon.py` resolves each
   `CLI_OPS` name through `OPS` to its handler and asserts that the handler body contains no
   `with <x>._store_lock` and no `<x>._store_lock.acquire(` call, that every `_writer_lock(`
   call in it passes a second argument that is not the literal `None`, and that every
   `_read_with_fallback(` call passes `writer_wait_s=` with a value that is not the literal
   `None`. A new `CLI_OPS` op that takes the lock fails it. {#r7}
8. **R8 Census of every holder.** One full-suite run with 23.2's recorder installed (and R4's
   alarm at 1 s) lists every `_store_lock` acquisition site in `daemon.py` and `store.py` with
   its holder name and its maximum recorded hold. The implementation summary carries the list,
   and each site is assigned to the task that bounds it (23.1 harness, 23.3 sync/watch, this
   task's R2/R5, 17.1) or gets a new `bug_registry.md` row. This is a list of HOLD LENGTHS; it
   is unrelated to 23.1 R1.6's lock-presence census, which moves every unlocked site under the
   lock. {#r8}

## Acceptance criteria {#acceptance}

Every case runs in 23.0's sandbox on a recorded daemon (23.2's `recorded_daemon`) serving a short
tmp socket, with `RMX_HEARTBEAT_S=0.2` and `RMX_HUB_HEARTBEAT_STALE_S=3` unless stated.

1. **Reads answer through a long writer hold (R1, R6).** A test thread holds `_store_lock` for
   10 s (more than 3× the stale window). During the hold: each R1 op, called through
   `daemon.call(…, timeout=2)` from 8 concurrent client threads, answers `ok` within 1 s; the
   heartbeat file's age, sampled every 0.1 s, never exceeds 1 s. Mutation: `_op_stats` back on
   `with d._store_lock:` FAILS (its calls time out, and with 4 of them in flight the 4 workers
   park and the sampled age passes 3 s); the same for `_op_query`. {#ac-1}
2. **Writer-needing ops are bounded and named (R2, R4).** During the same hold, with
   `RMX_CLI_WRITER_WAIT_S=1`: `partition_add` answers within 1.5 s with an error that starts
   `writer busy:` and names the holder op the test set; the `partitions` table is unchanged after
   the hold. Mutation: `partition_add` on a plain `with d._store_lock:` FAILS (no answer within
   1.5 s). {#ac-2}
3. **The rule is static (R7).** Mutation: `with d._store_lock:` added to `_op_list_linkages`
   FAILS the AST test; so does `_writer_lock(d, None)` in `_op_partition_add`, and
   `_read_with_fallback(…, writer_wait_s=None)` in `_op_stats`. {#ac-3}
4. **`context` learns without the lock (R3).** With the lock held by a test thread, a `context`
   op whose answer has grep hits answers within 1 s and appends one `learn_queue` line; after
   the release, one tick's drain applies it (the `mentions` link and its evidence rows exist,
   counted once). Mutation: `_learn_grep_hits` called directly under `with d._store_lock:` as
   at HEAD FAILS (the op does not answer within 1 s). {#ac-4}
5. **Compaction off the lock, nothing lost (R5).** A store with 2,000 entities and 5,000 links
   and a `facts.log` above the threshold. A seam pauses the unlocked dump; meanwhile a
   competitor `link` and one `memory_add` through daemon ops each complete within 1 s; the seam
   releases. Then: the recorder shows two holds for the compaction, neither containing the
   dump (the dump runs with `held_by_current_thread()` False), and a throwaway
   `rebuild --from-log` of the new `facts.log` equals the live catalog BY NAME (entities, links,
   evidence and memory content), the competitor's link and memory included. Mutations, each
   must FAIL: the dump inside the lock (the competitor does not complete within 1 s); hold 2
   without the `[L0, EOF)` append (the rebuild lacks the competitor's link); `L0` read after
   hold 1 releases (a seam appends one event between the copy and the read, and the rebuild
   lacks it). {#ac-5}
6. **Holders are named (R4).** With `RMX_HOLD_ALARM_S=0.5`, a 1 s hold taken inside a `stats`
   test op logs `lock hold: <op> 1.…s`; during a hold, `stats(include_health=True)` (served
   off the lock by R1) reports `writer_holder.op` equal to the holder's op and `held_s` ≥ the
   elapsed time. Mutation: no op name recorded FAILS (`writer_holder.op` is null). {#ac-6}
7. **Read freshness and `include_stale` (R1).** A `link` through a daemon op, then `stats`: the
   new link count is visible within `RMX_SNAPSHOT_DEBOUNCE_MS` + 1 s. On a fixture with one
   tracked file touched after its sync, `stats(include_stale=True)` served off the snapshot
   reports the same `stale_files` list as the writer's `stale_files()` read under the lock by
   the test. If they differ, `include_stale` takes R2's bounded writer path instead, and this
   AC asserts that path's answer. {#ac-7}
8. **The coupling bound (R6).** `RMX_CLI_WRITER_WAIT_S=500` at daemon start logs the clamp line
   and the effective wait is `HEARTBEAT_STALE_S − 2 × HEARTBEAT_INTERVAL_S`. Mutation: no clamp
   FAILS. The census (R8) is in the implementation summary with every site assigned, the
   snapshot's measured hold among them. {#ac-8}

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/daemon.py` | R1 (the 11 read ops on `_read_with_fallback`), R2 (`_writer_lock` with a bounded wait in 3 ops), R3 (`context` enqueues), R4 (holder name + alarm + `writer_holder`), R5 (two-hold compaction), R6 (clamp) |
| `src/refmatrix/store.py` | the dump-to-path form of `dump_catalog_to_log` (R5.2) |
| `tests/` | AC-1..AC-8 in a new `tests/test_read_path_holder_bounds.py`; the AST test (R7) |

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
