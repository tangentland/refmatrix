---
gmd: "0.1"
id: bsd-plan17-spec-review-3104a81
title: "plan-17 spec review: the handle R4 refreshes does not exist, AC-1 cannot pass under d-2, the never-lossy check runs after the irreversible step and proves itself, and a tick test would maintain the 8 live stores"
severity: BULLSHIT
plan: plan-17-nightly-store-maintenance
task: spec-review-17.1-17.3
round: 1
tags: [bsd, audit, spec-review, lance, maintenance, hub, compaction, bug-088]
---

# ch-bsd spec review of plan-17 (pre-implementation) {#root}

**Commit reviewed:** `3104a81` (branch `wave0-spec-reviews`). The working HEAD was `1bc9e24`, which
changes only `handoff.md`, so the plan and the three task specs are byte-identical to `3104a81`.
**Written:** 2026-10-14T11:11:26-0700.

**Method:** I read the plan, tasks 17.1-17.3, the plan review (C3, C5, C6, wave order), plan-23 and
its tasks 23.1-23.2, the storage-concurrency exploration (Option A), task 19.4, plan-18 and the
bug rows 085/088/093/098. I checked each factual claim against `src/refmatrix/` at HEAD and
against live state, READ-ONLY: `ls`/`du` on `.refmatrix/vectors/`, `~/.refmatrix/registry.json`,
`launchctl list`, the LaunchAgents plists, the `lance-compact-*.log` and `r7-lance-cost.log`
evidence, and the pylance 6.0.1 API signatures in `.venv-eval` (no dataset was opened). I did not
run any `rmx` command or test suite, I opened no Store, and I made no mutation. I did not reopen
d-1..d-4. C3's open question (nightly reap or dry-run plus audited apply) is answered by d-4, so I
did not reopen it either.

rel: specifies -> [[plan-17-nightly-store-maintenance]]
rel: related-to -> [[plan-review-2026-10-07]]
rel: related-to -> [[plan-23-bounded-write-harness]]
rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]

## Claims verified {#verified}

- **Correct:**
  - No `compact_files` or `cleanup_old_versions` call exists in `src/`.
  - `_vector_store` and the `self._vs` cache are at `store.py:3377-3406`.
  - `_queue_alert_loop` is at `hub.py:699`, and its `_bus_retention_once()` call is at `:714`.
  - `Watchdog.is_paused` is at `hub.py:221`.
  - The `embed --gc` route exists (`cli.py:10500`, op `embed_gc`).
  - The hand-run numbers match the logs: code.lance 61,395 versions to 1 in 16.5 s; cliquedb
    concept.lance 46,606 versions / 738.6 MB to 1 / 57.5 MB in 18.9 s; r7's 10.2 s to 0.2 s flush.
- **Stale:** `daemon.py:5538` is in `_op_merge_slots`. `_op_embed_gc` is at `daemon.py:5792`.
- **Regrowth is fast.** Live, 7 days after the hand compaction, this store's datasets hold
  code 185 / concept 261 / doc 190 / memory 37 / sessions-memory 17 versions, and `vectors/` is
  150 MB again (it was 105 MB). That is about 25-37 versions per day per busy dataset. With R5's
  threshold of 100, a dataset gets compacted about every 4 days.
- **The fleet is 8 launchd daemons:** cliquet, tholley (= global), thiquet, atldb, viascope,
  refmatrix, orderly, cliquedb. `registry.json` lists only 3 of them (global, refmatrix,
  viascope).

