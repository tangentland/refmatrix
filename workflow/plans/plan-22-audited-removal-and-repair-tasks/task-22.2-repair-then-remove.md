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
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 1, after 22.1a (#t8-wave1).
> Depends on: 22.1a (plan manifest contract); 23.1 (`bind(batch)`, `bounded_steps`); 23.2 (the
> write-count recorder); 23.0 (test sandbox). 22.1 (Wave 2) later adds the flag-sensitive classes
> to the engine's input; the primitives below already cover them.

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.2-lock-hold-fixture]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]
rel: derives-from -> [[plan-review-2026-10-14#t6-fixes]]
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
   - `remove_evidence(identity, keep)` — `keep=0` deletes every copy; `keep=1` collapses to one.
     Their 16.6 sidecar rows follow by 16.6's sidecar key.
   - `repoint_evidence(identity, new_line)` — updates `line` (and `span_end` by the same offset).
   - `rename_entity(kind, old, new)` — for an in-store `orphan-root` repair. **Merge on collision:**
     when `(partition, kind, new)` exists (`UNIQUE(partition, kind, name)`), the old entity's
     evidence rows and links re-attach to the existing entity, `protected` becomes the max of the
     two, and the old entity is purged only once it has no link left.
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
   after the `evidence` appends they refer to. {#r3}
4. **R4 Manifest and restore (22 #b-3, #m-4; DL #s-7).** {#r4}
   - The manifest `.refmatrix/removal/<id>.apply.jsonl` is an INTENT LOG: before each batch, an
     `intent` record with the full before-state of every row the batch touches (evidence rows with
     `file`/`line`/`detail`, sidecar rows, link weights, entity `protected`/`noise`, whether a
     vector existed); after the batch's transaction commits, a `commit` record (22 #s-2).
   - `removal_restore` reverts repairs (re-point back, un-collapse, rename back / un-merge) and
     re-inserts removals, from the manifest alone. It does not depend on `facts.log` replay (the
     global log is not a faithful source, 22 #m-4), and it emits the inverse events so a later
     rebuild agrees.
   - Restored entities get new ids; restore is checked by NAME. Vectors are restored by
     re-embedding every restored entity whose manifest says it had one, through the shared
     embedder (DL #s-7: the vector may meanwhile have been reaped by plan-17's orphan reap).
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
     `bind(batch)` seam; the 23.2 recorder counts its writes.
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
   - **Query set:** the store's own `query.log` questions, frozen into the manifest (hash + count),
     excluding rows whose cwd or root is a pytest temp dir.
   - **Measure:** run the frozen set on the clone, apply the plan to the clone with the engine
     itself, run it again. Per query: displacement of NON-candidate results in the top 10
     (1 − Jaccard@10 after removing candidates from the baseline list), and whether a candidate was
     in the baseline top 10.
   - **Noise and verdict:** refuse when the paired bootstrap 95% CI of the mean displacement
     excludes 0; print the delta, the CI and the count of queries that retrieved a candidate.
8. **R8 Apply interface (d6e as amended by d8g; 22 #b-8 clause).** {#r8}
   - `removal_apply` and `removal_restore` are verbs on both surfaces ([[plan-22-audited-removal-and-repair#interface]]);
     the verb-parity test holds.
   - Apply requires a manifest id from a prior `removal_audit` of the SAME store (root, partition
     and catalog identity recorded in the plan) AND `--confirm <sha256 of that plan file>`;
     either missing or mismatched → refusal, nothing written.
   - Apply refuses any store root not named on its own command line (`--root`, and for 22.5
     `--target-root`); no root is discovered or defaulted. The named root must equal the
     resolved root of the daemon the op runs in.
   - All writes go through daemon ops; no CLI path opens `Store()` on a live store.
9. **R9 Removals,** only for members with no correct form: `stale-line`, `out-of-range`,
   `missing-file` learned rows (22.1/22.1a); `orphan-root:unresolved`; `orphan-alias:unrepairable`
   and `empty-learned` / `stale-subject` after the gate passes. **`ambiguous` (any sub-class) and
   `unverifiable` are never removed.** {#r9}

## Acceptance criteria {#acceptance}

1. **Moved, not deleted.** On a fixture plan with a two-row `moved` set, both rows end on their new
   lines with link, sidecar row and protection intact, and 0 rows deleted. Mutation: `moved`
   deleted instead of repaired must FAIL.
2. **Dry run writes nothing.** Catalog hash, Lance versions, queue files, `facts.log` unchanged.
3. **Replay (22 #b-3).** `--apply`, then `rebuild_index_from_log` on a copy, reproduces the
   post-apply state INCLUDING every evidence row's `(file, line)` and every rename. Mutation: an
   apply that skips the new log events must FAIL.
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
   entities' evidence and links, `protected` is the max, and an `entity_rename{merged:true}` event
   is logged.
8. **Two partitions (22 #s-1).** With a competitor that binds the store's other partition between
   batches, 0 rows of the other partition change (recorder + row diff). Mutation: binding once
   before the loop must FAIL.
9. **No loss under load (22 #s-2).** A plan larger than plan-23's queue cap applies every member;
   applied + `changed_since_audit` + refused = plan size, exactly. A row edited between audit and
   apply is skipped and counted.
10. **Gate (22 #b-5).** On a clone where removing a candidate alias displaces a non-candidate
    result, the gate refuses and prints the CI. Mutation: running the gate on a store that lacks
    the candidates must FAIL (the pre-check refuses).
11. **Interface (d8g, 22 #b-8).** Apply refuses: no manifest; a manifest from another store; a
    wrong `--confirm` hash; a `--root` that differs from the daemon's root; a missing `--root`.
    Each refusal writes nothing. Mutation: defaulting the root must FAIL.
12. **Ambiguous kept.** Mutation: removing an `ambiguous` member must FAIL.
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
