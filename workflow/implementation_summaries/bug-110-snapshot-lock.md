---
gmd: "0.1"
id: impl-bug-110-snapshot-lock
title: "bug-110: the read snapshot no longer drops the daemon's DuckDB lock on its own writer slot"
tags: [implementation-summary, bug-110, daemon, duckdb, lock, snapshot]
metadata:
  node_type: implementation-summary
  status: in-review
  created: 2026-10-14
  updated: 2026-10-14
---

# bug-110: snapshot copy keeps the writer lock {#root}

rel: implements -> [[bug_registry#registry]]

## The defect {#defect}

DuckDB guards a database file with a POSIX `fcntl` lock. POSIX record locks belong to the
(process, file) pair and are released on ANY `close()` of ANY descriptor for that file in the
process. `Daemon._snapshot_catalog` copied the live writer slot with an in-process
`shutil.copy2`, whose close of the source descriptor released the daemon's lock the first time a
snapshot ran. From then on a second process could open the live slot read-write and commit; the
CLI's up/busy/absent check was the only guard. Found by ch-bsd bug-105 r5 #s5-3 (probe q2b).

## The fix {#fix}

`_copy_out_of_process(src, dst)` (module level, `daemon.py`) runs `cp -p` in a child process. A
child's descriptors are its own, so its close cannot release our locks, and fork does not inherit
POSIX locks. It raises `OSError` on a non-zero exit or a timeout, so `_snapshot_catalog`'s existing
`{"error": "copy"}` path is unchanged. `_rebuild_slot_from` uses it too: its source may be the
live writer slot.

## Sibling inventory {#inventory}

Every in-process byte copy of a catalog file in `src/`:

| site | verdict |
|---|---|
| `daemon.py` `_snapshot_catalog` | **patched**: the writer slot is open and locked |
| `daemon.py` `_rebuild_slot_from` | **patched**: source may be the writer. It has no callers today |
| `daemon.py` `_bootstrap_rotation_if_needed`, survivor clone | not reached: the store is closed before the copy and reopened after it, so the lock is taken fresh |
| `daemon.py` `_bootstrap_rotation_if_needed`, legacy seed | not reached: same close, copy, reopen |
| `daemon.py` `_op_replica_merge` swap | not reached: the writer is force-closed first, and the live merge is fenced (d9ae) |
| `cli.py` verb-alias merge snapshot | not reached: a separate CLI process after `s.close()` |
| `_MemMirror.refresh` | not reached: it ATTACHes `catalog.read.duckdb`, not a slot |

## Verification {#verification}

- RED at HEAD `ddce097`: `tests/test_bug110_snapshot_keeps_lock.py` controls that the open store
  refuses a second writer, then shows a second process COMMITTING after one snapshot
  (`workflow/review-output/bug110-red.log`).
- GREEN: that file plus the snapshot/replica families, 50 passed (`bug110-green.log`).
- End-to-end probe on a real `Daemon` (rotation bootstrap onto slot A, three write + snapshot
  rounds, second-writer probe after each): HEAD = COMMITTED after the first snapshot; fix =
  REFUSED in all three (`bug110-probe-head.log`, `bug110-probe-fixed.log`).
- Daemon/replica/snapshot/rotation/lock family: see `bug110-family.log`.

## Deploy note {#deploy}

A running daemon has already lost its lock and does not get it back: the fix lands when the
daemon restarts (`rmx daemon restart --relaunch` per store, which the deploy does).