{#verified-body}

## Findings {#findings}

### BULLSHIT #b-1: R4 refreshes a handle that does not exist; AC-3 and the "no handle refresh" mutation cannot fail, and the real concurrent readers are out of the daemon {#b-1}

**Where:** plan #design ("A hub- or CLI-side open would race the daemon's cached
`LanceVectorStore` handle"); 17.1 #why; R4; AC-3; AC-6 bullet 1.
**What the spec says:** the daemon caches a `LanceVectorStore` (`self._vs`) "that a cleanup can
invalidate". R4 drops and reopens it so that "no reader holds a removed version". AC-3 says "the
same read with R4 removed fails".
**What the code says:** `LanceVectorStore` (`vectors.py:46-277`) holds only `root`, `partition`
and `dim`. Every method (`upsert_vectors`, `drop_for`, `list_ids`, `read_vectors`, `ann_search`)
calls `lance.dataset(str(path))` fresh, so every call opens the latest version. No module in `src/`
keeps a `lance.dataset` object across calls. A read through `self._vs` after cleanup therefore
succeeds whether R4 runs or not. AC-3's "with R4 removed fails" cannot be built, and the AC-6
mutation "no handle refresh" survives by construction. The plan-of-plans row ("handle refresh")
inherits the premise.
**The hazard that does exist is unaddressed:**
- Lock-free Lance readers run outside the daemon:
  - `cli._replica_memory_recall` (`cli.py:10971`, "replica catalog slot + lock-free Lance") on the
    always-on prompt hooks;
  - `rmx recall` (`cli.py:10857`);
  - `memory compile`'s `consolidate.compile_memories(_read_store())` (`cli.py:12861`).
- `cleanup_old_versions(older_than=24h)` removes every version older than 24 h except the latest.
  On a dataset with no write in 24 h, the version an in-flight reader opened becomes
  non-latest the moment `compact_files` commits. Cleanup then deletes its data files under the
  reader.
- 17.2 R2's catch-up runs "at the first tick after wake", which is exactly when those prompt hooks
  start firing.
- No refresh inside the daemon can reach another process.

**Fix:**
- Delete R4 and AC-3, and correct the plan's premise.
- Replace them with a requirement that names the out-of-process readers and states the protection:
  - EITHER run cleanup with a version-retention floor (`retain_versions>=2`, or keep the
    pre-compaction version until the next run), so that an in-flight reader's version survives the
    pass;
  - OR state the failure mode (`_replica_memory_recall` returns None and falls back to the daemon
    RPC) and test that fallback against a real cleanup.
- An AC that can fail: a reader thread holding a dataset opened before compaction scans it to the
  end after cleanup runs.

**Pattern match:** YES. This is the fifth spec in a row whose AC cannot fail on the defect it
names (plan-16 r1-r4: tautological ACs).

### BULLSHIT #b-2: AC-1 cannot pass under d-2's 24 h window; it forces an undeclared knob, and the 24 h default then goes untested {#b-2}

**Where:** 17.1 AC-1; R2(d); plan #d-2.
**What:** AC-1 builds a fixture with 500 versions and expects "versions → ≤ 2 (24 h window: the
current version plus any made in the window)". A fixture built inside the test makes all 500
versions within the last few seconds. With `older_than=24h`, `cleanup_old_versions` removes none of
them, so the dataset ends at about 502 versions, not ≤ 2.

pylance 6.0.1's `cleanup_old_versions(older_than, retain_versions, ...)` takes no clock, and
Lance stamps each version with the wall clock at commit. To pass, the implementer has to add a
parameter (for example `older_than=timedelta(0)` in the test) that no requirement names. Once that
knob exists, nothing tests that production uses 24 h: the mutation `older_than=0` in the op's
default survives every AC, and d-2's rollback window is unverified.
**Fix:**
- Name the parameter in R1 (`older_than_s`, default 86400) and its env.
- Split AC-1 into two tests:
  - with `older_than_s=0`: versions → 1, orphans → 0, fingerprints hold;
  - with the default: a version committed seconds ago SURVIVES the run.
- Add "default `older_than` changed to 0" to AC-6's must-fail list.

**Pattern match:** YES (an AC that the implementer must bend: the cheap-fix shape, rule 10).

### BULLSHIT #b-3: the fingerprint check runs AFTER the irreversible step; the plan claims a mismatch "leaves the dataset as it was", and d-2's "rollback point" does not exist for the case it matters {#b-3}

