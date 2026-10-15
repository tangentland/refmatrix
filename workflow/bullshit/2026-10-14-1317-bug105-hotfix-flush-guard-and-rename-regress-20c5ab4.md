---
gmd: "0.1"
id: bsd-bug105-hotfix-20c5ab4
title: "bug-105 hotfix: the per-binding cache fixes the leak and the DuckDB repair is sound, but the daemon's periodic flush and transaction exit now only see the home binding, and rename orphans a dirty cache and loses bits"
severity: BULLSHIT
plan: bug-105
task: hotfix-0d05525-20c5ab4
tags: [bsd, audit, bug-105, fragments, bitmap, partition, repair, mutation]
---

# ch-bsd findings — bug-105 hotfix (fragment cache per binding + repair-index --fragments) {#root}

**Range:** a434f51..20c5ab4 (0d05525 cache-per-binding, 20c5ab4 repair) on `bug-105-fragment-partition`, clone `/Volumes/littlebig/refmatrix-bug105`
**Date:** 2026-10-14
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 4 (store.py, daemon.py, cli.py, tests/test_fragment_partition_scope.py)

## Evidence base {#evidence}

- All evidence is in `workflow/review-output/` in the clone. HEAD: 9 of 9 new tests pass (`bsd-bug105-head-green.log`).
- My attack probes are in `bsd-bug105-probe-tests.py.txt`. Results at HEAD are in `bsd-bug105-probes.log` and `bsd-bug105-probes-flushguard.log`. Results at a434f51 are in `bsd-bug105-probes-prefix-a434f51.log`.
- Mutation sweep: 8 mutants against the new test file, 5 killed and 3 survived (`bsd-bug105-mutations.log`). The tree was restored with `git checkout` and `__pycache__` was cleared. `git status` is clean.
- I checked the repaired probe copy (`refmatrix-bug105-probe/root`, read-only; `bsd-bug105-post-probe.log`):
  - 704,103 bits in total.
  - 0 foreign bits, 0 dead-entity bits, 0 rows under a missing partition.
  - 410 bits that exist only in fragments. Every one of them has a dead concept (213 distinct concepts).
- Timing on a scratch copy (`bsd-bug105-timing.log`): dry run 1.2 s, apply 1.1 s.
- No live store, socket or `rmx` was touched.

## Findings {#findings}

### BULLSHIT: the daemon's periodic flush only checks the home binding (regression) {#b-1}

**File:** src/refmatrix/daemon.py:2066-2068; src/refmatrix/store.py:4442
**What:**
- The durability backstop tick is gated on `if self.store._dirty_fragments:`, and its log count uses the same set.
- `transaction()` exit also flushes only on `if self._dirty_fragments:`.
- Since 0d05525 that property returns ONLY the current (home) binding's dirty set.
**Why it's bullshit:**
- Every write op runs under `with d._store_lock, d._st().with_partition(p)`: all `_op_memory_*` ops, forget, flag, and ingest into `sessions-*`.
- Those ops now leave their dirty set under binding `p`. The tick never sees it.
- It is flushed only when the home partition happens to get dirty too, or at `close()`.
- A fast-exit or SIGKILL in that window loses the bits. That is the "links missing from their fragment" class this hotfix exists to repair.
- `_request_snapshot()` after those ops may also publish stale bitmaps. I did not verify whether the snapshot path flushes first.
- Before the fix, the single dirty set was visible to both guards.
**Evidence:**
- `test_periodic_flush_guard_sees_other_binding_dirty`: after a `with_partition("memory-x")` link, `_dirty_bindings()` is non-empty and `_dirty_fragments` is `set()`.
- `test_transaction_exit_flushes_other_binding`: `with s.transaction(): with s.with_partition("other"): link` persists nothing at transaction exit. At a434f51 the same sequence persisted the bit, under the wrong partition.
**Fix:**
- Gate both guards, and the tick's log count, on `self.store._dirty_bindings()`.
- Add a test that drives the tick's body, or the transaction exit, with only a non-home binding dirty.
**Pattern match:** YES. This is the bug-098 shape again: the fix covered the main route but not every reader of the old single-binding assumption.

