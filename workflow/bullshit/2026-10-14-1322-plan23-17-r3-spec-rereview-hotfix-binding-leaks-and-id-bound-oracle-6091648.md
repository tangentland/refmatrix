---
gmd: "0.1"
id: bsd-plan23-17-spec-rereview-r3-6091648
title: "plan-23 + plan-17 spec re-review r3: the bug-105 hotfix 23.1 adopts 'unchanged' still leaks the binding (binding-local dirty guards, name in the cache key, merge flushes under a dropped id); 23.4's confirmed integrity oracle hashes sequence ids; vectors_restore cannot serve 22.2's new-id restore; 17.4's exclusion has no staleness alarm"
severity: BULLSHIT
plan: plan-23-bounded-write-harness
task: spec-rereview-r3-23.0-23.4-and-17.1-17.4
round: 3
tags: [bsd, audit, spec-review, re-review, plan-23, plan-17, partition, fragments, bug-105, option-a, facts-log, wave-1]
---

# ch-bsd spec re-review r3 of plan-23 and plan-17 at `6091648` {#root}

**Commit reviewed:** `6091648` (branch `wave0-spec-reviews`). **Written:** 2026-10-14T13:22:11-0700.
HEAD moved twice while I worked:
- `3021cd6` (13:15) changes only task 23.4's status lines to CONFIRMED (d9l), the ADR-0004 fold-in
  (d9k) and the decision log. I reviewed 23.4 at `3021cd6`.
- `097e7b1` touches no plan-17/23 file. It adds plan-18's contract note and #t10-waves, which I
  read for cross-plan consistency.

**Scope:**
- plan-23 and tasks 23.0-23.4;
- plan-17 and tasks 17.1-17.4 (17.4 for the first time);
- the prior report [[bsd-plan23-17-spec-rereview-32dde06]];
- decisions d9a, d9c, d9d, d9k, d9l and #t9-fixes in [[plan-review-2026-10-14]];
- the bug-105 hotfix in `/Volumes/littlebig/refmatrix-bug105`, branch `bug-105-fragment-partition`,
  commits `0d05525` and `20c5ab4`, which 23.1 R1.1 says it adopts.

**Method:**
- Every round-2 revision-table row was checked against the spec text.
- Every code fact a fix relies on was read at HEAD (`store.py`, `daemon.py`, `sync.py`,
  `ingest_records.py`, `vectors.py`, `duckdb_catalog.py`, `cli.py`).
- In the hotfix clone I ran only `git log` and `git show` and read files. I ran nothing there.

**Probes:** three throwaway probes, run against a COPY of the clone's `src/` placed in
`/tmp/rmxq-*` (`mkdtemp`, deleted afterwards). Each used `.venv-eval/bin/python -I`, with `HOME`
and `RMX_HOME` inside the tmp dir and a fresh tmp DuckDB store:
1. **Dirty guards.** A link under `with_partition("pb")` outside a transaction, then return to the
   home binding: `_dirty_fragments` (the current view) is False, while `_dirty_bindings()` is
   `[(2,'pb')]`. A periodic-guard tick wrote no `pb` row.
2. **Rename.** Link `a` (left dirty), `rename_partition`, link `b`, flush. The persisted row is
   `[3]`; expected `[2, 3]`. Entity `a`'s bit is lost, although `entity_links` holds 2 rows.
3. **Merge.** Link in `pb` (left dirty), `merge_partition("pb", home)`, flush. `partitions` is
   `[(1,…)]`, yet `bitmap_fragments` gained a row under `partition_id` 2, which no longer exists.

Not done: no `rmx`, no live store, no suite, and no edits to `src/`, `tests/`, plans or ledgers.

rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: specifies -> [[plan-23-bounded-write-harness]]
rel: specifies -> [[plan-17-nightly-store-maintenance]]
rel: related-to -> [[project_bug098_writer_partition_race]]
rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

## Prior findings: status {#prior-status}

### plan-23 r2 (10 findings) {#prior-23}