**Where:** plan #design ("A mismatch fails the op loudly and leaves the dataset as it was");
17.1 R2 order (a)..(e); AC-2; plan #d-2.
**What:**
- R2 fingerprints at (a), reaps at (b), compacts at (c), cleans up at (d), and fingerprints again
  at (e). A mismatch found at (e) is found after (d) has deleted old versions.
- For a dataset with no write in the last 24 h, (d) deletes EVERY pre-compaction version. That
  includes the only one whose content matched fingerprint (a).
- "Leaves the dataset as it was" is impossible in that order. d-2's stated rationale ("a day of
  versions as a rollback point") holds only for versions written today. It never holds for the
  pre-compaction state of a quiet dataset, which is exactly what you would roll back to.
- AC-2 checks `ok:false` and "the remaining datasets are untouched". It never checks that the
  MISMATCHED dataset can be restored, so it passes on the lossy order.

**Fix:**
- Reorder: (a) fingerprint → (b) reap → (c) compact → (d) fingerprint against (a) minus the reaped
  orphans → (e) cleanup ONLY on a match.
- On a mismatch: `restore()` the version recorded after (b) (it still exists, because cleanup has
  not run), report `ok:false`, and stop.
- AC-2 becomes: after a forced mismatch, the dataset's current fingerprint equals fingerprint (a)
  minus the reaped orphans, and its old versions are still on disk.
- Add the mutation "cleanup before the second fingerprint" to AC-6.

**Pattern match:** YES (memory `feedback_decay_never_loses_knowledge`, which 17.1 itself cites:
"removal only via audited path").

### BULLSHIT #b-4: the "never lossy" proof is circular, and R6's orphan definition contradicts the `gc_vectors` it builds on {#b-4}

