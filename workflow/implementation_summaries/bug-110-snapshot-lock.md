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
`{"error": "copy"}` path is unchanged and a partial copy is never installed. It runs `/bin/cp` by
absolute path. The survivor-clone branch of the rotation bootstrap uses it too.

## Sibling inventory {#inventory}

Every in-process byte copy of a catalog file in `src/`:

| site | verdict |
|---|---|
| `daemon.py` `_snapshot_catalog` | **patched**: the writer slot is open and locked |
| `daemon.py` `_rebuild_slot_from` | **deleted** (r1 #m-1): it had no callers |
| `daemon.py` `_bootstrap_rotation_if_needed`, survivor clone | **patched** (r1 #m-3): `close()` was inside the CHECKPOINT's `except: pass`, so a failed CHECKPOINT left the store open for the copy; close is now in a `finally` and the copy is out of process |
| `daemon.py` `_bootstrap_rotation_if_needed`, legacy seed | not reached: same close, copy, reopen |
| `daemon.py` `_op_replica_merge` swap | not reached by this defect: the writer is force-closed for the merge. **Not fenced**, which the first version of this table claimed (r1 #s-1). d9ae fences *partition* merge. A failing `replica_merge` dry run leaves the slot unlocked by another route; that is filed as bug-113 |
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

## Round 1 (ch-bsd `bsd-bug110-lock-held-tests-now-fail-60893d3`) {#round-1}

- **#b-1, and the error in my own verification.** Three tests in
  `test_save_state_embeds_memories.py` opened `Store(root)` on the live writer slot under the
  fixture's daemon. I compared the family's failures with master by NAME, and the names matched.
  The errors did not: master fails them on the WAL lock about 1 run in 5 (bug-108), while the fix
  refuses the main-file lock every run. **bug-108 is bug-110 seen from the test side.** The tests
  now force a snapshot and read it from a child process, as a CLI read does: 10 of 10 runs green
  (`bug110-r1-savestate-x10.log`).
- **A reader inside the test process saw an OLD snapshot** after a forced one. I first wrote
  "same inode, mechanism unnamed"; ch-bsd r2 measured it with `lsof`: DIFFERENT inodes. The test
  process held the replaced, unlinked file open through `search._REPLICA_CACHE` (filled by
  `verbs.memory_partition` → `cached_replica`), and DuckDB's `duckdb.connect()` instance cache
  hands that database to any later connect of the same path in the process. `gc` cannot see
  DuckDB's pybind connection objects, which is why I found no leak. `cached_replica` itself
  re-checks on every call, and the 4 live `rmx mcp` processes and the hub hold no duckdb fds, so
  today it is a LATENT defect for any second in-process opener. Filed as bug-112.
- **#s-2:** tests for a failing copy (a partial tmp is never installed; the previous snapshot is
  kept), a hanging copy and `-p`. Mutants M2 (returncode check), M4 (`-p`) and M5 (timeout) are
  each killed (`bug110-r1-mutations.log`).
- **#m-1, #m-2, #m-3:** as in the inventory above.

{#round-1-body}

## Round 2 (ch-bsd `bsd-bug110-r2-stale-snapshot-is-the-replica-cache-1fb6c0e`) {#round-2}

- **#s-1-r2:** the child read returns the memory names, and the two "no row without a vector"
  tests assert the expected names before asserting that nothing is pending. Mutation "snapshot
  frozen at boot" now fails all 3 dense tests; before this change it failed 1.
- **#s-2-r2:** `test_survivor_clone_closes_the_store_even_when_the_checkpoint_raises`. Mutation
  "close back inside the try" fails it (`bug110-r2-mutation.log`).
- **#m-1-r2:** the bug-112 text above and the test docstring now carry the measured mechanism.

{#round-2-body}

## Deploy note {#deploy}

A running daemon has already lost its lock and does not get it back: the fix lands when the
daemon restarts (`rmx daemon restart --relaunch` per store, which the deploy does).
