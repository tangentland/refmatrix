---
gmd: "0.1"
id: task-18.2-catalog-maintain-step
title: "Task 18.2: `catalog_maintain` — one bounded, measured CHECKPOINT + free-space read per store on 17.2's nightly tick, with hold bands, a lock-wait timeout, and the snapshot's own CHECKPOINT hold measured"
tags: [task, daemon, hub, duckdb, catalog, checkpoint, maintenance, lock]
metadata:
  node_type: task
  status: pending
  created: 2026-10-15
  updated: 2026-10-15
---

# Task 18.2: the `catalog_maintain` step {#root}

> Plan: [plan-18-duckdb-store-maintenance](../plan-18-duckdb-store-maintenance.md)
> Status: Pending (spec written 2026-10-15; not yet reviewed)
> Wave: 4 ([[plan-review-2026-10-14#t10-waves]]: "plan-18 as a 17.2 step").
> Depends on: 17.2 (the `maintenance_steps` registry, `maintain.json`, the step obligations of
> 17.2 R2); 17.1 R11 / R12 (the single-flight reply and `runs.jsonl` line shapes it copies);
> 23.0 (test sandbox); 23.2 (`recorded_daemon`, the per-hold statement counts); 18.1 (its Table
> B verdict sets the default `RMX_CATALOG_BAND_MODE`; everything else can be built first).
> Not on 23.1: the step is store-wide and partition-free, so it takes `_store_lock` directly and
> does not go through `bind(partition_name)` (R2).

rel: part-of -> [[plan-18-duckdb-store-maintenance]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]
rel: depends-on -> [[task-17.1-vectors-maintain-op#r11-single-flight]]
rel: depends-on -> [[task-17.1-vectors-maintain-op#r12-ledger]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: depends-on -> [[task-18.1-catalog-measurement]]
rel: implements -> [[plan-18-duckdb-store-maintenance#contract-2026-10-14]]
rel: related-to -> [[task-23.1-queue-and-drain#r1]]
rel: related-to -> [[project_bus_retention_global_queues]]
rel: depends-on -> [[feedback_causal_story_before_evidence]]

## Why {#why}

The plan's contract ([[plan-18-duckdb-store-maintenance#contract-2026-10-14]]) puts plan-18 on
17.2's tick as a registered step. At HEAD a CHECKPOINT already runs after every write burst
([[task-18.1-catalog-measurement#facts]] F1). So the step's value is not the CHECKPOINT itself. It
does three things:

- **It measures free space nightly.** Nothing reports it today, and `store_bytes` counts a
  bloated writer twice (18.1 F5).
- **It turns that into a hot hub row** when 18.1's bands say a reclaim is due.
- **It times every CHECKPOINT that holds `_store_lock`,** its own and the snapshot tick's. That
  gives the long holds a number.

Live evidence for that last point, stated as observed, with its cause NOT measured
(`feedback_causal_story_before_evidence`):

- On 2026-10-15 rmxd.log shows `facts.log compacted 294090489 -> 264498314 bytes` at 00:11:15.
  That compaction runs `dump_catalog_to_log()` under `_store_lock` (`daemon.py:2346-2354`).
- Then rmxd.log shows nothing until `pool drain disp: timed out after 10s, 3 of 20 workers still
  running (in flight: stats, stats, stats)` at 00:13:16.
- hub.log shows `graceful stop … 'stop_op': 'skipped: not answering ping (SIGTERM sent now)'`
  and `watchdog kickstarted` at 00:13:18.

What held the daemon between 00:11:15 and 00:13:16 is unknown. A step that adds its own hold
under the same lock must therefore bound three things: its wait for the lock, the work inside
its hold, and the seconds of that hold. It must also say how each is measured (R2, R4). {#why-body}

## Facts at HEAD `55f043d` (`src/` unchanged through `0611d2f`) {#facts}

The catalog facts F1-F7 are in [[task-18.1-catalog-measurement#facts]]. The lock and liveness
facts this step depends on:

- **L1 `_FairLock`** (`daemon.py:242`) is strict FIFO and supports
  `acquire(blocking=True, timeout=None) -> bool` (`:268`); a waiter that times out withdraws from
  the queue. It is not re-entrant.
- **L2 How a long hold becomes a restart** (read from code; the 00:11-00:13 incident's cause is
  not measured):
  - `stats` is in `CLI_OPS` (`daemon.py:6264`) and its handler takes `_store_lock`
    (`_op_stats`, `:3731-3732`). The hub's alert tick calls it for every store
    (`hub.py:630-659`).
  - The heartbeat file is touched only when a no-op submitted to the 4-worker cli pool COMPLETES
    (`_start_heartbeat`, `:1305-1339`). So when every cli worker is queued on `_store_lock`, the
    heartbeat stops.
  - The hub restarts a daemon whose ping misses `RMX_HUB_WATCH_GRACE_MISSES` (3) ticks of
    `RMX_HUB_WATCH_INTERVAL` (15 s) with a heartbeat older than `HEARTBEAT_STALE_S` (60 s)
    (`hub.py:39-49`, `_check` `:257-321`). A ping times out after
    `RMX_HUB_WATCH_PING_TIMEOUT` = 2 s (`hub.py:46-47`).
  - So a `_store_lock` hold longer than about 60 s, with 4 lock-taking cli ops queued, can get a
    working daemon restarted. A hold longer than 2 s can make pings miss.
- **L3 The snapshot's hold** (18.1 F1) is CHECKPOINT + child `cp` + `os.replace`, inside one
  `_store_lock` hold, after every write burst. Nothing times it. The `cp` of this store's 835 MB
  snapshot takes 0.16-0.20 s warm (18.1 F7). The CHECKPOINT's share is unmeasured.
- **L4 What NOT to call.** `_op_checkpoint` (`daemon.py:3871`) rebuilds
  `idx_entity_links_lk_concept` (776,359 rows here) inside its hold. `Store.vacuum`
  (`store.py:7260`) is row deletion, not space reclamation (18.1 F3).
- **L5 The facts.log compaction** is size-gated at 256 MiB (`_factslog_threshold`, `:2267`).
  It has a 10 % minimum-reclaim floor (`_FACTSLOG_MIN_RECLAIM`, `:2302`) and runs on its own 30-min
  thread (`_start_factslog_compact_tick`, `:2380`). At ~00:20 this store's `facts.log` was
  283,937,960 bytes, above the 268,435,456 threshold again. The 00:11 run reclaimed 10.06 %, so
  no floor was set (18.1 F4). That compaction is not this plan's; it is a lock holder this step
  must not stack behind (R2 c).
- **L6 Alerts already have a home.** The hub's queue row carries only actionable health keys
  (`hub.py:648-659`). `_queue_row_is_hot` (`:1231`) and `_hot_signature` (`:1211`) decide when a
  hot row is news (news on arrival or on a material change, with a rare re-assert; bug-048). 17.2
  R5 alerts only on consecutive `failed` / `refused` outcomes (plus `orphan_cap` and `stuck`), so
  a step's informational signal belongs in health, not in 17.2.

{#facts-body}

## Requirements {#requirements}

1. **R1 Verb, op, surfaces.** {#r1-verb}
   - Verb `rmx_catalog_maintain(dry_run: bool = False, status: bool = False,
     checkpoint: bool = True, *, invoked_by: str) -> dict`; daemon op `catalog_maintain`; CLI
     `rmx catalog maintain [--dry-run] [--status] [--no-checkpoint]` (a new `catalog` group); MCP
     parity through the verb-parity test.
   - `invoked_by` follows 17.1 R1 ([[task-17.1-vectors-maintain-op#r1-verb]]). It is
     keyword-only, set by the adapter (`cli`, `mcp`, `hub`) and never by a surface caller. The
     verb checks it against the closed set `{cli, mcp, hub}` and raises `ValueError` naming the
     value otherwise.
   - The CLI calls the daemon only. With the daemon not answering it exits non-zero with
     `daemon not answering; catalog maintain never runs in-process` and opens no file under
     the root (bug-110: an in-process open of the slot drops the daemon's lock).
2. **R2 One run, in this order, with ONE hold.** {#r2-order}
   - (a) **Lock-free pre-check.** `stat` the writer slot (`d._st().db_path`) and its `.wal`:
     `file_bytes_before`, `wal_bytes_before`.
   - (b) **WAL gate.** If `wal_bytes_before > RMX_CATALOG_WAL_MAX_BYTES` (default 64 MiB, 4× DuckDB's
     16 MiB auto-checkpoint threshold, 18.1 F1), this run does no CHECKPOINT. The outcome is
     `refused:wal_large` (counted by 17.2 R5) and the measurement (d) still runs. A WAL that
     big means the snapshot tick and DuckDB's auto-checkpoint have both stopped folding it. That
     is a defect signal, and a CHECKPOINT of an unknown-size WAL is an unbounded hold.
   - (c) **Bounded wait.** `_store_lock.acquire(timeout=RMX_CATALOG_LOCK_WAIT_S)` (default
     30). On timeout: outcome `skipped:lock_busy`, `ok: false`, no hold, `wait_s` reported. It
     never queues behind a facts.log compaction or a `vectors_maintain` dataset hold and then
     adds its own (L5).
   - (d) **Inside the one hold, exactly two statements.** `CHECKPOINT` is skipped on a dry run,
     with `checkpoint=False`, after (b), or under R4's downgrade. Then
     `PRAGMA database_size`. Nothing else runs in the hold: no DDL, no index rebuild (L4), no
     table scan, no `Store.vacuum`, no fragment flush.
   - (e) **Release, then measure the hold.** `wait_s` runs from the acquire call to its
     return. `hold_s` runs from the acquire's return to the release, measured by
     `time.monotonic()` in production code around the hold (not by 23.2's test-only recorder).
     The CHECKPOINT's own seconds are `checkpoint_s`.
   - (f) **Lock-free after.** `stat` the slot and `.wal` again: `file_bytes_after`,
     `wal_bytes_after`. Then compute `f = free_blocks / total_blocks` and the band (R5), write
     `<root>/maintain/catalog_state.json` (atomic tmp + rename), append the ledger line (R6),
     and log one `rmxd.log` line with `hold_s`, `wait_s`, `checkpoint_s`, `f` and the band.
   - **Why not `bind`.** 23.1's `bind(partition_name)` binds a partition inside the hold for
     partition-scoped writes ([[task-23.1-queue-and-drain#r1]]). A CHECKPOINT is store-wide and
     binds nothing. So the step takes `_store_lock` itself, as `_snapshot_catalog` does. With
     23.1 R1.6 adopted, nothing in (d) is a `Store` writer method that asserts the lock, and
     the step's hold is the one `with`.
3. **R3 Single-flight and lock-free status.** 17.1 R11's shape
   ([[task-17.1-vectors-maintain-op#r11-single-flight]]). A call during a run returns
   `{"ok": false, "already_running": true, "run_id", "started_at"}` and starts nothing.
   `status=True` returns the running state, or the last report when idle. Both read an
   in-process run state guarded by its own `threading.Lock`, never `_store_lock`. {#r3-single-flight}
4. **R4 Hold bands (Table D), pre-registered 2026-10-15 before any run.** {#r4-hold}

   | band | `hold_s` of one run | action |
   |---|---|---|
   | D0 | `≤ RMX_CATALOG_HOLD_ALARM_S` (2) | `ok` |
   | D1 | `2 < hold_s ≤ RMX_CATALOG_HOLD_MAX_S` (10) | `ok` plus `hold_alarm` in the report and a `rmxd.log` warning |
   | D2 | `hold_s > 10` | `ok` plus `hold_over`. `catalog_state.json` gets `checkpoint_disabled: {since, hold_s, run_id}`. Every later run with `invoked_by="hub"` skips the CHECKPOINT and reads only the PRAGMA (`checkpoint: "disabled_hold_over"`). Health carries `catalog_hold_over: true`, which makes the hub row hot (R7). A hand run (`cli` / `mcp`) with `checkpoint=True` whose `hold_s ≤ 10` clears the flag. |

   - **Why these numbers** (from L2, not from data): 2 s is the hub's ping timeout, so a shorter
     hold cannot make a ping miss. 10 s is a sixth of the 60 s heartbeat staleness that, with the
     cli pool queued on the lock, ends in a restart.
   - **How it is measured:** in production, R2 (e) on every run, and the D band is computed from
     that number. In tests, by 23.2's recorder, which must agree with the reported `hold_s` within
     50 ms (AC-1). Following 23.2 R5 ("seconds are an alarm, counts are the bound"), the test bound
     is the statement count in the hold (AC-2), not seconds.
   - The downgrade protects only against THIS step's hold. It leaves the snapshot tick's
     CHECKPOINT (R8) alone, because that one is the read path's freshness.
5. **R5 The reclaim band** (18.1 Tables A and B, [[task-18.1-catalog-measurement#r3]]).
   `RMX_CATALOG_BAND_MODE` selects how the band is read: {#r5-band}
   - `free_ratio`: Table A's edges are applied to `f` and `reclaimable_est =
     free_blocks × block_size`.
   - `growth` (the default until 18.1's verdict sets it): the band is `A2` when `file_bytes ≥ 2 ×`
     the store's baseline, else `A0`. The baseline is the first successful run's `file_bytes`,
     written once to `catalog_state.json` (`baseline_file_bytes`, `baseline_at`) and never moved
     by a later run. A successful 18.3 reclaim resets it.
   - On A2, health carries `catalog_reclaim_due: true`, which makes the hub row hot (R7). A1 is
     reported and does not make the row hot.
6. **R6 The ledger.** Every completed run appends one fsynced line to
   `<root>/maintain/runs.jsonl` in 17.1 R12's shape ([[task-17.1-vectors-maintain-op#r12-ledger]]):
   `{run_id, step: "catalog_maintain", invoked_by, dry_run, ok, started_at, finished_at,
   outcomes: {"catalog": <outcome>}}`, plus `wait_s, hold_s, checkpoint_s, checkpoint,
   file_bytes_before, file_bytes_after, wal_bytes_before, wal_bytes_after, block_size,
   total_blocks, used_blocks, free_blocks, f, band, band_mode, hold_band`. {#r6-ledger}
7. **R7 Health and the hub row** (L6). {#r7-health}
   - `_store_health` (`daemon.py:3744`) gains `catalog: {file_bytes, wal_bytes, f, band,
     band_mode, measured_at, hold_s_last, checkpoint_disabled, snapshot_hold_s_last,
     snapshot_hold_s_max_24h, snapshot_checkpoint_s_last}`. These are read from
     `catalog_state.json` and R8's in-memory ring plus one `stat` of the slot and `.wal`. There is
     no DuckDB call and no `_store_lock`.
   - `catalog_wal_large` is computed live from that `stat` (`wal_bytes > RMX_CATALOG_WAL_MAX_BYTES`),
     so a growing WAL shows without waiting for the night.
   - The hub's row builder (`hub.py:648-659`) copies `catalog_reclaim_due`, `catalog_wal_large` and
     `catalog_hold_over` into the row only when true. `_queue_row_is_hot` (`:1231`) treats each as
     hot, and `_hot_signature` (`:1211`) lists each as a reason. Each therefore alerts once on
     arrival and re-asserts at the existing cadence (bug-048), with no new alert mechanism.
8. **R8 Measure the CHECKPOINT that already runs.** `_snapshot_catalog` (`daemon.py:2621`)
   times its own hold (acquire → release around `:2651-2670`) and its CHECKPOINT
   (`:2653`). It keeps both in an in-memory ring covering the last 24 h, read lock-free by R7.
   It logs one `rmxd.log` line when the hold exceeds D1's 2 s edge. Its behaviour does not
   change. This is the baseline the nightly hold is compared against, and the only number for
   L3. {#r8-snapshot-hold}
9. **R9 Registration on 17.2** ([[task-17.2-hub-nightly-tick#r2-registry]],
   [[task-17.2-hub-nightly-tick#r7-unarmed]]). {#r9-register}
   - `MaintenanceStep(name="catalog_maintain", op="catalog_maintain", args=lambda root,
     dry_run, today: {"dry_run": dry_run}, requires_arming=False, reason=…,
     after_idle=<below>)` is registered LAST, as 17.2 R2's order says. `invoked_by="hub"` is
     set by 17.2's call path (17.1 R1), not by `args`.
   - **`requires_arming=False`**, with this reason: "a CHECKPOINT folds the WAL into the file the
     daemon already writes, the statement the snapshot tick runs after every write burst
     unarmed (`daemon.py:2653`), plus a metadata PRAGMA; it deletes nothing, rewrites no table
     and changes no row". The contract expected `True` because "a CHECKPOINT that rewrites the
     catalog is user-visible state". That premise does not hold at HEAD (18.1 F1, F2), so the
     difference is put to the user (plan open question Q4). The deleting action, the reclaim, is
     not on this tick at all (18.3).
   - **`after_idle`** names `vectors_maintain` and `memory_compile`, of those registered at hub
     start. Both take `_store_lock` in the same daemon for long holds. Waiting for them to go
     idle keeps this step's bounded wait (R2 c) from timing out behind them every night. While
     either is `still_running` or `stuck`, this step is `deferred` and stays due (17.2 R2).
   - **Not after `factslog_backup`.** That answers plan-17 open item 7
     ([[plan-17-nightly-store-maintenance#open-after-revision]]): 17.4 R2 copies `facts.log`
     from an open descriptor and never reads the catalog, and a CHECKPOINT never writes
     `facts.log`. So the two cannot tear each other, and the contract's "must not run at the same
     time" line is dropped.
   - **The bug-105 order** (the contract's "first CHECKPOINT after `repair-index --fragments`")
     is satisfied at HEAD. The live repair was applied 2026-10-14 to refmatrix, cliquedb, cliquet
     and viascope, and the other four were clean (bug-105 row). Since then the snapshot tick
     has checkpointed every store many times. The step adds no new kind of write.
10. **R10 Rollout.** After the deploy that carries 17.2 and this step: one hand
    `rmx catalog maintain --dry-run`, then one hand `rmx catalog maintain`, on each of the 8
    registered stores. No arming is needed (R9). Then one night is observed: every registered
    store has exactly one `invoked_by: "hub"` line, and each line's D band is recorded. The
    per-store table goes in the implementation summary. A D2 night on any store is a bug-registry
    row before the plan closes. {#r10-rollout}

## Acceptance criteria {#acceptance}

All tests run in the 23.0 sandbox, on real tmp daemons with short roots, with 23.2's
`recorded_daemon` installed as `_store_lock` before any op.

1. **AC-1 (one bounded hold, measured where it happens).** On a tmp store with a non-empty WAL,
   one run gives:
   - `wal_bytes_after < wal_bytes_before`, and the PRAGMA fields are present;
   - a ledger line (R6);
   - exactly ONE recorded hold for the run, whose duration is within 50 ms of the reported
     `hold_s`.

   Mutations: CHECKPOINT and PRAGMA in two holds FAILS (two holds); `hold_s` measured around the
   whole op, wait included, FAILS (more than 50 ms off with a competitor holding the lock 0.5 s
   first). {#ac-1}
2. **AC-2 (only the two statements).** The run is marked `max_writes_per_hold(statements=2)`.
   Mutations: calling `_op_checkpoint`'s body (DROP/CREATE INDEX + CHECKPOINT) FAILS (4
   statements); adding `Store.vacuum` FAILS. {#ac-2}
3. **AC-3 (bounded wait; the incident shape).** A competitor thread holds `_store_lock` on an
   event the test sets after 10 s, with `RMX_CATALOG_LOCK_WAIT_S=1`. The op returns
   `skipped:lock_busy` within 2 s with `wait_s ≈ 1`, records no hold of its own, and writes a
   ledger line with `ok: false`. The competitor then releases, and a second run succeeds.
   Mutation: a blocking `acquire()` without the timeout FAILS (the return comes only after
   10 s). {#ac-3}
4. **AC-4 (WAL gate).** With `RMX_CATALOG_WAL_MAX_BYTES=1` and a non-empty WAL, the outcome is
   `refused:wal_large`, no CHECKPOINT runs (`wal_bytes_after == wal_bytes_before`) and the PRAGMA
   fields are still reported. `_store_health` reports `catalog_wal_large: true`, and a hub queue
   row built from that health is hot. Mutation: the gate removed FAILS (the WAL shrinks).
   {#ac-4}
5. **AC-5 (hold bands and the downgrade).** The in-process routine takes a `checkpoint` seam (a
   keyword of the routine, not an op argument, as in 17.1 AC-2; default runs `CHECKPOINT`). With
   a seam that sleeps 0.3 s, `RMX_CATALOG_HOLD_ALARM_S=0.1` and `RMX_CATALOG_HOLD_MAX_S=0.2`:
   - run 1 (cli) → `hold_over` and `checkpoint_disabled` written;
   - run 2 (`invoked_by="hub"`) → the seam is NOT called, outcome `ok`,
     `checkpoint: "disabled_hold_over"`, and health `catalog_hold_over: true`;
   - run 3 (cli, fast seam) → the flag is cleared;
   - a run with a 0.15 s seam → `hold_alarm` and no downgrade.

   Mutation: the downgrade not persisted FAILS (run 2 calls the seam). {#ac-5}
6. **AC-6 (single flight, lock-free status).** A run's seam blocks on an event inside the hold.
   `status=True` and a second call each return within 1 s, and the second says
   `already_running`. The recorder shows no second hold. Mutation: status taking `_store_lock`
   FAILS (it returns only after release). {#ac-6}
7. **AC-7 (dry run).** No CHECKPOINT (`wal_bytes_after == wal_bytes_before`), the slot's size and
   mtime are unchanged, `would_checkpoint: true` is reported, and the ledger line has
   `dry_run: true`. {#ac-7}
8. **AC-8 (no fallback).** The CLI with the daemon stopped exits non-zero with the R1 message.
   Every file under the root keeps its mtime_ns, and a spy on `duckdb.connect` in the CLI
   process counts zero. {#ac-8}
9. **AC-9 (`invoked_by`).** A CLI run, an MCP run and a hub-invoked run append `cli`, `mcp` and
   `hub`. Neither surface exposes the parameter. `invoked_by="hand"` raises `ValueError` and
   appends nothing. {#ac-9}
10. **AC-10 (registration and order).** This runs in 17.2's tick harness (injected `roots` and
    `now`, two tmp stores). On the first due day `catalog_maintain` is called with
    `dry_run=False` (no arming).
    - With a test `vectors_maintain` op that blocks (17.2 AC-10's shape), `catalog_maintain` is
      `deferred` and is called on the tick after `vectors_maintain` reports idle.
    - With `factslog_backup` made to block instead, `catalog_maintain` still runs.

    Mutations: `requires_arming=True` FAILS (`dry_run:unarmed`); `after_idle` dropped FAILS (it
    runs while `vectors_maintain` blocks); `after_idle=("factslog_backup",)` FAILS (deferred
    while the backup blocks). {#ac-10}
11. **AC-11 (the band and the hot row).** In `growth` mode, a store whose `file_bytes` reaches 2×
    its baseline gets band A2 and `catalog_reclaim_due: true`. A hub row already hot for
    `stale_files` publishes news when the reclaim key arrives. Two further ticks with no change
    publish nothing. Clearing the state clears the key. In `free_ratio` mode the AC-1 fixture of
    18.1 (90 % deleted) gives A2 on `f`. Mutation: the key missing from `_hot_signature` FAILS
    (no news on arrival for an already-hot row). {#ac-11}
12. **AC-12 (the snapshot's hold is measured).** The test wraps `_copy_out_of_process` in a seam
    that sleeps 0.2 s (it is not the function under test) and triggers a write op. Health then
    reports `snapshot_hold_s_last ≥ 0.2` and `snapshot_checkpoint_s_last ≤
    snapshot_hold_s_last`. Mutation: the hold timed around the CHECKPOINT only FAILS
    (`< 0.2`). {#ac-12}
13. **AC-13 (pre-registered constants).** Defaults: `RMX_CATALOG_WAL_MAX_BYTES` 64 MiB,
    `RMX_CATALOG_LOCK_WAIT_S` 30, `RMX_CATALOG_HOLD_ALARM_S` 2, `RMX_CATALOG_HOLD_MAX_S` 10.
    Changing one FAILS this test. `RMX_CATALOG_BAND_MODE`'s default equals 18.1's Table B
    verdict as recorded in the plan; it is `growth` until that verdict exists. {#ac-13}
14. **AC-14 (pre-registered mutations, each must FAIL a named AC).** {#ac-14}
    - two holds → AC-1;
    - hold measured with the wait → AC-1;
    - `_op_checkpoint` body or `Store.vacuum` in the hold → AC-2;
    - no acquire timeout → AC-3;
    - WAL gate removed → AC-4;
    - downgrade not persisted, or cleared by a hub run → AC-5;
    - status under `_store_lock` → AC-6;
    - dry run that checkpoints → AC-7;
    - in-process CLI fallback → AC-8;
    - caller-set `invoked_by` → AC-9;
    - `requires_arming=True`, `after_idle` dropped, or `after_idle` on the backup → AC-10;
    - key missing from the hot signature → AC-11;
    - snapshot hold timed around the CHECKPOINT only → AC-12;
    - any constant changed → AC-13.

## Test strategy {#test-strategy}

- Task 23.0's sandbox is mandatory (d1a/d1b). Store daemons are real tmp daemons with short
  roots; the hub harness is 17.2's, with injected `roots` and `now`. No test reaches a live
  socket or a live root.
- Lock assertions use 23.2's `recorded_daemon` on a real `_FairLock`. Bounds are statement
  counts per hold, and seconds are compared, not bounded (23.2 R5).
- The mutation list in AC-14 is run before GREEN is declared, each restored in its own command.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/daemon.py` | `_op_catalog_maintain` + its routine (R2, `checkpoint` seam), run state (R3), `catalog_state.json`, `runs.jsonl` line (R6), `_store_health` `catalog` block (R7), `_snapshot_catalog` hold ring (R8) |
| `src/refmatrix/verbs.py` | `rmx_catalog_maintain`, the closed `invoked_by` set |
| `src/refmatrix/cli.py` | `catalog` group, `rmx catalog maintain` (daemon-only) |
| `src/refmatrix/mcp.py` | the tool, through the verb (parity test) |
| `src/refmatrix/hub.py` | the step's registration on `maintenance_steps` (R9); the three row keys, `_queue_row_is_hot`, `_hot_signature` (R7) |
| `tests/test_catalog_maintain.py`, `tests/test_hub_catalog_step.py` | new: AC-1..AC-14 |
| CLI tree (`scripts/gen-cli-tree.py` output) | regenerated for the new group |