**Where:** 17.1 R6 ("The only rows removed are orphans: vectors whose entity id is absent from the
catalog. That is verified by the fingerprint arithmetic"); R2(b); plan #d-4.
**What:**
- **The definitions differ.** `Store.gc_vectors` (`store.py:3489-3557`) does not use "absent from
  the catalog". It computes `catalog_ids` as `SELECT id FROM entities WHERE partition_id=? AND
  kind=?`, using the writer's CURRENT binding (`self._partition_id`). A vector whose entity exists
  under another kind or another partition counts as an orphan and is deleted. That is broader than
  R6, and the spec never notices the difference.
- **The proof is circular.** The fingerprint arithmetic ("after == before minus the reaped
  orphans") checks that the op removed what it chose to remove. It cannot check that the choice
  was right. A wrong `_partition_id` makes every id in the dataset an "orphan", the arithmetic
  balances, and the op reports ok.
- **The binding has been wrong before.** bug-098: the shared writer binding moved under in-flight
  writes, and lock-free ops re-bound it. 0.77.1 fixed three such paths, and Option A of the
  storage exploration exists because this class keeps recurring.
- **The result would not be gradual.** With d-4 automatic and nightly, one bad binding wipes a
  whole dataset's dense layer in a single night, with an `ok:true` summary. The rows come back
  only through a full re-embed (a model load per store).
- **The safety net has no reader.** The orphan list keeps ids and kind but not the vectors, and no
  op reads `orphans-*.jsonl`.

**Fix:**
- Define an orphan as an id absent from `entities` in EVERY partition (`SELECT 1 FROM entities
  WHERE id=?`, with no binding), or have the user rule on partition+kind explicitly.
- Compute it with the partition id passed in explicitly, not read from the shared binding.
- Add a ratio cap: orphans > max(50, 5%) of a dataset → `ok:false`, no reap, and an alert.
- Write the orphan vectors (not only the ids) into the jsonl, so a reap is restorable without a
  model.
- Add these mutations to AC-6:
  - orphans computed against another partition must FAIL a test;
  - the cap removed must FAIL a test.

**Pattern match:** YES (bug-098 class; impression "a check whose corpus is already clean cannot
tell you it stopped checking").

### BULLSHIT #b-5: a 17.2 tick test would run `vectors_maintain` on the 8 live stores; "its own home" isolates none of the root sources {#b-5}

**Where:** 17.2 #test-strategy ("The test suite must not reach the live hub (bug-088): the tick
under test is constructed in-process with its own home"); 17.2 R3/R4; 17.1 R1 CLI/MCP tests.
**What:**
- **The store list comes from `discovery.discover_roots()`** (`discovery.py:108`). That is the
  union of four sources, and setting `RMX_HOME` covers only one of them:
  - `_roots_from_launchd()` reads `launchctl.LAUNCH_AGENTS_DIR = Path.home() / "Library" /
    "LaunchAgents"`. That is computed at IMPORT (`launchctl.py:20`), so a later HOME or RMX_HOME
    patch does not change it. Today it yields all 8 live roots.
  - `registry.json` under `user_home()` is covered by `RMX_HOME`.
  - `_cwd_root()` reads `REFMATRIX_ROOT`, or else walks up from the cwd. pytest runs from the
    repo root, so this finds THIS project's live `.refmatrix`.
  - `user_home()` itself.
- **Nothing would stop the calls.** bug-088's refuse stage is DEFERRED by the user, so the
  recorder only records. A tick under test whose root list is not injected sends a WRITE op
  (orphan reap + compaction + cleanup) to every live store.
- **This is not hypothetical.** bug-088's second sighting was a test reaching the live daemon with
  `_root` unpatched.
- **The other tests have the same gap:**
  - 17.1's CLI test goes through `_root()`.
  - `_op_embed_gc`'s precedent calls `d._embedder()`. A `RemoteEmbedder` there dials the live
    `models.sock`, the 66-connect class in bug-088.

**Fix:**
- 17.2 R3: the run takes `roots: Callable[[], list[Path]]`, injected in tests. The tests assert
  that the call list equals the tmp roots, and that the conftest recorder logged ZERO connects to
  any `registry.json` or LaunchAgents root.
- 17.1: the CLI test patches `_root`. The dimension comes from the schema (R2(b)), so the op must
  never touch the embedder or `models.sock`. Assert that through the recorder too.

**Pattern match:** YES (bug-088; memory `project_suite_reaches_live_sockets`).

### BULLSHIT #b-6: unanchored deferral — "Task 17.1 also considers skipping the delete when none of the file's ids were ever embedded" {#b-6}

**Where:** plan #why, bullet "Per-file commits remain (ch-bsd r7 #m-1)".
**What:** r7 #m-1's fix was "filter to ids the catalog says carry a vector, so a no-match delete
commits nothing". The plan points it at 17.1, but 17.1 has no requirement, AC or file entry for
it. No task under `workflow/plans/*-tasks/` covers it either. I checked plan-23's consumers (they
list only the bug-093 yield) and the deferral registry. "Considers" names no deliverable. Rule 9a:
the target exists, but no scheduled task does the work.
**Fix:** add it as 17.1 R8 with an AC (a re-sync of a file none of whose ids are embedded commits
zero Lance versions; measured on a 61k-version clone). Or file a task spec, and make the plan
sentence point at it.

**Pattern match:** YES (rule 9a, always BULLSHIT).

### SKETCHY #s-1: "through plan-23's bounded drain and hold recorder" names a queue drain and a TEST fixture; 17.1 says it depends on nothing {#s-1}

**Where:** 17.1 R3, AC-4, and the header "Depends on: —".
**What:**
- 23.1's `drain(queue, apply_batch, lock, batch, hold_s)` drains a `BoundedQueue` of JSONL events.
  Datasets are not queued events.
- 23.2's `hold_recorder` and `max_lock_hold` marker are pytest fixtures. They do not provide R3's
  PRODUCTION "each hold is measured and reported".
- AC-4's "each hold is ≤ the measured bound" is circular: no bound is named, and R3's 60 s is
  warn-only.
- The header contradicts R3 and the plan review's wave order (C5 harness first, then 17.1).

**Fix:**
- Depend on 23.1/23.2 explicitly.
- State what is reused: 23.2's `lock_free_during` + `max_lock_hold(S)` in tests, and a production
  hold timer, either 23.1's per-batch timer exposed as a helper or a local one.
- Give AC-4 a number. The measured worst single-dataset hold is 18.9 s (cliquedb concept), so
  assert < 60 s on a 46k-version clone.

### SKETCHY #s-2: the nightly run rides the queue-alert thread — disabling alerts silently disables maintenance, and a serial run blocks the alert for up to 80 min {#s-2}

**Where:** 17.2 #why, R1, R4.
**What:**
- `_queue_alert_loop` (`hub.py:699-714`) returns immediately when `RMX_HUB_QUEUE_ALERT_INTERVAL <=
  0`. An operator who turns off the fleet alert also turns off nightly maintenance, with no log
  line about maintenance.
- The loop first ticks 1,800 s after hub start.
- R4 allows 600 s per store, serial, on that same thread. Eight stores that time out hold off the
  queue alert and bus retention for 80 min.
- When the hub-side 600 s timeout fires, the daemon op keeps running. The hub records a failure for
  a run that may succeed, and that failure counts toward R5's three-night alert.

**Fix:**
- Decouple the gate: the maintenance check runs even when the alert is disabled. A test sets the
  interval ≤ 0 and asserts that maintenance still runs.
- Bound the whole run (a per-run budget), or run it on the long-op job pattern (`embed_start` +
  `_run_detached_job`) and poll for the result.
- Count a timeout separately from a failure.

### SKETCHY #s-3: first-run semantics are undefined, so the first tick after deploy pre-empts 17.3's backup-first hand run {#s-3}

**Where:** 17.2 R1/R2; 17.3 R1 ("Depends on: 17.1, 17.2; deployed"; "Each store is backed up
first").
**What:** `~/.refmatrix/maintain.json` does not exist today. With no stamp, "the scheduled time has
passed since the last run" is true at once. So the first tick after the 17.2 deploy (mid-day, 30 min
after hub start) runs the real op on every store, before 17.3's dry-run + APFS clone.
**Fix:** define the stamp-absent case (seed the stamp to "now" and run at the next 03:30), or ship
17.2 with `RMX_HUB_MAINTAIN_AT=off` until 17.3 R1 completes. Add an AC for the stamp-absent tick.

### SKETCHY #s-4: 17.3's measurements cannot fail, and its store list contradicts the plan {#s-4}

**Where:** 17.3 R1/R2; plan #tasks row 17.3.
**What:**
- **The latency AC cannot fail.** R2's "bug-085's symptom is the acceptance test" measures
  watch-flush latency on cliquet (4,941 versions), atldb (1,354), orderly (225) and global (≤ 5).
  The 10.2 s → 0.2 s effect lives at about 61k versions, so these stores show no difference
  whether maintenance works or not.
- **Global cannot be measured this way.** The global store is memory-only: every ingest route
  refuses filesystem paths (0.65.0), so it has no "watch-flush re-sync of a large file".
- **The task and the plan disagree.**
  - Store list: the plan row says 17.3 runs "on cliquedb + viascope", but that was done on
    2026-10-07. 17.3 omits thiquet and refmatrix, even though refmatrix has regrown to
    185-261 versions and 150 MB.
  - Backup removal: the plan row says "after N days", while 17.3 AC-3 says "after the user
    confirms".

**Fix:**
- Measure flush latency on a store that has regrown past the threshold, or on a clone with
  ≥ 30k versions. Record the per-store version counts before and after.
- Drop the global-store latency leg.
- Reconcile the plan row with 17.3, and include refmatrix and thiquet.

### SKETCHY #s-5: `partition=None` is undefined, and a store has two partitions {#s-5}

**Where:** 17.1 R1; 17.2 R4.
**What:**
- `vectors/` holds one directory per partition. This store has `refmatrix/` and
  `sessions-refmatrix/`, and the exploration's census says every store has exactly
  `<project>` + `sessions-<project>`.
- `_op_embed_gc` maps `partition=None` to the BOUND partition only.
- 17.2 calls the op once per store. If None follows the `embed_gc` precedent, the sessions
  partition's datasets are never maintained or reaped.

**Fix:** R1 says that None means every partition directory under `vectors/`, each under its own
explicit partition id (see #b-4). Add an AC with two partitions.

### SKETCHY #s-6: "registered, supervised, running" and "registry order" are undefined; `registry.json` names 3 of the 8 stores {#s-6}

**Where:** plan #design; 17.2 R3.
**What:** `~/.refmatrix/registry.json` lists global, refmatrix and viascope. cliquedb, the largest
store (1.1 GB, 59k versions), is in launchd but not in the registry. If "registered" means
`registry.json`, the store that motivated the plan is never maintained. If it means
`discover_roots()`, its order is sorted by path, not "registry order".
**Fix:** name `discover_roots()` (or the launchd label set), and define supervised as a launchd
label and running as a ping. Add an AC that a launchd-only root is maintained.

### SKETCHY #s-7: the op is welded to `_store_lock` + the shared `with_partition` binding that Option A (the exploration's recommendation) removes {#s-7}

**Where:** plan #design ("The daemon owns the Lance handles and `_store_lock`"); 17.1 R3; the
exploration's #option-a and #recommendation ("A first").
**What:**
- Under Option A, appends run without `_store_lock`, and "the Lance datasets ... keep their own
  locks". A maintain op that relies on `_store_lock` to exclude Lance writers would then compact
  and clean up concurrently with embed upserts.
- Its orphan check reads the shared binding Option A deletes (#b-4).
- Plan-23 is also partly absorbed by Option A.
- The spec does not mention Option A at all.

**Fix:** take a per-dataset maintenance lock that every Lance writer path (`upsert_vectors`,
`drop_for`, `_drop_lance_for_purge*`) also takes, with `_store_lock` held only for the catalog
read. Or record in the plan that 17.1 is to be revisited when Option A lands. Add a rel to the
exploration.

### SKETCHY #s-8: nothing forbids an in-process CLI fallback, and the `embed --gc` precedent has one {#s-8}

**Where:** 17.1 R1 (CLI `rmx vectors maintain`).
**What:** `embed --gc` (`cli.py:10539-10549`) checks `daemon_mod.ping(root)`. When the ping fails,
it builds a `Daemon(root)` in-process and runs `_op_embed_gc` against `_store()`. A ping can fail
because the daemon is busy, or because it is down while launchd respawns it. Copied, that pattern
compacts and cleans up Lance from the CLI while a respawned daemon writes the same datasets.
**Fix:** R1: the CLI refuses with a named error when the daemon does not answer, and never falls
back in-process. Add a test with the daemon down that asserts no Lance version changed.

### MEH #m-1: stale citation `daemon.py:5538` {#m-1}

`daemon.py:5538` is the merge-slots dry-run unlink. `_op_embed_gc` is at `daemon.py:5792`.

### MEH #m-2: the vector checksum is undefined, and "before minus orphans" requires a decomposable one {#m-2}

R2(a)'s "vector checksum" has to be order-independent and per-id subtractable, for example a sum
or XOR of per-(id, vector) hashes. Otherwise "after == before minus the reaped orphans" cannot be
computed. Reading the whole concept matrix (about 65k × 384 floats) under the lock adds to the
hold, so count it in R7's hold seconds.

### MEH #m-3: R5's "skipped after one directory listing" cannot know "no orphans" {#m-3}

Knowing there are no orphans takes `list_ids` plus a catalog scan per dataset. Either skip on the
version count alone, or state the real cost of the check.

### MEH #m-4: the report omits the inverse repair {#m-4}

`gc_vectors` also clears `vectors_updated_at` for catalog rows whose vector is missing. That is a
catalog write, and it queues a re-embed (a model load on the next `embed`). R7's report and 17.2's
summary should carry `missing` next to `orphans`.

### MEH #m-5: the stamp and failure counts are per store, but 19.4 and plan-18 register steps {#m-5}

17.2 R1 keeps `last_maintained` per store, and R5 counts failures per store. 19.4 R1 makes
`maintain.json` "the only stamps" for its compile step. Once steps are registered, a store whose
vectors step succeeded and whose compile step failed is stamped done, and is not retried until the
next day. Key the stamps and failure counts by (store, step). R5's "N (default 3)" also has no env
name.

## Verdict {#verdict}

**NEEDS-REVISION.** 19 findings: 6 BULLSHIT, 8 SKETCHY, 5 MEH.

**User decisions needed:**
1. **Orphan definition (#b-4).** Is an orphan absent from the whole catalog, or absent from this
   partition+kind? d-4 approved an automatic reap on the premise "the entity is already gone",
   but `gc_vectors` deletes vectors whose entity is merely in another partition or kind.
2. **Rollback (#b-3 with d-2).** Should the pre-compaction version be kept until the next run? d-2
   promised a rollback point, and today the order deletes the only matching version of a quiet
   dataset.
3. **Out-of-process readers (#b-1).** Should cleanup keep a version floor for lock-free hook
   readers, or accept the fallback to the daemon RPC as the failure mode?
4. **Option A (#s-7).** Should 17.1 use a per-dataset Lance lock now, or record a revisit when
   Option A lands?

{#verdict-body}

rel: contradicts -> [[claude#no-mocks]]

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 3104a81 (plan-17 spec review r1: plan + tasks 17.1-17.3, HEAD 1bc9e24 handoff-only; written 2026-10-14T11:11:26-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 19 (6B/8S/5M) | [[bsd-plan17-spec-review-3104a81]]. #b-1 R4 refreshes a LanceVectorStore that caches no Lance handle (every method re-opens lance.dataset); AC-3 + mutation unfalsifiable; real hazard = lock-free out-of-daemon readers (_replica_memory_recall on hooks) vs 24h cleanup on a quiet dataset. #b-2 AC-1 (500 test-made versions → ≤2) impossible under older_than=24h. #b-3 fingerprint after cleanup; "leaves the dataset as it was" impossible; no rollback for quiet datasets. #b-4 orphan = absent from bound partition+kind (gc_vectors) ≠ R6 "absent from catalog"; fingerprint proof circular; bug-098 binding → whole-dataset reap ok:true. #b-5 tick tests: discover_roots reads LaunchAgents at import + cwd root → 8 live stores get a write op. #b-6 r7 #m-1 no-match-delete filter "considered" by 17.1, no R. S: plan-23 drain/fixture misnamed; maintenance on alert thread (interval<=0 disables it, 80 min block); first-run stamp absent → pre-empts 17.3 backups; 17.3 latency AC can't fail; partition=None; registry.json 3/8; Option A; CLI in-process fallback. Read-only; no rmx, no suite, no Store. |
```

last_run.log (one line):

```
2026-10-14T11:11:26-0700 commit=3104a81 verdict=DIRTY findings=19 (6B/8S/5M) report=2026-10-14-1111-plan17-spec-review-phantom-handle-and-circular-orphan-proof-3104a81.md
```

IMPRESSIONS.md bullets:

- A spec that justifies a mechanism by a cached handle must be checked for whether the handle
  caches anything. `LanceVectorStore` is a path wrapper, and the real readers live in other
  processes. Check the object, not its name. {#imp-phantom-handle}
- "Verified by the fingerprint arithmetic" verifies what was removed, not whether it should have
  been. A deletion guard must be computed independently of the selection that chose the rows, and
  it must run BEFORE the irreversible step. {#imp-circular-guard}
- Any hub-tick spec: `discover_roots()` reads LaunchAgents at import plus the cwd root, so RMX_HOME
  isolates nothing. The root list must be injected. {#imp-discover-roots-live}

Proposed impression memory: `impression_bsd_guard_after_irreversible_step` (type impression,
tags `[impression, ch-bsd, never-lossy]`). Its lead line: a never-lossy check placed after the
delete, or computed from the delete's own selection, is a log line rather than a guard.
