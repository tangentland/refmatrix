---
gmd: "0.1"
id: task-22.6-removal-entry-points
title: "Task 22.6: the removal entry points (forget, memory forget, memory bulk-forget, untrack, prune-noise --drop) and the bug-107 paths (sync purges, vacuum orphans, unprotect), each manifest-backed as ADR-0004 #a14-removal-scope classifies them"
tags: [task, removal, audit, manifest, bug-107, adr-0004, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
---

# Task 22.6: removal entry points and the bug-107 paths {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (created in revision round 3, 2026-10-14; [[#rev-round-3]])
> Wave: 1, after 22.2 (it needs the engine, the intent-record form and restore); parallel to
> 22.5. R4 (the sync edit fix) needs only 16.6's Wave-1 slice and may land first.
> Depends on: 22.2 (engine, primitives, R4 intent-record form, `removal_restore`), 22.1a
> (`removal_audit` verb, plan manifest), 16.6 Wave-1 slice (sidecar; R1e's interim), 23.1
> (`bind`), 23.2 (recorder), 23.0 (sandbox).

The user approved the ADR-0004 amendment (d9k): knowledge removal goes through plan-22's audited
path, and `forget` / `memory bulk-forget` are ENTRY POINTS to it (they build the manifest and
require the confirm); `untrack` and `prune-noise --drop` are listed exceptions that print what they
remove and write the same manifest form. The user then classified the removal paths that text had
missed (d9o, bug-107): `purge_path` on a deleted or ignored file is derived cleanup with a manifest
(learned rows go to it); sync's GMD legacy purge on a `.md` edit is a bug, fixed to keep learned
rows; `vacuum`'s orphan-evidence delete is derived cleanup with a manifest and a `facts.log` event;
`fold_concept_dups` is a merge, a plan-22 entry point owned with merge writes by the helix plan;
`unprotect` is not removal but writes a `facts.log` event with its source. The r3 re-review found
no task owning any of it (b-3). This is that task.

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]
rel: derives-from -> [[plan-review-2026-10-14#t9-approvals]]
rel: derives-from -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: depends-on -> [[task-22.2-repair-then-remove]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]
rel: related-to -> [[task-22.4-merge-writes]]

## Facts at HEAD (`5a8bf29`, read-only) {#facts}

- `rmx forget` (`cli.py:4567`, `forget_cmd`) previews with `forget_by_selector(dry_run=True)`
  (`store.py:6011`) and deletes on `--yes` or a prompt; it has no MCP surface.
- `rmx memory forget` (`cli.py:12597`) and `rmx memory bulk-forget` (`cli.py:12932`) call the
  verbs `memory_forget` / `memory_bulk_forget` (`verbs.py:1027-1029`, MCP `rmx_memory` actions
  `forget` / `bulk_forget`); `bulk_forget_memories` (`store.py:2878`) deletes memory rows,
  `memory_content` and links.
- `purge_path` (`store.py:5905`) purges every entity whose `path` is the file, whatever
  `protected` says, then logs `untrack`; `purge_entity` (`store.py:5692`) leaves the entity's
  `linkage_evidence` rows behind (no FK, `duckdb_catalog.py:162`).
- Sync (`sync.py:195-245`) calls `purge_path` on an ignored path, on a missing or unsupported
  path, on every changed GMD `.md` whose relpath-named `doc` entity exists, and on EVERY changed
  non-GMD file that existed before ("purge before re-add"). A learned hit is an entity named by
  its relpath with `path` = the absolute file (`daemon.py:4295-4330`), so both edit branches
  purge learned rows. The r3 re-review measured 241 of this repo's 710 learned entities on GMD
  documents and 26 learned entities tombstoned 47 times.
- `vacuum` (`store.py:6943`) step 2 bulk-purges the entities of `tracked_files` paths that no
  longer exist; step 3 deletes every `linkage_evidence` row whose entity is gone, with no event.
- `set_entity_flag` (`store.py:5976`) logs a `protect` (or `noise`) event per row with `kind`,
  `name`, `value`; no source.

## Requirements {#requirements}

1. **R1 Selector entry points: `forget`, `memory forget`, `memory bulk-forget` (d9k).** {#r1}
   - `removal_audit` gains a SELECTOR mode, `rmx removal audit --root R --selector
     forget|memory-forget|memory-bulk-forget <selector args>`. Its members come from the existing
     selection code, run with `dry_run=True` (`forget_by_selector`, the `memory_forget` lookup,
     `bulk_forget_memories`); no second selector implementation exists. Members are class
     `selected:<entry point>`, unit ENTITY, and the plan manifest records the selector verbatim.
   - The three commands become entry points to it, on every surface they have today (CLI; the
     `memory_forget` / `memory_bulk_forget` verbs and so MCP `rmx_memory`):
     - **without `--confirm`**: build the plan, print every member (kind, name, what goes with
       it: links, evidence rows, `memory_content`, tracked files, vector), the manifest id and
       its sha256; write nothing else. Today's `--dry-run` is accepted and means the same.
     - **with `--confirm <sha256>`**: rebuild the plan from the same selector; if its hash differs
       (the selection changed since), refuse and write nothing; else apply it through 22.2's
       engine (`removal_apply`), restorable with `removal_restore`.
     - `--yes`/`-y` and the click confirmation prompt are REMOVED: a flag that deletes without a
       manifest is the second path the ADR forbids. Passing `--yes` exits 2 naming `--confirm`.
   - A selector member is removed whole (entity, links, evidence, sidecar rows, `memory_content`,
     `tracked_files`, vector), through `_bulk_purge_ids` / `bulk_forget_memories`' delete, inside
     22.2's batch loop, with 22.2 R4's intent record holding every row first (22.2 R2's selector
     exception).
2. **R2 Listed exceptions: `untrack` and `prune-noise --drop` (d9k).** {#r2} Neither routes
   through `--confirm` (the ADR lists them as exceptions), but each writes the same manifest form
   BEFORE it changes anything: `.refmatrix/removal/<id>.cleanup.jsonl` holding 22.2 R4's intent
   records for every row it removes, then prints the manifest id, the counts per row kind, and
   `rmx removal restore --manifest <id>` as the way back. `removal_restore` accepts a cleanup
   manifest exactly as it accepts an apply manifest. Neither is ever run by a timer or a counter.
3. **R3 Deleted or ignored file: derived cleanup with a manifest (d9o).** {#r3} `purge_path` for
   a path that no longer exists or that is now ignored (sync's two branches, and `vacuum` step 2's
   dead tracked paths) first writes a cleanup manifest (R2's form) holding every LEARNED row under
   that path: each learned evidence row with its sidecar rows, the `query/*` `mentions` links, and
   any learned-only entity whole (with `protected` and its source). The learned rows are then
   removed through 22.2's row-level primitives (`remove_evidence` with `keep=0`, then the entity
   rule of 22.2 R2), so each removal has its `evidence_remove` event and the sidecar rows leave in
   the same transaction. Ingest-derived rows are purged as today. Restorable with
   `removal_restore`.
4. **R4 Sync's edit purges keep learned rows: bug-107 fixed (d9o).** {#r4} Both edit branches of
   sync (the GMD dispatch's legacy purge of the relpath-named `doc` entity, and the non-GMD
   "purge before re-add") call `purge_path(abs, keep_learned=True)`, which purges what ingest
   derived from the file (per-function entities, ingest links, ingest evidence) and KEEPS: every
   evidence row whose `detail` begins `learned from grep`, its sidecar rows, the `query/*`
   `mentions` links those rows hang on, the file entity they sit on (same id, so the sidecar key is
   unchanged), and its `protected` flag. The kept rows are not re-verified here: their lines may
   have shifted, and 16.6's verifier and 22.1's set rule judge them (d9o). No tombstone is logged
   for the kept entity; the purged ingest rows log their events as today, so a rebuild agrees with
   the live store. The d9o text names only the GMD purge; the non-GMD "purge before re-add" is the
   same act on a learned row (an edit is not a deletion), so it gets the same rule; the revision
   report names this for the orchestrator to record on bug-107.
5. **R5 `vacuum`'s orphan-evidence delete: manifest plus `facts.log` event (d9o).** {#r5}
   - Step 3 first writes a cleanup manifest (R2's form) of every `linkage_evidence` row whose
     entity is gone, with the sidecar rows of each identity, then deletes them, and logs one
     `evidence_orphan_drop{linkage, c, dead_entity_id, file, line, detail, n, manifest}` event per
     identity (`linkage` and `c` by NAME; the entity has no name left, so its dead id and the
     manifest id are recorded instead).
   - Replay applies it inside the ONE post-evidence pass ([[task-22.2-repair-then-remove#r3]],
     [[task-16.6-learned-row-validation#r1d]]): it deletes rows matching `(linkage, c, file, line,
     detail)` whose entity does not exist at that point; a match on a live entity is never
     deleted, it is counted `orphan_drop_skipped_live`.
   - After R3 and R4, learned rows stop becoming orphans on sync; step 3 drains the legacy ones
     and anything a non-plan-22 purge still leaves. Each drop is counted and printed by `vacuum`.
6. **R6 `unprotect` writes its source (d9o).** {#r6} Every `protect` event, value `true` or
   `false`, carries `source`: `upsert` (`upsert_entity(protected=True)`), `user`
   (`set_entity_flag` / `set_flag_by_selector` from the CLI or MCP), or `removal` (plan-22's
   engine, apply or restore). It is the field 22.2 R5 defines for protections, extended to the
   unprotect direction. Replay ignores it; 22.2 R5's attribution reads it where present and falls
   back to its log-adjacency rule for older events.
7. **R7 `fold_concept_dups` is not built here (d9o).** {#r7} It is a merge, an entry point to
   plan-22 owned with merge writes by the future helix plan: it travels with 22.4's hand-over
   ([[task-22.4-merge-writes#root]], d9j). Until then `rmx fold-concept-dups` is unchanged and
   is listed by `rmx removal audit --list` as an unrouted merge path, so it is visible, not
   forgotten.
8. **R8 No silent failures.** {#r8} Every entry point prints its counts per row kind; a manifest
   write failure aborts the removal before any row changes (the manifest is written first); every
   skipped row is counted with its reason.

## Acceptance criteria {#acceptance}

1. **forget needs the confirm.** On a sandbox store, `rmx forget 'query/x'` writes only a plan
   manifest and prints its hash; the catalog hash, Lance versions and `facts.log` are unchanged.
   `--confirm <that hash>` removes the entity; `--confirm` with a hash taken before a second
   matching entity was added refuses and writes nothing; `--yes` exits 2. Mutation "keep `--yes`
   as a direct delete" FAILS it.
2. **bulk-forget restores bodies.** `memory bulk-forget --mtype observation --confirm <hash>` on
   three memories, then `removal restore`, returns all three by NAME with equal `memory_content`
   (`content`, `mtype`, `tags`, `metadata`), links and vectors (22.2 AC-4's comparison). The same
   holds through the MCP `rmx_memory` action. Mutation "intent record without `memory_content`"
   FAILS it.
3. **untrack and prune-noise --drop write the manifest first.** Each, on a sandbox store, writes a
   `.cleanup.jsonl` manifest before any row changes, prints its id, and `removal restore` of it
   returns every removed row by name. Mutation "write the manifest after the delete" FAILS it (a
   crash injected between delete and manifest leaves rows unrecoverable).
4. **Deleted file: learned rows to the manifest (R3).** A file with a learned row (and its
   sidecar row) and an ingested symbol is deleted, then synced: the cleanup manifest holds the
   learned row and its sidecar row; `facts.log` holds its `evidence_remove` event;
   `rebuild_index_from_log` on a sandbox copy agrees with the live store on learned rows; restore
   returns the learned row and sidecar row. Mutation "plain `purge_path`" FAILS it (no manifest
   row; the sidecar row orphaned).
5. **Edit keeps learned rows (R4, bug-107).** A GMD `.md` and a `.py` file, each with a learned row
   and a sidecar row, are edited (a line inserted above the hit) and synced: each file entity
   keeps its id, its learned evidence row, its `query/*` `mentions` link, its sidecar row and its
   `protected` flag; its ingest rows are re-derived; a rebuild on a sandbox copy agrees. Then
   22.1's audit classifies the shifted row `moved`, never removed. Mutations "plain `purge_path`
   in the GMD branch" and "plain `purge_path` in the non-GMD branch" each FAIL it.
6. **vacuum drop is logged and replayable (R5).** A store holding two orphaned learned evidence
   rows (one with a sidecar row) is vacuumed: the cleanup manifest holds both rows and the sidecar
   row; `facts.log` holds two `evidence_orphan_drop` events; a rebuild on a sandbox copy agrees
   (no orphan resurrected); an `evidence_orphan_drop` replayed against a LIVE entity's matching
   row deletes nothing and counts `orphan_drop_skipped_live`. Mutation "delete without an event"
   FAILS the rebuild clause.
7. **unprotect source (R6).** `rmx unprotect X` logs a `protect` event with `value=false,
   source=user`; a 22.2 restore that re-protects logs `source=removal`. Mutation "no source on
   value=false" FAILS it.
8. **The fold path is visible (R7).** `rmx removal audit --list` on a store prints
   `fold-concept-dups` as an unrouted merge path.

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): redirected `$HOME`/global root/registry/
LaunchAgents before import, in-process `Daemon` + `Store` on a short `mkdtemp`, the 23.2 recorder
required, no `rmx` subprocess against a live root, the 23.0 guard active. CLI tests drive the click
commands in-process against the sandbox daemon. Crashes are injected between steps. Every listed
mutation is pre-registered and must turn its test RED.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/removal_audit.py` (22.1a's module, which holds `classify_provenance_free`) | selector mode of `removal_audit`; cleanup-manifest writer (R2's form, shared with 22.2 R4) |
| `src/refmatrix/cli.py` | `forget`, `memory forget`, `memory bulk-forget`: plan without `--confirm`, apply with it, `--yes` refused; `untrack`, `prune-noise --drop`: manifest first |
| `src/refmatrix/verbs.py` | `memory_forget`, `memory_bulk_forget`: the same plan/confirm contract (MCP parity) |
| `src/refmatrix/store.py` | `purge_path(..., keep_learned=)`; R3 manifest + row-level removal of learned rows; `vacuum` steps 2-3 manifest + `evidence_orphan_drop`; `protect` events carry `source`; replay of `evidence_orphan_drop` in the one pass |
| `src/refmatrix/sync.py` | both edit branches call `purge_path(..., keep_learned=True)` |
| `tests/test_removal_entry_points.py` (new) | AC-1..AC-8 |

## Revision round 3 (2026-10-14) {#rev-round-3}

Created to answer [[bsd-plan16-22-spec-rereview-r3-6091648]] b-3 and s-5, and decisions d9k and
d9o ([[plan-review-2026-10-14#t9-approvals]]).

| finding / decision | answered in |
|---|---|
| r3 b-3 / d9k (`forget`, `memory bulk-forget` are entry points; no task owned them) | [[#r1]]; AC-1, AC-2 |
| r3 b-3 (owner of the `untrack` / `prune-noise --drop` manifest form) | [[#r2]]; AC-3 |
| d9o `purge_path` deleted/ignored = derived cleanup with manifest | [[#r3]]; AC-4 |
| d9o sync GMD legacy purge = bug, keep learned rows (bug-107) | [[#r4]] (and the non-GMD edit purge, same act); AC-5 |
| d9o `vacuum` orphan evidence = manifest + `facts.log` event | [[#r5]]; AC-6 |
| d9o `unprotect` = event with source | [[#r6]]; AC-7 |
| d9o `fold_concept_dups` = merge entry point, helix plan | [[#r7]]; 22.4's hand-over; AC-8 |
| r3 s-5 (sidecar orphaned silently by purges) | [[#r3]], [[#r5]]; 16.6 R1e's interim |
