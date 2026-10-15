---
gmd: "0.1"
id: bsd-bug105-hotfix-r3-27b3653
title: "bug-105 hotfix r3: #b2-2 is closed and #b2-1 is mostly closed (pre-flush and final flush+repair under the lock, no deadlock with the real _FairLock, a concurrent writer leaves 0 missing / 0 misplaced bits), but merge's end-of-merge binding rebind still runs outside the lock, and merge never remaps fragment bits of collided ids, so its repair reports them dropped"
severity: BULLSHIT
plan: bug-105
task: hotfix-27b3653-r3
tags: [bsd, audit, bug-105, fragments, bitmap, partition, repair, merge, lock, mutation]
---

# ch-bsd findings r3: bug-105 r2 remedies (27b3653) {#root}

**Commit:** 27b365347e2a60c38bbff6fe76b7fc80601a8c24
- Range: a434f51..27b3653.
- Clone: `/Volumes/littlebig/refmatrix-bug105`, branch `bug-105-fragment-partition`.
- Code under audit: the r2 remedies in 27b3653.

**Date:** 2026-10-14 (written 2026-10-14T14:11:33-0700)
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed (27b3653):** 6
- Source: store.py, daemon.py, cli.py.
- Tests: `tests/test_fragment_repair_audit_r2.py`.
- Docs: the r1 and r2 reports.

rel: amends -> [[bsd-bug105-hotfix-r2-4fb803b]]
rel: amends -> [[bsd-bug105-hotfix-20c5ab4]]

## Evidence base {#evidence}

All logs are under `workflow/review-output/` in the clone.

**Interpreter and import path**
- Every run used `PYTHONPATH=<clone>/src` with `.venv-eval/bin/python`.
- `refmatrix.__file__` resolved to `/Volumes/littlebig/refmatrix-bug105/src/refmatrix/__init__.py`. This is recorded in `bsd-bug105-r3-family-head.log` and asserted by probe P0.

**Test runs**
- **Family at HEAD:** 77 passed (`bsd-bug105-r3-family-head.log`), and 77 passed again after the mutation batch and the `__pycache__` clear (`bsd-bug105-r3-family-post-mutation.log`). Files:
  - `test_fragment_partition_scope`, `test_fragment_repair_audit`, `_r2`
  - `test_partition_merge`, `test_partitions`
  - `test_bigop_nonblocking`, `test_snapshot_policy`
  - `test_plan4_remedy`, `test_ingest_partition_yield_race`
- **Wider set:** 304 passed and 12 failed (`bsd-bug105-r3-wide.log`). It covered every test file matching fragment, partition, merge, repair, snapshot, bitmap, purge, link, save_state, duckdb or store.
  - All 12 failures are in `test_plan4_remedy_r2` and `_r3` (launchctl plist rendering).
  - Each one is the dev-tree guard refusing to render a plist because `~/bin/rmx` under this PYTHONPATH imports the clone's git tree.
  - The hotfix has no launchctl hunk (`git diff a434f51..27b3653 -- src` touches only the merge, repair, fragment-cache, tick-guard, CLI print and op-registry hunks).
  - The same two files pass with the base tree exported outside any git tree (`bsd-bug105-r3-plan4-at-base.log`). So these failures are environmental, not this change.
  - The known WAL-lock flake (`test_save_state_embeds_memories`) passed in this run.

**r3 probes** (`bsd-bug105-r3-probe-tests.py.txt`; results in `bsd-bug105-r3-probes.log`, `-probe-p7.log` and `-probe-p8.log`): 6 pass and 3 fail. P3, P4 and P7 fail; each is a finding below.
- **P1:** merge with the REAL `daemon._FairLock` (not re-entrant) runs in a thread with a 30 s join. It completes, every `flush_fragments`, `_clear_fragment_caches` and `repair_fragments` call sees `lock.locked()`, and the lock ends released.
- **P2:** a concurrent writer thread takes the `_FairLock` and writes to `dst` (through `with_partition`) and to home, against a chunk=1 merge of 40 collisions. Afterwards every `entity_links` bit is in its entity's partition row: 0 missing and 0 misplaced.
- **P5 and P6:** a REAL daemon subprocess on a short mkdtemp root, with HOME, RMX_HOME and RMX_MODEL_SOCK isolated and RMX_SHARED_MODELS=0. `fragments_repair` reaches:
  - the sync `partition_merge` RPC result;
  - the async job result (`job_status`);
  - the `rmx partition merge -y` output (`fragments repair: … dropped_dead_concept=… links_skipped=…`, plus the manifest path);
  - `rmx daemon job <id>`.