### BULLSHIT: rename_partition orphans a dirty cache and loses bits (regression) {#b-2}

**File:** src/refmatrix/store.py:1632-1633 (rename), :1070-1078 (binding key)
**What:**
- The cache key is `(partition_id, partition_name)`.
- `rename_partition` rewrites `_partition_name` but does not re-key the cache or flush it first.
**Why it's bullshit:**
- Dirty bits cached under `(pid, old)` are orphaned.
- The next write after the rename loads a fresh `(pid, new)` cache from disk.
- `flush_fragments` then upserts `(pid, old)` first and `(pid, new)` second into the SAME DuckDB row, and the second upsert overwrites the first. Bits are lost.
- On SQLite the orphan is flushed into `fragments/<old>/`, a directory the rename just moved away.
- The pre-fix single cache did not lose these bits.
**Evidence:** `test_rename_with_dirty_cache_keeps_both_bits`:
- At HEAD: `assert {3} == {2, 3}`, so entity `a` is lost.
- At a434f51: passes.
- Same-pid caches split by name are not unique to rename. `merge_partition` (store.py:1928) rebinds name and id and leaves the src cache orphaned in the same way (see [[#s-1]]).
**Fix:**
- In `rename_partition`, call `flush_fragments()` before the rename, or move both cache dicts from `(pid, old)` to `(pid, new)`.
- Do the same for `merge_partition` when bound to src.
- Alternatively, key the DuckDB cache on pid alone.
- Add the probe as a test.
**Pattern match:** YES. The cache key was copied from the binding without walking every place the binding is rewritten. The brief listed rename and merge explicitly.

### SKETCHY: merge_partition never moves persisted fragment rows (recurrence path left open) {#s-1}

**File:** src/refmatrix/store.py:1635-1939
**What:**
- On DuckDB, merge reparents entities and moves `fragments/<src>` directories (the SQLite layout).
- It never touches `bitmap_fragments`. Src rows stay under the dropped `src_id`.
**Why:**
- After every merge, dst reads miss every reparented entity's bits until a repair runs.
- This is the "16 linkages under a partition_id with no partitions row" from the bug-105 row.
- It is pre-existing (it fails at a434f51 too), but the hotfix claims "every rebind", and the repair will be undone by the next merge.
**Evidence:** `test_merge_moves_persisted_fragment_rows` at HEAD returns `{(2,'mentions'): {2}}` with partition 2 already dropped.
**Fix:**
- Inside merge, union the src rows into dst rows under the same lock chunk, delete the src rows, and evict the src binding's cache.
- Or call `repair_fragments(dry_run=False)` scoped to src→dst at the end of merge.

### SKETCHY: the repair keeps dead-concept bits, and purge still creates them {#s-2}

**File:** src/refmatrix/store.py:4271-4361 (repair), :5940-5955 and :6248-6262 (purge concept side)
**What:**
- The repair only tests `bit & mask` (the entity) for existence. A bit whose CONCEPT (`bit >> 32`) is gone is "kept".
- On the repaired probe copy, all 410 bits that exist only in fragments have a dead concept, and 0 have a live concept.
- So the docstring's justification for the union ("74 own + 442 foreign bits exist only in fragments; a plain rebuild would lose real bits") is not supported. That census matched raw `linkage_types` names against canonical fragment names (e.g. `specified_by` vs `specified-by`). After canonicalisation, every remaining fragment-only bit is garbage.
**Why:**
- The union is harmless as a safety net, but it keeps garbage forever.
- Now that bits live in their ENTITY's partition, purging a concept still clears its concept range only in the BOUND partition's fragments. Any entity in another partition linked to that concept keeps a dead-concept bit.
- That is the recurrence path.
**Fix:**
- In the repair, drop bits whose concept id is absent from `entities` into the same manifest, under a separate `dropped_dead_concept` count.
- Make the purge concept-side sweep cover every partition's fragment rows.
- Correct the docstring numbers.

### SKETCHY: three surviving mutants show the repair's tests do not pin key properties {#s-3}

**File:** tests/test_fragment_partition_scope.py
**What:** Three mutants survived:
- m6: the DuckDB `transaction()` around DELETE-all + reinsert was removed.
- m7: `_canonical_verb` on fragment linkage names was removed.
- m8: `_clear_fragment_caches()` after apply was removed.

All 9 tests stay green under each.
**Why:**
- m8 is the dangerous one. Without the clear, the writer's still-cached contaminated bitmaps are re-flushed on the next link to that linkage, which silently undoes the repair on a live daemon. No test performs a write after the repair.
- m6 and m7 are behaviourally correct at HEAD. My probes `test_repair_rolls_back_on_failure` and `test_repair_orphan_partition_row_and_raw_alias` pass. But nothing in the suite would catch their removal.
**Fix:** Add those two probes, plus one test that repairs, then links an entity under the repaired linkage, flushes, and asserts that the foreign bit did not come back.

### SKETCHY: the SQLite repair silently deletes unread fragment files and is not atomic {#s-4}

**File:** src/refmatrix/store.py:4239-4268
**What:**
- `_read_all_fragment_rows` (SQLite) reads only directories named in `partitions`.
- `_write_all_fragment_rows` then `rglob("*.rb64")` and unlinks EVERYTHING. That includes orphan-partition directories and loose pre-partition files whose bits were never read, counted or put in the manifest.
- The unlink-then-rewrite also sits outside any transaction.
**Evidence:** `test_sqlite_repair_does_not_silently_delete_orphan_dir`: a live-entity bit in `fragments/gone-partition/` gives `moved=0 dropped_dead=0 kept=0`, and the file is deleted.
**Why:** The DuckDB backend is the live default, so impact is low. It is still an uncounted loss on a memory path, which [[claude#no-silent-failures]] forbids.
**Fix:** Either read every `*.rb64` (resolve a directory name with no partition by entity ownership, or count it), or refuse the SQLite backend loudly. Write to a temp tree and swap.

### MEH: dry run and manifest edges {#m-1}

- `dry_run=True` still calls `flush_fragments()`. On the daemon that is benign.
- The offline `--dry-run` opens a writer Store through `_store_rw()`, so connect-time migrations can write. "Changes nothing" refers to fragments only.
- The manifest name has 1-second granularity, so two runs in the same second overwrite each other.
- An apply with no drops writes an empty manifest. My timing run produced one.

### MEH: uncounted skips in the repair {#m-2}

- `entity_links` rows with a missing entity (`pid is None`) or an unknown `linkage_id` are skipped by a bare `continue`. Neither count is reported.
- Both are 0 on the probe copy. The memory-path rule still asks for counts.

### MEH: the write-time invariant is unenforced, and per-binding caches are never evicted {#m-3}

- The repair defines truth as "the bit lives in its entity's partition". `link()` still writes into the BOUND partition.
- Any cross-partition link written after the fix becomes a foreign bit again, and the next repair moves it out from under the binding partition's queries.
- A counter or assert at link time, warning when `entities.partition_id != _partition_id`, would make that visible.
- The writer Store keeps a fragment cache for every partition it ever bound, until `close()`. That is bounded by the total fragment size, but it is new resident memory on long-lived daemons.

### MEH: the `_NowPool` fake is reused without a registry row {#m-4}

- `test_repair_fragments_op_through_the_dispatcher` reuses the socketpair + `_NowPool` dispatcher fake.
- `workflow/test_mock_registry.md` row 70 lists only `tests/test_plan4_remedy_r2.py`. Add the new file to that row.

## What holds {#holds}

- Every daemon rebind site in the brief behaves:
  - The mirror at 439/441 and 4916/4920.
  - `_partition_keeping_yield` at 3334, which restores the key.
  - `_NO_PARTITION_ID` at 4937 and 4955/4959. A read under it caches an empty bitmap under `(-1, name)` and never writes.
  - Replica read stores, which are per call and closed.
  - `with_partition` (store 1941/1950).
  - `_merge_fragment_all_partitions`, which flushes inside each binding.
  - `rebuild_index_from_log`, which uses `_clear_fragment_caches` and a final all-binding flush.
- The pid-None binding resolves through `_connect()`.
- `bulk_link`, `link_many` and purge load and dirty under the same binding in one call.
- DuckDB repair:
  - The manifest is written before any change.
  - DELETE-all + reinsert inside one transaction rolls back cleanly on an injected insert failure.
  - Rows under a partition id with no partitions row, and raw alias names, are folded correctly.
  - The dry run leaves `bitmap_fragments` byte-identical.
  - A snapshot is requested only when something changed.
  - The CLI uses `retries=0` with a 600 s timeout.
- The new cache tests fail on the defect: the single-key mutant (m1) fails 9 of 9, and the flush-current-only mutant (m2) fails 2.
- The repair tests kill the links-only, keep-dead and dry-ignored mutants.

## Verdict {#verdict}

DIRTY: 10 findings (2 BULLSHIT, 4 SKETCHY, 4 MEH).

**Safe to deploy?** Not as committed.
- [[#b-1]] is a durability regression on every memory op of every store. The fix is a one-line guard change at two sites.
- [[#b-2]] loses bits on rename. The fix is to flush or re-key in `rename_partition`.

**Safe to run `repair-index --fragments` on live stores?**
- The DuckDB repair algorithm is sound and loses no live bit. It is fast (about 1 s per store on the probe copy), so the lock hold is short.
- Order of operations:
  1. Fix #b-1 and #b-2.
  2. Add the m8 test from [[#s-3]].
  3. Deploy.
  4. Back up each store's active catalog slot. The manifest records only DROPPED bits, not the moved ones, so it is not a restore point.
  5. Run `--dry-run` per store and read the counts.
  6. Apply.
- Running the repair on undeployed code would be re-contaminated by the old cache.
- [[#s-1]] (merge) and [[#s-2]] (dead concepts) do not block the repair. Both leave garbage or recurrence, not loss.

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[claude#before-commit]]
rel: evidence-for -> [[bsd-plan23-17-spec-rereview-32dde06#nb23-1]]

## Ledger lines (for the orchestrator to apply) {#ledger}

last_run.log:

```
2026-10-14T13:17:00-0700 commit=20c5ab4 verdict=DIRTY findings=10 (2B/4S/4M) report=2026-10-14-1317-bug105-hotfix-flush-guard-and-rename-regress-20c5ab4.md
```

INDEX.md row:

```
| 20c5ab4 (a434f51..20c5ab4, bug-105 hotfix 0d05525 + 20c5ab4; written 2026-10-14T13:17) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 10 (2B/4S/4M) | [[bsd-bug105-hotfix-20c5ab4]]. Per-binding cache closes the leak (m1 fails 9/9); DuckDB repair sound (rollback, alias, orphan pid, manifest-first; probe copy 0 foreign / 0 dead-entity). #b-1: daemon periodic flush + transaction exit gate on the HOME binding's dirty set, so with_partition writes (all memory ops) sit unflushed. #b-2: rename_partition orphans a dirty (pid, old) cache; the (pid, new) flush overwrites it and loses bits (passes at a434f51). SKETCHY: merge leaves bitmap_fragments under the dropped src id; repair keeps 410 dead-concept bits (the "fragment-only real bits" were a raw-vs-canonical census artefact); m6/m7/m8 survive (m8 = stale cache re-contaminates after repair); SQLite repair deletes unread orphan dirs uncounted. 8 mutations, 5 killed. |
```

IMPRESSIONS.md bullets:

```
- A cache re-keyed on a binding needs every READER of the old single cache re-audited too: the guard `if store._dirty_fragments` (daemon tick, transaction exit) silently narrowed to one binding (bug-105 #b-1).
- Census numbers that compare raw linkage_types names to canonical fragment names overstate "fragment-only" bits; canonicalise before counting (bug-105 #s-2).
```
