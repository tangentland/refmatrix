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
> Status: Pending (revision round 7, 2026-10-15; [[#rev-round-7]]; round 6 in [[#rev-round-6]], round 5
> in [[#rev-round-5]], round 3 in [[#rev-round-3]])
> Wave: 1, after 22.1a (#t8-wave1).
> Depends on: 22.1a (plan manifest contract); 16.6 Wave-1 slice (`move_learned_provenance` and the
> sidecar events); 21.1 R5 (`telemetry.row_provenance`, for R7's query set); 23.1 (`bind(partition_name)`, `bounded_steps`); 23.2 (the
> write-count recorder); 23.0 (test sandbox); 17.1 (`vectors_restore(..., id_map=)`, R4, d9z);
> 22.6 R6 (`entities.protect_source`, R5, d9ab; it lands in THIS task's slice, r6 m-7). 22.1 (Wave 2) later adds the flag-sensitive
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
     the two sidecar rows as 16.6 R1's `move_learned_provenance` does (earlier `learned_at`, max
     `stale_seen`, later mark; 16.6 R1c, which stated the same rule for `replica_merge`, is
     RETIRED by d9ay). No primitive leaves a sidecar row on a key its evidence row no longer has.
   - `remove_evidence(identity, keep, *, ingest_ok=False)` — `keep=0` deletes every copy; `keep=1`
     collapses to one. `keep=0` deletes the identity's sidecar rows (every reading); `keep=1` keeps
     them (the key is unchanged). The `evidence_remove` replay does the same.
     - **The ingest exception is named (r7 m-4).** By default the learned guard above holds: a row
       whose `detail` is not `learned from grep…` is not matched. `ingest_ok=True` lifts it, and
       exactly two callers pass it: R2's concept-side rule below and R9's
       `remove_dangling_evidence` (both remove ingest `rel:` evidence: 14,745 of cliquedb's 14,745
       dangling-evidence rows carry a `rel:` detail, r7 `#code-facts`). An AST test pins that list
       (AC-3c). Every `evidence_remove` event carries the row's `detail` as part of its identity, so
       replay deletes only rows with that exact `detail`, and applies the learned guard unless the
       event carries `ingest_ok: true`.
   - `repoint_evidence(identity, new_line)` — updates `line` (and `span_end` by the same offset),
     and moves the identity's sidecar rows to the new `line`.
   - `rename_entity(kind, old, new)` — for an in-store `orphan-root` repair. **Merge on collision:**
     when `(partition, kind, new)` exists (`UNIQUE(partition, kind, name)`), the old entity's
     evidence rows and links re-attach to the existing entity, `protected` becomes the max of the
     two, every re-attached evidence identity's sidecar rows move to the new `entity_id`, and the
     old entity is purged only once it has no link left.
   - **Link and entity removal.** A `mentions` link is unlinked (existing `unlink` event) only
     when no evidence row remains for its `(concept, entity)`. An entity is purged through
     `Store._bulk_purge_ids` (entity-level, tombstoned) ONLY when it has no link of any
     kind, no `tracked_files` row and no ingest evidence, AND it is unprotected or its
     `protect_source` is `learner` (R5, d9ab). `_bulk_purge_ids` is never called on an
     entity with an ingest link (it deletes all `entity_links` and `tracked_files`), with ONE
     exception: a member of a SELECTOR plan ([[task-22.6-removal-entry-points#r1]]), which the
     user named explicitly through `forget` / `memory forget` / `memory bulk-forget`; its intent
     record then holds every row `_bulk_purge_ids` deletes (R4), so restore returns them.
   - **No purge here leaves a dead-concept evidence row (r6 s-3, d9ar).** Neither
     `Store.purge_entity` nor `Store._bulk_purge_ids` deletes a `linkage_evidence` row (read at
     `3d3c798`), so an entity purged by this engine that is the CONCEPT of other entities'
     evidence rows (a `rel:` target, a selector member's doc) would leave each such row naming a
     dead id: a new `dangling-evidence` member ([[task-22.1a-provenance-free-classes#r1-dangling]]).
     Before such a purge, in the same batch, the engine records those rows in the intent record
     (R4's `evidence_row` form, with the concept named and its `old_id`, since it is still alive at
     intent time) and removes them through `remove_evidence(identity, keep=0, ingest_ok=True)`,
     which logs `evidence_remove` by name (with `detail` and `ingest_ok`). With R3's timestamp
     order (d9av) that event deletes on replay only the copies appended at or before it, so an
     identical row a later re-ingest of the other entity writes survives a rebuild (AC-3d). A
     restore of the purge re-attaches these rows to the restored concept (R4, r7 s-2). This holds
     for every purge the engine runs: class members, 22.5's moves and 22.6's selector members.
3. **R3 Row-level `facts.log` events, replayed (22 #b-3).** The replay knows only entity-level
   `tombstone` and append-only `evidence` today (`Store._apply_event_body`; the LWW pass in
   `Store.rebuild_index_from_log`). Add three ops, keyed by NAME (never by id):
   `evidence_remove{linkage, c, e_kind, e, file, line, detail, keep, ingest_ok}` (`detail` and
   `ingest_ok` added in round 7, r7 m-4), `evidence_repoint{…identity, new_line}`,
   `entity_rename{kind, from, to, merged}`. The sidecar's own events (16.6 R1d:
   `learned_provenance`, `learned_provenance_move`) are logged by the same call, AFTER the
   evidence op's own event, so a rebuild reproduces the sidecar too (b-2). {#r3}
   - **ONE row pass, appends and row ops together, in TIMESTAMP order (d9av; r7 b-1; replaces
     round 3's "after the `evidence` appends").** Both replay paths apply the `evidence` appends
     and every row-level op in ONE pass: `evidence` (the append), `learned_provenance`,
     `learned_provenance_move` (16.6), `evidence_remove`, `evidence_repoint`, `entity_rename`
     (here) and `evidence_orphan_drop` ([[task-22.6-removal-entry-points#r5]]), ordered by `ts`
     with ties broken by log position. So an `evidence_remove` (or a re-point, a rename, an
     orphan drop) at `T` acts only on the copies appended at or before `T`; a copy appended
     after `T` (a re-learned row, a re-ingested `rel:` edge) is applied after it and survives,
     exactly as the live store keeps it. The same rule, list and order is stated in
     [[task-16.6-learned-row-validation#r1d]], which builds the pass (this task adds its ops).
     - *Where the order comes from (read at `77ac38f`).* `Store.rebuild_index_from_log` sorts
       every event with `events.sort(key=lambda e: e.get("ts", 0))` (`store.py:7926`), a stable
       sort, so equal `ts` keep their log order; today it then collects `evidence` events into
       `evidence_events` (`:7998`) and applies them in pass 3 per partition (`:8087`), after
       entities, protections and links. The row pass replaces that `evidence_events` loop: per
       partition, it walks the evidence appends and row ops of that partition in the sorted
       order. The incremental path (`Store.apply_log_delta` → `_apply_one_event` →
       `_apply_event_body`) applies each event as it reads it, in log byte order, which already
       interleaves appends and row ops (`apply_log_delta` has no caller in `src/` at `77ac38f`:
       its only user, writer rotation, is dropped, d9ao; it stays tested).
     - *Within a call.* A primitive's sidecar event follows its evidence event in the same call
       (same `ts` from `_log_events`, or a later one from `_log_event`), so the tie-break by log
       position keeps it after; the learned provenance still follows its evidence row.
     - *Compaction is unaffected.* `Store.dump_catalog_to_log` gives each `evidence` event the
       synthetic `ts` `GREATEST(c.updated_at, e.updated_at)` (read at `77ac38f`) and a compacted
       log holds no `evidence_remove`, so the pass has nothing to order there; any row op logged
       after the compaction has a later `ts` than every dumped append. 16.6 R1d gives each dumped
       `learned_provenance` event its evidence row's `ts`, emitted after it.
     - Never a pass per op family: a re-point replayed before its row's `learned_provenance` event
       would leave that event no evidence row at the recorded line (`unresolved_provenance`), and
       the provenance would be lost (r3 m-1). Never a remove pass after all appends: it deletes a
       row the live store re-created after the remove (r7 b-1; AC-3d).
     - *How `c` resolves.* Each row op resolves `c` exactly as the `evidence` replay of the same
       row does: as kind `concept` (`store.py:8090` rebuild, `:7841` incremental). A row whose
       concept is a doc or memory entity is never rebuilt from its `evidence` event (r7
       `#code-facts`, a pre-existing replay gap this plan does not change), so its row op also
       resolves nothing there and is counted `skipped_unresolved`, never raised.
   - On replay, `evidence_repoint` and `entity_rename` move only `linkage_evidence` rows; the
     sidecar keys move only from their own `learned_provenance_move` events. `evidence_remove`
     also removes the identity's sidecar rows (16.6 R1d).
   - **No op keyed by id, ever (r6 b-1, d9aq).** The dangling removal of [[#r9]] adds NO op. It
     logs only existing, name-keyed events: `tombstone{kind, name}` and `unlink{linkage, c, e_kind,
     e}`, which `rebuild_index_from_log` resolves in its LWW pass (pass 2: a tombstone whose `ts`
     is at or after the key's latest `entity` event drops the entity; the latest of `link` /
     `unlink` per `(partition, linkage, c, e_kind, e)` wins), and `evidence_remove`, already in
     the one pass above. The incremental path (`Store.apply_log_delta` → `_apply_one_event` →
     `_apply_event_body`) resolves the same events by name; against a catalog that no longer
     holds the endpoint they resolve to nothing and are counted `skipped_unresolved`, never
     raised. Round 5's `link_remove{linkage, entity_id, concept_id}` is WITHDRAWN: a rebuild
     re-assigns every id through `upsert_entity`, so an id-keyed event matches nothing after it
     (or an unrelated row that now holds the id), and no replay path read it.
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
   - **Rows with a dead endpoint (r6 s-1; d9an, d9ar).** A `dangling-link` or `dangling-evidence`
     member touches no live entity on its dead side (and a both-dead link row, 7 on cliquedb,
     touches none at all), so the per-entity form above cannot hold it. Two more intent records,
     part of the same ONE form:
     - `link_row`: `{linkage, live_end: {side, partition, kind, name, old_id} | null, dead_end:
       {side, old_id, names_from_log: [{partition, kind, name}] | []}, dead_concept_too: bool,
       weight}`. `side` is `entity` or `concept`; `live_end` is null for a both-dead row;
       `names_from_log` is what [[#r9]]'s naming rule found (empty when nameless); `weight` may be
       NULL (379 of cliquedb's dead-entity rows).
     - `evidence_row`: `{linkage, live_entity: {partition, kind, name, old_id}, dead_concept:
       {old_id, names_from_log}, file, line, span_end, detail, multiplicity}`, plus the sidecar
       rows of that identity when its `detail` is a learned one.
     - **Restore of these two** resolves the live end BY NAME in its recorded partition (never by
       `old_id`) and re-inserts the row with the recorded DEAD id unchanged, so the restored row is
       the dangling row it was. It re-adds NO fragment bit: a bit of a dead endpoint is exactly what
       `Store.repair_fragments` drops, so restore and the repair agree. It emits no event and does
       not withdraw [[#r9]]'s tombstones: the endpoint is still dead in the catalog, and withdrawing
       the tombstone would re-arm the resurrection d9aq closes. A restored dangling row is
       therefore catalog-only; a later rebuild drops it, as it drops every row whose endpoint the
       log cannot name. A live end that no longer exists by name at restore time is counted
       `restore_live_end_missing` and printed, never re-attached by id.
     - **Every recorded dead id is re-checked before the re-insert (r7 s-1).** A dead id is dead
       only relative to the catalog it was recorded from: a rebuild creates a fresh catalog whose
       `seq_entities_id` starts again (`duckdb_catalog.py:50`, the `DEFAULT nextval` id column)
       and `upsert_entity` hands out dense ids, so the recorded id may name a LIVE, unrelated
       entity by restore time. For each recorded dead id (both ids of a both-dead row), in this
       order: (1) when THIS manifest's restore re-creates the entity that held it, the id is
       mapped through the restore's `id_map` (next bullet) and the row is re-attached live; (2)
       else restore asks the shared predicate, `LinkLiveness.dead_side`
       ([[task-22.1a-provenance-free-classes#r1-dangling]]), on the row as it would be
       re-inserted; when the recorded id is live now, the row is NOT inserted and is counted
       `restore_dead_id_reused` and printed with the id and the live entity's name; (3) else the
       row is re-inserted dangling, as above. A row restored dangling therefore always is
       dangling (AC-4c asserts it); it never becomes a live link to an unrelated entity, which
       `repair_fragments` would then turn into a queryable bit (`added_from_links`).
   - **Restore maps every recorded old id through its own `id_map` (r7 s-2).** Restored entities
     get new ids (below), so a row that names a restored entity by its OLD id would come back
     dangling the moment restore finishes. Restore therefore applies the `id_map` it builds for
     `vectors_restore` (below) to:
     - the dead side of every `link_row` / `evidence_row` it re-inserts, when that dead id is a
       key of the map (an engine purge of concept `A` records the concept-side rows of `B` with
       `A`'s `old_id`, R2): the row is re-inserted LIVE onto the restored entity, its bit set, and
       its `link` / `evidence` event logged by name (the purge logged `evidence_remove` for it, so
       under R3's timestamp order the new append is the one a rebuild keeps);
     - every SURVIVING `entity_links` / `linkage_evidence` row in the catalog that still names a
       restored old id (a purge outside the engine, 22.6 R2 `untrack`, R3, the `--as-memory`
       conversion, records only the purged entity's own rows and leaves `B`'s row in place,
       22.6 AC-9b): the id column is updated in place to the new id and, for a link, its bit is
       set in the live end's partition; NO event is logged, because the row's own `link` /
       `evidence` event already names the endpoint by name and the restored entity's `entity`
       event makes a rebuild re-attach it (a second `evidence` event would double the row on a
       rebuild). Each re-attached row is counted `restore_reattached` by kind.
     - Only this manifest's `id_map` is used: a dead id that another manifest's restore
       re-created is not this restore's to map, and step (2) above then finds it dead (its new
       id differs) and re-inserts the row dangling, counted, for the `dangling-evidence` class.
   - `removal_restore` reverts repairs (re-point back, un-collapse, rename back / un-merge) and
     re-inserts removals, from the manifest alone. It does not depend on `facts.log` replay (the
     global log is not a faithful source, 22 #m-4), and it emits the inverse events so a later
     rebuild agrees.
   - Restored entities get new ids; restore is checked by NAME. **Vectors (d9z):** after the
     entities are re-inserted, restore builds `id_map = {old_id: new_id}` from the manifest's
     `old_id` and the re-inserted entity's id (looked up by `(partition, kind, name)`), and calls
     17.1's verb with the caller-facing part of its exact signature (`vectors_restore(
     orphan_file: str, ids: list[int] | None = None, id_map: dict[int, int] | None = None,
     dry_run: bool = False, *, invoked_by: str) -> dict`; 17.1's adapters set `invoked_by` for
     the CLI and MCP surfaces, R1). Restore runs inside the daemon and calls the verb in-process,
     so it passes the value itself: `vectors_restore("removal/<apply_id>.vectors.jsonl",
     id_map=id_map, invoked_by="removal_restore")` (`removal_restore` is the in-process caller
     value 17.1 R1 defines; r6), with NO 23.1
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
     ([[task-22.6-removal-entry-points#r6]]), or (b) a CLI/MCP command record naming the entity,
     or (c) a `cli.log` grep record for its `query/*` concept (d9ak(b), the rule below).
     Everything else is USER-ASSERTED.
     - Only `protect_source = 'learner'` (written only by `daemon._learn_grep_hits`) or rule (c)
       makes a learned-only entity purgeable as a learner auto-protection.
     - Command records: `cli.log`'s `argv` for `rmx protect`, `add-entity` and `add-concept`
       (without `--no-protect`) name a USER protection. MCP calls write no command record today
       (no call log in `mcp.py` or `verbs.py`, read at `7f2014a`); MCP protections are
       attributed through the event's `source` (`user`) once 22.6 R6 lands.
     - **A `cli.log` grep record is learner evidence (d9ak(b), r6 s-4).** {#r5-grep-record}
       - *The record:* a row of the store's OWN `cli.log` (`<store_root>/cli.log`, written by
         `telemetry.log_cli_invocation`) whose `argv[0]` is `grep`. Its pattern `P` is the pattern
         operand of that `argv` as `rmx grep` reads it (the `pattern` it hands to
         `cli._broker_learn_from_grep`; once 16.1 lands, 16.1 R1's argv parser, the same reader).
         The record matches the concept named EXACTLY `query/P` in that store; no case or
         `canonical_name` folding.
       - *Its scope:* it attributes the protection of `query/P` itself and of every learned-only
         entity (R5's definition below) that carries a `mentions` link from `query/P`, as
         `learner`. It attributes nothing else: not an entity with any non-learned row, not a
         concept the record does not name, not another store's rows.
       - *Precedence:* an explicit `source` on the entity's latest `protect` event wins over it,
         and so does a command record naming the entity (`rmx protect` etc., `user`); the grep
         record decides only a protection that neither of those attributes. Record order
         against the `protect` event is not compared: a compacted log re-emits every `protect`
         event directly after its `entity`, with `ts` = the entity's `updated_at`.
       - *The count it gives (d9ak, read-only, 2026-10-14):* 217 of this repo's 426 learned-only
         protected entities and 90 of the global store's 4,793 are attributed `learner` by this
         rule (none of the 1,655 pytest-tmp ones).
         So class plans may purge those 217 + 90 entities whole; the other 209 + 4,703 stay
         `kept: asserted-protection` (d9ak(a)).
       - The rule reads the copied `cli.log` in a census and the live one read-only in the audit
         op; an unreadable `cli.log` is counted and printed, and every protection then falls to
         user-asserted (the safe default), never to learner.
     - **Log adjacency is NEVER evidence.** `Store.dump_catalog_to_log` writes every `protect`
       directly after its own `entity`, so in a compacted log
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
     `daemon_crud_probe`, 2026-06-11) name entities that are no longer protected. So rules (a)
     and (b) attribute NO existing protection to the learner (the table's rule-B column). Rule (c)
     does: d9ak(b) made the `cli.log` grep record a rule ([[#r5-grep-record]]; round 5 printed its
     count "for information only"), so 217 of this repo's and 90 of the global store's existing
     learned-only entities are learner-attributed and a class plan may purge those whole when they
     are its members; the other 209 + 4,703 are user-asserted, keep their entity and lose only
     their learned rows. New protections become purgeable once 22.6 R6 records `source=learner`.
     22.3's live global apply inherits this (d9aw): it prints how many of its members rule (c)
     attributes before the apply, and the user sees that count first
     ([[task-22.3-bug-086-global-repair#r3]]). (Round 6 kept the round-5 sentence "no existing
     entity is purged as a class member" above this paragraph; it contradicted rule (c) and is
     deleted, r7 s-3.)
6. **R6 Bounded, bound per batch, re-checked (22 #s-1, #s-2; #t2-fixes).** {#r6}
   - The apply is a bounded step loop over the in-memory plan through plan-23's `bounded_steps`,
     NOT the coalescing, overflow-dropping queue (`drain(queue)`): no repair or removal can be
     dropped.
   - Each batch takes the store lock once and binds its partition INSIDE that hold through 23.1's
     `bind(partition_name)` seam; the 23.2 recorder counts its writes.
   - **Store-scope members (r6 s-2).** `dangling-link` and `dangling-evidence` members have no
     partition of their own (`entity_links` and `linkage_evidence` carry no partition column), so
     22.1a records each member's LIVE end partition, or `none` for a both-dead row. The apply
     groups them into batches per recorded partition and binds that partition; the `none` batch
     binds the store's default partition only to hold the lock and deletes its rows by their full
     key `(entity_id, linkage_id, concept_id)`, which needs no binding. The fragment bits of every
     batch are cleared in EVERY partition (R9), and the events of R9 carry the partition of the
     `facts.log` event they answer, never the batch's binding.
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
   and `empty-learned` / `stale-subject` after the gate passes; `dangling-link` and
   `dangling-evidence` (22.1a; d9an, d9ar) as [[#r9-dangling]] states; the selector members of a
   confirmed 22.6 plan. **`ambiguous` (any sub-class), `unverifiable` and
   `orphan-root:unverifiable` (22.1a, r3 s-3) are never removed.** `orphan-root:home-readable`
   (22.1a; rows that read correctly today under no project store) is not a removal class: nothing
   is applied to it until the user rules on 22.5 R1's dry-run counts (d9b). An entity whose
   protection is user-asserted (R5, d9ab) is never removed by a class plan; only its learned rows
   are. {#r9}
   - **Dangling rows, replay-safe (d9an as amended by d9aq and d9ar; r6 b-1, s-2, s-3).**
     {#r9-dangling}
     - *Why events are needed at all.* `Store.rebuild_index_from_log` wipes the catalog and
       re-creates every entity whose `entity` event has no later `tombstone`, then replays each
       `link` whose two endpoint names both resolve. A dead endpoint that bug-111's raw DELETE
       removed has no tombstone, so a rebuild brings it back with its links: on cliquedb's
       `facts.log` (copy of 2026-10-14 23:43, read-only) 56 `(cliquedb, doc, name)` keys have
       `entity` events, no tombstone and no catalog row, and 1,129 `link` events name them as `e`.
       A compaction first (`Store.dump_catalog_to_log` emits only live entities) would drop them
       instead, so without events the outcome depends on which tick runs first.
     - *Naming a dead endpoint from the log.* 22.1a records, per dead id, the `names_from_log` its
       naming rule finds ([[task-22.1a-provenance-free-classes#r1-dangling]]): a
       `(partition, kind, name)` key with a surviving (untombstoned) `entity` event, no catalog
       row, and a last-wins `link` (or, for a dead concept of an evidence row, `evidence`) event
       to EVERY row of that dead id whose other end is alive, by linkage and live-end name, in
       the key's own partition (r7 m-3); it is NAMED when exactly one key qualifies and no other
       dead id claims it. A dead id whose best-covering logged key HAS a catalog row (the name
       was re-created under a new id) is `unnamed:reborn` (r7 m-1); every other dead id is
       `unnamed:none` or `unnamed:ambiguous`. On the cliquedb copy: 64 dead entity-side ids, 56
       named (each by one of the 56 keys above), 0 ambiguous, 8 reborn (ids 2791202-2791209:
       `cliquedb/architecture-index` and its seven section concepts, live again as ids
       3219330-3219337; seven are fully covered by their name's `link` events and the reborn
       entity holds every one of their rows, the eighth on 3,458 of its 3,459 rows), 0 none. On
       the evidence side: 4,778 dead concept ids, 0 named, 896 reborn (843 fully covered, 53 on
       part of their rows), 3,882 none ([[task-22.1a-provenance-free-classes#r1-dangling]]).
       Round 6 said the 8 were ids "whose rows no single logged name covers"; that was false
       (r7 m-1).
     - *`remove_dangling_links(members)` and `remove_dangling_evidence(members)`* (new `Store`
       methods, [[#files-to-modify]]), under a batch hold (R6), in this order per member:
       1. **Re-check** inside the hold: the row still exists and its dead side is still dead under
          the shared predicate (22.1a AC-8c); a NAMED endpoint whose key now has a live catalog
          row (re-ingested since the audit) is handled as `unnamed:reborn` (step 4's reborn
          rule) and counted `name_reborn`.
       2. **Intent record** (R4's `link_row` / `evidence_row`), written and fsynced first.
       3. **Delete** exactly that row by its key; for a link row, clear its bit (and, for a dead
          id, that id's concept-prefix row) in EVERY partition's fragments through the existing
          `Store._clear_purged_bits(bits_by_ln, dead_ids)`, passed only DEAD ids (bug-105: a dead
          id's bit may sit in any partition's row).
       4. **Log by name, never by id.** Each event carries the `partition` field of the
          `facts.log` event it answers, exactly as that event carries it (present with that value,
          or absent), never the batch's binding (R6), since rebuild keys events by
          `(partition or its bound partition, …)` (`store.py:7931`, `:7953`) and `_log_event` adds
          no partition itself (r7 m-3):
          - **NAMED dead endpoint:** once per apply, one `tombstone{kind, name}` with the partition
            field of its surviving `entity` event.
          - **Link row whose both ends are then named** (the live end by its catalog name, the
            dead end by its log name): one `unlink{linkage, c, e_kind, e}` per DISTINCT last-wins
            `link` key that answers the row, each with that `link` event's partition field (r7
            m-3: a compacted `entity` event may carry `partition` while later live `link` events
            do not, and an `unlink` keyed on the entity's partition would not override the
            live-shape key; if the name were later re-created in the bound partition the old link
            would revive). A later re-creation of the name then does not revive the old link (the
            latest of `link`/`unlink` wins).
          - **Evidence row of a NAMED dead concept:** the concept's tombstone AND one
            `evidence_remove{linkage, c, e_kind, e, file, line, detail, keep: 0, ingest_ok}` by
            name (d9av; r7 b-1), through `remove_evidence(identity, keep=0, ingest_ok=True)`.
            Under R3's timestamp order the remove deletes on replay only the copies appended at or
            before it: if the concept's name is re-created later and the old `evidence` events
            re-resolve, the remove still drops them (the live store does not hold them), while an
            identical row a later re-ingest appends after the remove survives (the live store
            holds it). Round 6's "tombstone only" branch, and its caveat that a re-created name
            re-attaches the old rows, are WITHDRAWN: that rested on the remove pass running after
            every append (AC-3e).
          - **`unnamed:reborn` (r7 m-1):** the best-covering key has a live catalog row, so NO
            tombstone (it would drop the reborn entity on a rebuild: its `ts` would be later than
            the reborn entity's `entity` event). For each dead row the reborn entity does NOT
            hold and whose last-wins event on the reborn key is a `link` (link side), or that a
            logged `evidence` event under the reborn name covers (evidence side), one `unlink` /
            `evidence_remove` by name as above; a dead row the reborn entity DOES hold logs
            nothing (the rebuild converges on the reborn entity, which holds the same row, and an
            `unlink` or `evidence_remove` on its key would delete that live row on a rebuild).
            Each reborn member is counted `reborn` in the apply report, with `reborn_unlinked` /
            `reborn_evidence_removed` for the rows that got an event. On cliquedb that is 1 row
            today at most (id 2791206's 3,459th row; 0 whose last word is `link`, r7 m-1).
       5. **A NAMELESS dead endpoint (`unnamed:none` / `unnamed:ambiguous`) logs nothing, by
          design.** No name covers its rows in its own partition: the log either names no key for
          it, or names several that no single one wins. So a rebuild cannot re-create the
          endpoint ONTO those rows (link and evidence replay need both names in the rebuilt
          catalog, and pass 3 skips a row whose `cid` or `eid` does not resolve), and the deleted
          row cannot come back from the log. There is also nothing to key an event on, and an
          id-keyed event would match nothing after a rebuild re-assigns ids ([[#r3]]). Round 6's
          reason, "no `entity` event that a rebuild would act on names it", described the 8
          cliquedb ids that are in fact reborn (r7 m-1). Each nameless member is counted
          `nameless` in the apply report.
     - A log name that would be resurrected but that no dead id claims (an `entity` event with no
       tombstone and no catalog row, tied to no dangling row) is NOT tombstoned by this class: it
       is not one of its rows. 22.1a AC-8b prints that count (`would_resurrect_unclaimed`; 0 on
       cliquedb) so it is visible.
     - Neither method touches a live entity, a live entity's other rows, or `protected`.

## Acceptance criteria {#acceptance}

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

   **3b. Dangling-link replay (r6 b-1, d9aq).** Sandbox store with two partitions, `p1` (the
   default) and `p2`. Its `facts.log` holds, for doc `D` in `p2`, an `entity` event carrying
   `partition: p2` (the compacted-log shape) and two `link` events (`mentions` from concept `X`,
   `part-of` from concept `Y`), and no tombstone; `D`'s `entities` row is then deleted by raw SQL
   (bug-111's shape), leaving its two `entity_links` rows dangling. A third `entity_links` row
   names an id that no `entity` event ever named (nameless). Steps: `removal_audit`, `--apply`,
   then `cp` the store and run `rebuild_index_from_log` on the copy. Expected: the live store and
   the copy each hold 0 `entity_links` rows with a dead endpoint, and `repair_fragments(dry_run=
   True)` on each reports `links_dead_entity == 0` and `links_dead_concept == 0`; the copy holds
   NO entity named `D` in any partition and no link to `X` or `Y` from one; `facts.log` gained
   exactly one `tombstone{kind: doc, name: D, partition: p2}` and two name-keyed `unlink` events,
   and no event at all for the nameless row; the apply report reads `named=1 nameless=1`.
   Mutations, each FAILS it: "log `link_remove` by id" (no tombstone: the copy resurrects `D`
   with both links); "no tombstone for the named dead endpoint" (unlinks only: the copy
   resurrects `D`); "tombstone without the `entity` event's partition field" (it keys on `p1`:
   the copy resurrects `D` in `p2`).
   **Partition of the `unlink` (r7 m-3).** `D`'s `mentions` `link` event from `X` carries NO
   `partition` field (the live shape) while its `entity` event carries `partition: p2`; after the
   apply the test re-creates a doc named `D` in `p1` (the bound partition) and rebuilds a second
   copy: that copy holds no `mentions` link from `X` to the new `D`. Mutation "key the `unlink`
   on the `entity` event's partition" FAILS it (the `unlink` keys on `p2`, the live-shape `link`
   key on `p1` still wins, and the old link revives onto the new `D`).
   **Reborn (r7 m-1).** A dead id `R0` whose two rows' logged name `R` was re-created under a new
   id: the live `R` holds one of `R0`'s rows; the other row's last-wins event under `R` is a `link`.
   The audit labels `R0` `unnamed:reborn`; the apply logs NO tombstone for `R`, ONE `unlink` (for
   the row `R` lacks) and nothing for the row `R` holds; the rebuilt copy equals the live store
   on `R`'s links (exactly the one it holds). Mutations, each FAILS it: "tombstone a reborn key"
   (the copy drops `R`); "no event for a reborn row" (the copy revives the lacking row onto `R`);
   "`unlink` every reborn row" (the copy loses the link `R` holds).

   **3c. Dangling-evidence (r6 s-3, d9ar).** Docs `A` and `B`, where `B`'s `rel:` edge to `A` is
   an evidence row of `B` with `A` as its concept. `A` is purged with `Store.purge_entity` (the
   test first asserts that this leaves `B`'s evidence row naming `A`'s dead id: the defect 22.6
   R9 now states). `removal_audit` lists it `dangling-evidence`; `--apply` removes it; afterwards 0
   `linkage_evidence` rows have a live entity and a dead concept, `B`'s other rows are byte-equal,
   and a rebuild on a copy resurrects neither `A` nor the row; `restore` puts the row back with
   `A`'s old id (R4's `evidence_row`). A second fixture purges a concept through this engine (R2's
   rule): 0 dangling-evidence rows result. Mutations: "drop the `dangling-evidence` sub-class"
   FAILS it (the row stays); "purge without first removing the concept-side evidence rows"
   (R2) FAILS the second fixture; "the learned guard applies to `ingest_ok` callers too" (r7
   m-4) FAILS both (the `rel:` row is not matched and stays). An AST test asserts that
   `remove_evidence(..., ingest_ok=True)` is called only from R2's concept-side rule and
   `remove_dangling_evidence`; mutation "a third caller passes `ingest_ok=True`" FAILS it.

   **3d. A removal followed by a re-creation survives the rebuild (d9av; r7 b-1).** Two
   fixtures, each ending with `rebuild_index_from_log` on a copy that must EQUAL the live store
   on `linkage_evidence` (multiset of rows by name), on the sidecar (every column but 16.6's
   mark columns) and with `unresolved_provenance == 0`:
   - *Learned (the branch switch).* File `F` has one learned row `(mentions, query/P, F, 12)`
     with its sidecar row (`F` learned-only, `protect_source='learner'`). `F` is deleted and a
     `missing-file` apply removes the row (`evidence_remove`) and purges `F` (`tombstone`). `F`
     is re-created with the same line and `P` is learned again: the learner writes the
     identical row (`entity F`, `evidence`, `learned_provenance` events, all later than the
     remove). Live: 1 row, 1 sidecar row. The copy: the same.
   - *Ingest, through R2.* The AC-3c second fixture's engine purge of concept `A` (kind
     `concept`: rebuild resolves an evidence row's concept only as kind `concept`,
     `store.py:8090`) removes `B`'s `rel:` evidence to `A`. Then `A` is re-created and `B` is
     edited and re-synced, writing the identical evidence row. Live: 1 row. The copy: the same.
   Mutation "`evidence_remove` applied after all appends" (round 6's pass order) FAILS both (the
   copy deletes the re-created row; the learned fixture also counts `unresolved_provenance` 1).

   **3e. The named dead-concept branch can fail (r7 b-1).** `B`'s evidence row names concept
   `A` (kind `concept`, with an `entity` event and an `evidence` event covering the row, so `A`
   is NAMED); `A`'s `entities` and `concepts` rows are then deleted by raw SQL (bug-111's shape:
   NO tombstone). `removal_audit` lists the row `dangling-evidence` with `A` named; `--apply`
   logs `tombstone{concept, A}` and one `evidence_remove` for the row. Three rebuilds on copies,
   each compared with the live store at that moment:
   1. right after the apply: the copy holds no entity named `A` and not the row;
   2. after `A` is re-created live (`B` untouched): the copy holds `A` and NOT `B`'s old row
      (the live store does not hold it);
   3. after `B` is re-ingested, writing the identical row: the copy holds the row once.
   Mutations, each FAILS it: "no tombstone for a named dead concept" (copy 1 resurrects `A`);
   "tombstone only, no `evidence_remove`" (round 6's branch: copy 2 re-attaches the old row to
   the re-created `A`); "`evidence_remove` applied after all appends" (copy 3 loses the row).
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
   The call carries `invoked_by="removal_restore"`; mutation "omit `invoked_by`" FAILS it (17.1
   R1's signature has no default).

   **4c. A dangling row restores onto the NAMED live end (r6 s-1).** The fixture removes a
   `dangling-link:entity` row whose live end is concept `X`, and a both-dead row. Then, on a copy,
   `rebuild_index_from_log`, followed by `restore` of the manifest on that copy. The fixture
   purges two entities created before `X`, so `X`'s id after the rebuild differs from its
   recorded `old_id` (asserted as a precondition). Expected: the restored row's `concept_id` is
   the rebuilt `X`'s id and its `entity_id` is the recorded dead id; its weight (NULL in the
   fixture) is equal; no fragment bit is re-added for either row; the both-dead row comes back
   with both recorded dead ids. A second run purges `X` before the restore: its row is counted
   `restore_live_end_missing` and not re-inserted. Mutation "restore by recorded live id" FAILS
   both runs (the row attaches to whatever entity now holds `X`'s old id, or to none).
   **Still dangling, and the reused dead id (r7 s-1).** After the restore, every restored row is
   still dangling: `LinkLiveness.dead_side` on it returns its recorded dead side. For that, the
   main rows' recorded dead ids are larger than every id in the rebuilt copy (an asserted
   precondition: the fixture creates and raw-deletes those entities last, after filler entities
   it purges with tombstones). A third row's recorded dead id EQUALS a live id in the rebuilt
   copy (asserted precondition: a small id, since the rebuild hands out dense ids from the
   sequence's start, `duckdb_catalog.py:50`): it is NOT inserted, it is counted
   `restore_dead_id_reused`, and the live entity holding that id has no new link or evidence row.
   Mutation "re-insert without the dead-id check" FAILS it (the row becomes a live link between
   unrelated entities, and the "still dangling" assertion fails on it).

   **4d. Restore re-attaches rows that name a restored entity by its old id (r7 s-2).** Concept
   `A` (kind `concept`) and doc `B`, `B` carrying a `rel:` evidence row whose concept is `A`. `A`
   is purged through this engine (R2's concept-side rule records `B`'s row as an `evidence_row`
   with `A`'s `old_id` and removes it). `restore` re-creates `A` under a NEW id and re-inserts
   `B`'s row naming `A`'s NEW id: compared by name, `B`'s evidence to `A` is back, 0
   `dangling-evidence` rows exist, `facts.log` gained one `evidence` event for it, and a rebuild
   on a copy holds the row once. Mutation "keep the recorded old id when the same manifest
   restores that entity" FAILS it (`B`'s row names a dead id after the restore: 1
   `dangling-evidence` row). The purge-outside-the-engine half (a SURVIVING row updated in place,
   no event) needs 22.6's entry points and is [[task-22.6-removal-entry-points]] AC-9c, built on
   this task's restore rule.
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

   **6c. A `cli.log` grep record attributes the learner (r6 s-4, d9ak(b)).** Four learned-only
   fixture entities, each with one `missing-file` learned row and no `source` on its protection:
   G carries a `mentions` link from `query/foo` and the store's `cli.log` holds a record with
   `argv: ["grep", "-n", "foo", "src"]`; H carries a link from `query/bar` and `cli.log` has no
   `grep` record with pattern `bar` (only `["grep", "-n", "Bar", "src"]`); K is linked from
   `query/foo` but also carries an ingest link (not learned-only); U is linked from `query/foo`
   and `cli.log` holds `["protect", "U"]`. The apply removes the four learned rows, purges G,
   keeps H (no exact-name record), K (not learned-only) and U (a user command record wins), and
   lists H and U `kept: asserted-protection`. Mutations, each FAILS it: "ignore `cli.log` grep
   records" (G kept); "match the pattern case-insensitively" (H purged); "a grep record beats a
   user command record" (U purged).
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
14. **Dangling rows removed, every partition's bit cleared (d9an; r6 s-2, m-7).** On a
    two-partition fixture built like 22.1a AC-8a's, holding a `:entity` row, a `:concept` row, a
    live-doc-concept row that is not a member, a both-dead row and a `dangling-evidence` row,
    `--apply` removes exactly the four members, and a following `repair_fragments(dry_run=True)` reports `links_dead_entity ==
    0` and `links_dead_concept == 0`; the bit of the `:entity` row, planted by the fixture in the
    NON-bound partition's fragment row, is gone; the both-dead row went through the `none` batch;
    `restore` puts all four rows back with their weights (R4's `link_row` / `evidence_row`).
    Mutations, each FAILS it: "remove without writing the manifest" (restore); "also remove the
    live-doc row" (count); "clear the bit in the bound partition only" (the planted bit stays);
    "skip the `none` batch" (the both-dead row stays).

## Files to modify {#files-to-modify}

r6 m-7: this task's own file list (symbols read at `3d3c798`).

| File | Change |
|------|--------|
| `src/refmatrix/store.py` | the R2 primitives (`remove_evidence(..., ingest_ok=)`, `repoint_evidence`, `rename_entity`) and R2's concept-side evidence rule before a purge; `remove_dangling_links` and `remove_dangling_evidence` (R9, built on `_clear_purged_bits`; reborn and per-`link`-key partition rules, r7); the R3 ops in `_apply_event_body` and in `rebuild_index_from_log`'s one timestamp-ordered row pass (16.6 R1d builds the pass; d9av); R4's restore of `link_row` / `evidence_row` with the dead-id re-check and the `id_map` re-attach (r7 s-1, s-2) |
| `src/refmatrix/removal_apply.py` (new) | the R6 batch loop over `bounded_steps` (incl. the per-partition and `none` batches), R4's intent log and restore, R7's gate, R5's attribution incl. [[#r5-grep-record]] |
| `src/refmatrix/verbs.py` | `removal_apply`, `removal_restore` (R8); `mcp.py` generates their tools from `verbs.VERBS` |
| `src/refmatrix/daemon.py` | the apply and restore ops under the writer lock (R6, R8) |
| `src/refmatrix/cli.py` | `rmx removal apply`, `rmx removal restore` (R8) |
| `tests/test_removal_apply.py` (new) | AC-1..AC-14 |

The protection-source column and the compactor's `source` are 22.6 R6's files; they land in this
task's slice (r6 m-7, [[plan-22-audited-removal-and-repair#dependencies]]).

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

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan16-22-spec-rereview-r6-0e77da3]] where it touches 22.2, and d9aq/d9ar
([[plan-review-2026-10-14#t12-approvals]]); cites d9ak/d9al/d9am ([[plan-review-2026-10-14#t11-approvals]]),
which round 5 reflected without citing. Later rows win over round 5 and the d9an revision.

| finding / decision | answered in |
|---|---|
| r6 b-1 / d9aq (the id-keyed `link_remove` has no reader and a rebuild resurrects the dead endpoints) | [[#r9-dangling]]: naming from `facts.log`, `tombstone` by name with the entity event's partition, `unlink` by name, nameless logs nothing (why stated); [[#r3]] "No op keyed by id" (`link_remove` WITHDRAWN); AC-3b + three mutations |
| r6 s-1 (no manifest form for a dangling row; restore by id after a rebuild) | [[#r4]] `link_row` / `evidence_row`, restore by name, no bit, no event; AC-4c + mutation |
| r6 s-2 (no partition for the class) | [[#r6]] "Store-scope members" (live-end partition or `none`); [[#r9-dangling]] bits cleared in every partition; AC-14 + two mutations |
| r6 s-3 / d9ar (`dangling-evidence`; purges create it) | [[#r9-dangling]] `remove_dangling_evidence`; [[#r2]] purge rule removes concept-side evidence first; [[#r4]] `evidence_row`; AC-3c + two mutations |
| r6 s-4 / d9ak(b) (`cli.log` grep record is learner evidence) | [[#r5-grep-record]] (record, scope, precedence, 217 / 90); [[#r5]] count text; AC-6c + three mutations |
| d9ak(a) (user-asserted entities kept, learned rows removed) | [[#r5]] (reflected since round 5; cited here) |
| d9al (a move is not a removal) | [[task-22.5-cross-store-move#r2]] step 4 (reflected since round 5; cited in [[task-22.5-cross-store-move#rev-round-6]]) |
| d9am (`source` vocabulary `learner`/`user`/`system`/`removal`; `upsert` dropped) | [[#r5]] reads it; owned by [[task-22.6-removal-entry-points#r6]] |
| r6 m-6 (stale line numbers) | [[#r2]], [[#r3]], [[#r5]] cite by symbol |
| r6 m-7 (unnumbered AC; no file list; 22.6 R6's slice) | AC-14 (was the unnumbered bullet); [[#files-to-modify]]; header names the slice |
| 17.1 R1's `invoked_by` (parallel revision) | [[#r4]] `invoked_by="removal_restore"`; AC-4b clause + mutation |

rel: amends -> [[bsd-plan16-22-spec-rereview-r6-0e77da3]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]
rel: depends-on -> [[task-17.1-vectors-maintain-op#r1-verb]]

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan16-22-spec-rereview-r7-331b414]] where it touches 22.2, and d9av/d9aw/d9ay
([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at `77ac38f`. Later rows win over
round 6.

| finding / decision | answered in |
|---|---|
| r7 b-1 / d9av (the one pass applied `evidence_remove` after EVERY append, so a rebuild deleted a row re-created after the remove) | [[#r3]] "ONE row pass, appends and row ops together, in TIMESTAMP order" (stable `ts` sort, ties by log position; incremental path in byte order; compaction unaffected; how `c` resolves); same rule in [[task-16.6-learned-row-validation#r1d]]; [[#r9-dangling]] step 4: a named dead concept's evidence row now logs `evidence_remove` by name too, round 6's tombstone-only branch and its caveat withdrawn; [[#r2]] concept-side rule cites the order; AC-3d (two fixtures) and AC-3e (named, untombstoned dead concept: the tombstone branch can fail), each with the mutation "`evidence_remove` applied after all appends" |
| r7 s-1 (restore re-inserts a recorded dead id that a rebuild may have handed to a live entity) | [[#r4]] "Every recorded dead id is re-checked" (`id_map` first, then `LinkLiveness.dead_side`, `restore_dead_id_reused`); AC-4c "still dangling" + reused-id fixture + mutation |
| r7 s-2 (an engine purge's restore brings the concept back under a new id and its inbound rows under the old one) | [[#r4]] "Restore maps every recorded old id through its own `id_map`" (re-inserted rows re-attached with an event; surviving rows updated in place, no event); [[#r2]]; AC-4d + mutation; the outside-engine half is [[task-22.6-removal-entry-points]] AC-9c |
| r7 s-3 / d9aw (R5 still said no existing entity is purged; 22.3 said so too) | [[#r5]] the stale sentence deleted and the rule (c) consequence stated (217 / 90 purgeable when class members); 22.3 [[task-22.3-bug-086-global-repair#r3]], AC-5 |
| r7 m-1 (the 8 "nameless" ids are reborn) | [[#r9-dangling]] naming paragraph (`unnamed:reborn`: 8 link-side, 896 evidence-side), step 1 (`name_reborn` follows the reborn rule), step 4 reborn rule (no tombstone; an event only for a dead row the reborn entity lacks), step 5's reason corrected; AC-3b reborn clause + three mutations; counts measured in [[task-22.1a-provenance-free-classes#r1-dangling]] |
| r7 m-3 (`unlink`'s partition; "the store's default") | [[#r9-dangling]] step 4: every event takes the partition field of the event it answers; one `unlink` per distinct last-wins `link` key; naming per partition; AC-3b partition clause + mutation |
| r7 m-4 (R2's concept-side rule called a primitive that refuses ingest rows) | [[#r2]] `remove_evidence(..., ingest_ok=True)`, two named callers, `detail` in the event identity; [[#r3]] event fields; AC-3c mutation + AST caller check |
| r7 m-2 (the shared predicate's maps; AST scope; the bit half) | owned by [[task-22.1a-provenance-free-classes#r1-dangling]] (AC-8c); [[#r4]]'s dead-id re-check calls the same `LinkLiveness.dead_side` |
| d9ay (16.6 R1c retired) | [[#r2]] cites 16.6 R1's collapse rule, not R1c |
| r7 m-5 (23.4's census trails plan-22) | not this task's: plan-23's owner updates [[task-23.4-option-a-measurement]] |

The rebuild's resolution of an evidence row's concept only as kind `concept` (r7 `#code-facts`)
is pre-existing and unchanged here; [[#r3]] states how the row ops inherit it.

rel: amends -> [[bsd-plan16-22-spec-rereview-r7-331b414]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-16.6-learned-row-validation#r1d]]