- **P8:** on the same daemon-up path, `rmx repair-index --fragments` dry-run → apply → dry-run prints every counter, and rmxd.log carries `dropped_dead_concept`, `links_skipped` and `unread_dirs`.

**Mutations:** 14 mutants; 5 killed, 9 survive (`bsd-bug105-r3-mutations.log`, script `bsd-bug105-r3-mutate.py.txt`). Each mutant was reverted with `git checkout -- <file>`, and the loop ended with `RESTORED clean`. `__pycache__` was then cleared under `src/` and `tests/`, and the tree was left at 27b3653 with a clean `git status`.

**Isolation:** no live store, live socket, main-tree file or deployed `rmx` against a real store was touched. Both probe daemons were stopped, and no `r3b-` process remains.

## Lock and deadlock analysis {#deadlock}

The question was whether any path can deadlock on `_FairLock` (daemon.py:200), which is not re-entrant. No reachable path can.

**Entry: nobody calls `merge_partition` while already holding `_store_lock`**
- `merge_partition` has three callers: `cli.py:4228/4275` (offline, `lock=None`, so `nullcontext`) and `daemon.py:4094/4120` (`lock=d._store_lock`).
- The op dispatcher (`_handle`) submits handlers to the pools without taking `_store_lock`.
- `_op_partition_merge` takes no store lock itself. The only lock it takes is `_jobs_lock` inside the progress callback.

**Inside the merge: no `with _lk:` is ever nested**
- Every `with _lk:` block runs in sequence: pre-flush, partition lookup, classify, counts, the per-chunk collisions and reparents, the tail, then the final flush + repair.
- `_tick` (the progress callback) runs between blocks, outside them.
- Nothing under the final block takes a lock. It calls `flush_fragments`, then `repair_fragments`, which calls `transaction()` and, on exit, `has_dirty_fragments` → `flush_fragments` → `_clear_fragment_caches`. The Store holds no reference to the daemon lock (grep of store.py).

**Confirmed by tests**
- P1 completes with the real `_FairLock`.
- `test_bigop_nonblocking` uses a non-re-entrant `threading.Lock` for both the sync and async merges, and also completes.
- `test_fragment_repair_audit_r2` uses an RLock stand-in (`_RecLock`). That test could NOT see a nesting bug: P1 is the test that can.

**`_op_repair_fragments`** holds `_store_lock` and calls `repair_fragments`, which re-acquires nothing.

