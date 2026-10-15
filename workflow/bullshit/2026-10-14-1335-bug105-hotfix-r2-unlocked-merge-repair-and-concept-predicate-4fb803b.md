---
gmd: "0.1"
id: bsd-bug105-hotfix-r2-4fb803b
title: "bug-105 hotfix r2: #b-1 and #b-2 are closed, but merge now runs a store-wide flush, cache clear and repair outside the writer lock, and the repair's dead-concept test reads `concepts` (kind=concept rows only), so it labels thousands of live typed-edge bits as dropped"
severity: BULLSHIT
plan: bug-105
task: hotfix-4fb803b-r2
tags: [bsd, audit, bug-105, fragments, bitmap, partition, repair, merge, lock, mutation]
---

# ch-bsd findings r2 — bug-105 audit remedies (4fb803b) {#root}

**Commit:** 4fb803ba46cdae72146679a1da1c408bf9443aa8 (range a434f51..4fb803b; clone `/Volumes/littlebig/refmatrix-bug105`, branch `bug-105-fragment-partition`)
**Date:** 2026-10-14
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed (4fb803b):** 3 (store.py, daemon.py, tests/test_fragment_repair_audit.py)

rel: amends -> [[bsd-bug105-hotfix-20c5ab4]]
rel: evidence-for -> [[bsd-plan23-17-spec-rereview-r3-6091648#nb23-r3-1]]

## Evidence base {#evidence}

All logs are under `workflow/review-output/` in the clone.

- **Family at HEAD:** 52 passed across `test_fragment_partition_scope`, `test_fragment_repair_audit`, `test_partition_merge`, `test_partitions`, `test_bigop_nonblocking` and `test_snapshot_policy` (`bsd-bug105-r2-family-head.log`).
- **r1 probes re-run at HEAD** (`bsd-bug105-r2-probes.log`): rename, transaction-exit, merge-rows, rollback and alias all pass. Four r1 probes fail, and none of the four is a regression:
  - `dead_concept` now counts under `dropped_dead_concept`, not `dropped_dead`.
  - The SQLite orphan dir is now left in place and reported, not read.
  - The home-guard probe asserted the OLD guard.
  - The memory-ops probe was already broken (`unknown kind: subject`).
- **r2 probes** (`bsd-bug105-r2-probe-tests.py.txt`; results in `bsd-bug105-r2-probes-only.log`): all 5 fail at HEAD.
- **Scratch-copy run** of the 4fb803b repair on a copy of the probe catalog (`bsd-bug105-r2-copy-repair.log`):
  - dry run 1.2 s, apply 1.25 s;
  - `dropped_dead_concept=4439`;
  - 410 bits actually removed;
  - the manifest lists 4,439 bits, of which 4,025 are still present after the apply.
- **Census on the read-only probe catalog** (`bsd-bug105-r2-concept-census.log`): 4,029 `entity_links` rows have a concept that is a LIVE entity with no `concepts` row:
  - has-part→code: 2,566;
  - memory/doc typed edges (related-to, amends, part-of, depends-on, …): the rest.
- **Mutations:** 17 mutants, 8 killed, 9 surviving (`bsd-bug105-r2-mutations.log`). After every mutant the tree was restored with `git checkout -- src` and `__pycache__` was cleared. `git status` shows only the r1 report as untracked.
- No live store, socket, main-tree file or `rmx` was touched.

## r1 status {#r1-status}

| r1 id | Status | Evidence |
|-------|--------|----------|
| #b-1 periodic flush / txn exit home-only | **closed (code); tick unpinned** | daemon.py:2066 and store.py:4502 use `has_dirty_fragments()`. No other `_dirty_fragments` reader exists outside the cache internals (grep of `src/`). M2 (txn guard back to the home binding) is killed. M1 (the daemon tick guard back to the home binding) SURVIVES: no test drives `_runner`'s tick ([[#s2-2]]). |
| #b-2 rename orphans the dirty cache | **closed** | flush + clear before the rename (store.py:1612-1616). The r1 probe passes. M3 (no flush) is killed. A write cannot be in flight: the daemon op holds `_store_lock` around the rename. |
| #s-1 merge leaves rows under the dropped id | **partial: fixed, and it introduced [[#b2-1]]** | The r1 probe passes (src rows are re-homed). M6 (no final repair) is killed. The new store-wide steps run outside the lock, and clear-before-repair resurrects unlinks. |
| #s-2 dead-concept bits kept; purge recurrence | **partial: wrong predicate, [[#b2-2]]** | The drop exists, but it tests `concepts`, not `entities`. The purge concept/entity sweeps are still bound-partition-only (store.py:5995-6015), so dead bits keep regrowing. The docstring still claims "the only bits removed are those whose entity id is absent" and still cites the 74/442 census. |
| #s-3 surviving mutants m6/m7/m8 | **mostly closed** | m6 = M13, m8 = M15 and the fragment-side m7 are all killed. The `entity_links`-side canonicalisation (M14) survives, along with new survivors M1, M11 and M12 ([[#s2-2]]). |
| #s-4 SQLite deletes unread files | **closed, with a residual** | Unread dirs are left and listed in `unread_dirs`, and only files that were read are unlinked. Residuals: loose top-level `fragments/*.rb64` files are neither read nor reported, and the test never reaches the write path (M12 survives). |
| #m-1 dry-run / manifest edges | **closed (minor residual)** | The dry run no longer flushes (M9 killed) and overlays the dirty cache (M10 killed). Manifests use millisecond names with `-dryrun`/`-applied`, and are written only when something drops. The offline `--dry-run` still opens a writer Store (`_store_rw`). |
| #m-2 uncounted skips | **closed in code, unpinned, unprinted** | `links_skipped` is counted. M11 survives, and neither the CLI nor the daemon log prints it ([[#s2-1]]). |
| #m-3 link writes to the bound partition / caches never evicted | **open (known), not a blocker** | Unchanged. The repair cures the existing damage. Regrowth is visible as `moved > 0` on a later dry run (see [[#verdict]]). |
| #m-4 `_NowPool` registry row | **open (known), not a blocker** | `workflow/test_mock_registry.md` is unchanged in the range. Test hygiene only. |

## Findings {#findings}

### BULLSHIT: merge_partition's new store-wide fragment steps run outside the writer lock, and its clear-before-repair resurrects interleaved unlinks {#b2-1}

**File:** src/refmatrix/store.py:1692-1696 (pre-flush) and :1953-1954 (final clear + repair); daemon.py:4094/4120 (the op does not hold `_store_lock`).

**What:**
- 4fb803b added `flush_fragments()` + `_clear_fragment_caches()` at the top of `merge_partition`, and `_clear_fragment_caches()` + `repair_fragments(dry_run=False)` at the end. All of them sit outside `with _lk:`.
- `merge_partition` deliberately yields the lock per chunk, and both daemon paths (sync and `--async`) call it without holding `_store_lock`. So these steps run concurrently with whatever ops interleave.

**Why it's bullshit:**
- `flush_fragments` temporarily rebinds `self._partition_id`/`_partition_name` to each dirty binding. A concurrent op under the lock reads the swapped binding and writes into the wrong partition. That is bug-098 exactly: "the shared writer's partition binding moved under in-flight writes".
- `repair_fragments` opens `transaction()` on the SHARED connection. Concurrent ops' statements join it, their `_maybe_commit` is suppressed, their post-commit flush is skipped, and the repair's DELETE-all + reinsert races their fragment flushes.
- Even under a lock, the end-of-merge `_clear_fragment_caches()` discards every op's dirty state from the lock-yield gaps. A dirty LINK is restored from `entity_links` by the union. A dirty UNLINK is not: the stale persisted row still holds the bit, `entity_links` no longer does, and the union writes it back.

**Evidence** (`bsd-bug105-r2-probes-only.log`):
- `test_merge_store_wide_flush_and_repair_run_under_the_writer_lock`: called outside the writer lock: `['flush_fragments', '_clear_fragment_caches', '_clear_fragment_caches', 'repair_fragments', 'flush_fragments', '_clear_fragment_caches']`.
- `test_merge_interleaved_unlink_is_not_resurrected`: an unlink in the progress callback (the lock-yield gap) leaves the bit in the home row after the merge: `assert 4294967298 not in {4294967298, 4294967299}`.
- M5 (no pre-flush) and M16 (flush instead of clear at the end) both survive. No test pins either step.

**Fix:**
- Wrap the pre-flush block in `with _lk:`, and wrap the end block (rebind + flush + repair) in `with _lk:`.
- Replace the end `_clear_fragment_caches()` with `flush_fragments()`. `repair_fragments` clears after writing.
- Adopt both probes as tests.
- Effort: about 6 lines.

**Pattern match:** YES. This is the 6th instance of the bug-098 binding class (see `#imp-binding-is-every-cache` and [[bsd-plan23-17-spec-rereview-r3-6091648#nb23-r3-1]]).

### BULLSHIT: the dead-concept drop tests the `concepts` table, which only holds kind=concept rows, so live typed edges are reported dropped and fragment-only ones are deleted {#b2-2}

**File:** src/refmatrix/store.py:4336 (`concept_ids = … FROM concepts`), :4375 (`if (bit >> _CONCEPT_SHIFT) not in concept_ids`).

**What:**
- A bit's high half is the concept_id, and `link()` accepts ANY entity id there.
- GMD `rel:` edges between memories and docs, and `has-part` to code, use the target entity as the concept.
- `concepts` rows are created only for `kind == 'concept'` (store.py:2226-2229).
- r1 [[bsd-bug105-hotfix-20c5ab4#s-2]] said "concept id absent from `entities`". The remedy used the wrong table.

**Why it's bullshit:**
- On the probe copy, 4,439 bits are counted as `dropped_dead_concept` and written to the manifest as dropped. Only 410 are dead. 4,025 of the "dropped" bits are still present after the apply, because the `entity_links` union re-adds them.
- The manifest therefore no longer records what the repair removed. It is wrong as an audit trail, and it is the artifact the operator reads after `--dry-run`.
- Any bit present only in fragments whose concept is a live memory, doc or code entity is DELETED. The docstring promises "a union that loses none".
- The probe copy has 0 such bits, because it was already repaired. Nobody has measured the other live stores, which have never been repaired.
- The docstring was not updated: it still says the only drop is a dead entity.

**Evidence:**
- Copy run: `dropped_dead_concept=4439`, actually removed 410, and "manifest-listed bits still present after apply: 4025".
- Census: has-part→code 2,566, related-to→memory 257, derives-from→doc 136, and so on.
- Probes:
  - `test_repair_does_not_call_a_live_wikilink_target_a_dead_concept` gives `dropped_dead_concept: 1` for a live memory→memory edge.
  - `test_repair_keeps_a_fragment_only_bit_whose_concept_is_a_live_doc`: the bit is deleted (`assert 8589934593 in set()`).
- M7 (`not in ent_part`) leaves all 52 tests green. Nothing pins the wrong predicate, so the fix is free.

**Fix:**
- `if (bit >> _CONCEPT_SHIFT) not in ent_part:` (one token), and drop the `concepts` query.
- Adopt both probes, and correct the docstring.

**Pattern match:** YES. This is a cheap fix (rule 10): the remedy names the r1 finding but implements a narrower or different test than the one prescribed. It matches the 0916 post-deploy note, "prescriptions narrower than the defect".

### SKETCHY: the operator never sees the new counters, and merge throws the repair report away {#s2-1}

**File:**
- src/refmatrix/cli.py:9421-9427: the print shows `dropped_dead` only.
- daemon.py:5389-5391: the log line shows `dropped_dead` only.
- store.py:1954: merge discards `repair_fragments`'s return value.

**What:**
- `rmx repair-index --fragments --dry-run` prints `dropped_dead=0` while the repair drops `dropped_dead_concept` bits. It never prints `links_skipped` or `unread_dirs`.
- A merge now performs a store-wide repair. Its drop counts, `unread_dirs` and manifest path appear in neither the merge result nor the daemon log.

**Why:**
- [[claude#no-silent-failures]] says a skipped or dropped item is counted AND printed.
- The user's plan is "dry-run, read the counts, apply". The counts they read are incomplete.

**Fix:**
- Print every counter in the CLI and in the daemon log.
- Have merge return a `fragments_repair` sub-dict and log its manifest path.

### SKETCHY: surviving mutants leave the remedies' key guards unpinned {#s2-2}

**File:** tests/test_fragment_repair_audit.py, tests/test_fragment_partition_scope.py

**What:** Four mutants survive that matter:
- **M1:** daemon tick guard back to `_dirty_fragments`. r1 asked for a test that drives the tick. `test_periodic_flush_guard_sees_other_binding_dirty` only tests the helper.
- **M14:** no `_canonical_verb` on `linkage_types` names in the `entity_links` pass. There is no data impact on the probe copy (`specified_by` has 0 rows), but a raw-named type would produce a non-canonical row that nothing reads.
- **M11:** `links_skipped` is never asserted.
- **M12:** SQLite unlink-all. The unread-dir test changes no row, so `_write_all_fragment_rows` never runs.

M5 and M16 are covered under [[#b2-1]]. M4 (rename without the clear) and M17 (always-manifest) are benign or equivalent.

**Fix:**
- A test that runs one `_runner` tick body, or extracts the tick into a callable, with only a non-home binding dirty.
- In the SQLite test, add one known-partition foreign bit so that the write path runs.

### MEH: residual recurrence and layout gaps {#m2-1}

- **Recurrence through purge.** `purge_entity`'s concept-side and entity-side sweeps still load only the BOUND partition's fragments. Dead bits in other partitions regrow until the next repair. This is r1 #s-2's second half.
- **Loose fragment files.** Top-level `fragments/*.rb64` files (pre-partition SQLite layout) are neither read nor reported.
- **Merge and repair are not atomic.** Merge commits before its repair. A crash in between leaves src rows under the dropped id. A later `repair-index --fragments` recovers them, so nothing is lost.
- **Cost.** A full-store repair adds about 1.2 s per 700k links to every merge, and it runs under the writer lock once [[#b2-1]] is fixed. That is acceptable.

### MEH: known items m-3 and m-4 remain open {#m2-2}

- **m-3** (link writes to the bound partition; per-binding caches never evicted). Not a blocker for merge, deploy or the repair. It can only regrow foreign bits, never lose them.
- **m-4** (`_NowPool` registry row for `tests/test_fragment_partition_scope.py`). Not a blocker: test hygiene only.

## Verdict {#verdict}

DIRTY: 6 findings (2 BULLSHIT, 2 SKETCHY, 2 MEH). Of the 10 r1 items: 3 closed, 4 closed with a residual, 1 partial, and 2 known-open (m-3, m-4).

**Safe to merge to master and deploy?** Not as committed.
- [[#b2-1]] is latent until someone runs `rmx partition merge`, sync or `--async`, against a live daemon. When that happens it can mis-file concurrent writes (bug-098) and resurrect unlinks.
- Rule 10 makes [[#b2-2]] a blocker.
- Both fixes are small: about 6 lines plus 1 token, and the suite already passes with the correct predicate (M7 green).

**Safe to run `repair-index --fragments` on live stores?** Not until [[#b2-2]] and [[#s2-1]] land.
- The dry run is harmless as it stands. It holds the lock for about 1 s, makes no catalog writes, and writes one manifest file. But it misreports: the CLI shows `dropped_dead` only, and the manifest lists live edges as dropped.
- An apply with the current predicate deletes any fragment-only bit whose concept is a live memory, doc or code entity.
- Order after the fixes:
  1. Fix [[#b2-1]] and [[#b2-2]], and print all counters ([[#s2-1]]).
  2. Merge `--no-ff` and deploy.
  3. Per store: back up the ACTIVE slot (`catalog.<A|B>.duckdb` named by `active`). The manifest records drops only, never moves, so it is not a restore point.
  4. Per store: `--dry-run`. Read `dropped_dead`, `dropped_dead_concept`, `links_skipped` and `unread_dirs`. Expect `dropped_dead_concept` to equal the dead-concept-entity count (410 on the refmatrix probe copy).
  5. Apply.
  6. A day later, dry-run again. A non-zero `moved` measures the m-3 regrowth.
- Do not run `partition merge` on any store between deploy and the [[#b2-1]] fix.

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[claude#before-commit]]

## Ledger lines (for the orchestrator to apply) {#ledger}

last_run.log:

```
2026-10-14T13:35:29-0700 commit=4fb803b verdict=DIRTY findings=6 (2B/2S/2M) report=2026-10-14-1335-bug105-hotfix-r2-unlocked-merge-repair-and-concept-predicate-4fb803b.md
```

INDEX.md row:

```
| 4fb803b (a434f51..4fb803b, bug-105 hotfix r2; written 2026-10-14T13:35) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 6 (2B/2S/2M); r1 10: 3 closed / 4 closed-residual / 1 partial / 2 known-open | [[bsd-bug105-hotfix-r2-4fb803b]]. #b-1/#b-2 closed (M2/M3 killed). #b2-1: merge's new pre-flush, final cache clear and store-wide repair run OUTSIDE _lk (daemon op holds no lock; flush rebinds _partition_id = bug-098; repair txn on shared conn); clear-before-repair resurrects an unlink made in a lock-yield gap (probe). #b2-2: dead-concept test reads `concepts` (kind=concept rows only): probe copy 4,439 "dropped", 410 dead, 4,025 still present; fragment-only live doc/memory-concept bits deleted; M7 (ent_part) green = free fix. S: CLI/daemon log print dropped_dead only, merge discards repair report; survivors M1 (tick unpinned), M11, M12, M14. 17 mutants, 8 killed. |
```

IMPRESSIONS.md bullets:

```
- A remedy that "adds a step" to a lock-yielding op (merge_partition) must put the step under the yielded lock; the store-wide flush rebinding _partition_id outside _lk is bug-098 for the 6th time (bug-105 r2 #b2-1).
- Check WHICH table a remedy's existence test reads: `concepts` holds kind=concept rows only, while link concept_ids are any entity; prescriptions get implemented against the nearest-named table (bug-105 r2 #b2-2).
```
