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
> Status: Pending (revision round 5, 2026-10-14: re-review [[bsd-plan23-17-spec-rereview-r4-878647c]]
> (ns17-r4-1 with d9z option a, nm17-r4-1); see [[#rev-round-5]]. Round 3: [[#rev-round-3]].
> Round 2: [[#rev-round-2]])
> Depends on: 23.0 (test sandbox), 23.2 (hold + write-count recorder), 23.1 (`bounded_steps`,
> `bind(partition_name)`, `RunResult.hold_s`; [[task-23.1-queue-and-drain#r10-contract]]). 17.2
> schedules it.

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: derives-from -> [[project_daemon_wedge_per_entity_lance_delete]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81]]
rel: derives-from -> [[plan-review-2026-10-14#t3]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: related-to -> [[exploration-storage-concurrency-redesign#option-a]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns17-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns17-3]]
rel: implements -> [[plan-review-2026-10-14#t9]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns17-r3-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#ns17-r3-2]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#nm17-r3-1]]
rel: related-to -> [[task-22.2-repair-then-remove]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#ns17-r4-1]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r4-878647c#nm17-r4-1]]
rel: implements -> [[plan-review-2026-10-14#t11-approvals]]

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
     status=False, confirm_orphans=None, invoked_by=…)` and `vectors_restore(orphan_file,
     ids=None, id_map=None, dry_run=False, invoked_by=…)`, each a verb with a daemon op, CLI
     (`rmx vectors maintain`, `rmx vectors restore`) and MCP parity (the verb-parity test).
   - **The two signatures, exactly (nm17-r4-1: one statement, not two).** The verb layer:
     `vectors_maintain(partition: str | None = None, kinds: list[str] | None = None,
     dry_run: bool = False, older_than_s: int = 86400, status: bool = False,
     confirm_orphans: list[str] | None = None, *, invoked_by: str) -> dict` and
     `vectors_restore(orphan_file: str, ids: list[int] | None = None,
     id_map: dict[int, int] | None = None, dry_run: bool = False, *, invoked_by: str) -> dict`.
     `invoked_by` is keyword-only and REQUIRED at the verb layer and is supplied by the adapter
     (below), never by the caller: the CLI options and the MCP tool schema do not expose it.
     What a CALLER passes is everything before the `*`; plan-22's 22.2 calls `vectors_restore`
     with `orphan_file` and `id_map` (R10, d9z).
   - `older_than_s` is the d-2 window, env-overridable by `RMX_MAINTAIN_OLDER_THAN_S`; the
     production default is 86400.
   - `partition=None` means EVERY partition directory under `<root>/vectors/` (today
     `<project>` and `sessions-<project>`). The directory name IS the partition NAME
     (`vectors/<partition_name>/<kind>.lance`, `store.py:3620`, `:3648`), and each dataset's step
     is bound by that NAME through 23.1's `bind(partition_name)`, never by an id and never by the
     writer's current binding (spec review #s-5; ns17-2). A directory whose name has no
     `partitions` row is reported `refused:unknown_partition` and left untouched (`bind` raises
     `UnknownPartition` and never creates one, 23.1 R1.1).
   - `confirm_orphans: list[str] | None = None` releases capped reaps, one sha PER DATASET (R6,
     d9c, ns17-r3-2). Same parameter on the verb, the op, the CLI (`--confirm-orphans <sha>`,
     repeatable) and MCP; the hub never passes it.
   - `invoked_by: "cli" | "mcp" | "hub"` names the SURFACE and is set by the adapter, not by the
     caller: the CLI adapter passes `"cli"`, the MCP adapter `"mcp"`, 17.2 `"hub"` (nm17-r3-2;
     it replaces round 2's `"hand"` default, which every surface inherited). It is recorded in the
     run ledger (R12); a "hand run" below means `invoked_by` in `{"cli", "mcp"}`.
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
   - The datasets run through 23.1's `bounded_steps(datasets, bind=daemon_bind(d),
     partition_of=lambda ds: ds.partition_name, apply=_maintain_dataset, batch=1, budget_s=…,
     cancel=d._shutdown_event.is_set, on_error=…, hold_alarm_s=RMX_MAINTAIN_HOLD_S)`. Each
     dataset step (R2 a-f) is one `_store_lock` hold; the lock is released between datasets. No
     queue is used.
   - `on_error`: a fingerprint mismatch (R2 e) returns `"stop"` (no further dataset in this run);
     the daemon's fatal-invalidation classifier returns `"fatal"`; any other error returns
     `"stop"`. Nothing is dead-lettered (there is no queue).
   - `cancel` is checked before each hold, so a shutdown during a long compaction waits for that
     step to finish and starts no further dataset; a step is never aborted mid-commit.
   - `budget_s` = `RMX_MAINTAIN_STORE_BUDGET_S` (default 1800, the same value as 17.2's per-store
     budget). Datasets not reached are reported `pending:budget` and run on the next call.
   - The step's Lance work (tag, delete, compact, cleanup) is NOT inside the DuckDB
     `batch_transaction` (23.1 R3.7's boundary); recovery from a crash mid-step is the tag
     (R2 b) plus the orphan list (R6), which is why `bounded_steps` (no durability claim) fits.
   - Every hold's seconds come from `RunResult.hold_s` (23.1 R1.5): `hold_s[i]` is dataset `i`'s
     hold, and R7 reports it per dataset. A hold over `RMX_MAINTAIN_HOLD_S` (default 60) is the
     23.1 hold alarm: a warning in the report and `rmxd.log`, never a stop.
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
     `RMX_MAINTAIN_ORPHAN_CAP_PCT` = 5 % of the dataset's rows), the REAP is refused, and only the
     reap (ns17-3, d9c): no orphan is deleted, the dataset's outcome is `refused:orphan_cap`
     (`ok:false`), and 17.2 alerts. Compaction and cleanup STILL run, behind the same fingerprint
     gate, with expected B = A (nothing was reaped). So a capped dataset's version count still
     falls every night instead of regrowing toward bug-085. The cap is the guard the fingerprint
     arithmetic cannot be (that arithmetic only checks what was chosen).
   - **Releasing the cap (d9c, ns17-r3-2): per dataset, and by intersection.**
     - Every run that computes orphans (a dry run included) writes ONE candidate file PER DATASET,
       `<root>/maintain/orphans-candidates-<run_id>-<partition>-<kind>.jsonl` (`{partition, kind,
       id}` per line, sorted by id), and reports that dataset's `orphan_list_sha` = sha256 of
       that file's bytes. The sha and the file are one thing, and one dataset.
     - A hand run with `confirm_orphans=[sha, …]` first resolves every sha to its candidate file
       under `<root>/maintain/`. A sha that matches no file refuses the WHOLE call before any
       dataset step (`ok:false`, `unknown_confirm_sha: [<sha>]`), so a typo changes nothing.
     - For a dataset with a confirmed file, the reap set is the INTERSECTION of the confirmed
       file's ids and the CURRENT whole-catalog orphans of that dataset (recomputed at run time).
       Every id in it was seen by the user and is still absent from every partition, so the reap
       is safe; the cap is lifted for exactly that set. A confirmed id that is no longer an orphan
       (its entity came back) is not reaped and is reported `confirmed_not_orphan`. Orphans that
       are NEW since the dry run are not covered by the confirmation: they obey the cap on their
       own, as in any run (reaped when under it, refused and listed in a fresh candidate file
       when over it), and the outcome names them (`new_since_confirm: n`).
     - So churn between the dry run and the confirmation (a watcher re-sync, R9's NULL-stamp
       vectors) never forces a re-confirmation loop: the confirmed set is reaped and only the new
       ones wait.
     - The gate is the list, not the surface (d8g's shape): the parameter exists on CLI and MCP
       alike, and only a list someone has seen can be confirmed. 17.3 runs it by hand; the hub
       never does. This is the release for 22.5's moves and 22.3's audited forgets too.
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
10. **R10 Restore op** (decision d3a close-out amendment; decision review #b-5; ns17-r3-1).
    {#r10-restore}
    `vectors_restore(orphan_file, ids=None, id_map=None, dry_run=False, *, invoked_by)` reads
    the list (`ids` narrows it to those OLD ids) and never touches the embedder.
    - **Which files it reads (d9z).** Any file in the R6 orphan-list format whose path resolves
      under `<root>/maintain/` (17.1's own reaps) or `<root>/removal/` (22.2's removal vectors,
      below). A relative `orphan_file` resolves against `<root>`; a path outside those two
      directories is refused before anything is read (`ok:false`,
      `orphan_file_outside_store`). Each line's required fields are exactly R6's: `run_id`,
      `ts`, `partition` (a NAME), `kind`, `id` (the OLD entity id), `dim`, `vector`
      (`list[float]`, length `dim`), `dataset_version`. A line missing any of them is counted
      `malformed` and reported, never silently skipped; the rest of the file still restores.
    - **`id_map: dict[int, int] | None`** maps a file's OLD id to the NEW id its entity has now.
      Its caller is plan-22's 22.2 (d9z, option a): 22.2 restores removed entities with NEW ids
      ("restore is checked by NAME", [[task-22.2-repair-then-remove#r4]]), so its manifest keeps
      each removed entity's OLD id, and before its finalize deletes their vectors it writes them
      to `<root>/removal/<apply_id>.vectors.jsonl` in the R6 format; its restore builds
      `{old_id: new_id}` from the manifest after the name-checked re-insert and calls
      `vectors_restore(<that file>, id_map=…)`. Lance rows carry only `id`, `vector` and
      `updated_at` (`vectors.py:32-41`) and the file carries no name, so without the map no
      restored entity's vector could ever be found again (ns17-r3-1). The exact fields 22.2 must
      write are listed in the plan's cross-plan note ([[plan-17-nightly-store-maintenance#open-after-revision]]
      item 3); plan-22 owns that text (ns17-r4-1: this spec does not claim it).
    - For each listed row: the target id is `id_map[old]` when the map has it, else `old`. The
      target dataset is `vectors/<the target entity's partition NAME>/<its kind>.lance`, read
      from the catalog NOW (any partition), so a vector follows its entity if 22.5 moved it.
      `dim` is checked against that dataset's schema (a mismatch is `not_restored: dim`).
    - The vector is upserted under the target id only when the target entity exists now AND has
      no vector yet; an existing vector is never overwritten (`not_restored: present`, a newer
      embedding wins). A target entity that is absent is `not_restored: absent` and the row stays
      in the list (restoring it would only be reaped again). The row's `vectors_updated_at` stamp
      is set on the restored entity.
    - Each target dataset is written in ONE hold through `bind(partition_name)` (the target
      partition's NAME), entered once per dataset (nm17-r3-1: not "`bind(batch)`"). Restore is NOT
      a `bounded_steps` run, so it has no `hold_s`, `cancel` or budget; it reports per dataset the
      restored, absent, present and dim counts and its hold seconds measured around `bind`.
11. **R11 Single-flight per store** (decision d3e close-out amendment; decision review #s-6).
    {#r11-single-flight}
    A `vectors_maintain` or `vectors_restore` call that arrives while one is running on the same
    daemon returns immediately with `{"ok": false, "already_running": true, "run_id": …,
    "started_at": …, "dataset": …}` and starts nothing. `vectors_maintain(status=True)` returns
    the running state, or the last run's report when idle, and never starts a run.
    - Both checks are LOCK-FREE reads (nm17-1): the run state is an in-process object guarded by
      its own small `threading.Lock`, never `_store_lock`. Ops run on `bg_pool`
      (12 workers by default, `daemon.py:1820-1826`); a check that took `_store_lock` would queue behind a 19 s dataset hold,
      and 17.2's 30 s poll would time out.
12. **R12 The run ledger** (ns17-5, the arming gate's input). {#r12-ledger}
    Every completed `vectors_maintain` run appends one line to `<root>/maintain/runs.jsonl`:
    `{run_id, step: "vectors_maintain", invoked_by, dry_run, ok, started_at, finished_at,
    outcomes: {dataset: outcome}}`, fsynced. `invoked_by` is the surface (`cli` / `mcp` / `hub`,
    R1), so the arm gate can require a dry run BEFORE the real hand run (17.2 R7, nm17-r3-2). 17.2's arm verb reads it. The file is kept forever.
    - **Restore records its surface too (nm17-r4-1).** Every completed `vectors_restore` run
      appends one line of the same shape with `step: "vectors_restore"`, its `invoked_by`, the
      `orphan_file`, whether an `id_map` was given (`id_map_n`: its size), and per dataset the
      restored / absent / present / dim / malformed counts. `vectors_restore` is not a
      registered `maintenance_steps` step, so 17.2's arm gate never reads these lines (it reads
      by `(store, step)` and no step is named `vectors_restore`).
    Every step registered on 17.2's `maintenance_steps` writes the same line shape with its own
    `step` name (17.2 R2).

## Acceptance criteria {#acceptance}

All fixtures are real Lance datasets in tmp stores inside the 23.0 sandbox.

1. **AC-1a (window 0).** A store with 500 versions, 3 fragments and 20 orphans, run with
   `older_than_s=0`: every untagged old version is gone, versions = current + the run's tag
   (≤ 2), orphans → 0, fingerprint B = A minus the 20, and the orphan file holds 20 rows WITH
   vectors equal to the originals.
2. **AC-1b (production default).** The same fixture run with the default `older_than_s`: a version
   committed seconds before the run still exists after it. Fails if the default is changed to 0.
3. **AC-2 (gate before delete).** A test-provided `compact` callable compacts and then rewrites
   one vector. The `compact` seam is a keyword of the in-process maintain ROUTINE in `store.py`
   (default: Lance's `compact_files`), not an op argument, because a callable cannot cross the
   JSON socket (nm17-2); the test calls the routine on a tmp `Daemon` + `Store`. Result: `ok:false`; the dataset's current fingerprint equals A minus the reaped
   orphans; the version count is ≥ the count before the run (nothing cleaned up); the run's tag is
   present; the next dataset is untouched.
4. **AC-3 (out-of-daemon reader).** A reader thread opens a dataset before the run and, after the
   run's cleanup with `older_than_s=0`, scans it to the end without error, because the tagged
   version's files survive. A second reader through R4's helper, pointed at a version whose files
   were removed, succeeds on the retry and its `cli.log` row has `lance_retries: 1`.
5. **AC-4 (holds, ns17-2).** Three datasets on a real recorded `_FairLock` (23.2
   `recorded_daemon`): a competitor queued on `_store_lock` before each release wins between every
   consecutive pair of dataset steps (2 ordered wins, read from the recorder's thread names, the
   23.1 AC-1 shape); the recorder shows exactly one hold per dataset; `RunResult.hold_s` has 3
   entries and each is within 50 ms of the recorder's hold; the report's per-dataset hold seconds
   equal `hold_s`; `max_lock_hold(60)` holds over a 2,000-version fixture. The 46k-version bound is
   measured in 17.3.
6. **AC-5 (dry run).** Versions, bytes, files, tags and the orphan directory are unchanged; the
   report says what would happen.
7. **AC-6 (whole catalog).** Two partitions; an entity in partition B has a vector in partition A's
   dataset: it is NOT reaped. An id absent from both partitions IS reaped. `partition=None`
   maintains both partition directories.
8. **AC-7 (cap, release and fail closed; ns17-3, d9c).**
   - 60 orphans out of 100 rows, a 300-version dataset: the reap is refused
     (`refused:orphan_cap`), 0 orphans deleted, the fingerprint equals A, AND the version count
     after the run is lower than before (compaction and cleanup ran).
   - A dry run reports `orphan_list_sha` per dataset; a hand run with `confirm_orphans=[that sha]`
     reaps all 60 (orphan list with vectors, fingerprint B = A minus the 60).
   - **Churn after the dry run (ns17-r3-2).** After the dry run, one NEW orphan is created and one
     of the 60 gets its entity back; the cap is set to 0 (`RMX_MAINTAIN_ORPHAN_CAP_N=0`,
     `RMX_MAINTAIN_ORPHAN_CAP_PCT=0`), so any unconfirmed orphan is over it. The hand run with the
     dry run's sha reaps the 59 confirmed ids still orphaned, leaves the new one (refused by the
     cap and written to a fresh candidate file), reports `confirmed_not_orphan: 1` and
     `new_since_confirm: 1`, and the outcome names the new id. Fingerprint B = A minus exactly
     the 59. The id whose entity came back keeps its vector.
   - **Per dataset.** Two capped datasets; confirming only dataset X's sha reaps X's set and
     leaves dataset Y refused `refused:orphan_cap`. A sha that matches no candidate file refuses
     the whole call (`unknown_confirm_sha`) with no dataset touched.
   - A catalog with 0 entities → `refused:catalog_empty`, nothing deleted.
   - A `vectors/` directory with no `partitions` row → `refused:unknown_partition`, and the
     `partitions` row count is unchanged.
9. **AC-8 (restore round trip, same ids).** Reap 20 orphans, re-insert 15 of their entity rows
   with the same ids, run `vectors_restore`: 15 vectors restored with byte-equal vectors, 5
   reported `absent`; the fingerprint over the 15 equals their pre-reap contribution.
   - **AC-8b (new ids, the 22.2 case; ns17-r3-1, d9z).** A test writes a 22.2-shaped file
     `<root>/removal/<apply_id>.vectors.jsonl`: 20 lines in the R6 format, each holding a real
     entity's OLD id and the vector read from its dataset; those 20 entities are then purged
     and their vectors deleted (as 22.2's finalize does). Re-create 15 of them by NAME with NEW
     ids (as 22.2's restore does), 3 of them in the OTHER partition; run
     `vectors_restore("removal/<apply_id>.vectors.jsonl", id_map={old: new for the 15})`: the
     15 vectors are byte-equal under the NEW ids, the 3 sit in the other partition's dataset, 5
     are `absent`, and no vector was written under any old id. A second restore with the same
     map reports 15 `present` and writes nothing. A file outside `maintain/` and `removal/`
     is refused `orphan_file_outside_store`; a line missing `vector` is counted `malformed`.
     Mutations: `id_map` ignored (restore by old id) FAILS (15 `absent`); a restore that reads
     only `<root>/maintain/` FAILS (the removal file is refused).
10. **AC-9 (no-match filter).** A re-sync of a file none of whose ids carry `vectors_updated_at`
    commits zero Lance versions (dataset version unchanged); a file with one embedded id commits
    exactly one per kind.
11. **AC-10 (single flight and no fallback).** A second call during a run gets `already_running`
    and the 23.2 write-count recorder shows no second run's writes. While a dataset step holds
    `_store_lock` (a `compact` seam that blocks on an event), `vectors_maintain(status=True)` and
    the second call each return within 1 s (nm17-1). The CLI with the daemon down exits non-zero
    and no Lance version changes.
12. **AC-13 (run ledger).** A CLI dry run, a CLI run, an MCP run and a hub-invoked run each append
    one `runs.jsonl` line with `invoked_by` = `cli` / `cli` / `mcp` / `hub`, and the right
    `dry_run` and `ok`; a run that fails at the fingerprint gate appends `ok: false`. A CLI
    `vectors_restore` and an MCP one each append one `step: "vectors_restore"` line with their
    `invoked_by` and counts (nm17-r4-1), and 17.2's arm gate given only those lines refuses to
    arm `vectors_maintain`. A caller cannot set `invoked_by` through either surface.
13. **AC-11 (no model).** The 23.0 sandbox records zero connects to `models.sock` and zero
    embedder constructions during a run (maintain and restore).
14. **AC-12 (pre-registered mutations, each must FAIL a named AC):**
    - default `older_than_s` changed to 0 → AC-1b;
    - cleanup moved before fingerprint B → AC-2;
    - the restore of `v_reaped` on mismatch removed → AC-2;
    - the tag not created, or cleanup with tags not protected → AC-3;
    - orphans computed against the bound partition (+ kind) → AC-6;
    - the ratio cap removed → AC-7;
    - a cap refusal that also skips compaction → AC-7 (the version count does not fall);
    - `confirm_orphans` accepted without resolving the sha to its file → AC-7 (the unknown sha
      reaps);
    - the confirmed reap not intersected with the current orphans → AC-7 (the id whose entity came
      back loses its vector);
    - one candidate file per run instead of per dataset → AC-7 (per-dataset case);
    - `id_map` ignored by restore → AC-8b;
    - restore overwriting an existing vector → AC-8b (second restore);
    - restore reading only `<root>/maintain/` (not `<root>/removal/`) → AC-8b;
    - the `step: "vectors_restore"` ledger line dropped → AC-13;
    - the `runs.jsonl` line dropped → AC-13;
    - `invoked_by` taken from the caller instead of the adapter → AC-13;
    - `bind` by partition id, or a `bind` that auto-creates → AC-7 (unknown partition);
    - the status / single-flight check taking `_store_lock` → AC-10;
    - hold seconds taken from anything but `RunResult.hold_s` → AC-4;
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
| `src/refmatrix/daemon.py` | the `runs.jsonl` ledger (R12); `confirm_orphans`, `invoked_by` |

## Test strategy {#test-strategy}

- Every test runs inside task 23.0's sandbox (decisions d1a/d1b): `$HOME`, global root, registry
  and LaunchAgents dir redirected before `refmatrix` is imported, store roots injected, and any
  socket outside the tmp dir refused. The CLI tests patch `_root` to the tmp store.
- Real Lance datasets in tmp stores with a short tmp root; no Lance mocks. Lance-dependent test
  files skip only when lance is not installed (the r8 #s-4 rule).
- Lock assertions use 23.2's recorder (ordered competitor wins), `max_lock_hold` and write-count
  recorder on the real `_FairLock`. `lock_free_during` is not used here: it is called from inside
  the code under test, and between datasets there is no such call site (ns17-2).
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

## Revision round 2 (2026-10-14) {#rev-round-2}

| finding / decision | answered at |
|---|---|
| ns17-2 (`bind(batch)` vs `bind(partition_name)`; no `bounded_steps`; id vs name; no per-hold source; AC-4 misuses `lock_free_during`) | header, [[#r1-verb]], [[#r3-holds]], AC-4, [[#test-strategy]]; 23.1's `hold_s` ([[task-23.1-queue-and-drain#r10-contract]]) |
| ns17-3 (cap refuses the plan's own case and blocks compaction; no release), d9c | [[#r6-orphans]] (cap + release), [[#r1-verb]] (`confirm_orphans`), AC-7, AC-12 |
| ns17-5 (arming needs a hand-run record) | [[#r12-ledger]], AC-13 |
| nm17-1 (status / single-flight lock-free) | [[#r11-single-flight]], AC-10 |
| nm17-2 (`compact` seam is in-process) | AC-2 |
| nb23-1 (bind never creates a partition) | [[#r1-verb]], AC-7 |

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]].

| finding / decision | answered at |
|---|---|
| ns17-r3-1 (`vectors_restore` by id vs 22.2's new ids; dlr #s-7 for real) | [[#r1-verb]] (exact signature), [[#r10-restore]] (`id_map`, target dataset by the entity's partition and kind, never overwrite), AC-8b, AC-12 |
| ns17-r3-2 (`--confirm-orphans` sha per run vs per dataset; churn loops) | [[#r1-verb]] (`confirm_orphans: list[str]`), [[#r6-orphans]] (per-dataset files; intersection; new orphans obey the cap; unknown sha refuses the call), AC-7, AC-12 |
| nm17-r3-1 (R10 `bind(batch)`; two items numbered 12; no mutation for AC-13) | [[#r10-restore]] (`bind(partition_name)` once per dataset, no `hold_s`/`cancel`/budget), [[#acceptance]] numbering, AC-12 (`runs.jsonl` line dropped → AC-13) |
| nm17-r3-2 (`invoked_by` defaults to "hand" on every surface) | [[#r1-verb]], [[#r12-ledger]], AC-13; the gate is [[task-17.2-hub-nightly-tick#r7-unarmed]] |
| d9c (release form) | [[#r6-orphans]] |

## Revision round 5 (2026-10-14) {#rev-round-5}

Source: [[bsd-plan23-17-spec-rereview-r4-878647c]] and [[plan-review-2026-10-14#t11-approvals]]
(d9z, option a).

| finding / decision | answered at |
|---|---|
| ns17-r4-1 (`id_map` has no caller: 22.2 drops the old id and deletes the vectors itself), d9z option a | [[#r10-restore]] ("Which files it reads": `maintain/` and `removal/`, the R6 fields; `id_map`'s caller is 22.2's `removal/<apply_id>.vectors.jsonl`), AC-8b (a 22.2-shaped file; new mutation); the fields 22.2 must write: [[plan-17-nightly-store-maintenance#open-after-revision]] item 3 |
| ns17-r3-1 (partial in r4) | the ns17-r4-1 row |
| nm17-r4-1 (restore signature stated two ways; does restore record its surface) | [[#r1-verb]] (both signatures, `invoked_by` keyword-only, adapter-set), [[#r12-ledger]] (`step: "vectors_restore"` lines, unread by the arm gate), AC-13 |

