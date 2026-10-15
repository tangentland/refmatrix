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
  updated: 2026-10-15
---

# Task 22.2: the repair-then-remove engine {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (revision round 14, 2026-10-15; [[#rev-round-14]]; round 13 in [[#rev-round-13]]; round 12 in [[#rev-round-12]]; round 11 in [[#rev-round-11]]; round 10 in [[#rev-round-10]]; round 9 in [[#rev-round-9]]; round 8 in [[#rev-round-8]]; round 7 in [[#rev-round-7]], round 6 in
> [[#rev-round-6]], round 5
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
       event carries `ingest_ok: true`. The event names the concept end as `(c_kind, c)`, the
       kind(s) given by R3's one helper `Store._row_op_c_kinds` (r8 b-1; [[#r3]]).
   - `repoint_evidence(identity, new_line)` — updates `line` (and `span_end` by the same offset),
     and moves the identity's sidecar rows to the new `line`.
   - `rename_entity(kind, old, new)` — for an in-store `orphan-root` repair. **Merge on collision:**
     when `(partition, kind, new)` exists (`UNIQUE(partition, kind, name)`), the old entity's
     evidence rows and links re-attach to the existing entity. Each re-attached link logs
     `unlink` of its old key and `link` of its new key through `edge_records.edge_event` (with
     `c_kind`), so the LWW pass moves it on a rebuild; `entity_rename` replays evidence only
     ([[#r3]]; r11 s-2, d9cc). `protected` becomes the max of the
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
     which logs `evidence_remove` by name (with `c_kind`, `detail` and `ingest_ok`; the purged
     concept's own kind, a `doc` for every `rel:` target). With R3's timestamp
     order (d9av) that event deletes on replay only the copies appended at or before it, so an
     identical row a later re-ingest of the other entity writes survives a rebuild (AC-3d). A
     restore of the purge re-attaches these rows to the restored concept (R4, r7 s-2). This holds
     for every purge the engine runs: class members, 22.5's moves and 22.6's selector members.
3. **R3 Row-level `facts.log` events, replayed (22 #b-3).** The replay knows only entity-level
   `tombstone` and append-only `evidence` today (the LWW pass in `Store.rebuild_index_from_log`,
   the ONE replay path: the uncalled incremental path is deleted by 16.6 R1f, d9bu). Add three
   ops, keyed by NAME (never by id):
   `evidence_remove{linkage, c_kind, c, e_kind, e, file, line, detail, keep, ingest_ok}` (`detail`
   and `ingest_ok` added in round 7, r7 m-4; `c_kind` in round 8, r8 b-1),
   `evidence_repoint{linkage, c_kind, c, e_kind, e, file, line, new_line}`, both built by
   16.6's `edge_records.row_event` and added to `edge_records.ROW_OPS` by this task
   ([[task-16.6-learned-row-validation#r1d-one-format]], d9bl), and
   `entity_rename{kind, from, to, merged}`, which names no edge and is not a row event. The sidecar's own events (16.6 R1d:
   `learned_provenance`, `learned_provenance_move`) are logged by the same call, AFTER the
   evidence op's own event, so a rebuild reproduces the sidecar too (b-2). {#r3}
   - **ONE row pass, appends and row ops together, in TIMESTAMP order (d9av; r7 b-1; replaces
     round 3's "after the `evidence` appends").** The rebuild applies the `evidence` appends
     and every row-level op in ONE pass: `evidence` (the append), `learned_provenance`,
     `learned_provenance_move` (16.6), `evidence_remove`, `evidence_repoint`, `entity_rename`
     (here) and `evidence_orphan_drop` ([[task-22.6-removal-entry-points#r5]]), ordered by `ts`
     with ties broken by log position. So an `evidence_remove` (or a re-point, a rename, an
     orphan drop) at `T` acts only on the copies appended at or before `T`; a copy appended
     after `T` (a re-learned row, a re-ingested `rel:` edge) is applied after it and survives,
     exactly as the live store keeps it. The same rule, list and order is stated in
     [[task-16.6-learned-row-validation#r1d]], which builds the pass (this task adds its ops).
     - *Where the order comes from (re-read at `23ad703`, 0.78.3; r8 m-5).*
       `Store.rebuild_index_from_log` sorts every event with `events.sort(key=lambda e:
       e.get("ts", 0))` (`store.py:7941`), a stable sort, so equal `ts` keep their log order; its
       pass 2 collects `evidence` events into `evidence_events`, Pass 2b (bug-117) resolves each
       legacy one's `c_kind` (counting `evidence_unresolved`), and pass 3 applies them per
       partition after entities, protections and links (counting `evidence_skipped_dead`). The
       row pass replaces only pass 3's loop and takes the appends AFTER Pass 2b
       ([[task-16.6-learned-row-validation#r1d]], r8 m-1): per partition, it walks the evidence
       appends and row ops of that partition in the sorted order. There is no second replay path
       to keep in step: `Store.apply_log_delta` → `_apply_one_event` → `_apply_event_body` had no
       caller (its only user, writer rotation, was dropped by d9ao) and 16.6 R1f deletes it
       (d9bu, r9 s-2); this task adds no branch to it.
     - *Within a call.* A primitive's sidecar event follows its evidence event in the same call
       (same `ts` from `_log_events`, or a later one from `_log_event`), so the tie-break by log
       position keeps it after; the learned provenance still follows its evidence row.
     - *Compaction is unaffected.* `Store.dump_catalog_to_log` gives each `evidence` event the
       synthetic `ts` `GREATEST(c.updated_at, e.updated_at)` (re-read at `23ad703`; since 0.78.3 each
       dumped edge event also carries `c_kind`) and a compacted
       log holds no `evidence_remove`, so the pass has nothing to order there; any row op logged
       after the compaction has a later `ts` than every dumped append. 16.6 R1d gives each dumped
       `learned_provenance` event its evidence row's `ts`, emitted after it.
     - Never a pass per op family: a re-point replayed before its row's `learned_provenance` event
       would leave that event no evidence row at the recorded line (`unresolved_provenance`), and
       the provenance would be lost (r3 m-1). Never a remove pass after all appends: it deletes a
       row the live store re-created after the remove (r7 b-1; AC-3d).
     - *How the ends resolve (r8 b-1, d9bl; replaces round 7's "as kind `concept`", which
       bug-117 made false).* Every row op carries the concept end as `(c_kind, c)` and the entity
       end as `(e_kind, e)`, spelled with `edge_records.edge_fields(linkage, c_kind, c, e_kind, e,
       **extra)` through 16.6's one builder `edge_records.row_event`; `edge_event` is not used,
       because it accepts only `link` / `unlink` / `evidence`. The op resolves its ends exactly
       as the `evidence` replay of the same row does: by `(c_kind, c)`, through
       `name_to_id[(c_kind, c)]`. A legacy append (no
       `c_kind`) is resolved by the ONE rule, `edge_records.resolve_legacy_kind`, through 16.6's
       `edge_records.resolve_c_kind` (Pass 2b), before the row pass matches identities by
       `edge_records.row_key`. A row op is never written without `c_kind` (`row_event` raises).
       Doc, memory and code concept ends replay since 0.78.3 (bug-117), so a row op on a `rel:`
       evidence row (a `doc` concept, the dominant case: all 14,745 cliquedb dangling-evidence
       rows) resolves and acts on a rebuild; AC-3c, AC-3d and AC-3f prove it.
     - *Which kind a LIVE primitive's op names (r8 b-1; one helper).* A row op must name the key
       a rebuild holds the copies under. For an append written since 0.78.3 that is the
       catalog row's own kind. For a LEGACY append the rebuild uses the one legacy rule, which
       picks `concept` whenever a `concept` of that name is logged, so a row live on `doc A` is
       rebuilt onto a live `concept A` (a pre-existing bug-117 residue; a compaction ends it,
       since `dump_catalog_to_log` re-emits every live row kinded). The primitives cannot tell
       the two apart without reading the log. They need not (r9 m-1): the legacy rule can
       mis-resolve a name ONLY to `concept` (`resolve_legacy_kind` returns `concept` whenever one
       is logged, live or tombstoned), so the LIVE kinds are the wrong input (a tombstoned
       `concept X`, which [[#r9]] itself logs, is invisible to them) and no log read is needed.
       ONE method, `Store._row_op_c_kinds(c_name, catalog_kind, row) -> tuple[tuple[str, int],
       ...]`, returns `(c_kind, keep)` pairs:
       - always `(catalog_kind, keep)` with the caller's `keep`;
       - plus `(edge_records.LEGACY_PREFERRED_KIND, n)` when `catalog_kind` differs from
         `edge_records.LEGACY_PREFERRED_KIND` (today's private `_LEGACY_PREFERRED_KIND`, made
         public by this task) and `n`, the number of copies identical to `row` that the LIVE
         `concept` of that name IN THE ROW'S PARTITION holds (`UNIQUE(partition, kind, name)`
         makes it at most one entity), is 0 or 1 (`n = 0` also when no such live entity exists)
         (r9 m-1, m-2: `keep = n`; r10 m-2: the partition). "Identical" means the same
         `linkage`, the same entity end BY NAME (`e_kind`, `e` of `row`'s live entity), and the
         same `file`, `line`, `detail`. It is defined only for a row whose entity end is a live,
         named entity: every caller is a live primitive acting on such a row. An orphan row
         (its entity end has no name) is never passed: 22.6's `vacuum` keys an orphan drop on
         the orphan's own appends and does not call this helper
         ([[task-22.6-removal-entry-points#r5-own-appends]], d9bz), and the helper RAISES on a
         row whose `entity_id` has no live entity rather than guess.
       - When `n >= 2` no extra pair is returned, and the row is counted `legacy_misresolved` and
         printed (the rebuild holds one copy more than live there; a compaction ends it, since
         `dump_catalog_to_log` re-emits every live row kinded).

       R2's primitives log one op per returned pair. On a rebuild, under the timestamp order,
       the extra op at `T` acts on the `concept` key's copies appended at or before `T`: the
       live concept's own `n` copies plus every legacy copy the rule put there, and `keep = n`
       collapses them to the `n` live holds (r9 m-2). When the appends are kinded, or no
       `concept` of that name was ever logged, the extra op matches nothing and the rebuild
       counts it `no_row` (harmless). The helper does NOT call `resolve_c_kind` or
       `resolve_legacy_kind`: it reads the one constant the rule is built on, so there is still
       one legacy rule (16.6 AC-9d check 2). Rows a primitive RE-POINTS are learned rows, whose
       concept is always `concept` (16.6 R1d), so `evidence_repoint` never gets an extra pair in
       practice; if it did, `n` must be 0 (a repoint has no `keep`), else it counts
       `legacy_misresolved`. [[#r9]]'s events need no such helper: the audit read the log, so
       each event names the key it answers exactly. AC-3f.
     - *One resolver (r8 m-3, closed by d9bu).* Round 8 recorded that a LEGACY append resolved
       over LOGGED kinds on a rebuild and over LIVE kinds incrementally (bug-120). The
       incremental path and its `_replay_concept` are deleted (16.6 R1f), so the rebuild's
       `edge_records.resolve_c_kind` over Pass 2b's logged kinds is the only resolver; bug-120
       closes by removal.
     - *Counters (r8 m-4).* The rebuild counts every skip, never raises: bug-117's
       `links_skipped_dead`, `evidence_skipped_dead`, `links_unresolved`,
       `evidence_unresolved`, and, for the row ops, 16.6's one `row_skips` dict (through
       `Store._row_skip`), rebuild-only (d9bu).
   - On replay, `evidence_repoint` and `entity_rename` move only `linkage_evidence` rows; the
     sidecar keys move only from their own `learned_provenance_move` events. A merged rename's
     links move only through their own `unlink` / `link` events ([[#r2]]) and the old entity
     leaves only through its own `tombstone` (`_bulk_purge_ids`), so `entity_rename` itself
     moves neither (r11 s-2). `evidence_remove`
     also removes the identity's sidecar rows (16.6 R1d).
   - **No op keyed by id, ever (r6 b-1, d9aq).** The dangling removal of [[#r9]] adds NO op. It
     logs only existing, name-keyed events: `tombstone{kind, name}` and `unlink{linkage, c_kind,
     c, e_kind, e}` (built by `edge_records.edge_event("unlink", …)` with a non-empty `c_kind`,
     r8 b-1), which `rebuild_index_from_log` resolves in its LWW pass (pass 2: a tombstone whose
     `ts` is at or after the key's latest `entity` event drops the entity; the latest of `link` /
     `unlink` per `(partition, linkage, c_kind, c, e_kind, e)` wins, Pass 2b merging a legacy
     key into its resolved kind by largest `ts`), and `evidence_remove`, already in the one pass
     above. A kindless `unlink` would go through Pass 2b's legacy rule, which picks `concept`
     whenever a `concept` of that name is logged, and land on another key than the kinded `link`
     it answers; the old link would then revive on re-creation (AC-3b's mutation). Round 5's `link_remove{linkage, entity_id, concept_id}` is WITHDRAWN: a rebuild
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
       set in the live end's partition. A re-attached LINK is never re-attached silently either
       (d9ch, round 14, superseding round 7's no-event rule for links): it logs one `link`
       event ([[#r4-relink]]), because the compaction that drops the evidence row's append
       drops the link's too. The same in-place update moves the identity's 16.6 sidecar rows
       to the new id (R2's "Owner of the sidecar's key columns"), and each of them is re-logged
       ([[#r4-relink]]). A re-attached EVIDENCE row is never re-attached silently (d9cg, superseding
       round 7's no-event rule for evidence; r12 open item): it logs one `restored_from`-tagged
       `evidence` append that RESTATES the row ([[#r4-restate]]), because a compaction between
       the purge and the restore has dropped the row's only append. Each re-attached row is
       counted `restore_reattached` by kind.
     - **A restore REVERSES the purge it undoes, by manifest id (d9cf, superseding d9cc (ii);
       r12 s-1).** {#r4-reversal} Every `tombstone` a manifest-writing purge logs (this engine's
       batches; [[task-22.6-removal-entry-points#r2]] `untrack` / `prune-noise --drop`,
       [[task-22.6-removal-entry-points#r3]], the `--as-memory` conversion of
       [[task-22.6-removal-entry-points#r9]]) carries `manifest: <apply_id>`. The `entity` event
       restore logs for every entity whose old id is a key of THIS restore's `id_map` (re-created,
       or found live by name, as the **Vectors (d9z)** bullet below builds the map) carries `restored_from:
       <apply_id>`. From that event on, a tombstone of the SAME entity key `(partition, kind,
       name)` whose `manifest` it names is REVERSED: the incarnation it purged had its surviving
       copies re-attached in place by this `id_map`; each re-attached evidence copy is restated
       by a tagged append that adds no copy while the purged incarnation's own append still
       holds it ([[#r4-restate]]; [[task-22.6-removal-entry-points#r5-timeline]]). A tombstone with no `manifest` (a purge
       outside plan-22) is never reversed.
       - *Spelling: one builder.* Both fields are spelled ONLY by
         `edge_records.reversal_fields(*, manifest: str | None = None, restored_from: str | None
         = None) -> dict` (it returns only the keys whose value is not None) and read ONLY by
         `edge_records.reversal_of(ev: dict) -> tuple[str | None, str | None]`. The two tombstone
         writers (`Store.purge_entity`, `Store._bulk_purge_ids`) take a keyword `manifest=` and
         splice `reversal_fields(manifest=...)` into their `tombstone` event; restore's
         `upsert_entity` call takes `restored_from=` and splices `reversal_fields(restored_from=
         ...)` into its `entity` event. The literal `"restored_from"` appears in no other `src/`
         module or in `scripts/factslog-restore.py`, and every `tombstone` write in `store.py`
         splices `reversal_fields` (22.6 AC-6f's AST check).
       - *Additive.* Replay, the compactor and 17.4's fold ignore both fields except inside the
         ONE revivable predicate, `edge_records.revivable`
         ([[task-22.6-removal-entry-points#r5-timeline]]). `dump_catalog_to_log` emits neither:
         a compacted log holds no `tombstone` for a reversal to cancel and no copy of a purged
         incarnation, so omitting both is exact (22.6 R6's "new field" rule; its compact-then-
         rebuild AC is 22.6 AC-6e's compacted variant).
     - **The restore restates every evidence row it re-attaches in place (d9cg; round 13).**
       {#r4-restate} For EVERY surviving `linkage_evidence` row the `id_map` re-attaches in
       place (the bullet above), restore logs one `evidence` append, after the restored
       entity's `entity{restored_from}` event, built by `edge_records.edge_event("evidence",
       linkage, c_kind, c, e_kind, e, file=, line=, span_end=, detail=,
       **edge_records.reversal_fields(restored_from=<apply_id>))` with `partition: <name>` (the
       row's partition; both ends by name as the catalog holds them after the re-attach, the
       restored end under its restored name). `edge_event` is the ONE builder of an `evidence`
       append (the dump and every live writer use it; `row_event` raises on `evidence`, which
       is in `EDGE_OPS`, not `ROW_OPS`), so this is d9cg's "one row-event builder". A row of
       multiplicity `k` logs `k` appends. A failed append aborts the restore's transaction
       (no silent path between the manifest and the store). The count of appends equals
       `restore_reattached`'s evidence count and is printed beside it.
       - *Why always, not only after a compaction.* `dump_catalog_to_log` emits a
         `linkage_evidence` row only when BOTH ends are live entities (its `evidence` query
         joins `entities` on `concept_id` and `entity_id`), so a compaction between the purge
         and the restore drops the orphaned row's append and the purge's `tombstone`; without
         an append, a rebuild of that log never holds the row while live does. Restore cannot
         tell from the catalog whether a compaction ran since the purge, and reading the log
         for it would make the restore's output depend on log history. So it always logs.
       - *No double count: the tagged append RESTATES, it does not add (chosen over idempotence
         by row key).* When the log was NOT compacted, the purged incarnation's own append
         still holds the copy on a rebuild ([[task-22.6-removal-entry-points#r5-timeline]]:
         its tombstone is reversed, so it is not revivable for a drop and stays), and a plain
         second append would hold the row twice. The rule, one function
         ([[task-22.6-removal-entry-points#r5-restated-fn]]): a `restored_from: M` `evidence`
         append ABSORBS the earliest copy still held, and not already absorbed by another tagged
         append, with the same `edge_records.row_key` plus
         `detail` (the `partition` field not compared: the row pass runs per partition, and a
         live-shape append carries no field) that was appended BEFORE the restored end's
         `tombstone` carrying `manifest: M` and whose every tombstone between it and that one
         was itself reversed before it (the copy belongs to the incarnation `M` purged); an
         absorbed copy keeps its own append's position and fields and the tagged append adds
         nothing. When no such copy is held (the compacted log has neither the copy nor the
         `M` tombstone), the tagged append adds the copy. The restored end is the end (entity
         or concept: 22.6 AC-9c re-attaches a concept end) whose key's timeline holds the `M`
         tombstone; a row whose both ends `M` purged is absorbed only by a copy that qualifies
         on both. This is the `restored_from` reading 22.6's revivable predicate already makes,
         carried to the append: a reversed tombstone means "the incarnation's copy stayed in
         place", and the tagged append names that same copy. Idempotence by `row_key` plus
         `detail` alone is REJECTED: it collapses a re-attached row of multiplicity 2 to one
         copy on a compacted log (AC-4e's multiplicity variant, 1 against live 2), and it would
         also let a restore's append fold into a different incarnation's or a live holder's
         copy of the same key.
       - *A later purge and restore of the same entity.* The absorbed copy keeps the old
         append's position, so a second restore (manifest `M2`) finds it again: the tombstone
         `M` between it and `M2`'s tombstone is reversed, so it still belongs to the incarnation
         `M2` purged (AC-4e's re-purge variant).
       - *The compactor.* After the restore, a compaction emits the live row as a plain dumped
         append (no `restored_from`; R6's new-field rule: the field has nothing left to absorb
         against in a log with no tombstone), which is exact.
     - **The restore re-logs every link and every sidecar row it re-attaches in place (d9ch;
       round 14).** {#r4-relink} d9cg's rule, carried to the two other row types the `id_map`
       re-attaches in place, so no row type is re-attached silently:
       - *Links.* For EVERY surviving `entity_links` row the `id_map` re-attaches in place,
         restore logs one `link` event, after the restored entity's `entity{restored_from}`
         event, built by `edge_records.edge_event("link", linkage, c_kind, c, e_kind, e,
         weight=<the row's catalog weight>)` with `partition: <name>` (the live end's partition,
         where the re-attach sets the bit; both ends by name as the catalog holds them after the
         re-attach), the same builder and fields `dump_catalog_to_log` and `Store.link` use. It
         carries no `restored_from`: a `link` event is a SET member, not a counted copy. Replay
         keeps the latest `link` / `unlink` per key `(partition, linkage, c_kind, c, e_kind, e)`
         (`rebuild_index_from_log`'s `link_state`), and 17.4's fold decides an edge by the same
         last event per edge key, so a second `link` on a key whose latest event is already
         `link` holds one edge on both: count-neutral on an uncompacted log, with no absorb
         rule and no new fold rule. Logged always, for the reason the evidence append is: the
         dump's `entity_links` query joins BOTH ends to live entities in the partition, so a
         compaction between the purge and the restore drops the orphaned link's `link` event,
         and the restore cannot see whether one ran. The count of `link` events equals
         `restore_reattached`'s link count and is printed beside it; a failed append aborts the
         restore's transaction.
         *Reach at HEAD (read while tracing, round 14).* No purge path at HEAD leaves a link
         that names the purged id: `Store.purge_entity` and `Store._bulk_purge_ids` delete
         `entity_links` on BOTH `entity_id` and `concept_id` (and `purge_entity` logs `unlink`
         per pair), and the merge path re-points both columns before its delete. A purged
         entity's own links are therefore the manifest's per-entity `link` records, which
         restore RE-INSERTS with its `link` events (the inverse events below), not rows it
         re-attaches in place. The in-place link set is non-empty only for a row some other
         route put in the catalog naming the old id after the purge (a writer holding a stale
         id, or a future purge path that keeps links); this rule covers that row so no row
         type is re-attached silently, and AC-4e's link leg plants one.
       - *Sidecar rows (16.6 R1d's dump omits them).* 16.6 R1d's dump emits a
         `learned_provenance` event only for a sidecar row whose evidence row it dumps
         ([[task-16.6-learned-row-validation#r1d]], round 14): the event is keyed by NAME and
         takes its evidence row's dumped `ts`, and a row with a dead end has neither a name for
         that end nor a dumped append. 16.6 R1e keeps the sidecar rows of a purged entity in
         place, so after `untrack` and a compaction the orphaned sidecar rows survive in the
         catalog with no event in the log. So for every sidecar row whose identity the restore
         re-attaches (its `entity_id` or `concept_id` moved to the new id in the same
         transaction), restore logs one `learned_provenance` event, built by 16.6's
         `edge_records.row_event` from the row's every non-mark column (16.6 R1d's field list,
         `c_kind` the concept's catalog kind), with `partition`, AFTER that row's restating
         `evidence` append ([[#r4-restate]]) and with its `ts` (R3's "within a call" order; in
         the row pass it ties with the append and follows it by log position, so its evidence
         row exists when it applies). No `learned_provenance_move` is logged: by name the key
         did not change (the restored entity keeps its name), so a move would name the same
         key twice. On an uncompacted log the original `learned_provenance` event still
         resolves (its evidence copy is held: the tombstone is reversed), and the re-logged
         event is a no-op on the sidecar's primary key (16.6 R1, `ON CONFLICT DO NOTHING`), so
         no absorb rule is needed; 17.4's fold counts no sidecar rows. The count of re-logged
         sidecar events is printed beside `restore_reattached`.
     - **The restore re-logs every sidecar row it RE-INSERTS (d9ci; round 15).**
       {#r4-reinsert-sidecar} d9cg and d9ch cover the rows the `id_map` re-attaches IN PLACE;
       d9ci closes the other half, so EVERY row the restore puts back is logged. When the
       restore re-inserts an `evidence_row` LIVE from the manifest (its dead side is a key of
       this `id_map`, the first bullet of "Restore maps every recorded old id" above; AC-4d's
       shape), that row's sidecar rows are not in the catalog: R2's concept-side rule removed
       the row with `remove_evidence(identity, keep=0, ingest_ok=True)`, which deletes the
       identity's sidecar rows live, and its `evidence_remove` replay deletes them on a rebuild
       too (16.6 R1d). So the original `learned_provenance` event no longer reaches a rebuild's
       sidecar, compacted log or not, and the restore re-logs each re-inserted sidecar row. The
       same holds for every other evidence row the restore re-inserts LIVE (both ends live
       after the restore) from a manifest record together with its sidecar rows (22.6 R3's
       learned rows, whose file entity the same restore re-creates): the rule below is the one
       call site for both. A row re-inserted DANGLING (the dead-id re-check's step (3), and so
       22.6 R5's vacuum rows, whose entity no restore re-creates) is catalog-only and logs no
       `evidence` append, so this rule does not reach its sidecar rows.
       - *One insert, one event.* Each sidecar row is re-inserted through 16.6's
         `Store.add_learned_provenance` (the table's only INSERT path, 16.6 R1; 22.5 R2's
         precedent), from the manifest's recorded columns, on the re-inserted row's identity
         (its dead side mapped to the new id). The one `learned_provenance` event that call logs
         per inserted row, built by `edge_records.row_event` (`c_kind` the concept's catalog
         kind, both ends by name, `partition`), IS the re-log; no second event is written. A row
         the call does not insert (16.6 R1's `ON CONFLICT DO NOTHING`: a reading of that
         identity already exists, e.g. re-learned between the purge and the restore) logs
         nothing, and the existing reading's own event already reaches the rebuild.
       - *Order.* After the row's own `evidence` append (the "logged by name" event above; `k`
         appends for multiplicity `k`) and with the same `ts` (R3's "within a call"; a later `ts`
         orders the same way under 16.6 R1d's within-a-call rule, and only an earlier one is
         wrong, AC-4e's second d9ci mutation): in the row pass it ties with the append and
         follows it by log position, so its evidence row exists when it applies. On an uncompacted log the original `learned_provenance` event resolves
         before the purge's `evidence_remove`, which removes it with its row; the re-logged
         event re-creates it after the re-insert. On a compacted log the dump holds neither the
         row nor its sidecar (both were removed live), and the re-logged event is the only one.
       - *No absorb rule.* The re-inserted `evidence` append is a plain append: the purge's
         `evidence_remove` deleted the old copy (R3's timestamp order), so there is no held copy
         to restate and `edge_records.restated_copy` is not involved. The sidecar event is a
         no-op on 16.6's primary key if one already resolves; 17.4's fold counts no sidecar rows.
       - A failed insert or append aborts the restore's transaction (no silent path between the
         manifest and the store). The count of sidecar events logged by re-inserts is printed
         beside `restore_reattached` as `restore_sidecar_reinserted`.
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
       (r7 m-1). **Covering and reborn by the one legacy rule (r8 m-2).** An event covers a key
       `(p, k, n)` only when its `c_kind` is `k`, or it is legacy and
       `edge_records.resolve_legacy_kind` over the kinds LOGGED for `n` in `p` returns `k`
       (22.1a condition (iii)); the reborn entities of a dead id are EVERY live key a covering
       event names that way, not one "best" key. Re-measured on the same cliquedb copy
       ([[task-22.1a-provenance-free-classes#r1-dangling]]): still 896 evidence-side reborn, 381
       of them covered by more than one live key (r7's best-key split depended on set order), 47
       carrying a row the reborn entity does not hold (121 `(row, key)` pairs, every one a row a
       `doc` of the same name holds live while the legacy rule resolves the name to `concept`).
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
          `(partition or its bound partition, …)` (`rebuild_index_from_log`'s `dpart` and `part`,
          `store.py:7946`, `:7968` at `23ad703`) and `_log_event` adds no partition itself (r7
          m-3). Each event names the concept end as `(c_kind, c)` (r8 b-1, d9bl): the `c_kind`
          of the KEY it answers, which for a legacy `link` / `evidence` event is the kind Pass 2b
          resolves it to (16.6's `edge_records.resolve_c_kind`, the one legacy rule), so the event
          lands on the key a rebuild holds:
          - **NAMED dead endpoint:** once per apply, one `tombstone{kind, name}` with the partition
            field of its surviving `entity` event.
          - **Link row whose both ends are then named** (the live end by its catalog name, the
            dead end by its log name): one `unlink{linkage, c_kind, c, e_kind, e}` per DISTINCT
            last-wins `link` key that answers the row (`c_kind` = that key's kind: the dead
            concept's logged key kind for a dead concept side, the live concept's catalog kind
            otherwise), each with that `link` event's partition field (r7
            m-3: a compacted `entity` event may carry `partition` while later live `link` events
            do not, and an `unlink` keyed on the entity's partition would not override the
            live-shape key; if the name were later re-created in the bound partition the old link
            would revive). A later re-creation of the name then does not revive the old link (the
            latest of `link`/`unlink` wins).
          - **Evidence row of a NAMED dead concept:** the concept's tombstone AND one
            `evidence_remove{linkage, c_kind, c, e_kind, e, file, line, detail, keep: 0,
            ingest_ok}` by name (d9av; r7 b-1), `c_kind` the dead concept's logged key kind (a
            `doc` for a `rel:` target), through `remove_evidence(identity, keep=0,
            ingest_ok=True)`.
            Under R3's timestamp order the remove deletes on replay only the copies appended at or
            before it: if the concept's name is re-created later and the old `evidence` events
            re-resolve, the remove still drops them (the live store does not hold them), while an
            identical row a later re-ingest appends after the remove survives (the live store
            holds it). Round 6's "tombstone only" branch, and its caveat that a re-created name
            re-attaches the old rows, are WITHDRAWN: that rested on the remove pass running after
            every append (AC-3e).
          - **`unnamed:reborn` (r7 m-1; per row and per live covering key, r8 m-2):** a
            covering key has a live catalog row, so NO tombstone (it would drop the reborn entity
            on a rebuild: its `ts` would be later than the reborn entity's `entity` event). For
            each dead row and each LIVE key that covers it (22.1a condition (iii): `c_kind`
            equal, or the one legacy rule over the logged kinds), when that key's entity does NOT
            hold the row and the key's last-wins event for the row is a `link` (link side), or a
            logged `evidence` event covers it (evidence side), one `unlink` / `evidence_remove`
            by name keyed on THAT key's kind, as above; a row the key's entity DOES hold logs
            nothing for that key (the rebuild converges on it, and an `unlink` or
            `evidence_remove` on its key would delete that live row on a rebuild). A row that
            another kind of the same name holds live while the legacy rule resolves the name to
            this key is also counted `legacy_misresolved` and printed: the rebuild resolves its
            legacy events to the other kind, which a compaction ends (`dump_catalog_to_log`
            re-emits every live row with its `c_kind`), not this engine. Each reborn member is
            counted `reborn` in the apply report, with `reborn_unlinked` /
            `reborn_evidence_removed` for the rows that got an event. On cliquedb: link side 1 row
            at most (id 2791206's 3,459th row; 0 whose last word is `link`, r7 m-1); evidence
            side 121 `evidence_remove` events on 47 dead ids, all 121 `legacy_misresolved` (10
            names live as both `doc` and `concept`; the doc holds every one), measured on the r6
            copy, whose log holds 0 kinded `evidence` events (r8 m-2).
       5. **A NAMELESS dead endpoint (`unnamed:none` / `unnamed:ambiguous`) logs nothing, by
          design.** No name covers its rows in its own partition: the log either names no key for
          it, or names several that no single one wins. So a rebuild cannot re-create the
          endpoint ONTO those rows (link and evidence replay need both names in the rebuilt
          catalog, and pass 3 skips and COUNTS a row whose `cid` or `eid` does not resolve:
          `links_skipped_dead` / `evidence_skipped_dead`, bug-117, r8 m-4), and the deleted
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
   `part-of` from DOC `Y`, its event carrying `c_kind: doc`), and no tombstone; the log also holds
   a `concept` named `Y` in `p2` (r8 b-1); `D`'s `entities` row is then deleted by raw SQL
   (bug-111's shape), leaving its two `entity_links` rows dangling. A third `entity_links` row
   names an id that no `entity` event ever named (nameless). Steps: `removal_audit`, `--apply`,
   then `cp` the store and run `rebuild_index_from_log` on the copy. Expected: the live store and
   the copy each hold 0 `entity_links` rows with a dead endpoint, and `repair_fragments(dry_run=
   True)` on each reports `links_dead_entity == 0` and `links_dead_concept == 0`; the copy holds
   NO entity named `D` in any partition and no link to `X` or `Y` from one; the copy's rebuild
   reports `links_skipped_dead == 0` and `links_unresolved == 0` (r8 m-4: every `link` key of `D`
   is answered by its `unlink`, so pass 3 has nothing dead to skip); `facts.log` gained exactly
   one `tombstone{kind: doc, name: D, partition: p2}` and two name-keyed `unlink` events, each
   with the `c_kind` of the `link` it answers (`concept` for `X`, `doc` for `Y`), and no event at
   all for the nameless row; the apply report reads `named=1 nameless=1`.
   Mutations, each FAILS it: "log `link_remove` by id" (no tombstone: the copy resurrects `D`
   with both links); "no tombstone for the named dead endpoint" (unlinks only: the copy
   resurrects `D`); "tombstone without the `entity` event's partition field" (it keys on `p1`:
   the copy resurrects `D` in `p2`); "tombstone only, no `unlink`" (the first copy reports
   `links_skipped_dead == 2`, r8 m-4).
   **Partition of the `unlink` (r7 m-3).** `D`'s `mentions` `link` event from `X` carries NO
   `partition` field (the live shape) while its `entity` event carries `partition: p2`; after the
   apply the test re-creates a doc named `D` in `p1` (the bound partition) and rebuilds a second
   copy: that copy holds no `mentions` link from `X` to the new `D`. Mutation "key the `unlink`
   on the `entity` event's partition" FAILS it (the `unlink` keys on `p2`, the live-shape `link`
   key on `p1` still wins, and the old link revives onto the new `D`).
   **Kind of the `unlink` (r8 b-1).** After the apply the test also re-creates a doc named `D` in
   `p2` and rebuilds a third copy: it holds no `part-of` link from doc `Y` to the new `D`.
   Mutation "`unlink` without `c_kind`" FAILS it (Pass 2b's legacy rule resolves the kindless
   `unlink` to `(concept, Y)`, the kinded `(doc, Y)` `link` key keeps its `link`, and the old link
   revives onto the new `D`).
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
   `A`'s old id (R4's `evidence_row`). A second fixture purges a DOC `A2` (a `rel:` target of
   `B`; r8 b-1: the dominant shape) through this engine (R2's rule): 0 dangling-evidence rows
   result, the logged `evidence_remove` carries `c_kind: doc`, and a rebuild on a copy holds no
   `B` row to `A2`, with `evidence_unresolved == 0` and `evidence_skipped_dead` equal to the
   number of `evidence` events naming `A2` in the fixture's log (`A2` is tombstoned, so each is
   skipped and counted, none silently; r8 m-4). Mutations: "drop the `dangling-evidence` sub-class"
   FAILS it (the row stays); "purge without first removing the concept-side evidence rows"
   (R2) FAILS the second fixture; "the learned guard applies to `ingest_ok` callers too" (r7
   m-4) FAILS both (the `rel:` row is not matched and stays); "row ops resolve `c` as kind
   `concept`" (r8 b-1) FAILS the second fixture's re-creation clause in AC-3d. An AST test asserts that
   `remove_evidence(..., ingest_ok=True)` is called only from R2's concept-side rule and
   `remove_dangling_evidence`; mutation "a third caller passes `ingest_ok=True`" FAILS it.

   **3d. A removal followed by a re-creation survives the rebuild (d9av; r7 b-1).** Two
   fixtures, each ending with `rebuild_index_from_log` on a copy that must EQUAL the live store
   on `linkage_evidence` (multiset of rows by name), on the sidecar (every column but 16.6's
   mark columns) and with `unresolved_provenance == 0` and `evidence_unresolved == 0` (r8 m-4):
   - *Learned (the branch switch).* File `F` has one learned row `(mentions, query/P, F, 12)`
     with its sidecar row (`F` learned-only, `protect_source='learner'`). `F` is deleted and a
     `missing-file` apply removes the row (`evidence_remove`) and purges `F` (`tombstone`). `F`
     is re-created with the same line and `P` is learned again: the learner writes the
     identical row (`entity F`, `evidence`, `learned_provenance` events, all later than the
     remove). Live: 1 row, 1 sidecar row. The copy: the same.
   - *Ingest, through R2.* The AC-3c second fixture's engine purge of DOC `A2` (r8 b-1: a `rel:`
     target, the dominant case; round 7 chose kind `concept` only because the rebuild then
     resolved every concept end as `concept`, which bug-117 ended in 0.78.3) removes `B`'s
     `rel:` evidence to `A2`, logging `evidence_remove{c_kind: doc, …}`. Then `A2` is re-created
     and `B` is edited and re-synced, writing the identical evidence row. Live: 1 row. The copy:
     the same.
   Mutations, each FAILS it: "`evidence_remove` applied after all appends" (round 6's pass
   order) FAILS both (the copy deletes the re-created row; the learned fixture also counts
   `unresolved_provenance` 1); "row ops resolve `c` as kind `concept`" (r8 b-1) FAILS the ingest
   fixture BEFORE the re-sync: a copy rebuilt right after `A2` is re-created holds `B`'s OLD row
   on the new `A2` (the remove resolved nothing, the old `doc` append re-attaches), while live
   holds none.

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
   Each copy's rebuild reports `evidence_unresolved == 0`; copy 1 reports
   `evidence_skipped_dead` equal to `B`'s appends to `A` the remove did not cover (0 in the
   fixture, r8 m-4). `A` stays kind `concept` here (r8 b-1: AC-3c/3d cover `doc`, so both kinds
   are covered).
   Mutations, each FAILS it: "no tombstone for a named dead concept" (copy 1 resurrects `A`);
   "tombstone only, no `evidence_remove`" (round 6's branch: copy 2 re-attaches the old row to
   the re-created `A`); "`evidence_remove` applied after all appends" (copy 3 loses the row).

   **3f. A legacy append against a kinded remove (r8 b-1; r9 m-1, m-2).** Doc `A` and concept `A`
   both live in the default partition; `B`'s `rel:` evidence row to doc `A` is held live, and its
   `evidence` event in `facts.log` is LEGACY (no `c_kind`, written as a pre-0.78.3 log holds it).
   Asserted precondition: a rebuild of a copy BEFORE the apply attaches `B`'s row to `concept A`
   (the one legacy rule picks `concept`), the bug-117 residue the helper exists for. `A` (the doc)
   is purged through this engine (R2's concept-side rule). Every copy below is rebuilt with
   `rebuild_index_from_log` (the one replay path, d9bu) and reports `evidence_unresolved == 0`.
   1. *Concept `A` holds no identical row.* `Store._row_op_c_kinds("A", "doc", row)` returns
      `(("doc", 0), ("concept", 0))`, and the apply logs one `evidence_remove` per pair. A rebuild
      on a copy holds no `B` row to either `A`, equal to live.
   2. *Concept `A` holds ONE identical row of its own* (same `B`, `file`, `line`, `detail`) before
      the purge: the helper returns `(("doc", 0), ("concept", 1))`, the apply prints
      `legacy_misresolved=0`, and concept `A`'s row is held once on the live store AND once on
      the copy (the `keep: 1` op collapses its own append and the misresolved legacy one, r9
      m-2). A variant with TWO identical copies on concept `A` returns `(("doc", 0),)` and prints
      `legacy_misresolved=1` (the counted residue a compaction ends).
   3. *A tombstoned concept, live kinds blind to it (r9 m-1).* `concept A` is created and
      tombstoned in the log (so no LIVE concept `A` exists); doc `A` holds `B`'s legacy row.
      Purge doc `A`: the helper returns `(("doc", 0), ("concept", 0))` although the live kinds
      for `A` are `{doc}`. Then re-create `concept A`. A rebuild on a copy holds no `B` row on
      `concept A`, equal to live.

   Mutations, each FAILS it: "a row op names only the catalog kind" (run 1's copy holds `B`'s
   row on concept `A`); "`keep: 0` on the concept op" (run 2's copy holds concept `A`'s row 0
   times, live once); "the helper reads LIVE kinds through the legacy rule" (round 8's helper:
   run 3 logs only the `doc` op, and the copy revives `B`'s legacy row on the re-created
   `concept A`, which live does not hold).
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
   restated by one `restored_from`-tagged append, [[#r4-restate]]) needs 22.6's entry points and
   is [[task-22.6-removal-entry-points]] AC-9c, built on this task's restore rule.

   **4e. A compaction between the purge and the restore loses nothing (d9cg; round 13; link and sidecar legs, d9ch, round 14; dead-side re-insert sidecar leg, d9ci, round 15).** Built
   on 22.6's `rmx untrack` (a purge outside the engine is the only path that leaves a surviving
   row for the `id_map` to re-attach in place), so it runs in 22.6's slice beside AC-9c
   (`tests/test_removal_entry_points.py`). On a sandbox store: doc `E` holds a `rel:` evidence
   row to concept `C` (append `a0`). (1) `rmx untrack` of `E`'s file (tombstone `manifest: M`;
   the row is orphaned, purge deletes no evidence). (2) `dump_catalog_to_log` (the compactor's
   call, `Daemon._compact_factslog_if_needed`): the dump holds no `E`, no tombstone and no
   `a0`. (3) `removal restore` of `M`: `E` re-created, its row re-attached in place, and
   `facts.log` gains exactly one `evidence` append for it carrying `restored_from: M`,
   `c_kind`, `e_kind: doc`, `e: E` and `partition` (`restore_reattached` evidence count 1).
   (4) `rebuild_index_from_log` on a copy: the `linkage_evidence` multiset compared by name
   (`linkage`, both ends, `file`, `line`, `span_end`, `detail`, multiplicity) EQUALS live's.
   *Concept-end variant:* the same with AC-9c's shape (concept `A` untracked, doc `B`'s row
   re-attached onto `A`'s new id): equal.
   *Uncompacted control:* steps 1, 3, 4 without step 2: the rebuild holds `E`'s row ONCE,
   equal to live (the tagged append is absorbed into `a0`'s copy).
   *Multiplicity variant:* `E` holds two identical rows: compacted and uncompacted, the rebuild
   holds two, equal to live.
   *Re-purge variant:* after step 4 of the uncompacted control, `untrack` again (`M2`), restore
   `M2`, rebuild: once, equal to live (the absorbed `a0` copy belongs to `M2`'s incarnation).
   *Link leg (d9ch; round 14):* `untrack` deletes `E`'s own links and logs `unlink` for each
   ([[#r4-relink]] "Reach at HEAD"), so the leg PLANTS the in-place row: after (1), the fixture
   inserts one `entity_links` row (`mentions`, concept `C`, entity `E`'s OLD id, weight 0.5)
   directly in the catalog, with no event (the dangling-link shape 22.1a's fixtures plant; a
   writer that held `E`'s stale id). After (2) the dump holds no `link` on that key (`E` dead);
   (3) re-attaches it in place and logs exactly one `link` event for it (`c_kind`, `e: E`,
   `weight: 0.5`, `partition`; `restore_reattached` link count 1); after (4) the `entity_links`
   SET compared by name (`linkage`, both ends, `weight`) EQUALS live's. The uncompacted control
   (steps 1, plant, 3, 4): equal, the link held once.
   *Sidecar leg (d9ch; round 14):* in the base fixture `E` also holds a learned evidence row from
   concept `query/foo` (kind `concept`) with one 16.6 sidecar row. After (2) the dump holds
   neither its append nor a `learned_provenance` event (16.6 R1d: a sidecar row with a dead end
   is not dumped); (3) logs one restating `evidence` append for it, then one `learned_provenance`
   event with the same `ts`; after (4) the sidecar EQUALS live's on every column but 16.6's three
   mark columns, and `unresolved_provenance` is 0. The uncompacted control: equal, one sidecar
   row (the re-logged event is a no-op on the primary key).
   *Dead-side re-insert sidecar leg (d9ci; round 15; [[#r4-reinsert-sidecar]]):* AC-4d's shape
   with a learned row, through this engine (no 22.6 entry point needed): doc `B` carries a
   learned `mentions` evidence row (`detail` `learned from grep…`) from concept `query/foo`
   (kind `concept`) with one 16.6 sidecar row; `query/foo` is purged through this engine as AC-4d
   purges `A` (R2's concept-side rule records `B`'s row as an `evidence_row` with its sidecar
   row, removes both, and logs `evidence_remove` with `keep: 0`). Run twice: uncompacted
   (purge, restore, rebuild on a copy) and compacted (purge, `dump_catalog_to_log`, restore,
   rebuild on a copy). In both, the restore logs for `B`'s row exactly one plain `evidence`
   append (no `restored_from`) and then one `learned_provenance` event with the same `ts`
   (`restore_sidecar_reinserted` 1); the rebuild's sidecar EQUALS live's on every column but
   16.6's three mark columns, and `unresolved_provenance` is 0.
   Mutations, each FAILS it:
   - "re-insert without re-logging the sidecar" (the sidecar row put back by a raw INSERT with no
     event): uncompacted, the rebuild applies the original `learned_provenance` event, then the
     purge's `evidence_remove` deletes the identity's sidecar rows (16.6 R1d), and the restore's
     append re-creates the evidence row with no sidecar event after it: 0 sidecar rows against
     live's 1; compacted, the dump holds no `learned_provenance` for `B`'s row (it was removed
     live before the dump), so again 0 against 1;
   - "re-log the re-inserted sidecar before the row's append" (or with an earlier `ts`): the row
     pass applies it after the `evidence_remove` and before the append, so no evidence row
     exists for it: `unresolved_provenance` 1 and 0 sidecar rows against live's 1, in both runs;
   - "re-attach a link without logging" (round 7's rule for links): after (2) the log holds no
     `link` event on `E`'s key (the dump's `entity_links` query joins both ends to live
     entities, and `E` was dead when it ran), (3) adds none, so (4)'s rebuild re-creates `E` and
     `C` but its `link_state` has no entry for the key: 0 `E`-to-`C` links against live's 1
     (the planted row has no event, so the uncompacted control fails the same way);
   - "log the re-attached link without `weight`": the rebuild's `self.link(..., weight=None)`
     holds the link with weight NULL against live's 0.5 (the set compared with `weight`);
   - "re-attach the sidecar without re-logging it": the compacted log holds no
     `learned_provenance` event for the row, so (4)'s rebuild holds the evidence row (from the
     restating append) and 0 sidecar rows against live's 1;
   - "log the sidecar event before the restating append" (or with an earlier `ts`): the row
     pass applies it before the append it names, the evidence row does not yet exist, so it is
     counted `unresolved_provenance` 1 and the rebuilt sidecar holds 0 rows against live's 1;
   - "re-attach without logging" (round 7's rule: the in-place update, no append): after (2)
     the log holds no record of `E`'s row (the dump's `evidence` query joins both ends to live
     entities, and `E` was dead when it ran), and (3) adds none, so (4)'s rebuild materializes
     `E` from its `entity{restored_from}` event and holds 0 `E`-to-`C` rows against live's 1;
     the concept-end variant likewise 0 against 1;
   - "the tagged append always adds a copy" (no absorption): the uncompacted control holds 2
     against live's 1 (`a0`'s copy, whose tombstone is reversed and so is not dropped, plus the
     restore's);
   - "absorb by `row_key` plus `detail` alone, idempotently" (the rejected alternative): the
     compacted multiplicity variant holds 1 against live's 2;
   - "the window ignores reversal of the earlier tombstone" (a copy qualifies only when NO
     tombstone lies between it and `M`'s): the re-purge variant holds 2 against live's 1.
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
   Each re-attached link logs `unlink` of its old key and `link` of its new key (with `c_kind`),
   and `rebuild_index_from_log` on a copy equals live by name on `entities`, `entity_links` and
   `linkage_evidence` (r11 s-2); the fixture's old entity links at least one concept the
   surviving entity does not. Mutation "re-attach links without logging `unlink` / `link`"
   FAILS it: the old key's latest event is still `link`, its entity is tombstoned, so the
   rebuild skips those links as dead (`links_skipped_dead` > 0) and holds none of them on the
   surviving key, while live holds every one.
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
| `src/refmatrix/store.py` | `manifest=` on `purge_entity` / `_bulk_purge_ids` (and the `purge_path` callers that write a manifest), spliced into the `tombstone` event; `restored_from=` on `upsert_entity`, spliced into restore's `entity` events; both through `edge_records.reversal_fields` ([[#r4-reversal]]; d9cf, r12 s-1); the R2 primitives (`remove_evidence(..., ingest_ok=)`, `repoint_evidence`, `rename_entity`, whose merge logs `unlink` / `link` per re-attached link, r11 s-2) and R2's concept-side evidence rule before a purge; `remove_dangling_links` and `remove_dangling_evidence` (R9, built on `_clear_purged_bits`; reborn and per-`link`-key partition rules, r7); the R3 ops in `rebuild_index_from_log`'s one timestamp-ordered row pass (no `_apply_event_body` branch: 16.6 R1f deletes it, d9bu) (16.6 R1d builds the pass; d9av); R4's restore of `link_row` / `evidence_row` with the dead-id re-check and the `id_map` re-attach (r7 s-1, s-2), which moves the re-attached identity's sidecar rows to the new id in the same transaction (R2's owner rule; [[#r4-relink]], d9ch); the rebuild's row pass applies a `restored_from`-tagged `evidence` append through `edge_records.restated_copy` (absorb or add; [[#r4-restate]]; d9cg); `Store._row_op_c_kinds`, the one helper naming a live primitive's op `(c_kind, keep)` pairs (r9 m-1, m-2), and every row-op event through `row_event` / every `unlink` through `edge_event` with `c_kind` (r8 b-1) |
| `src/refmatrix/edge_records.py` | `reversal_fields` / `reversal_of`, the one builder and reader of `manifest` on purge tombstones and `restored_from` on restore's `entity` events and on its restating `evidence` appends ([[#r4-reversal]], [[#r4-restate]]; d9cf, r12 s-1; d9cg; the functions that read them, `revivable` and `restated_copy`, are 22.6's); `evidence_remove` and `evidence_repoint` added to 16.6's `ROW_OPS`, built by `row_event` (r8 b-1, d9bl); `_LEGACY_PREFERRED_KIND` renamed to the public `LEGACY_PREFERRED_KIND` (read by `resolve_legacy_kind` and by `Store._row_op_c_kinds`, r9 m-1) |
| `scripts/factslog-restore.py` (plan-17 task 17.4's) | `evidence_remove`, `evidence_repoint`, `entity_rename` added to `FOLD_OPS`, each with its stated fold rule (r10 s-3), folded in the rebuild's `(ts, log position)` order: `evidence_remove` reduces the copies of its key (`row_key` plus `detail`, in its `partition` field) appended at or before it to its `keep`; `evidence_repoint` is count-neutral (it moves a copy's `file` / `line`, the evidence count is unchanged) and is named in `FOLD_OPS` as ignored for the counts; `entity_rename` renames the entity key in the fold's name map and, when `merged` is true (the [[#r2]] collision), moves the old key's evidence copies to the surviving key (count-neutral for `evidence`); links follow their own `unlink` / `link` events and the entity count follows the old key's own `tombstone`, so the rename itself changes neither (r11 s-2, d9cc: evidence moves; links and entities follow their own events). 22.6 AC-6d proves the fold's counts equal the rebuild's on AC-3's, AC-3d's, AC-3f's and AC-7's logs ([[task-22.6-removal-entry-points#acceptance]]). In the same commit as the replay branch: 17.4's AST test pins `FOLD_OPS` to `rebuild_index_from_log`'s op set, and an op missing from it fails restore verification loudly (`unknown event op`) ([[task-17.4-factslog-backup-snapshot#r6-restore]]; ns17-r9-2) |
| `src/refmatrix/removal_apply.py` (new) | the R6 batch loop over `bounded_steps` (incl. the per-partition and `none` batches), each batch's purges called with `manifest=<apply_id>`; R4's intent log and restore, restore's `entity` events with `restored_from=<apply_id>` for every `id_map` key ([[#r4-reversal]]; d9cf, r12 s-1), and one `restored_from`-tagged `evidence` append per evidence row re-attached in place, built by `edge_records.edge_event`, the count printed beside `restore_reattached` ([[#r4-restate]]; d9cg), one `link` event per link re-attached in place (`edge_event`, with `weight`) and one `learned_provenance` event per sidecar row of a re-attached identity (`row_event`, after its restating append, same `ts`), each count printed ([[#r4-relink]]; d9ch), and every sidecar row it re-inserts with a manifest evidence row re-inserted LIVE through 16.6's `Store.add_learned_provenance` after that row's `evidence` append, same `ts`, its one `learned_provenance` event the re-log, counted `restore_sidecar_reinserted` ([[#r4-reinsert-sidecar]]; d9ci), R7's gate, R5's attribution incl. [[#r5-grep-record]] |
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

Round 7 closed here with a note that the rebuild resolved an evidence row's concept only as kind
`concept` (r7 `#code-facts`) and that this was pre-existing and unchanged. bug-117 (0.78.3,
`391ffeb`) closed that gap after round 7 was written; the note is deleted in round 8 and
[[#r3]] "How the ends resolve" now follows the 0.78.3 code ([[#rev-round-8]]).

rel: amends -> [[bsd-plan16-22-spec-rereview-r7-331b414]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-16.6-learned-row-validation#r1d]]

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan16-22-spec-rereview-r8-23ad703]] where it touches 22.2 (b-1, m-2, m-3, m-4, m-5)
and d9bl ([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at `23ad703` (0.78.3,
bug-117); `src/` is unchanged from `23ad703` to the revision's HEAD. Later rows win over round 7.

| finding / decision | answered in |
|---|---|
| r8 b-1 / d9bl (R3 resolved `c` "as kind `concept`" and called doc/memory rows "never rebuilt"; every name-keyed op lacked `c_kind`) | [[#r3]] event list (`evidence_remove`, `evidence_repoint` carry `c_kind`, built by 16.6's `row_event`, in `ROW_OPS`); "How the ends resolve" rewritten (by `(c_kind, c)`, legacy appends by the one rule through `edge_records.resolve_c_kind`, identities by `row_key`); "Which kind a LIVE primitive's op names" (`Store._row_op_c_kinds`, one helper); "No op keyed by id": `unlink` carries `c_kind`, LWW key `(partition, linkage, c_kind, c, e_kind, e)`; [[#r2]] `remove_evidence` and the concept-side rule name `c_kind`; [[#r9-dangling]] step 4 (every event takes the `c_kind` of the key it answers; `unlink`, `evidence_remove`); AC-3b (`Y` a doc with a `concept Y` logged; mutation "`unlink` without `c_kind`"), AC-3c second fixture and AC-3d ingest fixture on a DOC (mutation "row ops resolve `c` as kind `concept`"), AC-3e kept on `concept`, new AC-3f (legacy append vs kinded remove, two mutations); [[#rev-round-7]] closing note deleted; [[#files-to-modify]] |
| r8 m-2 (naming and reborn by the one legacy rule; the 15 two-kind names) | [[#r9-dangling]] naming paragraph (covering by `c_kind` or the legacy rule over LOGGED kinds; every live covering key, not one best key) and step 4's reborn rule (per row and per live covering key; `legacy_misresolved`); re-measured on the r6 cliquedb copy: 896 reborn, 381 on more than one live key, 47 with 121 rows to remove, all 121 legacy-misresolved; the rule is owned by [[task-22.1a-provenance-free-classes#r1-dangling]] |
| r8 m-3 (legacy resolution differs between the paths) | [[#r3]] "The two paths agree on kinded events only"; the bug-registry row is the orchestrator's |
| r8 m-4 (the rebuild's counters) | [[#r3]] "Counters"; [[#r9-dangling]] step 5 (skips counted, `links_skipped_dead` / `evidence_skipped_dead`); AC-3b (`links_skipped_dead == 0`, mutation "tombstone only, no `unlink`" fails directly), AC-3c, AC-3d, AC-3e, AC-3f (`evidence_unresolved`, `evidence_skipped_dead`) |
| r8 m-5 (line pins shifted under 0.78.3) | [[#r3]] re-read at `23ad703` (`store.py:7941` sort, Pass 2b, pass 3 by symbol); [[#r9-dangling]] step 4 (`:7946`, `:7968`) |

rel: amends -> [[bsd-plan16-22-spec-rereview-r8-23ad703]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-16.6-learned-row-validation#r1d-one-format]]

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan16-22-spec-diffcheck-r9-29e335a]] where it touches 22.2 (s-2, m-1, m-2) and
d9bu ([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at `428267f` (`src/`
unchanged since `23ad703`). Later rows win over round 8.

| finding / decision | answered in |
|---|---|
| r9 s-2 / d9bu (the incremental replay path has no caller; the specs kept extending it) | [[#r3]]: the rebuild is the one replay path (16.6 R1f deletes `apply_log_delta`, `_apply_one_event`, `_apply_event_body`, `_replay_concept`); dropped: "Both replay paths", the incremental sentence of "Where the order comes from", the `_replay_concept` half of "How the ends resolve", the "two paths agree on kinded events only" paragraph (now "One resolver", bug-120 closed by removal), the incremental counter, the incremental sentence of "No op keyed by id"; AC-3f's incremental clause; [[#files-to-modify]] (no `_apply_event_body` branch) |
| r9 m-1 (`_row_op_c_kinds` read LIVE kinds; a tombstoned `concept` slipped through) | [[#r3]] "Which kind a LIVE primitive's op names": the extra `concept` pair whenever `catalog_kind` is not `concept` and the live concept holds 0 or 1 identical copies, from the public constant `edge_records.LEGACY_PREFERRED_KIND`, no legacy-rule call; AC-3f run 3 + mutation "the helper reads LIVE kinds through the legacy rule"; [[#files-to-modify]] `edge_records.py` |
| r9 m-2 (AC-3f's second-run divergence avoidable) | [[#r3]]: the concept op carries `keep = n` (`n` in 0, 1); `legacy_misresolved` only for `n >= 2`; AC-3f run 2 asserts copy equals live (once), its two-copy variant keeps the counter tested; mutation "`keep: 0` on the concept op" |
| ns17-r9-2 (coordinator: every new `facts.log` op this task adds is listed against 17.4's `scripts/factslog-restore.py` `FOLD_OPS`) | [[#files-to-modify]] `scripts/factslog-restore.py` row |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r9-29e335a]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 10 (2026-10-15) {#rev-round-10}

Answers [[bsd-plan16-22-spec-diffcheck-r10-451b505]] where it touches 22.2 (m-2, s-3) and
d9bz ([[plan-review-2026-10-14#t12-approvals]]). `src/` unchanged since `23ad703`. Later rows
win over round 9.

| finding / decision | answered in |
|---|---|
| r10 m-2 (`_row_op_c_kinds`'s `n` lost its partition; "identical" undefined for an orphan) | [[#r3]] "Which kind a LIVE primitive's op names": `n` counted on the live `concept` of that name in the ROW'S partition; "identical" defined (entity end by name) and only for a live, named entity end; the helper raises on an orphan row; 22.6's vacuum no longer calls it (r10 s-1, d9bz) |
| r10 s-3 (the `FOLD_OPS` row named no fold rule) | [[#files-to-modify]] `scripts/factslog-restore.py` row: the fold rule of `evidence_remove` (reduce to `keep`), `evidence_repoint` (count-neutral, named ignored), `entity_rename` (rename; merge on collision as [[#r2]]); the fold-equals-rebuild check is 22.6 AC-6d over this task's AC-3d / AC-3f logs |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r10-451b505]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-17.4-factslog-backup-snapshot#r6-restore]]

## Revision round 11 (2026-10-15) {#rev-round-11}

Answers [[bsd-plan16-22-spec-diffcheck-r11-d8188ee]] where it touches 22.2 (s-2 (i), (ii))
under d9cc ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until its ch-bsd loop is
clean). `src/` unchanged since `23ad703`. Later rows win over round 10.

| finding / decision | answered in |
|---|---|
| r11 s-2(i) / d9cc (a merged rename's re-attached links had no event; R3 replays only evidence) | [[#r2]] `rename_entity`: each re-attached link logs `unlink` (old key) and `link` (new key) through `edge_event` with `c_kind`; [[#r3]] "On replay": links and the old entity follow their own events; AC-7 adds live == rebuild by name and the mutation "re-attach links without logging `unlink` / `link`" (traced: the rebuild dead-skips the old key's links); [[#files-to-modify]] `store.py` row |
| r11 s-2(ii) (the `entity_rename` fold rule claimed links and an entity-count drop the rebuild does not make) | [[#files-to-modify]] `scripts/factslog-restore.py` row: "evidence moves; links and entities follow their own events"; 22.6 AC-6d runs over AC-3's and AC-7's logs ([[task-22.6-removal-entry-points#rev-round-11]]) |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r11-d8188ee]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 12 (2026-10-15) {#rev-round-12}

Answers [[bsd-plan16-22-spec-diffcheck-r12-2352e52]] where it touches 22.2 (s-1 (i) and the
files rows) under d9cf ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until its ch-bsd
loop is clean), which SUPERSEDES d9cc (ii), the `L > N` count guard. `src/` unchanged. Later rows
win over round 11.

| finding / decision | answered in |
|---|---|
| r12 s-1 (i) / d9cf (a count cannot tell which incarnation a restore re-attached, F5; only the restore knows which purge it undid) | [[#r4-reversal]]: `manifest: <apply_id>` on every manifest-writing purge's `tombstone`, `restored_from: <apply_id>` on restore's `entity` event for every `id_map` key, matched per entity key; one builder and one reader in `edge_records`; additive, read only by 22.6's `edge_records.revivable`; the dump emits neither (exact, stated); [[#files-to-modify]] `store.py`, `edge_records.py`, `removal_apply.py` rows |
| reviser's tightening of the report's text | the report's reversal test names the manifest only; [[#r4-reversal]] also requires the `entity` event to be the SAME entity key as the tombstone, because one manifest purges many entities: keyed per entity, a reversal cancels only the tombstone of the entity whose surviving rows that `id_map` re-attached, and a partial restore (22.2 R4's "partial apply" bullet) reverses only what it re-attached |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r12-2352e52]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-22.6-removal-entry-points#r5-timeline]]

## Revision round 13 (2026-10-15) {#rev-round-13}

Answers the round-12 reviser's open item (a compaction between a purge and its restore loses
the re-attached row on a rebuild; [[task-22.6-removal-entry-points#rev-round-12]] last row)
under d9cg ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until its ch-bsd loop is
clean). `src/` unchanged. Later rows win over round 7's no-event rule for evidence.

| finding / decision | answered in |
|---|---|
| d9cg (restore never re-attaches an evidence row silently) | [[#r4]] "Restore maps every recorded old id" (a re-attached link still logs nothing; a re-attached evidence row logs a restating append); [[#r4-restate]]: one `restored_from`-tagged `evidence` append per re-attached row (multiplicity `k` logs `k`), built by `edge_records.edge_event` (the one builder of an `evidence` append; `row_event` refuses `evidence`), with `c_kind`, both ends by name and `partition`, always logged (the restore cannot see whether a compaction ran) |
| double count when the log was NOT compacted (raised by the brief) | [[#r4-restate]] "No double count": the tagged append ABSORBS the purged incarnation's own still-held copy (same `row_key` plus `detail`, appended before the `M` tombstone, every tombstone between them reversed) and adds a copy only when none is held; one function `edge_records.restated_copy` ([[task-22.6-removal-entry-points#r5-restated-fn]]), the same three callers as `revivable`; idempotence by row key rejected (multiplicity, other incarnations) |
| d9cg AC | AC-4e (compacted, concept-end, uncompacted control, multiplicity and re-purge variants) with four mutations, "re-attach without logging" traced (the dump joins both ends to live entities, so the compacted log holds no record of the row: 0 against live 1); AC-4d's pointer to 22.6 AC-9c reworded; [[#files-to-modify]] `store.py`, `edge_records.py`, `removal_apply.py` rows |

rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-22.6-removal-entry-points#r5-restated-fn]]

## Revision round 14 (2026-10-15) {#rev-round-14}

Applies d9ch ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until its ch-bsd loop is
clean), which extends d9cg to every row type the restore re-attaches in place and answers the
round-13 reviser's open item ([[task-22.6-removal-entry-points#rev-round-13]] last row, now
CLOSED). `src/` unchanged. Later rows win over round 7's no-event rule for links.

| finding / decision | answered in |
|---|---|
| d9ch (a): a re-attached LINK logs a `link` event | [[#r4]] "Restore maps every recorded old id" (the no-event sentence for links replaced); [[#r4-relink]] *Links*: one `link` event per in-place link, built by `edge_records.edge_event` with `weight` and `partition`, no `restored_from` (a set member: replay's `link_state` and 17.4's fold keep the last event per key, so it is count-neutral uncompacted and needs no absorb rule); AC-4e link leg + mutations "re-attach a link without logging" (0 against live 1) and "log the re-attached link without `weight`" (NULL against 0.5) |
| reach of (a) at HEAD, found while tracing | [[#r4-relink]] "Reach at HEAD": `purge_entity` and `_bulk_purge_ids` delete `entity_links` on both columns (and `purge_entity` logs `unlink`), so no purge leaves an in-place link; a purged entity's links are re-INSERTED from the manifest with events. The rule covers a row another route puts there; AC-4e plants one (22.1a's dangling-shape fixture precedent). The [[#r4]] bullet's example ("leaves `B`'s row in place") holds for evidence rows only |
| d9ch (b): the sidecar of a re-attached learned evidence row | 16.6 R1d's dump emits a `learned_provenance` event only for a sidecar row whose evidence row it dumps (stated explicitly in [[task-16.6-learned-row-validation#rev-round-14]]), and R1e keeps a purged entity's sidecar rows in place, so the dump SKIPS them; [[#r4-relink]] *Sidecar rows*: the in-place update moves them to the new id (R2's owner rule) and the restore re-logs each through `row_event` after its restating append, same `ts`; no `learned_provenance_move` (by name the key is unchanged); uncompacted it is a no-op on 16.6's primary key; AC-4e sidecar leg + mutations "re-attach the sidecar without re-logging it" (0 rows against live 1) and "log the sidecar event before the restating append" (`unresolved_provenance` 1, 0 rows) |
| d9ch (c) | [[task-17.4-factslog-backup-snapshot#r6-restore]] step 3 names `edge_records.restated_copy` beside `revivable` ([[task-17.4-factslog-backup-snapshot#rev-round-14]]) |
| CLOSED in round 15 by d9ci ([[#rev-round-15]]); was: raised, not ruled by d9ch | the sidecar rows a restore RE-INSERTS with an `evidence_row` (the dead-side re-insert, not in place): [[#r4]] logs their `evidence` append by name but names no `learned_provenance` event for the manifest's sidecar rows; if the restore re-inserts them silently, a rebuild loses them even with no compaction. Needs a ruling (the same rule, one more call site). ANSWERED by d9ci: [[#r4-reinsert-sidecar]] and AC-4e's dead-side re-insert sidecar leg |

rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-16.6-learned-row-validation#r1d]]

## Revision round 15 (2026-10-15) {#rev-round-15}

Applies d9ci ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until its ch-bsd loop is
clean), which completes d9cg and d9ch: every row the restore puts back is logged, whether
re-attached in place or re-inserted on the dead side. Answers the round-14 open item
([[#rev-round-14]] last row, now CLOSED). `src/` unchanged.

| finding / decision | answered in |
|---|---|
| d9ci: the sidecar rows of an `evidence_row` the restore re-inserts LIVE from the manifest | [[#r4-reinsert-sidecar]]: re-inserted through 16.6's `Store.add_learned_provenance` (the table's only INSERT path; 22.5 R2's precedent), whose one `learned_provenance` event per inserted row (`row_event`) is the re-log, after the row's own plain `evidence` append, same `ts`; the same call site serves every evidence row a restore re-inserts LIVE with its sidecar rows (22.6 R3's learned rows); no absorb rule (the purge's `evidence_remove` deleted the old copy and its sidecar rows, live and on replay); counted `restore_sidecar_reinserted` |
| d9ci AC | AC-4e dead-side re-insert sidecar leg (AC-4d's engine-purge shape with a learned row; uncompacted and compacted runs) + mutations "re-insert without re-logging the sidecar" (traced: uncompacted, the original event is undone by the purge's `evidence_remove`; compacted, the dump holds none: 0 against live 1 in both) and "re-log the re-inserted sidecar before the row's append" (`unresolved_provenance` 1); [[#files-to-modify]] `removal_apply.py` row |
| raised, not ruled by d9ci (found while applying it) | the sidecar rows of a row re-inserted DANGLING (the dead-id re-check's step (3); 22.6 R5's vacuum rows, AC-6's sidecar row): the row is catalog-only with no event, but 16.6 R1 makes `add_learned_provenance`, which logs, the table's only INSERT path, so the spec names no way to put the sidecar back as catalog-only too; [[#r4-reinsert-sidecar]] states the rule does not reach them. Needs a ruling |

rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-16.6-learned-row-validation#r1]]
