---
gmd: "0.1"
id: task-18.3-offline-reclaim
title: "Task 18.3: an in-daemon catalog reclaim — rewrite the writer slot into a sibling file, gate it, swap it and reopen it under ONE bounded `_store_lock` hold on the shared catalog-hold helper; hand-run first, then an armed, reason-gated step on 17.2's tick"
tags: [task, duckdb, catalog, reclaim, in-daemon, swap, lock, maintenance]
metadata:
  node_type: task
  status: pending
  created: 2026-10-15
  updated: 2026-10-15
---

# Task 18.3: in-daemon catalog reclaim {#root}

> Plan: [plan-18-duckdb-store-maintenance](../plan-18-duckdb-store-maintenance.md)
> Status: Pending. **Rewritten 2026-10-15 from the 18.1 verdict** ([[#rev-18-1-verdict]]): C12
> is lifted (d9be) and the reclaim is RESHAPED from an offline stop-the-daemon rewrite to an
> in-daemon rewrite-and-swap (d9bf). It is no longer conditional. It needs a fresh ch-bsd spec
> review and the user's approval before it is built (d9bf: "rewritten and re-reviewed before
> approval"). d9bp/d9bq/d9br (PROVISIONAL, from ch-bsd 18.1 r1) amend it: the swap is gated on
> bug-112's FIX plus a sentinel read-back, no offline route survives, and feasibility is decided
> on a LOADED hold. Revision round 2 (same day, ch-bsd plan-18 r1, d9bw; [[#rev-round-2]])
> fixes the rollback's foreign WAL, makes the deadline a real bound, converges the writer reopen
> and the writer-lost exit with the bug-113 fix, and cleans crash residue. The file name and id
> keep `offline-reclaim` so inbound links stay stable.
> Wave: 4 ([[plan-review-2026-10-14#t10-waves]]).
> Depends on:
> - **bug-112 FIXED and reachable from `master`** (an in-process `duckdb.connect` of a path that
>   is already open returns the cached database; [[bug_registry]]). The fix is in progress on
>   branch `bugs-112-113-118`. 18.3 does not start before it merges, and AC-18 reproduces the
>   swap write-loss against the merged fix (d9bp a). What 18.3 uses from it (read on the branch,
>   [[#facts]] I4): `backend.open_duckdb` is THE opener (a read-only open is a private
>   `:memory:` instance that `ATTACH`es the file `READ_ONLY`; a write open first closes every
>   REGISTERED holder bound to a replaced inode, `_close_stale_holders`). Closing a stale
>   holder from another thread is safe only under `_store_lock`, so 18.3's reopen runs inside
>   the hold and asserts it (R8).
> - **bug-113's fix, converged before it merges** (d9bw d): its `_writer_lost` becomes the ONE
>   immediate writer-lost exit and its `_reopen_writer_after_merge` delegates to the ONE reopen
>   (R8 "THE reopen", "THE writer-lost exit"). This is raised on the bug branch, which adopts it
>   before merge.
> - **23.5** ([[task-23.5-read-path-and-holder-bounds#cross-plan-18]]): `Daemon._inflight`, the
>   one `lock hold:` alarm, and item 5, the compaction port 18.3 owns (R8; d9bw c).
> - **23.1 R1.6** ([[task-23.1-queue-and-drain#r1-6-proposed]]): `Daemon._install_writer_store`,
>   `Store.writer_lock`, `Store.close()` re-raising `WriterLockNotHeld` and recording
>   `close_errors`.
> - **18.2**: the shared catalog-hold helper ([[task-18.2-catalog-maintain-step#r11-hold-helper]]),
>   the `catalog` CLI group, `catalog_state.json` and its growth band, Table D's constants.
> - 17.2 (the `maintenance_steps` registry and per-(store, step) arming), 23.0 (test sandbox),
>   23.2 (`recorded_daemon`).

rel: part-of -> [[plan-18-duckdb-store-maintenance]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-18.1-catalog-measurement]]
rel: depends-on -> [[task-18.2-catalog-maintain-step#r11-hold-helper]]
rel: depends-on -> [[task-23.1-queue-and-drain#r1-6-proposed]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: depends-on -> [[task-17.2-hub-nightly-tick#r7-unarmed]]
rel: depends-on -> [[bug_registry]]
rel: derives-from -> [[bsd-plan18-task18-1-measurement-r1-8a93ab1]]
rel: derives-from -> [[bsd-plan18-r1-spec-review-b84fd8d]]
rel: depends-on -> [[task-23.5-read-path-and-holder-bounds#cross-plan-18]]
rel: related-to -> [[plan-review-2026-10-07#consolidations]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]

## Why {#why}

On DuckDB 1.5.3 only a rewrite into a new file gives free blocks back
([[task-18.1-catalog-measurement#facts]] F2). 18.1 measured the fleet on copies on 2026-10-15
([[plan-18-duckdb-store-maintenance#verdict-18-1]]):

- four stores pay: refmatrix (789.0 -> 176.8 MiB, A2), global (241.8 -> 34.0, A2), cliquedb
  (230.5 -> 99.8, A2) and viascope (291.5 -> 158.3, A1). About 1.1 GiB is reclaimable in the
  writers, and the same again in their snapshots (18.1 F5);
- every rewrite is in C0, and the slowest is refmatrix at a max of 1.98 s.

18.1 R3 recorded an in-daemon variant as "proposable only if EVERY store's max `rewrite_s ≤ 5`",
which leaves a 2x margin under 18.2's 10 s hold ceiling. That holds on every store. An in-daemon
swap removes everything that made the offline design heavy and risky: the watchdog pause, the
daemon stop, `daemon.lock`, the launchd kickstart, and the minutes of downtime. The cost is a
hold of a few seconds on a live daemon, which 18.2 already knows how to bound and measure.
{#why-body}

## Facts at HEAD `23ad703` {#facts}

The catalog facts F1-F7 are in [[task-18.1-catalog-measurement#facts]] and the lock and liveness
facts L1-L6 in [[task-18.2-catalog-maintain-step#facts]]. The facts this design rests on:

- **I1 The shape already exists six times.** Each of these holds `_store_lock` around a DuckDB
  maintenance statement and a file operation, and each spells it out by hand:
  - the snapshot tick (`_snapshot_catalog`, `daemon.py:2669`: CHECKPOINT `:2702`, child copy
    `:2714`, `os.replace`);
  - `_op_checkpoint` (`:3956`: index DROP/CREATE + CHECKPOINT `:3971`);
  - the init slot rebind (CHECKPOINT `:1762`, close, `Store(` `:1768`, fallback `:1791`);
  - `_bootstrap_rotation_if_needed`'s two branches (`:2878`: CHECKPOINT `:2924` + close + child
    copy `:2930` + `Store(` `:2936`; CHECKPOINT `:2960` + close + `shutil.copy2` + `Store(`
    `:2972`);
  - `_op_replica_merge` (`:5485`: CHECKPOINT `:5533`, `Store(` `:5575`, `:5593`, `:5642`;
    fenced since d9ae, bug-113 open);
  - and `rmx compact` (`cli.py:7630`, its CHECKPOINT `:7692`) does it OUT of the daemon (F3's
    four flaws).

  **Three more CHECKPOINTs** (ch-bsd r1 S-1; re-read at `7c8d6c5`, `src/` equal to `23ad703`),
  each ported or exempted by name (R8):
  - `store.py:3899`, inside `Store.rebuild_entities_indexes` (the entities rebuild's own fold
    after its DDL). It is reached under a hand-spelled `with … _store_lock:` by
    `_run_pending_repair` (`daemon.py:1418`, boot) and `_op_repair_entities` (`:5391`). Those
    two holds are PORTED onto the helper (label `repair_entities`); the CHECKPOINT stays in the
    `Store` method as the one named `store.py` exemption, because it closes that rebuild's own
    DDL and is timed by the hold that calls it;
  - `replica_merge.py:391`, in `merge_slots` (the fenced merge's target build): EXEMPT with
    `_op_replica_merge` (fenced, d9ae);
  - `cli.py:3785`, in `merge_verb_aliases` (an offline verb-alias merge with the daemon down,
    like `rmx compact`): EXEMPT; there is no daemon and no `_store_lock` on that path, so the
    helper does not apply. (`cli.py:7692` goes with `rmx compact`, R10.)
- **I2 Lock order.** `_snapshot_catalog` takes `_snapshot_lock` (a `threading.Lock`,
  `daemon.py:833`) and then `_store_lock` (`:2692`, `:2700`). Anything that takes `_store_lock`
  first and then wants the snapshot inside the same hold would invert that order.
- **I3 `Store.close()`** (`store.py:2166`) flushes fragments, closes the read view and the
  connection, and today swallows every error. 23.1 R1.6 item 4 makes it re-raise
  `WriterLockNotHeld` after closing and record other flush errors in `close_errors`.
- **I4 bug-112, reproduced on this exact swap** ([[bsd-plan18-task18-1-measurement-r1-8a93ab1#b-1]],
  duckdb 1.5.3). A `duckdb.connect()` to a path that already has an open connection in the
  process returns THAT database. With a second in-process `connect` to the slot still open:
  close the first, `os.replace` a new file over the path, and `connect` again. The reopen
  returns the OLD database, and a write through it, followed by a CHECKPOINT, never reaches the
  file on disk: the row is lost silently. A cursor of the closed connection does not trigger
  it; a second `connect` does. `gc` cannot see the holder. A fresh process (the old offline
  design) has no instance cache; an in-daemon swap does, so it needs bug-112's fix AND a
  per-run proof that the reopened connection is the new file (R4 step 11).
  - **The fix, as read on `bugs-112-113-118`** (`backend.py:101-150`): `open_duckdb(path,
    read_only=…)` is the one opener. A read-only open is a private `:memory:` instance that
    `ATTACH`es the file `READ_ONLY`, so it keeps its own (old) snapshot until it closes. A write
    open calls `_close_stale_holders`, which closes every REGISTERED connection bound to a
    replaced inode before `duckdb.connect`. An unregistered raw `duckdb.connect` is invisible
    to it, which is why the sentinel stays (AC-4 b). Closing a connection another thread may
    be using is safe only while that thread cannot run a statement, that is, under
    `_store_lock` (R8 "THE reopen").
- **I9 The idle number is not the loaded number** ([[bsd-plan18-task18-1-measurement-r1-8a93ab1#s-1]]).
  18.1's refmatrix rewrite took 1.94 s idle in a dedicated child; on the same copy with 6
  concurrent read loops it took 3.60 / 3.72 / 3.92 s. The rest of the hold (gate with content
  hash 0.10 s, CHECKPOINT ~0, copy 0.04-0.18 s, open 0.005 s) added about 0.3 s. The rewrite's
  peak RSS was 884 MiB, which in the daemon adds to the serving process.
- **I5 bug-113's lessons** (the merge defect). Its target was built by a separate schema
  (`init_catalog`) that lagged the Store's; it left a connection open on error; and it returned
  with the writer closed. `COPY FROM DATABASE` copies the writer's OWN schema, so the first
  lesson does not apply here. The other two are R6's rules.
- **I6 The exits.** The LaunchAgent's `KeepAlive {SuccessfulExit: false}`
  (`launchctl.py:258`) respawns on a non-zero exit, and the boot path opens the slot named by
  the `active` marker. But `_fast_exit_if_invalidated` (`daemon.py:1443`) RETURNS unless
  `_is_fatal_invalidation(exc)`: a failed link or a failed identity check is not a DuckDB
  invalidation, so it does not exit, and where it does fire it queues an entities rebuild
  (`_mark_repair_needed`) for the respawn (ch-bsd r1 S-3). The bug-113 fix adds
  `_writer_lost` (branch `daemon.py:1443`), which sets shutdown, sleeps `RMX_DEGRADE_EXIT_S`
  (2 s) with the lock released, and then `os._exit(2)`. R8 makes ONE immediate writer-lost
  exit of it.
- **I7 What a hold can cost.** The hub restarts a daemon after 3 missed pings 15 s apart with a
  heartbeat older than 60 s (18.2 L2). A hold of at most 10 s can miss at most one 2 s ping and
  cannot age the heartbeat past 60 s.
- **I8 Slot offsets** (`catalog.<S>.offset`, `daemon.py:2839`) record the `facts.log` position
  a slot is current to. A rewrite under the same slot letter carries the same rows, so the
  offset stays true and is not touched.
- **I10 Every reopen writes a WAL, and DuckDB replays a FOREIGN WAL silently**
  ([[bsd-plan18-r1-spec-review-b84fd8d#b-1]], `p3b_wal.py`, duckdb 1.5.3). `Store.init()` runs
  `UPDATE linkage_types SET inverse_of=…` on every open (`store.py:1199-1206`); after a reopen
  on orderly's copy the slot's `.wal` was 1,204 bytes. A WAL written against the NEW file, left
  beside the slot when the OLD inode is restored, is replayed into the old file on the next
  open without an error: DuckDB logs deletes by row id and a rewrite renumbers row ids, so the
  probe's restored file came back with 52,038 rows for 50,000 and rows deleted in the old file
  reappeared. The slot's NAME is safe only together with a `.wal` that belongs to the inode at
  that name.
- **I11 An interrupt between statements is dropped**
  ([[bsd-plan18-r1-spec-review-b84fd8d#b-2]], `p1_interrupt.py`). `con.interrupt()` with no
  statement running, or during Python work between two statements, is lost: the next 10 s
  query ran to completion. An interrupt during a running `COPY FROM DATABASE` stops it in
  0.55 s, and the partial target has no `.wal`.
- **I12 A closed writer `Store` reopens itself** (ch-bsd r1 S-7). `Store._connect()`
  (`store.py:1228`) reconnects whenever `_conn is None`, and `close()` sets it to `None`. The
  flush tick evaluates `_periodic_flush(self.store, self._store_lock, …)` (`daemon.py:2136`)
  BEFORE it takes the lock, so a pre-swap `Store` reference can outlive the swap and open the
  slot path again, with stale partition and fragment caches (bug-098's and bug-105's classes).

{#facts-body}

## The design in one picture {#design}

```
verb rmx_catalog_reclaim ──> daemon op catalog_reclaim
  every call (not status / list-backups): residue sweep first (R3 h)
  dry_run=True  : REHEARSAL, lock-free, in children, on a copy of the snapshot (R2)
  dry_run=False : preconditions (R3), reclaim_inflight marker, then ONE hold (R4):

  _catalog_hold("reclaim", snapshot=True, lock_wait_s=30)
    takes _snapshot_lock, then _store_lock; registered as _inflight("reclaim")   (I2)
    steps 1-2, uninterruptible: flush_fragments; CHECKPOINT
    Phase A, inside h.interruptible(5 s): flag + re-interrupt every 50 ms,
      and a deadline check before EVERY statement (I11):
      ATTACH new; COPY FROM DATABASE; CHECKPOINT new; GATE (R5); SENTINEL; DETACH
    Phase B, the swap (no <slot>.wal at any replace, I10):
      close writer -> link slot to backups/ -> os.replace(new, slot)
      -> THE reopen (Daemon._reopen_writer, under _store_lock, through open_duckdb)
      -> SENTINEL read-back + total_blocks (+ inode, counts) -> drop sentinel
    Phase C: snapshot() — the snapshot tick's own locked body
  after_locked: read-only link, mem mirror          (still inside _snapshot_lock)
  after: write-through check of the snapshot in a child, baseline reset, marker
         cleared, ledger, rmxd.log
  any failure -> rollback (R6): close the reopened writer, move its .wal aside, restore,
                 reopen; a rollback that fails -> THE writer-lost exit (os._exit(2))
```

## Requirements {#requirements}

1. **R1 Verb, op, surfaces, one ledger.** {#r1-verb}
   - Verb `rmx_catalog_reclaim(dry_run: bool = True, confirm: str | None = None,
     status: bool = False, list_backups: bool = False, clear_disabled: str | None = None, *,
     invoked_by: str) -> dict`, daemon op `catalog_reclaim`, CLI `rmx catalog reclaim
     [--confirm <run_id>] [--status] [--list-backups] [--clear-disabled <run_id>]`, MCP parity
     through the verb-parity test. `clear_disabled` is hand-only (`cli` / `mcp`) and must name
     the `run_id` recorded in the mark it clears: `reclaim_disabled` (R6) or `rewrite_too_slow`
     (R11). Each mark carries a `run_id`, so one flag clears either, and only by naming it.
     `reclaim_hold_over` is not cleared by this flag (R7 c).
   - `invoked_by` is keyword-only and adapter-set (17.1 R1), from the closed set
     `{cli, mcp, hub}`; any other value raises `ValueError` naming it.
     - `cli` / `mcp` with `dry_run=False` need `confirm=<rehearsal run_id>` (R3 a).
     - `hub` never passes `confirm`; with `dry_run=False` it is the armed tick step (R9), which
       rehearses inside the same op. `hub` with a `confirm` raises `ValueError`.
   - The CLI calls the daemon only. With the daemon not answering it exits non-zero with
     `daemon not answering; catalog reclaim never runs in-process` and opens no file under the
     root (bug-110).
   - Single-flight and a lock-free `status=True`, in 17.1 R11's shape. Every completed run
     appends one fsynced `<root>/maintain/runs.jsonl` line with `step: "catalog_reclaim"`
     (17.1 R12 shape; fields in R2 and R4).
2. **R2 The rehearsal** (`dry_run=True`). It runs in the daemon process with no `_store_lock`
   hold and no DuckDB statement in-process. {#r2-rehearse}
   - Disk check first: free space under the root ≥ `2 × snapshot bytes + 256 MiB`, else
     `refused:disk`.
   - Copy `catalog.read.duckdb` to `<root>/maintain/reclaim-scratch-<run_id>/snap.duckdb` with
     `_copy_out_of_process`.
   - Three times on fresh targets, a child runs `python -m refmatrix.catalog_maint rewrite
     <copy> <target>`, which calls the PRODUCTION `catalog_maint.rewrite_into(con, src, target)`
     (the function R4 runs in the daemon). It records `rewrite_s` (median, and max over EVERY
     run) and `rewrite_bytes` (the MEDIAN of the runs; one rewrite's size varies by about 1.3 %,
     [[bsd-plan18-task18-1-measurement-r1-8a93ab1#s-5]]).
   - One child runs `python -m refmatrix.catalog_maint gate <copy> <target>`, which calls the
     PRODUCTION `catalog_maint.gate(con, a, b)` (R5) and records `gate_s` and its verdict.
   - The report has `file_bytes` (the copy's size), `rewrite_bytes`, `r`, `reclaimable`, the
     18.1 Table A band, `rewrite_s_median`, `rewrite_s_max`, `gate_s`,
     `idle_hold_s = rewrite_s_max + gate_s`, the gate verdict, the duckdb version, and
     `rehearsal_sha` (sha256 of the canonical report JSON).
   - The rehearsal is IDLE, in a child: it is a prefilter, not the feasibility number (I9). An
     `idle_hold_s` over `RMX_CATALOG_RECLAIM_BUDGET_S` (5 s) cannot pass under load, so it
     marks the store `rewrite_too_slow` (R11). The loaded number is R14's and, on every real
     run, R4's own `hold_s`.
   - **The baseline** (18.2 R5, through `update_state`, 18.2 R13). A successful rehearsal
     writes its median `rewrite_bytes` as the baseline (`baseline_source:
     "rehearsal:<run_id>"`) when `catalog_state.json` has none, OR when its own Table A band
     is A0 (d9bw a: the re-seed that keeps a legitimately grown store from a permanent false
     A2). An A1 or A2 rehearsal never moves an existing baseline.
   - The scratch dir is removed afterwards. Its removal and its byte count are in the report.
     A removal that fails is an error, not a skip.
3. **R3 Preconditions of a real run**, checked before any hold. Each failure returns
   `refused:<reason>`, records no hold, changes no file, and writes a ledger line with
   `ok: false`. {#r3-preconditions}
   - (a) **The rehearsal.** For `cli` / `mcp`: a `runs.jsonl` line with this `run_id`,
     `step: "catalog_reclaim"`, `dry_run: true`, `ok: true`, finished ≤
     `RMX_CATALOG_RECLAIM_MAX_AGE_S` (86,400) ago (`refused:no_rehearsal` /
     `refused:rehearsal_stale`). For `hub`: the rehearsal R2 runs first inside the same op.
   - (b) **Band and feasibility.** The rehearsal's band is A1 or A2 (`refused:band_a0`), its
     gate passed (`refused:rehearsal_gate`), its `idle_hold_s` is within the budget, and
     `catalog_state.json` has no `rewrite_too_slow` mark (both `refused:rewrite_too_slow`, R11).
     R14's loaded verdict is not read here: R14 runs on tmp copies, never on the live store.
     On the live store the bound is R4's deadline (a real bound after B-2) and R11's
     two-deadline mark; R14's verdict gates R12's hand procedure (ch-bsd r1 S-4).
   - (c) **Drift.** The writer slot's `file_bytes` now is within 10 % of the rehearsal's
     (`refused:drift`).
   - (d) **Disk.** Free space ≥ `2 × rewrite_bytes + 256 MiB`: the new file plus the new
     snapshot's tmp copy. The old slot is kept as a hard link and costs no new space
     (`refused:disk`).
   - (e) **WAL.** The slot's `.wal` is ≤ `RMX_CATALOG_WAL_MAX_BYTES` (18.2, 64 MiB), so the
     CHECKPOINT inside the hold is bounded (`refused:wal_large`).
   - (f) **The slot is bound.** `d._st().db_path` equals `_replica_file(_active_slot)` and
     health's `slot_bound` is true. A daemon serving the legacy fallback is never reclaimed
     (`refused:slot_unbound`).
   - (g) **Not disabled.** `catalog_state.json` has no `reclaim_disabled` (R6 and R4's
     write-through check; every caller; `refused:reclaim_disabled`). For `hub` only, also no
     `reclaim_hold_over` (R7 c; `refused:reclaim_hold_over`), no `checkpoint_disabled` (18.2
     R4: a store whose plain CHECKPOINT ran over 10 s gets no automatic rewrite) and no
     unremoved pre-reclaim backup (R9). The two disable keys are separate (ch-bsd r1 S-4):
     `reclaim_disabled` means a failed rollback or a failed write-through and is cleared only
     by `--clear-disabled <run_id>`; `reclaim_hold_over` means a slow but correct run and is
     cleared by a hand run whose `hold_s ≤ 10`, as 18.2 D2 clears its own flag.
   - (h) **Crash residue is swept first** (ch-bsd r1 S-6). Every `catalog_reclaim` call except
     `status` and `list_backups`, under the op's single flight and before any rehearsal or
     hold, runs `catalog_maint.sweep_residue(d)`:
     - **Files.** Every `catalog.*.reclaim-*.duckdb`, `catalog.*.duckdb.rollback`, and the
       `.wal` of either, in the root, is MOVED to
       `backups/<name>.residue-<UTC stamp>` with one log line each (never deleted). Each of
       these names matches `store_bytes`'s `catalog*.duckdb` / `*.wal` globs
       (`daemon.py:3864`) and `discovery.footprint`'s, so an orphan would be counted as live
       catalog. A `maintain/reclaim-scratch-*` dir left by a crashed rehearsal is removed (it
       holds only copies), with its bytes counted and logged.
     - **The sentinel.** When `catalog_state.json` carries `reclaim_inflight` (written through
       `update_state` before R4's hold and cleared in its `after`), the run that set it did not
       finish. The sweep then takes one short hold, `d._catalog_hold("reclaim_residue",
       lambda h: h.drop_sentinel())`: `DROP TABLE IF EXISTS _rmx_reclaim_sentinel` +
       `CHECKPOINT`, logging whether the table existed. Without this, a SIGKILL after step 9
       boots with the sentinel in the live slot, the next COPY carries it, and step 5's
       `CREATE TABLE` fails on every later run.
     - The sweep's counts (`residue_moved`, `residue_bytes`, `sentinel_dropped`) are in the
       report and the ledger line. A move or a drop that fails is an error outcome
       (`failed:residue`), not a skip.
4. **R4 The one hold.** The real run is ONE call of 18.2's helper,
   `d._catalog_hold("reclaim", body, snapshot=True, lock_wait_s=RMX_CATALOG_LOCK_WAIT_S,
   after_locked=…, after=…)` ([[task-18.2-catalog-maintain-step#r11-hold-helper]]). It reuses
   18.2's wait (30 s) and Table D's 10 s ceiling for the whole hold, and adds one constant, the
   5 s Phase A budget (d9bp: the 5 s gate, applied to the loaded number). On a wait timeout the
   outcome is `skipped:lock_busy` with no hold. {#r4-hold}
   - **Before the hold.** `update_state` writes `reclaim_inflight: {run_id, at}` (18.2 R13).
     The `after` callback clears it on every outcome that returns; a crash leaves it, and the
     next call's residue sweep acts on it (R3 h).
   - **Lock order and naming.** `snapshot=True` makes the helper take `_snapshot_lock` and THEN
     `_store_lock` (I2). Both waits are inside the one `lock_wait_s` budget. The helper
     registers the hold as `_inflight("reclaim")` (18.2 R11; 23.5), and its alarm threshold is
     the 2 s D1 edge, on 23.5's one alarm line.
   - **Steps 1-2, inside the hold and NOT interruptible** (ch-bsd r1 M-4; d9bt Q-D's wording,
     "Phase A = rewrite + gate", now matches):
     1. `if st.has_dirty_fragments(): st.flush_fragments()`: dirty bitmap fragments are in
        memory, and the COPY reads tables;
     2. `h.checkpoint()`: the WAL is folded into the slot.

     These are the snapshot tick's own short statements; a deadline that could interrupt them
     would only move their cost to the next snapshot tick.
   - **Phase A, interruptible.** Run inside `with h.interruptible(RMX_CATALOG_RECLAIM_BUDGET_S):`
     (I11; ch-bsd r1 B-2, d9bw "Q-D stands after the interrupt is made a real bound"):
     3. `h.rewrite_into(new)` with `new = <root>/catalog.<S>.reclaim-<run_id>.duckdb` (a path no
        connection in the process has opened; bug-112): `ATTACH`, `COPY FROM DATABASE`,
        `CHECKPOINT` on the new file, timed as `rewrite_s`;
     4. `h.gate("rc")` (R5) between the writer and the new file, timed as `gate_s`. It also
        records the pre-swap per-table counts;
     5. **The sentinel** (d9bp a). AFTER the gate passes: `CREATE TABLE
        rc._rmx_reclaim_sentinel(run_id VARCHAR)`, insert this `run_id`, and `CHECKPOINT` the
        new file. Then record the new file's `PRAGMA database_size` `total_blocks`;
     6. `DETACH`. The new file's `.wal` must be absent or 0 bytes.

     **How the deadline bounds Phase A.** `interruptible(budget)` (added by 18.3 to
     `CatalogHold`) starts a timer at entry, so the budget runs from the end of step 2:
     - when the budget passes, the timer sets `h.deadline_hit = True` and calls
       `con.interrupt()` on the writer connection, then RE-ISSUES `con.interrupt()` every
       50 ms (`RMX_CATALOG_INTERRUPT_REPEAT_S`) until the block exits. An interrupt that lands
       between two statements is dropped by DuckDB (I11); the next one lands on the next
       statement;
     - every statement in Phase A runs through `CatalogHold._exec` (18.2 R11), which calls
       `h.check_deadline()` first and raises `DeadlineExceeded` if the flag is set. That covers
       the gate's per-table loop, the sentinel's three statements and any Python between them;
     - on exit the block stops the timer and JOINS its thread before returning, so no interrupt
       is issued after Phase A ends, and an interrupt pending with no statement running is
       dropped (I11), so Phase B never sees one.

     Phase A then raises `DeadlineExceeded` (or DuckDB's `InterruptException`), R6 A runs,
     the outcome is `failed:deadline`, and the store's consecutive-deadline count goes up
     (R11).
   - **Phase B, the swap.** Not interruptible; each step is timed. `CatalogHold.swap` asserts
     at EVERY `os.replace` it makes, forward or back, that no `<slot>.wal` exists (or that it
     is 0 bytes): the invariant of R6 is "the slot name plus a `.wal` that belongs to the inode
     at that name" (I10).
     7. `h.close_writer()`: `Store.retire()` on the bound writer (R8: close, then the Store is
        terminally closed, I12). A raised error or a non-empty `close_errors` goes to R6 B,
        with nothing renamed yet.
     8. The slot's `.wal` must be absent or 0 bytes, else R6 B.
     9. `os.link(slot, backups/catalog.<S>.pre-reclaim-<run_id>.duckdb)`, then
        `os.replace(new, slot)`, then `fsync` of the root and `backups/` directories. The slot
        is never unlinked or renamed away: at every instant its path names either the original
        inode or the gated new one (R6 invariant).
     10. `h.reopen_writer(slot)`: THE reopen (R8), `Daemon._reopen_writer`, which runs under
         the `_store_lock` this hold already holds (it asserts that) and opens through
         `backend.open_duckdb`, so a registered stale holder of the old inode is closed first
         (I4). `Store.init()` writes a WAL on this open (I10), which is why R6 B closes this
         writer before any restore.
     11. **Identity check and sentinel read-back.** All of these must hold, else R6 B:
         - `SELECT run_id FROM _rmx_reclaim_sentinel` on the reopened writer returns exactly
           this `run_id`. The old file has no such table, so a reopen that got the cached old
           database (I4) fails here (d9bp a);
         - its `PRAGMA database_size.total_blocks` equals step 5's;
         - the slot's `st_ino` equals the inode the new file had before step 9;
         - the per-table counts equal step 4's.

         Only the sentinel and `total_blocks` detect I4 (ch-bsd r1 M-2). The `st_ino` leg
         stats the PATH, which step 9's `os.replace` just set, so a cached old database passes
         it; it guards against a wrong path, not against I4. Neither of the first two may be
         dropped on the belief that the inode backs it up.

         Then `DROP TABLE _rmx_reclaim_sentinel` through the reopened writer. That is the
         first write through the new connection, and the after-release check proves it reached
         disk.
   - **Phase C.** `h.snapshot()`: the snapshot tick's own locked body (18.2 R8: fragment flush,
     CHECKPOINT, child copy of the slot to `catalog.read.duckdb.tmp`, `os.replace`), run inside
     the same hold so the snapshot is the reclaimed file before the hold ends (F5, R7).
   - **`after_locked`** (after `_store_lock` is released, inside `_snapshot_lock`; 18.2 R11):
     swing `read_only.duckdb` and refresh the mem mirror, exactly as the snapshot tick does.
   - **`after`** (both locks released): a child opens a copy of the new snapshot and checks
     that `_rmx_reclaim_sentinel` is ABSENT and the per-table counts equal step 4's. That
     proves the reopened connection's first write reached the file on disk, the exact loss in
     I4. Writes after the release make a rollback unsafe, so a failure here does not roll back:
     it writes `reclaim_disabled` (cause `write_through`, with this `run_id`), logs one loud
     line, and makes the hub row hot through `catalog_hold_over`'s path (18.2 R7). Then reset
     18.2's baseline (R7 b), clear `reclaim_inflight`, append the ledger line, and log one
     `rmxd.log` line. Every state write is an `update_state` call.
   - **Memory.** The COPY runs in the daemon, so its working set adds to the serving process: a
     peak of 884 MiB on refmatrix's copy (I9). The ledger line records `ru_maxrss` before and
     after the hold, and R14 measures the peak per store. This cost is stated, not hidden.
   - **The report and the ledger line** carry: `wait_s`, `hold_s`, the D band of `hold_s` (18.2
     Table D), and per-phase seconds (`flush_s`, `checkpoint_s`, `rewrite_s`, `gate_s`,
     `sentinel_s`, `close_s`, `swap_s`, `reopen_s`, `snapshot_s`), plus `phase_a_s` against the
     budget and `deadline_hit`. They also carry `file_bytes_before`, `file_bytes_after`,
     `rewrite_bytes`, `r`, the backup path and its bytes, `ru_maxrss` before and after, the
     rehearsal `run_id` and its `idle_hold_s`, `hold_vs_idle = hold_s / idle_hold_s` (the live
     load factor, I9), and the residue sweep's counts (R3 h).
5. **R5 The gate: ONE function shared with 18.1** (d9br). `catalog_maint.gate(con, a, b) ->
   list[str]` is used by the rehearsal child, inside the hold, and by 18.1's script once its
   remedy imports it ([[task-18.1-catalog-measurement#r1]] "The gate"; its AC-4 variants test
   the same legs). It returns an empty list on a pass; each difference names the object and
   both values. Its legs: {#r5-gate}
   - **rows:** the table sets are equal, and for every table `count(*)` and an
     order-independent content hash over EVERY column (for example `sum(hash(<col>))` per
     column) are equal, so a one-cell change in a non-key column fails it;
   - **columns:** per table, `duckdb_columns()` name, type, default and nullable are equal (a
     changed `nextval` default, which ids depend on, fails it);
   - **constraints:** the `duckdb_constraints()` `constraint_text` multiset per table is equal;
   - **indexes:** the `duckdb_indexes()` `sql` set is equal (a definition, not only a name);
   - **sequences:** every sequence's last value is equal (F2: `COPY FROM DATABASE` carries
     sequence state);
   - **other objects:** the non-internal views (with their `sql`), macros (`duckdb_functions()`
     with `internal = false`) and user types (`duckdb_types()` with `internal = false`) are
     equal.

   The sentinel table (R4 step 5) is created AFTER the gate and dropped after the read-back, so
   the gate never sees it. The whole gate cost 0.10 s for the content hash plus 0.005 s for
   counts on refmatrix's copy (I9).
6. **R6 Rollback, never a guess.** {#r6-rollback}
   - **Invariant** (restated for I10, ch-bsd r1 B-1). At every instant the slot's NAME holds
     a complete file (the original or the gated new one), AND any `<slot>.wal` beside it
     belongs to the inode at that name. Only `os.link` and `os.replace` touch the slot's name,
     and `CatalogHold.swap` asserts that no `<slot>.wal` exists at each replace it makes,
     forward or back (R4 Phase B). So a crash at any point (SIGKILL, power loss, an exit)
     leaves a slot that a boot opens with every row and no foreign replay.
   - **A: Phase A fails** (gate difference, deadline, statement error). The writer was never
     closed. `DETACH` runs in a `finally`. A gate-failed, complete new file is moved to
     `backups/catalog.<S>.reclaim-failed-<run_id>.duckdb` and kept. An interrupted, partial
     file is deleted (I11: it has no `.wal`), and its path and bytes are reported
     (`partial_removed`). The outcome is `failed:gate` or `failed:deadline`, with `ok: false`.
   - **B: Phase B fails** (close error, WAL present, link or replace error, reopen error,
     identity mismatch). This path runs still inside the hold, IN THIS ORDER:
     1. **Close the reopened writer**, if step 10 opened one: `h.close_writer()` (its close
        checkpoints and removes the WAL that `init()` wrote, I10).
     2. **No foreign WAL.** Require `<slot>.wal` to be absent or 0 bytes. If it is not,
        `os.replace(<slot>.wal, backups/catalog.<S>.reclaim-failed-<run_id>.duckdb.wal)`
        BEFORE the restore, with one log line naming its size.
     3. **Restore.** If the replace happened, `os.link(slot,
        backups/…reclaim-failed-<run_id>.duckdb)` keeps the new file. Then `os.link(backup,
        <slot>.rollback)` and `CatalogHold.swap`'s `os.replace(<slot>.rollback, slot)` restore
        the original inode atomically (the no-`.wal` assertion holds here by steps 1-2).
     4. **Reopen**: `h.reopen_writer(slot)` (THE reopen, R8), then an identity check against the
        PRE state: per-table counts equal step 4's, and `total_blocks` equals the old file's.
     - On success: the redundant `pre-reclaim` link is removed (it names the same inode as the
       slot, so no bytes go), and the outcome is `rolled_back:<cause>`, `ok: false`.
     - The `rolled_back:sentinel` case (bug-112's class) goes through the same four steps. With
       bug-112's fix, `open_duckdb`'s stale-holder close would also close the new-file
       connection before the next write open; that is an ordering accident the spec does not
       rely on, so step 1 is stated.
   - **A rollback that fails** (any step above raises, or the original's identity check
     fails). The daemon must not keep serving with a closed or unverified writer (I5).
     - It writes `catalog_state.json` `reclaim_disabled: {run_id, cause, at}` (through
       `update_state`).
     - It calls THE writer-lost exit, `Daemon._writer_lost(where, exc)` (R8), with
       `_store_lock` still held: one log line naming the slot, the backup, the failed file and
       each one's inode, then `os._exit(2)` immediately, so no queued op runs on a closed
       writer, and with no repair marker (a swap failure is not an index invalidation, I6).
       launchd respawns the daemon, and by the invariant the boot opens a complete file with
       no foreign WAL.
     - `reclaim_disabled` blocks every later real run until a hand
       `rmx catalog reclaim --clear-disabled <run_id>` after the user has read the log.
7. **R7 The snapshot, the double count, and the band after a reclaim.** {#r7-after}
   - (a) **F5.** The snapshot is refreshed inside the hold (Phase C). After the run,
     `catalog.read.duckdb` has the slot's bytes, and `_store_health` `store_bytes` falls by
     about twice the reclaimable bytes. The old snapshot's inode and the backup's inode have no
     descriptor in the daemon process (bug-112's fix is what makes that hold for in-process
     snapshot readers).
   - (b) **Baseline** (d9bq, as amended by d9bw a). 18.2's `catalog_state.json` gets
     `baseline_file_bytes = rewrite_bytes` (the new file's size, which is the store's live-data
     size), `baseline_at` and `baseline_source: "reclaim:<run_id>"`. 18.2's growth band
     (`file_bytes ≥ 2 ×` baseline AND `file_bytes − baseline ≥ 64 MiB`) then starts at Table
     A's A2 edge; it stays near it only through the A0 re-seed (R2), not "exactly".
   - (c) **Hold bands.** A real run with `hold_s` over `RMX_CATALOG_HOLD_MAX_S` (possible only
     in steps 1-2 or Phases B and C, since Phase A is bounded by the deadline) writes its OWN
     key, `reclaim_hold_over: {since, hold_s, run_id}` (ch-bsd r1 S-4), not
     `reclaim_disabled`. It blocks hub runs only (R3 g); a hand run whose `hold_s ≤ 10` clears
     it, as 18.2 D2 does for `checkpoint_disabled`. A D1 hold (2-10 s) is reported, and its
     `rmxd.log` warning is 23.5's one `lock hold:` line at the 2 s label threshold.
   - (d) **Backups are visible.** `_store_health` `catalog` gains `backup_bytes`, the sum over
     `backups/catalog.*.duckdb`. Those files are outside `store_bytes`'s
     `catalog*.duckdb` glob (`daemon.py:3864`), so the disk they hold must be visible elsewhere.
     `rmx catalog reclaim --list-backups` lists them with sizes. They are removed only by the
     user, as 17.3's backups are.
8. **R8 One helper, not a seventh copy** (the user's rule, 2026-10-15: converge repeated shapes
   into one function; d9bl applies it to edge records). 18.2 builds
   `catalog_maint.CatalogHold` and `Daemon._catalog_hold`
   ([[task-18.2-catalog-maintain-step#r11-hold-helper]]) and ports the snapshot tick,
   `_op_checkpoint` and `catalog_maintain` onto it. 18.3 adds the swap half, and ports the
   remaining hand-spelled sites of I1 onto it. {#r8-one-helper}
   - **Adds to `CatalogHold`:** `interruptible(budget_s)` and the deadline check in `_exec`
     (R4), `rewrite_into(target)`, `gate(alias)`, `close_writer()`, `swap(new, backup)` (with
     the no-`.wal` assertion, R6), `reopen_writer(path)` and `drop_sentinel()` (R3 h).
     `rewrite_into` and `gate` are module functions over an executor (18.2 R11), so the
     rehearsal child (R2) and the hold run the same code.
   - **THE reopen** (ch-bsd r1 S-3; d9bw d). `Daemon._reopen_writer(path: Path, *, where: str)
     -> Store` is the one close-and-reopen sequence after boot's first open, and
     `CatalogHold.reopen_writer` calls it:
     - it asserts `self._store_lock.held_by_current_thread()` (23.1 R1.6), because the opener's
       stale-holder close is safe only under `_store_lock` (I4);
     - `st = Store(root, partition)`, `st.db_path = path`, `self._install_writer_store(st)`
       (23.1 R1.6's ONE installer), `st.init()`, `st._connect()`. The connection is opened by
       `backend.open_duckdb` (bug-112's fix, THE opener), so a registered holder of a replaced
       inode is closed first;
     - it raises on any failure and decides nothing; the caller rolls back (R6 B) or exits.
     - The bug-113 fix's `_reopen_writer_after_merge(d, slot, where)` becomes
       `d._reopen_writer(d._replica_file(slot), where=…)`, then `d._active_slot = slot` and
       `d._refresh_read_only_link()`, and on an exception `d._writer_lost(where, exc)`. Its
       direct `d.store = st` (an assignment 23.1 R1.6's AST rule forbids outside
       `_install_writer_store`) goes. This is raised on `bugs-112-113-118` before it merges.
   - **THE writer-lost exit** (ch-bsd r1 S-3; d9bw d). `Daemon._writer_lost(where: str, exc:
     BaseException) -> NoReturn` keeps the bug-113 fix's name and becomes immediate:
     - one log line `writer-lost: <where>: <exc!r>; exiting 2 for respawn`, a flush of the log
       file, and `os._exit(2)` in the CALLING thread, while that thread still holds
       `_store_lock`. No queued op can then run on a closed writer, and no `_mark_repair_needed`
       is written (I6: this is not an invalidation);
     - its callers write their state BEFORE calling it (R6's `reclaim_disabled`);
     - the bug-113 fix's 2 s delayed thread (`RMX_DEGRADE_EXIT_S`, lock released) goes: the
       op's reply is not delivered, the client sees the socket close, and the record is the log
       line plus the state. `_arm_deferred_exit` (a degraded READ) is a different condition
       and is unchanged.
     - 18.3's failed rollback (R6) and every exit of `_op_replica_merge` that cannot reopen
       call it. `_fast_exit_if_invalidated` stays the exit for a DuckDB invalidation only.
   - **The zombie writer guard** (I12; ch-bsd r1 S-7). `Store.retire()` = `close()` plus a
     terminal flag. After it, `Store._connect()` raises `StoreClosed` instead of reconnecting,
     so a pre-swap reference captured outside `_store_lock` (the flush tick's argument, any
     `st = d._st()` taken before the lock) fails loudly instead of opening the slot a second
     time with stale caches. `close_writer()` calls `retire()`; plain `close()` keeps its
     behaviour for its other callers.
   - **Ports** onto `_catalog_hold` + `checkpoint()` + `close_writer()` + `reopen_writer()`:
     - the init slot rebind (`daemon.py:1755-1791`; 23.1 R1.6 item 4 already moves it under
       `_store_lock`);
     - both `_bootstrap_rotation_if_needed` branches (`:2918-2936`, `:2955-2972`). Their copies
       go through the helper's `copy_out`, and the legacy branch's in-process `shutil.copy2`
       goes with them;
     - the two entities-rebuild holds, `_run_pending_repair` (`:1418`) and
       `_op_repair_entities` (`:5391`), label `repair_entities`, body
       `h.store.rebuild_entities_indexes()` (I1's three more sites);
     - **23.5's compaction hold 2** (d9bw c; [[task-23.5-read-path-and-holder-bounds#cross-plan-18]]
       item 5): append `[L0, EOF)`, the ts-order check, `fsync`, rename, the offset reset, now
       a `_catalog_hold("compact", …)` body instead of a plain `with self._store_lock:` under
       `_inflight("compact")`. Hold 1 is already the snapshot's (`snapshot(pin_to=…)`, 18.2 R8).
       23.5 AC-5 (two holds, nothing lost, the ts-order refusal and its counter) stays green
       after the port.

     Behaviour is unchanged at each site, including the init rebind's legacy fallback and its
     loud log line, and each gets a hold-ring entry and the one alarm.
   - **After 18.3** (checked by AC-14, over `daemon.py`, `catalog_maint.py`, `store.py` and
     `cli.py`):
     - the `"CHECKPOINT"` literal appears only in the `CatalogHold` methods and child entry
       point named in 18.2 R11, plus three named exemptions, each matched by function name:
       `Store.rebuild_entities_indexes` (`store.py`; its hold is the helper's
       `repair_entities`), `merge_verb_aliases` (`cli.py`; offline, daemon down, no
       `_store_lock`), and `_op_replica_merge` with `replica_merge.merge_slots` (fenced,
       d9ae). A CHECKPOINT anywhere else in those four files fails the test;
     - no `_copy_out_of_process(` call outside the helper, except in `_op_replica_merge`;
     - `_install_writer_store` is called only from `Daemon._reopen_writer` and boot's first
       open (`serve_forever`'s two first-open sites); `_op_replica_merge`'s reopens go through
       `_reopen_writer` too (AC-14 no longer contradicts R8);
     - `os._exit(2)` appears only in `_writer_lost` and `_fast_exit_if_invalidated` (the
       `os._exit(0)` clean-shutdown sites, `daemon.py:2086`, `:6489`, `:6521`, are not exits
       for respawn);
     - `rmx compact` has no daemon code of its own (R10).
9. **R9 The tick step: 18.2's growth band is the trigger, 17.2's arming is the gate.** It is
   safe under the conditions below; if any one is dropped, the step is not registered.
   {#r9-tick-step}
   - **Registration.** `MaintenanceStep(name="catalog_reclaim", op="catalog_reclaim",
     args=lambda root, dry_run, today: {"dry_run": dry_run}, requires_arming=True, reason=…,
     after_idle=("vectors_maintain", "memory_compile", "catalog_maintain"))` is registered
     AFTER `catalog_maintain`, so it is last.
   - **The reason** (d9bc). With `invoked_by="hub"` the op first reads `catalog_state.json`.
     Unless tonight's `catalog_maintain` measured band `A2` (`measured_at` ≤ 24 h old), it
     returns `skipped:no_reason` with no child, no hold and no copy. Band `unknown` (no
     baseline yet; 18.2 R5) is a reason for the REHEARSAL only, which seeds the baseline; it
     never leads to a swap on the same night. An A2 night whose rehearsal measures A0 (a store
     that grew legitimately) re-seeds the baseline (R2; d9bw a) and does not swap, so the next
     night is A0 with no rehearsal. The ledger line and one
     `rmxd.log` line carry the reason detail (`band A0: file 412 MiB < 2 × baseline 354 MiB` or
     similar). 18.2's band is computed from a `stat` against the baseline, so the trigger costs
     nothing on a store that does not need it.
   - **Unarmed** (`dry_run=True`, 17.2 R7): the rehearsal only. The hub report then shows the
     numbers a hand confirm would act on.
   - **Armed** (`dry_run=False`): the rehearsal (R2), then R3's preconditions, then R4, all in
     one op. A store is armed only by 17.2's `hub_maintain_arm`, which needs a hand rehearsal
     and a later hand real run (`ok: true`) on that store. The hand rollout (R12) produces
     exactly that pair.
   - **Why `requires_arming=True`, against d9bg's "needs no extra hand arming".** d9bg is about
     `catalog_maintain`'s CHECKPOINT, which the snapshot tick already runs unarmed. This step
     replaces the live writer's FILE, the riskiest operation in the store. Arming costs nothing
     extra: the arming record is the hand run R12 already requires. An A0 store has no real-run
     line and so cannot be armed until a hand run on it. Put to the user as Q-A.
   - **Unattended backups are capped.** A hub run refuses while an earlier
     `pre-reclaim` backup of that store is still on disk (`refused:backup_pending`, not hot;
     health shows `backup_bytes`). Each store then holds at most one unremoved backup, and
     nothing deletes a backup on its own.
   - **Bounded like any hold.** R3 (g) skips a store whose CHECKPOINT ran over 10 s (18.2 D2)
     or whose last reclaim was disabled (`reclaim_disabled`) or ran over 10 s
     (`reclaim_hold_over`). R4's budget interrupts Phase A at 5 s, and R11 retires a store after two such deadlines. 17.2 calls
     the step with `retries=0`, single-flight, under its stuck ceiling.
10. **R10 `rmx compact` is retired onto the verb.** `rmx compact` becomes `rmx catalog reclaim`
    under its old name: with no flag it rehearses and prints the report, and with
    `--confirm <run_id>` it runs for real. {#r10-compact}
    - Deleted: its EXPORT/IMPORT path (`cli.py:7686`, `:7691`), its in-process `duckdb.connect`,
      its daemon stop and its `spawn_daemon` restart, and the `--keep-backup` flag (a backup is
      always kept, R7 d).
    - The CLI tree is regenerated, and the generated-artifact checks run with the family
      (`feedback_family_list_misses_generated_checks`).
11. **R11 No offline route: a store too slow for the daemon stays unreclaimed, and the user
    decides** (d9bp b, as amended by d9bw b). The old offline design is not kept as a fallback;
    nothing in this plan builds it. {#r11-offline-route}
    - A store is `rewrite_too_slow` when any of these holds:
      - its rehearsal's `idle_hold_s` exceeds 5 s (the mark's `run_id` is the rehearsal's);
      - two consecutive real runs end `failed:deadline` (R4's interrupt; the mark's `run_id` is
        the second run's).
    - The mark is written to `catalog_state.json` through `update_state`
      (`rewrite_too_slow: {since, cause, value, run_id}`). Every later real run refuses
      `refused:rewrite_too_slow` (Table C's refusal name,
      [[task-18.1-catalog-measurement#r3]]). Health reports it and the hub row is hot, as
      `catalog_reclaim_due` is.
    - **R14's loaded verdict does not write the live mark.** R14 runs on tmp copies and never
      touches a live store. Its `rewrite_too_slow` verdict for a store is enforced by R12 (the
      hand rollout does not start that store), and on the live store by R4's deadline, which
      is now a real bound, and the two-deadline mark above (ch-bsd r1 S-4).
    - **The honest terminal state** (d9bw b; ch-bsd r1 B-5). The store stays unreclaimed. It
      carries the hot hub row and a bug-registry row naming the number, and the USER decides
      what happens to it. There is no pointer to a helix plan: no helix plan file exists
      (`plan-11-helix-phase2-versioned-graph` is superseded) and none lists this item. When a
      helix plan is drafted it may inherit this state by name. Zero stores are in it on
      2026-10-15 (R14 not yet run; 18.1's slowest idle rewrite is 1.98 s).
    - Only a hand `--clear-disabled <run_id>` naming the mark's `run_id`, after a new R14
      measurement with an `eligible` verdict, lifts the mark.
12. **R12 The hand rollout.** It covers the four stores 18.1 banded A1/A2: refmatrix, global
    (`~/.refmatrix`), cliquedb and viascope. One store at a time, each announced to the user
    first. {#r12-procedure}
    - **This procedure is not a control** (ch-bsd r1 M-8; d8g: "the gate is the record, not the
      surface"). Nothing enforces the announcement, and an MCP agent can rehearse, confirm and
      arm. The controls are the code's: R3's preconditions, R4's deadline and ceiling, R5's
      gate, R6's rollback, and 17.2's arming record.
    - R14's loaded measurement has been run for the store, and its verdict is `eligible`
      (loaded max raw `phase_a_s` ≤ 5 s and loaded max `hold_s` ≤ 10 s).
    - `rmx catalog reclaim`, then read the report and check its `idle_hold_s` against 18.1's
      max for that store (1.98, 0.47, 1.06 and 1.76 s): a value over 2× 18.1's max + 1 s is
      investigated before any confirm.
    - `--confirm <run_id>`, then read `hold_s`, the D band, `hold_vs_idle` and the RSS fields,
      and compare `hold_s` with R14's loaded max for the store.
    - A D1 hold on a live store, or a `phase_a_s` over 5 s (`deadline_hit`), gets a
      bug-registry row before the next store.
    - Record the before/after table (file, snapshot, `store_bytes`, `hold_s`) in the
      implementation summary.
    - Arm the step: `rmx hub maintain arm --root <root> --step catalog_reclaim --run-id <id>`.
    - The store's next 18.2 night must show `baseline_source: reclaim:<run_id>` and band A0.
13. **R13 What it never touches** (d9ao; `feedback_decay_never_loses_knowledge`). The only
    name the reclaim changes is the writer slot's, and only through R4's link + replace. The
    swap target is resolved from the bound writer (R3 f), never from the marker's complement.
    {#r13-untouched}
    - Never written, moved or opened: the frozen inactive slot (18.1 F6: viascope's B slot
      holds 113,985 ids found nowhere else), the legacy `catalog.duckdb`, `facts.log`, both
      `catalog.<S>.offset` files (I8), `vectors/`, and the `active` marker (same slot letter).
    - The pre-reclaim backup is kept whole (R7 d). This is not knowledge removal under
      ADR-0004 `#rule-no-delete`: every row is carried and verified (R5), and the old file
      survives under `backups/`.

14. **R14 The loaded feasibility measurement** (d9bp c), run before the rollout and re-run on
    request. `eval/catalog_maint/measure_reclaim_hold.py` is evaluation code, but it measures
    the PRODUCTION op in a real daemon (`feedback_measure_the_path_users_run`). {#r14-loaded}
    - **Per registered store:** copy its snapshot (a child `/bin/cp -p`, as 18.1 does) into a
      23.0-style short tmp root as BOTH writer slots (`catalog.A.duckdb`, `catalog.B.duckdb`)
      plus an `active` marker naming A, so the tmp daemon boots bound to A without the
      asymmetric rotation bootstrap copying A to B under measurement (ch-bsd r1 S-8). Nothing
      touches the live root's files except that copy's read, and no live socket is used.
    - **The load** (S-8). 6 concurrent reader loops through the tmp daemon's socket, mixing
      `stats`, `query` and one model-free read named in the script (or `context` with its dense
      leg disabled, stated in the report). `context` with dense on is excluded: the tmp daemon
      may not reach the hub's `models.sock`, and private model workers would change the CPU load
      the measurement is meant to reproduce. Plus one writer loop (`upsert_entity`) at about
      2 Hz.
    - **The load is measured, not configured.** Each loop counts the calls it COMPLETED, from
      the client side, with a timestamp per completion. A row records, per loop, the completions
      inside the run's `[acquire, release]` window (from the ledger's timestamps), and the
      script REFUSES a row in which any loop completed zero calls in that window (the row is an
      error row, not a verdict).
    - **The runs:** 3 production real runs (`rehearse`, then `confirm`), each on a fresh copy,
      with `RMX_CATALOG_RECLAIM_BUDGET_S` raised to 60 so the production deadline does not
      truncate the number being measured (S-8). Per run it records `hold_s`, the per-phase
      seconds, `phase_a_s` RAW, and the daemon's peak RSS (sampled every 50 ms from
      `ps -o rss`, and `ru_maxrss` from the ledger).
    - **Output:** `workflow/review-output/plan18-reclaim-hold-<YYYYMMDD>.{jsonl,md}`, with one
      row per store: loaded max `hold_s`, max raw `phase_a_s`, peak RSS, the per-loop completion
      counts, the duckdb version, and a verdict. The verdict compares the raw numbers with the
      production edges: `eligible` (loaded max `phase_a_s` ≤ 5 s AND loaded max `hold_s` ≤
      10 s) or `rewrite_too_slow` (R11). The plan records the per-store verdicts before R12
      starts.
    - **Pre-registered edges** (written 2026-10-15, before any run): 5 s on the loaded max
      `phase_a_s` (the deadline's budget, d9bp, Q-D) and 10 s on the loaded max whole hold
      (Table D). A peak RSS over 2 GiB on any store is a user decision before its rollout; it
      is not an automatic refusal.

## Acceptance criteria {#acceptance}

Tests run in the 23.0 sandbox on real tmp daemons with short roots, with 23.2's
`recorded_daemon` installed as `_store_lock` before any op. All DuckDB files are real; there are
no DuckDB mocks. The routines take keyword seams (the 17.1 AC-2 / 18.2 AC-5 pattern), not op
arguments: `gate_seam`, `phase_a_seam`, `reopen_seam`, `rollback_seam`, `free_bytes`, `now`. The
fixture is 18.1's AC-1 shape: 200,000 entities and their links, 90 % purged, WAL checkpointed.

1. **AC-1 (round trip, in the daemon).** Rehearse, then confirm. {#ac-1}
   - the slot is ≥ 50 % smaller, and the R5 gate is equal before and after;
   - the daemon's pid is UNCHANGED, and health has `slot_bound: true`;
   - exactly ONE recorded hold for the real run, within 50 ms of the reported `hold_s`;
   - after the run, a new entity's id is greater than the old max id (the sequence carried
     over);
   - **writes land in the new file:** an entity is written after the run, then a `snapshot` op
     is forced (so the write is CHECKPOINTed out of the WAL; ch-bsd r1 M-5), and a fresh child
     opening a copy of the slot sees it; it is NOT in the backup;
   - the backup's sha256 equals the pre-run slot's;
   - unchanged bytes and mtime_ns: the `active` marker, the frozen inactive slot, the legacy
     `catalog.duckdb`, `facts.log`, both `catalog.<S>.offset` files, and every file under
     `vectors/`.
2. **AC-2 (gate failure, one variant per leg; d9br).** `gate_seam` changes the attached new
   file before the compare, once per variant: {#ac-2}
   - deletes one row;
   - changes one value in a non-key column (counts unchanged);
   - alters one column's DEFAULT;
   - drops one index, and separately re-creates one index with a different column list under
     the same name;
   - drops one constraint's table and re-creates it with different CHECK text;
   - drops one sequence;
   - adds one view, one macro and one user type (three runs).

   Each outcome is `failed:gate` naming the object. The slot's inode is unchanged, the daemon
   pid is the same and serves the pre-run counts, and the failed file is in `backups/`.
   Mutations: the gate removed FAILS (the slot loses the row); each leg removed in turn FAILS
   its own variant.
3. **AC-3 (deadline).** `RMX_CATALOG_RECLAIM_BUDGET_S=0.5`. `phase_a_seam` runs a finite slow
   statement on the writer connection (about 20 s of `range()` work). The outcome is
   `failed:deadline`, with `hold_s < 1.5`. The slot is untouched, the partial file is gone and
   reported in `partial_removed`, and the daemon then serves a write. A second consecutive
   `failed:deadline` writes `rewrite_too_slow`, and a third call refuses
   `refused:rewrite_too_slow` with no hold. Mutations: no interrupt timer FAILS (`hold_s ≈ 20`);
   the consecutive count not persisted FAILS (the third call holds). {#ac-3}
   - **AC-3b (the deadline lands in a gap between statements; ch-bsd r1 B-2).**
     `RMX_CATALOG_RECLAIM_BUDGET_S=0.5`. `phase_a_seam` runs a short statement, sleeps 1 s in
     Python, then runs a second short statement and a third that would take about 20 s. The
     outcome is `failed:deadline` with `deadline_hit: true` and `hold_s < 1.5`, and the second
     statement never runs (a seam counter). Mutations: a single-shot `interrupt()` timer FAILS
     (the interrupt is dropped in the gap, the second and third statements run, `hold_s ≥ 1`);
     `_exec` without `check_deadline()` FAILS (the second statement runs); the deadline armed
     at the acquire instead of after step 2 FAILS AC-3c.
   - **AC-3c (steps 1-2 are outside the budget; M-4).** A seam makes step 2's CHECKPOINT take
     0.8 s with the budget at 0.5 s: the run does not end `failed:deadline` on step 2, and
     `phase_a_s` excludes the 0.8 s.
4. **AC-4 (rollback, including bug-112's class).** {#ac-4}
   - (a) `reopen_seam` raises once after the replace → `rolled_back:reopen`. The slot's inode
     equals the ORIGINAL inode, the counts equal the pre counts, the pid is the same and a write
     succeeds, and the new file is kept as `reclaim-failed`.
   - (b) The test holds a second in-process connection to the slot opened by a RAW
     `duckdb.connect(slot)` in the daemon process (a seam run before the op). It is not
     registered with `backend.open_duckdb`, so the fix's stale-holder close cannot see it and
     the reopen gets the cached old database (I4). The test proves the guard, not the fix: the
     sentinel read-back finds no table → `rolled_back:sentinel`, with the same assertions as
     (a), and the slot has no `.wal` after the run (R6 B steps 1-2).
   - Mutations: the sentinel read-back removed FAILS (b) together with the `total_blocks` and
     inode checks removed (the run reports `ok`, and AC-1's fresh-child read does not see the
     post-run write); the sentinel left in the slot FAILS AC-1 (the R5 gate of the slot
     against the backup then differs by one table).
5. **AC-5 (a rollback that fails).** The daemon runs as a subprocess. `reopen_seam` fails the
   reopen and `rollback_seam` fails the restore link. {#ac-5}
   - The process exits with code 2, after one log line naming the slot, backup and failed file
     with their inodes. `reclaim_disabled` is written.
   - A fresh daemon booted on the root answers, with counts equal to the pre counts.
   - A real run then refuses `refused:reclaim_disabled` until `--clear-disabled`.
   - Mutation: returning `ok: false` and staying up with the writer closed FAILS (the process
     does not exit, and a write op fails on the closed connection).
6. **AC-6 (crash consistency, the R6 invariant, forward AND back).** The daemon runs as a
   subprocess. At each point the seam blocks on an event, the test sends SIGKILL, then boots a
   fresh daemon on the root. {#ac-6}
   - **Forward points** (Phase B): after the close, after the link, after the replace, after
     the reopen.
   - **Rollback points** (ch-bsd r1 B-1; the identity check forced to fail after the reopen):
     after the reopened writer writes (the seam deletes one row and re-inserts it with the
     same values: logically neutral, but the WAL logs the delete by row id, and the fixture's
     90 % purge makes the new file's row ids differ from the old file's), after R6 B step 1's
     close, and after R6 B step 3's restoring replace.
   - **The judgment** is the full R5 gate (row content hash, not per-table counts, which the
     foreign-WAL corruption can leave plausible), run by a child against the backup's content,
     AFTER the boot and after one rehearsal call (`rmx catalog reclaim` with no flag), whose
     residue sweep (R3 h) runs first. The gate must be equal at every point. Then a second real
     reclaim on the same root succeeds (S-6: no permanent sentinel failure).

   Mutations: `rename(slot → backup)` + `rename(new → slot)` in place of link + replace FAILS (a
   kill between the renames leaves no slot, and the boot opens an empty catalog); a rollback
   without R6 B step 1 or step 2 FAILS (at the restoring-replace point the boot replays the new
   file's WAL into the old file and the gate differs); `swap`'s no-`.wal` assertion removed
   together with step 2 FAILS the same point; the residue sweep removed FAILS (the second
   reclaim fails on the sentinel, and the gate differs by one table).
7. **AC-7 (production path = 18.1's path; 18.1 R4).** On 18.1's AC-2 fixture (200/80 MiB,
   d9bh): {#ac-7}
   - (a) the production rehearsal against 18.1's `measure_root` (script `8a93ab1`, or its
     `master` merge, which imports the shared `rewrite_into` / `gate`): median
     `rewrite_bytes` within `max(2 %, 512 KiB)` (d9br as amended by d9bv: the r2 fleet re-run
     measured up to 2.17 % in whole 256 KiB block steps), median `rewrite_s` within ±25 %;
   - (b) a real run on a tmp daemon whose slot is that fixture: its `rewrite_bytes` (the new
     file before the swap) within `max(2 %, 512 KiB)` of the rehearsal's, and its `rewrite_s`
     (the COPY phase only) within ±25 % of the rehearsal median.

   If (a) fails, 18.1's verdict is re-taken through the production routine before any live
   reclaim (18.1 R4).
8. **AC-8 (preconditions refuse before any hold).** Each case refuses with its reason, with no
   recorded hold, no file changed and the daemon pid unchanged: {#ac-8}
   - no rehearsal line;
   - a rehearsal over 24 h old (`now` seam);
   - band A0;
   - a rehearsal whose gate failed;
   - `idle_hold_s` over the budget (`RMX_CATALOG_RECLAIM_BUDGET_S=0.001`), which also writes
     `rewrite_too_slow`;
   - `rewrite_too_slow` already set;
   - 15 % drift;
   - not enough disk (`free_bytes` seam);
   - a WAL over 64 MiB (`RMX_CATALOG_WAL_MAX_BYTES=1`);
   - a daemon bound to the legacy file;
   - `reclaim_disabled` set (every caller: `refused:reclaim_disabled`);
   - `reclaim_hold_over` set, `hub` caller (`refused:reclaim_hold_over`); the same state with a
     `cli` caller is NOT refused for it.

   Mutation: the budget check removed FAILS (the run proceeds).
9. **AC-9 (hold over the ceiling; ch-bsd r1 S-4).** `RMX_CATALOG_HOLD_MAX_S=0.2`, with a Phase
   C seam that sleeps 0.3 s: `hold_over`, and `reclaim_hold_over` written (NOT
   `reclaim_disabled`). A hub run is then refused `refused:reclaim_hold_over`. A hand run with
   no seam runs (R3 g does not refuse it for this key) and, with `hold_s ≤ 0.2`, clears it.
   Separately, with `reclaim_disabled` set, a hand run is refused and only
   `--clear-disabled <run_id>` clears it. Mutations: the flag not persisted FAILS; one shared
   key for both FAILS (either the hand run is refused or a hand run clears
   `reclaim_disabled`). {#ac-9}
10. **AC-10 (the snapshot and F5).** After AC-1's run: {#ac-10}
    - `catalog.read.duckdb` has the slot's size, and its mtime_ns is no later than the
      recorder's release time for the hold;
    - `store_bytes` fell by ≥ 1.8 × (pre-run slot bytes − post-run slot bytes);
    - health `catalog.backup_bytes` equals the backup's size;
    - after the daemon reports `_read_inflight == 0` (a private read-only ATTACH legitimately
      keeps its old snapshot until it closes; ch-bsd r1 M-6), `lsof -p <daemon pid>` lists no
      descriptor on the backup's inode or on the replaced snapshot's inode.

    Mutation: no Phase C snapshot (left to the next write tick) FAILS.
11. **AC-11 (the tick step).** This runs in 17.2's harness (injected `roots` and `now`, two tmp
    stores), with `catalog_state.json` set by real `catalog_maintain` runs. {#ac-11}
    - (a) band A0: `skipped:no_reason`, no child process spawned (a spy on `subprocess.run`),
      no hold, and the reason detail in the ledger;
    - (b) band A2, unarmed: `dry_run:unarmed`, a rehearsal line, and the slot inode unchanged;
    - (c) band A2, armed through a hand rehearsal + hand confirm + `hub_maintain_arm`: a real
      run, `ok`, and the baseline reset; the next night is band A0 and `skipped:no_reason`;
    - (d) armed with an earlier `pre-reclaim` backup present: `refused:backup_pending`;
    - (e) `catalog_maintain` blocked (17.2 AC-10's shape): `deferred`;
    - (f) **the re-seed** (d9bw a; ch-bsd r1 B-3): a store at 2.1× its baseline (band A2) whose
      live data really grew (its rehearsal measures Table A A0): the night's run rehearses,
      writes `baseline_source: "rehearsal:<run_id>"` with the rehearsal's median
      `rewrite_bytes`, and does not swap; the next night is band A0 and `skipped:no_reason`
      with no child spawned.

    Mutations: the reason gate removed FAILS (a spawns the rehearsal); `requires_arming=False`
    FAILS (b swaps); the backup cap removed FAILS (d); the A0 re-seed removed FAILS (f: the next
    night rehearses again).
12. **AC-12 (`invoked_by`, surfaces, no fallback).** {#ac-12}
    - A CLI and an MCP rehearsal append `cli` / `mcp` lines with `dry_run: true`.
    - A hand confirm appends `dry_run: false` with the R4 fields.
    - `invoked_by="hub"` with `confirm` raises `ValueError`, and so does `invoked_by="hand"`.
    - A `cli` real call with no confirm → `refused:no_rehearsal`.
    - The CLI with the daemon stopped exits non-zero with the R1 message: a spy on
      `duckdb.connect` in the CLI process counts zero, and every file under the root keeps its
      mtime_ns.
13. **AC-13 (`rmx compact` retired).** `rmx compact` rehearses and changes no slot.
    `rmx compact --confirm <id>` runs the real path (one recorded hold). `cli.py` has no
    `EXPORT DATABASE`, `IMPORT DATABASE` or `spawn_daemon` in `compact`, and no
    `--keep-backup`. The regenerated CLI tree check passes. {#ac-13}
14. **AC-14 (one helper, one reopen, one exit; AST).** Over `daemon.py`, `catalog_maint.py`,
    `store.py` and `cli.py` (ch-bsd r1 S-1, S-3): {#ac-14}
    - 18.2 AC-17's walk, with 18.3's functions on the catalog list (`_op_catalog_reclaim`, the
      init rebind's function, `_bootstrap_rotation_if_needed`, `_run_pending_repair`,
      `_op_repair_entities`, the compaction's hold-2 function): no `_store_lock` /
      `_snapshot_lock` reference in any of them, and exactly one `_catalog_hold` call
      reachable from each op;
    - the `"CHECKPOINT"` literal only at R8's named sites and three named exemptions;
    - no `_copy_out_of_process(` call outside the helper and `_op_replica_merge`;
    - `_install_writer_store` called only from `Daemon._reopen_writer` and boot's two first-open
      sites; `_reopen_writer_after_merge` calls `_reopen_writer` (no `d.store =` assignment);
    - `os._exit(2)` only in `_writer_lost` and `_fast_exit_if_invalidated`.

    Mutations: an inline swap in `_op_catalog_reclaim` FAILS; the init rebind left hand-spelled
    FAILS; a `with d._store_lock:` in `catalog_maint.py` FAILS; a new `con.execute("CHECKPOINT")`
    in a `Store` method other than `rebuild_entities_indexes` FAILS; a second writer reopen
    (`Store(…)` + `_install_writer_store` in a new function) FAILS; `_reopen_writer_after_merge`
    keeping its own `os._exit` thread FAILS.
15. **AC-15 (lock order; ch-bsd r1 B-4).** The inversion is caught by an observable that can
    fail, not by a deadlock that a consistent inversion never produces: {#ac-15}
    - 18.2 AC-17's lock-order case, run with label `reclaim`: a competitor holds ONLY
      `_snapshot_lock`; `rmx catalog reclaim --confirm` with `RMX_CATALOG_LOCK_WAIT_S=1` returns
      `skipped:lock_busy`; meanwhile a write op completes in under 0.5 s and 23.2's recorder
      shows no `_store_lock` acquisition by the reclaim's thread;
    - a write burst during a reclaim's Phase A (the seam blocks on an event) completes within
      5 s of the release, and the snapshot tick's next hold follows the reclaim's.

    Mutation: the helper taking `_store_lock` before `_snapshot_lock` FAILS the first case (the
    write op blocks for the full second; the recorder shows the reclaim's thread holding
    `_store_lock`).
16. **AC-16 (pre-registered constants).** `RMX_CATALOG_RECLAIM_BUDGET_S` = 5 (18.1 R3's
    in-daemon edge, applied to the loaded number by d9bp), two consecutive deadlines for
    `rewrite_too_slow`, the bytes tolerance `max(2 %, 512 KiB)` (d9bv), `RMX_CATALOG_RECLAIM_MAX_AGE_S` = 86,400, drift 0.10, a disk margin
    of 256 MiB, and `RMX_CATALOG_INTERRUPT_REPEAT_S` = 0.05 (B-2). The reused 18.2 constants
    (`RMX_CATALOG_HOLD_MAX_S` 10, `RMX_CATALOG_LOCK_WAIT_S` 30, `RMX_CATALOG_WAL_MAX_BYTES`
    64 MiB, `RMX_CATALOG_RECLAIM_FLOOR_BYTES` 64 MiB) are imported, not redefined. Changing a value, or
    redefining a reused one, FAILS this test. {#ac-16}
17. **AC-17 (pre-registered mutations; each must FAIL a named AC).** Each is restored in its own
    command (`feedback_mutation_must_fail_not_hang`). {#ac-17}
    - the gate removed, or any one gate leg removed → AC-2;
    - the consecutive-deadline count not persisted → AC-3;
    - the sentinel read-back removed, or the sentinel left in the slot → AC-4 / AC-1;
    - the post-release write-through check removed → AC-18;
    - no deadline interrupt → AC-3; a single-shot interrupt, or `_exec` without the deadline
      check → AC-3b; the deadline armed at the acquire → AC-3c;
    - the identity check removed → AC-4;
    - staying up after a failed rollback, or the delayed-exit thread kept → AC-5 / AC-21;
    - rename in place of link + replace; a rollback without closing the reopened writer or
      without moving its `.wal`; the residue sweep removed → AC-6;
    - the budget check removed → AC-8;
    - `reclaim_disabled` not persisted, or one key shared with `reclaim_hold_over` → AC-9;
    - no Phase C snapshot → AC-10;
    - the reason gate removed, `requires_arming=False`, no backup cap, or no A0 re-seed → AC-11;
    - `hub` accepted with `confirm` → AC-12;
    - an inline swap, a hand-spelled init rebind, a lock in `catalog_maint.py`, a CHECKPOINT in
      a new `Store` method, a second writer reopen → AC-14;
    - inverted lock order → AC-15;
    - a constant changed → AC-16;
    - `duckdb.connect` substituted for `open_duckdb` → AC-18 (a);
    - the script's readers not measured, or the production budget kept → AC-19;
    - `_connect` reconnecting a retired Store → AC-20;
    - residue files left in the root, or deleted instead of moved → AC-22;
    - the `active` marker flipped, the inactive slot used as the target, or the backup deleted
      after a success → AC-1.

18. **AC-18 (bug-112's swap write-loss, against the merged fix; d9bp a).** {#ac-18}
    - (a) **The reproduction through THE opener** (ch-bsd r1 M-3): in one process, open two
      connections to a file BOTH through `backend.open_duckdb`, close one, `os.replace` a new
      file over the path, open again through `open_duckdb`, write a row, CHECKPOINT, close
      everything; a child then reads the path and finds the row. The same test with plain
      `duckdb.connect` substituted for `open_duckdb` (at all three opens) FAILS: on duckdb
      1.5.3 the row is lost (ch-bsd 18.1 r1's evidence). This is the fix's regression guard.
      `open_duckdb` closes only REGISTERED holders; the unregistered case is AC-4 (b)'s.
    - (b) **Through the product:** AC-1's run with the after-release write-through check:
      the child sees no sentinel table, and sees the entity written after the run. Mutation:
      the post-release check removed FAILS a variant whose `reopen_seam` returns the old
      connection AND whose read-back seam is forced to pass (the loss goes unreported).
19. **AC-19 (the loaded measurement is the product path, under measured load; ch-bsd r1
    S-8).** R14's script on 18.1's AC-2 fixture, in the sandbox, with both slots and `active`
    in the tmp root: {#ac-19}
    - each row records `hold_s` and raw `phase_a_s` from the production op's ledger line (not a
      timer of the script's own), a peak RSS above the idle daemon's, the per-loop completion
      counts inside `[acquire, release]` (each ≥ 1), and a verdict;
    - with the script's Phase A edge set to 0.001 s, the verdict is `rewrite_too_slow` while the
      run itself completes `ok` (the production deadline is raised to 60 s, so the number is
      not truncated);
    - the tmp daemon makes no connection to a `models.sock` (its model-client counter is 0);
    - the boot log of the tmp daemon has no rotation-bootstrap copy.

    Mutations: the script timing its own COPY instead of calling the op FAILS (no ledger
    `run_id` in the row); the reader loops not started, or started but blocked so that none
    completes in the window, FAILS (the script refuses the row: a loop with zero completions);
    the production budget not raised FAILS a variant whose Phase A seam sleeps 1 s with the
    budget at 0.5 s (the row reports `failed:deadline` and a truncated `phase_a_s` instead of a
    raw number).
20. **AC-20 (no zombie writer; ch-bsd r1 S-7).** The test captures `pre = d.store` before a
    reclaim. After a successful run, `pre.stats()` (any method that connects) raises
    `StoreClosed`, the slot gains no second registered holder in `backend`'s registry, and a
    flush tick whose `_periodic_flush` was handed `pre` before the swap logs one failure line
    and writes nothing to the slot. Mutation: `close_writer()` calling plain `close()` FAILS
    (`pre.stats()` reconnects and returns). {#ac-20}
21. **AC-21 (one writer-lost exit, shared with the merge; ch-bsd r1 S-3, d9bw d).** The daemon
    runs as a subprocess. {#ac-21}
    - (a) AC-5's failed rollback: the exit code is 2 within 0.5 s of the log line, and a write
      op queued on `_store_lock` before the failure never runs (its client sees the socket
      close, and the fresh daemon's catalog does not contain its row).
    - (b) The merge path, on the bug-113 branch once converged: a `_reopen_writer` failure seam
      inside `_reopen_writer_after_merge` gives the same exit through `_writer_lost`, with no
      `repair.needed` marker written.

    Mutations: `_writer_lost` keeping the 2 s delayed thread with the lock released FAILS (a)
    (the queued write runs on the retired writer first and fails, or the exit comes after
    2 s); `_fast_exit_if_invalidated` named as the exit FAILS (a) (the process does not exit:
    the error is not an invalidation).
22. **AC-22 (crash residue is swept; ch-bsd r1 S-6).** On a tmp root with planted residue
    (`catalog.A.reclaim-x.duckdb` and its `.wal`, `catalog.A.duckdb.rollback`, a
    `maintain/reclaim-scratch-x/` dir, and `reclaim_inflight` set with
    `_rmx_reclaim_sentinel` present in the slot), one rehearsal call: {#ac-22}
    - every planted catalog file is in `backups/` with a `.residue-` name and its bytes
      unchanged, none remains in the root, and `store_bytes` falls by their size;
    - the scratch dir is gone and its bytes are reported;
    - the sentinel table is gone from the slot (`sentinel_dropped: true`), `reclaim_inflight`
      is cleared, and a following real reclaim succeeds;
    - the report and the ledger line carry `residue_moved`, `residue_bytes` and
      `sentinel_dropped`.

    Mutations: the sweep removed FAILS (the real reclaim fails `CREATE TABLE … already exists`);
    a delete in place of the move FAILS (no file in `backups/`).

## Test strategy {#test-strategy}

- Tier 1 (in-process, 23.0) covers AC-1..AC-22. Every daemon is a real tmp daemon; AC-5,
  AC-6 and AC-21 run the daemon as a subprocess so the exit code and the SIGKILL are real. No launchd
  path is under test: the design never stops or starts a daemon. AC-5's respawn is a fresh boot
  by the test; launchd's respawn rule is fact I6, not a property of this task.
- Locks are checked with 23.2's recorder on a real `_FairLock`. The bound is one hold per real
  run; seconds are compared, not used as the bound, except AC-3's deadline (23.2 R5).
- The AC-17 mutations (and AC-18 and AC-19's own) run before GREEN is declared.
- No test touches a live root or a live socket.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/catalog_maint.py` | (created by 18.2) adds `CatalogHold.interruptible` and the deadline check in `_exec`, `rewrite_into`, `gate`, `CatalogHold.close_writer` / `swap` (no-`.wal` assertion) / `reopen_writer` / `drop_sentinel`, `sweep_residue`, the `rewrite` / `gate` child entry points, the rehearsal and real-run routines with their seams |
| `src/refmatrix/daemon.py` | `_op_catalog_reclaim` (status, list-backups, clear-disabled); `Daemon._reopen_writer` (THE reopen) and `Daemon._writer_lost` (THE immediate exit), converged with the bug-113 fix; the init rebind, both `_bootstrap_rotation_if_needed` branches, `_run_pending_repair`, `_op_repair_entities` and 23.5's compaction hold 2 ported onto the helper (R8); `_store_health` `catalog.backup_bytes` |
| `src/refmatrix/store.py` | `Store.retire()` and `StoreClosed` from `_connect` on a retired Store (R8, I12) |
| `src/refmatrix/verbs.py`, `cli.py`, `mcp.py` | `rmx_catalog_reclaim`; `rmx catalog reclaim`; `rmx compact` retired onto it (R10) |
| `src/refmatrix/hub.py` | the `catalog_reclaim` registration (R9) |
| `eval/catalog_maint/measure_catalogs.py` | when merged from the 18.1 clone, imports `catalog_maint.rewrite_into` / `gate`, so a re-taken 18.1 measures the product |
| `eval/catalog_maint/measure_reclaim_hold.py` | new: R14's loaded measurement over the production op |
| `tests/test_catalog_reclaim.py`, `tests/test_hub_catalog_reclaim_step.py`, `tests/test_catalog_reclaim_load.py` | new: AC-1..AC-22 (AC-18 a may live with bug-112's own test file if the fix already ships it; it must exist and FAIL with `duckdb.connect` substituted) |
| CLI tree | regenerated |

## Open questions (with recommended answers) {#open-questions}

- **Q-A, `requires_arming` for the reclaim step.** Recommended: `True` (R9). It reads against
  d9bg's last sentence; the reason is in R9. If the user prefers `False`, R3 (g)'s backup cap and
  the fresh in-op rehearsal remain the only guards, and AC-11 (b) changes to expect a swap.
- **Q-C, `facts.log` compaction on the helper.** CLOSED (d9bw c; 23.5
  [[task-23.5-read-path-and-holder-bounds#cross-plan-18]] item 5): 18.3 owns the port of 23.5's
  compaction hold 2 onto `_catalog_hold` (R8 "Ports"). Its hold then gets the ring and the one
  alarm, which is what the 00:11-00:13 restart (18.2 `#why`) lacked.
- **Q-D, where the deadline falls.** Stands (d9bw), now that the interrupt is a real bound
  (R4: flag + 50 ms re-interrupt + per-statement check). The 5 s budget covers Phase A
  (rewrite + gate + sentinel), armed after the uninterruptible flush and CHECKPOINT (steps
  1-2, M-4), and the whole hold is measured against Table D's 10 s. Phases B and C were about
  0.3 s on refmatrix's copy (I9) and cannot be interrupted safely mid-swap. If the user wants a
  hard 5 s on the whole hold, the Phase A budget becomes `5 s − R14's max (steps 1-2 + B + C)`
  per store.
- **Q-E, the memory cost.** Recommended: accept it, with R14's per-store peak stated before
  each store's rollout and the 2 GiB edge as a user decision. The alternative, running the COPY
  in a child, needs the child to read the live slot, which bug-110 forbids while the daemon
  holds it.

## Revision 2026-10-15 (18.1 verdict) {#rev-18-1-verdict}

| source | change |
|---|---|
| d9be (C12 lifted, Q3 moot) | the CONDITIONAL status is gone; [[#why]] cites the 18.1 table; Table C's 30/120 s edges no longer gate anything here |
| d9bf (in-daemon rewrite-and-swap) | the whole design: [[#design]], R2-R7. Dropped: the watchdog pause, the daemon stop, `daemon.lock`, the launchd kickstart, the restart wait, and the 23.0 tier-2/3 dependency. Added: dependencies on bug-112 and 23.1 R1.6; the identity check (AC-4); the crash-consistency invariant (AC-6); the deadline interrupt (AC-3); lock order (AC-15) |
| d9bf (offline route for > 5 s) | first written as "specified, not built"; replaced by d9bp b below |
| d9bp a (bug-112 FIX + sentinel; PROVISIONAL) | header dependency on branch `bugs-112-113-118`; [[#facts]] I4 (the reproduction); R4 step 5 and step 11 (sentinel written after the gate, read back after the reopen, refuse and roll back if absent); the after-release write-through check; [[#ac-4]], [[#ac-18]] |
| d9bp b (no offline route; PROVISIONAL) | [[#r11-offline-route]] rewritten: `refused:rewrite_too_slow` → helix plan; Q-B withdrawn. The helix pointer is superseded by d9bw b ([[#rev-round-2]]) |
| d9bp c (loaded feasibility; PROVISIONAL) | [[#facts]] I9; [[#r14-loaded]] (full hold, tmp daemon, 6 readers + a writer, peak RSS); R4's 5 s Phase A budget with `con.interrupt()`; the rehearsal demoted to an idle prefilter; [[#ac-3]], [[#ac-19]]; Q-D, Q-E |
| d9bq (baseline = 18.1 `rewrite_bytes`; PROVISIONAL) | [[#r7-after]] (b) resets to the new `rewrite_bytes`; R2 seeds a missing baseline from a rehearsal |
| d9br (one gate; median bytes; 2 % tolerance; PROVISIONAL) | [[#r5-gate]] (six legs, shared with 18.1); [[#ac-2]] (one variant per leg); [[#ac-7]] (2 %, medians) |
| d9bf (`rmx compact` retired) | [[#r10-compact]] onto the in-daemon verb |
| d9bc + d9bg (reason-gated; growth band) | [[#r9-tick-step]] replaces `#r9-not-nightly`: an armed tick step whose reason is 18.2's A2 growth band; [[#r7-after]] (b) resets the baseline |
| 18.1 R4 (production path) | [[#ac-7]] compares against 18.1's script and the real run; `rewrite_into` / `gate` are shared with the rehearsal child |
| 18.1 F5 (double count) | [[#r7-after]] (a), [[#ac-10]] |
| the user's convergence rule | [[#r8-one-helper]], [[#ac-14]]: one catalog-hold helper (built by 18.2) instead of a seventh hand-spelled hold |
| bug-113's lessons | [[#facts]] I5; R6's "never serve with the writer closed" and the `finally` DETACH |
| frozen slots (d9ao) | [[#r13-untouched]] (was R6) and [[#ac-1]]'s unchanged-bytes list |
| anchors | kept: [[#acceptance]], [[#ac-7]] (18.1 R4 links them). Renumbered: `#r5-rollback` → [[#r6-rollback]] (nothing linked it). Retired: `#r6-untouched` → [[#r13-untouched]] and `#r9-not-nightly` → [[#r9-tick-step]]; the plan's two links move with them |

## Revision round 2 {#rev-round-2}

From ch-bsd plan-18 r1 ([[bsd-plan18-r1-spec-review-b84fd8d]]) and the rulings d9bw (with
d9bp-d9bv) in [[plan-review-2026-10-14]]; 23.5's hand-off list
([[task-23.5-read-path-and-holder-bounds#cross-plan-18]]) and the bug-112/113 fix (branch
`bugs-112-113-118`, read-only) carried in.

| finding | change |
|---|---|
| B-1 (rollback restores the old inode beside the new file's WAL; foreign WAL replayed silently) | [[#facts]] I10; [[#r6-rollback]] invariant restated (name + a `.wal` that belongs to it), R6 B in order: close the reopened writer, move a non-empty `<slot>.wal` to `backups/` BEFORE the restore, restore, reopen; `CatalogHold.swap` asserts no `<slot>.wal` at every replace (R4 Phase B); [[#ac-6]] gains three rollback crash points judged by the full R5 gate, and the two mutations |
| B-2 (single-shot interrupt dropped between statements) | [[#facts]] I11; [[#r4-hold]] `interruptible`: flag + re-interrupt every 50 ms + `check_deadline()` before every statement in the one `_exec`, the timer joined on exit; [[#ac-3]] gains AC-3b (a 1 s Python gap, budget 0.5 s) and AC-3c; [[#ac-16]] pins 50 ms |
| B-3 (growth band vs Table A) / d9bw a | R2: an A0 rehearsal re-seeds the baseline; R7 (b) "exactly" corrected; R9 re-seed note; [[#ac-11]] (f) |
| B-4 (lock-order mutation cannot fail) | [[#ac-15]]: a competitor holding only `_snapshot_lock`, `skipped:lock_busy`, a write completes, the recorder shows no `_store_lock` by the reclaim |
| B-5 (unanchored "goes to the helix plan") / d9bw b | [[#r11-offline-route]]: the honest terminal state (unreclaimed, hot row, bug-registry row, the user decides); no helix pointer |
| S-1 (AST bypass; three missed CHECKPOINTs) | [[#facts]] I1 lists `store.py:3899`, `replica_merge.py:391`, `cli.py:3785` (re-read at `7c8d6c5`); R8 ports `_run_pending_repair` and `_op_repair_entities` and names three exemptions by function; [[#ac-14]] walks `daemon.py`, `catalog_maint.py`, `store.py`, `cli.py` |
| S-2 (23.5 obligations) / d9bw c | header depends on 23.5; R4 `_inflight("reclaim")`, the one alarm, `after_locked`; R8 ports 23.5's compaction hold 2; Q-C closed |
| S-3 (three reopens, three exits; the named exit does not fire) / d9bw d | [[#facts]] I6 corrected; R8 "THE reopen" (`Daemon._reopen_writer`, under `_store_lock`, through `open_duckdb` and `_install_writer_store`) and "THE writer-lost exit" (`_writer_lost`, immediate, lock held, no repair marker), with the bug-113 helpers delegating; R6 calls it; [[#ac-14]] no longer contradicts R8; new [[#ac-21]] |
| S-4 (`hold_over` vs `reclaim_disabled`; `rewrite_too_slow` had no `run_id`) | R7 (c) and R3 (g): separate `reclaim_hold_over` key (hub-only block, a fast hand run clears it); R1 / R11: each mark carries a `run_id` for `--clear-disabled`; R3 (b) / R11: R14's verdict gates R12, the live bound is the deadline; [[#ac-8]], [[#ac-9]] name the keys |
| S-5 (two RMW writers of `catalog_state.json`) | every write through 18.2 R13's `update_state` (R2, R4, R6, R11) |
| S-6 (crash residue) | R3 (h) residue sweep: files moved to `backups/` (never deleted), scratch removed, the sentinel dropped under a short hold when `reclaim_inflight` shows an unfinished run; R4 writes and clears `reclaim_inflight`; [[#ac-6]] second reclaim succeeds; new [[#ac-22]] |
| S-7 (zombie writer) | [[#facts]] I12; R8 `Store.retire()` + `StoreClosed`; `close_writer()` uses it; new [[#ac-20]] |
| S-8 (R14 not measurable as written) | [[#r14-loaded]]: both slots + `active`; model-free reader mix; per-loop completions in the hold window, rows with a zero loop refused; budget raised to 60 s and raw `phase_a_s` compared with 5 s, whole hold with 10 s; [[#ac-19]]; R12 uses the verdict |
| M-2 (`st_ino` vacuous for I4) | R4 step 11 says only the sentinel and `total_blocks` detect I4 |
| M-3 (AC-18 a self-contradictory) | [[#ac-18]] (a) through `open_duckdb`, FAILS with `duckdb.connect` substituted |
| M-4 (Phase A scope vs d9bt) | R4: steps 1-2 outside the budget, the deadline armed after step 2; Q-D wording aligned |
| M-5 (AC-1 write sits in the WAL) | [[#ac-1]] forces a `snapshot` op before the child reads |
| M-6 (`lsof` races in-flight readers) | [[#ac-10]] waits for `_read_inflight == 0` |
| M-8 (the announcement is not enforced) | [[#r12-procedure]] says it is not a control (d8g) |
| d9bv (bytes tolerance) | [[#ac-7]] and [[#ac-16]]: `max(2 %, 512 KiB)` |
| bug-112 fix facts | header and I4: `backend.open_duckdb` is THE opener; the stale-holder close is safe only under `_store_lock`, which THE reopen asserts |
