---
gmd: "0.1"
id: bsd-bug110-r2-1fb6c0e
title: "ch-bsd r2 — bug-110 remedy (60893d3..1fb6c0e): all six r1 findings closed at the cited lines; bug-112's stale in-process read is DuckDB's connect() instance cache pinned by search._REPLICA_CACHE; two of the three rewritten tests pass on a frozen snapshot"
severity: SKETCHY
plan: bug-110
task: bug-110-snapshot-lock
tags: [bsd, audit, bug-110, bug-112, bug-113, duckdb, snapshot, instance-cache, r2]
---

# ch-bsd r2 — fix(daemon,tests): bug-110 r1 remedy {#root}

**Commit range:** 60893d3..1fb6c0e (7954a97 code + tests, 1fb6c0e summary + r1 ledger).
**Date:** written 2026-10-14T21:35:15-0700.
**Author:** Todd Holley / Opus 5.5 / orchestrator.
**Files changed:** 8. Code: `src/refmatrix/daemon.py`, `tests/test_bug110_snapshot_keeps_lock.py`,
`tests/test_save_state_embeds_memories.py`. Docs: the implementation summary and the ledger.
**Tree:** littlebig clone `/Volumes/littlebig/refmatrix-bug110`, branch `bug-110-snapshot-lock`.
Every run used `PYTHONPATH=<clone>/src` with the main tree's `.venv-eval` interpreter, a fresh
`HOME`, a dead `RMX_MODEL_SOCK`, and `HF_HOME` pointed at the real model cache in offline mode.
Nine mutations were each restored with `git checkout -- src tests` and `__pycache__` was
cleared after each. `git status` was clean at the end. The only contact with live processes was a
read-only `lsof` of the four `rmx mcp` processes and the hub.

rel: evidence-for -> [[impl-bug-110-snapshot-lock]]
rel: amends -> [[bsd-bug110-r1-60893d3]]

## r1 findings, re-verified {#r1-status}

| r1 | status | evidence |
|---|---|---|
| #b-1 | **CLOSED** | `test_save_state_embeds_memories.py:50-86` (`_READER`, `_read_snapshot` at :68) read a forced snapshot in a child process. 10/10 runs: 18 passed, 0 skipped (`bsd-bug110-r2-savestate-x10.log`). Mutation MA fakes the drain's result dict so no vectors are written; it is killed by all 3 dense tests. The bug-108 registry row is not updated in this range (see #m-2-r2). |
| #s-1 | **CLOSED** (doc) | The inventory row is corrected. The bug-113 facts are re-measured at HEAD (see [[#bug113-facts]]). |
| #s-2 | **CLOSED** | M2 (`if False:` instead of the returncode check), M4 (drop `-p`) and M5 (drop `timeout=`) are each killed by a new test in `test_bug110_snapshot_keeps_lock.py:91-145` (`bsd-bug110-r2-mutations.log`). |
| #m-1 | **CLOSED** | `_rebuild_slot_from` is deleted. No references remain in `src/`, `tests/` or `docs/`. |
| #m-2 | **CLOSED** | `_CP = "/bin/cp"` at `daemon.py:200`. |
| #m-3 | **CLOSED** (code), guard unpinned | `close()` now sits in a `finally` at `daemon.py:2873-2882`. Mutant M6 moves it back inside the `try`; it survives `test_daemon_rotation.py`, `test_slot_rotation_drift.py` and the bug-110 file (16 passed). See #s-2-r2. |

The remedy family run passed: 67 passed across the bug-110, save-state, rotation, snapshot-tier,
snapshot-policy, replica-symlink, replica-merge, slot-drift and CLI-rotation files
(`bsd-bug110-r2-family.log`).

## Point (1): bug-112, the mechanism is named {#bug112-mechanism}

The mechanism is DuckDB's `duckdb.connect()` database-instance cache, pinned by the
process-lifetime `search._REPLICA_CACHE`. It is not a stale page cache, and it does not involve
the same inode.

Primitive, DuckDB 1.5.2 (`bsd-bug110-r2-duck-instance-cache.log`):

1. Open `c1 = connect(f, read_only=True)`; it sees 1 row.
2. `os.replace` a new file over `f` (new inode, 5 rows).
3. Open `c2 = connect(f, read_only=True)` while c1 is still open. **c2 sees 1 row.** DuckDB
   hands back c1's DatabaseInstance, which still holds the unlinked old inode. Two variants
   confirm the cache: a different config raises "same database file with a different
   configuration", and a different spelling of the path (`dir/./snap.duckdb`) also gets the
   stale instance.
4. After every in-process connection closes, the next open sees 5 rows.
5. `ATTACH ... (READ_ONLY)` from a `:memory:` connection does NOT go through this cache: it
   sees the new file. So `_MemMirror.refresh` is unaffected.

In the test (`bsd-bug110-r2-stale-probe.log`, `-probe2.log`):

