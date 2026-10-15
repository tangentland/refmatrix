---
gmd: "0.1"
id: bsd-bug110-r1-60893d3
title: "ch-bsd r1 — bug-110 (60893d3): the out-of-process copy keeps the writer lock through 40+ live ops; three save-state tests that opened the live slot now fail deterministically (bug-108 is the same mechanism), and the inventory misreads replica merge as fenced"
severity: BULLSHIT
plan: bug-110
task: bug-110-snapshot-lock
tags: [bsd, audit, bug-110, bug-108, duckdb, lock, snapshot, daemon, r1]
---

# ch-bsd r1 — fix(daemon): bug-110 — snapshot copies the writer slot in a child process {#root}

**Commit range:** ddce097..60893d3 (1 commit).
**Date:** written 2026-10-14T20:48:18-0700.
**Author:** Todd Holley / Opus 5.5 / orchestrator.
**Files changed:** 3: `src/refmatrix/daemon.py`, `tests/test_bug110_snapshot_keeps_lock.py`,
`workflow/implementation_summaries/bug-110-snapshot-lock.md`.
**Tree:** littlebig clone `/Volumes/littlebig/refmatrix-bug110`, branch `bug-110-snapshot-lock`.
The base was compared from `git archive ddce097` copies in the session scratchpad. Every daemon
ran with `HOME` set to a fresh `/tmp` dir and `RMX_MODEL_SOCK` pointing at a dead path, so no
live store, socket or hub was touched. 5 mutations were each restored with `git checkout --` and
`__pycache__` cleared; `git status` was clean afterwards.

rel: evidence-for -> [[impl-bug-110-snapshot-lock]]

## What holds (measured) {#holds}

- **The mechanism (DuckDB 1.5.2).** `bsd-bug110-mech.log`: an in-process `open().close()` of
  the main file drops the lock (P3, OPEN), and so does `shutil.copy2` (P9). The following leave
  it held: `stat`/`exists`/`glob`/`getsize` (P1); a second in-process `duckdb.connect`,
  read-only (raises "different configuration") or same-config (P4/P5); an `ATTACH ... READ_ONLY`
  from `:memory:` (raises "Unique file handle conflict") (P6); a child `cp -p` (P8).
- **The WAL.** `bsd-bug110-wal.log`: DuckDB also `fcntl`-locks the `.wal` (W0 LOCKED). After a
  CHECKPOINT removes the WAL and a later write recreates it, the new WAL is locked again (W3).
  An in-process open+close of the `.wal` drops only the WAL lock; the main lock stays (W1). The
  main-file lock is what refuses a second process, and the snapshot path only unlinks the TMP
  file's `.wal`.