**Residual: the docstring is wrong about the lock.** The merge docstring still says `lock` is "any re-enterable context manager, e.g. the daemon's `_store_lock`". `_store_lock` is NOT re-enterable. See [[#m3-2]].

## r2 status {#r2-status}

| r2 id | Status | Evidence |
|-------|--------|----------|
| #b2-1 merge fragment steps outside the lock; clear-before-repair resurrects unlinks | **partial (mostly closed)** | The pre-flush (store.py:1697-1700) and the final flush + repair (:1960-1962) are under `_lk`. M19 (pre-flush unlocked) and M18 (final block unlocked) are both killed by the adopted lock test. The final step flushes instead of clearing, and M16 (back to clear) is killed by the adopted interleaved-unlink test. P1 shows no deadlock with the real lock, and P2 shows a concurrent writer is neither lost nor misplaced. **Residual:** the binding rebind just before the final block (:1950-1952) still runs outside the lock. The r2 fix text named it ("rebind + flush + repair"). See [[#b3-1]]. |
| #b2-2 dead-concept predicate reads `concepts` only | **closed** | `concept_ids.update(ent_part)` (:4351). The adopted probes pass. M20 (revert to concepts-only) is killed by both adopted tests. The docstring was corrected (:4334-4336). A sibling remains, in merge rather than the predicate: [[#s3-1]]. |
| #s2-1 counters not printed; merge discards the repair report | **closed (MEH residual)** | merge returns `fragments_repair` (M21 killed). `rmx partition merge` prints the counters on the daemon-up sync path (P6). The async job result and `rmx daemon job` carry them (P5, P6). `repair-index --fragments` and its rmxd.log line print all counters (P8). **Residual:** for a merge, rmxd.log logs nothing about the repair or its manifest; the sync path logs only `merge-progress`, and async logs `merge-done job=…` ([[#m3-2]]). Every new print is unpinned (M22-M25 survive, [[#s3-2]]). |
| #s2-2 surviving mutants | **open** | M1 (tick guard), M11 (links_skipped), M12 (SQLite unlink-all) and M14 (entity_links canonical names) all survive at 27b3653. 27b3653 neither addresses nor justifies them. See [[#s3-2]]. |
| #m2-1 residual recurrence and layout gaps | **open (known)** | 4fb803b..27b3653 does not touch `purge_entity`, the loose `fragments/*.rb64` files, or merge atomicity. One more layout gap was found: [[#m3-1]]. |
| #m2-2 known m-3 / m-4 | **open (known), not blockers** | Unchanged. |

## Findings {#findings}

### BULLSHIT (escalated): merge still rebinds the shared writer's partition outside the writer lock {#b3-1}

**File:** src/refmatrix/store.py:1950-1952. Blame: e0bab03e, 2026-06-04, so the rebind predates this hotfix. 27b3653 did not move it.

```python
if self._partition_name == src_name:
    self._partition_name = dst_name
    self._partition_id = dst_id
```

**What:**
- This runs after the tail `with _lk:` block exits and before the final `with _lk:` block.
- On the daemon both `_op_partition_merge` paths run it on a pool thread, without `_store_lock`.
- The r2 prescription for #b2-1 was explicit: "wrap the end block (rebind + flush + repair) in `with _lk:`". 27b3653 wrapped the flush and the repair but not the rebind, and the commit message does not mention it.

**Why it's bullshit:**
- This is the bug-098 shape: the shared writer's partition binding moves under an in-flight write. Any op holding the lock can observe the two assignments separately: name=dst while id=src.
- Since 0d05525 the fragment cache is keyed on `(partition_id, partition_name)`, so that half-state creates a hybrid cache binding. An op that links in that window caches bits under `(src_id, 'dst')` and flushes them under the dropped `src_id`.
- The condition `self._partition_name == src_name` is true when the daemon's home partition is SRC. It is also true while another op is inside `with_partition(src)`, and `with_partition` re-creates a dropped partition row by name.

**Evidence:**
- Probe P3, `test_p3_home_binding_rebind_happens_under_the_writer_lock`, binds the store to SRC and records `lock.locked()` when `_partition_name` becomes `dst`. It got `[False]` (`bsd-bug105-r3-probes.log`).

**Fix:**
- Move the three lines inside the final `with _lk:` block, ahead of `flush_fragments()`.
- Adopt P3.
- Effort: a 3-line move.

**Pattern match:** YES. This is the 7th instance of the binding class (`#imp-binding-is-every-cache`; r2 #b2-1 was the 6th). It is escalated from SKETCHY under the 3+-occurrence rule.

**Scope of the block:**
- It is reachable ONLY through `rmx partition merge`, sync or `--async`, against a live daemon.
- It does not block git-merging the branch, deploying, or running `rmx repair-index --fragments`; see [[#verdict]].
- It does block closing #b2-1, and it blocks any live `partition merge`.

### SKETCHY: merge never remaps fragment bits of collided ids, so its repair reports remapped bits as dropped and deletes fragment-only ones irreversibly {#s3-1}

**File:**
- src/refmatrix/store.py:1777-1849: the collision loop remaps `entity_links`, `linkage_evidence`, `concepts` and `memory_content` from `src_eid` to `dst_eid`, but never touches the fragment bits.
- :1960-1962: the final `repair_fragments`.

**What:**
- A collided SRC entity is deleted, and its id lives on in packed fragment bits, either as the concept (the high half) or as the entity (the low half).
- The post-merge repair sees those ids as dead. It counts the bits as `dropped_dead_concept` or `dropped_dead` and writes them to the manifest under the dead SRC id.
- If the bit also has an `entity_links` row, that row was remapped, so the union re-adds the DST-id bit through `added_from_links`. Nothing is lost, but the report says "dropped".
- A fragment-only bit (no `entity_links` row) is deleted. The manifest holds it under the dead SRC id, so a restore cannot bring it back to the DST id it belongs to.

**Why:**
- This is the #b2-2 failure mode again, now in merge: the operator-facing drop count and the manifest describe live, remapped data as dead.
- The merge's purpose is the `memory-<project>` → `<project>` consolidation. There, collisions (`entities_merged`) are the bulk of the work, so `dropped_dead_concept` will be large and almost all of it false.

**Evidence:**
- **P6 (daemon-up CLI, one collided concept, no fragment-only bits):** `dropped_dead_concept=1` and `added_from_links=1`, and a manifest was written. Nothing was actually lost.
- **P7 (`bsd-bug105-r3-probe-p7.log`):** one live link plus one fragment-only link under a collided concept gave `dropped_dead_concept=2` and `added_from_links=1`. The DST row holds only `_pack(dk, e)`, so the fragment-only `_pack(dk, f)` is gone.

**Pre-existing?**
- Before 4fb803b the merge did no fragment repair. Those bits stayed under the dead SRC id, where no query by the DST concept can reach them, so this did not newly make anything unreachable.
- What is new: the repair now makes the loss permanent (it deletes the bits and keeps only an unrestorable manifest record), and it reports remapped bits as drops.

**Fix:**
- Apply the collision map (`src_eid → dst_eid`, on both halves) to every fragment row under the lock before the final repair, or pass the map into `repair_fragments` so it remaps instead of dropping.
- Adopt P7.
- Effort: about 15-20 lines.

**Pattern match:** YES. The remedy implemented a narrower fix than the defect: r1 #s-1 was "merge leaves fragment rows inconsistent", and the remedy re-homed partitions but did not remap ids. This matches the 0916 note, "prescriptions narrower than the defect".

### SKETCHY: the r2 survivors are still alive, and every #s2-1 print is unpinned {#s3-2}

**File:** tests/test_fragment_repair_audit*.py, tests/test_partition_merge.py

**What:** 14 mutants against the HEAD family of 77 tests (`bsd-bug105-r3-mutations.log`):
- **Killed (5):**
  - M16: final clear instead of flush.
  - M18: final block unlocked.
  - M19: pre-flush unlocked.
  - M20: concepts-only predicate.
  - M21: `fragments_repair` set to None.
- **Survive, r2 carry-overs (4):**
  - M1: daemon tick guard reads `_dirty_fragments`.
  - M11: `links_skipped` never incremented.
  - M12: SQLite unlink-all.
  - M14: no `_canonical_verb` on the `linkage_types` names.
- **Survive, new (5):**
  - M5: no pre-flush. This is now near-equivalent: the final flush + repair re-homes dirty SRC-binding bits, so a test would have to construct a dirty bit whose id the merge remaps.
  - M22: the `partition merge` repair print is disabled.
  - M23: `repair-index` loses `dropped_dead_concept` and `links_skipped`.
  - M24: `repair-index` loses `unread_dirs`.
  - M25: the daemon log loses the new counters.

**Why:**
- The counters are the operator's only window into a destructive repair. r2 ranked "the counts they read are incomplete" as SKETCHY, and today nothing stops that regression from returning.
- M1, M11, M12 and M14 were reported in r2 with concrete fixes, and 27b3653 neither addresses nor justifies them.
- If they are still unaddressed at r4, they become a third sighting, and the finding escalates to BULLSHIT.

**Fix:**
- Adopt P5, P6 and P8 (they kill M21 on the daemon path, M22, M23 and M25).
- Apply the r2 fixes for M1, M11, M12 and M14: a tick-body test with only a non-home binding dirty; one `entity_links` row with an unknown partition; one known-partition foreign bit in the SQLite test; one raw-named linkage type.

### MEH: SQLite merge strands a SRC fragment file whenever DST already holds that linkage {#m3-1}

**File:** src/refmatrix/store.py:1925-1945. The "Existing target: best-effort skip" branch predates the hotfix.

**What:**
- When `fragments/<dst>/<L>.rb64` exists, the SRC file stays put and `rmdir` fails.
- After the SRC row is dropped, the repair reports `fragments/<src>` in `unread_dirs` and never re-homes it.
- P4 shows `unread_dirs=['…/fragments/src']` after a plain merge.
- The bits that only that file holds stay stranded.

**Why MEH:**
- DuckDB is the production backend, and SQLite only autodetects for legacy stores.
- The leftover directory is reported, not deleted.

**Fix:** Have the SQLite merge leave the shared-linkage file for the repair to union, by reading SRC's dir before the partition row drops, rather than skipping it.

### MEH: merge's repair is invisible in rmxd.log, and the merge docstring is stale {#m3-2}

**rmxd.log is silent about the merge's repair.**
- After a merge it shows only `merge-progress …` and `merge-done src2->dst job=…` (P5 output). There is no repair counter and no manifest path.
- The r2 fix asked merge to "log its manifest path".
- The sync CLI and `rmx daemon job` do show the report, but a `--async` operator who never polls has no record of it.

**The `merge_partition` docstring is stale in two places.**
- "Returns" omits `fragments_repair`.
- It still calls `lock` "any re-enterable context manager, e.g. the daemon's `_store_lock`", but `_FairLock` is not re-entrant. No path nests it ([[#deadlock]]), yet the doc invites a future nested `with _lk:` that would hang the daemon.
- `test_fragment_repair_audit_r2._RecLock` is re-entrant too, so it would not catch that nesting.

**Fix:**
- Add `d._log(f"merge-repair {src}->{dst} {res['fragments_repair']}")` on both paths.
- Correct the docstring.
- Make `_RecLock` non-re-entrant, or adopt P1.

## Verdict {#verdict}

**DIRTY: 5 findings (1 BULLSHIT, 2 SKETCHY, 2 MEH).** r2's 6 ids:
- 1 closed: #b2-2.
- 1 closed with a MEH residual: #s2-1.
- 1 partial: #b2-1, residual [[#b3-1]].
- 1 open: #s2-2.
- 2 known-open: #m2-1, #m2-2.

**Is merge → deploy → per-store backup → dry run → apply safe?** Yes for that sequence, meaning the hotfix with `rmx repair-index --fragments`.
- **What the repair path is now:**
  - It runs under `_store_lock` (`_op_repair_fragments`).
  - It uses the corrected predicate.
  - It prints every counter in the CLI and in rmxd.log (P8).
  - Its dry run does not write.
  - It cannot deadlock.
- **Why the open findings do not touch it:** [[#b3-1]] and [[#s3-1]] are reachable only through `rmx partition merge`.
- **The sequence:**
  1. `merge --no-ff`, then deploy.
  2. Per store, back up the ACTIVE slot (`catalog.<A|B>.duckdb`, named by `active`). The manifest records drops only, never moves, so it is not a restore point.
  3. Run `--dry-run`. Read `dropped_dead`, `dropped_dead_concept`, `links_skipped` and `unread_dirs`. Expect `dropped_dead_concept` to equal the dead-concept-entity count (410 on the refmatrix probe copy, NOT 4,439).
  4. Apply.
  5. A day later, dry-run again. A non-zero `moved` measures the m-3 regrowth.
- **Do NOT run `rmx partition merge` on any live store** until [[#b3-1]] (a 3-line move) and [[#s3-1]] are fixed. If a merge cannot wait, first restart the daemon bound to a partition other than SRC, and expect `dropped_dead_concept` to roughly equal the collided bits.

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[claude#before-commit]]

## Ledger lines (for the orchestrator to apply) {#ledger}

last_run.log:

```
2026-10-14T14:11:33-0700 commit=27b3653 verdict=DIRTY findings=5 (1B/2S/2M) report=2026-10-14-1411-bug105-hotfix-r3-rebind-outside-lock-and-unremapped-collision-bits-27b3653.md
```

INDEX.md row:

```
| 27b3653 (a434f51..27b3653, bug-105 hotfix r3; written 2026-10-14T14:11) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 5 (1B/2S/2M); r2 6: 1 closed / 1 closed-residual / 1 partial / 1 open / 2 known-open | [[bsd-bug105-hotfix-r3-27b3653]]. #b2-2 closed (M20 killed). #b2-1 mostly closed: pre-flush + final flush/repair under _lk (M18/M19/M16 killed), no deadlock with the real non-reentrant _FairLock (P1), concurrent writer 0 missing/0 misplaced (P2). B (escalated, binding class #7): merge's end rebind of _partition_name/_partition_id (store.py:1950, pre-existing e0bab03) still outside _lk though r2 prescribed it (P3 [False]). S: merge never remaps fragment bits of collided ids, so the repair reports remapped bits dropped and deletes fragment-only ones irreversibly (P6 dropped_dead_concept=1 with no loss; P7 2 reported, 1 lost). S: survivors M1/M11/M12/M14 still alive + M22-M25 (every #s2-1 print) unpinned; 14 mutants, 5 killed. M: SQLite merge strands src file on a shared linkage (P4); rmxd.log silent on merge's repair, docstring calls _FairLock re-enterable. Deploy + repair-index sequence SAFE; no live partition merge until #b3-1/#s3-1. |
```

IMPRESSIONS.md bullets:

```
- A prescription with a parenthetical list gets implemented minus the item that was already there: r2 said "rebind + flush + repair" under the lock; 27b3653 locked the two new steps and left the June rebind outside (bug-105 r3 #b3-1). Check every item of a list fix, not the headline.
- A re-entrant stand-in lock in a test cannot see a nested-acquire deadlock; probe lock fixes with the production lock class (_FairLock), never an RLock (bug-105 r3 #deadlock).
- A repair that classifies ids as dead must run after every id REMAP, not just every partition move: merge remaps entity_links but not fragment bits, so its repair "drops" live remapped bits (bug-105 r3 #s3-1).
```
