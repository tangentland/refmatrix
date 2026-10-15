---
gmd: "0.1"
id: bsd-plan23-17-spec-rereview-r4-878647c
title: "plan-23 + plan-17 spec re-review r4: 23.1 adopts the bug-105 hotfix at 4fb803b, which 27b3653 superseded for two BULLSHIT defects; AC-4's fragment mutations cannot fire; 23.4's by-key dealing ignores cross-key dependencies; 17.1's id_map has no caller; 17.4's restore never restores the catalog and resets offsets nothing reads"
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: spec-rereview-r4-23.0-23.4-and-17.1-17.4
round: 4
tags: [bsd, audit, spec-review, re-review, plan-23, plan-17, partition, fragments, bug-105, option-a, facts-log, wave-1]
---

# ch-bsd spec re-review r4 of plan-23 and plan-17 at `878647c` {#root}

**Commit reviewed:** `878647c` (branch `wave0-spec-reviews`). The round-3 spec revision is
`a820b22`; `878647c` adds d9p-d9u and touches no plan-17/23 file. **Written:**
2026-10-14T14:08:13-0700. HEAD moved to `224495c` (14:06:48) while I worked. That commit adds
d9v and d9w to the decision log only, and touches no plan-17/23 file.

**Scope:**
- plan-23 with tasks 23.0-23.4, and plan-17 with tasks 17.1-17.4;
- my round-3 report [[bsd-plan23-17-spec-rereview-r3-6091648]];
- decisions d9k-d9o, d9p-d9u and #t10-waves in [[plan-review-2026-10-14]];
- the cross-plan text these specs cite: 22.2 R4/R6, 19.4 AC-2, plan-18 `#contract-2026-10-14`
  and `bug_registry.md` rows 099 and 105-108;
- the bug-105 hotfix clone `/Volumes/littlebig/refmatrix-bug105`, branch
  `bug-105-fragment-partition`, head `27b3653` (13:54:57).

