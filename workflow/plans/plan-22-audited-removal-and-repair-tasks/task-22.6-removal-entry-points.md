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
> Status: Pending (created in revision round 3, 2026-10-14; revised in round 5, [[#rev-round-5]])
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

## Facts at HEAD (`5a8bf29`, read-only; re-read at `7f2014a` below) {#facts}

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

**Re-read at `7f2014a` (round 5; `src/` unchanged since `b1c4324`):**
- Sync's branches: ignored path `sync.py:203`; `not ap.exists() or not is_supported`
  `sync.py:209` (it also purges files that EXIST with an unsupported extension; the learner gives
  `kind="doc"` to every non-code hit, `daemon.py:4322`); the GMD legacy purge guard
  `sync.py:231`; the non-GMD purge-before-re-add `sync.py:241`.
- `rmx ingest`'s twin of the GMD legacy purge: `ingest.py:1179-1180`.
- `rmx sync --invalidate P`: `purge_path` on every named path, existing or not
  (`cli.py:8433-8434`).
- `ingest_gmd --as-memory`: a raw `DELETE FROM entities ... kind='doc'` (`ingest_gmd.py:891-896`),
  no tombstone, links and evidence left behind.
- `merge_partition` (`store.py:1606`): deletes source `memory_content` (`:1765`) and source
  entities (`:1812`).
- Daemon ops that delete on the socket today: `prune_noise` (`daemon.py:3899`), `forget`
  (`:4384`), `untrack` (`:4398`), `memory_forget` (`:5061`), `memory_bulk_forget` (`:5117`).
- CLI: `forget` `cli.py:4567`, `untrack` `:4607`, `prune-noise` `:7769`, `memory forget`
  `:12597` (its `@click.confirmation_option` at `:12599` IS its `--yes`; the daemon-down
  fallback `s = _store(); s.forget_memory(...)` at `:12616-12618`), `memory dedup` `:12628`
  (`fold_concept_dups`, `store.py:5808`; MCP `rmx_memory` action `dedup`, `verbs.py:1029`),
  `memory bulk-forget` `:12932`.
- The compactor: `Daemon._compact_factslog_if_needed` (`daemon.py:2274`) calls
  `Store.dump_catalog_to_log` (`store.py:7210`), which REPLACES `facts.log` with a snapshot of
  `linkage_type`, `entity`, `protect`, `noise`, `memory_content`, `link`, `evidence` and `track`
  events; each `protect` follows its own `entity` (`store.py:7279-7285`) and carries no `source`.
  This repo's log was compacted at 14:00:44 today.

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
     - **The confirm hash is the SELECTION, not the plan file (r4 s-4).** It is the sha256 of the
       canonical JSON (`sort_keys`, `separators=(",",":")`) of `{entry_point, selector,
       members}`, where `selector` is the selector arguments verbatim and `members` is the list,
       sorted by `(partition, kind, name)`, of each member's `(partition, kind, name)` and its row
       counts (links, evidence rows, sidecar rows, `memory_content` 0/1, `tracked_files` rows,
       vector 0/1). It holds NO catalog identity, snapshot version, timestamp, manifest id or
       path. So an unrelated write between plan and confirm (a sync, a learn, an STM promote, a
       snapshot rotation) does not refuse; a write that changes WHAT would be removed does.
       The plan file records this hash beside 22.1a R4's catalog identity, which is informational
       here.
     - `--yes`/`-y` and the click confirmation prompt are REMOVED: a flag that deletes without a
       manifest is the second path the ADR forbids. Passing `--yes` exits 2 naming `--confirm`.
     - **Below the CLI (r4 s-4).** The daemon ops `forget` (`daemon.py:4384`), `memory_forget`
       (`:5061`) and `memory_bulk_forget` (`:5117`) stop deleting on `dry_run=false`: they accept
       either `dry_run=true` (the selection preview, unchanged) or a `{manifest, confirm}` pair
       they hand to `removal_apply`; any other call is refused with an error naming
       `rmx removal`. `untrack` (`:4398`) and `prune_noise` (`:3899`) write R2's cleanup manifest
       inside the op before any delete, so a raw socket call gets the same manifest as the CLI.
     - **No daemon-down fallback.** `rmx memory forget`'s `s = _store(); s.forget_memory(...)`
       (`cli.py:12616-12618`) is removed: with the daemon down the command exits nonzero naming
       the daemon, as every other write does (`feedback_store_calls_via_daemon`).
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
3. **R3 Missing or ignored file: derived cleanup with a manifest (d9o).** {#r3} `purge_path` for
   a path that no longer EXISTS or that is now IGNORED (sync's `should_ignore` branch,
   `sync.py:203`; the MISSING half of `sync.py:209`; `vacuum` step 2's dead tracked paths) first
   writes a cleanup manifest (R2's form) holding every LEARNED row under
   that path: each learned evidence row with its sidecar rows, the `query/*` `mentions` links, and
   any learned-only entity whole (with `protected` and its source). The learned rows are then
   removed through 22.2's row-level primitives (`remove_evidence` with `keep=0`, then the entity
   rule of 22.2 R2), so each removal has its `evidence_remove` event and the sidecar rows leave in
   the same transaction. Ingest-derived rows are purged as today. Restorable with
   `removal_restore`.
   - **An existing file with an unsupported extension is NOT this branch (r4 s-2).** Today
     `sync.py:209` treats `not ap.exists() or not is_supported` alike. The learner teaches any
     non-code hit as `kind="doc"` (`daemon.py:4322`), so 100 of this repo's 706 learned entities
     sit on unsupported extensions (`.log` 70, `.json` 14, none 7; r4 count). The branch splits:
     a MISSING file is R3; an EXISTING unsupported file keeps its learned rows exactly as R4
     keeps them (ingest-derived rows, if any, are purged), because an edit, or no edit, is not a
     deletion (d9p).
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
   same act on a learned row (an edit is not a deletion), so it gets the same rule (d9p).
   - **The two branches are NOT the same call (r4 s-1).**
     - **Non-GMD** (`sync.py:241`; the EXISTING-unsupported half of `sync.py:209`, R3): the
       learner's relpath entity IS the file entity sync re-adds (both `upsert_entity(kind,
       name=rel, path=abs)`), so `purge_path(abs, keep_learned=True)` is right there: it purges
       the per-function entities and the ingest rows, keeps the file entity (same id) and its
       learned rows.
     - **GMD** (`sync.py:231`, and its twin on the `rmx ingest` path, `ingest.py:1179-1180`):
       `purge_path` is NEVER called. Every entity the GMD pass owns at that path (the doc-id
       `doc` entity and every `{#anchor}` `concept`, all with `path=str(path)`,
       `ingest_gmd.py:964-967`, `:1015-1018`) is left alone: `purge_entity` would unlink their
       inbound `rel:` edges from OTHER docs, which re-ingesting this doc does not re-create. The
       branch instead calls `Store.purge_legacy_relpath_doc(rel, abs)`, which touches ONLY the
       relpath-named `doc` entity: it deletes that entity's non-learned links and evidence (with
       their events), and then purges the entity itself (tombstoned) only if no learned row is
       left on it; a learned relpath entity is kept with its id, learned rows, sidecar rows,
       `query/*` links and `protected` flag.
     - **The guard (r4 s-1).** The GMD guard (`sync.py:231`, `ingest.py:1179`) fires only when
       the relpath-named `doc` entity carries at least one non-learned row (an ingest link, an
       ingest evidence row, or a `tracked_files` row at its path for the legacy tree pass). A
       relpath entity whose rows are all learned does not fire it, so a learned GMD doc costs no
       purge on every later edit (this repo has 241 such docs, r3).
   - **`rmx sync --invalidate P` is a re-ingest (r4 s-2).** `cli.py:8433-8434` calls
     `purge_path` on every named path; it becomes: an EXISTING path is re-ingested under this
     requirement's rules (learned rows kept), a MISSING path goes to R3 (manifest).
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
6. **R6 Every protection records its source, and the compactor keeps it (d9o, d9ab; r4 b-2).**
   {#r6}
   - **The field.** Every `protect` event, value `true` or `false`, carries `source`, set by the
     CALLER, never inferred:
     - `learner`: only `_learn_grep_hits` (`daemon.py:4295`, its `add_concept` and
       `upsert_entity(protected=True)` calls);
     - `user`: a CLI or MCP command (`rmx protect` / `unprotect` through `set_flag_by_selector`,
       `store.py:6003`; `rmx add-entity` / `add-concept` and their MCP tools; `link --protect`;
       `memory add` with protect);
     - `system`: other internal protected writes (compiled subjects, `store.py:2633`);
     - `removal`: plan-22's engine, apply or restore.
     `upsert_entity`, `add_concept`, `link` and `set_entity_flag` take a keyword
     `protect_source`; a protected write without one logs no `source`, and that protection is
     user-asserted (22.2 R5): the safe default.
   - **Persisted.** A nullable `entities.protect_source` column, added by `Store.init`'s existing
     additive-column migration (`store.py:1230-1310`, beside `vectors_partition`), holds the
     source of the protection in force (NULL = unattributed). Live writes set it; replay sets it
     from each `protect` event's `source` (NULL when absent); unprotect clears it.
   - **The compactor keeps it (d9ab companion 1).** `dump_catalog_to_log` (`store.py:7210`)
     emits `source` = `protect_source` on every `protect` event it writes (`store.py:7279-7285`),
     omitting the key when NULL. Without this the field lasts only until the next periodic
     compaction (`daemon.py:2274`; this repo compacted three times on 2026-10-14).
   - **The rule for every new event field or table plans 16 and 22 add:** it has a
     `dump_catalog_to_log` clause and a compact-then-rebuild AC. 16.6 R1d does this for
     `learned_provenance` ([[task-16.6-learned-row-validation#r1d]]); 22.2's row-level ops change
     state the dump already captures (an `evidence_remove` leaves no row to emit).
   - Replay ignores `source` for the flag value. 22.2 R5's attribution reads `protect_source`
     and `cli.log` command records only; the log-adjacency rule is withdrawn (d9ab).
7. **R7 Merge entry points are not built here (d9o, d9ac).** {#r7} Two paths are MERGES, entry
   points to plan-22 owned with merge writes by the future helix plan; both travel with 22.4's
   hand-over ([[task-22.4-merge-writes#r5]], d9j):
   - `fold_concept_dups` (`store.py:5808`), surfaced as `rmx memory dedup` (`cli.py:12628`) and
     MCP `rmx_memory` action `dedup` (`verbs.py:1029`) (r4 m-6: there is no
     `rmx fold-concept-dups`);
   - `merge_partition` (`store.py:1606`; it deletes source `memory_content`, `:1765`, and source
     entities, `:1812`). Its dropped fragment bits go to a manifest through the bug-105 hotfix
     (read-only in `/Volumes/littlebig/refmatrix-bug105`, branch `bug-105-fragment-partition`,
     `fb285cc`: `merge_partition` runs `repair_fragments(..., manifest_dir=<root>/backups)`, which
     writes `fragments-repair-<stamp>-<kind>.jsonl`). This task builds on that code once the
     hotfix is MERGED TO MASTER, as existing code; it plans no second copy of it (d9ac).
   Until then both are unchanged, and `rmx removal audit --list` prints each as an unrouted
   merge path (`memory dedup`, `merge-partition`), so they are visible, not forgotten.
8. **R8 No silent failures.** {#r8} Every entry point prints its counts per row kind; a manifest
   write failure aborts the removal before any row changes (the manifest is written first); every
   skipped row is counted with its reason.
9. **R9 Every other removal path, classified (r4 s-2, d9ac).** {#r9} With R1-R7 and plan-22
   [[plan-22-audited-removal-and-repair#scope]], these are the remaining paths, each with its
   class:

   | path (at `7f2014a`) | class | rule |
   |---|---|---|
   | `ingest.py:1179-1180` (the `rmx ingest` twin of sync's GMD legacy purge) | re-ingest, a bug-107 twin | R4's GMD branch and guard, unchanged in every other respect |
   | `rmx sync --invalidate P` (`cli.py:8433-8434`) | re-ingest | R4 for an existing path (learned rows kept); R3 for a missing one |
   | sync's `not ap.exists() or not is_supported` (`sync.py:209`) | split | missing → R3 (manifest); existing-unsupported → keeps learned rows (R3's sub-bullet, R4's rule) |
   | `ingest_gmd --as-memory`'s raw `DELETE FROM entities ... kind='doc'` (`ingest_gmd.py:891-896`) | derived conversion (doc → memory for the same file) | becomes `purge_entity` (tombstoned, links and evidence unlinked with their events, so a rebuild cannot resurrect the row); any learned row on that entity first goes to an R2-form cleanup manifest |
   | `merge_partition` (`store.py:1606`) | merge entry point, helix plan (d9ac) | R7 |
   | `fold_concept_dups` (`store.py:5808`) | merge entry point, helix plan (d9o) | R7 |

## Acceptance criteria {#acceptance}

1. **forget needs the confirm.** On a sandbox store, `rmx forget 'query/x'` writes only a plan
   manifest and prints its hash; the catalog hash, Lance versions and `facts.log` are unchanged.
   `--confirm <that hash>` removes the entity; `--confirm` with a hash taken before a second
   matching entity was added refuses and writes nothing; `--yes` exits 2. Mutation "keep `--yes`
   as a direct delete" FAILS it.

   **1b. An unrelated write does not refuse (r4 s-4).** Between plan and `--confirm`, the test
   syncs an unrelated file, teaches an unrelated `query/y`, and rotates the read snapshot: the
   confirm applies. Mutation "hash the whole plan file (catalog identity included)" FAILS it.

   **1c. No removal below the CLI (r4 s-4).** A raw `forget` op with `dry_run=false` and no
   confirmed manifest, and the same for `memory_forget` and `memory_bulk_forget`, is refused and
   writes nothing (catalog hash and `facts.log` unchanged); a raw `untrack` op writes its cleanup
   manifest before any row changes. With the daemon stopped, `rmx memory forget X` exits nonzero
   and opens no `Store()` (the 23.0 audit hook records no catalog open). Mutations "keep the
   direct-delete `forget` op" and "keep the `_store()` fallback" each FAIL it.
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
   `protected` flag; its ingest rows are re-derived; a rebuild on a sandbox copy agrees. No
   `evidence_remove` or `tombstone` event is logged for the kept rows, and 16.6's
   `learned_verify.matching_lines` on each edited file holds the hit's shifted line, so 22.1's
   set rule (Wave 2; its AC-5c) will re-point it (r4 m-5: this AC needs nothing from Wave 2).
   Mutations "plain `purge_path` in the GMD branch" and "plain `purge_path` in the non-GMD branch"
   each FAIL it.

   **5b. A GMD edit keeps the doc graph (r4 s-1).** Two GMD docs, A and B, where B has a `rel:`
   edge to an anchor of A, and A also carries a learned relpath row. A is edited and synced
   (and, separately, re-ingested with `rmx ingest`): A's doc-id entity id and every anchor id are
   unchanged, B's inbound `rel:` edge to A's anchor survives, and A's learned relpath entity keeps
   its id. A second edit of A logs no purge of the relpath entity (the guard does not fire on an
   all-learned relpath entity). Mutations "`purge_path(abs, keep_learned=True)` in the GMD branch"
   (anchor ids change, B's edge is lost) and "guard fires on any relpath entity" each FAIL it.

   **5c. Existing unsupported file and `--invalidate` (r4 s-2).** A learned row on an existing
   `x.log` survives a sync of `x.log`; `rmx sync --invalidate a.py` on an existing `a.py` keeps
   its learned row; `--invalidate` on a deleted path writes R3's manifest. Mutation "existing
   unsupported file → plain `purge_path`" FAILS it.
6. **vacuum drop is logged and replayable (R5).** A store holding two orphaned learned evidence
   rows (one with a sidecar row) is vacuumed: the cleanup manifest holds both rows and the sidecar
   row; `facts.log` holds two `evidence_orphan_drop` events; a rebuild on a sandbox copy agrees
   (no orphan resurrected); an `evidence_orphan_drop` replayed against a LIVE entity's matching
   row deletes nothing and counts `orphan_drop_skipped_live`. Mutation "delete without an event"
   FAILS the rebuild clause.
7. **unprotect source (R6).** `rmx unprotect X` logs a `protect` event with `value=false,
   source=user`; a 22.2 restore that re-protects logs `source=removal`; a learn logs
   `source=learner`. Mutation "no source on value=false" FAILS it.

   **7b. The source survives compaction (r4 b-2, d9ab).** Protect L through `_learn_grep_hits`
   and U through `rmx protect U`; run `dump_catalog_to_log` (the compactor, `daemon.py:2274`'s
   call), then `rebuild_index_from_log` on a sandbox copy: `entities.protect_source` is
   `learner` for L and `user` for U, and the compacted log's two `protect` events carry those
   `source` values. Mutation "dump without `source`" FAILS it (both NULL after the rebuild, so
   22.2 R5 reads L as user-asserted).
8. **The merge paths are visible (R7; r4 m-6; d9ac).** `rmx removal audit --list` on a store
   prints `memory dedup` (MCP `rmx_memory` `dedup`) and `merge-partition` as unrouted merge paths.
9. **The remaining paths (R9).** The `ingest_gmd --as-memory` conversion of a doc that has a
   learned row writes a cleanup manifest holding it and logs a `tombstone` for the doc entity; a
   rebuild on a sandbox copy does not resurrect the doc entity. Mutation "keep the raw DELETE"
   FAILS it.

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
| `src/refmatrix/sync.py` | non-GMD edit and existing-unsupported branches call `purge_path(..., keep_learned=True)`; the GMD branch calls `purge_legacy_relpath_doc` behind the narrowed guard (R4) |
| `src/refmatrix/ingest.py` | the GMD legacy purge twin (`:1179-1180`): R4's GMD rule and guard |
| `src/refmatrix/ingest_gmd.py` | `--as-memory`: the raw DELETE becomes `purge_entity` with an R2-form manifest for learned rows (R9) |
| `src/refmatrix/daemon.py` | `forget` / `memory_forget` / `memory_bulk_forget` ops: preview or confirmed manifest only; `untrack` / `prune_noise` ops write the manifest first (R1, R2); `_learn_grep_hits` passes `protect_source='learner'` (R6) |
| `src/refmatrix/cli.py` (also) | `sync --invalidate` as a re-ingest (R4); `memory forget` without the `_store()` fallback (R1) |
| `src/refmatrix/store.py` (also) | `entities.protect_source` column + `protect_source` keyword on the protect writers; `dump_catalog_to_log` emits `source` (R6); `purge_legacy_relpath_doc` (R4) |
| `tests/test_removal_entry_points.py` (new) | AC-1..AC-9 |
| `tests/test_learned_evidence.py` (16.6's) | 16.6 AC-11's test is REWRITTEN by this task (r4 m-5): from R3/R5 on, `purge_path` of a missing file and `vacuum` move the sidecar row into a manifest (AC-4, AC-6) instead of leaving it; AC-11 keeps only its `orphaned_provenance` count for paths this task does not route |

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

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan16-22-spec-rereview-r4-878647c]] and d9ab/d9ac
([[plan-review-2026-10-14#t11-approvals]]). Later rows win over round 3.

| finding / decision | answered in |
|---|---|
| r4 b-2 / d9ab (compaction drops `source`; adjacency attributes every protection) | [[#r6]]: caller-set `source` (`learner` only from `_learn_grep_hits`), persisted in `entities.protect_source`, emitted by `dump_catalog_to_log`; the "new field ⇒ dump clause + compact-then-rebuild AC" rule; AC-7b + mutation; 22.2 R5 |
| r4 s-1 (GMD branch purges the doc-id entity, anchors and inbound `rel:` edges on every edit) | [[#r4]] "The two branches are NOT the same call": GMD branch never calls `purge_path`; `purge_legacy_relpath_doc`; narrowed guard; AC-5b + two mutations |
| r4 s-2 / d9ac (unclassified removal paths) | [[#r9]] table (`ingest.py:1179-1180`, `sync --invalidate`, `sync.py:209` split, `ingest_gmd.py:891-896`); [[#r3]] "missing or ignored"; [[#r4]] `--invalidate`; [[#r7]] `merge_partition` (helix merge entry point, d9ac); AC-5c, AC-8, AC-9 |
| r4 s-4 (confirm hash vs live writes; daemon ops stay direct-delete; daemon-down fallback) | [[#r1]] selection hash, "Below the CLI", "No daemon-down fallback"; AC-1b, AC-1c + mutations; `daemon.py` in [[#files-to-modify]] |
| r4 m-5 (AC-5 needs Wave 2; 16.6 AC-11 will start failing) | AC-5 uses 16.6's `matching_lines`, not 22.1; [[#files-to-modify]] rewrites 16.6 AC-11's test; [[task-16.6-learned-row-validation#acceptance]] AC-11 scoped |
| r4 m-6 (`rmx fold-concept-dups` does not exist) | [[#r7]], AC-8: `rmx memory dedup` / MCP `rmx_memory` `dedup` |
| r3 s-5 (partial: sync and vacuum remove learned rows) | closed by the s-1 and s-2 rows |
| line numbers | [[#facts]] re-read at `7f2014a` |

rel: amends -> [[bsd-plan16-22-spec-rereview-r4-878647c]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]
