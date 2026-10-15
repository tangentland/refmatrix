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
> on a LOADED hold. The file name and id keep `offline-reclaim` so inbound links stay stable.
> Wave: 4 ([[plan-review-2026-10-14#t10-waves]]).
> Depends on:
> - **bug-112 FIXED and reachable from `master`** (an in-process `duckdb.connect` of a path that
>   is already open returns the cached database; [[bug_registry]]). The fix is in progress on
>   branch `bugs-112-113-118`. 18.3 does not start before it merges, and AC-18 reproduces the
>   swap write-loss against the merged fix (d9bp a).
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
  - and `rmx compact` (`cli.py:7630`) does it OUT of the daemon (F3's four flaws).
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
  per-run proof that the reopened connection is the new file (R4 step 10).
- **I9 The idle number is not the loaded number** ([[bsd-plan18-task18-1-measurement-r1-8a93ab1#s-1]]).
  18.1's refmatrix rewrite took 1.94 s idle in a dedicated child; on the same copy with 6
  concurrent read loops it took 3.60 / 3.72 / 3.92 s. The rest of the hold (gate with content
  hash 0.10 s, CHECKPOINT ~0, copy 0.04-0.18 s, open 0.005 s) added about 0.3 s. The rewrite's
  peak RSS was 884 MiB, which in the daemon adds to the serving process.
- **I5 bug-113's lessons** (the merge defect). Its target was built by a separate schema
  (`init_catalog`) that lagged the Store's; it left a connection open on error; and it returned
  with the writer closed. `COPY FROM DATABASE` copies the writer's OWN schema, so the first
  lesson does not apply here. The other two are R6's rules.
- **I6 The fast exit.** `_fast_exit_if_invalidated` (`daemon.py:1443`) ends in `os._exit(2)`.
  The LaunchAgent's `KeepAlive {SuccessfulExit: false}` (`launchctl.py:258`) respawns on a
  non-zero exit, and the boot path opens the slot named by the `active` marker.
- **I7 What a hold can cost.** The hub restarts a daemon after 3 missed pings 15 s apart with a
  heartbeat older than 60 s (18.2 L2). A hold of at most 10 s can miss at most one 2 s ping and
  cannot age the heartbeat past 60 s.
- **I8 Slot offsets** (`catalog.<S>.offset`, `daemon.py:2839`) record the `facts.log` position
  a slot is current to. A rewrite under the same slot letter carries the same rows, so the
  offset stays true and is not touched.

{#facts-body}

## The design in one picture {#design}

```
verb rmx_catalog_reclaim ──> daemon op catalog_reclaim
  dry_run=True  : REHEARSAL, lock-free, in children, on a copy of the snapshot (R2)
  dry_run=False : preconditions (R3), then ONE hold through the 18.2 helper (R4):

  _catalog_hold("reclaim", snapshot=True, lock_wait_s=30, deadline_s=10)
    takes _snapshot_lock, then _store_lock                         (I2)
    Phase A, interrupted (con.interrupt()) past the 5 s budget:
      flush_fragments; CHECKPOINT; ATTACH new; COPY FROM DATABASE; CHECKPOINT new;
      GATE (R5) writer vs new; write SENTINEL into new; DETACH
    Phase B, the swap:
      close writer -> link slot to backups/ -> os.replace(new, slot)
      -> reopen_writer(slot) through _install_writer_store
      -> identity check + SENTINEL read-back (absent -> rollback), drop sentinel
    Phase C: snapshot() — the snapshot tick's own locked body
  release; after: read-only link, mem mirror, write-through check of the snapshot in a child,
  baseline reset, ledger, rmxd.log
  any failure -> rollback (R6); the slot path never names a missing or partial file
```

## Requirements {#requirements}

1. **R1 Verb, op, surfaces, one ledger.** {#r1-verb}
   - Verb `rmx_catalog_reclaim(dry_run: bool = True, confirm: str | None = None,
     status: bool = False, list_backups: bool = False, clear_disabled: str | None = None, *,
     invoked_by: str) -> dict`, daemon op `catalog_reclaim`, CLI `rmx catalog reclaim
     [--confirm <run_id>] [--status] [--list-backups] [--clear-disabled <run_id>]`, MCP parity
     through the verb-parity test. `clear_disabled` is hand-only (`cli` / `mcp`) and must name
     the `run_id` recorded in `reclaim_disabled` (R6).
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
   - With no `baseline_file_bytes` in `catalog_state.json`, a successful rehearsal writes
     `rewrite_bytes` as the baseline (`baseline_source: "rehearsal:<run_id>"`; 18.2 R5).
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
   - (g) **Not disabled.** `catalog_state.json` has no `reclaim_disabled` (R6, R7 c). For `hub`
     only, also no `checkpoint_disabled` (18.2 R4: a store whose plain CHECKPOINT ran over 10 s
     gets no automatic rewrite) and no unremoved pre-reclaim backup (R9).
4. **R4 The one hold.** The real run is ONE call of 18.2's helper,
   `d._catalog_hold("reclaim", body, snapshot=True, lock_wait_s=RMX_CATALOG_LOCK_WAIT_S,
   deadline_s=RMX_CATALOG_RECLAIM_BUDGET_S)` ([[task-18.2-catalog-maintain-step#r11-hold-helper]]).
   It reuses 18.2's wait (30 s) and Table D's 10 s ceiling for the whole hold, and adds one
   constant, the 5 s Phase A budget (d9bp: the 5 s gate, applied to the loaded number). On a
   wait timeout the outcome is `skipped:lock_busy` with no hold. {#r4-hold}
   - **Lock order.** `snapshot=True` makes the helper take `_snapshot_lock` and THEN
     `_store_lock` (I2). Both waits are inside the one `lock_wait_s` budget.
   - **Phase A, interruptible.** Inside the hold:
     1. `st.flush_fragments()`: dirty bitmap fragments are in memory, and the COPY reads tables;
     2. `h.checkpoint()`: the WAL is folded into the slot;
     3. `h.rewrite_into(new)` with `new = <root>/catalog.<S>.reclaim-<run_id>.duckdb` (a path no
        connection in the process has opened; bug-112): `ATTACH`, `COPY FROM DATABASE`,
        `CHECKPOINT` on the new file, timed as `rewrite_s`;
     4. `h.gate("rc")` (R5) between the writer and the new file, timed as `gate_s`. It also
        records the pre-swap per-table counts;
     5. **The sentinel** (d9bp a). AFTER the gate passes: `CREATE TABLE
        rc._rmx_reclaim_sentinel(run_id VARCHAR)`, insert this `run_id`, and `CHECKPOINT` the
        new file. Then record the new file's `PRAGMA database_size` `total_blocks`;
     6. `DETACH`. The new file's `.wal` must be absent or 0 bytes.

     If Phase A is still running `deadline_s` (5 s) after the acquire returned, the helper's
     timer calls `con.interrupt()` on the writer connection. Phase A then raises and R6 A runs;
     the store's consecutive-deadline count goes up (R11).
   - **Phase B, the swap.** Not interruptible; each step is timed.
     7. `h.close_writer()`: `Store.close()`. A raised error or a non-empty `close_errors` goes
        to R6 B, with nothing renamed yet.
     8. The slot's `.wal` must be absent or 0 bytes, else R6 B.
     9. `os.link(slot, backups/catalog.<S>.pre-reclaim-<run_id>.duckdb)`, then
        `os.replace(new, slot)`, then `fsync` of the root and `backups/` directories. The slot
        is never unlinked or renamed away: at every instant its path names either the original
        inode or the gated new one (R6 invariant).
     10. `h.reopen_writer(slot)`: the ONE close-and-reopen sequence (R8), through
         `_install_writer_store`.
     11. **Identity check and sentinel read-back.** All of these must hold, else R6 B:
         - `SELECT run_id FROM _rmx_reclaim_sentinel` on the reopened writer returns exactly
           this `run_id`. The old file has no such table, so a reopen that got the cached old
           database (I4) fails here (d9bp a);
         - its `PRAGMA database_size.total_blocks` equals step 5's;
         - the slot's `st_ino` equals the inode the new file had before step 9;
         - the per-table counts equal step 4's.

         Then `DROP TABLE _rmx_reclaim_sentinel` through the reopened writer. That is the
         first write through the new connection, and the after-release check proves it reached
         disk.
   - **Phase C.** `h.snapshot()`: the snapshot tick's own locked body (CHECKPOINT, child copy
     of the slot to `catalog.read.duckdb.tmp`, `os.replace`), run inside the same hold so the
     snapshot is the reclaimed file before the hold ends (F5, R7).
   - **After the release** (the helper's `after` callbacks): swing `read_only.duckdb` and refresh
     the mem mirror (as the snapshot tick does). Then a child opens a copy of the new snapshot
     and checks that `_rmx_reclaim_sentinel` is ABSENT and the per-table counts equal step 4's.
     That proves the reopened connection's first write reached the file on disk, the exact loss
     in I4. Writes after the release make a rollback unsafe, so a failure here does not roll
     back: it writes `reclaim_disabled` (cause `write_through`), logs one loud line, and makes
     the hub row hot through `catalog_hold_over`'s path (18.2 R7). Then reset 18.2's baseline
     (R7 b), append the ledger line, and log one `rmxd.log` line.
   - **Memory.** The COPY runs in the daemon, so its working set adds to the serving process: a
     peak of 884 MiB on refmatrix's copy (I9). The ledger line records `ru_maxrss` before and
     after the hold, and R14 measures the peak per store. This cost is stated, not hidden.
   - **The report and the ledger line** carry: `wait_s`, `hold_s`, the D band of `hold_s` (18.2
     Table D), and per-phase seconds (`flush_s`, `checkpoint_s`, `rewrite_s`, `gate_s`,
     `sentinel_s`, `close_s`, `swap_s`, `reopen_s`, `snapshot_s`), plus `phase_a_s` against the
     budget. They also carry `file_bytes_before`, `file_bytes_after`, `rewrite_bytes`, `r`,
     the backup path and its bytes, `ru_maxrss` before and after, the rehearsal `run_id` and
     its `idle_hold_s`, and `hold_vs_idle = hold_s / idle_hold_s` (the live load factor, I9).
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
   - **Invariant.** Only `os.link` and `os.replace` touch the slot's NAME, so a crash at any
     point (SIGKILL, power loss, a fast exit) leaves the slot naming a complete file: the
     original, or the gated new one. A boot on either opens a catalog with every row.
   - **A: Phase A fails** (gate difference, deadline interrupt, statement error). The writer
     was never closed. `DETACH` runs in a `finally`. A gate-failed, complete new file is moved
     to `backups/catalog.<S>.reclaim-failed-<run_id>.duckdb` and kept. An interrupted, partial
     file is deleted, and its path and bytes are reported (`partial_removed`). The outcome is
     `failed:gate` or `failed:deadline`, with `ok: false`.
   - **B: Phase B fails** (close error, WAL present, link or replace error, reopen error,
     identity mismatch). This path runs still inside the hold:
     - If the replace happened, `os.link(slot, backups/…reclaim-failed-<run_id>.duckdb)` keeps
       the new file. Then `os.link(backup, <slot>.rollback)` and
       `os.replace(<slot>.rollback, slot)` restore the original inode atomically.
     - `h.reopen_writer(slot)`, then an identity check against the PRE state: per-table counts
       equal step 4's, and `total_blocks` equals the old file's.
     - On success: the redundant `pre-reclaim` link is removed (it names the same inode as the
       slot, so no bytes go), and the outcome is `rolled_back:<cause>`, `ok: false`.
   - **A rollback that fails** (any step above raises, or the original's identity check fails).
     The daemon must not keep serving with a closed or unverified writer (I5).
     - It logs one line naming the slot, the backup, the failed file and each one's inode.
     - It writes `catalog_state.json` `reclaim_disabled: {run_id, cause, at}`.
     - It exits through the fast-exit path (`os._exit(2)`, I6). launchd respawns the daemon,
       and by the invariant the boot opens a complete file.
     - `reclaim_disabled` blocks every later real run until a hand
       `rmx catalog reclaim --clear-disabled <run_id>` after the user has read the log.
7. **R7 The snapshot, the double count, and the band after a reclaim.** {#r7-after}
   - (a) **F5.** The snapshot is refreshed inside the hold (Phase C). After the run,
     `catalog.read.duckdb` has the slot's bytes, and `_store_health` `store_bytes` falls by
     about twice the reclaimable bytes. The old snapshot's inode and the backup's inode have no
     descriptor in the daemon process (bug-112's fix is what makes that hold for in-process
     snapshot readers).
   - (b) **Baseline** (d9bq). 18.2's `catalog_state.json` gets `baseline_file_bytes =
     rewrite_bytes` (the new file's size, which is the store's live-data size), `baseline_at`
     and `baseline_source: "reclaim:<run_id>"`. 18.2's growth band (`file_bytes ≥ 2 ×`
     baseline) is then exactly Table A's A2 edge, `r ≥ 0.50`.
   - (c) **Hold bands.** A real run with `hold_s` over `RMX_CATALOG_HOLD_MAX_S` (possible only
     in Phase B or C, since Phase A is interrupted at the deadline) writes `reclaim_disabled`
     with cause `hold_over`. Only a hand run whose `hold_s ≤ 10` clears it. A D1 hold (2-10 s)
     is reported with a `rmxd.log` warning.
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
   - **Adds:** `rewrite_into(target)`, `gate(alias)`, `close_writer()`, `swap(new, backup)`,
     and `reopen_writer(path)`.
     - `reopen_writer` is the only place a writer Store is constructed and installed after
       boot's first open: `Store(root, partition)`, `db_path = path`, `_install_writer_store`,
       `init()`.
     - `rewrite_into` and `gate` are module functions over a connection, so the rehearsal child
       (R2) and the hold run the same code.
   - **Ports** onto `_catalog_hold` + `checkpoint()` + `close_writer()` + `reopen_writer()`:
     - the init slot rebind (`daemon.py:1755-1791`; 23.1 R1.6 item 4 already moves it under
       `_store_lock`);
     - both `_bootstrap_rotation_if_needed` branches (`:2918-2936`, `:2955-2972`). Their copies
       go through the helper's `copy_out`, and the legacy branch's in-process `shutil.copy2`
       goes with them.

     Behaviour is unchanged at each site, including the init rebind's legacy fallback and its
     loud log line.
   - **After 18.3:**
     - `daemon.py` has no `"CHECKPOINT"` string literal and no `_copy_out_of_process(` call
       outside the helper, except in `_op_replica_merge`. That exemption is named: the op is
       fenced (d9ae), bug-113 is open against it, and the helix plan owns the live merge;
     - `_install_writer_store` is called only from `reopen_writer` and boot's first open;
     - `rmx compact` has no daemon code of its own (R10).
   - **Not ported, and why.** `_compact_factslog_locked` (23.1) also holds `_store_lock` around
     a dump and a file swap, but its file is `facts.log`, not the catalog, and 23.1 owns it.
     It is the same shape one level up and is raised as open question Q-C.
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
     never leads to a swap on the same night. The ledger line and one
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
     or whose last reclaim was disabled. R4's budget interrupts Phase A at 5 s, and R11 retires a store after two such deadlines. 17.2 calls
     the step with `retries=0`, single-flight, under its stuck ceiling.
10. **R10 `rmx compact` is retired onto the verb.** `rmx compact` becomes `rmx catalog reclaim`
    under its old name: with no flag it rehearses and prints the report, and with
    `--confirm <run_id>` it runs for real. {#r10-compact}
    - Deleted: its EXPORT/IMPORT path (`cli.py:7686`, `:7691`), its in-process `duckdb.connect`,
      its daemon stop and its `spawn_daemon` restart, and the `--keep-backup` flag (a backup is
      always kept, R7 d).
    - The CLI tree is regenerated, and the generated-artifact checks run with the family
      (`feedback_family_list_misses_generated_checks`).
11. **R11 No offline route: a store too slow for the daemon goes to the helix plan** (d9bp b).
    The old offline design is not kept as a fallback; nothing in this plan builds it.
    {#r11-offline-route}
    - A store is `rewrite_too_slow` when any of these holds:
      - R14's loaded max hold for it exceeds 5 s;
      - its rehearsal's `idle_hold_s` exceeds 5 s;
      - two consecutive real runs end `failed:deadline` (R4's interrupt).
    - The mark is written to `catalog_state.json` (`rewrite_too_slow: {since, cause, value}`).
      Every later real run refuses `refused:rewrite_too_slow` (Table C's refusal name,
      [[task-18.1-catalog-measurement#r3]]). Health reports it and the hub row is hot, as
      `catalog_reclaim_due` is.
    - The store gets a bug-registry row naming the number, and goes to the helix plan, as
      Table C's C2 does. Only a hand `--clear-disabled` after a new R14 measurement under 5 s
      lifts the mark.
12. **R12 The hand rollout.** It covers the four stores 18.1 banded A1/A2: refmatrix, global
    (`~/.refmatrix`), cliquedb and viascope. One store at a time, each announced to the user
    first. {#r12-procedure}
    - R14's loaded measurement has been run for the store, and its loaded max hold is ≤ 5 s.
    - `rmx catalog reclaim`, then read the report and check its `idle_hold_s` against 18.1's
      max for that store (1.98, 0.47, 1.06 and 1.76 s): a value over 2× 18.1's max + 1 s is
      investigated before any confirm.
    - `--confirm <run_id>`, then read `hold_s`, the D band, `hold_vs_idle` and the RSS fields,
      and compare `hold_s` with R14's loaded max for the store.
    - A D1 hold on a live store, or a `hold_s` over 5 s, gets a bug-registry row before the next
      store.
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
      23.0-style short tmp root as the writer slot of a tmp daemon. Nothing touches the live
      root's files except that copy's read, and no live socket is used.
    - **The load:** 6 concurrent reader loops through the tmp daemon's socket (`stats`,
      `context`, `query`), plus one writer loop (`upsert_entity`) at about 2 Hz.
    - **The runs:** 3 production real runs (`rehearse`, then `confirm`), each on a fresh copy.
      Per run it records `hold_s`, the per-phase seconds, `phase_a_s`, and the daemon's peak RSS
      (sampled every 50 ms from `ps -o rss`, and `ru_maxrss` from the ledger).
    - **Output:** `workflow/review-output/plan18-reclaim-hold-<YYYYMMDD>.{jsonl,md}`, with one
      row per store: loaded max `hold_s`, max `phase_a_s`, peak RSS, the duckdb version, and a
      verdict, `eligible` (loaded max hold ≤ 5 s) or `rewrite_too_slow` (R11). The plan records
      the per-store verdicts before R12 starts.
    - **Pre-registered edges** (written 2026-10-15, before any run): 5 s on the loaded max
      hold (d9bp). A peak RSS over 2 GiB on any store is a user decision before its rollout; it
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
   - **writes land in the new file:** an entity written after the run is seen by a fresh child
     opening a copy of the slot, and is NOT in the backup;
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
4. **AC-4 (rollback, including bug-112's class).** {#ac-4}
   - (a) `reopen_seam` raises once after the replace → `rolled_back:reopen`. The slot's inode
     equals the ORIGINAL inode, the counts equal the pre counts, the pid is the same and a write
     succeeds, and the new file is kept as `reclaim-failed`.
   - (b) The test holds a second in-process `duckdb.connect(slot)` in the daemon (a seam run
     before the op), so the reopen gets the cached old database (I4). With bug-112's fix this
     case must not reach the old database at all; the test runs it to prove the guard, not the
     fix: the sentinel read-back finds no table → `rolled_back:sentinel`, with the same
     assertions as (a).
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
6. **AC-6 (crash consistency, the R6 invariant).** For each point in Phase B (after the close,
   after the link, after the replace, after the reopen), the seam blocks on an event, the test
   sends SIGKILL to the daemon, and then it boots a fresh daemon on the root. Each boot opens,
   and its counts equal the pre counts. Mutation: `rename(slot → backup)` + `rename(new → slot)`
   in place of link + replace FAILS (a kill between the renames leaves no slot, and the boot
   opens an empty catalog). {#ac-6}
7. **AC-7 (production path = 18.1's path; 18.1 R4).** On 18.1's AC-2 fixture (200/80 MiB,
   d9bh): {#ac-7}
   - (a) the production rehearsal against 18.1's `measure_root` (script `8a93ab1`, or its
     `master` merge, which imports the shared `rewrite_into` / `gate`): median
     `rewrite_bytes` within 2 % (d9br: one rewrite's size varies by about 1.3 %), median
     `rewrite_s` within ±25 %;
   - (b) a real run on a tmp daemon whose slot is that fixture: its `rewrite_bytes` (the new
     file before the swap) within 2 % of the rehearsal's, and its `rewrite_s` (the COPY phase
     only) within ±25 % of the rehearsal median.

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
   - `reclaim_disabled` set.

   Mutation: the budget check removed FAILS (the run proceeds).
9. **AC-9 (hold over the ceiling).** `RMX_CATALOG_HOLD_MAX_S=0.2`, with a Phase C seam that
   sleeps 0.3 s: `hold_over`, and `reclaim_disabled` with cause `hold_over`. A hub run is then
   refused. A hand run with no seam clears it. Mutation: the flag not persisted FAILS. {#ac-9}
10. **AC-10 (the snapshot and F5).** After AC-1's run: {#ac-10}
    - `catalog.read.duckdb` has the slot's size, and its mtime_ns is no later than the
      recorder's release time for the hold;
    - `store_bytes` fell by ≥ 1.8 × (pre-run slot bytes − post-run slot bytes);
    - health `catalog.backup_bytes` equals the backup's size;
    - `lsof -p <daemon pid>` lists no descriptor on the backup's inode or on the replaced
      snapshot's inode.

    Mutation: no Phase C snapshot (left to the next write tick) FAILS.
11. **AC-11 (the tick step).** This runs in 17.2's harness (injected `roots` and `now`, two tmp
    stores), with `catalog_state.json` set by real `catalog_maintain` runs. {#ac-11}
    - (a) band A0: `skipped:no_reason`, no child process spawned (a spy on `subprocess.run`),
      no hold, and the reason detail in the ledger;
    - (b) band A2, unarmed: `dry_run:unarmed`, a rehearsal line, and the slot inode unchanged;
    - (c) band A2, armed through a hand rehearsal + hand confirm + `hub_maintain_arm`: a real
      run, `ok`, and the baseline reset; the next night is band A0 and `skipped:no_reason`;
    - (d) armed with an earlier `pre-reclaim` backup present: `refused:backup_pending`;
    - (e) `catalog_maintain` blocked (17.2 AC-10's shape): `deferred`.

    Mutations: the reason gate removed FAILS (a spawns the rehearsal); `requires_arming=False`
    FAILS (b swaps); the backup cap removed FAILS (d).
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
14. **AC-14 (one helper; AST over `daemon.py`).** {#ac-14}
    - no `"CHECKPOINT"` string literal and no `_copy_out_of_process(` call outside
      `_op_replica_merge`;
    - `_install_writer_store` is called only from `CatalogHold.reopen_writer` and boot's first
      open;
    - `_op_catalog_reclaim` takes no lock itself: no `_store_lock` or `_snapshot_lock`
      reference in its body.

    Mutations: an inline swap in `_op_catalog_reclaim` FAILS; the init rebind left hand-spelled
    FAILS.
15. **AC-15 (lock order).** A write burst runs while a reclaim is in Phase A (the seam blocks on
    an event), so the snapshot tick is waiting. Releasing the event completes both within 5 s,
    and the snapshot tick's next hold follows the reclaim's. Mutation: the helper taking
    `_store_lock` before `_snapshot_lock` FAILS (a deadlock, caught by the test's 5 s bound and
    reported as a failure, not a hang). {#ac-15}
16. **AC-16 (pre-registered constants).** `RMX_CATALOG_RECLAIM_BUDGET_S` = 5 (18.1 R3's
    in-daemon edge, applied to the loaded number by d9bp), two consecutive deadlines for
    `rewrite_too_slow`, the 2 % bytes tolerance, `RMX_CATALOG_RECLAIM_MAX_AGE_S` = 86,400, drift 0.10, and a disk margin of 256 MiB.
    The reused 18.2 constants (`RMX_CATALOG_HOLD_MAX_S` 10, `RMX_CATALOG_LOCK_WAIT_S` 30,
    `RMX_CATALOG_WAL_MAX_BYTES` 64 MiB) are imported, not redefined. Changing a value, or
    redefining a reused one, FAILS this test. {#ac-16}
17. **AC-17 (pre-registered mutations; each must FAIL a named AC).** Each is restored in its own
    command (`feedback_mutation_must_fail_not_hang`). {#ac-17}
    - the gate removed, or any one gate leg removed → AC-2;
    - the consecutive-deadline count not persisted → AC-3;
    - the sentinel read-back removed, or the sentinel left in the slot → AC-4 / AC-1;
    - the post-release write-through check removed → AC-18;
    - no deadline interrupt → AC-3;
    - the identity check removed → AC-4;
    - staying up after a failed rollback → AC-5;
    - rename in place of link + replace → AC-6;
    - the budget check removed → AC-8;
    - `reclaim_disabled` not persisted → AC-9;
    - no Phase C snapshot → AC-10;
    - the reason gate removed, `requires_arming=False`, or no backup cap → AC-11;
    - `hub` accepted with `confirm` → AC-12;
    - an inline swap, or a hand-spelled init rebind → AC-14;
    - inverted lock order → AC-15;
    - a constant changed → AC-16;
    - the `active` marker flipped, the inactive slot used as the target, or the backup deleted
      after a success → AC-1.

18. **AC-18 (bug-112's swap write-loss, against the merged fix; d9bp a).** {#ac-18}
    - (a) **The bare reproduction**, with no refmatrix code: in one process, open two
      connections to a file, close one, `os.replace` a new file over the path, connect again,
      write a row, CHECKPOINT, close everything; a child then reads the path. With bug-112's
      fix in the code path the daemon uses to open its writer (`Store._connect`, or whatever
      the fix names), the row is on disk. This test is the fix's regression guard, and it
      FAILS on the unfixed opener (the row is lost; ch-bsd r1's evidence).
    - (b) **Through the product:** AC-1's run with the after-release write-through check:
      the child sees no sentinel table, and sees the entity written after the run. Mutation:
      the post-release check removed FAILS a variant whose `reopen_seam` returns the old
      connection AND whose read-back seam is forced to pass (the loss goes unreported).
19. **AC-19 (the loaded measurement is the product path).** R14's script on 18.1's AC-2
    fixture, in the sandbox: each row records `hold_s` from the production op's ledger line (not
    a timer of the script's own), a peak RSS above the idle daemon's, and a verdict. With
    `RMX_CATALOG_RECLAIM_BUDGET_S=0.001` the verdict is `rewrite_too_slow`. Mutations: the
    script timing its own COPY instead of calling the op FAILS (no ledger `run_id` in the row);
    the reader loops not started FAILS (the row's `readers` count is 0, and the script refuses
    a row without load). {#ac-19}

## Test strategy {#test-strategy}

- Tier 1 (in-process, 23.0) covers AC-1..AC-19. Every daemon is a real tmp daemon; AC-5 and
  AC-6 run the daemon as a subprocess so the exit code and the SIGKILL are real. No launchd
  path is under test: the design never stops or starts a daemon. AC-5's respawn is a fresh boot
  by the test; launchd's respawn rule is fact I6, not a property of this task.
- Locks are checked with 23.2's recorder on a real `_FairLock`. The bound is one hold per real
  run; seconds are compared, not used as the bound, except AC-3's deadline (23.2 R5).
- The AC-17 mutations (and AC-18 and AC-19's own) run before GREEN is declared.
- No test touches a live root or a live socket.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/catalog_maint.py` | (created by 18.2) adds `rewrite_into`, `gate`, `CatalogHold.close_writer` / `swap` / `reopen_writer`, the `rewrite` / `gate` child entry points, the rehearsal and real-run routines with their seams |
| `src/refmatrix/daemon.py` | `_op_catalog_reclaim` (status, list-backups, clear-disabled); the init rebind and both `_bootstrap_rotation_if_needed` branches ported onto the helper (R8); `_store_health` `catalog.backup_bytes` |
| `src/refmatrix/verbs.py`, `cli.py`, `mcp.py` | `rmx_catalog_reclaim`; `rmx catalog reclaim`; `rmx compact` retired onto it (R10) |
| `src/refmatrix/hub.py` | the `catalog_reclaim` registration (R9) |
| `eval/catalog_maint/measure_catalogs.py` | when merged from the 18.1 clone, imports `catalog_maint.rewrite_into` / `gate`, so a re-taken 18.1 measures the product |
| `eval/catalog_maint/measure_reclaim_hold.py` | new: R14's loaded measurement over the production op |
| `tests/test_catalog_reclaim.py`, `tests/test_hub_catalog_reclaim_step.py`, `tests/test_catalog_reclaim_load.py` | new: AC-1..AC-19 (AC-18 a may live with bug-112's own test file if the fix already ships it; it must exist and FAIL on the unfixed opener) |
| CLI tree | regenerated |

## Open questions (with recommended answers) {#open-questions}

- **Q-A, `requires_arming` for the reclaim step.** Recommended: `True` (R9). It reads against
  d9bg's last sentence; the reason is in R9. If the user prefers `False`, R3 (g)'s backup cap and
  the fresh in-op rehearsal remain the only guards, and AC-11 (b) changes to expect a swap.
- **Q-C, `facts.log` compaction on the helper.** Recommended: yes, as a 23.1 or 23.5
  amendment, not here. `_compact_factslog_locked` is the same hold-and-swap shape. Its
  unmeasured hold is the open question behind the 00:11-00:13 restart (18.2 `#why`), and the
  helper's hold ring would give it a number for free.
- **Q-D, where the deadline falls.** Recommended: the 5 s budget interrupts Phase A only, and
  the whole hold is measured against Table D's 10 s. Phases B and C were about 0.3 s on
  refmatrix's copy (I9) and cannot be interrupted safely mid-swap. If the user wants a hard 5 s
  on the whole hold, the Phase A budget becomes `5 s − R14's max (phase B + C)` per store.
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
| d9bp b (no offline route; PROVISIONAL) | [[#r11-offline-route]] rewritten: `refused:rewrite_too_slow` → helix plan; Q-B withdrawn |
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