**Method:**
- Each round-3 id was traced to the anchor in its `#rev-round-3` row, and the text there was read.
- Every code fact a fix relies on was read with `git show` / `sed` at HEAD (`daemon.py`,
  `store.py`, `cli.py`, `ingest_records.py`, `models_local.py`) and in the clone at `27b3653`
  (`git show 27b3653:<path>`; the clone's two audit reports included).
- The clone was read only: nothing was run, nothing was written. No `rmx` call touched a live
  store, and no test was run.

rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: specifies -> [[plan-23-bounded-write-harness]]
rel: specifies -> [[plan-17-nightly-store-maintenance]]
rel: related-to -> [[project_bug098_writer_partition_race]]
rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

## Round-3 findings: status {#prior-status}

| id | status | evidence at `878647c` (spec) / HEAD and clone `27b3653` (code) |
|---|---|---|
| nb23-r3-1 hotfix leaks the binding | **partial** | All three leaks are closed in code at `27b3653`: `_runner` guards on `has_dirty_fragments()` (`daemon.py:2066`); `Store.transaction`'s post-commit flush does the same (`store.py:4517`); `rename_partition` flushes and clears before it renames (`store.py:1614-1616`); merge flushes before it remaps and repairs after. 23.1 R1.1 states a five-point contract, and AC-3d (i)-(v) has six mutations. However, the contract text describes `4fb803b`, which `27b3653` superseded for two BULLSHIT defects. One AC-3d mutation cannot fire against the adopted code. See [[#nb23-r4-1]]. |
| ns23-r3-1 rollback drops pre-batch bits | closed | R1.3 step 1 pre-flushes before `BEGIN` and asserts the set is clean. AC-4(f) reads rows by SQL, and its no-pre-flush mutation fires. The rollback DROP itself has no case that can kill its mutation ([[#ns23-r4-1]]). |
| ns23-r3-2 events of rolled-back holds | closed | R1.3 step 5 buffers events until `COMMIT`; R3.7 states the residual; AC-16b's no-buffer mutation fires. **Correction to my r3 text:** its "A/B slot delta-replay" leg was false, because nothing reads the slot offsets ([[#nm23-r4-2]]). The `rebuild_index_from_log` leg stands. The residual's closure is new work ([[#ns23-r4-2]]). |
| ns23-r3-3 concurrent syncs | closed | 23.3 R8 adds `_sync_mutex`, a lock order and `add_evidence_if_absent`. AC-9 has three mutations. One nit on how the AC forces the race: [[#nm23-r4-3]]. |
| ns23-r3-4 23.4 oracle by id (+4 items) | closed as asked (d9m) | All five items and the positive control are in place (R3, R4, R6, AC-1, AC-3). The corrected procedure has new soundness holes: [[#ns23-r4-3]]. |
| nm23-r3-1 status stated three ways | closed | The header, `#ranges` and plan open item 1 all say CONFIRMED d9l / d9m. |
| nm23-r3-2 repair described as a rebuild | closed | 23.1 R1.1 describes a union with a manifest and classifies it under ADR-0004 `#rule-no-delete` (d9k). |
| nm23-3 (carried) stale bug-099 row | closed in the registry | `bug_registry.md:152` now records d2a. Plan-23 open item 6 still calls the row stale ([[#nm23-r4-2]]). |
| ns17-r3-1 `vectors_restore` by id vs new ids | **partial** | 17.1 R1/R10 and AC-8b add `id_map`. Plan-22 neither names `id_map` nor keeps the old id, and its own finalize deletes the vectors in question ([[#ns17-r4-1]]). |
| ns17-r3-2 confirm sha per run | closed | 17.1 R6 uses a candidate file and sha per dataset, a list parameter, the intersection with current orphans, and `new_since_confirm`. AC-7 has the churn and per-dataset cases, plus three mutations. 17.3 step 4 matches. |
| ns17-r3-3 no staleness alarm; step order | closed | 17.2 R2 registers the backup first and makes steps independent, with `after_idle`. R8 checks backup age on every wake, also under `off`. AC-13, AC-14 and 17.4 AC-8 test it. A clock nit is in [[#nm17-r4-1]]. |
| ns17-r3-4 restore overwrites the live log | closed as asked | 17.4 R6 orders the script: throwaway rebuild, verify, move aside, install. Half of my r3 premise was false (the offsets have no reader), and the runbook restores the wrong thing ([[#ns17-r4-2]]). |
| nm17-r3-1 17.1 leftovers | closed | R10 uses `bind(partition_name)` per dataset with no `hold_s`, cancel or budget. AC items are numbered 1-14 uniquely, and the AC-13 mutation is listed. |
| nm17-r3-2 arm gate order | closed | 17.2 R7 requires an earlier dry-run line, and `invoked_by` is the surface, set by the adapter. AC-12 and AC-13 test it. |
| nm17-r3-3 R4 polls the wrong op | closed | 17.2 R4 polls each step's own op; AC-13 checks it. |
| nm17-r3-4 17.3 clone `HOME` | closed | 17.3 R2 steps 5-6 state the no-model daemon (`RMX_NO_EMBED_WARMUP`, `daemon.py:1161`; `HF_HUB_OFFLINE`, `models_local.py:50`), the build-time rate log, and that the AC fails rather than shrinking. |
| nm17-r3-5 19.4 AC-2 vs arming | closed (plan-19) | 19.4 AC-2 is now day-1 `dry_run:unarmed`, then a hand dry run and a real run, then arm (`task-19.4…:102-112`). Plan-17 open item 6 still says "still asserts" ([[#nm17-r4-1]]). |
| nm17-r3-6 17.4 AC-3 / `fclonefileat` | closed | AC-3 compares against the SOURCE catalog's name-keyed hash; R4 states the `ctypes` call; AC-10 forces the stream fallback. |

**Closure:** of 18 round-3 ids (8 for plan-23 including carried nm23-3, 10 for plan-17), 16 are
closed and 2 are partial (nb23-r3-1, ns17-r3-1). {#prior-status-body}

## New findings: plan-23 {#findings-23}

### BULLSHIT nb23-r4-1: 23.1's adopted contract is the hotfix at `4fb803b`, which `27b3653` superseded for two BULLSHIT defects; its fallback cherry-pick list omits the fix, and one AC-3d mutation cannot fire {#nb23-r4-1}

**Where:** 23.1 `#facts` round 3 ("commits `0d05525`, `20c5ab4`, `4fb803b`; line numbers are the
clone's at `4fb803b`"); R1.1 item 4 (`merge_partition` "at its end clears again and runs
`repair_fragments`"); R1.1 item 5 ("23.1's first commit carries `0d05525`, `20c5ab4` and
`4fb803b`"); R1.1 repair text ("a bit whose CONCEPT is gone"); AC-3d mutations.

**What:** the clone's ch-bsd r2 audit of `4fb803b` (committed in the clone at `27b3653`,
`…-1335-bug105-hotfix-r2-unlocked-merge-repair-and-concept-predicate-4fb803b.md`) found two
BULLSHIT defects in exactly the mechanism 23.1 adopts. `27b3653` (13:54:57, one minute before
`a820b22`) fixes both:
- **#b2-1.** Merge's pre-flush and its end block ran OUTSIDE `with _lk:`, and the daemon merge op
  does not hold `_store_lock` (`daemon.py:4094`, `:4120`; the lock is taken per chunk inside
  `merge_partition`). `flush_fragments` rebinds `_partition_id` while it writes, which is the
  bug-098 shape. Separately, the END `_clear_fragment_caches()` discarded an unlink made in a
  lock-yield gap, and the union repair then wrote the bit back from the stale row. `27b3653`
  wraps both blocks in `with _lk:` and FLUSHES instead of clearing at the end
  (`store.py:1697-1700`, `:1960-1962` at `27b3653`).
- **#b2-2.** The repair called a concept dead when it had no `concepts` row. On the probe copy
  that labelled 4,439 bits dead where 410 were, and it deleted fragment-only bits whose concept is
  a live doc or memory entity. `27b3653`: a concept is alive if its id is in `entities` OR
  `concepts` (`store.py:4347-4351`).

23.1's text matches `4fb803b`, not `27b3653`:
- R1.1 item 4 says "clears again", which is the resurrection defect.
- It gives no rule that a store-wide fragment step runs under the writer lock.
- It leaves "concept is gone" undefined.
- Item 5's fallback commit list ends at `4fb803b`. A 23.1 started before the merge would carry
  both BULLSHIT defects and leave out `tests/test_fragment_repair_audit_r2.py`, the only test that
  pins them.
- The same commit, `a820b22`, updated the bug-105 row in `bug_registry.md:158` to "27b3653 r2
  remedies (merge's fragment work under the writer lock, flush not clear; a concept is alive if
  in `entities` or `concepts`)". So the spec contradicts the registry it ships beside.

**The AC-3d (iii) mutation cannot fire.** "`merge_partition` without its pre-flush → (iii)": at
`27b3653` the end block flushes and then runs the union repair. A dirty `pb` bit that skipped the
pre-flush is therefore flushed under `pb`'s (dropped) id and re-homed by the repair. `home` holds
the bit, and no row stays under the dropped id. The mutant passes (iii). The clone's r2 audit
already reported this mutant (M5) as surviving. No 23.1 AC covers the unlink-in-a-yield-gap case
or the live-concept case.

**Why it is bullshit:** 23.1 "owns the contract from then on". A contract that tells the next
editor to clear before the repair, and a fallback that ships a lossy concept predicate, would
reintroduce defects that are already fixed. This repeats nb23-r3-1: a hotfix adopted by
description, with the description behind the code.

**Fix (about 15 lines of spec):**
- R1.1 item 4 follows `27b3653`:
  - every store-wide fragment step in merge (the pre-flush and clear, and the end flush and
    repair) runs under the writer lock merge was given;
  - the end FLUSHES, never clears;
  - a concept is alive if its id is in `entities` or `concepts`.
- Item 5 drops the cherry-pick fallback: **23.1 starts only after the hotfix branch has merged to
  `master`**, at its final audited sha, including the r2/r3 test files. Name that as a hard
  `Depends on:` line rather than a list of shas that keeps going stale.
- AC-3d gains:
  - (vi) an unlink made in merge's lock-yield gap (the progress callback) is NOT resurrected;
  - (vii) a fragment-only bit whose concept is a live doc entity survives `repair_fragments`.
- Mutations: "end clear instead of flush" → (vi); "concepts-table-only predicate" → (vii).
- Replace the unkillable "merge without pre-flush" mutation with "merge's pre-flush outside
  `lock`". It is killed by a recorder that asserts the lock is held at every
  `flush_fragments` / `repair_fragments` call (the clone's
  `test_merge_store_wide_flush_and_repair_run_under_the_writer_lock` shape).

**Pattern match:** YES. `#imp-guards-read-the-old-shape` (r3) and nb23-r3-1: the spec trails the
hotfix by one audit round, for the second round running.

### SKETCHY ns23-r4-1: AC-4's counting `apply` dirties no fragment, so its two fragment mutations and AC-18's secondary claim cannot fire, and the rollback-drop rule has no killing case {#ns23-r4-1}

**Where:** 23.1 AC-4 ("A COUNTING `apply` (adds the event count to one counter row)"; "a fresh
`Daemon` + `Store` drains to completion … the fragment cache equals the database's
`bitmap_fragments` rows"; mutations "fragments flushed after `COMMIT` (loss at (d))" and "the
cache not dropped on rollback"); AC-18 ("AC-4's fault (d) then also FAILS"); R1.3 (on rollback
"the cache entries the batch dirtied are dropped").

**What:**
- The counting `apply` writes one counter row and links nothing, so:
  - fault (d) "inside the in-transaction fragment flush" flushes nothing;
  - moving the flush after `COMMIT` loses nothing;
  - the counter is 600 under every fragment mutation.
- "The cache equals the rows" is checked on a FRESH `Store`, whose cache is empty and lazy-loads
  from those rows, so it is equal by construction.
- The "cache not dropped" mutation therefore survives AC-4, and AC-4(f) only kills the
  no-pre-flush mutation. Here is why (f) misses the drop:
  - step 3's in-transaction flush already DISCARDED the dirty marks;
  - at fault (b), the batch's rolled-back bit sits in the cache as a CLEAN entry;
  - nothing reads it until a later link in the same `(pa, mentions)` dirties the entry and
    flushes the phantom bit;
  - (f) reads rows right after recovery, so it cannot see that.
- R1.3 also leaves open how "entries the batch dirtied" is known once step 3 has cleared the
  marks.

**Fix:**
- AC-4's `apply` also links one entity per event into `(pa, mentions)`.
- The post-recovery check is "every `bitmap_fragments` row equals the bitmap rebuilt from
  `entity_links`", made in the SAME process after one more link and flush into `(pa, mentions)`.
- R1.3 says how the drop is done. Because step 1 left nothing dirty at `BEGIN`, a rollback can
  drop EVERY binding's cache (`_clear_fragment_caches()`) exactly. State that, so no
  implementation looks for dirty marks the flush has already discarded.
- Rewrite AC-18's secondary claim against the linking `apply`.

### SKETCHY ns23-r4-2: R3.7's at-most-once `facts.log` residual is closed only by a compaction that production never forces, and nothing detects it {#ns23-r4-2}

**Where:** 23.1 R3.7 ("the next `facts.log` compaction (`dump_catalog_to_log`) re-derives the log
from the catalog, which closes the gap"); AC-16b second case ("after a forced `facts.log`
compaction the log's `evidence` count is D").

**What:**
- Compaction is size-gated with a floor that holds it off "until it grows past" on big stores
  (`daemon.py:2297-2311`), so "the next compaction" can be weeks away. Nothing records that a
  batch's events were lost, so nothing forces one.
- The rows at risk are learn rows: the learned grep rows that 17.4 #why calls "the one store file
  that cannot be regenerated", which exist only in the catalog and `facts.log`.
- 17.4's daily copy then backs up a log without them. A restore from that copy (the disaster
  case 17.4 exists for, [[#ns17-r4-2]]) loses them for good.
- AC-16b proves the closure through a manual `force=True` that no production path takes. That is
  the "benchmark a path users do not run" shape.

**Fix:**
- `batch_transaction` writes `events_pending=true` on the batch's `queue_offsets` row inside the
  transaction (for `bounded_steps`, a one-row marker table). After the append it clears the flag
  in a tiny follow-up write.
- At daemon boot, any set flag forces `_compact_factslog_if_needed(force=True)` (under the lock,
  logged).
- AC-16b's second case asserts the evidence count D after a plain RESTART, with no manual force.
  Mutation: no boot check FAILS.

### SKETCHY ns23-r4-3: 23.4's corrected procedure still biases the oracle: by-key dealing ignores cross-key dependencies, the absolute dead-bit check fires on any live copy, and "that file's `st_birthtime`" is the copy's {#ns23-r4-3}

**Where:** 23.4 R3 (dealt "by a hash of their row key's NAMES … so every write to one key stays
on one thread in log order"; the window "whose `ts` is later than that file's `st_birthtime`" of
"the copied `facts.log`"); R6 ("a bit whose id resolves to no entity is itself a mismatch");
`#ranges` (d9l numbers, d9m procedure, "neither … change … without a new user decision").

**What:**
1. **Cross-key dependencies.** A link transaction `(src, linkage, dst)` needs both entities, and
   their creates (or deletes) sit on OTHER threads because they are dealt by the entity's key.
   At N > 1:
   - a link can run before its entity's create commits, so it fails or creates the entity
     itself with defaults;
   - or it can run after a later delete of that entity.

   Either way the by-name end state depends on the interleaving, `integrity_mismatch` follows, and
   the verdict is NO-GO for an artifact. This is r3's id defect, moved from ids to dependency
   order. The positive control (AC-3) does not require a cross-thread create→link pair, so it
   cannot catch it.
2. **The dead-bit check is absolute, not differential.** A copy of a live snapshot already holds
   dead bits:
   - 410 on the census copy (clone r2 report #b2-2);
   - the bug-105 rows under a dropped `partition_id`;
   - new ones that keep regrowing through `purge_entity`'s bound-partition sweeps (clone r2
     #m2-1).

   So R6 fires at N = 1, the result is INVALID, and it stays INVALID for as long as the copy has
   them.
3. **Birth time.** Copying `facts.log` creates a new inode, so "the copied `facts.log`'s
   `st_birthtime`" is the copy time. No event is later than it, so the workload is 0 events and
   the result is always INVALID. The live file's birth time is the intended value. (Compaction
   emits snapshot events with historical `ts` values, `store.py:7264-7275`, so the filter works
   when it reads the live file's birth time.)

**Fix (the numbers stay; the procedure changes, so the user re-acknowledges, as with d9m):**
- Deal by dependency, not by one key. A transaction waits until every EARLIER transaction (in log
  order) that touches any entity name it touches has committed: a per-name log-position barrier.
  Per-name order then holds for every key a transaction touches, so the end state is
  interleaving-independent by construction.
- The positive control includes a create on thread 1 followed by a link to it dealt to thread 2.
- Count dead bits and unknown-partition rows in the REFERENCE run and in each measured run; a
  difference is the mismatch. Alternatively, run `repair_fragments(dry_run=False)` on the tmp
  copy before the reference and record its report.
- R3 reads `st_birthtime` from the LIVE `facts.log` with `os.stat` in the copy phase (a stat is
  not an open, so AC-5's two-open count holds) and records it. AC-7 adds a case on a copied
  fixture.

### MEH nm23-r4-1: AC-3d (v)'s search fails on the adopted code or gets loosened {#nm23-r4-1}

- The allow-list names the two properties, `_dirty_bindings`, `_clear_fragment_caches`,
  `link` / `unlink` / `_load_fragment` / `flush_fragments` and the repair.
- At `27b3653`, `store.py` also touches `_dirty_fragments` / `_fragments` in eight methods the
  list does not name:
  - `save_bitmap` (`:4472`);
  - `bulk_link` (`:4762`);
  - `link_many` (`:4847`);
  - `purge_entity` (`:6018`, `:6029`);
  - `_bulk_purge_ids` (`:6336`);
  - `_merge_fragment_all_partitions` (`:4133`);
  - `_drop_legacy_fragment_raw` (`:4114`);
  - `_flush_current_binding` / `_flush_fragments_duckdb` (`:4212-4262`).
- As written, (v) fails on correct code. The likely "fix" is to search outside `store.py` only,
  which misses a binding-local guard creeping back inside it.
- Fix: search for a DECISION, not a mention: `if .*_dirty_fragments` / `len(.*_dirty_fragments)`
  anywhere in `src/` outside `_flush_current_binding` and `_flush_fragments_duckdb`.

### MEH nm23-r4-2: three cited facts are false at HEAD {#nm23-r4-2}

- **Nothing reads the slot offsets.**
  - 23.1 `#facts` round 3 says "the A/B slots delta-replay from byte offsets into the same file
    (`daemon.py:2789`)"; R3.7 repeats it, and so does 17.4 #why.
  - At HEAD, `_read_slot_offset` (`daemon.py:2796`) has no caller.
  - Writer rotation is dropped, and the refresh thread "is no longer started"
    (`daemon.py:2812-2828`, `_refresh_replica_now`).
  - Offsets are WRITTEN (compaction `:2321`, the upgrade seed `:2841`) and never read.
  - This error came from my r3 text (ns23-r3-2, ns17-r3-4). The `rebuild_index_from_log` leg is
    real.
- **bug-099 is not stale.** Plan-23 open item 6 says the bug-099 row still reads "pending with
  the user". `bug_registry.md:152` records d2a, through `a820b22` itself.
- **AC-1's spec-sha check has nothing to compare against.** 23.4 AC-1 refuses a jsonl "whose
  recorded spec sha differs from the one the confirmation names". d9m (`5a8bf29`) names no sha.
  Its procedure text landed afterwards, in `a820b22`. `git log -S'rev-round-3'` also stops
  returning one commit as soon as a later revision adds or removes a `[[#rev-round-3]]`
  reference. Fix: name the sha in the decision row that confirms the next amendment, and compare
  against that literal value.

### MEH nm23-r4-3: 23.3 AC-9 does not force the race it tests {#nm23-r4-3}

- "Started together from two threads" does not guarantee that sync B is queued before sync A's
  first release. If A drains first, the "no `_sync_mutex`" mutant passes.
- Fix: a barrier. B's first `bind` is enqueued on the recorder's lock (visible in its wait queue)
  before A's first step releases.

{#findings-23-body}

## New findings: plan-17 {#findings-17}

### SKETCHY ns17-r4-1: `vectors_restore`'s `id_map` has no caller: 22.2 keeps no old id, never names the map, and deletes the removed entities' vectors itself {#ns17-r4-1}

**Where:**
- 17.1 R1 and R10 ("Plan-22's 22.2 … passes `old_id → new_id` from its manifest"), AC-8b;
- plan-17 open item 3 (`plan-17…md:265`: "plan-22's revision names the parameter");
- `task-22.2-repair-then-remove.md:107-110` (the manifest keeps "its whole `entities` row except
  `id`"), `:123-126` (restore through `vectors_restore`, no map), `:152-154` (Lance deletes
  "finalized once per kind").

**What:**
- A search of plan-22 for `id_map` returns nothing.
- 22.2's manifest drops the id, so 22.2 cannot build `old → new`.
- 22.2's own finalize deletes the vectors of the entities it removes, so those vectors are never
  plan-17 orphans and never reach an orphan list.
- 17.1's new parameter, its AC-8b and its two mutations therefore test a path no consumer can
  call: a dead-code contract. Plan-17's "settled" text asserts a plan-22 edit that does not exist.

**Fix (pick one, and write it in BOTH plans):**
- (a) 22.2's intent record keeps the old `id`, and the vector rows it is about to delete in
  finalize (the 17.1 orphan-list format, under `.refmatrix/removal/`). 22.2's restore calls
  `vectors_restore(<that file>, id_map=…)`, and 22.2 AC-4 asserts byte-equal vectors under the
  new ids.
- (b) Drop `id_map`. State that 22.2 re-embeds, and that `vectors_restore` serves only same-id
  restores of plan-17 reaps.

(a) keeps derived state without a model call. (b) is honest and smaller. Either way plan-17 open
item 3 stops claiming the other plan's text.

**Pattern match:** YES. `#imp-restore-shares-a-key` (r3). My r3 prescription assumed 22.2's
manifest kept the id; it does not.

### SKETCHY ns17-r4-2: 17.4's restore never restores the catalog, and resets offsets nothing reads; it serves no stated failure {#ns17-r4-2}

**Where:** 17.4 R6 (steps 1-3; "the catalog itself … is not touched by this script"; "writes BOTH
`catalog.A.offset` and `catalog.B.offset`"), AC-9, the AC-6 mutation "not resetting the offsets",
17.3 R3 docs, plan-17 open item 5.

**What:** R6 names no scenario. The two real ones are:
- **(a) The live log is damaged and the catalog is healthy.** `dump_catalog_to_log` (a forced
  compaction) re-derives the full log and loses nothing. R6 instead installs a copy up to a day
  old beneath a newer catalog, which loses that day from the log.
- **(b) The disaster 17.4 exists for.** The catalogs and Lance data are excluded from Time
  Machine (`tm-exclusions.sh`, 17.4 #why) and so is the live log (R7). After a restore only
  `backups/` comes back.
  - R6 then rebuilds into a throwaway, verifies it, and DISCARDS it.
  - "Move the live log aside" has no live log to move.
  - The live root keeps NO catalog.
  - Nothing replays the installed log at daemon start.
  - The learned rows the backup holds never reach the store unless the operator knows to run a
    rebuild on the live root. The runbook does not say so.
- **The offset write is ceremonial.** `_read_slot_offset` has no caller ([[#nm23-r4-2]]). So
  AC-9's offset check and the AC-6 mutation test a write that no reader consumes. My r3 premise
  ("the next delta-replay applies the wrong records") was false.

**Fix:** state both scenarios in R6:
- (a) is `rmx` compaction with `force`, never the backup.
- (b) rebuilds the LIVE root from the copy after the throwaway verification:
  - the daemon is stopped;
  - the verified throwaway catalog is promoted into the live root's active slot;
  - the installed log matches it;
  - the daemon starts.

Drop the offset requirement, or keep it only as "consistent with the promoted slot", with no AC
of its own. AC-9 runs scenario (b): delete the catalogs and the live log, run the script, start
the daemon, and the entity and learned-row counts equal the copy's.

### MEH nm17-r4-1: small items {#nm17-r4-1}

- **17.4 AC-8's daemon clause cannot pass as written.**
  - Only the hub's clock is injected, while the copy's `copied_at` is wall time (the op receives
    only `today`).
  - The daemon's `_store_health` reads its own wall clock, so it sees age ≈ 0 and stale false.
  - Fix: back-date `meta.json` (17.2 AC-14's shape), or inject the daemon's clock.
- **17.1's restore signature is stated two ways.** R1's verb list gives `vectors_restore(…,
  invoked_by=…)`, and the "exactly" signature omits `invoked_by`. R12 also writes ledger lines
  only for `vectors_maintain`. Say whether restore records its surface.
- **Plan-17 open item 6 is stale.** It says 19.4 AC-2 "still asserts plan + apply". 19.4 AC-2 now
  arms by run id (closed in plan-19).
- **Plan-18 contradicts 17.2.** Plan-18 `#contract-2026-10-14:50` says the backup and a CHECKPOINT
  "must not run on the same store at the same time". 17.2 R2 says the backup is consistent under
  any concurrent write and leaves `after_idle` to plan-18. Plan-18 should either justify the
  constraint or drop it; nothing in the copy reads the catalog.

{#findings-17-body}

## The writer-handle idea vs 23.1's `bind` {#writer-handle}

The user's idea is `with d.writer(partition) as w:`. The handle owns the lock and the binding,
re-sets the binding after every yield, flushes on exit, and adds a held-lock assert in Store
writers. Here is what 23.1 already gives, and what it lacks.

- **Already given, for harness consumers only:** `daemon_bind(d)` takes `_store_lock`, then
  `with_partition(name, create=False)` inside the hold, and exits both in one `with` (R1.1).
  `batch_transaction` flushes inside the transaction (R1.3). No binding is held across a release,
  so there is no "re-set after yield" because nothing yields inside it. For learn, 16.6, 17.1,
  19.2, 22.2 and 23.3, that IS the handle, minus the assert.
- **Not given:**
  1. **The held-lock assert.** Nothing in 23.1 makes `link`, `flush_fragments`,
     `repair_fragments` or `with_partition` check that the writer lock is held. The hotfix's r2
     #b2-1 was exactly that bug: `merge_partition` took the lock as an OPTIONAL argument
     (`lock if lock is not None else nullcontext()`), and its store-wide flush ran unlocked. An
     assert would have failed the first test.
  2. **Coverage of non-harness writers.** These keep their own `with d._store_lock:` and
     ad-hoc rebinding:
     - every `_op_*` that writes;
     - merge's chunked lock yield;
     - `_partition_keeping_yield`;
     - `Store.transaction` callers.

     23.1's AC-3 even keeps the bug-098 competitor ("releases WHILE STILL BOUND") as a legal shape.
     A writer handle would make that shape impossible rather than tolerated.
- **Verdict:** 23.1's `bind` is the writer handle's harness-scoped half. The assert, and the
  migration of `_op_*` writers onto the same handle, would be new scope. Not demanded here.
  [[#nb23-r4-1]]'s lock-held recorder check is the minimal, test-side form of the assert.

{#writer-handle-body}

## Cross-plan consistency {#cross-plan}

| question | answer |
|---|---|
| 23.1 R1.1 vs the hotfix head `27b3653` | **Conflict:** the spec describes `4fb803b` ([[#nb23-r4-1]]); `bug_registry.md:158` (same commit) describes `27b3653`. |
| 17.1 `id_map` vs 22.2 | **Conflict:** 22.2 keeps no id, names no map, and deletes the vectors itself ([[#ns17-r4-1]]). |
| 17.4 restore vs the slot-offset model | The offsets are unread at HEAD ([[#ns17-r4-2]], [[#nm23-r4-2]]). |
| 23.3 R4 purge-on-edit vs d9p / 22.6 R4 | Compatible. 23.3's per-file step calls `purge_path`; 22.6 R4 makes it keep learned rows on edit; 23.3 AC-6's "same graph as HEAD" is read at 23.3's implementation time. 23.3 lands before 22.6 in #t10-waves, so 22.6 must re-run 23.3's AC-6 fixture. Worth one line in 22.6, not a finding here. |
| 17.2 step order vs plan-18's contract | Plan-18's "must not run at the same time" is unexplained ([[#nm17-r4-1]]). |
| 19.4 vs 17.2 R7 | Consistent now (19.4 AC-2 arms by run id); plan-17 open item 6 is stale. |
| Wave order | #t10-waves: 23.0 ∥ 23.4, 23.2 → 23.1 → 23.3; 17.1 → 17.2 → 17.4 after 23.1; 17.3 in Wave 2. The specs' `Depends on:` lines agree. [[#nb23-r4-1]] adds "after the hotfix merges" to 23.1. |

{#cross-plan-body}

## Needs the user {#needs-user}

1. **23.4's procedure ([[#ns23-r4-3]]).** d9m froze it. Dependency-ordered dealing, a
   differential dead-bit check and the live birth time each change it. The numbers stay.
2. **ns17-r4-1's choice:** (a) 22.2 keeps vectors and old ids in its manifest, or (b) drop
   `id_map` and re-embed. Either is spec-settleable, but it decides plan-22's manifest size.
3. **Nothing else.** nb23-r4-1, ns23-r4-1, ns23-r4-2 and ns17-r4-2 are spec fixes. ns17-r4-2's
   scenario (b) changes what the runbook does to a live root, which is announced-and-backed-up
   surgery under CLAUDE.md, but it adds no new decision.

{#needs-user-body}

## Verdict {#verdict}

**plan-23: NEEDS-REVISION.** 7 new findings: 1 BULLSHIT (nb23-r4-1), 3 SKETCHY (ns23-r4-1..3),
3 MEH. Round 3: 7 of 8 closed, and nb23-r3-1 is partial (the code is fixed; the spec trails it).

**plan-17: NEEDS-REVISION.** 3 new findings: 0 BULLSHIT, 2 SKETCHY (ns17-r4-1, ns17-r4-2), 1 MEH.
Round 3: 9 of 10 closed, and ns17-r3-1 is partial.

**Totals:** 10 new findings (1B / 5S / 4M); round 3: 16 of 18 closed, 2 partial. The trend is
19 → 17 → 10, but the BULLSHIT is again a hotfix adopted one audit round late. {#verdict-body}

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 878647c (plan-23 + plan-17 SPEC re-review r4: 23.0-23.4, 17.1-17.4 at a820b22's revision; HEAD 224495c at write, decision log only; bug-105 clone 27b3653 read-only; written 2026-10-14T14:08:13-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 10 new (1B/5S/4M); r3: 16 closed / 2 partial (nb23-r3-1, ns17-r3-1) | [[bsd-plan23-17-spec-rereview-r4-878647c]]. plan-23 NEEDS-REVISION: B nb23-r4-1 23.1 contract = hotfix 4fb803b ("clears again" at merge end resurrects yield-gap unlinks; no writer-lock rule; concept-alive undefined; fallback cherry-pick omits 27b3653 + its r2 tests; AC-3d(iii) no-pre-flush mutant survives 27b3653's end flush+repair; bug_registry:158 in the same commit says 27b3653). S: AC-4 counting apply dirties no fragment, fresh-Store cache==rows tautological, 2 fragment mutations + AC-18 claim unkillable; R3.7 at-most-once event residual closed only by a never-forced compaction, undetected, hits learned rows; 23.4 by-key dealing ignores create/delete->link dependencies, absolute dead-bit check fires on any live copy (410 on census copy), copy's st_birthtime -> 0 events. M: AC-3d(v) allow-list misses 8 store.py methods; slot offsets have no reader (my r3 premise), bug-099 not stale, AC-1 spec sha unnamed; 23.3 AC-9 race not forced. plan-17 NEEDS-REVISION: S: id_map has no caller (22.2 manifest drops id, never names map, finalize deletes vectors itself; plan-17 open item 3 false); 17.4 restore never restores the catalog in the TM-disaster case, offsets unread, scenario (a) is a forced compaction. M: AC-8 daemon clock, restore signature, stale item 6, plan-18 overlap rule. Needs user: 23.4 procedure re-ack; ns17-r4-1 (a)/(b). |
```

last_run.log (one line):

```
2026-10-14T14:08:13-0700 commit=878647c verdict=DIRTY findings=10 (1B/5S/4M) report=2026-10-14-1408-plan23-17-r4-spec-rereview-superseded-hotfix-contract-and-callerless-id-map-878647c.md
```

IMPRESSIONS.md bullets:

- 2026-10-14 (plan-23 r4): A SPEC THAT ADOPTS A HOTFIX BY SHA TRAILS IT BY ONE AUDIT ROUND. 23.1
  described 4fb803b while 27b3653 had already fixed two BULLSHITs in it, and the registry in the
  same commit knew. Make the dependency "after the hotfix merges", not a sha list.
  {#imp-adopt-by-merge-not-sha}
- 2026-10-14 (plan-23/17 r4): CHECK THAT THE READER EXISTS BEFORE PRESCRIBING A WRITE. My r3 had
  17.4 and 23.1 reset and reason about A/B slot offsets that nothing has read since rotation was
  dropped. Before any "keep X consistent" fix, find X's consumer. {#imp-find-the-reader}
- 2026-10-14 (plan-17 r4): A CONSUMER-NAMED PARAMETER NEEDS THE CONSUMER'S EDIT, IN ITS FILE.
  17.1's `id_map` cites 22.2, but 22.2 drops the id and deletes the vectors itself. Grep the other
  plan for the parameter before calling it settled. {#imp-param-needs-consumer-edit}

rel: related-to -> [[impression_bsd_guard_cannot_fire]]
