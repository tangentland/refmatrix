---
gmd: "0.1"
id: task-22.2-repair-then-remove
title: "Task 22.2: repair what can be repaired, remove only what cannot — row-level events, intent-logged manifest, restore by name, bind-per-batch, ablation gate on a copy of the same store"
tags: [task, repair, removal, audit, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  revised: 2026-10-14
---

# Task 22.2: the repair-then-remove engine {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (revision round 5, 2026-10-14; [[#rev-round-5]]; round 3 in [[#rev-round-3]])
> Wave: 1, after 22.1a (#t8-wave1).
> Depends on: 22.1a (plan manifest contract); 16.6 Wave-1 slice (`move_learned_provenance` and the
> sidecar events); 21.1 R5 (`telemetry.row_provenance`, for R7's query set); 23.1 (`bind(partition_name)`, `bounded_steps`); 23.2 (the
> write-count recorder); 23.0 (test sandbox); 17.1 (`vectors_restore(..., id_map=)`, R4, d9z);
> 22.6 R6 (`entities.protect_source`, R5, d9ab). 22.1 (Wave 2) later adds the flag-sensitive
> classes to the engine's input; the primitives below already cover them.

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]
rel: derives-from -> [[plan-review-2026-10-14#t6-fixes]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: motivates -> [[task-22.6-removal-entry-points]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: related-to -> [[plan-17-nightly-store-maintenance]]

## Requirements {#requirements}

1. **R1 Repairs** (user, 2026-10-07: "don't delete moves, repair them if possible"). {#r1}
   - `moved` (from 22.1, per `(concept, file)` set) → each row's `line` re-pointed to its paired
     new line through the re-point primitive ([[#r2]]). The row, its link, its sidecar row and the
     entity's protection are kept. `grown`/`shrunk` sets: every row follows 22.1's pairing
     ([[task-22.1-audit-classes#r1]], r3 b-2): fixed points stay, paired rows are re-pointed, and
     only the rows 22.1 leaves unpaired (`stale-line` / `out-of-range`) are removed. A row is never
     removed because its old line number is outside the new set.
   - `duplicate` → collapse each row identity to one row. Nothing distinct is lost.
   - `orphan-root:resolved` → handed to 22.5's cross-store move (d6b/d8c). The engine never
     rewrites a relative global row into an absolute global entity (the global store is
     memory-only, `is_memory_only_root`, `store.py:503`; 22 #s-3).
   - `orphan-alias:repairable` → restore the `same_as` edge to the concept named EXACTLY in the
     alias's own description `alias of '<name>'`, only when that concept exists and is not `noise`
     (22 #s-5). No `canonical_name` lookup.
2. **R2 Primitives, row-level (22 #s-6, #s-3).** New `Store` methods, each called only under a
   batch hold, each logging its event ([[#r3]]): {#r2}
   - **Row identity** = `(linkage_id, concept_id, entity_id, file, line)`; every learned-row
     primitive also requires `detail LIKE 'learned from grep%'`, so ingest evidence is never
     matched.
   - **Owner of the sidecar's key columns (s-5).** Every primitive below that changes a column of
     16.6's sidecar key (`entity_id`, `linkage_id`, `concept_id`, `file`, `line`) moves or deletes
     the sidecar rows of that identity IN THE SAME TRANSACTION, through 16.6's
     `Store.move_learned_provenance(old_identity, new_identity)`
     ([[task-16.6-learned-row-validation#r1]]), which logs `learned_provenance_move`
     ([[task-16.6-learned-row-validation#r1d]]). A move onto a key that already exists collapses
     the two sidecar rows as 16.6 R1c does (earlier `learned_at`, max `stale_seen`, later mark).
     No primitive leaves a sidecar row on a key its evidence row no longer has.
   - `remove_evidence(identity, keep)` — `keep=0` deletes every copy; `keep=1` collapses to one.
     `keep=0` deletes the identity's sidecar rows (every reading); `keep=1` keeps them (the key is
     unchanged). The `evidence_remove` replay does the same.
   - `repoint_evidence(identity, new_line)` — updates `line` (and `span_end` by the same offset),
     and moves the identity's sidecar rows to the new `line`.
   - `rename_entity(kind, old, new)` — for an in-store `orphan-root` repair. **Merge on collision:**
     when `(partition, kind, new)` exists (`UNIQUE(partition, kind, name)`), the old entity's
     evidence rows and links re-attach to the existing entity, `protected` becomes the max of the
     two, every re-attached evidence identity's sidecar rows move to the new `entity_id`, and the
     old entity is purged only once it has no link left.
   - **Link and entity removal.** A `mentions` link is unlinked (existing `unlink` event) only
     when no evidence row remains for its `(concept, entity)`. An entity is purged through
     `_bulk_purge_ids` (`store.py:6032`, entity-level, tombstoned) ONLY when it has no link of any
     kind, no `tracked_files` row and no ingest evidence, AND it is unprotected or its
     `protect_source` is `learner` (R5, d9ab). `_bulk_purge_ids` is never called on an
     entity with an ingest link (it deletes all `entity_links` and `tracked_files`), with ONE
     exception: a member of a SELECTOR plan ([[task-22.6-removal-entry-points#r1]]), which the
     user named explicitly through `forget` / `memory forget` / `memory bulk-forget`; its intent
     record then holds every row `_bulk_purge_ids` deletes (R4), so restore returns them.
3. **R3 Row-level `facts.log` events, replayed (22 #b-3).** The replay knows only entity-level
   `tombstone` and append-only `evidence` today (`_apply_event_body`, `store.py:7460`; the LWW pass
   in `rebuild_index_from_log`, `store.py:7566`). Add three ops, keyed by NAME (never by id):
   `evidence_remove{linkage, c, e_kind, e, file, line, keep}`, `evidence_repoint{…identity,
   new_line}`, `entity_rename{kind, from, to, merged}`. The sidecar's own events (16.6 R1d:
   `learned_provenance`, `learned_provenance_move`) are logged by the same call, AFTER the
   evidence op's own event, so a rebuild reproduces the sidecar too (b-2). {#r3}
   - **ONE post-evidence pass, in log order (r3 m-1).** Both replay paths apply, after the
     `evidence` appends, ONE pass over the log in `facts.log` order holding every row-level op:
     `learned_provenance`, `learned_provenance_move` (16.6), `evidence_remove`,
     `evidence_repoint`, `entity_rename` (here) and `evidence_orphan_drop`
     ([[task-22.6-removal-entry-points#r5]]). Never a pass per op family: a re-point replayed
     before its row's `learned_provenance` event would leave that event no evidence row at the
     recorded line (`unresolved_provenance`), and the provenance would be lost. The same list
     and order is stated in [[task-16.6-learned-row-validation#r1d]].
   - On replay, `evidence_repoint` and `entity_rename` move only `linkage_evidence` rows; the
     sidecar keys move only from their own `learned_provenance_move` events. `evidence_remove`
     also removes the identity's sidecar rows (16.6 R1d).
4. **R4 Manifest and restore (22 #b-3, #m-4; DL #s-7).** {#r4}
   - The manifest `.refmatrix/removal/<id>.apply.jsonl` is an INTENT LOG: before each batch, an
     `intent` record with the full before-state of every row the batch touches; after the batch's
     transaction commits, a `commit` record (22 #s-2). The before-state is enough to rebuild
     every removed row by itself (r3 b-3), so it holds:
     - per touched ENTITY, its whole `entities` row, its OLD `id` included as `old_id` (d9z):
       `old_id`, `partition`, `kind`, `name`, `path`, `tldr`, `meta`, `canonical_name`,
       `protected`, `protect_source` ([[task-22.6-removal-entry-points#r6]]; NULL when
       unattributed), `noise`, `created_at`, `updated_at`, `vectors_updated_at`,
       `vectors_partition`, and whether a vector existed;
     - per touched entity that HAS a vector, the vector itself (d9z), in the vectors file
       `<root>/removal/<apply_id>.vectors.jsonl` (`<root>` the store root, `<apply_id>` this
       manifest's id; 17.1 R10 reads only `<root>/maintain/` and `<root>/removal/`), one line per
       entity in 17.1 R6's orphan-list format, exactly
       ([[task-17.1-vectors-maintain-op#r10-restore]];
       [[plan-17-nightly-store-maintenance#open-after-revision]] item 3): `run_id` (=
       `<apply_id>`), `ts` (write time, ISO-8601), `partition` (NAME at removal time), `kind`,
       `id` (the OLD entity id), `dim` (from the dataset schema), `vector` (`list[float]`, read
       from the Lance row, byte-equal on round trip), `dataset_version` (the Lance version it
       was read from). Each line is read inside the batch's hold, appended and fsynced before
       the batch's transaction commits, and so always BEFORE R6's finalize deletes any vector
       of that kind; a failed read or write aborts the batch, and so the finalize (22.6 R8, no
       silent failure). An entity whose catalog stamp says it had a vector but whose dataset
       holds none (a plan-17 reap took it first) is recorded `vector_missing_at_intent` and
       counted;
     - per MEMORY entity, its `memory_content` row (`content`, `mtype`, `tags`, `metadata`,
       `created_at`, `updated_at`; `duckdb_catalog.py:89`);
     - its `tracked_files` rows, when the plan removes them (a selector member only, R2);
     - every evidence row (`file`, `line`, `span_end`, `detail`, multiplicity) and its sidecar
       rows (every column);
     - every link (linkage name, other end by name, weight).
     This is ONE record form for every manifest plan-22 writes: class plans, 22.5's moves, and
     22.6's selector plans and derived-cleanup manifests.
   - `removal_restore` reverts repairs (re-point back, un-collapse, rename back / un-merge) and
     re-inserts removals, from the manifest alone. It does not depend on `facts.log` replay (the
     global log is not a faithful source, 22 #m-4), and it emits the inverse events so a later
     rebuild agrees.
   - Restored entities get new ids; restore is checked by NAME. **Vectors (d9z):** after the
     entities are re-inserted, restore builds `id_map = {old_id: new_id}` from the manifest's
     `old_id` and the re-inserted entity's id (looked up by `(partition, kind, name)`), and calls
     17.1's verb with the caller-facing part of its exact signature (`vectors_restore(
     orphan_file: str, ids: list[int] | None = None, id_map: dict[int, int] | None = None,
     dry_run: bool = False, *, invoked_by: str) -> dict`; `invoked_by` is set by 17.1's adapter,
     R1): `vectors_restore("removal/<apply_id>.vectors.jsonl", id_map=id_map)`, with NO 23.1
     `bind` held (17.1 R10 takes its own per-dataset `bind`; the lock is not re-entrant)
     ([[task-17.1-vectors-maintain-op#r10-restore]]). Each vector is re-inserted under the NEW id
     with no model call. Its per-dataset report is printed and recorded in the manifest:
     `present` (a newer vector exists and wins) is reported; `dim` (the dataset's dimension
     changed since) is re-embedded; `absent` cannot happen after a successful re-insert and is an
     ERROR, never skipped. A `vector_missing_at_intent` entity is restored from a plan-17 orphan
     list (`<root>/maintain/orphans-<run_id>.jsonl`, with the same `id_map`) when one holds its
     old id, else re-embedded through the shared embedder; both are counted (DL #s-7).
   - A partial apply (an `intent` with no `commit`) is restorable: restore applies an inverse only
     where the catalog holds that row's post-state.
5. **R5 Never ingest-owned; protection (22 #s-4; DL #b-2; d8b).** {#r5}
   - An entity that is ingested, tracked, or has any non-learned link keeps every non-learned link,
     its `tracked_files` row and its `protected` flag. Only its learned evidence rows change.
   - The engine never clears `protected` on an entity that survives the apply. Protection leaves
     only with a whole-entity purge of a learned-only entity, and the manifest restores it.
   - **Learner auto-protect distinguished (d9ab, r4 b-2).** A protection's origin is trusted ONLY
     from (a) an explicit `source` on its `protect` event, persisted in the catalog's
     `entities.protect_source` and re-emitted by the compactor
     ([[task-22.6-removal-entry-points#r6]]), or (b) a CLI/MCP command record naming the entity.
     Everything else is USER-ASSERTED.
     - Only `protect_source = 'learner'` (written only by `_learn_grep_hits`,
       `daemon.py:4295`) makes a learned-only entity purgeable as a learner auto-protection.
     - Command records: `cli.log`'s `argv` for `rmx protect`, `add-entity` and `add-concept`
       (without `--no-protect`) name a USER protection. MCP calls write no command record today
       (no call log in `mcp.py` or `verbs.py`, read at `7f2014a`); MCP protections are
       attributed through the event's `source` (`user`) once 22.6 R6 lands.
     - **Log adjacency is NEVER evidence.** `dump_catalog_to_log` (`store.py:7210`) writes every
       `protect` directly after its own `entity` (`store.py:7272-7284`), so in a compacted log
       adjacency is the compactor's signature, not the learner's. Round 3's "`upsert` iff every
       `protect` follows its `entity`" rule is WITHDRAWN.
     - A learned-only entity whose protection is user-asserted is NEVER removed by a class plan:
       its learned rows may still be removed (R9), the entity itself stays, protected, and is
       listed in the manifest as `kept: asserted-protection` with its counts. Only the user's
       explicit selector entry point ([[task-22.6-removal-entry-points#r1]]) removes such an
       entity.
     - Replay ignores `source` for the flag itself and restores `protect_source` from it.
       (d8b: plan-19 no longer needs this source, so 19.3 does not depend on 22.2.)
   - **The pre-build count (d9ab), taken 2026-10-14 14:30 PDT, read-only.** Copies of each
     store's `catalog.read.duckdb`, `facts.log` and `cli.log` in a fresh `mktemp -d` under the
     session scratchpad, opened with `duckdb.connect(read_only=True)` from `.venv-eval`; no
     `rmx`, no socket, no live file opened; the copies were deleted after the count. "Learned-only"
     = an entity with learned evidence, no other evidence, no `tracked_files` row at its path, and
     no link other than a `query/*` `mentions` link.

     | store | protected entities | of them learned-only | pytest-tmp learned-only | `protect` events with `source` | rule A (adjacency, round 3): learner | rule B (d9ab): learner | rule B: user-asserted |
     |---|---|---|---|---|---|---|---|
     | this repo (`refmatrix` partition) | 2,256 | 426 | 0 | 0 | 2,256 (all; 426 learned-only) | 0 | 2,256 (426 learned-only) |
     | global (`global` partition) | 4,946 | 4,793 | 1,655 | 0 | 4,946 (all; 4,793 learned-only) | 0 | 4,946 (4,793 learned-only) |

     Every `protect` event in both logs follows its own `entity` (2,303 / 2,303 here, 5,024 /
     5,024 global): this repo's log was compacted at 14:00:44 today, the global log on
     2026-10-07 01:13:11. The only CLI protect records (`rmx protect crud_probe`,
     `daemon_crud_probe`, 2026-06-11) name entities that are no longer protected. So under d9ab
     NO existing protection is learner-attributed: class plans may remove learned ROWS from all
     4,793 + 426 learned-only entities, but no existing entity is purged as a class member; new
     protections become purgeable once 22.6 R6 records `source=learner`. For information only
     (not a rule): treating a `cli.log` `rmx grep PATTERN` record as a learner record for the
     concept `query/PATTERN` would attribute 217 of this repo's 426 and 90 of the global 4,793
     learned-only entities (none of the 1,655 pytest-tmp ones).
6. **R6 Bounded, bound per batch, re-checked (22 #s-1, #s-2; #t2-fixes).** {#r6}
   - The apply is a bounded step loop over the in-memory plan through plan-23's `bounded_steps`,
     NOT the coalescing, overflow-dropping queue (`drain(queue)`): no repair or removal can be
     dropped.
   - Each batch takes the store lock once and binds its partition INSIDE that hold through 23.1's
     `bind(partition_name)` seam; the 23.2 recorder counts its writes.
   - Inside its hold, each row is re-classified with the same classifier; a row whose class
     changed since the audit (or since the dry-run on a copy) is skipped and counted
     `changed_since_audit`.
   - Lance deletes are collected across batches and finalized once per kind after the loop. The
     finalize is recorded in the manifest; re-running `apply` with the same manifest resumes an
     interrupted run (finalize included) and is idempotent.
7. **R7 The ablation gate, on a copy of THIS store (22 #b-5; d-3).** For the concept classes
   (`orphan-alias`, `empty-learned`, `stale-subject`): {#r7}
   - The gate runs on an APFS clone of the very store being applied, through a sandbox daemon, on
     the production read path (`build_context` / recall, the paths users run;
     `feedback_measure_the_path_users_run`).
   - **Pre-check:** every candidate in the plan exists in the clone; otherwise the gate refuses
     ("gate store lacks the candidates").
   - **Query set (s-6, d8d, d9g):** the store's own `query.log` questions, read from the copy taken
     with the clone, frozen into the manifest (hash + count). Each row is classified by 21.1's ONE
     classifier, `telemetry.row_provenance(row, reader_root=<the ORIGINAL store root recorded in
     the plan manifest>)` ([[task-21.1-context-usage-telemetry]] R5; owner 21.1, `telemetry.py`):
     `attributed` and `legacy_unattributed` rows are kept, `test_artifact` and `legacy_fixture`
     rows are excluded, and the three counts are printed (`excluded_test_rows=<n>
     legacy_fixture_rows=<n> legacy_unattributed=<n>`). This task carries no copy of the predicate.
     `reader_root` is the original root, not the clone's sandbox path, so the live rows are not
     misread as another test tree's.
   - **Measure (m-7):** run the frozen set on the clone, apply the plan to the clone with the engine
     itself, run it again. Per query, on EQUAL-LENGTH lists: `B` = the first 10 NON-candidate
     results of the baseline ranking (read deep enough to hold 10), `A` = the top 10 after the
     apply; displacement = 1 − Jaccard(`A`, `B`). A query whose only change is that a candidate
     left the list scores 0. Also recorded: whether a candidate was in the baseline top 10.
   - **Noise and verdict:** refuse when the paired bootstrap 95% CI of the mean displacement
     excludes 0; print the delta, the CI and the count of queries that retrieved a candidate.
8. **R8 Apply interface (d6e as amended by d8g; 22 #b-8 clause).** {#r8}
   - `removal_apply` and `removal_restore` are verbs on both surfaces ([[plan-22-audited-removal-and-repair#interface]]);
     the verb-parity test holds.
   - Apply requires a manifest id from a prior `removal_audit` of the SAME store (root, partition
     and catalog identity recorded in the plan) AND `--confirm <sha256 of that plan file>`;
     either missing or mismatched → refusal, nothing written. For a 22.6 SELECTOR plan the
     confirm value is instead its selection hash, rebuilt and compared at confirm time
     ([[task-22.6-removal-entry-points#r1]], r4 s-4), so an unrelated write between plan and
     confirm does not refuse; R6's per-row re-check still skips anything that changed.
   - Apply refuses any store root not named on its own command line (`--root`, and for 22.5
     `--target-root`); no root is discovered or defaulted.
   - **One spelling of "root" (m-8).** Every `--root`/`--target-root` names a STORE root: the
     `.refmatrix` directory, the value the daemon was started on (`Path(d.root)`, launchd's
     `REFMATRIX_ROOT`). The check is `Path(named).resolve() == Path(d.root).resolve()`. For the
     global store that is `~/.refmatrix` (recognised by `discovery.is_global_root`, which honours
     `RMX_HOME`, so the 23.0 sandbox's redirect works). A store's PROJECT root (its parent;
     `$HOME` for the global store) is only the base relative rows resolve against
     (`Path(root).parent`, `cli.py:667`, `daemon.py:2136`) and is refused as `--root`.
   - All writes go through daemon ops; no CLI path opens `Store()` on a live store.
9. **R9 Removals,** only for members with no correct form: `stale-line`, `out-of-range`,
   `missing-file` learned rows (22.1/22.1a); `orphan-root:unresolved`; `orphan-alias:unrepairable`
   and `empty-learned` / `stale-subject` after the gate passes; `dangling-link` (22.1a, d9an)
   through `remove_dangling_links(rows)`, which deletes exactly the listed `entity_links` rows and
   any fragment bit they still own, writes each row (with its weight) to the apply manifest
   ([[#r4]]) so restore re-inserts it, and logs one `link_remove{linkage, entity_id, concept_id}`
   event per row (by id: the dead endpoint has no name to key on); the selector members of a
   confirmed 22.6 plan. **`ambiguous` (any sub-class), `unverifiable` and
   `orphan-root:unverifiable` (22.1a, r3 s-3) are never removed.** `orphan-root:home-readable`
   (22.1a; rows that read correctly today under no project store) is not a removal class: nothing
   is applied to it until the user rules on 22.5 R1's dry-run counts (d9b). An entity whose
   protection is user-asserted (R5, d9ab) is never removed by a class plan; only its learned rows
   are. {#r9}

## Acceptance criteria {#acceptance}

- **Dangling links (d9an).** On the 22.1a AC-8a fixture, `--apply` removes the three members, and
  a following `repair_fragments(dry_run=True)` reports `links_dead_entity == 0` and
  `links_dead_concept == 0`; `restore` puts all three rows back with their weights. Mutation
  "remove without writing the manifest" FAILS the restore; mutation "also remove the live-doc
  row" FAILS the count.

1. **Moved, not deleted (s-5).** On a fixture plan with a two-row `moved` set, both rows end on
   their new lines with link and protection intact and 0 rows deleted, and every sidecar row of the
   set joins its evidence row on ALL FIVE identity columns (new `line` included), with no sidecar
   row left on an old key. Mutations: `moved` deleted instead of repaired must FAIL; "re-point
   without moving the sidecar" must FAIL the join.
2. **Dry run writes nothing.** Catalog hash, Lance versions, queue files, `facts.log` unchanged.
3. **Replay (22 #b-3; b-2; r3 m-1).** `--apply`, then `rebuild_index_from_log` on a copy,
   reproduces the post-apply state INCLUDING every evidence row's `(file, line)`, every rename, and
   EQUAL sidecar rows (every column but 16.6's three mark columns). The fixture re-points a row
   whose `learned_provenance` event precedes the re-point in the log. Mutations: an apply that
   skips the new log events must FAIL; a re-point that skips the `learned_provenance_move` event
   must FAIL the sidecar equality; "replay 22.2's ops in their own pass before the provenance ops"
   must FAIL it (`unresolved_provenance` > 0, the re-pointed row loses its sidecar row).
4. **Restore by name (22 #b-3; DL #s-7; r3 b-3).** `--apply` then `restore` gives, compared by
   NAME, equal entity sets with equal `path`, `tldr`, `meta`, `canonical_name`,
   `protected`/`noise`; equal `memory_content` rows (`content`, `mtype`, `tags`, `metadata`) for
   memory entities; equal `(linkage, concept, entity, weight)` tuples; equal evidence rows
   (`file`, `line`, `detail`, multiplicity); equal sidecar rows; and a vector for every entity
   that had one. A by-id comparison is not used. Restore of a run killed between an `intent` and
   its `commit` also returns the pre-apply state. The fixture plan holds a learned file entity
   (with `path`) and a memory entity. Mutations: "intent record without `path`/`tldr`/`meta`"
   FAILS it (the restored file entity has `path` NULL); "intent record without
   `memory_content`" FAILS it (the restored memory has no body).

   **4b. Vectors restored by `id_map`, no model call (d9z).** The fixture plan removes two
   learned-only entities with vectors and one with a catalog stamp but no Lance row. After
   `--apply` then `restore`: the manifest's `.vectors.jsonl` holds the two vectors under their
   OLD ids in 17.1's orphan-list form; restore calls `vectors_restore(orphan_file, id_map=...)`;
   the two restored entities (NEW ids) carry byte-equal vectors; the 23.0 sandbox records zero
   connects to `models.sock` for them; the stamped-but-missing one is counted
   `vector_missing_at_intent` and re-embedded. Mutations: "omit `id_map`" FAILS it (17.1 reports
   both `absent` and no vector is restored); "manifest without the vector side file" FAILS it.
5. **Ingest untouched (22 #s-6).** A shared learned+ingested file entity with a `missing-file`
   learned row keeps its ingest links and its `tracked_files` row byte-equal. Mutation: removing
   through `_bulk_purge_ids` must FAIL.
6. **Protection (22 #s-4; d9ab).** A user-protected (`set_flag_by_selector`) entity with learned
   rows stays protected and is not purged; an entity with no attributable protect event is
   reported, not purged. **6b (r4 b-2).** Three learned-only fixture entities, each with one
   `missing-file` learned row: X protected by `_learn_grep_hits` (`protect_source='learner'`), Y
   protected by `rmx protect Y` (`source=user`, a `cli.log` record), Z whose only protect event
   directly follows its `entity` event with no `source` (the compacted-log shape, written by
   running `dump_catalog_to_log` on a store whose `protect_source` column is NULL). The apply
   removes all three learned rows, purges X, keeps Y and Z protected and lists both
   `kept: asserted-protection`. Mutation "attribute by adjacency (round 3's rule)" FAILS it (Z
   purged); mutation "`protect_source` NULL counts as learner" FAILS it.
7. **Rename merge.** Renaming onto an existing name merges: one entity remains, it carries both
   entities' evidence and links, `protected` is the max, every moved evidence row's sidecar rows
   join it under the new `entity_id`, and an `entity_rename{merged:true}` event is logged.
8. **Two partitions (22 #s-1).** With a competitor that binds the store's other partition between
   batches, 0 rows of the other partition change (recorder + row diff). Mutation: binding once
   before the loop must FAIL.
9. **No loss under load (22 #s-2).** A plan larger than plan-23's queue cap applies every member;
   applied + `changed_since_audit` + refused = plan size, exactly. A row edited between audit and
   apply is skipped and counted.
10. **Gate (22 #b-5; m-7).** On a clone where removing a candidate alias displaces a non-candidate
    result, the gate refuses and prints the CI. On a clone where the candidate was in the top 10
    and its removal changes nothing else, the gate PASSES (displacement 0). Mutations: running the
    gate on a store that lacks the candidates must FAIL (the pre-check refuses); "compare the 9
    survivors against the new top 10" must FAIL the passing case.

    **10b. Query-set classifier (s-6).** A frozen set built from a fixture `query.log` holding an
    attributed row, a `pytest-of-*` cwd row and an `alpha|beta` no-cwd `grep` row keeps exactly the
    first and prints `excluded_test_rows=1 legacy_fixture_rows=1`. Mutation "classify with a local
    `pytest-of` substring check" FAILS it (the `alpha|beta` row survives).
11. **Interface (d8g, 22 #b-8; m-8).** Apply refuses: no manifest; a manifest from another store;
    a wrong `--confirm` hash; a `--root` that differs from the daemon's root; a missing `--root`;
    the global store's PROJECT root (`$HOME`) given where its store root (`~/.refmatrix`) belongs.
    The sandbox global store named by its store root is accepted. Each refusal writes nothing.
    Mutations: defaulting the root must FAIL; "compare against the project root" must FAIL the
    accepted case.
12. **Ambiguous, unverifiable and home-readable kept (d6a, d9b; r3 s-3).** A plan holding an
    `ambiguous:root`, an `unverifiable`, an `orphan-root:unverifiable` and an
    `orphan-root:home-readable` member applies nothing to any of them. Mutations: removing an
    `ambiguous` member must FAIL; removing a `home-readable` member must FAIL; removing an
    `orphan-root:unverifiable` member must FAIL.
13. **One Lance finalize per kind** per apply (recorder), not one per batch.

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): redirected `$HOME`/global root/registry/
LaunchAgents before import, in-process `Daemon` + `Store` on a short `mkdtemp`, real `_FairLock`,
the 23.2 recorder required, no `rmx` subprocess, the 23.0 guard active. Clones for the gate live
under the sandbox. Every listed mutation is pre-registered and must turn its test RED.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered in |
|---|---|
| 22 #b-1 (set repair) | [[#r1]]; AC-1 |
| 22 #b-3 (row-level replay; restore by name) | [[#r3]], [[#r4]]; AC-3, AC-4 |
| 22 #b-5 (gate on this store's copy) | [[#r7]]; AC-10 |
| 22 #b-8 clause (explicit root) | [[#r8]]; AC-11 |
| 22 #s-1 (`bind`, two partitions) | [[#r6]]; AC-8 |
| 22 #s-2 (no lossy queue, intent log, re-check) | [[#r4]], [[#r6]]; AC-4, AC-9 |
| 22 #s-3 (rename merge; memory-only global) | [[#r1]], [[#r2]]; AC-7 |
| 22 #s-4, DL #b-2, d8b (learner auto-protect) | [[#r5]]; AC-6 |
| 22 #s-5 (alias from its own text) | [[#r1]] |
| 22 #s-6 (row-level primitive) | [[#r2]]; AC-5 |
| 22 #m-4 (manifest, not log, recovers) | [[#r4]] |
| DL #s-5, d6e, d8g (one verb both surfaces; manifest gate) | [[#r8]]; AC-11 |
| DL #s-7 (vectors in restore) | [[#r4]]; AC-4 |
| d6a (ambiguous kept) | [[#r9]]; AC-12 |
| d6b/d8c (resolved rows move, not rewrite) | [[#r1]] |
| #t2-fixes (22's apply uses `bind` + recorder, not the lossy queue) | [[#r6]] |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan16-22-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]]. Later rows win.

| finding / decision | answered in |
|---|---|
| re-review s-5 (repairs change sidecar key columns; no owner) / #t9-fixes "22.2/22.5 update provenance keys" | [[#r2]] "Owner of the sidecar's key columns" (this task, through 16.6's `move_learned_provenance`); AC-1, AC-7 |
| re-review b-2 (22.2 AC-3 cannot see the sidecar) | [[#r3]] (sidecar events logged by the same call); AC-3 "equal sidecar rows" + mutation |
| re-review s-6 / #t9-fixes "d8d's predicate owned by 21.1 in `telemetry.py`" / d9g | [[#r7]] query set through `telemetry.row_provenance` (no local copy); AC-10b |
| re-review m-7 (displacement positive by construction) | [[#r7]] equal-length lists; AC-10 passing case + mutation |
| re-review m-8 (two spellings of the global root) | [[#r8]] "One spelling of root"; AC-11 |
| d9b (no-owner rows readable today: nothing applied until the user rules) | [[#r9]]; AC-12 |
| plan-22 r1 b-3 (partial: sidecar not replayable) | closed by the b-2 row and 16.6 R1d |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan16-22-spec-rereview-r3-6091648]] and d9k/d9o
([[plan-review-2026-10-14#t9-approvals]]). Later rows win over round 2.

| finding / decision | answered in |
|---|---|
| r3 b-3 / d9k (the manifest cannot restore memory bodies or entity `path`/`tldr`/`meta`) | [[#r4]] the ONE intent-record form (whole entity row, `memory_content`, `tracked_files` for selector members); AC-4 + two mutations; [[#r2]] selector exception; [[task-22.6-removal-entry-points]] |
| r3 b-2 (shifted rows removed) | [[#r1]] `grown`/`shrunk` follow 22.1's pairing |
| r3 m-1 (one replay pass) | [[#r3]] one post-evidence pass in log order (same list as 16.6 R1d); AC-3 + mutation |
| r3 s-3 (`Unverifiable`-only entities) | [[#r9]] `orphan-root:unverifiable` never removed; AC-12 + mutation |
| d9o (`evidence_orphan_drop`, selector plans, derived-cleanup manifests use this engine) | [[#r3]], [[#r4]], [[#r9]]; owned by 22.6 |

rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: derives-from -> [[plan-review-2026-10-14#t9-approvals]]

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan16-22-spec-rereview-r4-878647c]] and d9ab/d9z
([[plan-review-2026-10-14#t11-approvals]]). Later rows win over round 3.

| finding / decision | answered in |
|---|---|
| r4 b-2 / d9ab (adjacency reads every compacted protection as `upsert`) | [[#r5]]: origin only from `source` (`entities.protect_source`, 22.6 R6) or a CLI/MCP command record; adjacency withdrawn; user-asserted entities never class-removed, their learned rows may be; [[#r2]] purge rule; [[#r9]]; AC-6b + two mutations |
| d9ab pre-build count | [[#r5]] table: under d9ab 0 existing protections are learner-attributed (repo 2,256 / 426 learned-only; global 4,946 / 4,793 learned-only incl. 1,655 pytest-tmp); under the withdrawn rule all were |
| d9ab compactor companion | owned by [[task-22.6-removal-entry-points#r6]] (`source`) and [[task-16.6-learned-row-validation#r1d]] (`learned_provenance`), each with a compact-then-rebuild AC |
| d9z (`vectors_restore`'s `id_map` gets its caller) | [[#r4]]: `old_id` and the vector in the manifest (`.vectors.jsonl`, 17.1's orphan-list form); restore calls `vectors_restore(orphan_file, ids=None, id_map=..., dry_run=False)`; AC-4b + two mutations |
| r4 s-4 (selector confirm hash vs live writes) | [[#r8]]: a selector plan confirms by its selection hash (22.6 R1) |

rel: amends -> [[bsd-plan16-22-spec-rereview-r4-878647c]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]
rel: depends-on -> [[task-17.1-vectors-maintain-op#r10-restore]]

## Revision: dangling-link (2026-10-14, d9an) {#rev-dangling}

| finding / decision | answered in |
|---|---|
| d9an; bug-111 r1 #1 | [[#r9]] `remove_dangling_links`; the dangling-link AC |

rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]
rel: depends-on -> [[task-22.1a-provenance-free-classes#r1-dangling]]