- `verbs.memory_partition(root)` (`verbs.py:246`) calls `search.cached_replica(root)`
  (`search.py:38-73`). That opens a read-only Store on `catalog.read.duckdb` and caches it for
  the life of the process.
- `lsof -p <self>` then shows fd 3r on inode **454513124**. The forced snapshot installs inode
  **454513161**. The fd stays on 454513124, so these are **different inodes**. The summary's
  "same inode" is wrong.
- A new in-process `Store(root, read_only=True)` reads the pre-embed image: pending
  `[(1, other_note), (3, savestate_a)]`. A child process reads `[]`.
- Calling `cached_replica(root)` again re-stats the file, sees the new signature, closes the
  cached Store and reopens. After that, both the cache and a fresh in-process Store read `[]`.
  Dropping the cache entry by hand also leaves 0 duckdb fds.
- Why "no leaked Python duckdb connection" was found: `gc.get_objects()` reported
  `DuckDBPyConnection=0` while lsof showed the fd open. A pybind object is not tracked by gc.
  Counting `Store` objects with a live `_conn` found it at once.

**Product impact, measured where I could:**

- **MCP, hub, federated search: not a defect today.** Their only in-process snapshot reader is
  `cached_replica`. It re-stats on every call and returns fresh data (measured above). A
  read-only `lsof` of the four live `rmx mcp` processes (up 2 h to 27 days) and the hub found
  **0** duckdb fds, so none of them pins a replaced 765 MB snapshot right now.
- **Latent: any second in-process open of the snapshot path while a cache entry is outdated.**
  That open gets the cache's old image, and it keeps getting it until the next `cached_replica`
  call. The sites are listed below.
  - CLI `_read_store()` / `_replica_store()` (`cli.py:680-700`) after a `memory_partition` call
    in the same process, as in `memory_recall` (`cli.py:11915`). These are short-lived and
    read-only, so the staleness is bounded to one snapshot interval, the lag a reader has
    anyway.
  - The reverse case, by the same primitive (not driven end to end): if a non-cache connection
    such as `_replica_store`'s, which `atexit` keeps open, holds an old image when
    `cached_replica` refreshes, the cache records the NEW signature over OLD data. It then
    stays stale for as long as that other connection lives.
  - Daemon `_open_read_store` file-backed reads (`daemon.py:2451`): an op that opens while an
    overlapping op still holds the previous snapshot gets the previous image. This is bounded
    by the op's duration and inferred from the primitive, not measured on a daemon.
