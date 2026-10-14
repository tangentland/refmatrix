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
> Status: Pending (revision round 2, 2026-10-14; [[#rev-round-2]])
> Wave: 1, after 22.1a (#t8-wave1).
> Depends on: 22.1a (plan manifest contract); 16.6 Wave-1 slice (`move_learned_provenance` and the
> sidecar events); 21.1 R5 (`telemetry.row_provenance`, for R7's query set); 23.1 (`bind(partition_name)`, `bounded_steps`); 23.2 (the
> write-count recorder); 23.0 (test sandbox). 22.1 (Wave 2) later adds the flag-sensitive classes
> to the engine's input; the primitives below already cover them.

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]
rel: derives-from -> [[plan-review-2026-10-14#t6-fixes]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: related-to -> [[plan-17-nightly-store-maintenance]]

## Requirements {#requirements}

1. **R1 Repairs** (user, 2026-10-07: "don't delete moves, repair them if possible"). {#r1}
   - `moved` (from 22.1, per `(concept, file)` set) → each row's `line` re-pointed to its paired
     new line through the re-point primitive ([[#r2]]). The row, its link, its sidecar row and the
     entity's protection are kept. `grown`/`shrunk` sets: surviving lines stay; only lines with no
     match left are removed (as `stale-line`).
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
     kind, no `tracked_files` row and no ingest evidence. `_bulk_purge_ids` is never called on an
     entity with an ingest link (it deletes all `entity_links` and `tracked_files`).
3. **R3 Row-level `facts.log` events, replayed (22 #b-3).** The replay knows only entity-level
   `tombstone` and append-only `evidence` today (`_apply_event_body`, `store.py:7460`; the LWW pass
   in `rebuild_index_from_log`, `store.py:7566`). Add three ops, keyed by NAME (never by id):
   `evidence_remove{linkage, c, e_kind, e, file, line, keep}`, `evidence_repoint{…identity,
   new_line}`, `entity_rename{kind, from, to, merged}`. Both replay paths apply them in log order
   after the `evidence` appends they refer to. The sidecar's own events (16.6 R1d:
   `learned_provenance`, `learned_provenance_move`) are logged by the same call, so a rebuild
   reproduces the sidecar too (b-2). {#r3}
4. **R4 Manifest and restore (22 #b-3, #m-4; DL #s-7).** {#r4}
   - The manifest `.refmatrix/removal/<id>.apply.jsonl` is an INTENT LOG: before each batch, an
     `intent` record with the full before-state of every row the batch touches (evidence rows with
     `file`/`line`/`detail`, sidecar rows, link weights, entity `protected`/`noise`, whether a
     vector existed); after the batch's transaction commits, a `commit` record (22 #s-2).
   - `removal_restore` reverts repairs (re-point back, un-collapse, rename back / un-merge) and
     re-inserts removals, from the manifest alone. It does not depend on `facts.log` replay (the
     global log is not a faithful source, 22 #m-4), and it emits the inverse events so a later
     rebuild agrees.
   - Restored entities get new ids; restore is checked by NAME. Vectors are restored first from
     plan-17's orphan list through `vectors_restore` (17.1 `#r10-restore`) when the reaped vector is
     there, and otherwise by re-embedding every restored entity whose manifest says it had one,
     through the shared embedder (DL #s-7: the vector may meanwhile have been reaped).
   - A partial apply (an `intent` with no `commit`) is restorable: restore applies an inverse only
     where the catalog holds that row's post-state.
5. **R5 Never ingest-owned; protection (22 #s-4; DL #b-2; d8b).** {#r5}
   - An entity that is ingested, tracked, or has any non-learned link keeps every non-learned link,
     its `tracked_files` row and its `protected` flag. Only its learned evidence rows change.
   - The engine never clears `protected` on an entity that survives the apply. Protection leaves
     only with a whole-entity purge of a learned-only entity, and the manifest restores it.
   - **Learner auto-protect distinguished.** Going forward, the `protect` event carries `source`:
     `upsert` from `upsert_entity(protected=True)` (`store.py:2183`), `user` from
     `set_entity_flag` / `set_flag_by_selector` (`store.py:6003`). Replay ignores the field. For
     existing protections the source is attributed from `facts.log`: `upsert` iff every `protect`
     event for the name directly follows an `entity` event for the same name; anything else,
     including a name the log does not hold, is `unknown` and counts as asserted. A learned-only
     entity whose protection is `user` or `unknown` is NOT purged; its learned rows may still be
     removed, and the entity is reported. (d8b: plan-19 no longer needs this source, so 19.3 does
     not depend on 22.2.)
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
     either missing or mismatched → refusal, nothing written.
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
   and `empty-learned` / `stale-subject` after the gate passes. **`ambiguous` (any sub-class) and
   `unverifiable` are never removed.** `orphan-root:home-readable` (22.1a; rows that read correctly
   today under no project store) is not a removal class: nothing is applied to it until the user
   rules on 22.5 R1's dry-run counts (d9b). {#r9}

## Acceptance criteria {#acceptance}

1. **Moved, not deleted (s-5).** On a fixture plan with a two-row `moved` set, both rows end on
   their new lines with link and protection intact and 0 rows deleted, and every sidecar row of the
   set joins its evidence row on ALL FIVE identity columns (new `line` included), with no sidecar
   row left on an old key. Mutations: `moved` deleted instead of repaired must FAIL; "re-point
   without moving the sidecar" must FAIL the join.
2. **Dry run writes nothing.** Catalog hash, Lance versions, queue files, `facts.log` unchanged.
3. **Replay (22 #b-3; b-2).** `--apply`, then `rebuild_index_from_log` on a copy, reproduces the
   post-apply state INCLUDING every evidence row's `(file, line)`, every rename, and EQUAL sidecar
   rows (every column but 16.6's three mark columns). Mutations: an apply that skips the new log
   events must FAIL; a re-point that skips the `learned_provenance_move` event must FAIL the
   sidecar equality.
4. **Restore by name (22 #b-3; DL #s-7).** `--apply` then `restore` gives, compared by NAME, equal
   entity sets with equal `protected`/`noise`, equal `(linkage, concept, entity, weight)` tuples,
   equal evidence rows (`file`, `line`, `detail`, multiplicity), equal sidecar rows, and a vector
   for every entity that had one. A by-id comparison is not used. Restore of a run killed between
   an `intent` and its `commit` also returns the pre-apply state.
5. **Ingest untouched (22 #s-6).** A shared learned+ingested file entity with a `missing-file`
   learned row keeps its ingest links and its `tracked_files` row byte-equal. Mutation: removing
   through `_bulk_purge_ids` must FAIL.
6. **Protection (22 #s-4).** A user-protected (`set_flag_by_selector`) entity with learned rows
   stays protected and is not purged; an entity with no attributable protect event is reported,
   not purged.
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
12. **Ambiguous and home-readable kept (d6a, d9b).** A plan holding an `ambiguous:root`, an
    `unverifiable` and an `orphan-root:home-readable` member applies nothing to any of them.
    Mutations: removing an `ambiguous` member must FAIL; removing a `home-readable` member must
    FAIL.
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
