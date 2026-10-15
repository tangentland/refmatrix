---
gmd: "0.1"
id: bsd-plan23-17-spec-rereview-r6-0e77da3
title: "plan-23 + plan-17 spec re-review r6: every round-4 finding closed; 23.1 still labels R1.6 PROPOSED after d9ag adopted it, its writer_lock goes None on 7 of 8 daemon reopen sites, R8 builds on a replica_merge that bug-113 breaks, 23.4's by-name hash cannot resolve dangling links, and 17.4's restore drops a day when only the catalog is lost"
severity: SKETCHY
plan: plan-23-bounded-write-harness
task: spec-rereview-r6-23.0-23.4-and-17.1-17.4
round: 6
tags: [bsd, audit, spec-review, re-review, plan-23, plan-17, writer-lock, bug-105, bug-110, bug-111, bug-113, d9ag, wave-1]
---

# ch-bsd spec re-review r6 of plan-23 and plan-17 at `0e77da3` {#root}

**Commit reviewed:** `0e77da3` (branch `wave0-spec-reviews`; the merge of master 0.78.1 into it).
The round-5 spec revision is `d454bf9` (14:45:35), with `734dc5f` adding the d9ad pin row. No
plan-17/23 file has changed since `d454bf9` (`git log d454bf9..HEAD` on both plans' files is
empty). **Written:** 2026-10-14T23:53:39-0700.

**Scope:**
- plan-23 with tasks 23.0-23.4, and plan-17 with tasks 17.1-17.4;
- my round-4 report [[bsd-plan23-17-spec-rereview-r4-878647c]];
- decisions d9y-d9an in [[plan-review-2026-10-14]], d9ac, d9ad, d9ae, d9ag, d9aj and d9an
  in particular;
- the 0.78.0/0.78.1 code at HEAD: `src/refmatrix/store.py` (`merge_partition`,
  `repair_fragments`, `_clear_purged_bits`, `purge_entity`), `daemon.py` (`_FairLock`,
  `_copy_out_of_process`, `_snapshot_catalog`, `_periodic_flush`, `_compact_factslog_if_needed`,
  `_op_partition_merge`, the writer-Store assignment sites), `replica_merge.py`, `ingest_gmd.py`;
  the merged hotfix suite (`tests/test_fragment_*`); `bug_registry.md` rows 112 and 113;
- 22.2 R4 for the cross-plan `id_map` contract.

**Method:** read only. Each round-4 id was traced to its `#rev-round-5` row and the spec text
there was read. Every code fact was read at HEAD. The AC-3d (v) decision search was run with
Python `re` + `ast` over `src/`. Nothing was run against a store, no test was run, and no plan,
spec or source file was edited.

rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c]]
rel: related-to -> [[plan-review-2026-10-14]]
rel: specifies -> [[plan-23-bounded-write-harness]]
rel: specifies -> [[plan-17-nightly-store-maintenance]]
rel: contradicts -> [[plan-review-2026-10-14#t11-approvals]]
rel: contradicts -> [[claude#no-silent-failures]]

## Round-4 findings: status {#prior-status}

| id | status | evidence at `0e77da3` |
|---|---|---|
| nb23-r4-1 superseded hotfix contract | **closed** | 23.1 header: "Depends on: … **the bug-105 hotfix MERGED TO `master`** … it never carries hotfix commits itself". R1.1 item 4: "at its end it FLUSHES, never clears". Item 5 is the writer-lock rule. Item 6: "A bit is dead only if its entity is gone, or its concept id is in neither `entities` nor `concepts`". Item 7 names no sha. AC-3d maps cases (ii)-(ix) to the merged test names; all 8 names exist at HEAD (`test_fragment_repair_audit{,_r2,_r3}.py`). The no-pre-flush (iii) mutant is "DROPPED … Its lock-rule replacement is (ix)". New drift since round 5: [[#nm23-r6-1]]. |
| ns23-r4-1 AC-4 dirties no fragment | **closed** | AC-4: "A COUNTING AND LINKING `apply` … links one fresh entity per event into `(pa, mentions)`". The check runs "in the SAME process and on the SAME `Store` … then ONE more `link` … and one `flush_fragments()`". R1.3: "How the drop is done (ns23-r4-1): `_clear_fragment_caches()`, EVERY binding, every entry". AC-18 is rewritten against the linking `apply`. Each listed mutation now has a killing case (traced: post-COMMIT flush at (d), no drop at (b), drop-by-marks). |
| ns23-r4-2 at-most-once residual | **closed** | R3.4 adds the `events_pending` column. R3.7 items 1-4 set it in the transaction, clear it after the append, and force a compaction at boot. AC-16b's second case runs "a plain RESTART … with no manual force", with three mutations. One wording defect: [[#nm23-r6-2]]. |
| ns23-r4-3 23.4 procedure | **closed (d9y)** | R3 adds the "per-name log-position barrier" and `blocked_by_exhausted`. R6 makes dead bits "DIFFERENTIAL, not absolute". R3 "Whose birth time" reads `os.stat(<live facts.log>)` and records `live_birthtime`. AC-3 adds the cross-thread pair and a differential negative control; AC-7 adds the third case. I traced the barrier for deadlock: every wait points to a lower log position, so the lowest uncommitted position is always at the head of its thread. A new gap is in the entity_links half: [[#ns23-r6-4]]. |
| nm23-r4-1 AC-3d (v) allow-list | **closed** | (v) now searches for a decision, not a mention. At HEAD the regex hits exactly `store.py:4164` (`_load_fragment`) and `:4220` (`_flush_current_binding`). That includes the bug-111 code (`_clear_purged_bits` tests a local `frag`). |
| nm23-r4-2 three false facts | **closed** | (1) 23.1 `#facts` round 5: "Nothing reads the A/B slot offsets", and `_read_slot_offset` (`daemon.py:2798`) still has no caller. (2) Plan-23 open item 6 is SETTLED: "the bug-099 row is NOT stale". (3) d9ad: "23.4 procedure pin = `d454bf9`". The 23.4 file is unchanged since then. Nit: AC-1 says "the commit that lands this revision ALSO adds one row", but the row landed 14 s later in `734dc5f`. That is harmless, because the check compares against the literal sha. |
| nm23-r4-3 AC-9 race not forced | **closed** | 23.3 AC-9 "The barrier": A's first `apply` waits until B is inside the wrapped `_sync_mutex.acquire` or holds a `_FairLock` waiter ticket, with a 10 s deadline. |
| ns17-r4-1 `id_map` has no caller | **closed (d9z a)** | `task-22.2…:110-155` keeps `old_id` and writes `removal/<apply_id>.vectors.jsonl` in 17.1 R6's format. It builds `id_map` and calls `vectors_restore("removal/<apply_id>.vectors.jsonl", id_map=id_map)`; AC-4b covers this with two mutations. Plan-17's item 3 now trails plan-22, and `invoked_by` has no value for this caller: [[#nm17-r6-1]]. |
| ns17-r4-2 restore never restores the catalog | **closed** | 17.4 R6 (a): "The backup is NOT used … `rmx compact-log --force`". (b) steps 1-7: refuse while the daemon pings, throwaway rebuild, verify, move aside, **promote**, install the log, offsets "only as consistent bookkeeping … no AC of its own". AC-9 runs both scenarios. A classification gap: [[#ns17-r6-1]]. |
| nm17-r4-1 small items | **closed** | AC-8 "BACK-DATES the meta file" for the daemon clause. 17.1 R1 gives "The two signatures, exactly", and R12 adds "Restore records its surface too". Open item 6 is SETTLED in plan-19. Item 7 hands the CHECKPOINT-overlap question to plan-18; plan-18 `:50` still carries the constraint, which is plan-18's to edit. |

**Closure:** 10 of 10 round-4 findings are closed (plan-23 7 of 7, plan-17 3 of 3).
{#prior-status-body}

## Asked: is R1.6 ADOPTED in 23.1, and is it consistent with bug-110? {#asked}

1. **No. The spec text still says PROPOSED.** d9ag ("23.1 R1.6 … is ADOPTED as written; no
   longer PROPOSED", logged at `e41c6e8`, 15:57:36) came 72 minutes after `d454bf9`. No spec
   edit followed. See [[#ns23-r6-1]].
2. **Partly consistent with bug-110.**
   - R1.6 checks which THREAD owns `_store_lock` (`_FairLock` gains `_owner`). bug-110's lock
     is DuckDB's POSIX `fcntl` lock on the slot file, owned by the (process, file) pair, and
     dropped by any in-process `close()` of any descriptor for that file.
   - The two are orthogonal. Nothing R1.6 adds opens or closes a slot descriptor. The
     snapshot path (`_snapshot_catalog`: CHECKPOINT under `_store_lock`, then
     `_copy_out_of_process` runs `/bin/cp -p` in a child, `daemon.py:203-226`, `:2621-2660`) is
     untouched by it, and holds `_store_lock` around the copy. So R1.6 neither causes bug-110
     nor detects it.
   - Two gaps follow.
     - The spec never says the check is blind to the file lock, so the WARN-mode census can be
       read as "no unlocked writes" while an in-process descriptor close has dropped the
       DuckDB lock.
     - More concretely, R1.6's `Store.writer_lock` is set "when it opens its writer Store",
       but the daemon assigns its writer Store at 8 sites. Every reopen therefore yields a
       Store with `writer_lock = None`, and the check silently turns itself off. The reopen
       sites are exactly the paths bug-110/bug-113 showed leave the writer closed or reopened.
       See [[#ns23-r6-2]].

{#asked-body}

## New findings: plan-23 {#findings-23}

### SKETCHY ns23-r6-1: R1.6 and AC-20 still say PROPOSED, with a removal clause, after d9ag adopted them {#ns23-r6-1}

**Where:** the PROPOSED label appears in six live places:
- `task-23.1…:18` (header: "(R1.6, PROPOSED)");
- `:231` ("R1.6 (PROPOSED) turns this rule into a check");
- `:307` ("**PROPOSED (needs the user's confirmation)**");
- `:341` ("If the user declines, R1.6 and AC-20 are removed …");
- `:744` (AC-20 "PROPOSED with R1.6 (removed if the user declines)");
- `plan-23…:72` (the 23.1 task row: "a held-writer-lock check PROPOSED") and `:158` (open
  item 7: "**PROPOSED, needs the user**").

**What:**
- d9ag (`e41c6e8`) adopted R1.6 "as written". d9aj says that older revision tables keep
  PROPOSED as history, and that only LIVE status labels change.
- Every label above is live. The spec's own text tells an implementer that R1.6 and AC-20 are
  optional, and how to drop them.
- R1.6 is the only part of 23.1 that turns item 5 (the writer-lock rule) from a rule into a
  check. It also carries a full-suite census that has to happen before the check raises.

**Fix:**
- Relabel the six places "ADOPTED (d9ag)" and delete the "If the user declines" sentence and
  AC-20's "(removed if the user declines)".
- Plan-23 open item 7 becomes "SETTLED (d9ag)".
- The `#rev-round-5` row keeps "PROPOSED" (history, d9aj). Add a round-6 row citing d9ag.

**Pattern match:** YES. The spec trails a decision. This is the same shape as
`#imp-adopt-by-merge-not-sha`, here with a decision row instead of a hotfix.

### SKETCHY ns23-r6-2: R1.6's `writer_lock` is wired at one open, but the daemon assigns its writer Store at 8 sites, so the check switches itself off after any reopen {#ns23-r6-2}

**Where:** R1.6 item 2 ("`Store.writer_lock` (default `None`) is set by the `Daemon` to its
`_store_lock` when it opens its writer Store. A Store with no `writer_lock` … skips the check");
AC-20.

**What:**
- `daemon.py` assigns the writer Store at `:1665`, `:1734`, `:1757`, `:2888`, `:2924`, `:5490`,
  `:5508` and `:5557` (`self.store = Store(…)` / `d.store = Store(…)`). Those are the boot path
  and the reopen paths: fatal recovery, the replica-merge writer reopen, and the repair reopens.
- A spec that sets the field "when it opens its writer Store" gets one site right. After the
  first reopen, `writer_lock` is `None`, and the check's own exemption ("it has no lock to
  hold") turns a guarded store into an unguarded one, with nothing logged.
- bug-113 shows that the replica-merge path really does close and reopen the writer. So does
  bug-110's lock history (`bug_registry.md:166`).
- A reference captured at open time has a second problem: it goes stale if 23.2's
  `recorded_daemon` installs its recorder as `_store_lock` after the Store opened. That case is
  loud, because every op raises, but it is still wrong.
- bug-110 framing: the spec should say in one line that this check is about the THREAD lock.
  The DuckDB `fcntl` lock is covered by a separate rule: no in-process descriptor of the writer
  slot or its `.wal` in the daemon process, which is `_copy_out_of_process`'s rule. R1.6's census
  can therefore not be cited as proof against bug-110's class.

**Fix:**
- Resolve the lock dynamically. Either `Store.writer_lock` is a callable, or the Daemon installs
  every writer Store through ONE helper, `Daemon._install_writer_store(st)`, which sets it.
- An AST test asserts that no `.store = Store(` assignment exists in `daemon.py` outside that
  helper.
- AC-20 adds a case: after a reopen path (the replica-merge or fatal-recovery reopen),
  `flush_fragments()` from an unlocked thread still raises `WriterLockNotHeld`.
- Mutation: one assignment site bypasses the helper. It FAILS the AST test, and the reopen case
  FAILS too.
- Add the one-line scope note on the DuckDB file lock.

**Pattern match:** YES. This is `#imp-clean-corpus-hides-a-dead-gate`: a gate that turns off
silently. The census run would pass, because a check that is off reports no sites.

### SKETCHY ns23-r6-3: R8 and AC-13 build on `replica_merge`, which at 0.78.1 fails on every real store (bug-113, open) and copies an explicit table list {#ns23-r6-3}

**Where:** 23.1 R8 ("`replica_merge` merges `queue_offsets` by taking, per `(queue,
segment)`, the larger `offset_bytes` …"); AC-13 ("Two slots whose `queue_offsets` rows
differ"); `bug_registry.md:166` (bug-113); `replica_merge.py:35,57-122`.

**What:**
- `merge_slots` builds its target with `duckdb_catalog.init_catalog`. That function lacks
  `entities.vectors_partition`, so on any store whose slots carry the column it fails "13
  columns but 14 values". On its error path it also leaves its connection and ATTACH open, and
  the writer closed. All of this is bug-113, open.
- It merges an explicit list of tables. `queue_offsets`, `queue_counters` and `bounded_runs`
  are not on it, so they are dropped from the merged target unless BOTH `init_catalog` and
  `merge_slots` gain them.
- An AC-13 fixture built from two `init_catalog` slots would pass while the production command
  fails before it reaches any `queue_offsets` row.
- Writer rotation is dropped (round-5 `#facts`), so it is unclear what still produces two
  diverged slots. 23.1 does not say whether R8 protects a live path at all.

**Fix (choose one, in 23.1):**
- (a) Add a `Depends on:` line on bug-113's fix. R8 names `duckdb_catalog.init_catalog` and the
  `merge_slots` table list as files to change. AC-13 runs `_op_replica_merge` through a
  sandboxed daemon on slots built by `Store.init()` (the 14-column `entities`), and asserts that
  the writer is open and holds its lock afterwards (bug-110's second-process probe).
- (b) State that replica merge has no producer of diverged slots, and retire R8 and AC-13 with
  that evidence.

**Pattern match:** YES. This is `#imp-inventory-row-wrong-fence` (bug-110 r1): "fenced" was
about partition merge, while replica merge is live and broken.

### SKETCHY ns23-r6-4: 23.4 R6's by-name hash of `entity_links` has no rule for rows that resolve to no name (d9an's dangling links); the differential census covers fragment bits only {#ns23-r6-4}

**Where:** 23.4 R6 (`entity_links` hashed as "(entity's partition name, entity kind, entity
name, linkage name, concept's partition name, concept name) plus `weight`", resolved through
the run's own `entities`); the census ("bits whose entity is absent … or whose concept is in
neither"); d9an (dangling-link class: "cliquedb: 5,298 dead-entity + 8 dead-concept rows on
2026-10-14").

**What:**
- bug-111 (0.78.1) established that live catalogs hold `entity_links` rows whose entity or
  concept id exists in neither table. `repair_fragments` now counts them separately
  (`links_dead_entity`, `links_dead_concept`, `store.py:4370-4395`) and leaves them for plan
  22.
- 23.4's input is a copy of a live snapshot, so it carries such rows. R6 has no rule for them,
  and the two likely implementations both go wrong:
  - a resolver that raises gives an error at N = 1, which is INVALID on every copy, forever;
  - an inner join drops them silently, and then a run that creates or loses dangling rows is
    invisible to the oracle.
- The workload's "row deletes" can create dangling rows if the replayed delete shape does not
  also delete links. That is exactly the case the differential check exists for, and it does
  not reach `entity_links`.

**Fix:** this is a procedure change, so it needs a new user decision and a new pin row
(AC-1, d9ad).
- The census also counts dangling `entity_links` rows: per linkage, entity-dead and
  concept-dead, plus the untouched id set. A mismatch is a difference from the reference run's
  census, as for bits.
- The by-name hash excludes those rows explicitly.
- AC-3's smoke fixture carries 2 dangling rows. Mutation: a resolver that raises on them makes
  the positive control INVALID, so it FAILS.

{#findings-23-body}

### MEH nm23-r6-1: the hotfix moved again after round 5 (the d9ae fence, a fifth test file, bug-111's gates and direct swap), and item 7's correction did not happen {#nm23-r6-1}

R1.1 item 7 says: "If a later hotfix audit changes the code, this list is corrected to match the
merged code." The r4/r5 hotfix audits and bug-111 changed the code, and the spec still reads as
of `fb285cc`:
- **The fence (d9ae).** Merge's lock path no longer has a production caller. The
  `merge_partition` docstring says "no production caller since bug-105 r4 fenced the live merge",
  and `_op_partition_merge` refuses a live merge. Yet `#facts` round 5 says "an r4 audit is
  running", and R1.6 lists "merge's chunked yield" among the live non-harness writers. AC-20's
  "merge's end block taken out of its `with _lk:`" therefore kills a mutant on a path only the
  helix plan will call (d9ac).
- **Five files, not four.** `tests/test_fragment_repair_audit_r4.py` (fence, M1
  `_periodic_flush`, M11 `links_skipped`, M14 canonical verb, the r5 remap pins) is not in
  AC-3d's "pass unchanged" list. Its `test_periodic_flush_persists_another_bindings_dirty_bits`
  is 23.1's own case (i) under another name, on the exact function R6 re-plumbs.
- **bug-111.**
  - The repair's links half now applies the same liveness gate as the fragment half. 23.1's
    "UNION of the `entity_links` bits" text and the AC-3b/AC-4/AC-16 oracles ("equals the bitmap
    rebuilt from `entity_links`") omit it, which is wrong on any fixture holding a dangling
    link.
  - `_clear_purged_bits` (`store.py:6315`, r2) visits every partition by a DIRECT
    `_partition_id`/`_partition_name` swap, not by `with_partition`. Purge used to reach R1.6's
    `with_partition` check, and no longer does. R1.6 item 3's list of direct rebind sites names
    merge's end block and `_partition_keeping_yield`, but not this one.

**Fix:**
- Item 7's correction pass: name 5 files.
- Drop merge from R1.6's live-writer list (helix-owned).
- Add `_clear_purged_bits` to R1.6 item 3, with an AC-20 case: `purge_entity` from an unlocked
  thread raises, and no fragment row changes.
- Restate the oracles as "rebuilt from the `entity_links` rows whose entity and concept are
  alive".

**Pattern match:** YES, `#imp-adopt-by-merge-not-sha`, for the third round. It is not escalated:
the four contract points (per-binding cache, flush not clear, lock rule, alive predicate) are
all still true at HEAD, and item 7 was designed to absorb exactly this.

### MEH nm23-r6-2: R3.7's boot check runs the compaction "in the same hold" as the flag clear, but the compaction method takes the non-re-entrant lock itself {#nm23-r6-2}

**Where:** R3.7 step 3: "runs `_compact_factslog_if_needed(force=True)` (under
`_store_lock`, as that method already does) … and clears the flags in the same hold after the
compaction returns".

**What:** `_compact_factslog_if_needed` acquires `self._store_lock` itself (`daemon.py:2346`).
`_FairLock` is not re-entrant (the spec says so itself, in 22.2/17.1). So "the same hold" is
either a self-deadlock, if the caller wraps it, or two holds. Two holds is benign, because a
batch clears its own flag inside its own hold, but it is not what the text says.

**Fix:** either factor out `_compact_factslog_locked()` and call it and the clear inside one
hold, or say "two holds; the clear touches only the rows read before the compaction".

## New findings: plan-17 {#findings-17}

### SKETCHY ns17-r6-1: 17.4 R6 classifies by "the catalog opens" alone, so a lost or corrupt catalog with an intact live log loses up to a day {#ns17-r6-1}

**Where:** 17.4 R6 (a) ("detects this case (an active-slot catalog file exists in the live root
and opens) and refuses"); (b) step 1 (the ping refusal, listed only for (b)); step 4 ("Moves
aside … `facts.log`"); AC-9.

**What:**
- **Case (c) has no rule.** Here the catalog is absent or will not open, and the live
  `facts.log` is intact. Real precedents: the 2026-09-14 ART-index crash loop, and a catalog
  deleted with the log kept.
  - The script routes (c) to (b). It moves the NEWER live log aside and rebuilds from a copy up
    to a day old.
  - `rmx rebuild --from-log` on the live log, through the same throwaway-verify-promote
    sequence, would lose nothing.
  - #why calls the log "the one store file that cannot be regenerated", and this path throws
    away its newest day while it sits on disk.
- **The open probe has no stated position or mode.**
  - With the daemon up and the catalog healthy, DuckDB's lock refusal reads as "does not open".
    The right outcome (a refusal) then arrives only by accident, through (b)'s ping step.
  - A read-write open of a stopped store's catalog can replay its WAL. The probe should be
    read-only.

**Fix:**
- Run the ping refusal first, for every scenario. Make the open probe `read_only` and classify a
  lock error as "daemon up".
- Add a scenario (c): the catalog is absent or unopenable and the live log is present and
  parses. The rebuild source is the LIVE log (copied to the throwaway, verified, promoted). The
  backup copy is used only when the live log is missing or fails verification, and the script
  says which source it used.
- AC-9 (c): corrupt the catalog file, keep the live log, run the script. The post-copy appends
  survive. Mutation: (c) routed to the backup copy FAILS (the appends are missing).

### MEH nm17-r6-1: plan-17 open item 3 now trails plan-22, and `invoked_by` has no value for 22.2's in-process call {#nm17-r6-1}

- **Item 3 is stale.** It says "plan-22's side is plan-22's to write, and this item does not
  claim it is written", and that 22.2 "today … keeps 'its whole `entities` row except `id`'".
  22.2 R4 (`task-22.2…:110-155`) and AC-4b now write all of it (d9z). This is the reverse of r4.
- **`invoked_by` has no value for this caller.**
  - 17.1 R1 makes `invoked_by` "keyword-only and REQUIRED … supplied by the adapter (`cli` /
    `mcp` / `hub`), never by the caller". 22.2 R4 calls `vectors_restore(…, id_map=…)` from
    `removal_restore`, which is not an adapter.
  - So 22.2's call either raises `TypeError` or invents a value outside the vocabulary, and the
    R12 `runs.jsonl` line that records the surface has nothing true to record.
- **Fix:**
  - Item 3 becomes "written: 22.2 R4 / AC-4b (d9z)".
  - 17.1 R1 adds an in-process caller value (for example `invoked_by="removal_restore"`), or
    says 22.2 goes through the verb adapter. 22.2 R4 names the value.

### MEH nm17-r6-2: 17.1 R9's no-match filter covers the batch delete only; since 0.78.1 the memory bridge drops docs through the single-id delete {#nm17-r6-2}

- 17.1 R9 calls `_drop_lance_for_purge_batch` "the only vector delete on file re-sync" and
  filters only there.
- bug-111 (`176a0cd`, `ab088f4`) routes `ingest_gmd_paths(as_memory=True)`'s prior-doc drop
  through `purge_entity` (`ingest_gmd.py:910`), which calls `_drop_lance_for_purge`
  (`store.py:3679`). That function issues one unfiltered `ds.delete("id = N")` per entity,
  which is one Lance version per dropped doc, the bug-085 shape. It runs on the SessionStart /
  save-state bridge. In practice it is rare (one conversion per doc), but it is a vector delete
  path R9 does not cover.
- **Fix:** R9 applies the NULL-stamp filter in `_drop_lance_for_purge` too, or the doc drop
  batches its ids through `_drop_lance_for_purge_batch`. AC: an as-memory ingest that drops a
  never-embedded doc commits 0 Lance versions.

{#findings-17-body}

## Needs the user {#needs-user}

1. **ns23-r6-4** changes 23.4's procedure: the census counts dangling links, and the hash
   excludes them. Under AC-1 and d9ad that is a new user decision AND a new pin row. The ranges
   do not change.
2. **ns23-r6-3** (a) or (b): fix `replica_merge` first (bug-113), or retire R8/AC-13 because
   rotation is gone.
3. Everything else is a spec edit with no new decision. ns23-r6-1 is d9ag applied.

{#needs-user-body}

## Verdict {#verdict}

**plan-23: NEEDS-REVISION.** 6 new findings: 0 BULLSHIT, 4 SKETCHY (ns23-r6-1..4), 2 MEH.
Round 4: 7 of 7 closed.

**plan-17: NEEDS-REVISION.** 3 new findings: 0 BULLSHIT, 1 SKETCHY (ns17-r6-1), 2 MEH. Round 4:
3 of 3 closed.

**Totals:** 9 new findings (0B / 5S / 4M); round 4: 10 of 10 closed. The trend is 19 → 17 → 10 →
9, and this is the first round with no BULLSHIT. Two of the five SKETCHY findings are drift
against code that shipped after round 5 (bug-113 under R8, the reopen sites under R1.6).
{#verdict-body}