- **Disk:** an idle long-lived process with a cache entry pins each replaced snapshot inode
  (765 MB on this project's live store) until its next `cached_replica` call. This is not
  occurring live now (0 fds).

**For the bug-112 row:** severity low and latent. Root cause: the DuckDB connect() instance cache
plus the process-lifetime replica cache. Fix candidates:

1. Have `cached_replica` serve every in-process snapshot read (one opener per path).
2. Or route the CLI reads through it.
3. Or open the snapshot via `ATTACH` from `:memory:`, which bypasses the instance cache (measured).

## Point (2): does the child-process read weaken the tests? {#point2}

It does not weaken them against the defect they exist for: MA (drain skipped, result faked) is
killed by all three. The child imports the same tree, because it inherits `PYTHONPATH` and
`conftest.py` refuses a run without it.

It does weaken them against a stale snapshot, which is the failure mode bug-112 itself
describes. See #s-1-r2.

## Point (3): bug-113 facts, confirmed at HEAD {#bug113-facts}

Source: `bsd-bug110-r2-bug113-merge.log`, from a real `serve_forever` daemon in an isolated
HOME.

- **Schema drift.** `replica_merge {"dry_run": true}` on a freshly ingested store returns
  `ok:false`, `merge build: BinderException('table entities has 13 columns but 14 values were
  supplied')`. The missing column is **`vectors_partition`**. Store adds it (`store.py:271`,
  plus migrations at `:1283`/`:1345`), but `duckdb_catalog.init_catalog` (`duckdb_catalog.py:249`),
  which `merge_slots` builds its target with, does not have it. Measured: 14 vs 13 columns.
- **Leaked connection.** `merge_slots` (`replica_merge.py:112/120` connect, `:128-129`
  `ATTACH a/b`) has no try/finally. On the exception, `con` and both ATTACHes stay live, and
  `_op_replica_merge`'s failure-path reopen (`daemon.py:5485-5494`) logs `merge: failed AND
  reopen failed: ... Unique file handle conflict: Cannot attach "catalog" ...`. `d.store` is then
  left as a Store whose `init()` failed.
- **Slot unlocked.** A second process gets `OPEN` on `catalog.A.duckdb` immediately after the
  op. It is `REFUSED` again 4 s later (with 1-2 s ticks), once a lazy reconnect re-takes it.
- **Also true, by reading:**
  - `_op_replica_merge` never passes `dry_run` to `merge_slots`, so a dry run builds the full
    merge into `catalog.merge.tmp.duckdb` and then deletes it. This is by design according to
    the comment.
  - The successful-swap path's `_shutil.copy2(A, B)` (`daemon.py:5541`) runs while the writer
    is closed, so it is not a bug-110 site.
  - The command is reached through `rmx replica merge`, which requires a daemon. Nothing fences
    it.

## Point (4): ten runs {#point4}

`tests/test_save_state_embeds_memories.py` × 10 gave 18 passed in every run, 0 skipped, 20-73 s
per run (`bsd-bug110-r2-savestate-x10.log`).

## Findings {#findings}

### SKETCHY: two of the three rewritten tests pass on a snapshot frozen before the rows existed {#s-1-r2}

**File:** `tests/test_save_state_embeds_memories.py:181` (`pending == []`), `:201`.
**What:** Both tests now assert only that the snapshot holds no vectorless memory rows. They never
assert that the memory rows ARE in the snapshot they read.
**Measured:** mutant MB makes `_snapshot_catalog` copy only when no snapshot exists, so the
snapshot stays frozen at the empty store from daemon boot. The op still returns `snapshot_path`.
Result: `test_no_memory_row_is_left_without_a_vector` and `test_a_bare_ingest_gmd_as_memory_embeds_too`
**pass**. Only the recall test fails, with `None == 'savestate_recallme'`. The old writer-slot
read could not be stale. The child read can be, and a stale image is exactly the class bug-112
names.
**Failure scenario:** a regression makes the forced snapshot leave an old image in place, or
read one (any bug-112 variant). Then "no memory row is left without a vector" holds vacuously
on a catalog with zero memory rows. This file's own docstring says the whole bug was a check
that passed on a half-save.
**Fix:**
1. Have the child return the names of the `kind=memory` rows in the partition, alongside
   `pending`.
2. Assert that `{savestate_a, other_note}` and `{hook_written_note}` are present AND that
   `pending == []`.
3. Re-run MB: both tests must fail.

**Pattern match:** YES. [[bsd-impressions#imp-consolidated-r12]] (`imp-zero-on-both-sides`:
"fixed, 0 now" vacuous on both sides).

rel: contradicts -> [[claude#system-dependent-tests]]

### SKETCHY (escalated from MEH): the #m-3 `finally` is unpinned {#s-2-r2}

**File:** `src/refmatrix/daemon.py:2873-2882`.
**What:** M6 moves `self.store.close()` back inside the `try` that the CHECKPOINT raises from. It
survives every rotation test (16 passed). No test makes the pre-copy CHECKPOINT fail.
**Failure scenario:**
- The bug-110 drop is now moot here, because the copy runs out of process.
- A skipped close still matters. Suppose the CHECKPOINT raised because the DuckDB instance is
  invalidated. The following `Store(...).init()` on the same path then gets the invalidated
  instance back from the connect() cache shown in [[#bug112-mechanism]]. The repair fails, and
  only the remedy's `finally` prevents it.
**Fix:** a `_bootstrap_rotation_if_needed` test with one slot missing and a store whose
`_connect().execute("CHECKPOINT")` raises. Assert that the store was closed before the copy
and that the clone completed.
**Pattern match:** YES. [[bsd-impressions#imp-remedy-guards-unpinned]]. This is its third
sighting (bug-109 r4, bug-110 r1 #s-2, now), so MEH escalates to SKETCHY.

### MEH: bug-112's recorded facts are wrong, and the registry rows are still unwritten {#m-1-r2}

**File:** `workflow/implementation_summaries/bug-110-snapshot-lock.md#round-1` ("Same inode",
"mechanism is unnamed"); `tests/test_save_state_embeds_memories.py:75` ("mechanism not yet
named").
**What:**
- The held inode differs from the installed one: 454513124 vs 454513161.
- The mechanism is the one named in [[#bug112-mechanism]].
- A row written from the summary would record a false fact and send the next reader hunting
  for a page cache.
**Fix:** write bug-112 from [[#bug112-mechanism]] and amend the summary and the docstring to
point at it.

### MEH: r1 #m-3's registry half is still open {#m-2-r2}

**File:** `workflow/bug_registry.md`.
**What:** The clone's branch predates 753ab12, so the bug-108 to bug-111 rows do not exist on
it. The range writes none of these:
- bug-108 root cause (= bug-110), fixed-by;
- bug-110 status;
- bug-112;
- bug-113.

These rows are anchored to the merge, as the caller stated. Recorded here so the merge is not
mistaken for closing it.

## Verdict {#verdict}

DIRTY: 4 findings (0 BULLSHIT, 2 SKETCHY, 2 MEH).

- Every r1 finding is closed at its cited lines, and each named mutant is killed.
- 10/10 runs of the save-state file are green. The family run gave 67 passed.
- No BULLSHIT, so nothing blocks the merge. #s-1-r2 is a short test change, and it should land
  before bug-112 is fixed: those two tests are the ones that would fail to notice it regressing.

rel: contradicts -> [[claude#system-dependent-tests]]
