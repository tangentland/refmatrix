---
gmd: "0.1"
id: task-23.1-queue-and-drain
title: "Task 23.1: one bind/recorder core with three front-ends (durable queue drain, non-consuming tail, bounded steps), offsets committed in the batch transaction, and one tick registry; learn_queue re-based on it"
tags: [task, queue, drain, tail, lock, partition, exactly-once, tick, bug-098, bug-099, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-15
---

# Task 23.1: queue, tail, bounded steps, and the tick registry {#root}

> Plan: [plan-23-bounded-write-harness](../plan-23-bounded-write-harness.md)
> Status: Pending (revision round 7, 2026-10-15: re-review [[bsd-plan23-17-spec-rereview-r7-331b414]]
> (nb23-r7-1, ns23-r7-1, nm23-r7-1, nm23-r7-2, nm23-r7-3); see [[#rev-round-7]]. The non-harness
> lock holders d9az gives plan-23 are task 23.5's, not this task's. Revision round 6,
> 2026-10-15: re-review [[bsd-plan23-17-spec-rereview-r6-0e77da3]]
> (ns23-r6-1, ns23-r6-2, ns23-r6-3, nm23-r6-1, nm23-r6-2) with d9ag and d9ao; see
> [[#rev-round-6]]. Round 5, 2026-10-14: re-review [[bsd-plan23-17-spec-rereview-r4-878647c]]
> (nb23-r4-1, ns23-r4-1, ns23-r4-2, nm23-r4-1, nm23-r4-2) and the user's writer-handle idea
> (R1.6, ADOPTED (d9ag)); see [[#rev-round-5]]. Round 3: [[#rev-round-3]]. Round 2: [[#rev-round-2]])
> Depends on: 23.0 (test sandbox), 23.2 (hold + write-count recorder), and **the bug-105 hotfix
> MERGED TO `master`** (branch `bug-105-fragment-partition`, at whatever sha its last clean
> ch-bsd audit closes on, with its five test files; merged in 0.78.0, [[#facts]] round 6). 23.1 does not start before that merge, and
> it never carries hotfix commits itself (nb23-r4-1).
> Blocks: 23.3; 16.6's Wave 1 slice; 22.2 (and so 22.5, 22.3); 17.1; 19.2
> Not gated on 23.4: the `bind` seam serves either verdict (decision-log #s-2).
> Not gated on bug-113 (the `replica_merge` schema defect): R8 / AC-13 are RETIRED (d9ao), so
> nothing in 23.1 runs `replica_merge`.

rel: part-of -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: implements -> [[plan-review-2026-10-14#t2-fixes]]
rel: implements -> [[plan-review-2026-10-14#t8-amendments-body]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81#findings]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2#s-1]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2#s-3]]
rel: related-to -> [[project_bug098_writer_partition_race]]
rel: related-to -> [[exploration-storage-concurrency-redesign#option-a]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#nb23-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#nb23-2]]
rel: implements -> [[plan-review-2026-10-14#t9]]
rel: implements -> [[plan-review-2026-10-14#t9-fixes]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#nb23-r3-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns23-r3-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns23-r3-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#nm23-r3-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#nb23-r4-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#ns23-r4-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#ns23-r4-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#nm23-r4-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#nm23-r4-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#writer-handle]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3#ns23-r6-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3#ns23-r6-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3#ns23-r6-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3#nm23-r6-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r6-0e77da3#nm23-r6-2]]
rel: implements -> [[plan-review-2026-10-14#t12-approvals]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#nb23-r7-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#ns23-r7-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#nm23-r7-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#nm23-r7-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#nm23-r7-3]]

## Facts at HEAD `b1c4324` this spec builds on {#facts}

- `daemon._drain_learn_queue` (`daemon.py:2079`) takes `_store_lock` ONCE PER coalesced entry
  (`test_the_drain_yields_the_writer_lock_between_entries` pins it), with a whole-tick deadline
  `LEARN_DRAIN_BUDGET_S` (5 s, `:647`), a shutdown stop, fatal-invalidation handling (mark repair,
  arm deferred exit, stop) and a re-append `requeue` of the remainder.
- `learn_queue.read_rotated` (`learn_queue.py:92`) parses, coalesces (UNION of hits per pattern),
  bounds (newest `MAX_QUEUE_LINES` win, overflow counted) and UNLINKS the rotated file BEFORE any
  entry is applied. Nothing reads an orphaned `*.draining` file. bug-099 is this silent loss.
- `_runner` (`daemon.py:2035`) drains only learn, then flushes fragments under the lock.
- `Store.with_partition` (`store.py:1911`) mutates the ONE writer Store's binding;
  `_partition_keeping_yield` (`daemon.py:3313`) is the only yield that restores it (bug-098).
  `_learn_grep_hits` (`daemon.py:4295`) writes into whatever is bound at rest.
- `Store.transaction` (`store.py:4233`) flushes dirty fragments AFTER `COMMIT` and only prints a
  failure. On the DuckDB backend fragments are rows of the `bitmap_fragments` table
  (`_flush_fragments_duckdb`), keyed by the BOUND `partition_id`, so they can be written inside the
  batch's own transaction.
- `replica_merge` keeps the A-side row on conflict for tables without `updated_at`.
- `rmx learn status` (`cli.py:7292`) runs in the CLI and shows the queue depth only when learning is
  OFF; the overflow reaches only the daemon's `rmxd.log` line.

Added in revision round 2, each re-read at HEAD `3357c44`:
- **The fragment cache is partition-agnostic (bug-105).** `Store._fragments: dict[str, BitMap64]`
  and `_dirty_fragments: set[str]` are keyed by LINKAGE only (`store.py:1055-1056`; the comment
  above them still says the Store is bound to one partition for its lifetime). `with_partition`
  (`store.py:1911-1952`) swaps `_partition_id`, `_partition_name` and `_vs`, and never touches the
  fragment cache. `_load_fragment` (`store.py:4080`) and `_flush_fragments_duckdb`
  (`store.py:4156`) use whatever partition is bound at the moment they run.
- **`with_partition` auto-creates.** It runs `INSERT OR IGNORE INTO partitions(name, kind,
  created_at)` for any name it is given (`store.py:1911-1952`), so a typo creates a partition.
- **`Store.transaction` nests silently** (`if self._in_transaction: yield`, `store.py:4245`) and
  flushes fragments only AFTER `COMMIT` (`store.py:4256-4269`).
- **Learn evidence is not idempotent (bug-106).** `_learn_grep_hits` (`daemon.py:4295`) calls
  `store.link("mentions", …)` and `store.add_evidence(…)` per `(file, line)`. `add_evidence`
  (`store.py:5267`) is a plain `INSERT INTO linkage_evidence`, and `linkage_evidence` has no
  primary key or unique constraint (`duckdb_catalog.py:162`). Two identical learns give two sets of
  evidence rows (the re-review's probe 2: 4 rows from 2 learns). The `link` half IS idempotent (a
  set bit).
- **The live store is already contaminated.** The re-review's census of a tmp copy of this repo's
  read snapshot found fragment bits under the wrong partition (`sessions-refmatrix mentions`
  195,003 of 422,811). The repair is bug-105's hotfix (d9a), not this task.

Added in revision round 3, read read-only in the hotfix clone `/Volumes/littlebig/refmatrix-bug105`
(branch `bug-105-fragment-partition`, commits `0d05525`, `20c5ab4`, `4fb803b`; line numbers are the
clone's at `4fb803b`), and at HEAD `5a8bf29` for the rest:
- **The hotfix's cache.** `Store._fragment_cache: dict[(partition_id, partition_name), dict[str,
  BitMap64]]` and `_dirty_by_binding: dict[(partition_id, partition_name), set[str]]`
  (`store.py:1063-1064`). `_fragments` and `_dirty_fragments` are PROPERTIES that return the
  CURRENT binding's view (`store.py:1076-1082`). `flush_fragments` (`:4174`) iterates
  `_dirty_bindings()` and writes each binding's dirty set under its own partition, then restores
  the caller's binding.
- **The guards read every binding** (`4fb803b`, audit #b-1). `Store.has_dirty_fragments()` and
  `Store.dirty_fragment_count()` (`store.py:1091-1097`) span every binding; `_runner`'s periodic
  flush (`daemon.py:2066`) and `Store.transaction`'s post-commit flush (`store.py:4502`) call them.
  No caller outside `store.py` reads `_dirty_fragments` any more.
- **Rename and merge keep their bits** (`4fb803b`, audit #b-2/#s-1). `rename_partition`
  (`store.py:1599`) calls `flush_fragments()` then `_clear_fragment_caches()` BEFORE it renames,
  so the name in the key can never split one partition into two caches. `merge_partition`
  (`store.py:1648`, real runs only) flushes every binding and clears the cache before it remaps
  entity ids and drops SRC (`:1692`), and at the end clears the cache again and calls
  `repair_fragments(dry_run=False, manifest_dir=root / "backups")` (`:1949-1954`), which re-homes
  every bit of the dropped SRC id to its entity's partition.
- **The repair is a union with a manifest, not a rebuild** (`20c5ab4` + `4fb803b`;
  `store.py:4308`). Each partition's fragment becomes the UNION of the `entity_links` bits of its
  entities and every existing fragment bit whose entity lives in it (moved there if it sat under
  another partition). Only two kinds of bit are dropped: a bit whose ENTITY is gone
  (`dropped_dead`) and a bit whose CONCEPT is gone (`dropped_dead_concept`); both go to a JSONL
  manifest under `backups/fragments-repair-<stamp>-{dryrun|applied}.jsonl`, written before any
  change. Dry run is the default and writes nothing (it overlays unflushed cache bits instead of
  flushing). Skipped `entity_links` rows are counted (`links_skipped`); fragment directories of
  unknown partitions are left on disk and reported (`unread_dirs`). Its docstring records why a
  pure rebuild from `entity_links` was rejected: on the census copy it would have lost 74
  own-partition bits and 442 foreign bits that existed only in fragment rows (nm23-r3-2).
- **`facts.log` events are appended at once, inside any open transaction.** `Store._log_event`
  (`store.py:1080`) opens the log and appends; `link` logs its `link` event (`:4366`) and
  `add_evidence` its `evidence` event (`:5293`) right after their statements, whether or not a
  transaction is open. `rebuild_index_from_log` replays `link` / `unlink` / `evidence` events
  (`store.py:7648`, `:7676-7681`). A batch that rolls back therefore leaves events for rows the
  catalog never committed (ns23-r3-2). (Round 3 also said "the A/B slots delta-replay from byte
  offsets into the same file"; that is FALSE at HEAD, see round 5 below.)

Added in revision round 5. The round-3 bullets above describe the hotfix at `4fb803b`, which later
audit rounds superseded; where they differ, these win. Hotfix facts were read read-only in the
clone at `fb285cc` (2026-10-14 14:20, r3 remedies; an r4 audit is running), and are cited as
the shape of the EXISTING code 23.1 builds on once it merges, not as a pin (nb23-r4-1):
- **Merge's store-wide fragment work runs under the writer lock it was given**
  (`27b3653` r2 #b2-1, `fc4c8d1` r3 #b3-1). `merge_partition` (`store.py:1648` at `fb285cc`)
  runs its pre-flush + `_clear_fragment_caches()` inside `with _lk:` (`:1698-1701`), and its end
  block, also inside one `with _lk:` (`:1962-1969`), (1) moves the home binding SRC → DST,
  (2) FLUSHES (never clears; a clear discarded an unlink made in a lock-yield gap and the union
  repair then wrote the bit back from the stale row), and (3) calls
  `repair_fragments(dry_run=False, manifest_dir=root / "backups", id_map={src: dst for every
  collision})`.
- **A concept is alive if its id is in `entities` OR `concepts`** (`27b3653` r2 #b2-2;
  `store.py:4360-4364`). A typed edge or `has-part` uses a doc / memory / code entity as the
  concept, and only `kind='concept'` entities have a `concepts` row; the code comment records
  that the concepts-only test called 4,025 live bits dead on a copy.
- **`repair_fragments(*, dry_run=True, manifest_dir=None, id_map=None)`** (`store.py:4325`,
  `fc4c8d1` r3 #s3-1): `id_map` (old entity id → new id) is applied to BOTH halves of every bit
  before it is classified, so a merge's colliding SRC ids move instead of being dropped as dead.
  Its docstring: "Caller holds the writer lock (the daemon op does)."
- **The hotfix's own regression suite**, as of `fb285cc`: `tests/test_fragment_partition_scope.py`,
  `tests/test_fragment_repair_audit.py`, `tests/test_fragment_repair_audit_r2.py` (among them
  `test_merge_store_wide_flush_and_repair_run_under_the_writer_lock`,
  `test_merge_interleaved_unlink_is_not_resurrected`,
  `test_repair_keeps_a_fragment_only_bit_whose_concept_is_a_live_doc`) and
  `tests/test_fragment_repair_audit_r3.py` (among them
  `test_p3_home_binding_rebind_happens_under_the_writer_lock`,
  `test_p7_merge_collision_bits_are_remapped_not_reported_dropped`). Each reads
  `bitmap_fragments` rows by SQL.
- **Decisions on the binding-local views** at `fb285cc` (nm23-r4-1): the only `if` / `for` /
  `in` tests on `_dirty_fragments` / `_fragments` in `src/` are inside `_load_fragment`
  (`store.py:4163`), `_flush_current_binding` (`:4219`, `:4225`) and `_flush_fragments_duckdb`
  (`:4247`). Many other methods MENTION the views (`save_bitmap`, `bulk_link`, `link_many`,
  `purge_entity`, `_bulk_purge_ids`, `_merge_fragment_all_partitions`,
  `_drop_legacy_fragment_raw`), to set or discard bits, not to decide a flush.
- **Nothing reads the A/B slot offsets** (nm23-r4-2), at HEAD `39dffbb`: `_read_slot_offset`
  (`daemon.py:2796`) has no caller in `src/`; `_refresh_replica_now` is a no-op ("writer rotation
  is DROPPED … the refresh thread is no longer started", `daemon.py:2812-2826`). Offsets are only
  WRITTEN (compaction, `daemon.py:2318-2321`; the rotation bootstrap seed, `:2841-2846`).
- **Compaction is size-gated with a floor** (ns23-r4-2): `_compact_factslog_if_needed`
  (`daemon.py:2274`) skips while `size < max(threshold, floor)` unless `force=True`
  (`:2309-2312`), and the floor holds a big store off "until it grows past" its compacted size
  times 1.25. `rmx compact-log --force` and the daemon op `compact_factslog` (`daemon.py:4020`)
  are the forced paths.
- **`_FairLock` records no owner** (`daemon.py:200`): its state is `_mu`, `_held` and
  `_waiters`; `locked()` says whether SOME thread holds it, never which. A held-lock assert needs
  an owner field (R1.6).

Added in revision round 6, read at HEAD `3d3c798` (0.78.1; `src/` identical to `0e77da3`). The
hotfix is merged; these bullets correct the round-5 ones where they differ (R1.1 item 7's
correction pass, nm23-r6-1):
- **Live merge is fenced (d9ae).** `_op_partition_merge` (`daemon.py:4051`) answers a dry run
  and REFUSES a live merge ("live partition merge is disabled (bug-105 #b4-1/#s4-1)"); merge runs
  only OFFLINE, with the daemon down, as `Store.merge_partition(…, lock=None)`. The
  `merge_partition` docstring (`store.py:1682`) says "no production caller since bug-105 r4
  fenced the live merge". The merge redesign is the helix plan's (d9ac). Round 5's "an r4 audit
  is running" is superseded: r4 ran, and its outcome is this fence.
- **The hotfix's suite is FIVE files.** `tests/test_fragment_partition_scope.py`,
  `tests/test_fragment_repair_audit.py`, `_r2.py`, `_r3.py`, and `_r4.py` (the fence, the M1
  periodic-flush guard, M11 `links_skipped`, M14 the canonical verb, the r5 remap pins). `_r4.py`'s
  `test_periodic_flush_persists_another_bindings_dirty_bits` (`:117`) pins `_periodic_flush`
  (`daemon.py:228`), the function R6.1 re-plumbs into the tick: it is AC-3d case (i)'s pre-image.
- **The repair's links half has the liveness gate (bug-111, 0.78.1).** In `repair_fragments`
  (`store.py:4326`), an `entity_links` row whose entity has no partition is skipped and counted in
  `links_skipped` and `links_dead_entity`; a row whose concept id is in neither `entities` nor
  `concepts` is skipped and counted in `links_dead_concept` (`store.py:4379-4395`). Those rows are
  LEFT in `entity_links` for plan-22's `dangling-link` class (d9an). So "the bitmap rebuilt from
  `entity_links`" is the bitmap of the ALIVE rows only.
- **Purge rebinds directly (bug-111 r2).** `_clear_purged_bits` (`store.py:6315`), called by
  `purge_entity` (`:6059`) and `_bulk_purge_ids` (`:6400`), visits every partition by assigning
  `_partition_id` / `_partition_name` directly from one read of `partitions`, not through
  `with_partition`, and restores the caller's binding in a `finally`. Its docstring: "Caller
  holds the writer lock."
- **The daemon assigns its writer Store at 8 sites** (ns23-r6-2): `serve_forever` (`daemon.py:1665`
  boot open, `:1734` init slot rebind, `:1757` its legacy fallback), `_bootstrap_rotation_if_needed`
  (`:2888` asymmetric slot repair, `:2924` legacy bootstrap), `_op_replica_merge` (`:5490` reopen
  after a failed merge build, `:5508` dry-run reopen, `:5557` reopen after the swap). Each is
  `self.store = Store(…)` / `d.store = Store(…)` followed by `db_path` and `init()`.
- **`replica_merge` is broken on real stores and has no producer of diverged slots** (bug-113,
  open; `bug_registry.md:166`): `merge_slots` builds its target with `duckdb_catalog.init_catalog`,
  which lacks `entities.vectors_partition`, and merges an explicit table list. Writer rotation is
  dropped (`_refresh_replica_now`, `daemon.py:2814`, a no-op). R8 / AC-13 are RETIRED (d9ao).
- **`_compact_factslog_if_needed` (`daemon.py:2307`) takes the lock itself**: its size gate runs
  unlocked, then `with self._store_lock:` (`:2346`) wraps `dump_catalog_to_log()` and the slot
  offset reset; the floor bookkeeping and log lines run after the release. `_FairLock`
  (`daemon.py:242`) is NOT re-entrant: a thread that holds it and calls `acquire` again queues
  behind itself (nm23-r6-2).
- Line moves since round 5: `_FairLock` `daemon.py:242` (was 200), `_read_slot_offset` `:2798`,
  `_refresh_replica_now` `:2814`, `_load_fragment` `store.py:4152` (its decision at `:4164`),
  `_flush_current_binding` `:4218` (decision at `:4220`).

Added in revision round 7, read at HEAD `77ac38f` (`src/` unchanged since `0e77da3`):
- **The shutdown close takes no lock and its flush failure is swallowed (nb23-r7-1).**
  `serve_forever`'s finally closes the writer on a new thread `rmxd-close`: `_do_close` runs
  `self._st().close()` (`daemon.py:2018-2020`) with no `_store_lock`, bounded by
  `close_budget`; a captured error is logged as "store close failed" (`:2037-2038`).
  `Store.close()` runs `try: self.flush_fragments() except Exception: pass`
  (`store.py:2173-2176`) before it closes the read view and the connection, each in its own
  bare `except: pass` (`:2177-2188`). So a `WriterLockNotHeld` raised by the flush never
  reaches `close_err`, and the bits dirtied since the last periodic tick are dropped unsaid.
- **The init slot rebind runs unlocked (nb23-r7-1).** `serve_forever`'s rebind
  (`daemon.py:1727-1732`) runs `CHECKPOINT`, `flush_fragments()` and `close()` in one `try`
  whose `except` logs "init slot rebind: close failed" and so skips `close()` when the flush
  raises; it is under no lock. Both `_bootstrap_rotation_if_needed` branches already wrap
  the same sequence in `with self._store_lock:` (`:2871`, `:2911`).
- **Purge writes Lance before it reaches the rebind (ns23-r7-1).** `purge_entity`
  (`store.py:5990`) calls `_drop_lance_for_purge` at `:6015` and `_clear_purged_bits` only at
  `:6059`; `_bulk_purge_ids` (`:6363`) drops Lance at `:6385` and clears bits at `:6400`;
  `purge_path` (`:6188`) calls `_drop_lance_for_purge_batch` at `:6207` and then
  `purge_entity(…, _skip_lance=True)` per id. A Lance delete commits a version even with no
  match (Lance 6.0.1, the r7 re-review's run).
- **Every `store` attribute assignment in `daemon.py` (nm23-r7-1):** the 8 `Store(…)` sites of
  round 6 and one annotated declaration, `self.store: Store | None = None` in
  `Daemon.__init__` (`daemon.py:728`, an `ast.AnnAssign`, not an `ast.Assign`). `cli.py` sets
  `d.store` on in-process `Daemon` objects at 7 sites (`cli.py:7201`, `:10170`, `:10412`,
  `:10476`, `:10592`, `:10694`, `:10770`); those daemons never serve a socket and never get a
  `writer_lock`, so they are outside R1.6's rule (item 2's "no `writer_lock`" case).
- **23.2's `HoldRecorder` surface is closed (nm23-r7-2).** [[task-23.2-lock-hold-fixture#r2]]
  lists `acquire`, `release`, `locked`, `__enter__`, `__exit__`; it was approved (d9at)
  before `_FairLock.held_by_current_thread` existed, so a recorded daemon would answer R1.6's
  check with `AttributeError`.
- **A concept entity has a `concepts` row (nm23-r7-3).** The `concepts` DDL
  (`store.py:282`: id "equals entities.id where kind='concept'"), with inserts at `:1860`,
  `:2246`, `:2421-2429`; the 0.78.1 gate (`store.py:4388`) calls a concept dead only if its id
  is in neither `entities` nor `concepts`.
{#facts-body}

## Requirements {#requirements}

### R1 One core: `bind`, the batch transaction, the recorder hook {#r1}

`src/refmatrix/bounded.py` holds one core that all three front-ends (R3, R4, R5) run through.

1. **`bind(partition_name) -> ContextManager[Handle]`** is supplied by the store's owner, never
   built by a consumer (23 #b-1, d2b). The daemon's implementation, `daemon_bind(d)`:
   `with d._store_lock:` then, INSIDE that hold, `with st.with_partition(name, create=False):`
   and yield the store. The binding is entered after the lock is taken and exited before it is
   released, in one `with`; no binding is ever held across a release. Under Option A (23.4 GO)
   `bind` returns a per-op cursor handle and no consumer's `apply` changes.
   - `with_partition` gains a keyword `create: bool = True`. Existing callers keep today's
     auto-create. `bind` always passes `create=False`: an unknown name raises
     `UnknownPartition(name)` BEFORE any row is written, and the `partitions` table is unchanged
     (nb23-1).
   - **The binding is every piece of state keyed by the partition, not only the id** (nb23-1,
     nb23-r3-1, bug-105, d9a). That includes the state that DECIDES whether to flush, and every op
     that changes a partition's name or id. The mechanism is bug-105's hotfix AS MERGED TO
     `master` ([[#facts]] rounds 3 and 5; nb23-r4-1), ADOPTED with AC-3b and AC-3d as the
     regression tests it must pass (no longer "unchanged"; nb23-r3-1). Its contract, which 23.1 owns from then on, inside
     `store.py` and never in a consumer:
     1. **Per-binding cache.** `_fragment_cache` and `_dirty_by_binding` are keyed by the binding
        `(partition_id, partition_name)`; `_fragments` / `_dirty_fragments` are views of the
        CURRENT binding only, so any rebind switches caches however it is done. Every load reads
        the bound partition's row.
     2. **Every flush writes each binding's dirty set under ITS OWN `partition_id`**
        (`flush_fragments` over `_dirty_bindings()`), never under the id bound at flush time, and
        restores the caller's binding.
     3. **Every "is anything dirty" test spans every binding.** `has_dirty_fragments()` and
        `dirty_fragment_count()` are the only such tests: `_runner`'s periodic flush,
        `Store.transaction`'s post-commit flush, R1.3's pre-flush, R6's tick and R7 use them. No
        code outside `store.py`'s cache internals reads `_dirty_fragments` or `_fragments` (a
        binding-local view) to decide a flush; AC-3d (v) checks it by search.
     4. **An op that changes a partition's name or id first flushes every binding, then clears the
        cache; at its end it FLUSHES, never clears** (nb23-r4-1, following the hotfix's r2/r3
        remedies). The name is part of the key, which is sound only under this rule:
        `rename_partition` flushes and clears before it renames. `merge_partition` (real runs)
        flushes and clears before it remaps entity ids and drops SRC. At its end, in ONE hold of
        the writer lock it was given, it moves the home binding SRC → DST, FLUSHES, and runs
        `repair_fragments(dry_run=False, manifest_dir=root / "backups", id_map={src_id: dst_id
        for every collision})`, so no bit stays under the dropped id, every remapped entity's bit
        is re-homed, and an unlink made in a lock-yield gap (the progress callback between
        chunks) is not resurrected from a stale row. Any future op that renames, merges, drops or
        renumbers a partition follows the same rule.
     5. **Every store-wide fragment step runs under the writer lock** (nb23-r4-1; r2 #b2-1, r3
        #b3-1). `flush_fragments` rebinds `_partition_id` while it writes, so a flush, a cache
        clear, a repair or a rebind that runs while another op holds the lock is the bug-098
        shape. An op that yields the lock (merge's per-chunk `with _lk:`) takes it again around
        each of these steps; an op that takes the lock as an optional argument never runs them
        under `nullcontext()` when a lock exists. R1.6 (ADOPTED (d9ag)) turns this rule into a
        check. Since the d9ae fence, merge's per-chunk yield runs only OFFLINE with `lock=None`
        ([[#facts]] round 6); the rule binds every live writer, and the helix plan's merge
        redesign (d9ac) when it lands.
     6. **A bit is dead only if its entity is gone, or its concept id is in neither `entities`
        nor `concepts`** (nb23-r4-1; r2 #b2-2). A concept id can be any entity id (typed edges,
        `has-part`), so "absent from `concepts`" alone is never "dead".
     7. **Where the code lives (nb23-r4-1; the brief's merge rule).** All of the above is the
        bug-105 hotfix's code, adopted as EXISTING code once it is merged to `master` (the
        header's `Depends on:`). 23.1 does not re-implement it, does not cherry-pick it, and
        names no sha as its source: the contract is whatever the merged, audited branch holds,
        and its FIVE test files ([[#facts]] round 6, correcting round 5's four) are the
        contract's regression suite, kept green by every 23.1 commit (AC-3d). If a later hotfix
        audit changes the code, this list is corrected to match the merged code, not the other
        way round. **Round-6 correction pass (nm23-r6-1), at 0.78.1:** the live merge is fenced
        (d9ae; item 4's merge text describes the OFFLINE merge, still under this rule); the fifth
        file is `tests/test_fragment_repair_audit_r4.py`; bug-111 added the links-half liveness
        gate (item 6 applies to `entity_links` rows too: a dangling row contributes no bit and is
        counted, never removed by the repair) and `_clear_purged_bits`' direct rebind (R1.6
        item 3 names it). The four contract points (per-binding cache, flush-not-clear, lock rule,
        alive predicate) are unchanged.
   - **The live store's existing cross-partition bits** are repaired by the hotfix's
     `rmx repair-index --fragments` (`Store.repair_fragments`), announced and backed up first
     (d9a). It is NOT "a rebuild from `entity_links`" (nm23-r3-2, correcting this spec's round-2
     text and d9a's wording): it is the UNION of the `entity_links` bits and every existing
     fragment bit, each moved to its entity's partition, and it drops only bits whose entity or
     concept is gone (item 6), into a manifest written first. Its `entity_links` half takes only
     ALIVE rows (bug-111): a dangling row is counted (`links_dead_entity`, `links_dead_concept`)
     and left for plan-22's `dangling-link` class (d9an). That is derived-index cleanup with a manifest
     under ADR-0004 `#rule-no-delete` (d9k). No later task may "simplify" it into the lossy
     rebuild; a pure `entity_links` rebuild would have lost 516 bits on the census copy. 23.1 ships
     no repair of its own.
2. **Batches carry partition NAMES, never ids** (r10 #s-1's id-1 fallback). `bind` resolves the
   name and raises on an unknown one; there is no fallback to partition 1. A batch never spans two
   partitions: the front-end cuts a batch at every partition change.
3. **One transaction per hold.** Inside the bound handle the core runs
   `with handle.batch_transaction():` → `apply(handle, batch)` → the dirty fragments are flushed
   INSIDE the transaction (DuckDB `bitmap_fragments`) → the front-end's offset row is written (R3,
   R4) → `COMMIT`.
   - `Store.batch_transaction()` is a NEW primitive (nm23-4), not a change to
     `Store.transaction`. Its steps, in order:
     1. **Pre-flush (ns23-r3-1).** If `has_dirty_fragments()`, flush EVERY binding's dirty set
        in its own commit (the ordinary `flush_fragments`), under the same hold, BEFORE `BEGIN`.
        Those bits came from earlier committed writes (a `link()` outside the harness leaves its
        fragment for `_runner`'s periodic flush). A pre-flush failure raises before `BEGIN`: the
        batch is not applied, `fragment_flush_failures` is incremented, the entries stay dirty,
        and the run takes the `on_error` path (R2). After it, `has_dirty_fragments()` is False;
        the core asserts that at `BEGIN`.
     2. `BEGIN`; yield to `apply`.
     3. Flush every dirty entry, each under its own `partition_id` (R1.1). Because the dirty set
        was empty at `BEGIN`, every entry flushed here is the batch's own.
     4. The caller's offset write; `COMMIT`.
     5. **Events after `COMMIT` (ns23-r3-2).** While `batch_transaction` is open, `_log_event` and
        `_log_events` append to an in-memory buffer instead of `facts.log`. After `COMMIT` the
        buffer is appended in ONE write (`_log_events`). On rollback it is discarded. So no
        `facts.log` event exists for a row that a rollback removed, and a retry emits each
        event once.

     It RAISES `NestedTransaction` if `_in_transaction` is already true, so it can never silently
     fall into `Store.transaction`'s nested no-op and move the flush back after `COMMIT`.
     `Store.transaction` keeps its post-`COMMIT` flush outside the harness (R7). Relational rows,
     bitmap fragments and the offset are atomic (d2a + its amendment). If anything raises after
     `BEGIN`, the transaction rolls back, the event buffer is discarded, AND the fragment cache
     is dropped so it reloads from the database (a rolled-back batch must not leave bits in the
     cache that the catalog does not hold).
     - **How the drop is done (ns23-r4-1): `_clear_fragment_caches()`, EVERY binding, every
       entry.** Step 3's in-transaction flush has already cleared the dirty marks, so "the
       entries the batch dirtied" can no longer be found by their marks; the batch's bits sit in
       the cache as CLEAN entries that a later link to the same `(partition, linkage)` would
       flush. Clearing the whole cache is exact because step 1 left nothing dirty at `BEGIN` and
       nothing outside the batch can have dirtied an entry since (the hold is the batch's): every
       cached entry is either an unchanged copy of a committed row (it reloads identical) or
       carries the batch's rolled-back bits (it must go). No earlier committed bit is lost, and
       no other binding's entry is un-dirtied by a flush that the rollback then un-writes
       (ns23-r3-1). An implementation that looks for dirty marks here is wrong by construction.
     - The harness refuses the SQLite backend with an error naming it.
4. **`prepare(batch)`** (optional) runs OFF the lock before each hold: re-stats, file reads, record
   building (16.6 R4's pre-step; 23.3's semantic records). It must not touch the writer
   connection.
5. **Every run returns** `RunResult{applied, batches, holds, max_hold_s, hold_s, finalize_ran,
   alarms, stopped, failed, dead_lettered, overflow, malformed, pending,
   fragment_flush_failures}`, where `stopped ∈ {"", "budget", "shutdown", "store-invalid",
   "error"}`.
   - `hold_s: list[float]` is the duration of every hold IN ORDER, one entry per batch, plus one
     final entry for `finalize` when `finalize_ran` is true (ns17-2: 17.1 reports hold seconds per
     dataset and 17.3 reads them; with `batch=1` in `bounded_steps`, `hold_s[i]` is step `i`'s
     hold). The core measures it around the `bind` hold, in production code, not through 23.2's
     test-only recorder. `holds == len(hold_s)` and `max_hold_s == max(hold_s, default=0)`.
6. **ADOPTED (d9ag): a held-writer-lock check in the Store's writers** (the user's
   writer-handle idea, 2026-10-14; [[bsd-plan23-17-spec-rereview-r4-878647c#writer-handle]];
   adopted as written by d9ag, with round 6's reopen wiring in item 2 and the purge rebind in
   item 3).
   `bind` (R1.1) already is the writer handle for harness consumers: it takes the lock, binds
   inside the hold, exits both in one `with`, and holds no binding across a release, so nothing
   needs re-binding "after a yield". What it does NOT give is a check that fires when a store-wide
   fragment step or a rebind runs WITHOUT the lock, the hotfix's r2 #b2-1 / r3 #b3-1 shape, in
   harness and non-harness writers alike (every writing `_op_*`, `_partition_keeping_yield`,
   purge's `_clear_purged_bits`, `Store.transaction` callers). Merge is not on this list: since
   the d9ae fence its chunked yield runs only offline with `lock=None` (a Store with no
   `writer_lock`), and the live merge belongs to the helix plan (d9ac), which inherits this
   check (nm23-r6-1). The requirement:
   1. **`_FairLock` gains an owner.** `_owner: int | None`, set to `threading.get_ident()` by the
      thread that ends up holding the lock (the fast path in `acquire`, and the woken waiter
      after `ev.wait` returns True, since `release` hands ownership to it), cleared in
      `_pass_or_release_locked` before hand-off or release, and read by a new
      `held_by_current_thread() -> bool`. The timeout-race branch (handed the lock, then passes
      it on) never leaves `_owner` set to itself. **23.1 itself edits 23.2's `HoldRecorder`
      (nm23-r7-2):** 23.2's approved surface (d9at) is closed and lacks the method, so 23.1 adds
      one explicit pass-through, `HoldRecorder.held_by_current_thread()` returning the wrapped
      lock's answer, in `tests/lockhold.py` ([[#files]]). It is an explicit method, not a
      `__getattr__` catch-all, so the recorder's surface stays a list a reader can check, and an
      attribute the wrapped lock lacks still raises.
   2. **The Store knows the lock, on EVERY writer Store, resolved at check time (ns23-r6-2).**
      - `Store.writer_lock: Callable[[], Lock] | None` (default `None`) is a zero-argument
        callable that returns the lock to check, not a lock captured at open time. The Daemon
        installs `lambda: self._store_lock`, so a recorder that 23.2's `recorded_daemon`
        installs as `_store_lock` after the Store opened is the lock checked.
      - **ONE installer.** `Daemon._install_writer_store(st: Store) -> Store` sets
        `st.writer_lock` and assigns `self.store = st`. All 8 writer-Store sites ([[#facts]]
        round 6: `serve_forever` `:1665`, `:1734`, `:1757`; `_bootstrap_rotation_if_needed`
        `:2888`, `:2924`; `_op_replica_merge` `:5490`, `:5508`, `:5557`) call it in place of
        their `self.store = Store(…)` / `d.store = Store(…)` assignment, at the same position
        (construct, install, then `db_path` and `init()` as today), so no site's failure
        behaviour changes. Any future writer-Store site uses it too.
      - An AST test over `daemon.py` asserts that no assignment to an attribute named `store`
        exists outside `_install_writer_store`, WHATEVER its value (nm23-r7-1): any
        `ast.Assign` or `ast.AugAssign` target, any `ast.AnnAssign` target with a value, any
        tuple-unpacking element, and any `setattr(<x>, "store", …)` call. Round 6's rule
        matched only `x.store = Store(…)`, so `st = Store(…); …; self.store = st` passed it.
        Exactly one exemption, by location AND shape: the declaration
        `self.store: Store | None = None` in `Daemon.__init__` ([[#facts]] round 7; an
        `AnnAssign` whose value is the constant `None`). `cli.py`'s in-process `d.store = …`
        sites are outside the rule (no `writer_lock`; [[#facts]] round 7) (AC-20).
      - A Store with no `writer_lock` (in-process CLI, offline merge, `serial_bind`, a test
        `Store`) skips the check: it has no lock to hold.
   3. **The check.** `Store._require_writer_lock(site: str)` raises `WriterLockNotHeld(site)`
      (a real exception, not an `assert` statement, which `python -O` strips) when
      `writer_lock` is set and `not writer_lock().held_by_current_thread()`. It is called at the
      top of `flush_fragments`, `repair_fragments` (when `dry_run=False`), `transaction`,
      `batch_transaction`, `with_partition` (entry and exit), `_clear_fragment_caches`, and at
      every direct rebind of `_partition_id` / `_partition_name` outside `with_partition`:
      `_clear_purged_bits` (`store.py:6315`, reached by `purge_entity` and `_bulk_purge_ids`;
      bug-111 r2 moved purge off `with_partition`, nm23-r6-1), `_partition_keeping_yield`'s
      restore (which runs right after its `acquire`), and the offline merge end block's
      SRC → DST move (`store.py:1966`; a no-op check there today, since an offline Store has no
      `writer_lock`, but it binds the helix plan's live merge).
      - **Purge checks FIRST, before any write (ns23-r7-1).** `purge_entity`, `_bulk_purge_ids`
        and `purge_path` call `_require_writer_lock("purge")` as their first statement, before
        any Lance delete or SQL statement. The rebind check in `_clear_purged_bits` stays. A
        check only at the rebind fires AFTER the Lance delete ([[#facts]] round 7): the entity
        keeps its row and its non-NULL `vectors_updated_at`, so `pending_embeddings` never
        re-queues it and its vector is gone.
   4. **First run = census; every site it finds is MOVED UNDER THE LOCK (nb23-r7-1).** Before
      the check is switched on, one full-suite run with the check in WARN mode (log the site and
      the stack, do not raise) lists every call site that reaches these methods unlocked. Every
      site is moved under the lock. There is no "named safe" route: a site left unlocked still
      raises once the check is on, and at the two sites round 6 offered as "safe" that raise
      lands inside an `except` that hides it. Only then does the check raise. Round 6's text
      ("each is either moved under the lock or named in the implementation summary with why it
      is safe (for example `Store.close()` at daemon shutdown …, or `serve_forever`'s init slot
      rebind flush at `:1729` …)") is withdrawn. The two known sites, specified:
      - **Shutdown close.** `_do_close` (`daemon.py:2018`) runs
        `self._store_lock.acquire(timeout=<close_budget minus 0.5 s, floor 0>)` around
        `self._st().close()` and releases in a `finally`. On a timeout it does NOT call
        `close()` (the process exit releases the file locks, as the existing close-timeout
        path already relies on) and logs one line, `store close: writer lock not acquired in
        <s>s; <n> dirty fragment(s) NOT flushed`, with `n = dirty_fragment_count()`; it never
        skips silently.
      - **Init slot rebind.** The `CHECKPOINT` + `flush_fragments()` + `close()` sequence at
        `daemon.py:1727-1732` and the reopen through `_install_writer_store` run inside
        `with self._store_lock:`, as both `_bootstrap_rotation_if_needed` branches already do
        (`:2871`, `:2911`). `close()` moves to its own `finally` inside that hold (the bug-110
        r1 #m-3 shape at `:2873-2881`), so a failed flush no longer skips the close.
      - **`Store.close()` stops swallowing the check (nb23-r7-1).** Its flush step catches
        `WriterLockNotHeld` separately: it runs the read-view and connection closes (the file
        lock must still be released), then RE-RAISES the `WriterLockNotHeld`, which
        `_do_close`'s `close_err` path logs as "store close failed". Any OTHER exception from
        that flush is no longer `pass`: it is appended to a new `Store.close_errors: list[str]`
        and the read-view and connection closes still run; `_do_close` logs each entry. The
        connection-close steps keep their own isolation (their comment's reason, a
        FatalException-invalidated catalog, is unchanged).
   5. **Scope: the THREAD lock only (ns23-r6-2, bug-110).** The check proves which thread holds
      `_store_lock`. It is blind to DuckDB's `fcntl` lock on the slot file, which belongs to the
      (process, file) pair and is dropped by ANY in-process `close()` of a descriptor for that
      file (bug-110). That lock is covered by a separate rule, not by this check: the daemon
      process never opens a descriptor of the writer slot or its `.wal` in-process
      (`_copy_out_of_process`, `daemon.py:203`). A clean WARN-mode census is therefore never
      cited as evidence against bug-110's class.
   6. **Not in scope:** migrating every `_op_*` writer onto a `d.writer(partition)` handle.
      The check makes an unlocked write fail loudly wherever it happens; moving the ops onto
      one handle is separate scope for its own plan if the user wants it. {#r1-6-proposed}

### R2 Stop paths, error policy, and the hold alarm (23 #s-1) {#r2}

Every front-end takes the same keyword set, all named:
- `batch` (default **1** event per hold; a consumer raises it explicitly);
- `budget_s` (whole-run budget, checked before each hold; the remainder stays pending);
- `cancel()` (checked before each hold; the daemon passes `d._shutdown_event.is_set`);
- `on_error(exc, batch) -> "dead-letter" | "stop" | "fatal"`. `fatal` is the daemon's classifier
  for `Daemon._is_fatal_invalidation`: mark repair, arm the deferred exit, stop; the failed batch's
  transaction is rolled back and its offset NOT advanced. `dead-letter` appends the batch's raw
  lines and the error to `<queue>.deadletter.jsonl`, counts it (`dead_lettered`, persisted in R6),
  and advances the offset in its own transaction: no batch is silently skipped and none blocks the
  queue forever. The dead-letter file is kept forever (no rotation, no unlink) and is re-drivable
  (R6.7, nm23-1). `stop` leaves the batch pending. Default: `stop`;
- `hold_alarm_s`: a hold longer than this logs a warning with the batch size and the R3 counts of
  23.2's recorder when installed. It is an ALARM, never a stop and never a guarantee (23 #s-5);
  consumers assert write counts through 23.2;
- `finalize(handle, summary)` (optional): run ONCE after the last batch, under its own hold through
  `bind`, inside its own transaction (23 #b-3: 22.2's one Lance delete per kind, not per batch). For
  R3/R4, every batch transaction sets `finalize_pending=true` on its offset row and finalize's
  transaction clears it; a run that starts with the flag set runs finalize FIRST. For R5 (no
  durability), finalize runs in a `finally` after any stop.
- **Requeue is resume-from-offset.** The remainder of a stopped run stays in its segment past the
  committed offset; nothing is re-appended (a re-append doubles the remainder on a crash between the
  append and the unlink).

### R3 `BoundedQueue` + `drain(queue, …)`: the durable, coalescing, consuming front-end {#r3}

1. `BoundedQueue(path, *, key_fn, merge_fn, max_lines)`: `key_fn` and `merge_fn` are REQUIRED
   (23 #s-2). `merge_fn(acc, ev) -> acc` states the merge: UNION (learn), SUM (counts), MAX (times).
   There is no last-wins default. The key always includes the event's partition name.
2. **Append** is one `O_APPEND` JSON line with no lock and no socket (today's `enqueue`).
3. **Segments.** A drain rotates the live file to a NEW segment `<name>.<seq>.seg` (never
   overwritten) and keeps it until its LAST offset commits; only then is it unlinked. At daemon boot
   every segment, and any legacy `*.draining` file left by pre-23.1 code, is adopted and resumed
   from its committed offset (bug-099, d2d).
4. **Offsets (d2a).** A catalog table `queue_offsets(queue, segment, offset_bytes,
   finalize_pending, events_pending, PRIMARY KEY(queue, segment))` (`events_pending`: R3.7,
   ns23-r4-2); each batch writes its row inside R1's
   transaction. The committed offset is the byte position after the last raw line the committed
   batches fully cover.
5. **Coalesce scope.**
   - `scope="window"` (default): a batch coalesces only the raw lines in its own window; the offset
     after the window commits with it. Effects are exactly-once: required for any non-idempotent
     merge (SUM, MAX-with-count).
   - `scope="segment"`: the whole segment is coalesced first (today's learn shape: N greps → M
     patterns), entries are applied per hold, and each hold commits the covered prefix. A crash can
     re-apply an entry whose lines lie past the prefix, so the harness REFUSES `scope="segment"`
     unless the queue is declared `idempotent=True`.
   - `idempotent=True` is a CLAIM, and a claim is checked, not trusted (nb23-2). A queue may
     declare it only if its task carries a crash-replay AC of the AC-16 shape (a child exits after
     hold 1 of 3; after the restart every effect is counted and equals its distinct-key count),
     with the non-idempotent write as a pre-registered mutation that FAILS it. The plan's consumer
     table names that AC beside the declaration. Learn declares it after R9.5 makes its evidence
     write insert-if-absent; AC-16 is its check.
6. **Overflow** past `max_lines` drops the OLDEST lines (newest win, today's rule), counts them in
   the run result and in the persisted counter of R6. Never silent.
7. **Exactly-once boundary, stated** (#t8-amendments d2a): it covers what commits in the one DuckDB
   transaction: relational rows, `bitmap_fragments` rows, the offset. Lance writes are not in it;
   a consumer that writes Lance does it in `finalize`, which is re-run while `finalize_pending` is
   set and must be idempotent.
   - **`facts.log` is post-commit (ns23-r3-2).** A batch's events are written only after its
     `COMMIT` (R1.3 step 5), never for a rolled-back batch, so `rebuild_index_from_log` cannot
     resurrect a rolled-back link or duplicate a rolled-back evidence row. (Round 3 also named
     "the A/B slot delta-replay" here; nothing reads the slot offsets at HEAD, nm23-r4-2, so
     `rebuild_index_from_log` and 17.4's restore are the log's only replay readers.) The
     residual, stated: a SIGKILL in the one `write` between `COMMIT` and the append loses that
     batch's events (at most once; never a phantom). The catalog is the authority (the
     `_log_event` docstring), and a compaction (`dump_catalog_to_log`) re-derives the log from
     the catalog.
   - **The residual is detected and closed at the next boot, not "at the next compaction"
     (ns23-r4-2).** Compaction is size-gated with a floor ([[#facts]] round 5), so on a big
     store the next one can be weeks away, while the lost events are learn rows, which exist
     only in the catalog and the log, and 17.4's daily copy would back up a log without them.
     So:
     1. Inside every batch transaction, before `COMMIT`, the core sets `events_pending = true`
        on the batch's `queue_offsets` row (for `bounded_steps`, which has no offset row, on a
        one-row-per-run `bounded_runs(run_key, events_pending)` marker table). It commits with
        the batch.
     2. After the post-commit append (R1.3 step 5) returns, the core clears the flag in a
        one-statement follow-up write under the same hold. A batch with no buffered events
        never sets it.
     3. At daemon boot (before the first tick), if any `queue_offsets` or `bounded_runs` row has
        `events_pending = true`, the daemon compacts and clears in ONE hold (nm23-r6-2).
        `_compact_factslog_if_needed` takes `_store_lock` itself and `_FairLock` is not
        re-entrant ([[#facts]] round 6), so the boot check does NOT call it inside a hold.
        Instead its locked body is factored out: `Daemon._compact_factslog_locked() -> dict`
        runs `dump_catalog_to_log()` and the A/B slot-offset reset, and REQUIRES the caller to
        hold `_store_lock` (it raises if `not self._store_lock.held_by_current_thread()`,
        R1.6 item 1). `_compact_factslog_if_needed` keeps its size gate, its floor bookkeeping
        and its log lines, and calls the helper inside its own `with self._store_lock:`, so its
        behaviour is unchanged. The boot check is: `with self._store_lock:` read the flagged
        rows, call `_compact_factslog_locked()`, clear exactly those rows' flags; then log one
        `rmxd.log` line naming them. No batch can set a flag between the read and the clear,
        because both are in the one hold. A failed compaction raises before the clear, so it
        leaves the flags set, logs the error, and is retried at the next boot; it is reported by
        `queue_status` as `events_pending: [<queue/run>]`.
     4. The flag is set and cleared in the catalog, so a crash between `COMMIT` and the clear is
        exactly the case it records; a crash after the clear has no residual to close.

### R4 `TailLog` + `tail(log, …)`: the non-consuming reader (d4a) {#r4}

1. `TailLog(path, *, key_fn, merge_fn)` reads by `(file, offset_bytes)` from the committed offset
   to the LAST COMPLETE NEWLINE; a torn tail from a lock-free appender is left for the next run.
2. It NEVER rotates, unlinks, truncates or rewrites the file (the file is shared with plan-21's
   measurement and is the retained replay source, #t8-amendments d2a). Its offset is a
   `queue_offsets` row (segment = the file name) committed in the batch transaction (R1.3).
3. There is no overflow: a backlog is read in `batch`-line windows until the budget ends.
4. Any future rotation of a tailed log must be segment-aware `(segment, offset)` and must retain
   every segment past the lowest committed offset; plan-23 rotates none.
5. Rows are returned raw. Filtering (for example d8d's pytest-temp-dir predicate) is the
   consumer's `prepare`/`apply`.

### R5 `bounded_steps(items, …)`: in-memory steps with no durability claim {#r5}

For loops over an in-memory list that are not queues (23 #s-3): 17.1's datasets, 22.2's apply plan,
23.3's file chunks. Each step goes through R1 (`bind` per step with the step's partition name, one
transaction, the recorder hook) and R2 (budget, cancel, error policy, alarm, finalize in a
`finally`). Crash recovery is the consumer's (22.2's manifest, 23.3's mtime gate); the docstring
says so.

### R6 The tick registry: one registry, one shared budget (d4a, 23 #s-3) {#r6}

1. `Daemon.tick_registry.register(name, runner, *, kind)`, `kind ∈ {"drain", "tail",
   "bounded_steps"}`, in a fixed registration order. `_runner` calls `tick_registry.run()` where it
   calls `_drain_learn_queue()` today; the periodic fragment flush stays after it, every tick, as
   today's `_periodic_flush(store, lock, log)` (`daemon.py:228`, signature unchanged, so the
   hotfix's M1 pin passes unchanged; AC-3d (x)), guarded by `has_dirty_fragments()` (every binding), never by the binding-local
   `_dirty_fragments` (nb23-r3-1, R1.1 item 3).
2. ONE budget for all registrants together: `LEARN_DRAIN_BUDGET_S` (default 5 s) keeps its name so
   existing tests that patch it still work; each registrant gets what the ones before it left.
3. Start rotates round-robin: a tick starts at the registrant after the one that exhausted the
   previous tick's budget, so no registrant starves.
4. Registrants at the end of 23.1: `learn` (drain). Later: 19.2's fold (tail), 16.6's marks
   (drain). 17.1, 22.2 and 23.3 use `bounded_steps` from their own ops, not the tick.
5. **Persisted counters + a daemon op (23 #s-6).** A catalog table
   `queue_counters(queue, overflow_total, malformed_total, dead_lettered_total, failed_total)` is
   updated in the batch transaction. Daemon op `queue_status` returns, per registrant: pending lines
   (live file + every segment past its committed offset), the four totals, `last_run_at`,
   `last_stopped`, and the store's `fragment_flush_failures` total. `_store_health` keeps
   `learn_queue_pending` and adds `learn_queue_overflow_total`.
6. `rmx learn status` calls `queue_status` through the daemon UNCONDITIONALLY (learning on or off)
   and prints `queued: N`, `overflow (dropped, total): N`, `dead-lettered: N`. With the daemon
   unreachable it prints `queue counters unknown (daemon unreachable)`, never `0`.
7. **Re-drive (nm23-1, #t9-fixes).** Daemon op and verb `queue_redrive(queue)` (CLI
   `rmx learn redrive`, MCP parity through the verb-parity test). Under the queue's own append
   path it re-appends every line of `<queue>.deadletter.jsonl` to the live queue file, then renames
   the dead-letter file to `<queue>.deadletter.<ts>.redriven.jsonl`, which is kept forever (the
   history of what failed). It returns the line count. A re-driven line that fails again is
   dead-lettered again and counted again. `queue_status` reports the dead-letter file's current
   line count beside `dead_lettered_total`.

### R7 Fragment flush failures are surfaced and retried (#t8-amendments d2a) {#r7}

Inside the harness a fragment flush failure rolls the batch back (R1.3) and is retried with it.
Outside the harness, `Store.transaction`'s post-`COMMIT` flush failure stops being a bare `print`:
it increments `Store.fragment_flush_failures`, keeps the fragments dirty for the periodic flush to
retry, logs to `rmxd.log`, and is reported by `queue_status` and `_store_health`.

### R8 `replica_merge` cannot roll an offset back: RETIRED (d9ao) {#r8}

**RETIRED (d9ao, round 6; ns23-r6-3 option (b)).** Nothing in 23.1 implements or tests this
requirement, and `replica_merge.py` / `duckdb_catalog.py` are not in 23.1's file list. Reason:
writer rotation is dropped (`Daemon._refresh_replica_now`, `daemon.py:2814`, is a no-op and the
refresh thread is not started), so no live path produces two diverged slots; and the frozen
inactive slots predate the queue tables (`queue_offsets`, `queue_counters`, `bounded_runs`), so
no slot pair can hold diverged rows of them. `replica_merge` itself is broken on every real store
(bug-113, open: an `init_catalog` target that lacks `entities.vectors_partition`, an explicit
table list), and an AC built on `init_catalog` slots would have passed while the production
command fails.
- **The frozen slots are a separate item (d9ao).** `rmx replica audit` (2026-10-15) found rows
  present only in the inactive slot on atldb, refmatrix and viascope (by id); a by-name census
  decides recover (after bug-113's fix) or discard. That item is not 23.1's.
- **bug-113 is not a 23.1 dependency.** If a later plan revives slot merging, it adds the queue
  tables to both `init_catalog` and `merge_slots`' table list and writes its own AC through
  `_op_replica_merge` on `Store.init()` slots.
- Original text, kept as history: "`replica_merge` merges `queue_offsets` by taking, per
  `(queue, segment)`, the larger `offset_bytes` (and `finalize_pending` and `events_pending`
  from that row), and `queue_counters` by elementwise max. Folded tables carry their own
  monotone rule (19.2 R6 `memory_usage`, 16.6 R1c sidecar); 23.1 does not edit them."

### R9 Re-base `learn_queue` on R3, and correct its docstrings {#r9}

1. Learn becomes `BoundedQueue(…, key_fn=pattern+partition, merge_fn=UNION by (file, line),
   max_lines=MAX_QUEUE_LINES, idempotent=True)` (true only through R9.5, checked by AC-16) drained with `scope="segment"`, `batch=1` (one
   coalesced pattern per hold, the contract `test_the_drain_yields_the_writer_lock_between_entries`
   pins), `budget_s=LEARN_DRAIN_BUDGET_S`, the daemon's fatal classifier, registered as `learn` in
   R6. Its partition is the store's project partition, bound explicitly through `bind`, not
   "whatever is bound at rest".
2. Behaviour that changes, each with its own RED test: the bug-099 loss (R3.3); the remainder is
   left in its segment instead of re-appended (R2); a non-fatal failure is dead-lettered instead of
   dropped after a log line (R2).
3. Every other existing test in `tests/test_learn_queue.py`, `tests/test_learn_broker_bounded.py`
   and `tests/test_learn_toggle_sites.py` passes unchanged. A test whose assertion encodes the old
   behaviour is listed in the implementation summary with its old and new assertion (known:
   `test_the_drain_stops_at_its_budget_and_requeues_the_rest` asserts the log word `requeued`; its
   `pending_lines == 10` assertion stays).
4. The superseded "ONE lock acquisition" text is corrected in the `learn_queue.py` module
   docstring, the `_drain_learn_queue` docstring, the `_runner` comment, and the
   `tests/test_learn_queue.py` module docstring and section header (23 #m-3).
5. **Learn's evidence write is insert-if-absent (nb23-2, bug-106, #t9-fixes).** A new
   `Store.add_evidence_if_absent(linkage, concept_id, entity_id, *, file, line, span_end=None,
   detail=None) -> bool` inserts the row only when no `linkage_evidence` row has the same
   `(entity_id, linkage_id, concept_id, file, line)` (one `INSERT … SELECT … WHERE NOT EXISTS`;
   no schema change, because the table already holds duplicates and a unique index would fail to
   build). It returns whether it inserted, and emits the `facts.log` `evidence` event ONLY when it
   did (inside the harness, into R1.3's post-commit buffer, so a rolled-back insert leaves no
   event). `_learn_grep_hits` uses it for every `(file, line)`. `add_evidence` itself is unchanged
   for its other callers. This also stops today's duplication when the same pattern is learned
   twice with no crash. The duplicates already in live stores are plan-22's to audit (bug-106
   row). Plan-16's 16.1 R4 ("write only the missing evidence rows") builds on this method.
   - What a replay may still repeat, stated: `upsert_entity` is `INSERT … ON CONFLICT` and `link`
     sets a bit, so the CATALOG state is idempotent. A re-applied entry can append a second
     `entity` event to `facts.log`; replaying it re-upserts the same row, so a rebuild from the
     log is unchanged. AC-16 counts evidence rows and `evidence` events, which must not repeat.

### R10 The consumer contract, by exact name (ns17-2) {#r10-contract}

Every consumer task (16.6, 17.1, 19.2, 22.2, 23.3) names these, and only these:

| name | signature | notes |
|---|---|---|
| `bind` | `bind(partition_name: str) -> ContextManager[Handle]` | supplied by the owner: `daemon_bind(d)` (daemon), `serial_bind(store)` (non-daemon, 23.3 R3); names, never ids; raises `UnknownPartition`; never creates a partition |
| `drain` | `drain(queue: BoundedQueue, *, bind, apply, batch=1, budget_s, cancel, on_error, hold_alarm_s, finalize=None, prepare=None, scope="window") -> RunResult` | R3 |
| `tail` | `tail(log: TailLog, *, bind, apply, batch=1, budget_s, cancel, on_error, hold_alarm_s, finalize=None, prepare=None) -> RunResult` | R4 |
| `bounded_steps` | `bounded_steps(items: list, *, bind, partition_of: Callable[[Any], str], apply, batch=1, budget_s, cancel, on_error, hold_alarm_s, finalize=None, prepare=None) -> RunResult` | R5; `partition_of` gives each step's partition NAME |
| `RunResult` | R1.5, including `hold_s` and `finalize_ran` | |
| `Daemon.tick_registry` | `register(name, runner, *, kind)` | the DAEMON tick only (R6). The hub's nightly steps are a different registry, plan-17's `maintenance_steps` |
| `queue_status`, `queue_redrive` | daemon ops + verbs | R6.5, R6.7 |
| `Store.batch_transaction` | `batch_transaction() -> ContextManager[None]`; raises `NestedTransaction` | R1.3: pre-flush, `BEGIN`, in-transaction flush, offset, `COMMIT`, post-commit events |
| `Store.has_dirty_fragments`, `Store.dirty_fragment_count` | `has_dirty_fragments() -> bool`, `dirty_fragment_count() -> int` | every binding (R1.1 item 3); the only "anything dirty" tests |
| `Store.add_evidence_if_absent` | `add_evidence_if_absent(linkage, concept_id, entity_id, *, file, line, span_end=None, detail=None) -> bool` | R9.5; also used by 23.3's semantic writes ([[task-23.3-sync-between-file-yield#r8]]) and 16.1 R4 |
| `Store.repair_fragments` | `repair_fragments(*, dry_run=True, manifest_dir=None, id_map=None) -> dict` | the hotfix's union-with-manifest repair as merged (R1.1 items 4-7; `id_map` is merge's collision map); not re-implemented by 23.1. Not to be confused with 17.1's `vectors_restore(id_map=…)`, a different parameter on a different op |

Where an earlier spec says "`bind(batch)`", it means `bind(partition_name)` entered once per batch.

## Acceptance criteria {#acceptance}

Holds and writes are counted by 23.2's `HoldRecorder` on a REAL `_FairLock` installed through
`recorded_daemon`, never by the drain's own return value (23 #s-4).

**The alive-links oracle (nm23-r6-1, bug-111).** Wherever an AC below compares a fragment row to
"the bitmap rebuilt from `entity_links`", it means the bitmap of that partition's `entity_links`
rows for that linkage whose entity exists AND whose concept id is in `entities` or `concepts`
(R1.1 item 6, the same gate `repair_fragments`' links half applies at 0.78.1). A dangling row
contributes no bit and is never deleted by 23.1's code.

1. **Holds and yields.** 1,000 events with 1,000 DISTINCT keys, `batch=200`: the recorder counts
   exactly 5 holds, and a competitor queued on the lock before each release wins between EVERY
   consecutive pair (4 ordered wins recorded by the recorder's thread names). Mutation: one hold
   around all batches FAILS. {#ac-1}
2. **SUM coalesce.** 1,000 events over 10 keys with a SUM `merge_fn`, `scope="window"`: the 10
   totals equal the per-key event counts. Constructing a `BoundedQueue` or `TailLog` without
   `merge_fn` raises `TypeError`. Mutation: a last-wins merge FAILS. {#ac-2}
3. **Partition binding (23 #b-1).** Two batches for partition `pa`. Between them a competitor takes
   the lock, enters `with_partition("pb")`, writes one row, and releases WHILE STILL BOUND (the
   bug-098 shape). After the drain, 0 rows of the drain's batches are in `pb` and all are in `pa`.
   An event naming an unknown partition raises; nothing is written to partition 1. Mutation: hoist
   the bind outside the batch loop FAILS. {#ac-3}
   - **AC-3b fragment rows (nb23-1, bug-105).** In the same run, both the drain's batches and the
     competitor write `mentions` links (the competitor links one `pb` entity and releases while
     bound, leaving a dirty `pb` fragment in the cache). After the drain, and after a fresh `Store`
     reopens the catalog: `pa`'s `bitmap_fragments` row for `mentions` holds no bit whose entity's
     `partition_id` is `pb`'s, `pb`'s row holds none of `pa`'s, and each row equals the bitmap
     rebuilt from that partition's ALIVE `entity_links` rows (the alive-links oracle). The
     fixture carries one dangling `(pa, mentions)` row whose concept is dead under item 6: before
     the drain, by SQL that bypasses purge, the concept's `concepts` row AND its `entities` row
     are both deleted (nm23-r7-3: deleting only the `entities` row leaves the id in `concepts`,
     which keeps the concept ALIVE under item 6 and the 0.78.1 gate, so "its bit is in no row"
     would fail against correct code). After the drain the row is still in `entity_links` and
     its bit is in no row. The check is a SQL + pyroaring census over the
     ROWS, not the cache. Mutations, each must FAIL: the cache keyed by linkage only (HEAD's
     shape); a flush that writes every dirty entry under the id bound at flush time.
   - **AC-3c no auto-create.** `bind("no-such-partition")` raises `UnknownPartition`, and
     `SELECT count(*) FROM partitions` is the same before and after. Mutation: `bind` calling
     `with_partition(name)` with the default `create=True` FAILS (the count rises).
   - **AC-3d the binding leaks AC-3b cannot see (nb23-r3-1, nb23-r4-1).** Every case reads the
     `bitmap_fragments` ROW by SQL (a fresh cursor on the store's connection, decoded with
     pyroaring) BEFORE any close, never through the cache, because `close()` flushes every
     binding. Partitions `home` (the at-rest binding) and `pb`.
     - **The hotfix's suite, as merged, is part of this AC and is not rewritten.** At 23.1's
       FIRST commit and at its last, the FIVE files `tests/test_fragment_partition_scope.py`,
       `tests/test_fragment_repair_audit.py`, `tests/test_fragment_repair_audit_r2.py`,
       `tests/test_fragment_repair_audit_r3.py` and `tests/test_fragment_repair_audit_r4.py`
       (nm23-r6-1; round 5 named four) pass unchanged on `master` (the first run also
       proves the `Depends on:` merge happened: the files exist). They pin, by their merged
       names:
       - (ii) rename keeps both bits: `test_rename_with_dirty_cache_keeps_both_bits`;
       - (iii) merge re-homes persisted rows: `test_merge_moves_persisted_fragment_rows`;
       - (iv) transaction exit flushes the other binding:
         `test_transaction_exit_flushes_other_binding`;
       - (vi) an unlink made in merge's lock-yield gap is NOT resurrected:
         `test_merge_interleaved_unlink_is_not_resurrected`;
       - (vii) a fragment-only bit whose concept is a live doc entity survives
         `repair_fragments`: `test_repair_keeps_a_fragment_only_bit_whose_concept_is_a_live_doc`;
       - (viii) merge's colliding ids are remapped, not dropped:
         `test_p7_merge_collision_bits_are_remapped_not_reported_dropped`;
       - (ix) the lock rule (R1.1 item 5): a recorder asserts the writer lock is held at every
         `flush_fragments` / `repair_fragments` call in merge and at the home-binding rebind:
         `test_merge_store_wide_flush_and_repair_run_under_the_writer_lock`,
         `test_p3_home_binding_rebind_happens_under_the_writer_lock`;
       - (x) the d9ae fence and the r2 survivor pins, in `_r4.py`: the live merge is refused
         (`test_daemon_refuses_a_live_merge_sync_and_async`); `_periodic_flush` flushes another
         binding's dirty bits (`test_periodic_flush_persists_another_bindings_dirty_bits`, M1,
         the pre-image of 23.1's case (i)); `links_skipped` counts a dangling link
         (`test_links_skipped_counts_a_link_to_a_missing_entity`, M11); the canonical verb on
         the links side (`test_repair_files_a_legacy_snake_verb_link_under_the_canonical_kebab_name`,
         M14). R6.1 keeps `_periodic_flush(store, lock, log)` (`daemon.py:228`) as the tick's
         flush body with its signature unchanged, so the M1 test needs no rewrite.
       If the merged branch names a test differently, the implementation summary maps each case
       to the merged name; a case with no merged test is written by 23.1 in this shape.
     - **23.1's own cases** (the code 23.1 changes):
       - (i) **Other binding dirty at the tick.** Link one `pb` entity under
         `with_partition("pb")` outside any transaction and return to `home`, which is clean.
         One `_runner` tick, now through `tick_registry` (R6.1). `pb`'s `mentions` row holds
         the bit.
       - (v) **No binding-local DECISION** (nm23-r4-1). A search of `src/` for a decision on a
         binding-local view, `rmx grep -nE '\b(if|while|and|or|not)\b .*\._(dirty_)?fragments\b|\b(len|bool)\(.*\._(dirty_)?fragments\b' src/`
         (at `fb285cc` it hits `store.py:4163` and `:4219` only),
         returns hits only inside `_load_fragment`, `_flush_current_binding` and
         `_flush_fragments_duckdb` (each hit's enclosing `def` is read by the test with `ast`).
         A mere mention (setting or discarding a bit, as `save_bitmap`, `bulk_link`,
         `link_many`, `purge_entity`, `_bulk_purge_ids` and the merge helpers do) is not a
         decision and is not searched for, so the case passes on the merged code without an
         allow-list of mentioning methods, and it covers `store.py` itself.
     - **Mutations, each must FAIL the named case.** 23.1's own: `_runner`'s / the tick's guard
       back on `_dirty_fragments` → (i); a new `if self.store._dirty_fragments:` in `daemon.py`
       → (v); a new `if self._dirty_fragments:` added to `Store.transaction` → (v). The hotfix's
       code, killed by its merged suite (re-run, not re-written, by 23.1's mutation pass): the
       merge's END block clearing instead of flushing → (vi); the concepts-table-only alive
       predicate → (vii); `id_map` not passed by merge → (viii); merge's pre-flush, or its end
       flush + repair, outside `lock` → (ix); the home-binding rebind outside `lock` → (ix);
       `rename_partition` without its pre-flush and cache clear → (ii); merge without its
       closing `repair_fragments` → (iii). Round 3's "`merge_partition` without its pre-flush
       → (iii)" is DROPPED: on the merged code the end flush + repair re-home a bit that skipped
       the pre-flush, so that mutant passes (iii) and was never a valid kill (nb23-r4-1; the
       clone's r2 audit reported it, M5, as surviving). Its lock-rule replacement is (ix).
4. **Exactly-once across the windows (d2a, 23 #b-2).** A COUNTING AND LINKING `apply`
   (ns23-r4-1): per batch it adds the event count to one counter row AND links one fresh entity
   per event into `(pa, mentions)` under one concept, so every batch dirties a fragment and the
   in-transaction flush (R1.3 step 3) has bits to write. 600 events, `batch=100`. A fault is
   injected at each of: (a) after `apply`, before the offset write; (b) after the offset write,
   before `COMMIT`; (c) after `COMMIT`, before the segment bookkeeping; (d) inside the
   in-transaction fragment flush; (e) a SIGKILL-shaped `os._exit(137)` mid-`apply`. (a), (b),
   (d) raise in-process; (c) and (e) run the drain in a spawned child process (not `rmx`, not a
   fork of a process holding DuckDB) on the same tmp root.
   - **The check, after each fault.** (a), (b), (d): in the SAME process and on the SAME
     `Store` (no close, no reopen), the drain resumes to completion; then ONE more `link` into
     `(pa, mentions)` outside the harness and one `flush_fragments()`; then: the counter equals
     600; `entity_links` holds exactly 600 + 1 `mentions` links under the concept; and the
     `(pa, mentions)` `bitmap_fragments` row, read by SQL, equals the bitmap rebuilt from
     `pa`'s alive `entity_links` rows (the alive-links oracle). The extra link-and-flush is what makes a phantom visible: a
     rolled-back bit left in the cache as a CLEAN entry is written back only when a later link
     dirties that entry. (c), (e): the child is dead, so a fresh `Daemon` + `Store` drains to
     completion and the same three equalities hold after the same extra link-and-flush.
   - **Mutations, each must FAIL:** the offset written in its own autocommit after `COMMIT`
     (double count at (c)); the offset written before the batch (loss at (a)); fragments
     flushed after `COMMIT` (at (d) the fault fires after the batch's links and offset have
     committed; the error path's cache drop then discards their only copy of the bits, and the
     resumed drain starts past that batch, so the row lacks bits that `entity_links` holds); the
     cache NOT dropped on rollback (at (b) the rolled-back links' bits stay as clean cache
     entries and the extra link-and-flush writes them: the row holds bits with no
     `entity_links` row); the drop done by dirty marks instead of `_clear_fragment_caches()`
     (same failure as "not dropped", because step 3 already cleared the marks).
   - **(f) Pre-existing dirty bits survive a rollback (ns23-r3-1).** Before the batch, one
     committed but unflushed `link` in `(pa, mentions)` and one in `(pb, mentions)` (outside the
     harness, so they wait for the periodic flush). The batch also links into `(pa, mentions)` and
     faults at (b). After recovery (no close in between), both rows read by SQL contain their
     pre-existing bit, and each equals the bitmap rebuilt from its partition's alive
     `entity_links` rows.
     Mutation: `batch_transaction` without the pre-flush FAILS (the `pa` bit is dropped with the
     batch's entry, and the `pb` entry was flushed inside the rolled-back transaction and
     un-dirtied). {#ac-4}
5. **bug-099 (RED at HEAD).** Enqueue 3 learn records; drain in a spawned child that `os._exit`s
   after the rotate, before any apply; restart. At HEAD: 0 learned rows and 0 pending (the loss).
   After 23.1: 3 patterns applied, 0 pending, no pattern applied twice. A legacy `*.draining` file
   present at boot is adopted and applied. {#ac-5}
6. **Segment scope is refused for non-idempotent queues.** `scope="segment"` on a queue without
   `idempotent=True` raises at construction. {#ac-6}
7. **Stop paths.** Budget: remainder pending, `stopped="budget"`. Shutdown: `cancel()` true →
   nothing applied, all pending. Fatal invalidation: repair marked, deferred exit armed, the failed
   batch not applied and still pending. Non-fatal error: the batch is in the dead-letter file,
   `dead_lettered_total` is 1, the queue moves on. Hold alarm: a hold over `hold_alarm_s` logs the
   alarm with its counts and the run continues. {#ac-7}
8. **Finalize once (23 #b-3).** A 22.2-shaped apply over 5 batches that collects Lance deletes and
   issues them in `finalize`: 23.2's `max_writes_per_run(lance_versions=<kinds>)` passes. A crash
   after the last batch and before finalize: the next run runs finalize first, once. Mutation: the
   delete issued per batch FAILS the per-run count. {#ac-8}
9. **O(1) statements per batch.** A batch of 10 and a batch of 100 events through a bulk `apply`
   execute the same number of statements per hold (± 2, 23.2 R3). A consumer `apply` that loops one
   upsert per event FAILS `max_writes_per_hold`. {#ac-9}
10. **Tail.** A concurrent appender writes 1,000 lines, the last one torn (no newline). The fold
    reads exactly the complete lines; the file's inode, size and bytes are unchanged afterwards;
    the next run picks up the torn line once it is completed. Drop the folded table and reset the
    offset: a re-fold yields identical rows (the drop-and-replay property 19.2 relies on). {#ac-10}
11. **Tick registry.** Three registrants (a drain, a tail, a `bounded_steps` runner), each able to
    use the whole budget: one tick's total registrant time ≤ `LEARN_DRAIN_BUDGET_S` + one hold;
    over 3 ticks every registrant runs at least once; the fragment flush runs every tick. Mutation:
    a per-registrant budget FAILS (the tick takes ~3× the budget). {#ac-11}
12. **Overflow surface.** On a sandboxed daemon (23.0) serving a short tmp socket, overflow the
    learn queue by 7 with learning ON: `rmx learn status` prints `overflow (dropped, total): 7`.
    With the daemon stopped it prints `queue counters unknown (daemon unreachable)`. Mutation:
    print only when learning is off FAILS. {#ac-12}
13. **RETIRED (d9ao) with R8.** No test is written for it, and it is not in the test list.
    Reason: [[#r8]] (rotation dropped, no producer of diverged slots; the frozen-slot census is a
    separate d9ao item; bug-113 is not a 23.1 dependency). Original text, kept as history:
    "**`replica_merge`.** Two slots whose `queue_offsets` rows differ: the merged row carries the
    larger offset; `queue_counters` carries the elementwise max. Mutation: keep the A-side row
    FAILS when A is older." {#ac-13}
14. **Fragment flush failure is surfaced.** A failing post-`COMMIT` flush in `Store.transaction`
    increments `fragment_flush_failures`, keeps the fragment dirty, and the next periodic flush
    writes it; `queue_status` reports the count. {#ac-14}
15. **Learn tests.** The R9.3 test files pass; the docstrings named in R9.4 no longer say "ONE lock
    acquisition" (`rmx grep -n 'ONE lock acquisition'` on those files returns nothing). {#ac-15}
16. **Learn replay is idempotent, checked (nb23-2, bug-106).** Three learn patterns whose hits
    total D distinct `(pattern, file, line)` triples, `scope="segment"`, `batch=1`. A spawned child
    drains and `os._exit(137)`s after hold 1 of 3 commits; a fresh `Daemon` + `Store` drains to
    completion. Then: `linkage_evidence` holds exactly D learn rows, the store's `facts.log` holds
    exactly D `evidence` events for them, and the `mentions` fragment row equals the bitmap rebuilt
    from the alive `entity_links` rows. A second, crash-free learn of the same three patterns adds 0 evidence
    rows and 0 `evidence` events. Mutation: `_learn_grep_hits` back on the plain `add_evidence`
    INSERT FAILS (rows > D). {#ac-16}
    - **AC-16b a kill INSIDE a hold (ns23-r3-2).** The same three patterns. The spawned child
      `os._exit(137)`s inside hold 2, after its first `add_evidence_if_absent` and its first `link`
      and before `COMMIT`. A fresh `Daemon` + `Store` drains to completion. Then `facts.log`
      holds exactly D `evidence` events for the learn rows (none from the killed hold twice), and
      every `link` event in it names a link present in `entity_links` (no event for a link the
      rollback removed). A second case kills after `COMMIT` and before the event append: the
      catalog holds hold 2's rows and its `queue_offsets` row has `events_pending = true`;
      `facts.log` lacks hold 2's events (the stated at-most-once residual, R3.7). Then a plain
      RESTART of the daemon, with no manual force and with the log far below the compaction
      threshold: the boot check compacts, `rmxd.log` has one line naming the queue, the flag is
      false, and the log's `evidence` count is D (ns23-r4-2). Mutations, each must FAIL:
      `_log_event` appending to `facts.log` at once inside `batch_transaction` (no buffer) → the
      first case (D + hold 2's events); no boot check → the second case (evidence count < D);
      the flag cleared inside the transaction instead of after the append → the second case
      (the flag is false after the kill and the boot does nothing); the boot check calling
      `_compact_factslog_if_needed(force=True)` inside its own `with self._store_lock:` (the
      non-re-entrant self-deadlock, nm23-r6-2) → the second case, whose restart must answer
      `ping` within 10 s and does not.
17. **Dead-letter re-drive.** One learn batch fails non-fatally (dead-lettered, AC-7); the fault is
    removed; `rmx learn redrive` reports 1 line; the next drain applies it; the dead-letter file is
    gone and its `*.redriven.jsonl` copy holds the line. Mutation: a redrive that unlinks the
    dead-letter file instead of renaming it FAILS (the kept copy is missing). {#ac-17}
18. **`batch_transaction` refuses to nest (nm23-4).** Entering `batch_transaction()` inside an open
    `Store.transaction()` raises `NestedTransaction`, and no row is written. Mutation: let it fall
    through to the nested no-op FAILS this case. Secondary claim, against AC-4's LINKING `apply`
    (ns23-r4-1): with the fall-through, AC-4 run inside an outer `Store.transaction()` puts the
    fragment flush after the outer `COMMIT`, so fault (d) no longer rolls the batch's links back
    and AC-4's fragment-row equality FAILS. {#ac-18}
19. **`hold_s` is production data.** A `bounded_steps` run over 3 items with `batch=1` and a
    finalize returns `len(hold_s) == 4`, `finalize_ran` true, each entry within 50 ms of the hold
    23.2's recorder measured for the same hold, and `max_hold_s == max(hold_s)`. Mutation: return
    only `max_hold_s` (an empty `hold_s`) FAILS. {#ac-19}
20. **ADOPTED (d9ag) with R1.6: the writer-lock check fires.**
    - `_FairLock`: after `acquire` (fast path, and as a woken waiter) `held_by_current_thread()`
      is True in the holder and False in every other thread; after `release` it is False
      everywhere; a waiter whose `acquire` timed out in the hand-off race never reports True.
    - On a recorded daemon whose writer Store was installed by `_install_writer_store`:
      `flush_fragments()`, `repair_fragments(dry_run=False)`, `with_partition("pb")`,
      `Store.transaction()`, `batch_transaction()` and `purge_entity(<id>)` each raise
      `WriterLockNotHeld` when called from a thread without the lock, and write nothing (the
      `bitmap_fragments`, `partitions` and `entities` rows are unchanged). Each succeeds under
      `with d._store_lock:`. A Store with no `writer_lock` runs all six unlocked (the in-process
      path).
    - **Purge writes NOTHING, Lance included (ns23-r7-1).** The purge case is run three times,
      once each through `purge_entity(<id>)`, `_bulk_purge_ids([<id>…])` and
      `purge_path(<abs>)`, on an entity WITH a stored vector. Each raises from its first-line
      check (R1.6 item 3), and after the raise: the entity's Lance dataset `version` is
      unchanged, `ann_search` / a direct Lance read still returns that id's vector, its
      `vectors_updated_at` is unchanged, and the three catalog tables are unchanged.
    - **Shutdown keeps the last dirty bit (nb23-r7-1).** A recorded daemon serves on a short
      tmp socket with the periodic flush tick disabled (interval far above the test's length).
      One `link` under `with d._store_lock:` leaves a dirty `(home, mentions)` fragment; then
      `d.stop` with no tick in between. After a fresh `Store` opens the slot, the
      `bitmap_fragments` row (read by SQL) holds the bit, and `rmxd.log` has no "store close"
      error line. A second case holds `_store_lock` from a test thread across the whole stop:
      `rmxd.log` has the line `store close: writer lock not acquired in …; 1 dirty fragment(s)
      NOT flushed`.
    - **Init rebind under the lock.** A recorded daemon booted, check ON, on a store whose
      active slot file exists while its Store opened `catalog.duckdb` (the condition at
      `daemon.py:1722-1726`) takes the rebind: `rmxd.log` has `init slot rebind: db_path -> …`
      and NO `init slot rebind: close failed` line, and the recorder shows the rebind's
      flush and close inside one hold by the booting thread.
    - **The check survives a reopen (ns23-r6-2).** On the same recorded daemon, with no slot
      files, `d._bootstrap_rotation_if_needed()` closes the writer and reopens it on slot A (the
      `:2924` site); then, with `A` removed, it reopens through the asymmetric-repair site
      (`:2888`). After each, `d.store` is a different object from before (a reopen really
      happened) and `flush_fragments()` from an unlocked thread still raises
      `WriterLockNotHeld`. (These sites, not `_op_replica_merge`'s, because bug-113 makes the
      replica-merge reopen fail; its three sites are covered by the AST case.)
    - **One installer, by AST (nm23-r7-1).** A test parses `daemon.py` and finds no assignment
      to an `Attribute` named `store` (`Assign`, `AugAssign`, `AnnAssign` with a value, a
      tuple-unpacking element, or `setattr(…, "store", …)`), whatever its value, outside
      `Daemon._install_writer_store`, except the one `AnnAssign` of `None` in
      `Daemon.__init__`. The test also asserts that exemption matches exactly one node, so a
      second `None` declaration elsewhere fails it.
    - **A lock replaced after install is the lock checked.** After the writer Store is
      installed, the test assigns a fresh 23.2 `HoldRecorder` to `d._store_lock` (the shape of a
      recorder installed after the Store opened): an op under `with d._store_lock:` (the new
      recorder) succeeds, and an unlocked `flush_fragments()` raises.
    - The WARN-mode census run's site list is in the implementation summary, and every site on
      it is MOVED UNDER THE LOCK (nb23-r7-1; no site is resolved by naming it safe). A second
      WARN-mode run after the moves lists zero sites; its log is captured beside the first.
    - Mutations, each must FAIL: the check removed from `flush_fragments`; `_owner` not set on
      the woken-waiter path (the holder reports False and every op under the lock raises); one
      of the 8 sites assigning `self.store = Store(…)` directly instead of through the helper
      (FAILS the AST case, and, at `:2924` or `:2888`, the reopen case); `writer_lock` captured
      as the lock object at install time instead of a callable (FAILS the replaced-lock case:
      the op under the new recorder raises); the check removed from `_clear_purged_bits` (FAILS the
      `purge_entity` case: the purge writes unlocked); **round 7 (nm23-r7-1, ns23-r7-1,
      nb23-r7-1, nm23-r7-2):** the `:5557` site rewritten as the two-statement
      `st = Store(…); …; d.store = st` (FAILS the AST case; round 6's rule passed it); the purge
      check kept ONLY in `_clear_purged_bits` (FAILS the purge case: the Lance `version` is
      +1 and the vector is gone, for each of the three entry points); `_do_close` calling
      `close()` without taking the lock (FAILS the shutdown case: the check raises inside
      `close()`, the bit is missing from the row); `Store.close()` swallowing
      `WriterLockNotHeld` as before (FAILS the shutdown case: the bit is missing AND no
      "store close failed" line); the init rebind left outside `with self._store_lock:`
      (FAILS the init-rebind case: a "close failed" line); `HoldRecorder` without
      `held_by_current_thread` (FAILS the replaced-lock case with `AttributeError` instead of
      the expected results). Round 5's "merge's end block taken out of
      its `with _lk:`" is DROPPED: since the d9ae fence that path runs only offline with no
      `writer_lock`, so the check cannot see it; the hotfix suite's (ix) still pins the offline
      merge's lock rule (nm23-r6-1). {#ac-20}

## Files to modify {#files}

Added in revision round 7 (nb23-r7-1, nm23-r7-2), so the edits the round-6 text implied have an
owner. Not exhaustive for R1-R9's new modules; it names every EXISTING file 23.1 changes.

| file | change |
|---|---|
| `src/refmatrix/bounded.py` (new) | R1-R6's core, front-ends and tick registry |
| `src/refmatrix/store.py` | `with_partition(create=)`; `batch_transaction`; the event buffer; `writer_lock` + `_require_writer_lock` at R1.6 item 3's sites, purge's three first-line checks included; `Store.close()`'s flush step no longer swallows `WriterLockNotHeld` and records other errors in `close_errors` (R1.6 item 4); `add_evidence_if_absent`; `fragment_flush_failures` |
| `src/refmatrix/daemon.py` | `_FairLock` owner + `held_by_current_thread`; `_install_writer_store` at the 8 sites; `_do_close` under a bounded `_store_lock` acquire; the init slot rebind inside `with self._store_lock:`; `_compact_factslog_locked`; the boot `events_pending` check; `tick_registry`; `queue_status` / `queue_redrive`; learn re-based |
| `src/refmatrix/learn_queue.py`, `verbs.py`, `cli.py`, `mcp.py` | R9; `rmx learn status` / `redrive` and their verbs |
| `tests/lockhold.py` | `HoldRecorder.held_by_current_thread()`, one explicit pass-through (R1.6 item 1; nm23-r7-2). 23.2's other surface is unchanged |

## Test strategy {#test-strategy}

- Every test runs inside task 23.0's sandbox (d1a/d1b): redirected `$HOME`, global root and
  registry, injected store roots, the refuse guard on, children refused outside the tmp dir.
- In-process `Daemon(root)` + real `Store` on a short `mkdtemp` root (the `test_learn_queue.py`
  `_daemon_with_store` shape), built through 23.2's `recorded_daemon` so the recorder IS
  `_store_lock` from the first op; `daemon.ping` False.
- Faults (c) and (e) run in a spawned Python child that opens its own `Store` after the parent has
  closed its handle; the parent never forks while holding a DuckDB connection.
- Only AC-12 runs `rmx`, against a daemon on the sandbox's tmp socket.
- The 23.0 touches log gains 0 lines for this task's files.
- Logs: `workflow/review-output/pytest-bounded.log`.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 23 #b-1 (no partition rule across yields; bug-098) | [[#r1]] 1-2, [[#ac-3]] |
| 23 #b-2 (marker outside the transaction; AC kills at a boundary) | [[#r3]] 3-5, [[#ac-4]], [[#ac-5]] |
| 23 #b-3 (per-row writes invisible; no finalize) | [[#r2]] finalize, [[#ac-8]], [[#ac-9]]; 23.2 R3 |
| 23 #s-1 (N per hold vs learn's contract; four stop paths) | [[#r2]], [[#r9]] 1, [[#ac-7]] |
| 23 #s-2 (key-only coalesce) | [[#r3]] 1, [[#ac-2]] |
| 23 #s-3 (not queue-shaped consumers; tick registry; plan-21) | [[#r4]], [[#r5]], [[#r6]], [[#ac-11]]; plan [[plan-23-bounded-write-harness#consumers]] |
| 23 #s-4 (holds counted by the drain; `_FairLock`; 23.2 first) | [[#acceptance]] preamble, [[#ac-1]] |
| 23 #s-5 (bound is a warning) | [[#r2]] `hold_alarm_s` |
| 23 #s-6 (overflow has no route to `learn status`) | [[#r6]] 5-6, [[#ac-12]] |
| 23 #s-7 (kill / sandbox undefined) | [[#test-strategy]], [[#ac-4]] |
| 23 #m-3 (stale ONE-acquisition docstrings) | [[#r9]] 4, [[#ac-15]] |
| d2a (offset in the batch's DuckDB transaction) | [[#r1]] 3, [[#r3]] 4, [[#ac-4]] |
| #t8-amendments d2a (fragments; `replica_merge`; retained replay source) | [[#r7]], [[#r8]], [[#r4]] 2 and 4, [[#ac-13]], [[#ac-14]] |
| d2b (`bind` seam, Option A not folded in) | [[#r1]] 1 |
| d2d (bug-099 fixed by 23.1) | [[#r3]] 3, [[#ac-5]] |
| d4a + #t8-amendments d4a (non-consuming tail reader; tick registry; one budget) | [[#r4]], [[#r6]], [[#ac-10]], [[#ac-11]] |
| #t2-fixes (`bind` per batch inside the hold + two-partition AC; recorder + finalize; one event per hold, budget/shutdown/error/requeue; required `merge_fn`; real `_FairLock`; every batch released; overflow through a daemon op) | [[#r1]], [[#r2]], [[#r3]], [[#r6]], [[#ac-1]], [[#ac-3]] |
| decision-log #s-1 (exactly-once boundary, fragments, `replica_merge`, retention) | [[#r3]] 7, [[#r7]], [[#r8]], [[#r4]] |
| decision-log #s-3 (tail mode, tick registry, 23.3 on `bounded_steps`) | [[#r4]], [[#r5]], [[#r6]] |
| decision-log #m-3 (16.6 rides the overflow-dropping queue) | [[#r3]] 6 (counted, persisted, printed); 16.6's lower-bound reading is 16.6's |
| d1a/d1b (sandboxed tests) | [[#test-strategy]] |

## Revision round 2 (2026-10-14) {#rev-round-2}

| finding / decision | answered at |
|---|---|
| nb23-1 (fragment cache unbound; `with_partition` auto-creates) | [[#facts]], [[#r1]] 1 and 3, [[#ac-3]] (AC-3b, AC-3c) |
| d9a (bug-105 hotfixed now; 23.1 owns the contract going forward) | [[#r1]] 1 (mechanism (a) or (b); the live repair is the hotfix's) |
| nb23-2 (learn not idempotent), bug-106, #t9-fixes "learn evidence insert-if-absent" | [[#r3]] 5, [[#r9]] 1 and 5, [[#ac-16]] |
| nm23-1 (dead-letter retention, re-drive), #t9-fixes "dead-letter kept with a re-drive" | [[#r2]] `on_error`, [[#r6]] 7, [[#ac-17]] |
| nm23-4 (name the batch primitive; no silent nesting) | [[#r1]] 3, [[#ac-18]] |
| ns17-2 (17.1's names; per-hold seconds) | [[#r1]] 5 (`hold_s`), [[#r10-contract]], [[#ac-19]] |
| ns17-1 (daemon tick registry vs hub step registry) | [[#r10-contract]] (`Daemon.tick_registry` is daemon-only) |

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]] and the bug-105 hotfix's audit remedies
(`4fb803b`, read read-only in the clone).

| finding / decision | answered at |
|---|---|
| nb23-r3-1 (hotfix adopted "unchanged" but leaks: binding-local guards, name in the key, merge under a dropped id; AC-3b blind) | [[#facts]] (round 3), [[#r1]] 1 (the five-point contract; "adopted, with AC-3d"), [[#r6]] 1, [[#r10-contract]], [[#ac-3]] AC-3d (i)-(v) with six mutations |
| ns23-r3-1 (rollback drops pre-batch dirty bits and un-dirties other bindings) | [[#r1]] 3 (step 1 pre-flush before `BEGIN`; exact drop), [[#ac-4]] (f) |
| ns23-r3-2 (`facts.log` events inside holds that roll back) | [[#facts]] (round 3), [[#r1]] 3 (step 5 post-commit buffer), [[#r3]] 7 (event log post-commit; residual stated), [[#r9]] 5, [[#ac-16]] AC-16b |
| nm23-r3-2 (repair described as "rebuilt from `entity_links`") | [[#facts]] (round 3), [[#r1]] 1 (union with manifest; d9a's wording corrected) |
| d9a (bug-105 hotfix now; 23.1 owns the contract) | [[#r1]] 1 item 5 (built on, or carried as the first commit) |
| d9k (ADR-0004 `#rule-no-delete`: manifest-backed derived cleanup) | [[#r1]] 1 (the repair's classification) |
| ns23-r3-3 (23.3 uses `add_evidence_if_absent`) | [[#r10-contract]] (`Store.add_evidence_if_absent` row); [[task-23.3-sync-between-file-yield#r8]] |

## Revision round 5 (2026-10-14) {#rev-round-5}

Source: [[bsd-plan23-17-spec-rereview-r4-878647c]], the user's writer-handle idea (its
`#writer-handle` section), and the shared round-5 rule that a spec adopting a hotfix depends on
the hotfix MERGED TO `master`, never on a sha list.

| finding / decision | answered at |
|---|---|
| nb23-r4-1 (contract described `4fb803b`; "clears again"; no lock rule; concept-alive undefined; cherry-pick fallback; unkillable AC-3d (iii) mutant) | header `Depends on:` (hotfix merged to `master`), [[#facts]] round 5, [[#r1]] 1 items 4-7, [[#r10-contract]] (`repair_fragments(id_map=)`), [[#ac-3]] AC-3d (the merged suite as cases (ii)-(ix); mutations reassigned; the (iii) no-pre-flush mutant dropped, replaced by (ix)) |
| nb23-r3-1 (partial in r4: the spec trailed the code) | the nb23-r4-1 row: the contract now follows the merged code, not a sha |
| ns23-r4-1 (counting `apply` dirties no fragment; fresh-Store check tautological; rollback drop undefined; AC-18 claim) | [[#r1]] 3 ("How the drop is done": `_clear_fragment_caches()`), [[#ac-4]] (linking `apply`; same-process check after one more link and flush), [[#ac-18]] |
| ns23-r4-2 (at-most-once event residual closed only by a never-forced compaction) | [[#facts]] round 5 (size gate + floor), [[#r3]] 4 (`events_pending` column) and 7 (flag set in the transaction, cleared after the append, boot-time forced compaction), [[#r8]], [[#ac-16]] AC-16b second case (plain restart; two new mutations) |
| nm23-r4-1 (AC-3d (v) allow-list fails on the merged code) | [[#facts]] round 5 (decisions vs mentions), [[#ac-3]] AC-3d (v) (search for a decision, not a mention) |
| nm23-r4-2 item 1 (slot offsets have no reader) | [[#facts]] round 3 note + round 5, [[#r3]] 7 |
| writer-handle idea (held-lock assert; non-harness writers) | [[#r1-6-proposed]] (PROPOSED: `_FairLock` owner, `Store.writer_lock`, `WriterLockNotHeld` at five methods + the rebind sites, WARN-mode census first), [[#ac-20]] (PROPOSED). Needs the user. |

## Revision round 6 (2026-10-15) {#rev-round-6}

Source: [[bsd-plan23-17-spec-rereview-r6-0e77da3]] and [[plan-review-2026-10-14#t12-approvals]]
(d9ao), with d9ag (R1.6 ADOPTED as written) and d9aj (older revision tables keep PROPOSED as
history; only live labels change) applied. Code facts re-read at HEAD `3d3c798`. The round-5
table above is unchanged history.

| finding / decision | answered at |
|---|---|
| ns23-r6-1 (R1.6 / AC-20 still PROPOSED, with a removal clause, after d9ag) | header status, [[#r1]] 1 item 5, [[#r1-6-proposed]] ("ADOPTED (d9ag)"; the "if the user declines" sentence deleted), [[#ac-20]] ("(removed if the user declines)" deleted); plan [[plan-23-bounded-write-harness#open-after-revision]] 7 SETTLED |
| ns23-r6-2 (`writer_lock` set at one of 8 writer-Store sites; captured lock goes stale; bug-110 scope) | [[#facts]] round 6 (the 8 sites), [[#r1-6-proposed]] item 2 (`writer_lock` a callable; ONE installer `Daemon._install_writer_store`; AST rule) and item 5 (thread lock only; DuckDB `fcntl` lock is `_copy_out_of_process`'s rule), [[#ac-20]] (reopen case at `:2924` / `:2888`, AST case, replaced-lock case; three new mutations) |
| ns23-r6-3 (R8 / AC-13 on a `replica_merge` bug-113 breaks), d9ao option (b) | header (`Not gated on bug-113`), [[#facts]] round 6, [[#r8]] RETIRED (reason; frozen-slot census is a separate d9ao item; bug-113 not a dependency), [[#ac-13]] RETIRED |
| nm23-r6-1 (hotfix moved: d9ae fence, fifth test file, bug-111's links gate and direct purge rebind; item 7 correction not done) | [[#facts]] round 6, [[#r1]] 1 items 5 and 7 (correction pass) and the repair bullet, [[#r1-6-proposed]] (merge dropped from the live-writer list; `_clear_purged_bits` added to item 3), [[#r6]] 1 (`_periodic_flush` kept), [[#acceptance]] preamble (alive-links oracle), [[#ac-3]] (AC-3b dangling fixture row; AC-3d five files, case (x)), [[#ac-4]], [[#ac-16]], [[#ac-20]] (`purge_entity` case; the fenced-merge mutant dropped) |
| nm23-r6-2 (boot compaction "in the same hold" vs the non-re-entrant lock) | [[#facts]] round 6, [[#r3]] 7 step 3 (`_compact_factslog_locked()` factored out; read, compact and clear in ONE hold), [[#ac-16]] AC-16b (self-deadlock mutation) |


## Revision round 7 (2026-10-15) {#rev-round-7}

Source: [[bsd-plan23-17-spec-rereview-r7-331b414]]. Code facts re-read at HEAD `77ac38f`
(`src/` unchanged since `0e77da3`). d9az (plan-23 owns the non-harness `_store_lock` holders and
the heartbeat's coupling to the cli pool) is answered by a NEW task,
[[task-23.5-read-path-and-holder-bounds]], not here: 23.1 stays the harness. The round-6 table
above is unchanged history.

| finding / decision | answered at |
|---|---|
| nb23-r7-1 (the "named safe" census route; the check raises inside `Store.close()`'s bare `except` at shutdown and inside the init rebind's `try`) | [[#facts]] round 7, [[#r1-6-proposed]] item 4 (route withdrawn; every site moved under the lock; `_do_close` under a bounded acquire with a logged dirty count on timeout; the init rebind in `with self._store_lock:` with `close()` in a `finally`; `Store.close()` re-raises `WriterLockNotHeld` after closing and records other flush errors), [[#ac-20]] (shutdown case, its lock-held variant, init-rebind case, second census run with zero sites; three mutations), [[#files]] |
| ns23-r7-1 (purge's check fires after its Lance delete; the AC cannot see Lance) | [[#facts]] round 7, [[#r1-6-proposed]] item 3 (first-line checks in `purge_entity`, `_bulk_purge_ids`, `purge_path`; the rebind check kept), [[#ac-20]] (purge case ×3 entry points asserts the Lance `version`, the vector and `vectors_updated_at`; mutation "check only at the rebind") |
| nm23-r7-1 (the AST rule matches only `x.store = Store(…)`) | [[#facts]] round 7 (the `AnnAssign` at `daemon.py:728`; `cli.py`'s in-process sites out of scope), [[#r1-6-proposed]] item 2 (any assignment form, any value; one exemption by location and shape), [[#ac-20]] (AST case; mutation: the two-statement form at `:5557`) |
| nm23-r7-2 (`HoldRecorder`'s approved surface lacks `held_by_current_thread`) | [[#facts]] round 7, [[#r1-6-proposed]] item 1 (23.1 adds one explicit pass-through in `tests/lockhold.py`; 23.2's approved spec is not reopened), [[#files]], [[#ac-20]] (mutation) |
| nm23-r7-3 (AC-3b's dangling fixture row is alive by its `concepts` row) | [[#facts]] round 7, [[#ac-3]] AC-3b (delete the concept from `concepts` AND `entities`) |
| ns-x-r7-1 (19.2 R6/AC-10 and 16.6 R1c still build on `replica_merge` after d9ao) | not owned here: plans 19 and 16 own it ([[bsd-plan23-17-spec-rereview-r7-331b414#ns-x-r7-1]]). 23.1's side is unchanged: [[#r8]] stays RETIRED and names no consumer rule as live |
| d9az (non-harness holders; heartbeat coupling) | [[task-23.5-read-path-and-holder-bounds]]; plan [[plan-23-bounded-write-harness#scope-d9az]] |
