---
gmd: "0.1"
id: task-17.1-vectors-maintain-op
title: "Task 17.1: a daemon op that reaps whole-catalog orphan vectors, compacts and cleans each Lance dataset behind a fingerprint gate — bounded, restorable, never lossy"
tags: [task, daemon, lance, maintenance, compaction]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-14
---

# Task 17.1: the `vectors_maintain` and `vectors_restore` ops {#root}

> Plan: [plan-17-nightly-store-maintenance](../plan-17-nightly-store-maintenance.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 23.0 (test sandbox), 23.2 (hold + write-count recorder), 23.1 (`bind(batch)` seam,
> per-batch hold timer). 17.2 schedules it.

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: derives-from -> [[project_daemon_wedge_per_entity_lance_delete]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14#t3]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: related-to -> [[exploration-storage-concurrency-redesign#option-a]]

## Why {#why}

Nothing in `src/` compacts a Lance dataset or removes old versions. By hand on 2026-10-07:
- refmatrix 1.3 GB → 105 MB (`code.lance` 61,395 → 1 version);
- viascope 925 MB → 229 MB;
- cliquedb 1.1 GB → 62 MB.

Every dataset's fingerprint was identical before and after (`workflow/review-output/lance-compact-*.log`).
The hand run stopped the daemon so that no daemon write raced the compaction. Note what the daemon
does NOT hold: `LanceVectorStore` (`vectors.py:46`) keeps only `root`, `partition` and `dim`, and
every method opens `lance.dataset(path)` fresh (`vectors.py:114,131,146,171,258`), so there is no
in-daemon Lance handle to refresh. The readers that can hold a version across a cleanup are
out-of-daemon and lock-free (R4).

Orphan vectors (559 in this store's `code.lance`) are reaped only by a manual `embed --gc`, whose op
`_op_embed_gc` is at `daemon.py:5792` (the old citation `daemon.py:5538` pointed into
`_op_merge_slots`; spec review #m-1). That op builds an embedder just to learn the vector dimension,
and `Store.gc_vectors` (`store.py:3489`) defines an orphan as an id absent from the BOUND
partition + kind (`WHERE partition_id=? AND kind=?` with `self._partition_id`), which deletes the
vector of an entity that lives in another partition or kind. This task does not reuse that rule
(R6, decision d3a). {#why-body}

## Requirements {#requirements}

1. **R1 Verbs + daemon ops, every partition, no in-process fallback.** {#r1-verb}
   - `vectors_maintain(partition=None, kinds=None, dry_run=False, older_than_s=86400,
     status=False)` and `vectors_restore(orphan_file, ids=None, dry_run=False)`, each a verb with a
     daemon op, CLI (`rmx vectors maintain`, `rmx vectors restore`) and MCP parity (the
     verb-parity test).
   - `older_than_s` is the d-2 window, env-overridable by `RMX_MAINTAIN_OLDER_THAN_S`; the
     production default is 86400.
   - `partition=None` means EVERY partition directory under `<root>/vectors/` (today
     `<project>` and `sessions-<project>`), each processed under its own explicit partition id
     resolved from the `partitions` table, never the writer's current binding (spec review #s-5).
   - The CLI calls the daemon only. When `daemon_mod.ping(root)` fails it exits non-zero with
     `daemon not answering; vectors maintain never runs in-process` and changes nothing. It never
     builds a `Daemon(root)` in-process (the `embed --gc` fallback at `cli.py:10544-10549` is the
     pattern NOT copied; spec review #s-8).
2. **R2 Per dataset, in this order, gate before any delete** (spec review #b-3, decisions d3b,
   d-2). {#r2-order}
   - (a) **Fingerprint A**: `rows`, and `h = Σ blake2b_64(id ‖ vector bytes) mod 2^64` over every
     row. The sum is order-independent and per-id subtractable, so "A minus the reaped orphans" is
     computable (spec review #m-2). The read time counts toward the hold seconds in R7.
   - (b) **Tag** the current version `rmx-maintain-<run_id>` (`ds.tags.create`). This is the
     run's rollback point.
   - (c) **Orphans** by R6; refuse above the cap; write the orphan list (with vectors, fsynced);
     then delete them. Record the version number `v_reaped` after the delete.
   - (d) `optimize.compact_files()`.
   - (e) **Fingerprint B**. Expected: `rows_B = rows_A − n_reaped` and
     `h_B = h_A − Σ hash(reaped)`. Any other result: check out `v_reaped` and `restore()` it,
     run NO cleanup, keep every tag, return `ok:false` with a loud error naming the dataset, and
     touch no further dataset in this run.
   - (f) Only on a match: `cleanup_old_versions(older_than=timedelta(seconds=older_than_s),
     error_if_tagged_old_versions=False)`. Tagged versions are never removed (pylance 6.0.1
     semantics, verified in `.venv-eval`). Then delete the tag of the PREVIOUS successful run on
     this dataset, so the newest successful run's tag is always kept until the next successful
     run (d3b).
   - **Tag lifecycle across failed runs** (decision review, d3b verdict): a failed or refused run
     deletes no tag. Tags from consecutive failed runs accumulate until the next successful run,
     which releases every tag older than its own. The report lists the tags held per dataset.
3. **R3 Bounded lock holds through plan-23's seam** (spec review #s-1; decision d2b). {#r3-holds}
   - Each dataset step (R2 a-f) is one `_store_lock` hold, entered through 23.1's `bind(batch)`
     with the dataset's explicit partition, and timed by 23.1's per-batch hold timer. The lock is
     released between datasets. No queue is used.
   - Every hold's seconds are reported (R7). A hold over `RMX_MAINTAIN_HOLD_S` (default 60) is a
     warning in the report and `rmxd.log`; a dataset step is never aborted mid-commit.
   - No per-dataset Lance lock (d2b); the Option A revisit is recorded in the plan, triggered by
     23.4's verdict.
4. **R4 Out-of-daemon readers retry once and count it** (spec review #b-1; decision d3c; decision
   review #m-4). {#r4-readers}
   - The readers are `_replica_memory_recall` (`cli.py:10971`), `rmx recall` (`recall_cmd`,
     `cli.py:10791`) and `memory compile` (`consolidate.compile_memories(_read_store())`,
     `cli.py:12861`). Each Lance read they make goes through one shared helper: on a
     missing-file error (Lance `FileNotFoundError` / "not found" `OSError` on a data file), it
     re-opens the dataset at its current version and retries ONCE. A second failure propagates
     as today.
   - The count lands in the invocation's `cli.log` row as `lance_retries` (written by
     `log_cli_invocation`, `cli.py:14504`), 0 when none happened.
   - Nothing in the daemon is "refreshed"; the old R4 and its AC-3 are deleted, because
     `LanceVectorStore` caches no handle.
5. **R5 Skip cheap, with the real cost stated** (spec review #m-3). {#r5-skip}
   A dataset with fewer than `RMX_MAINTAIN_MIN_VERSIONS` (default 100) versions AND zero orphans is
   skipped and reported `skipped`. Knowing "zero orphans" costs one `list_ids` scan plus one
   catalog id query per dataset; that cost is reported as `check_s`. A dataset at or over the
   threshold is never skipped.
6. **R6 Orphans: whole catalog, capped, restorable** (spec review #b-4; decision d3a and its
   close-out amendment; decision review #b-5). {#r6-orphans}
   - **Definition.** An orphan is a vector whose id is absent from `entities` in EVERY partition:
     `SELECT id FROM entities WHERE id IN (…)` with no `partition_id` or `kind` predicate and no
     dependence on the writer's binding. A vector whose entity exists in another partition or kind
     is NOT an orphan.
   - **Fail closed.** If the catalog id read raises, or `SELECT count(*) FROM entities` is 0, the
     dataset is refused (`ok:false`, reason `catalog_unreadable` / `catalog_empty`) and nothing is
     deleted.
   - **Ratio cap.** If orphans > max(`RMX_MAINTAIN_ORPHAN_CAP_N` = 50,
     `RMX_MAINTAIN_ORPHAN_CAP_PCT` = 5 % of the dataset's rows), the reap is refused: `ok:false`,
     reason `orphan_cap`, no delete, no compaction of that dataset, and 17.2 alerts. The cap is
     the guard the fingerprint arithmetic cannot be (that arithmetic only checks what was
     chosen).
   - **Orphan list.** Before the delete, every orphan is appended to
     `<root>/maintain/orphans-<run_id>.jsonl` as `{run_id, ts, partition, kind, id, dim,
     vector: [float…], dataset_version}`, then fsynced. A failed write aborts the reap. The format
     is stable so that plan-22's restore can read it (decision review #s-7; its owner is listed in
     the plan's open items).
   - **Retention.** Orphan lists are kept forever (decay never loses knowledge); no plan-17 code
     rotates or deletes them.
7. **R7 Report, including the inverse repair** (spec review #m-4). {#r7-report}
   Per dataset: partition, kind; versions, fragments and deletion files before/after; bytes
   before/after; `orphans` reaped; `missing` (catalog rows in this partition + kind whose
   `vectors_updated_at` is set but which have no vector; their stamp is cleared, as `gc_vectors`
   does, which re-queues an embed); hold seconds; `check_s`; tags held; outcome (`ok`, `skipped`,
   `refused:<reason>`, `failed:<error>`). Returned in the op result and logged to `rmxd.log`.
8. **R8 The dimension comes from the dataset schema.** The op never constructs an embedder and
   never connects to `models.sock` (spec review #b-5). {#r8-dim}
9. **R9 No Lance commit for a delete that matches nothing** (spec review #b-6; r7 #m-1).
   {#r9-no-match-filter}
   `Store._drop_lance_for_purge_batch` (`store.py:3634`, the only vector delete on file re-sync via
   `purge_path` `store.py:5905` and `_bulk_purge_ids` `store.py:6032`) first filters each kind's ids
   to the catalog rows with `vectors_updated_at IS NOT NULL`. A kind left with no ids issues no
   `ds.delete`, so it commits no version. A vector whose row had a NULL stamp is left behind and
   becomes a whole-catalog orphan once the row is purged; the next `vectors_maintain` reaps it into
   the orphan list.
10. **R10 Restore op** (decision d3a close-out amendment; decision review #b-5). {#r10-restore}
    `vectors_restore(orphan_file, ids=None)` reads the list, checks `dim` against the dataset
    schema, and upserts the vector of every listed id whose entity is in the catalog NOW (any
    partition). Ids still absent are reported `not_restored: absent` and left in the list (a
    restore of them would only be reaped again). It runs through the same `bind(batch)` hold as
    R3 and never touches the embedder.
11. **R11 Single-flight per store** (decision d3e close-out amendment; decision review #s-6).
    {#r11-single-flight}
    A `vectors_maintain` or `vectors_restore` call that arrives while one is running on the same
    daemon returns immediately with `{"ok": false, "already_running": true, "run_id": …,
    "started_at": …, "dataset": …}` and starts nothing. `vectors_maintain(status=True)` returns
    the running state, or the last run's report when idle, and never starts a run.

## Acceptance criteria {#acceptance}

All fixtures are real Lance datasets in tmp stores inside the 23.0 sandbox.

1. **AC-1a (window 0).** A store with 500 versions, 3 fragments and 20 orphans, run with
   `older_than_s=0`: every untagged old version is gone, versions = current + the run's tag
   (≤ 2), orphans → 0, fingerprint B = A minus the 20, and the orphan file holds 20 rows WITH
   vectors equal to the originals.
2. **AC-1b (production default).** The same fixture run with the default `older_than_s`: a version
   committed seconds before the run still exists after it. Fails if the default is changed to 0.
3. **AC-2 (gate before delete).** A test-provided `compact` callable (the op takes the compaction
   step as a parameter whose default is Lance's `compact_files`) compacts and then rewrites one
   vector. Result: `ok:false`; the dataset's current fingerprint equals A minus the reaped
   orphans; the version count is ≥ the count before the run (nothing cleaned up); the run's tag is
   present; the next dataset is untouched.
4. **AC-3 (out-of-daemon reader).** A reader thread opens a dataset before the run and, after the
   run's cleanup with `older_than_s=0`, scans it to the end without error, because the tagged
   version's files survive. A second reader through R4's helper, pointed at a version whose files
   were removed, succeeds on the retry and its `cli.log` row has `lance_retries: 1`.
5. **AC-4 (holds).** Through 23.2: `lock_free_during` acquires `_store_lock` between datasets;
   `max_lock_hold(60)` holds over a 2,000-version fixture; the recorder shows exactly one hold per
   dataset. The 46k-version bound is measured in 17.3.
6. **AC-5 (dry run).** Versions, bytes, files, tags and the orphan directory are unchanged; the
   report says what would happen.
7. **AC-6 (whole catalog).** Two partitions; an entity in partition B has a vector in partition A's
   dataset: it is NOT reaped. An id absent from both partitions IS reaped. `partition=None`
   maintains both partition directories.
8. **AC-7 (cap and fail closed).** 60 orphans out of 100 rows → refused, nothing deleted, report
   `refused:orphan_cap`. A catalog with 0 entities → `refused:catalog_empty`, nothing deleted.
9. **AC-8 (restore round trip).** Reap 20 orphans, re-insert 15 of their entity rows with the same
   ids, run `vectors_restore`: 15 vectors restored with byte-equal vectors, 5 reported `absent`;
   the fingerprint over the 15 equals their pre-reap contribution.
10. **AC-9 (no-match filter).** A re-sync of a file none of whose ids carry `vectors_updated_at`
    commits zero Lance versions (dataset version unchanged); a file with one embedded id commits
    exactly one per kind.
11. **AC-10 (single flight and no fallback).** A second call during a run gets `already_running`
    and the 23.2 write-count recorder shows no second run's writes. The CLI with the daemon down
    exits non-zero and no Lance version changes.
12. **AC-11 (no model).** The 23.0 sandbox records zero connects to `models.sock` and zero
    embedder constructions during a run.
13. **AC-12 (pre-registered mutations, each must FAIL a named AC):**
    - default `older_than_s` changed to 0 → AC-1b;
    - cleanup moved before fingerprint B → AC-2;
    - the restore of `v_reaped` on mismatch removed → AC-2;
    - the tag not created, or cleanup with tags not protected → AC-3;
    - orphans computed against the bound partition (+ kind) → AC-6;
    - the ratio cap removed → AC-7;
    - the empty-catalog refusal removed → AC-7;
    - vectors not written to the orphan list → AC-8;
    - the no-match filter removed → AC-9;
    - the single-flight check removed → AC-10;
    - an in-process fallback added to the CLI → AC-10;
    - the dimension taken from an embedder → AC-11;
    - the lock held across datasets → AC-4;
    - the fingerprint check skipped → AC-2.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/vectors.py` | dimension from schema; fingerprint; tag/compact/cleanup/restore helpers; the retry-once reader helper |
| `src/refmatrix/store.py` | the maintain and restore routines (whole-catalog orphan query, cap, orphan list); the no-match filter in `_drop_lance_for_purge_batch` |
| `src/refmatrix/daemon.py`, `verbs.py`, `cli.py`, `mcp.py` | the ops with single-flight, verbs, CLI (no fallback), MCP |
| `src/refmatrix/cli.py`, `consolidate.py`, `telemetry.py` | readers use the retry helper; `lance_retries` on the `cli.log` row |

## Test strategy {#test-strategy}

- Every test runs inside task 23.0's sandbox (decisions d1a/d1b): `$HOME`, global root, registry
  and LaunchAgents dir redirected before `refmatrix` is imported, store roots injected, and any
  socket outside the tmp dir refused. The CLI tests patch `_root` to the tmp store.
- Real Lance datasets in tmp stores with a short tmp root; no Lance mocks. Lance-dependent test
  files skip only when lance is not installed (the r8 #s-4 rule).
- Lock assertions use 23.2's `lock_free_during`, `max_lock_hold` and write-count recorder on the
  real `_FairLock`.
- The mutation list in AC-12 is run before GREEN is declared; each mutation is restored in its
  own command.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 17 #b-1 | [[#why]], [[#r4-readers]], AC-3 (old R4/AC-3 deleted) |
| 17 #b-2 | [[#r1-verb]] (`older_than_s`), AC-1a, AC-1b, AC-12 |
| 17 #b-3 | [[#r2-order]] (e)-(f), AC-2, AC-12 |
| 17 #b-4 | [[#r6-orphans]], AC-6, AC-7, AC-12 |
| 17 #b-5 | [[#r8-dim]], AC-11, [[#test-strategy]] |
| 17 #b-6 | [[#r9-no-match-filter]], AC-9 |
| 17 #s-1 | header dependencies, [[#r3-holds]], AC-4 |
| 17 #s-5 | [[#r1-verb]], AC-6 |
| 17 #s-7 | [[#r3-holds]] (d2b; revisit in plan `#option-a-revisit`) |
| 17 #s-8 | [[#r1-verb]], AC-10 |
| 17 #m-1 | [[#why]] |
| 17 #m-2 | [[#r2-order]] (a) |
| 17 #m-3 | [[#r5-skip]] |
| 17 #m-4 | [[#r7-report]] |
| d2b | [[#r3-holds]] |
| d3a + close-out (cap, restore) | [[#r6-orphans]], [[#r10-restore]], AC-7, AC-8 |
| d3b (+ tag lifecycle) | [[#r2-order]] (b), (f) |
| d3c (+ decision review #m-4) | [[#r4-readers]] |
| d3e close-out (single-flight) | [[#r11-single-flight]] |
| decision review #b-5 | [[#r6-orphans]] (cap, retention), [[#r10-restore]] |
| decision review #s-7 | [[#r6-orphans]] (stable list format) |
| d1a/d1b (23.0) | [[#test-strategy]] |