- **The fix, on a real `serve_forever` daemon** (`bsd-bug110-sweep-fixed.log`,
  `bsd-bug110-sweep2.log`). After each of these, a second process was REFUSED: 40+ ops (ingest,
  sync, snapshot, checkpoint, stats with `include_health`, context, grep, learn, replica
  status/audit/refresh/relink, repair_fragments/entities, vacuum, compact, rebuild_index,
  pagerank, memory ops, partition merge dry-run), 8 s of flush/index-repair/heartbeat/snapshot
  ticks, and a watcher edit. The one exception is `replica_merge` (#s-1). At base, the slot was
  already OPEN at "up", because the snapshot tick ran during boot (`bsd-bug110-merge.log`).
- **The RED test.** M1 (snapshot call site back to `shutil.copy2`) is killed by
  `test_second_writer_is_refused_before_and_after_a_snapshot`.
- **Cost** (`bsd-bug110-perf.log`, 767 MiB file, 3 runs each).
  - APFS: copy2 0.32-0.42 s, cp 0.29-0.33 s.
  - HFS+ littlebig: copy2 8.7-15.2 s, cp 8.8-14.4 s.
  - cp does NOT clone: one copy consumed 768 MiB of free space.
  - Spawn cost: `subprocess.run` median 9.7 ms from a process with 2 GiB resident and 40
    threads, against 9.0 ms from a lean one.
  - The store lock is held for as long as before; copy2 had no time bound, and cp now has
    600 s.
- **`cp -p` on other filesystems.** It exits 0 on HFS+ and FAT32 (a mounted MS-DOS image). It
  copies every xattr (`user.b110` + quarantine), while copy2 copied only quarantine. DuckDB does
  not care.

## Findings {#findings}

### BULLSHIT: the fix turns three save-state tests into deterministic failures, hidden by a name-only comparison {#b-1}

**File:** `tests/test_save_state_embeds_memories.py:125`, `:149`, `:175`. Each runs
`Store(root)` + `_connect()` in the TEST process while the fixture's spawned daemon is live.
**What:** The summary's verification says the daemon family run (`bug110-family.log`) matches the
"same 24 failures" as `bug110-failures-at-head.log`. The test NAMES match. The failure messages
do not.
- At ddce097, the three tests fail with bug-108's verbatim signature: `TransactionException
  ... Could not set lock on file "…/catalog.A.duckdb.wal": Conflicting lock is held in …
  Python`.
- At 60893d3, they fail with `IOException: Could not set lock on file "…/catalog.A.duckdb"`.
  That is the main file: the open is now refused.

**Measured** (`bsd-bug110-savestate-ab.log`, isolated HOME, real model cache via HF_HOME):

| tree | runs | result | error |
|---|---|---|---|
| fix 60893d3 | 3 × 3 tests | 9/9 fail | main-file lock |
| base ddce097 | 3 × 3 tests | 6/9 fail | WAL lock |

`bsd-bug110-bug108-mech.log` reproduces it outside pytest. At base, the harness's
`Store(root)` raised the bug-108 WAL error once and then COMMITTED twice to the live slot. The
daemon's own final probe then hit `IO Error: Failure while replaying WAL file`, so two writers
had corrupted the WAL. At the fix, it was refused 3/3.

**Why it's bullshit:** bug-108 ("not diagnosed", "flaky, about 1 in 5") is bug-110 seen from
the test side. Once the snapshot drops the daemon's main lock, the test can open the slot, and
it collides only on the WAL lock that DuckDB re-takes. The fix removes the window those tests
depended on. In the main tree they pass about 4 runs in 5, so after the merge they will fail on
every run. The commit does not touch the tests, the bug-108 row, or the summary's claim that
the family is "clone-environmental".
**Fix:**
1. Make the three tests read through the daemon: `dm.call(root, "memory_get"/"query"...)`, or
   a read-only Store on `catalog.read.duckdb` after a forced snapshot. The live writer slot is
   exactly what bug-110 forbids a second process to open.
2. Prove 0 failures in 10 runs on the branch.
3. Update bug-108 to `fixed by bug-110 + test fix` with this evidence.
4. Compare failure lists by message, not by name.

**Pattern match:** YES. See [[bsd-impressions#imp-same-name-different-failure]] (new) and
`imp-clean-corpus-hides-a-dead-gate` in memory: a list compared by key hid a changed value.

rel: contradicts -> [[claude#system-dependent-tests]]

### SKETCHY: the inventory calls replica merge "fenced (d9ae)"; it runs live, drops the lock, and fails on the current schema {#s-1}

**File:** `workflow/implementation_summaries/bug-110-snapshot-lock.md` (inventory row
`_op_replica_merge`); `src/refmatrix/daemon.py:5465-5510`; `src/refmatrix/cli.py:8703-8728`.
**What:** The d9ae fence is on PARTITION merge (`cli.py:4194`). `rmx replica merge` REQUIRES a
running daemon (`cli.py:8703`) and closes the writer (`_force_close_store`) for the whole merge.
For that whole span, the slot is unlocked to every other process.
**Measured:** `bsd-bug110-sweep-fixed.log` and `bsd-bug110-merge.log`, identical at base and fix.
1. `replica_merge {"dry_run": true}` on a freshly ingested store returns `merge build:
   BinderException('table entities has 13 columns but 14 values were supplied')`.
2. The reopen then fails: `merge: failed AND reopen failed: ... Unique file handle conflict ...
   already attached by database "a"`, because `merge_slots` leaks its `con` and ATTACH on the
   exception.
3. A second process got `OPEN` on `catalog.A.duckdb` right after the op. The lock came back only
   when a later tick lazily reconnected.

**Failure scenario:** an operator runs `rmx replica merge --dry-run` on any migrated store. It
fails on the schema, and until the next reconnect the live slot is unlocked to any CLI
in-process fallback.
**Fix:**
1. Correct the inventory row.
2. File a bug row for the pre-existing defects: `merge_slots` schema drift (13 vs 14 columns),
   the leaked connection on error, and the slot left unlocked on the failure path.
3. Either fence `replica merge` like partition merge or keep a lock-holding handle across the
   merge.

**Pattern match:** YES. See [[impression_bsd_guard_cannot_fire]]: a claimed guard that does
not cover this path.

### SKETCHY: the new helper's error branch is unpinned; a non-zero `cp` would install a truncated snapshot {#s-2}

**File:** `src/refmatrix/daemon.py:216-219` (`if proc.returncode != 0`), `:213-215` (timeout).
**What:** Mutations, `bsd-bug110-mutations.log`:
- M2 (`if False:` instead of the returncode check) survives.
- M4 (drop `-p`) and M5 (drop `timeout=`) survive.
- M3 (`_rebuild_slot_from` call site reverted) survives because nothing calls that method.
- Only M1 is killed.

**Failure scenario:** on a full volume, `cp -p` exits 1 and leaves a partial file. On a FAT
image, 23,068,672 of 40,000,000 bytes were written, then `fcopyfile failed: No space left on
device`, rc=1. With M2 in place, `os.replace(tmp, snap)` would install that truncated
`catalog.read.duckdb` for every reader and the mirror, and the suite stays green.
**Fix:** add a test that runs `_snapshot_catalog` with a failing copy. Two ways to make it fail:
put `cp` on PATH as `false`, or give a `dst` in a read-only dir. Assert two things: the
`{"error": "copy"}` dict comes back, and the old snapshot is unchanged. Add a second test that
pins the timeout so it becomes `OSError(ETIMEDOUT)`.

**Pattern match:** YES. See [[bsd-impressions#imp-remedy-guards-unpinned]].

### MEH: `_rebuild_slot_from` has no callers, and it was patched instead of deleted {#m-1}

**File:** `src/refmatrix/daemon.py:2540-2561`.
**What:** The summary admits "It has no callers today". The only reference anywhere in `src/` and
`tests/` is its own definition. Patching dead code makes it look maintained. The fix is to
delete it, or wire it and test it.

### MEH: `cp` is resolved through a user PATH {#m-2}

**File:** `src/refmatrix/daemon.py:213`.
**What:** The launchd daemons run with `PATH=/Users/tholley/bin:~/.local/bin:/opt/local/bin:
/opt/local/sbin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin` (read from a
`com.refmatrix.daemon.*` plist). Any `cp` placed ahead of `/bin`, such as a coreutils gnubin
or a shim, becomes the snapshot copier. Today `which -a cp` gives only `/bin/cp`. The fix is
to call `/bin/cp` by absolute path.

### MEH: the inventory holds only on the happy path, and the registry is not updated {#m-3}

**File:** `src/refmatrix/daemon.py:2898-2905`; `workflow/bug_registry.md`.
**What:**
- The survivor-clone branch wraps `CHECKPOINT; flush_fragments; close()` in one `try/except
  Exception: pass`. If the CHECKPOINT raises, `close()` is skipped and the in-process
  `shutil.copy2` runs with the store still open. That is the bug-110 drop at boot. The
  summary's verdict "not reached: the store is closed before the copy" assumes CHECKPOINT
  succeeds.
- The commit leaves the bug-110 row as "Not fixed / open" (main tree, line 163).
- bug-108's root cause is now known (#b-1) but is not recorded.

## Verdict {#verdict}

DIRTY: 6 findings (1 BULLSHIT, 2 SKETCHY, 3 MEH). The core claim is TRUE: the out-of-process
copy keeps DuckDB's lock, measured on a real daemon. The merge is blocked by #b-1: as committed,
the branch turns three tests into failures on every run in the main tree.

rel: contradicts -> [[claude#no-workarounds]]