| id | status | evidence at `6091648` |
|---|---|---|
| nb23-1 fragment cache unbound | **partial** | 23.1 R1.1 states the contract (every entry belongs to one `partition_id`; flush under its own id), adds `create=False` with `UnknownPartition`, AC-3b (a SQL census over rows after a reopen, with two mutations) and AC-3c (no auto-create). But R1.1 adopts the hotfix "unchanged", and the hotfix still leaks in three places that no AC can see ([[#nb23-r3-1]]). |
| nb23-2 learn not idempotent | closed | R9.5 `add_evidence_if_absent` (`INSERT … SELECT … WHERE NOT EXISTS`; event only on insert); R3.5 makes `idempotent=True` a checked claim; AC-16 (child exits after hold 1 of 3; D rows and D events; a crash-free re-learn adds 0; mutation). The consumer table names AC-16. Residual on rolled-back holds: [[#ns23-r3-2]]. |
| nb23-3 23.3 stamps before semantics | closed | R4 keeps `pending_stamps` and stamps in each file's last step; AC-5 covers crash, cancel and budget with a row diff and a mutation. `mark_tracked` at `sync.py:244` and the gate at `:217-227` were verified. New concurrency gap: [[#ns23-r3-3]]. |
| nb23-4 bug-093 op-start line | closed | 23.3 R7 and AC-8 (the line is present while the first hold is blocked, with a mutation). |
| ns23-1 23.4 ranges unsound | closed (as asked) | All five items answered: fragment upserts are in the workload with AC-6; the verdict is concurrency-only; INVALID at N=1 with AC-7; the expected state and min/median are defined; an audit hook replaces stat with AC-5. The confirmed rule has NEW soundness defects ([[#ns23-r3-4]]). |
| ns23-2 23.0 AC-4 stat | closed | Content delta: run tag, `/pytest-of-`, sandbox root, d9g shape, `telemetry.is_test_artifact_row` after 21.1, and a decoy-dir detector check. |
| nm23-1 dead-letter | closed | R2 keeps the file forever; R6.7 `queue_redrive` verb with rename-not-unlink; AC-17. |
| nm23-2 d8d predicate owner | closed | 21.1 R5 defines `telemetry.is_test_artifact_row` (`task-21.1…:96`); 23.0 AC-4 imports it. |
| nm23-3 stale bug-099 row | **open (deferred)** | `bug_registry.md:152` still says "pending with the user". Plan-23 open item 6 hands it to "the docs step". That is acceptable as a docs chore, but it is still not done. |
| nm23-4 name the batch primitive | closed | `Store.batch_transaction()` raises `NestedTransaction`; AC-18 links its mutation to AC-4(d). |

Carried from r1: b-1 is **partial** (the same gap as nb23-1); b-2 is **closed** (nb23-2).

### plan-17 r2 (10 findings) {#prior-17}

| id | status | evidence |
|---|---|---|
| ns17-1 two registries | closed | 17.2 R2 `maintenance_steps` with its own signature; the header drops 23.1; 23.1 R10 says `tick_registry` is daemon-only; 19.4's preamble now says "INJECTED roots". |
| ns17-2 17.1 mis-consumes 23.1 | closed | 17.1 R3 names the full `bounded_steps(...)` call (names, `on_error`, `cancel`, budget); 23.1 R1.5 adds `hold_s` with AC-19; AC-4 uses ordered competitor wins. Leftover wording: [[#nm17-r3-1]]. |
| ns17-3 cap blocks compaction | closed | R6: a refusal skips the reap only, and the fingerprint expects B = A; `--confirm-orphans <sha>`; AC-7 covers four cases. The sha's granularity is new: [[#ns17-r3-2]]. |
| ns17-4 `still_running` unbounded | closed | R4 `stuck` after `RMX_MAINTAIN_STUCK_AFTER` budgets, one alert, stops blocking; AC-10. Intra-store step order is still unstated ([[#ns17-r3-3]]). |
| ns17-5 per-step arming | closed | `requires_arming` and a reason per step (registration fails without them); `hub_maintain_arm` on both surfaces, gated by `runs.jsonl`; AC-11 and AC-12; 17.4 declares False; 19.4 declares True. |
| ns17-6 17.3 ACs had no input | closed | A synthetic clone of ≥ 30,000 versions; an under-30k clone FAILS rather than being waived. `--standalone`/`--no-watch` exist (`cli.py:2925-2962`). Leftover: [[#nm17-r3-4]]. |
| nm17-1 lock-free status | closed | R11 uses an in-process run state with its own lock; AC-10 requires a return within 1 s while a step holds `_store_lock`. |
| nm17-2 small gaps | closed | `not_supervised` is dropped; GO-serial is named; the `compact` seam is in-process. |
| nm17-3 restore across plans | **partial** | 22.2 now names `vectors_restore` (`task-22.2…:96`), and ADR-0004 `#rule-no-delete` (d9k) scopes manifest-backed derived cleanup. But 22.2 restores entities with NEW ids, and `vectors_restore` matches by id ([[#ns17-r3-1]]). |
| nm17-4 17.4 unreviewed | closed | Reviewed here; it has a revision row. |

Carried from r1/dlr: 17 s-1 and s-4 are **closed**; dlr #s-7 is **partial** (the same gap as nm17-3).

**Closure:**
- plan-23 r2: 8 closed, 1 partial, 1 open (docs chore).
- plan-17 r2: 9 closed, 1 partial.
- Carried partials: 23 b-1 is still partial and 23 b-2 is now closed. 17 s-1 and s-4 are now
  closed; dlr #s-7 is still partial.

{#prior-status-body}

## New findings: plan-23 {#findings-23}

### BULLSHIT nb23-r3-1: 23.1 adopts the bug-105 hotfix "unchanged", but the hotfix leaks the binding in three places, and AC-3b can see none of them {#nb23-r3-1}

**Where:** 23.1 R1.1 ("If it has merged when 23.1 starts, 23.1 uses that mechanism unchanged and
AC-3b is its regression test"); R6.1 ("the periodic fragment flush stays after it, every tick");
AC-3b; plan-23 #why ("The binding is every piece of state keyed by the partition").

**What the hotfix does** (`0d05525`): the cache is
`_fragment_cache[(partition_id, partition_name)]`, and `_fragments` / `_dirty_fragments` are
PROPERTIES that return the CURRENT binding's view. `flush_fragments` iterates `_dirty_bindings()`.
Three defects remain:

1. **The guards read the current view, not every binding.** At these sites, a dirty entry under
   any other binding never triggers a flush. It waits for `close()` (which flushes all) or for an
   unrelated dirty write in the at-rest binding. On fast-exit or SIGKILL, which is how the daemon
   is designed to die, those bits never reach `bitmap_fragments`, and nothing counts them:
   - the periodic flush, `if self.store._dirty_fragments:` (`daemon.py:2066` in the clone,
     unchanged by the hotfix);
   - `Store.transaction`'s post-commit `if self._dirty_fragments:` (`store.py:4442` in the clone).

   Probe 1 confirms this.
2. **The partition NAME is part of the key.** `rename_partition` sets `_partition_name = new`
   (`store.py:1633`), which splits one partition id into two caches. The flush then upserts each
   cache's whole blob under the same id, and the last one wins. Probe 2 lost a committed link's bit.
3. **Merge flushes under a dropped id.** `merge_partition` deletes the SRC partition row and
   rebinds (`store.py:1928-1929`). A dirty SRC cache then flushes under the deleted id. Probe 3
   created a row under `partition_id` 2, which no longer exists. The r2 census found 16 such
   linkages in the live snapshot.

**Why it is bullshit:**
- Plan-23's own sentence says the binding is every piece of state keyed by the partition. The
  guards that DECIDE whether to flush are that state too.
- R1.1 makes the hotfix 23.1's contract "unchanged". AC-3b cannot fail on any of the three:
  - it reopens after a clean drain and close, and `close()` flushes every binding, which hides
    defect 1;
  - it never renames;
  - it never merges.
- AC-11's "the fragment flush runs every tick" passes with the binding-local guard.
- The repair (`20c5ab4`) cures the past. These three defects keep producing new damage: foreign
  rows, lost bits, and rows under a dropped id. A repair-then-regrow loop is the pattern d9a was
  meant to end.

**Fix (in the hotfix before it merges, and stated in 23.1 R1.1 as the contract):**
- Every "is anything dirty" test uses `_dirty_bindings()`: `_runner`'s periodic flush,
  `Store.transaction`'s post-commit flush, and any other caller. A `grep _dirty_fragments` over
  `src/` outside `store.py`'s cache internals returns nothing.
- Key the cache by `partition_id` alone. The name is derivable, and the flush writes by id.
- `merge_partition` and `rename_partition` flush every dirty binding BEFORE they mutate
  `partitions`. Merge then drops the SRC cache.
- Add AC-3d to 23.1, with three cases:
  - (i) a link under `with_partition("pb")` outside a transaction, the at-rest binding clean, one
    `_runner` tick, then read `pb`'s row through a SECOND read-only connection before any close:
    the bit is present;
  - (ii) dirty, then rename, then link, then flush: both bits are present;
  - (iii) dirty `pb`, then merge into home, then flush: 0 `bitmap_fragments` rows whose
    `partition_id` has no `partitions` row.
- Mutations (each must FAIL): the guards back on `_dirty_fragments`; a cache key that includes the
  name; merge without the pre-flush.
- R1.1's "unchanged" becomes "adopted, with AC-3d as the regression test it must pass".

**Pattern match:** YES. `#imp-binding-is-every-cache` (r2) said to enumerate the attributes the
bound id parameterizes. The hotfix moved the dict and left the readers of the dict. This is the
5th instance of the bug-098 class.

### SKETCHY ns23-r3-1: R1.3's rollback rule drops dirty bits that predate the batch and silently un-dirties other bindings' entries {#ns23-r3-1}

**Where:** 23.1 R1.3: on rollback, "the in-memory fragment cache entries the batch dirtied are
dropped so they reload from the database". `batch_transaction` flushes "every dirty fragment
entry".

**What:**
- Outside the harness, `link()` marks a fragment dirty and leaves the flush to `_runner`'s 30 s
  periodic flush (`store.py:4339-4345`; `daemon.py:2064-2069`). At any moment the cache can
  therefore hold committed-but-unflushed bits.
- A batch that dirties the same `(partition, linkage)` and then rolls back (faults (a), (b) or (d);
  a `fatal`; a dead-letter) DROPS that entry. The earlier op's bits are then neither in the cache
  nor in the row, while `entity_links` still holds them: a silent bug-105-shaped divergence.
- The in-transaction flush also flushes OTHER bindings' dirty entries (the competitor's `pb`
  fragment in AC-3) and clears their dirty marks. A rollback un-writes the rows, but nothing
  re-marks the entries dirty, so those bits are lost at close.
- AC-4 starts from a clean cache, so it cannot see either case.

**Fix:**
- `batch_transaction` flushes every pre-existing dirty binding in its own commit BEFORE `BEGIN`,
  under the same hold. The dirty set at `BEGIN` is then empty, every entry the transaction flushes
  is the batch's own, and dropping them on rollback is exact.
- Add AC-4(f): one committed, unflushed link in `(pa, mentions)` and one in `(pb, mentions)` before
  a batch that faults at (b). After recovery, both rows contain their bits.
- Mutation: no pre-flush FAILS.

### SKETCHY ns23-r3-2: `facts.log` events are appended inside holds that may roll back, so a rolled-back batch's `link` and `evidence` events are replayed into rebuilds and into the A/B slot delta-replay {#ns23-r3-2}

**Where:** 23.1 R3.7 (the exactly-once boundary does not mention `facts.log`); R9.5 ("AC-16
counts evidence rows and `evidence` events, which must not repeat").

**What:**
- `Store._log_event` appends to `facts.log` at once (`store.py:1080-1094`). That includes inside an
  open transaction: `link` logs at `:4361`, and `add_evidence` logs at `:5288`.
- A batch that raises after its first insert leaves events for rows that ROLLBACK removes. The
  retry then emits them again.
- `rebuild_index_from_log` replays `link` and `evidence` events (`store.py:7648`, `:7681`). The
  A/B slots delta-replay from byte offsets into the same log (17.4 #why).
- So a rolled-back learn batch resurrects its links on the other slot and duplicates evidence on a
  rebuild. That is bug-106's duplication, moved into the log.
- AC-16 exits only BETWEEN holds, so it cannot see this.
- It is pre-existing for `Store.transaction`. 23.1 makes rollback a NORMAL path (dead-letter,
  fatal, every fault).

**Fix:**
- Inside `batch_transaction`, `_log_event` buffers its events and appends them after `COMMIT`. On
  rollback, the buffer is discarded.
- State in R3.7 that the event log is inside the boundary (post-commit), or explicitly outside it
  with the consequence.
- Add AC-16b: a child `os._exit`s INSIDE hold 2, after its first `add_evidence_if_absent`. After
  recovery: exactly D `evidence` events, and no `link` event for a link absent from `entity_links`.

### SKETCHY ns23-r3-3: 23.3 lets two `_sync_paths` runs interleave per step, with nothing to serialize them {#ns23-r3-3}

**Where:** 23.3 R1 and R3 (the three daemon sites drop their outer `_store_lock`); AC-6 (one sync).

**What:**
- Today the watcher `_flush` (`daemon.py:3000`), `_op_sync_files` (`:3338`) and `_op_sync_since`
  (`:3707`) each hold `_store_lock` for the whole sync, so two syncs never interleave. No other
  sync mutex exists; a search for sync locks in `daemon.py` finds none.
- After 23.3, a watch flush and a git post-commit `sync_since` over the same just-edited file
  interleave at step granularity:
  1. A purges and re-upserts `f`;
  2. B purges and re-upserts `f`;
  3. A applies `f`'s semantics;
  4. B applies them again.
- `bulk_apply_records` writes evidence through the plain `add_evidence` (`ingest_records.py:461`),
  so the evidence is duplicated. A's semantic step may also target an entity B has already purged.
- AC-1 to AC-6 each run one sync.

**Fix:**
- A per-store `sync_mutex` (a plain lock, NOT `_store_lock`) is held across one whole
  `bounded_steps` run. A second sync waits or coalesces its paths into the running one. The writer
  still yields between steps to every non-sync op.
- Add AC-9: two concurrent syncs of the same 3 files. The final rows equal one sync's (AC-6's
  diff), with no duplicate evidence row.
- Mutation: no mutex FAILS.

### SKETCHY ns23-r3-4: 23.4's CONFIRMED integrity oracle hashes sequence-assigned ids, so a correct concurrent run reads `integrity_mismatch` → NO-GO; and three more procedural holes {#ns23-r3-4}

**Where:** 23.4 R3 (dealt by key, "the end state does not depend on the interleaving"); R4; R6
(content hash of `entity_links` "over its key", and of `bitmap_fragments` over its blob); #ranges
(any `integrity_mismatch` at N > 1 → NO-GO); AC-1. Confirmed by the user as d9l at `3021cd6`.

**What:**
1. **The ids depend on the interleaving.** `entities.id` is `DEFAULT nextval('seq_entities_id')`
   (`duckdb_catalog.py:50`). DuckDB sequences are not transactional:
   - a conflicted or retried transaction BURNS ids;
   - concurrent creates take ids in commit order, not log order.

   The `entity_links` key `(entity_id, linkage_id, concept_id)` and every fragment bit (`concept
   << 32 | entity`) embed those ids. So any replay window that creates one entity, plus a single
   conflict retry, makes N > 1 differ from the serial reference. The result is NO-GO for an
   artifact, and the oracle can only fire one way. INVALID is checked only at N = 1, where the
   order is serial and the artifact never appears.
2. **The 60 s stop breaks the expected state.** R4 stops a run at 60 s. With key-dealt threads,
   each stopped thread sits at a different log position, so no serial prefix equals the state.
   R6's "same transaction list" assumes a drained run.
3. **Re-applying failed transactions after the run reorders keys.** R6 re-applies a failed
   transaction serially AFTER the run. If the same key's later transaction (an unlink after a
   failed link) already ran, the re-applied link resurrects the bit, and `integrity_mismatch`
   follows.
4. **The workload is not pinned.** "The most recent write events" has no count and no window.
   After a `facts.log` compaction, the tail is a `dump_catalog_to_log` snapshot in dump order, not a
   workload. That is a free parameter after confirmation.
5. **AC-1 cannot prove the order.** "The commit that adds the first jsonl reference is later than
   the confirmation commit" orders commits, not runs. A run can precede the confirmation and be
   committed after it.

**Fix (the numbers can stay; the procedure needs the user's re-acknowledgement because it is part
of what d9l froze):**
- R6 compares by NAME:
  - `entity_links` hashed over `(partition, kind, name, linkage, concept-name)`;
  - fragments decoded to the same name tuples.
- Or the replay pins ids: every create carries the serial reference run's id.
- No 60 s cap for the verdict workload. Size it so N = 1 drains it, and treat a run that does not
  drain as INVALID.
- A failed transaction halts its key's stream and is retried in place, up to K counted attempts,
  never re-applied after the run.
- Pin the workload: the last 20,000 non-snapshot events (or the 7 days before the copy), and record
  the facts.log compaction time. A post-compaction log with fewer events is INVALID.
- Add a positive control to AC-3: the smoke test at N = 2, with creates and a forced conflict, MUST
  pass integrity. A detector that only proves it can fire is half a detector.
- AC-1 compares the first jsonl row's `ts` with `3021cd6`'s committer time.

### MEH nm23-r3-1: the status of 23.4's ranges is stated three ways {#nm23-r3-1}

- Plan-23 #open-after-revision item 1 says "OPEN, user … PROPOSED".
- 23.4's header and #ranges say CONFIRMED, citing "d9d: '2 - yes'". The decision is d9l.
- #ranges then also says "the user confirms or changes these numbers before the first measured
  run".

Fix: one status, citing d9l. The [[#ns23-r3-4]] amendment re-opens it anyway.

### MEH nm23-r3-2: 23.1 R1.1 and d9a describe the repair as "rebuilt from `entity_links` (loses nothing)"; the shipped repair is a union {#nm23-r3-2}

- `Store.repair_fragments` (`20c5ab4`) unions the `entity_links` bits with every existing fragment
  bit, rehomed to its entity's partition. It drops only dead-entity bits, into a manifest written
  first.
- Its docstring records why: a pure rebuild would have lost 74 own-partition bits and 442 foreign
  bits that exist only in fragment rows.
- ADR-0004 `#rule-no-delete` (d9k) covers the manifest-backed drop as derived-index cleanup.

Fix: correct the description, so that no later task "simplifies" the repair into the lossy rebuild
the text describes.

{#findings-23-body}

## New findings: plan-17 {#findings-17}

### SKETCHY ns17-r3-1: `vectors_restore` restores by id, but 22.2 restores entities with NEW ids, so the vectors half of restore can never fire {#ns17-r3-1}

**Where:**
- 17.1 R10 ("upserts the vector of every listed id whose entity is in the catalog NOW");
- AC-8 ("re-insert 15 of their entity rows with the SAME ids");
- `task-22.2…:95-98` ("Restored entities get new ids … Vectors are restored first from plan-17's
  orphan list through `vectors_restore`").

**What:**
- Lance rows carry only `id`, `vector` and `updated_at` (`vectors.py:32-41`).
- The orphan list holds `{partition, kind, id, …}` and no name. The entity is gone at reap time, so
  the name is not known.
- Every id 22.2 restores is new, so `vectors_restore` reports every row `absent`, and 22.2 always
  falls back to re-embedding.
- AC-8 tests the one case 22.2 says never happens.

**Fix:**
- `vectors_restore(orphan_file, ids=None, id_map: dict[int, int] | None = None)`. 22.2 passes
  `old_id → new_id` from its manifest, and the vector is upserted under the new id.
- Add AC-8b: reap, restore the entities with new ids, restore with `id_map`. The vectors are
  byte-equal under the new ids.
- Plan-22's spec names the parameter. This closes dlr #s-7 for real.

### SKETCHY ns17-r3-2: the `--confirm-orphans` sha is per run file but reported per dataset, takes one CLI value, and is invalidated by any churn, so the release can loop on a live store {#ns17-r3-2}

**Where:** 17.1 R6 "Releasing the cap" and AC-7.

**What:**
- R6 writes ONE candidate file per run (`orphans-candidates-<run_id>.jsonl`, all datasets). It
  reports `orphan_list_sha` "= sha256 of that file's bytes, per dataset". Those are two different
  things. The CLI takes one `--confirm-orphans <sha>`, while a store can have several capped
  datasets.
- The hand run recomputes the list and requires byte-equality. On a store with its watcher running,
  one new orphan in ANY dataset between the dry run and the user's confirmation (minutes to hours)
  gives `refused:orphan_confirm_mismatch`. The cycle is dry-run, re-show, mismatch, and repeat.
- R9 makes new orphans a routine product of re-syncs (NULL-stamp vectors).

**Fix:**
- Per-dataset candidate files, each with its own sha. `confirm_orphans` takes a list.
- The hand run reaps the INTERSECTION of the confirmed file's ids and the current whole-catalog
  orphans. Every id in it is still absent from every partition, so the reap is safe. Candidates
  that are new since the dry run obey the cap as usual.
- AC-7's stale-sha case becomes: one new orphan after the dry run → the confirmed 60 are reaped,
  the new one is left, and the outcome names it.

### SKETCHY ns17-r3-3: after 17.3 excludes the live `facts.log` from Time Machine, nothing alarms when the daily copy stops being made {#ns17-r3-3}

**Where:** 17.4 R5 ("No silent failure" covers runs that execute) and R7 (exclusion once the copy is
≤ 1 day old); 17.2 R2/R4 (registration order vectors-first; behaviour of a store's later steps while
an earlier step is `still_running` or `stuck` is unstated); plan-18's new #contract-2026-10-14 asks
the same order question.

**What:**
- The exclusion is permanent. The copy depends on the hub tick running, and the copy can stop in
  three ways, each without a 17.4 failure:
  - `RMX_HUB_MAINTAIN_AT=off`;
  - the hub is down, or its thread died;
  - `vectors_maintain` on that store is `still_running` or `stuck`. `stuck` stops blocking OTHER
    stores, but nothing says the same store's `factslog_backup` step runs.
- In each case the backup ages silently while the live log, the only file that holds learned rows
  and flags, has no Time Machine copy.

**Fix:**
- Register `factslog_backup` FIRST. It is cheap and non-destructive.
- 17.2 states that a store's steps are independent: a later step runs even when an earlier one is
  `still_running` or `stuck`.
- `_store_health` and `rmx hub status` report `factslog_backup_age_h` from `meta.json`.
- The hub raises an alert when that age is over 48 h for any store, whether or not the tick ran.
  The `off` disable line names the stores whose live log is excluded.
- Add AC-8 to 17.4: with `vectors_maintain` blocked (the AC-10 shape), the backup step on the same
  store still copies. With the clock advanced 3 days and no tick, the staleness alert fires once.

### SKETCHY ns17-r3-4: 17.4's restore runbook overwrites the live `facts.log` and ignores the A/B slot offsets {#ns17-r3-4}

**Where:** 17.4 R6: "`cp backups/facts.log.daily facts.log` with the daemon stopped, then
`rmx rebuild --from-log` into a THROWAWAY root first".

**What:**
- Read in order, the runbook copies OVER the live log first, which destroys every event since the
  copy.
- The slot offsets are byte positions into that file (`_slot_offset_path`, `daemon.py:2789`;
  compaction resets them for exactly this reason, `:2318-2321`). After the copy they point past EOF
  or into different bytes, and the next delta-replay applies the wrong records.

**Fix:**
- Order the runbook:
  1. rebuild into a throwaway root;
  2. verify (AC-3's counts);
  3. with the daemon stopped, move the live log aside (keep it), install the copy, and reset both
     slot offsets to the new EOF, as compaction does.
- An AC runs the runbook on a tmp store and checks the offsets.

### MEH nm17-r3-1: 17.1 leftovers {#nm17-r3-1}

- R10 still says "the same `bind(batch)` hold as R3". Restore is not on `bounded_steps`, so it has
  no `hold_s`, `cancel` or budget.
- The ACs carry two items numbered "12." (AC-13 and AC-11).
- AC-12's mutation list has no entry for AC-13. Add "drop the `runs.jsonl` line → AC-13".

### MEH nm17-r3-2: the arm gate proves "a successful real run", not d3d's order {#nm17-r3-2}

- 17.2 R7 checks one `runs.jsonl` line: hand, not dry, ok.
- `invoked_by` defaults to `"hand"` on every surface, so an agent's MCP call is a "hand" run, and
  no dry run needs to precede it.
- Fix: the gate also requires an earlier `dry_run: true, ok: true` line of the same step on that
  store. `invoked_by` records the surface (`cli` / `mcp` / `hub`).

### MEH nm17-r3-3: 17.2 R4 polls `vectors_maintain(status=True)` for every step {#nm17-r3-3}

It should poll the step's own `op` (17.4's `factslog_backup`, plan-18's step).

### MEH nm17-r3-4: 17.3's clone daemon runs with `HOME` in the tmp dir {#nm17-r3-4}

- That moves the model cache path, and models load from the local cache only.
- Fix: state either "embedding off for the clone (the timed re-sync measures the purge/delete
  path)", or point `HF_HOME` at the real cache, read-only.
- State the expected build time of 30,000 Lance commits, and that the AC fails rather than being
  shortened.

### MEH nm17-r3-5: 19.4 AC-2 still asserts plan + apply on the scheduled day for a step it declares `requires_arming=True` {#nm17-r3-5}

- Plan-19's file. 17.2 R7 makes it dry-run until it is armed.
- Fix: AC-2 arms it first by a hand-run `run_id`, or asserts `dry_run:unarmed`.

### MEH nm17-r3-6: 17.4 small items {#nm17-r3-6}

- AC-3 (replay equivalence) replays identical bytes on both sides, so it adds nothing over AC-2.
  Compare with the SOURCE STORE's catalog at the copy's offset instead, or drop it.
- `fclonefileat` has no Python binding. State the ctypes call and keep an AC that forces the
  streamed fallback.

{#findings-17-body}

## Cross-plan consistency {#cross-plan}

| question | answer |
|---|---|
| 23.1 R1.1 vs the hotfix `0d05525`/`20c5ab4` | Mechanism (a) in spirit, but the key includes the name, the guards are binding-local and merge flushes under a dropped id ([[#nb23-r3-1]]). The repair's description is wrong ([[#nm23-r3-2]]). |
| 23.1 R10 names vs 17.1 / 19.2 / 22.2 / 16.6 | Consistent: `bind(partition_name)`, `bounded_steps`, `tick_registry.register(…, kind="tail")`, `hold_s`, `add_evidence_if_absent` (16.1 R4). 17.1 R10's `bind(batch)` remains ([[#nm17-r3-1]]). |
| `maintenance_steps` vs `tick_registry` | Settled: two registries. 17.2, 17.4, 19.4 and plan-18's contract all use `maintenance_steps`. |
| `vectors_restore` vs 22.2 restore | **Conflict:** id match vs new ids ([[#ns17-r3-1]]). |
| `requires_arming` | 17.4 False, 19.4 True, plan-18 "expected True". 19.4 AC-2 ignores its own value ([[#nm17-r3-5]]). |
| intra-store step order | Unstated in 17.2. 17.4 and plan-18 both depend on it ([[#ns17-r3-3]]). |
| 23.4 verdict vs plan-17 revisit | Consistent (GO-serial = keep `bind`; INVALID triggers nothing). Its oracle is biased toward NO-GO ([[#ns23-r3-4]]). |
| Wave order | plan-23/17 cite #t8-wave1, and #t10-waves (`097e7b1`) agrees: 17.4 after 17.2 in Wave 1, 17.3 in Wave 2. |

{#cross-plan-body}

## Open-after-revision items: classification {#open-items}

### plan-23 {#open-23}

1. **23.4's ranges.** The user CONFIRMED them (d9l). The numbers can stay. The procedure fixes in
   [[#ns23-r3-4]] change what was frozen (the oracle by name, no 60 s cap, in-place retry, a pinned
   workload, a positive control), so **the user re-acknowledges** them. This is the only item that
   needs the user.
2. to 5. Settled; verified above (nb23-2, nm23-2, nm23-1, nb23-4).
6. **Registry rows:** the orchestrator's docs chore; no user needed. bug-099 is still stale.

### plan-17 {#open-17}

1. Settled (two registries).
2. Settled by d9c, but the release FORM needs [[#ns17-r3-2]]'s per-dataset intersection. **The spec
   settles it** within d9c's wording ("sha of the dry-run orphan list").
3. Plan-22 now names `vectors_restore`, but by id. **The spec settles it** with `id_map`
   ([[#ns17-r3-1]]).
4. Settled; [[#nm17-r3-2]] is a spec tweak.
5. (New) 17.4's exclusion safety ([[#ns17-r3-3]], [[#ns17-r3-4]]): **the spec settles it.**

{#open-items-body}

## Verdict {#verdict}

**plan-23: NEEDS-REVISION.** 7 new findings: 1 BULLSHIT (nb23-r3-1), 4 SKETCHY (ns23-r3-1..4),
2 MEH. Prior r2: 8 closed, 1 partial (nb23-1), 1 open (the nm23-3 docs chore).
- Every r2 BULLSHIT except nb23-1 is closed with an AC that can fail.
- nb23-1's contract now rests on a hotfix that still leaks. The fix is in `bug-105-fragment-partition`
  before it merges, plus AC-3d.

**plan-17: NEEDS-REVISION.** 10 new findings: 0 BULLSHIT, 4 SKETCHY (ns17-r3-1..4), 6 MEH.
Prior r2: 9 closed, 1 partial (nm17-3). All of the new findings can be settled in the specs.

**Totals:** 17 new findings (1B / 8S / 8M). {#verdict-body}

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 6091648 (plan-23 + plan-17 SPEC re-review r3: 23.0-23.4, 17.1-17.4 (17.4 first review); 23.4 read at 3021cd6 = d9l CONFIRMED; HEAD 097e7b1 at write, no plan-17/23 change; bug-105 hotfix 0d05525/20c5ab4 read-only; written 2026-10-14T13:22:11-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 17 new (1B/8S/8M); prior 23: 8 closed/1 partial/1 open, 17: 9 closed/1 partial | [[bsd-plan23-17-spec-rereview-r3-6091648]]. plan-23 NEEDS-REVISION: B nb23-r3-1 23.1 adopts hotfix "unchanged" but its dirty guards read the current binding (periodic flush daemon.py:2066, Store.transaction post-commit; probe: pb dirty, guard False), cache key includes the name (probe: rename loses a committed bit), merge flushes dirty SRC under the dropped id (probe: row under partition_id 2 with no partitions row); AC-3b blind (clean close). S: rollback drops pre-batch dirty bits/undirties other bindings; facts.log events inside rolled-back holds feed rebuild + slot replay; 23.3 concurrent syncs interleave per step (no sync mutex, dup evidence); 23.4 confirmed oracle hashes nextval ids (burned by retries) -> NO-GO artifact, 60 s cap vs expected state, post-run re-apply reorders keys, workload unpinned. plan-17 NEEDS-REVISION: S: vectors_restore by id vs 22.2 new ids; confirm-orphans sha per-run vs per-dataset, churn loops; 17.4 no staleness alarm after TM exclusion + intra-store step order unstated; 17.4 restore runbook overwrites live log, ignores slot offsets. |
```

last_run.log (one line):

```
2026-10-14T13:22:11-0700 commit=6091648 verdict=DIRTY findings=17 (1B/8S/8M) report=2026-10-14-1322-plan23-17-r3-spec-rereview-hotfix-binding-leaks-and-id-bound-oracle-6091648.md
```

IMPRESSIONS.md bullets:

- 2026-10-14 (plan-23/17 r3): A CACHE FIX MOVES THE DICT; THE GUARDS STILL READ THE OLD SHAPE.
  bug-105's hotfix keyed the cache per binding but left `if store._dirty_fragments:` (now the
  current view) in the periodic flush and in `transaction()`, and added the NAME to the key, so a
  rename splits one partition. After any re-keying, grep every reader of the old attribute and every
  op that mutates the key (rename, merge). {#imp-guards-read-the-old-shape}
- 2026-10-14 (plan-23 r3): AN INTEGRITY ORACLE MUST BE INVARIANT TO WHAT CONCURRENCY LEGITIMATELY
  CHANGES. 23.4 compares id-bearing hashes while ids come from non-transactional sequences, so it
  can only fire. Ask what a CORRECT N>1 run is allowed to differ in, and demand a positive control.
  {#imp-oracle-invariant-to-legit-change}
- 2026-10-14 (plan-17 r3): A RESTORE CONTRACT NEEDS THE KEY BOTH SIDES SHARE. 17.1 restores by old
  id; 22.2 restores with new ids. Check that the producer's key survives the consumer's restore.
  {#imp-restore-shares-a-key}

Proposed impression memory: `impression_bsd_guards_read_the_old_shape` (type impression, tags
`[impression, ch-bsd, partition]`). It amends `impression_bsd_binding_is_every_cache`. Its lead
line: re-keying a cache is not done until every guard, size check and key-mutating op reads the new
shape. It is the 5th bug-098-class instance.

Recommended bug-105 follow-up (for the hotfix branch's owner; I did not edit the registry). Reopen
or annotate the row with:
- the binding-local guards (`daemon.py:2066`, `store.py:4442` in the clone);
- the name in the key (`store.py:1633` rename);
- merge flushing under a dropped id (`store.py:1928`).

Probes 1-3 above are the evidence.

rel: related-to -> [[impression_bsd_guard_cannot_fire]]
