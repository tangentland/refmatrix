---
gmd: "0.1"
id: task-18.2-catalog-maintain-step
title: "Task 18.2: `catalog_maintain` — a reason-gated, bounded, measured CHECKPOINT per store on 17.2's nightly tick, banded on growth against the 18.1 baseline, built on ONE shared catalog-hold helper that the snapshot tick and `_op_checkpoint` also use"
tags: [task, daemon, hub, duckdb, catalog, checkpoint, maintenance, lock]
metadata:
  node_type: task
  status: pending
  created: 2026-10-15
  updated: 2026-10-15
---

# Task 18.2: the `catalog_maintain` step {#root}

> Plan: [plan-18-duckdb-store-maintenance](../plan-18-duckdb-store-maintenance.md)
> Status: Pending (spec written 2026-10-15; revised the same day for the 18.1 verdict, see
> [[#rev-18-1-verdict]]; revision round 2 the same day for ch-bsd plan-18 r1, see
> [[#rev-round-2]]; revision round 3 for ch-bsd plan-18 r2, see [[#rev-round-3]]; re-review
> pending)
> Wave: 4 ([[plan-review-2026-10-14#t10-waves]]: "plan-18 as a 17.2 step").
> Depends on: 17.2 (the `maintenance_steps` registry, `maintain.json`, the step obligations of
> 17.2 R2); 17.1 R11 / R12 (the single-flight reply and `runs.jsonl` line shapes it copies);
> 23.0 (test sandbox); 23.2 (`recorded_daemon`, the per-hold statement counts); 23.5
> (`Daemon._inflight`, the ONE `lock hold:` alarm in `_FairLock`'s release, `pin_to` and the
> snapshot's fragment flush; its [[task-23.5-read-path-and-holder-bounds#cross-plan-18]] list is
> carried into R8 and R11); 23.1 R1.6 (`_FairLock.held_by_current_thread`); 18.1 (DONE: its
> Table B verdict made `growth` the band mode, d9bg, and its `rewrite_bytes` are the baselines,
> d9bq).
> Not on 23.1: the step is store-wide and partition-free, so it takes `_store_lock` directly
> (through the shared helper, [[#r11-hold-helper]]) and does not go through
> `bind(partition_name)` (R2).
> Blocks: 18.3, which extends the helper and uses this step's band as its trigger.

rel: part-of -> [[plan-18-duckdb-store-maintenance]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
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
rel: derives-from -> [[bsd-plan18-task18-1-measurement-r1-8a93ab1]]
rel: derives-from -> [[bsd-plan18-r1-spec-review-b84fd8d]]
rel: depends-on -> [[task-23.5-read-path-and-holder-bounds#cross-plan-18]]
rel: depends-on -> [[task-23.1-queue-and-drain#r1-6-proposed]]
rel: derives-from -> [[bsd-plan18-r2-spec-diffcheck-cb7bf5b]]

## Why {#why}

The plan's contract ([[plan-18-duckdb-store-maintenance#contract-2026-10-14]]) puts plan-18 on
17.2's tick as a registered step. At HEAD a CHECKPOINT already runs after every write burst
([[task-18.1-catalog-measurement#facts]] F1). So the step's value is not the CHECKPOINT itself. It
does three things:

- **It measures free space nightly.** Nothing reports it today, and `store_bytes` counts a
  bloated writer twice (18.1 F5).
- **It turns that into a hot hub row** when 18.1's bands say a reclaim is due.
- **It times every catalog-maintenance hold the daemon runs:** its own, the snapshot tick's and
  `_op_checkpoint`'s at 18.2, and the rest of 18.3 R8's port list after 18.3. That gives the
  long holds a number. The CHECKPOINTs that stay off the helper are named, each with its reason,
  in [[task-18.3-offline-reclaim#facts]] I1 (ch-bsd r1 S-1).

Live evidence for that last point, stated as observed, with its cause NOT measured
(`feedback_causal_story_before_evidence`):

- On 2026-10-15 rmxd.log shows `facts.log compacted 294090489 -> 264498314 bytes` at 00:11:15.
  That compaction runs `dump_catalog_to_log()` under `_store_lock` (`daemon.py:2380-2389` at
  `23ad703`).
- Then rmxd.log shows nothing until `pool drain disp: timed out after 10s, 3 of 20 workers still
  running (in flight: stats, stats, stats)` at 00:13:16.
- hub.log shows `graceful stop … 'stop_op': 'skipped: not answering ping (SIGTERM sent now)'`
  and `watchdog kickstarted` at 00:13:18.

What held the daemon between 00:11:15 and 00:13:16 is unknown. A step that adds its own hold
under the same lock must therefore bound three things: its wait for the lock, the work inside
its hold, and the seconds of that hold. It must also say how each is measured (R2, R4).

Two decisions of 2026-10-15 shape the rest:

- **d9bc: a reason to run.** The step runs its hold only when a measured reason calls for it:
  a WAL the snapshot tick failed to fold, or a hand run. A night with no reason costs two
  `stat` calls and a ledger line saying why nothing ran (R12).
- **d9bg / d9bq: band on growth against the live size.** 18.1 found every store B-disagree: `f`
  under-reads `r` by 0.115 to 0.657 on 7 stores and over-reads on thiquet (f 0.550, r 0.272);
  no cause is claimed (d9bq). The band is therefore growth, and its baseline is each store's
  18.1 `rewrite_bytes`, its LIVE size (R5). The band is A2 when `file_bytes ≥ 2 ×` that
  baseline AND `file_bytes − baseline ≥ 64 MiB` (Table A's floor; d9bw a). At the instant the
  baseline is measured that is Table A's A2 edge (`r ≥ 0.50` with `reclaimable ≥ 64 MiB`). It
  stays close to it only because an A0 rehearsal re-seeds the baseline (R5), so a store that
  grows legitimately does not keep a false hot row. Growth needs only a `stat`, so the band is
  known every night without a hold.

The step's three CHECKPOINT-holding siblings (the snapshot tick, `_op_checkpoint`, and 18.3's
reclaim) share one helper instead of four hand-spelled holds (R11; the user's rule, 2026-10-15:
converge repeated shapes into one function). {#why-body}

## Facts at HEAD `23ad703` (`src/` unchanged through `7c8d6c5`) {#facts}

Re-cited in revision round 2 (ch-bsd r1 M-1): the first draft cited `55f043d`, and `daemon.py`
changed after it (bug-115/116, `607d759`, `1c86d9c`). `git diff 23ad703 7c8d6c5 -- src` is
empty. The catalog facts F1-F7 are in [[task-18.1-catalog-measurement#facts]]. The lock and
liveness facts this step depends on:

- **L1 `_FairLock`** (`daemon.py:247`) is strict FIFO and supports
  `acquire(blocking=True, timeout=None) -> bool` (`:273`); a waiter that times out withdraws from
  the queue. It is not re-entrant.
- **L2 How a long hold becomes a restart** (read from code; the 00:11-00:13 incident's cause is
  not measured):
  - `stats` is in `CLI_OPS` (`daemon.py:6361`) and its handler takes `_store_lock`
    (`_op_stats`, `:3816-3817`). The hub's queue gather calls it for every store
    (`_gather_queues`, `hub.py:612`; the call `:624`).
  - The heartbeat file is touched only when a no-op submitted to the 4-worker cli pool COMPLETES
    (`_start_heartbeat`, `:1323-1360`). So when every cli worker is queued on `_store_lock`, the
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
- **L4 What NOT to call.** `_op_checkpoint` (`daemon.py:3956`) rebuilds
  `idx_entity_links_lk_concept` (776,359 rows here) inside its hold. `Store.vacuum`
  (`store.py:7259`) is row deletion, not space reclamation (18.1 F3).
- **L5 The facts.log compaction** is size-gated at 256 MiB (`_factslog_threshold`, `:2301`).
  It has a 10 % minimum-reclaim floor (`_FACTSLOG_MIN_RECLAIM`, `:2336`) and runs on its own 30-min
  thread (`_start_factslog_compact_tick`, `:2428`). At ~00:20 this store's `facts.log` was
  283,937,960 bytes, above the 268,435,456 threshold again. The 00:11 run reclaimed 10.06 %, so
  no floor was set (18.1 F4). That compaction is not this plan's; it is a lock holder this step
  must not stack behind (R2 c).
- **L6 Alerts already have a home.** The hub's queue row carries only actionable health keys
  (built in `_gather_queues`, `hub.py:612-662`). `_queue_row_is_hot` (`:1231`) and `_hot_signature` (`:1211`) decide when a
  hot row is news (news on arrival or on a material change, with a rare re-assert; bug-048). 17.2
  R5 alerts only on consecutive `failed` / `refused` outcomes (plus `orphan_cap` and `stuck`), so
  a step's informational signal belongs in health, not in 17.2.

{#facts-body}

## Requirements {#requirements}

1. **R1 Verb, op, surfaces.** {#r1-verb}
   - Verb `rmx_catalog_maintain(dry_run: bool = False, status: bool = False,
     checkpoint: bool = True, baseline_from: str | None = None, *, invoked_by: str) -> dict`;
     daemon op `catalog_maintain`; CLI `rmx catalog maintain [--dry-run] [--status]
     [--no-checkpoint] [--baseline-from <18.1 jsonl>]` (a new `catalog` group); MCP parity
     through the verb-parity test. `baseline_from` is hand-only (R5); `invoked_by="hub"` with it
     raises `ValueError`.
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
   - (b2) **Reason gate** (R12, d9bc). From (a)'s numbers and `catalog_state.json`, compute the
     band (R5) and the run's `reasons`. With no reason the run ends here: outcome
     `skipped:no_reason`, `ok: true`, no hold, and the ledger line and one `rmxd.log` line carry
     `reasons: []` and the `reason_detail`.
   - (c) **Bounded wait.** The hold is ONE call of the shared helper,
     `d._catalog_hold("catalog_maintain", body, lock_wait_s=RMX_CATALOG_LOCK_WAIT_S)` (default
     30; [[#r11-hold-helper]]). On timeout: outcome `skipped:lock_busy`, `ok: false`, no hold,
     `wait_s` reported. It never queues behind a facts.log compaction or a `vectors_maintain`
     dataset hold and then adds its own (L5).
   - (d) **Inside the one hold, exactly two statements.** `CHECKPOINT` is skipped on a dry run,
     with `checkpoint=False`, after (b), or under R4's downgrade. Then
     `PRAGMA database_size`. Nothing else runs in the hold: no DDL, no index rebuild (L4), no
     table scan, no `Store.vacuum`, no fragment flush.
   - (e) **Release, then measure the hold.** The helper measures it (R11): `wait_s` runs from
     the acquire call to its return, and `hold_s` from the acquire's return to the release, by
     `time.monotonic()` in production code around the hold (not by 23.2's test-only recorder).
     The CHECKPOINT's own seconds are `checkpoint_s` (the helper's `checkpoint()` times it).
   - (f) **Lock-free after.** `stat` the slot and `.wal` again: `file_bytes_after`,
     `wal_bytes_after`. Then compute `f = free_blocks / total_blocks` and the band (R5), write
     `<root>/maintain/catalog_state.json` through the ONE state writer
     `catalog_maint.update_state` ([[#r13-state]]), append the ledger line (R6), and log one
     `rmxd.log` line with `hold_s`, `wait_s`, `checkpoint_s`, `f` and the band.
   - **Why not `bind`.** 23.1's `bind(partition_name)` binds a partition inside the hold for
     partition-scoped writes ([[task-23.1-queue-and-drain#r1]]). A CHECKPOINT is store-wide and
     binds nothing. So the step takes `_store_lock` through the helper, as `_snapshot_catalog`
     does after R11. With 23.1 R1.6 adopted, nothing in (d) is a `Store` writer method that
     asserts the lock, and the step's hold is the helper's one acquire.
3. **R3 Single-flight and lock-free status.** 17.1 R11's shape
   ([[task-17.1-vectors-maintain-op#r11-single-flight]]). A call during a run returns
   `{"ok": false, "already_running": true, "run_id", "started_at"}` and starts nothing.
   `status=True` returns the running state, or the last report when idle. Both read an
   in-process run state guarded by its own `threading.Lock`, never `_store_lock`. {#r3-single-flight}
4. **R4 Hold bands (Table D), pre-registered 2026-10-15 before any run.** {#r4-hold}

   | band | `hold_s` of one run | action |
   |---|---|---|
   | D0 | `≤ RMX_CATALOG_HOLD_ALARM_S` (2) | `ok` |
   | D1 | `2 < hold_s ≤ RMX_CATALOG_HOLD_MAX_S` (10) | `ok` plus `hold_alarm` in the report; the `rmxd.log` warning is 23.5 R4's ONE `lock hold:` line, fired for this label at 2 s (R11 "The alarm") |
   | D2 | `hold_s > 10` | `ok` plus `hold_over`. `catalog_state.json` gets `checkpoint_disabled: {since, hold_s, run_id}` (through `update_state`, R13). Every later run with `invoked_by="hub"` skips the CHECKPOINT and reads only the PRAGMA (`checkpoint: "disabled_hold_over"`). Health carries `catalog_hold_over: true`, which makes the hub row hot (R7). A hand run (`cli` / `mcp`) with `checkpoint=True` whose `hold_s ≤ 10` clears the flag. |

   - **Why these numbers** (from L2, not from data): 2 s is the hub's ping timeout, so a shorter
     hold cannot make a ping miss. 10 s is a sixth of the 60 s heartbeat staleness that, with the
     cli pool queued on the lock, ends in a restart.
   - **How it is measured:** in production, R2 (e) on every run, and the D band is computed from
     that number. In tests, by 23.2's recorder, which must agree with the reported `hold_s` within
     50 ms (AC-1). Following 23.2 R5 ("seconds are an alarm, counts are the bound"), the test bound
     is the statement count in the hold (AC-2), not seconds.
   - The downgrade protects only against THIS step's hold. It leaves the snapshot tick's
     CHECKPOINT (R8) alone, because that one is the read path's freshness.
5. **R5 The reclaim band** (18.1 Tables A and B, [[task-18.1-catalog-measurement#r3]]; d9bg
   as amended by d9bq; this is the ONE definition, and 18.3 uses it). `RMX_CATALOG_BAND_MODE`
   selects how the band is read. Its default is `growth`, because 18.1's fleet row is
   B-disagree on all 8 stores. {#r5-band}
   - `growth` (default): `catalog_reclaim_due` and band `A2` when `file_bytes ≥ 2 ×
     baseline_file_bytes` AND `file_bytes − baseline_file_bytes ≥ RMX_CATALOG_RECLAIM_FLOOR_BYTES`
     (64 MiB, Table A's A0 floor; d9bw a), else `A0`. At the instant the baseline is measured
     that is Table A's A2 edge (`r ≥ 0.50` and `reclaimable ≥ 64 MiB`). It is NOT that edge
     afterwards: live data can grow, and only the re-seed below keeps the two close
     (ch-bsd r1 B-3 corrected d9bq's "exactly"). It is computed from R2 (a)'s `stat` alone, so
     it is current on every run, including a `skipped:no_reason` one. With no baseline the band
     is `unknown`.
     - Without the floor, cliquet (18.1: file 74,723,328, rewrite 31,207,424, reclaimable
       43.5 MB, Table A A0) flagged A2 on night one, and every night after, with a rehearsal
       that a hand confirm would refuse `refused:band_a0`. The floor makes it A0 (AC-16).
   - **The baseline is the live size, a measured `rewrite_bytes`.** It lives in
     `<root>/maintain/catalog_state.json` as `baseline_file_bytes`, `baseline_at` and
     `baseline_source`, and it is set in exactly four ways:
     - **From 18.1** (the rollout, R10): a hand run with `baseline_from=<path>` reads that 18.1
       report (the jsonl of the run the plan's verdict cites), takes the line whose `root`
       equals this store's root, and writes that line's `rewrite_bytes` (the median of its
       runs, once 18.1's remedy lands, d9br), with
       `baseline_source: "18.1:<file name>:<as_of>"`. No line for the root →
       `refused:no_baseline_row`; a line with `error` or no `rewrite_bytes` →
       `refused:baseline_row_invalid`; a baseline already set → `refused:baseline_set` (a file
       never overwrites one).
     - **A reclaim rehearsal** (a store with no 18.1 line, for example one registered later):
       18.3's rehearsal writes its median `rewrite_bytes` when no baseline exists
       (`baseline_source: "rehearsal:<run_id>"`; [[task-18.3-offline-reclaim#r2-rehearse]]).
       Band `unknown` is 18.3's reason to run that rehearsal.
     - **A reclaim** resets it to the new file's `rewrite_bytes`
       (`baseline_source: "reclaim:<run_id>"`; [[task-18.3-offline-reclaim#r7-after]]).
     - **An A0 rehearsal re-seeds it** (d9bw a). A rehearsal whose Table A band is A0 writes its
       median `rewrite_bytes` as the baseline (`baseline_source: "rehearsal:<run_id>"`), the
       same kind of number the rehearsal seed above already writes: a measured live size.
       So a store that grew legitimately from 177 to 354 MiB of live data (r ≈ 0) is A2 for
       at most one night: that night's rehearsal measures it A0 and re-seeds, and the next night
       is A0 with no rehearsal ([[task-18.3-offline-reclaim#ac-11]] (f)).

     Nothing else moves it. A `file_bytes` is never used as a baseline: it is the bloated size,
     and growth against it would flag refmatrix only at r ≈ 0.89 and global at r ≈ 0.93
     ([[bsd-plan18-task18-1-measurement-r1-8a93ab1#s-2]]).
   - `free_ratio` (opt-in only): Table A's edges applied to `f`, and `reclaimable_est =
     free_blocks × block_size`. It is kept for a store a future measurement shows B-agree; at
     2026-10-15 no store qualifies.
   - `f` is still read inside every hold that runs (R2 d) and reported with `f_measured_at`. It
     is not banded.
   - On A2, health carries `catalog_reclaim_due: true`, which makes the hub row hot (R7). It is
     also 18.3's trigger ([[task-18.3-offline-reclaim#r9-tick-step]]). A1 cannot arise in
     `growth` mode.
6. **R6 The ledger.** Every completed run appends one fsynced line to
   `<root>/maintain/runs.jsonl` in 17.1 R12's shape ([[task-17.1-vectors-maintain-op#r12-ledger]]):
   `{run_id, step: "catalog_maintain", invoked_by, dry_run, ok, started_at, finished_at,
   outcomes: {"catalog": <outcome>}}`, plus `wait_s, hold_s, checkpoint_s, checkpoint,
   file_bytes_before, file_bytes_after, wal_bytes_before, wal_bytes_after, block_size,
   total_blocks, used_blocks, free_blocks, f, band, band_mode, hold_band, reasons,
   reason_detail, baseline_file_bytes, baseline_source`. A `skipped:no_reason` line carries the
   `stat` fields, the band and the reason detail; its PRAGMA fields are `null`. {#r6-ledger}
7. **R7 Health and the hub row** (L6). {#r7-health}
   - `_store_health` (`daemon.py:3829` at `23ad703`) gains `catalog: {file_bytes, wal_bytes, f,
     f_measured_at, band, band_mode, baseline_file_bytes, baseline_source, measured_at,
     last_reasons, hold_s_last, checkpoint_disabled, snapshot_hold_s_last,
     snapshot_hold_s_max_24h, snapshot_checkpoint_s_last}`. These are read from
     `catalog_state.json` and the helper's hold ring (R8, R11), plus one `stat` of the slot and
     `.wal`. There is no DuckDB call and no `_store_lock`. 18.3 adds `backup_bytes`.
   - `catalog_wal_large` is computed live from that `stat` (`wal_bytes > RMX_CATALOG_WAL_MAX_BYTES`),
     so a growing WAL shows without waiting for the night.
   - The hub's row builder (`_gather_queues`, `hub.py:612-662`) copies `catalog_reclaim_due`, `catalog_wal_large` and
     `catalog_hold_over` into the row only when true. `_queue_row_is_hot` (`:1231`) treats each as
     hot, and `_hot_signature` (`:1211`) lists each as a reason. Each therefore alerts once on
     arrival and re-asserts at the existing cadence (bug-048), with no new alert mechanism.
8. **R8 Measure the CHECKPOINT that already runs.** `_snapshot_catalog` (`daemon.py:2669` at
   `23ad703`; its hold is `:2700-2721`, its CHECKPOINT `:2702`) is ported onto the helper
   (R11) with the label `snapshot` and `snapshot=True`. The helper then times its hold and its
   CHECKPOINT and keeps both in the per-label ring covering the last 24 h (read lock-free by
   R7). A hold over D1's 2 s edge is logged by 23.5 R4's one `lock hold:` line (R11 "The
   alarm"), not by a line of the helper's own. The snapshot's behaviour does not change, and
   "behaviour" includes 23.5's additions to it
   ([[task-23.5-read-path-and-holder-bounds#cross-plan-18]] items 3 and 4):
   - inside the `_store_lock` body, `if store.has_dirty_fragments(): store.flush_fragments()`
     BEFORE the CHECKPOINT (a flush error returns `{"error": "flush"}` with one log line). 23.5
     R7's flush-order AST assertion moves with the body: it walks `CatalogHold.snapshot`, not
     `_snapshot_catalog`, and is retargeted in the port's commit, not deleted (23.5 item 4;
     ch-bsd plan-18 r2 N-M3; AC-12);
   - the same statements in the same order and the same error returns;
   - with `pin_to`, the live log's size `L0` read inside the `_store_lock` body after the copy
     and the `os.replace`, and the result's `log_size` and `pinned`;
   - the read-only link swing, the mirror refresh and the `pin_to` link AFTER `_store_lock` is
     released but BEFORE `_snapshot_lock` is released, as at HEAD (`daemon.py:2692-2738`). They
     are the helper's `after_locked` callbacks (R11), never its `after` ones.

   This is the baseline the nightly hold is compared against, and the only number for L3.
   {#r8-snapshot-hold}
9. **R9 Registration on 17.2** ([[task-17.2-hub-nightly-tick#r2-registry]],
   [[task-17.2-hub-nightly-tick#r7-unarmed]]). {#r9-register}
   - `MaintenanceStep(name="catalog_maintain", op="catalog_maintain", args=lambda root,
     dry_run, today: {"dry_run": dry_run}, requires_arming=False, reason=…,
     after_idle=<below>)` is registered LAST, as 17.2 R2's order says. `invoked_by="hub"` is
     set by 17.2's call path (17.1 R1), not by `args`.
   - **`requires_arming=False`** (d9bg, answering plan Q4), with this reason: "a CHECKPOINT
     folds the WAL into the file the daemon already writes, the statement the snapshot tick runs
     after every write burst unarmed (`daemon.py:2702`), plus a metadata PRAGMA; it deletes
     nothing, rewrites no table and changes no row; and it runs only with a measured reason
     (R12, d9bc)". The contract expected `True` because "a CHECKPOINT that rewrites the catalog
     is user-visible state". That premise does not hold at HEAD (18.1 F1, F2).
   - **The reclaim is a separate step.** 18.3 registers `catalog_reclaim` AFTER this step, with
     `after_idle` naming it and with `requires_arming=True`. Its reason is this step's A2 band
     ([[task-18.3-offline-reclaim#r9-tick-step]]). This step never calls the reclaim, so its
     one-hold bound (AC-1) holds on every run.
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
    `rmx catalog maintain --dry-run`, then one hand
    `rmx catalog maintain --baseline-from <18.1 jsonl>`, on each of the 8 registered stores. The
    jsonl is the run the plan's 18.1 verdict cites: the fleet run is re-taken after 18.1's
    remedy (d9br), so not necessarily `plan18-catalog-measure-20261015.jsonl`. Each store's
    health then shows its 18.1 baseline, and the stores 18.1 banded A2 show
    `catalog_reclaim_due`. No
    arming is needed (R9). Then one night is observed: every registered
    store has exactly one `invoked_by: "hub"` line, and each line's D band is recorded. The
    per-store table goes in the implementation summary. A D2 night on any store is a bug-registry
    row before the plan closes. {#r10-rollout}
11. **R11 ONE catalog-hold helper** (the user's rule, 2026-10-15: converge repeated shapes into
    one function). Six places hold `_store_lock` around a DuckDB maintenance statement and a
    file operation, each spelled out by hand ([[task-18.3-offline-reclaim#facts]] I1). This
    step would add a seventh. Instead, 18.2 builds the helper and puts three of them on it, and
    18.3 extends it and moves the rest. {#r11-hold-helper}
    - **Where.** A new module `src/refmatrix/catalog_maint.py` holds `CatalogHold`, the SQL
      routines and the state writer (R13). `Daemon._catalog_hold(label: str, body:
      Callable[[CatalogHold], dict], *, snapshot: bool = False, lock_wait_s: float | None =
      None, after_locked: Sequence[Callable[[dict], None]] = (), after:
      Sequence[Callable[[dict], None]] = ()) -> dict` is the only entry point. (The first draft's
      `deadline_s` parameter is gone: 18.3 arms its deadline inside the body, after its
      uninterruptible steps, through `CatalogHold.interruptible`; ch-bsd r1 B-2 / M-4.)
    - **The holder is named through 23.5** ([[task-23.5-read-path-and-holder-bounds#cross-plan-18]]
      item 1). For its whole hold the helper enters `Daemon._inflight(label)` (an `InflightEntry`
      with `kind="tick"`), so 23.5 R4's `writer_holder` and its `WriterBusy` message name the
      label. The helper keeps no holder registry of its own. When one thread holds two entries
      (an op such as `catalog_maintain` called through the cli pool, plus the helper's tick
      entry), 23.5 R4's `writer_holder` names the most recently registered (inner) one, so the
      label and its alarm threshold below are the helper's, not the outer op's (ch-bsd 23/17
      r10).
    - **The locks.** With `snapshot=True` it takes `_snapshot_lock` and THEN `_store_lock`,
      the snapshot tick's order (`daemon.py:2692`, `:2700`). Otherwise it takes `_store_lock`
      alone. `lock_wait_s=None` blocks, as the snapshot tick does today; a number bounds both
      waits together and returns `{"outcome": "skipped:lock_busy", "wait_s": …}` with no body
      call. A timeout on `_snapshot_lock` returns before `_store_lock` is touched, so a
      `snapshot=True` caller never holds `_store_lock` while it waits for `_snapshot_lock`
      (AC-17's lock-order case observes exactly this). Each lock is released in its own
      `finally`, `_store_lock` first.
    - **The numbers.** `wait_s` and `hold_s` come from `time.monotonic()` around the acquire
      and the `_store_lock` hold, plus per-step seconds from `CatalogHold.mark(name)`. They are
      pushed to a per-label ring covering 24 h, behind its own `threading.Lock` and read
      lock-free by R7. The ring is a measurement ledger, not an alarm.
    - **The alarm** ([[task-23.5-read-path-and-holder-bounds#cross-plan-18]] item 2). The helper
      writes no `rmxd.log` line of its own for a long hold. 23.5 R4's `lock hold: <label> <s>s`
      line, fired in `_FairLock`'s release, is the one alarm. Plan-18's 2 s edge (D1) is a
      per-label threshold on that alarm: 18.2 registers `snapshot`, `checkpoint_op` and
      `catalog_maintain` (18.3 adds its labels) at `RMX_CATALOG_HOLD_ALARM_S` in the
      label → seconds map that 23.5's release path reads. That is not a second line.
    - **ONE statement path.** Every statement `CatalogHold` runs goes through
      `CatalogHold._exec(sql, params=())`. 18.3 adds the deadline check to that one method, so
      no statement can skip it (B-2). The module functions that the rehearsal child also runs
      (18.3's `rewrite_into`, `gate`) take an executor, not a raw connection: `h._exec` in the
      hold, a plain executor in the child.
    - **What `CatalogHold` offers at 18.2:** `store` (the bound writer `Store`), `checkpoint()`
      (timed into `checkpoint_s`), `database_size()` (the PRAGMA row), `copy_out(src, dst)`
      (`_copy_out_of_process`), `replace(src, dst)` (`os.replace` plus an `fsync` of the parent
      directory), `snapshot(pin_to=None)` (the snapshot tick's locked body as R8 states it:
      dirty-fragment flush, CHECKPOINT, child copy to `.tmp`, replace, `L0`), and `mark(name)`.
      18.3 adds `interruptible`, `rewrite_into`, `gate`, `close_writer`, `swap`,
      `reopen_writer` and `drop_sentinel`.
    - **Two callback phases** (ch-bsd r1 S-2). Each runs in order with the body's result. An
      exception in one is logged and counted in the result (`after_errors`), and the rest still
      run.
      - `after_locked` (only with `snapshot=True`): after `_store_lock` is released and BEFORE
        `_snapshot_lock` is released. This is where HEAD runs the read-only link swing and the
        mirror refresh (`daemon.py:2692-2738`), and where 23.5's `pin_to` link must land.
      - `after`: after both locks are released. For `_request_snapshot()`, state files, ledger
        lines and child checks.
    - **The callers at 18.2:**
      - `_snapshot_catalog`: label `snapshot`, `snapshot=True`, body `h.snapshot(pin_to)`,
        `after_locked` = the link swing, the mirror refresh and the `pin_to` link. Its debounce
        and its return dict are unchanged (R8).
      - `_op_checkpoint`: label `checkpoint_op`, body = its DROP/CREATE INDEX plus
        `h.checkpoint()`, `after` = `_request_snapshot()`. Behaviour unchanged; it now has a
        measured hold.
      - `catalog_maintain`: label `catalog_maintain` (R2).
    - **Not here:** the boot sites, `_bootstrap_rotation_if_needed`, the two entities-rebuild
      holds and 23.5's compaction hold 2 (18.3 R8 moves them, with the swap half);
      `_op_replica_merge` (fenced, d9ae; 18.3 R8 names its exemption and its reopen).
    - **The bypass rule** (ch-bsd r1 S-1, r2 N-B2; AC-17). An AST walk over EVERY
      `src/refmatrix/*.py` (a fixed file list let a lock or a CHECKPOINT moved one module over
      pass, r2 N-B2). Every exemption is a QUALIFIED function name (`module.Class.method` or
      `module.function`), never a file or a line:
      - in `catalog_maint`, `_store_lock` and `_snapshot_lock` are referenced nowhere, and
        `.execute(` appears only in the executors (`CatalogHold._exec` and the child's);
      - `_snapshot_lock` is referenced only in `daemon.Daemon._catalog_hold` and its
        `Daemon.__init__` declaration, in any module; `_store_lock` is referenced inside no
        function on the catalog list (`daemon.Daemon._snapshot_catalog`,
        `daemon._op_checkpoint`, `daemon._op_catalog_maintain`, and 18.3's additions to it);
      - **the CHECKPOINT rule.** A CHECKPOINT statement is any string constant (an
        `ast.Constant`, or a literal part of an f-string) matching
        `^\s*(FORCE\s+)?CHECKPOINT\b`, case-insensitive; docstrings are not statements and are
        skipped. One may appear only in `catalog_maint.CatalogHold.checkpoint` / `snapshot` /
        `rewrite_into` (and 18.3's `drop_sentinel` and child entry point), or in a function on
        one of two exemption lists the test holds as named constants:
        - **permanent** (each with its reason, [[task-18.3-offline-reclaim#facts]] I1):
          `store.Store.rebuild_entities_indexes`, `cli.merge_verb_aliases`,
          `daemon._op_replica_merge`, `replica_merge.merge_slots`;
        - **staged**, each marked with the task that removes it: `daemon.Daemon.serve_forever`
          (the init slot rebind is inline there at HEAD; pending 18.3 R8),
          `daemon.Daemon._bootstrap_rotation_if_needed` (pending 18.3 R8), `cli.compact`
          (pending 18.3 R10). [[task-18.3-offline-reclaim#ac-14]] asserts the staged list is
          EMPTY.

        This is the census at `master` `b381b6d` (`src/refmatrix/*.py`, SQL CHECKPOINT
        constants): the seven functions above plus `_snapshot_catalog` and `_op_checkpoint`,
        which 18.2 ports. So the rule is green on 18.2's own correct code, and a CHECKPOINT
        added to any other function, in any module (`store.py`, `backend.py`, a new module),
        is red;
      - from each op on the catalog list, exactly ONE `_catalog_hold` call is reachable,
        walking the calls into `catalog_maint` (ch-bsd r1 M-7: the routine with the
        `checkpoint` seam, not the op, holds the call).
12. **R12 The reason gate** (d9bc: "we should have a reason to run"). The hold runs only for a
    reason, and every run says which reason it had, or why it had none. {#r12-reason}

    | reason | condition (from R2 a's `stat` and `catalog_state.json`) | what runs |
    |---|---|---|
    | `hand` | `invoked_by ∈ {cli, mcp}` | the hold: CHECKPOINT (unless `--no-checkpoint` or the WAL gate) + PRAGMA |
    | `wal_unfolded` | `RMX_CATALOG_WAL_FOLD_BYTES` (16 MiB, DuckDB's `checkpoint_threshold`, 18.1 F1) `≤ wal_bytes ≤` the 64 MiB WAL gate | the hold: CHECKPOINT + PRAGMA (the snapshot tick should have folded this WAL; the step does) |
    | `wal_large` | `wal_bytes >` 64 MiB | `refused:wal_large`; the hold runs the PRAGMA only (R2 b) |
    | (band) | growth band `A2` or `unknown` | no hold: the band is already known from the `stat`, and the action it calls for is 18.3's reclaim step, not a CHECKPOINT |
    | none | none of the above | `skipped:no_reason`, `ok: true`, no hold |

    - `reasons` (a list) and `reason_detail` (one line with the numbers, for example
      `wal 0 B < 16 MiB; file 790 MiB < 2 × baseline 177 MiB = 354 MiB`) go in every ledger
      line and in one `rmxd.log` line per run, run or skipped.
    - `catalog_state.json` is written on every run, so the band, `measured_at` and the reason
      are current for 18.3's step and for health even on a night with no hold.
    - The D2 downgrade (R4) still applies: a `wal_unfolded` hub run on a store with
      `checkpoint_disabled` reads only the PRAGMA.

13. **R13 ONE locked writer for `catalog_state.json`** (ch-bsd r1 S-5). The file holds safety
    latches (`checkpoint_disabled`, and 18.3's `reclaim_disabled`, `reclaim_hold_over`,
    `rewrite_too_slow`, `reclaim_inflight`) as well as the band and the baseline, and two ops
    (this step and 18.3's reclaim, hand and hub runs, and 18.3's `after` callbacks outside any
    hold) write it. {#r13-state}
    - `catalog_maint.update_state(root, mutate: Callable[[dict], None]) -> dict` is the only
      writer. Under a process-wide `threading.Lock` it reads the file, calls `mutate` on the
      dict, writes a tmp file with a unique name (`catalog_state.json.<pid>.<thread>.<n>.tmp`),
      `fsync`s it, renames it over the file, and `fsync`s the directory. It returns the new
      dict. A read-only `catalog_maint.read_state(root)` needs no lock (the rename is atomic).
    - Every write of the file in 18.2 and 18.3 is an `update_state` call that sets or clears
      only its own keys. **The enforcement is a string-constant rule** (ch-bsd r2 N-M2; AC-17),
      because a rule that matches writes "onto a `catalog_state.json` path" misses
      `p = state_path(root); p.write_text(…)`: across every `src/refmatrix/*.py`, the only
      non-docstring string constant containing `catalog_state` is the one assignment
      `catalog_maint.STATE_FILE = "catalog_state.json"`, and the name `STATE_FILE` is referenced
      only inside `catalog_maint.update_state` and `catalog_maint.read_state`. There is no path
      helper; a log line says "catalog state", not the file name. Any second writer must then
      either spell the name (a second constant), reference `STATE_FILE` (outside the two
      functions), or go through a helper that does one of those, and each fails the rule.

## Acceptance criteria {#acceptance}

All tests run in the 23.0 sandbox, on real tmp daemons with short roots, with 23.2's
`recorded_daemon` installed as `_store_lock` before any op.

1. **AC-1 (one bounded hold, measured where it happens).** On a tmp store with a non-empty WAL,
   one hand (`cli`) run, reason `hand`, gives:
   - `wal_bytes_after < wal_bytes_before`, and the PRAGMA fields are present;
   - a ledger line (R6);
   - exactly ONE recorded hold for the run, whose duration is within 50 ms of the reported
     `hold_s`.

   A second variant (ch-bsd r1 M-5) runs the same hand run while a competitor thread holds
   `_store_lock` for 0.5 s first (released on a timer): the reported `wait_s ≥ 0.45`, and the
   recorded hold is still within 50 ms of `hold_s`.

   Mutations: CHECKPOINT and PRAGMA in two holds FAILS (two holds); `hold_s` measured around the
   whole op, wait included, FAILS the competitor variant (about 0.5 s off). {#ac-1}
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
    `dry_run=False` (no arming). On a store with a 0-byte WAL and a baseline it has not doubled,
    the outcome is `skipped:no_reason` with no recorded hold.
    - With a test `vectors_maintain` op that blocks (17.2 AC-10's shape), `catalog_maintain` is
      `deferred` and is called on the tick after `vectors_maintain` reports idle.
    - With `factslog_backup` made to block instead, `catalog_maintain` still runs.

    Mutations: `requires_arming=True` FAILS (`dry_run:unarmed`); `after_idle` dropped FAILS (it
    runs while `vectors_maintain` blocks); `after_idle=("factslog_backup",)` FAILS (deferred
    while the backup blocks). {#ac-10}
11. **AC-11 (the band and the hot row).** In `growth` mode, a store whose `file_bytes` reaches 2×
    its baseline gets band A2 and `catalog_reclaim_due: true`, on a `skipped:no_reason` hub run
    with no hold (the band needs only the `stat`). A hub row already hot for
    `stale_files` publishes news when the reclaim key arrives. Two further ticks with no change
    publish nothing. Clearing the state clears the key. In `free_ratio` mode the AC-1 fixture of
    18.1 (90 % deleted) gives A2 on `f`. Mutation: the key missing from `_hot_signature` FAILS
    (no news on arrival for an already-hot row). {#ac-11}
12. **AC-12 (the snapshot's hold is measured, and its behaviour kept).** The test wraps
    `_copy_out_of_process` in a seam that sleeps 0.2 s (it is not the function under test) and
    triggers a write op. {#ac-12}
    - Health then reports `snapshot_hold_s_last ≥ 0.2` and `snapshot_checkpoint_s_last ≤
      snapshot_hold_s_last`.
    - **The `after_locked` phase** (ch-bsd r1 S-2). A seam on the mem mirror's `refresh()`
      records `_snapshot_lock.locked()` and whether the current thread holds `_store_lock`:
      `True` and `False`. A snapshot run with `pin_to` has the `pin_to` link on disk with the
      new snapshot's inode when `_snapshot_lock` is next acquired by another thread, and its
      result carries `log_size` and `pinned: true`.
    - A dirty fragment present before the tick is in the snapshot copy (23.5 R1.9's flush).
    - **The flush-order AST** (23.5 R7's assertion, moved by the port; ch-bsd r2 N-M3): in
      `catalog_maint.CatalogHold.snapshot`, the `flush_fragments` call precedes the
      `checkpoint()` call in source order. 23.5 R7's test that walked `_snapshot_catalog` is
      retargeted to this function, not deleted.

    Mutations: the hold timed around the CHECKPOINT only FAILS (`< 0.2`); the link swing and
    mirror refresh moved to `after` FAILS (`_snapshot_lock.locked()` is `False` in the seam);
    the flush dropped from `snapshot()` FAILS (the fragment is missing from the copy); the flush
    moved after the CHECKPOINT FAILS (the flush-order AST, and the copy, which is the file
    without its WAL, misses the fragment).
13. **AC-13 (pre-registered constants).** Defaults: `RMX_CATALOG_WAL_MAX_BYTES` 64 MiB,
    `RMX_CATALOG_LOCK_WAIT_S` 30, `RMX_CATALOG_HOLD_ALARM_S` 2, `RMX_CATALOG_HOLD_MAX_S` 10.
    `RMX_CATALOG_WAL_FOLD_BYTES` 16 MiB, `RMX_CATALOG_BAND_MODE` `growth` (18.1's Table B
    fleet verdict, d9bg), the growth factor 2, and `RMX_CATALOG_RECLAIM_FLOOR_BYTES` 64 MiB
    (Table A's floor, d9bw a). Changing one FAILS this test. {#ac-13}
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
    - any constant changed → AC-13;
    - an unconditional hub CHECKPOINT, or a run with no `reasons` logged → AC-15;
    - a baseline taken from `file_bytes`, overwritten by `--baseline-from`, or the 64 MiB floor
      dropped from the growth band → AC-16;
    - a hand-spelled hold left in `_snapshot_catalog` or `_op_checkpoint`, a
      `with d._store_lock:` inside `catalog_maint.py`, inverted lock order, the holder not
      registered through `_inflight`, or a second hold-alarm line → AC-17;
    - link swing / mirror refresh moved to `after`, the flush dropped from `snapshot()`, or the
      flush moved after the CHECKPOINT → AC-12;
    - `catalog_state.json` written without `update_state`'s lock → AC-18;
    - a CHECKPOINT in a `Store` method or in any module outside the named sites, or a second
      `catalog_state.json` writer → AC-17.
15. **AC-15 (the reason gate; d9bc).** In 17.2's harness, three hub runs on three tmp stores: {#ac-15}
    - (a) a 0-byte WAL and no growth: `skipped:no_reason`, zero recorded holds, and the ledger
      and `rmxd.log` lines carry `reasons: []` and a `reason_detail` naming both numbers;
    - (b) a WAL of at least `RMX_CATALOG_WAL_FOLD_BYTES` (set to 1 KiB for the test):
      `reasons: ["wal_unfolded"]`, one hold, and the WAL shrinks;
    - (c) a store in A2: `reasons: []`, no hold, `band: "A2"`, and `catalog_reclaim_due: true`.

    A `cli` run on (a)'s store has `reasons: ["hand"]` and one hold. Mutation: the hub
    CHECKPOINTing without a reason FAILS (a records a hold).
16. **AC-16 (the baseline; d9bq).** {#ac-16}
    - A hand run with `--baseline-from` on a fixture jsonl writes that root's `rewrite_bytes`,
      not its `file_bytes`, with `baseline_source` naming the file and `as_of`.
    - A second `--baseline-from` refuses `refused:baseline_set`.
    - A root with no line refuses `refused:no_baseline_row`; an `error` line refuses
      `refused:baseline_row_invalid`.
    - A store with no baseline reports band `unknown`.
    - With the fixture's 18.1 numbers for refmatrix (file 827,338,752; rewrite 185,348,096),
      the band is A2 on the first run.
    - With the fixture's 18.1 numbers for cliquet (file 74,723,328; rewrite 31,207,424; file
      ≥ 2 × rewrite but file − rewrite = 43.5 MB < 64 MiB), the band is A0 (Table A's A0;
      ch-bsd r1 B-3). The r2 line (rewrite 31,469,568) gives A0 as well.

    Mutations: `file_bytes` as the baseline FAILS (refmatrix is A0); an overwriting
    `--baseline-from` FAILS; the 64 MiB floor dropped FAILS (cliquet is A2).
17. **AC-17 (one helper, and the checks that it stays one).** {#ac-17}
    - **The AST walk** of R11 "The bypass rule", over EVERY `src/refmatrix/*.py` (ch-bsd r1
      S-1, r2 N-B2), exemptions by qualified function name: no `_store_lock` / `_snapshot_lock`
      reference in `catalog_maint`; none in the catalog-list functions; `_snapshot_lock` only in
      `Daemon._catalog_hold` (and `Daemon.__init__`); a CHECKPOINT statement constant only in the
      named `CatalogHold` methods, the permanent exemptions and the STAGED exemptions
      (`Daemon.serve_forever`, `Daemon._bootstrap_rotation_if_needed`, `cli.compact`, each
      marked "pending 18.3 R8 / R10"); `.execute(` in `catalog_maint` only in the executors;
      and exactly one `_catalog_hold` call reachable from each catalog-list op, walking into
      `catalog_maint` (ch-bsd r1 M-7). The test is green at 18.2 GREEN on the census of R11.
    - **One state writer, statically** (R13; ch-bsd r2 N-M2): the only non-docstring string
      constant containing `catalog_state` in `src/refmatrix` is `catalog_maint.STATE_FILE`'s,
      and `STATE_FILE` is referenced only in `update_state` and `read_state`.
    - Health reports a hold ring entry for each of the labels `snapshot`, `checkpoint_op` and
      `catalog_maintain` after one of each runs.
    - **The holder is named** (23.5 item 1). While a `catalog_maintain` seam blocks inside the
      hold, `stats(include_health=True)` reports `writer_holder.op == "catalog_maintain"`.
    - **One alarm** (23.5 item 2). With the label threshold at 0.1 s and a 0.3 s seam, `rmxd.log`
      gains exactly ONE line for the hold, and it is 23.5 R4's `lock hold: catalog_maintain`
      line.
    - **Lock order, by an observable that can fail** (ch-bsd r1 B-4). A competitor thread holds
      ONLY `_snapshot_lock`, on an event. A test body run through
      `d._catalog_hold("order_probe", body, snapshot=True, lock_wait_s=1)` returns
      `skipped:lock_busy` with no body call. During that second a write op (`upsert_entity`)
      completes in under 0.5 s, and 23.2's recorder shows no `_store_lock` acquisition by the
      helper's thread.
    - A write burst during a `catalog_maintain` hold (the seam blocks on an event) completes
      both within 5 s of the release.

    Mutations: a hand-spelled hold left in `_op_checkpoint` FAILS (AST); a `with
    d._store_lock:` inside `catalog_maint.py` (the code moved out of `daemon.py`) FAILS (AST); a
    raw `.execute("CHECKPOINT")` in a `Store` method called from the body FAILS (AST:
    `store.py` is walked, and the method is on neither exemption list); the same statement in a
    function of `backend.py` FAILS (AST, any module); a second `catalog_state.json` writer
    (`(root / "maintain" / "catalog_state.json").write_text(…)`, or a `state_path()` helper
    returning `… / STATE_FILE`) FAILS (the state-writer rule: a second constant, or a reference
    outside the two functions); the helper taking `_store_lock` before `_snapshot_lock`
    with `snapshot=True` FAILS the lock-order case (the write op blocks for the full second, and
    the recorder shows the helper's thread holding `_store_lock`); no `_inflight` entry FAILS
    (`writer_holder` is `untracked thread …`); a helper-owned hold log line FAILS (two lines).
18. **AC-18 (one state writer; ch-bsd r1 S-5).** Two threads call `update_state` with seams that
    interleave them (A reads, then B reads, writes `reclaim_disabled`, then A writes `band`):
    the file afterwards holds BOTH keys. A `catalog_maintain` run and a test write of
    `reclaim_disabled` interleaved the same way keep both. Mutation: `update_state` without its
    lock FAILS (one key is lost); a tmp name without the thread part FAILS (the two writers
    rename one tmp file). {#ac-18}

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
| `src/refmatrix/catalog_maint.py` | new: `CatalogHold` and its 18.2 methods, the one executor `_exec` (R11); `update_state` / `read_state` (R13) |
| `src/refmatrix/daemon.py` | `Daemon._catalog_hold` (with `_inflight`, `after_locked` / `after`, the per-label alarm thresholds) and its hold ring (R11); `_op_catalog_maintain` + its routine (R2, `checkpoint` seam, reason gate R12), run state (R3), `catalog_state.json` with the baseline (R5), `runs.jsonl` line (R6), `_store_health` `catalog` block (R7); `_snapshot_catalog` and `_op_checkpoint` ported onto the helper (R8, R11) |
| `src/refmatrix/verbs.py` | `rmx_catalog_maintain`, the closed `invoked_by` set |
| `src/refmatrix/cli.py` | `catalog` group, `rmx catalog maintain` (daemon-only) |
| `src/refmatrix/mcp.py` | the tool, through the verb (parity test) |
| `src/refmatrix/hub.py` | the step's registration on `maintenance_steps` (R9); the three row keys, `_queue_row_is_hot`, `_hot_signature` (R7) |
| `tests/test_catalog_maintain.py`, `tests/test_hub_catalog_step.py`, `tests/test_catalog_hold.py` | new: AC-1..AC-18 |
| CLI tree (`scripts/gen-cli-tree.py` output) | regenerated for the new group |

## Revision 2026-10-15 (18.1 verdict) {#rev-18-1-verdict}

| source | change |
|---|---|
| d9bc (a reason to run) | [[#r12-reason]]; R2 (b2); the ledger's `reasons` / `reason_detail` (R6); [[#ac-15]]; R9's reason text |
| d9bg (growth default; Q4: `requires_arming=False` stands) | header; [[#why]]; [[#r5-band]] default `growth`; R9 states Q4 answered; [[#ac-13]] pins `growth` |
| d9bq (PROVISIONAL; amends d9bg: baseline = 18.1 `rewrite_bytes`, reset after each reclaim, one definition) | [[#r5-band]] rewritten as the one definition 18.3 uses: `--baseline-from` takes `rewrite_bytes`, a rehearsal seeds a missing one, a reclaim resets it, never a `file_bytes`; the corrected under-read figures in [[#why]]; [[#ac-16]] |
| the user's convergence rule | [[#r11-hold-helper]]: one `_catalog_hold` helper; the snapshot tick (R8) and `_op_checkpoint` ported onto it; 18.3 extends it; [[#ac-17]] |
| 18.3's tick step | R9 names it; this step never calls the reclaim, so AC-1's one hold stands |
| line numbers | R7, R8 and R9 cite `daemon.py` at `23ad703` |

## Revision round 2 {#rev-round-2}

From ch-bsd plan-18 r1 ([[bsd-plan18-r1-spec-review-b84fd8d]]) and the rulings d9bw (with
d9bp-d9bv) in [[plan-review-2026-10-14]]; 23.5's hand-off list
([[task-23.5-read-path-and-holder-bounds#cross-plan-18]]) carried in.

| finding | change |
|---|---|
| B-3 (growth flags A2 where Table A says A0; a frozen baseline) / d9bw a | [[#r5-band]]: A2 needs `file − baseline ≥ 64 MiB` as well; an A0 rehearsal re-seeds the baseline (a fourth source); "exactly r ≥ 0.50" corrected in [[#why]] and R5; [[#ac-13]] pins the floor; [[#ac-16]] gains the cliquet row (A0) and the floor mutation |
| B-4 (the lock-order mutation could not fail) | [[#r11-hold-helper]] "The locks": a `_snapshot_lock` timeout returns before `_store_lock` is touched; [[#ac-17]]'s lock-order case: a competitor holds ONLY `_snapshot_lock`, a `snapshot=True` hold returns `skipped:lock_busy`, a write op completes meanwhile, and the recorder shows no `_store_lock` acquisition by the helper |
| B-2 / M-4 (deadline) | R11: `deadline_s` removed from `_catalog_hold`; ONE statement path `CatalogHold._exec` that 18.3 gives the per-statement deadline check; 18.3 adds `interruptible` |
| S-1 (AST bypassable; census misses three CHECKPOINTs) | R11 "The bypass rule": the walk covers `daemon.py` AND `catalog_maint.py`, `.execute(` only in executors, the literal only at named sites and named exemptions (18.3 I1); [[#ac-17]] mutations: a lock in `catalog_maint.py`, a CHECKPOINT in a `Store` method; [[#why]] no longer claims "every CHECKPOINT that holds `_store_lock`" |
| S-2 (23.5's obligations; `after` drops HEAD's `_snapshot_lock` ordering) | R11: `_inflight(label)` registration, no helper alarm line (a per-label threshold on 23.5 R4's one alarm), `after_locked` + `after` phases, `snapshot(pin_to)` with the fragment flush and `L0`; [[#r8-snapshot-hold]] names them as behaviour; R4 D1's warning is 23.5's line; [[#ac-12]] asserts `_snapshot_lock` held during the mirror refresh, `pin_to`, the flush; [[#ac-17]] the holder name and the one alarm; header depends on 23.5 and 23.1 R1.6 |
| S-5 (two ops read-modify-write `catalog_state.json`) | new [[#r13-state]] `update_state` under a process-wide lock; R2 (f) and R4 D2 use it; new [[#ac-18]] |
| M-1 (stale lines, false "src unchanged") | [[#facts]] re-cited at `23ad703` (unchanged through `7c8d6c5`); L1-L6, R7 and `#why` lines updated |
| M-5 (AC-1's wait mutation had no competitor) | [[#ac-1]] gains the 0.5 s competitor variant |
| M-7 ("each calls `_catalog_hold` once" vs AC-5's seam split) | [[#ac-17]]: exactly one `_catalog_hold` call reachable from each op, walking into `catalog_maint.py` |

## Revision round 3 {#rev-round-3}

From ch-bsd plan-18 r2 ([[bsd-plan18-r2-spec-diffcheck-cb7bf5b]]). Each mutation added here was
reasoned against the code it must reject; the census below was read at `master` `b381b6d`.

| finding | change |
|---|---|
| N-B2 (the rule is red at 18.2 GREEN and cannot see `store.py`) | [[#r11-hold-helper]] "The bypass rule": the walk covers EVERY `src/refmatrix/*.py`; exemptions by qualified function name; a CHECKPOINT is a SQL-statement string constant (`^\s*(FORCE\s+)?CHECKPOINT\b`, f-string parts included, docstrings skipped); a PERMANENT list (`Store.rebuild_entities_indexes`, `cli.merge_verb_aliases`, `_op_replica_merge`, `replica_merge.merge_slots`) and a STAGED list (`Daemon.serve_forever` for the inline init rebind, `Daemon._bootstrap_rotation_if_needed`, `cli.compact`), which 18.3 AC-14 requires EMPTY; the census at `b381b6d` is stated so the rule is green on 18.2's correct code. [[#ac-17]] and [[#ac-14]]: the `store.py` mutation now fails as written, plus a `backend.py` variant |
| N-M2 (the state-writer check was attributed to AC-17 but absent; a path match is defeatable) | [[#r13-state]]: one string-constant rule (`catalog_maint.STATE_FILE`, referenced only in `update_state` / `read_state`, no path helper); [[#ac-17]] lists it with the mutation "a second writer FAILS" |
| N-M3 (23.5 item 4's flush-order AST not carried) | [[#r8-snapshot-hold]]: the assertion moves to `CatalogHold.snapshot`; [[#ac-12]] lists it and a flush-after-CHECKPOINT mutation |
