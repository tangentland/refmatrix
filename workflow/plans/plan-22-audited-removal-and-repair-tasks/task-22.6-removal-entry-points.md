---
gmd: "0.1"
id: task-22.6-removal-entry-points
title: "Task 22.6: the removal entry points (forget, memory forget, memory bulk-forget, untrack, prune-noise --drop) and the bug-107 paths (sync purges, vacuum orphans, unprotect), each manifest-backed as ADR-0004 #a14-removal-scope classifies them"
tags: [task, removal, audit, manifest, bug-107, adr-0004, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-15
---

# Task 22.6: removal entry points and the bug-107 paths {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (created in revision round 3, 2026-10-14; revised in round 5, [[#rev-round-5]],
> round 6, 2026-10-15, [[#rev-round-6]], round 7, 2026-10-15, [[#rev-round-7]], round 8,
> 2026-10-15, [[#rev-round-8]], and round 9, 2026-10-15, [[#rev-round-9]])
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

**Re-read at `3d3c798` (round 6, r6 m-6; 0.78.1 merged bug-111 and bug-105).** The line numbers
above are pinned to their shas; the requirements below cite by SYMBOL.
- `ingest_gmd --as-memory` (the `as_memory` branch of `ingest_gmd.ingest_gmd_paths`) no longer
  runs a raw DELETE: it calls `store.purge_entity` for each `doc` entity matched on name AND path
  (bug-111 r1 #4). So it tombstones, unlinks the links with their events and clears every
  partition's bits; what is left for R9 is the learned-row manifest.
- `Store.purge_entity` and `Store._bulk_purge_ids` delete NO `linkage_evidence` row, on either
  side; `Store.vacuum` step 3 deletes only rows whose ENTITY is gone (r6 `#ev-evidence-orphans`:
  14,745 cliquedb and 5,920 refmatrix rows with a live entity and a dead concept).
- `merge_partition`: the bug-105 hotfix is merged (0.78.0); `daemon._op_partition_merge` now
  refuses a LIVE merge (`dry_run=True` preview only; d9ae), and `rmx partition merge` runs
  `Store.merge_partition` offline.
- Moved since `7f2014a` (read at `3d3c798`): `dump_catalog_to_log` (`store.py:7527`),
  `_bulk_purge_ids` (`:6363`), `vacuum` (`:7260`), `set_flag_by_selector` (`:6286`),
  `purge_entity` (`:5990`), `Daemon._compact_factslog_if_needed` (`daemon.py:2307`),
  `_learn_grep_hits` (`daemon.py:4237`).

**Re-read at `23ad703` (round 8, r8 m-5; 0.78.3 merged bug-117).** Every edge event (`link`,
`unlink`, `evidence`) now carries `c_kind`, written through `edge_records.edge_fields` /
`edge_event`, including `purge_entity`'s unlinks and `dump_catalog_to_log`'s events; the rebuild
resolves a concept end by `(c_kind, c)` and a legacy one by `edge_records.resolve_legacy_kind`
(Pass 2b), so doc and memory concept ends replay. Moved since `3d3c798`: `dump_catalog_to_log`
(`store.py:7526`), `_bulk_purge_ids` (`:6362`), `vacuum` (`:7259`), `set_flag_by_selector`
(`:6285`), `purge_entity` (`:5989`), `purge_path` (`:6187`),
`Daemon._compact_factslog_if_needed` (`daemon.py:2341`), `_learn_grep_hits` (`daemon.py:4322`).
The requirements cite by symbol; `purge_entity` and `_bulk_purge_ids` still delete no
`linkage_evidence` row, and `vacuum` step 3 still deletes rows whose ENTITY is gone.

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
     - **Below the CLI (r4 s-4).** The daemon ops `forget` (`daemon._op_forget`), `memory_forget`
       (`_op_memory_forget`) and `memory_bulk_forget` (`_op_memory_bulk_forget`) stop deleting on `dry_run=false`: they accept
       either `dry_run=true` (the selection preview, unchanged) or a `{manifest, confirm}` pair
       they hand to `removal_apply`; any other call is refused with an error naming
       `rmx removal`. `untrack` (`_op_untrack`) and `prune_noise` (`_op_prune_noise`) write R2's cleanup manifest
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
   - **A file that comes back (r7 b-1, d9av).** A branch switch deletes a file and re-creates it,
     and the next grep re-learns the identical row. Replay applies `evidence` appends and row ops
     together in timestamp order ([[task-22.2-repair-then-remove#r3]]), so this R3's
     `evidence_remove` at `T1` deletes on a rebuild only the copies appended at or before `T1`;
     the re-learned row (appended at `T2`) and its `learned_provenance` survive, as they do live
     (AC-4).
   - **An existing file with an unsupported extension is NOT this branch (r4 s-2).** Today
     `sync.py:209` treats `not ap.exists() or not is_supported` alike. The learner teaches any
     non-code hit as `kind="doc"` (`daemon._learn_grep_hits`), so 100 of this repo's 706 learned entities
     sit on unsupported extensions (`.log` 70, `.json` 14, none 7; r4 count). The branch splits:
     a MISSING file is R3; an EXISTING unsupported file keeps its learned rows exactly as R4
     keeps them (ingest-derived rows, if any, are purged), because an edit, or no edit, is not a
     deletion (d9p).
4. **R4 Sync's edit purges keep learned rows: bug-107 fixed (d9o).** {#r4} Both edit branches of
   sync keep learned rows, through two DIFFERENT calls (r6 m-5): the non-GMD "purge before
   re-add" calls `purge_path(abs, keep_learned=True)`, and the GMD dispatch's legacy purge of the
   relpath-named `doc` entity calls `Store.purge_legacy_relpath_doc(rel, abs)` and never
   `purge_path` (the sub-bullet below). `purge_path(abs, keep_learned=True)` purges what ingest
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
     `evidence_orphan_drop{linkage, c_kind, c, e_kind: null, e: null, file, line, detail,
     dead_entity_id, n, manifest}` event per identity, built by 16.6's
     `edge_records.row_event` with `c_kind` (this task adds the op to `edge_records.ROW_OPS`;
     [[task-16.6-learned-row-validation#r1d-one-format]], d9bl; r8 b-1). `linkage` and the
     concept end are by NAME; the entity has no name left, so its end is null and its dead id and
     the manifest id are recorded instead. The concept end is keyed by exactly one of two rules,
     by whether the concept is alive (r9 s-1):
     - **Live concept.** Its kind(s) come from 22.2's one helper `Store._row_op_c_kinds`, one
       event per returned pair, carrying the pair's `c_kind` and no `keep` (the drop deletes
       every matching copy whose entity was dead at `T`, [[#r5-timeline]]; no live entity holds
       a copy of an orphan, so the helper's `concept` pair always has `n = 0`;
       [[task-22.2-repair-then-remove#r3]]). `_row_op_c_kinds` is called ONLY for a live
       concept.
     - **Both ends dead (r9 s-1).** {#r5-both-dead} An orphan whose CONCEPT id is dead too has
       no catalog name and no catalog kind (cliquedb: 5,341 of its 7,599 vacuum orphans;
       refmatrix r6 copy: 2,679). It is named by 22.1a's dead-id naming
       ([[task-22.1a-provenance-free-classes#r1-dangling]], covering per
       [[task-22.1a-provenance-free-classes#r1-covering]]), the same `names_from_log` 22.2 R9
       uses, never a second naming. A NAMED or `unnamed:reborn` concept logs the drop on EACH
       logged key that covers the row, with THAT key's `c_kind` and `c`, exactly as 22.2 R9
       step 4 keys its events ([[task-22.2-repair-then-remove#r9-dangling]]). A NAMELESS
       concept (`unnamed:none` / `unnamed:ambiguous`) logs NO event, because no logged name lets
       a rebuild re-attach the row (22.2 R9 step 5's reason); the row is still deleted with its
       manifest entry, and counted `orphan_drop_nameless` and printed by `vacuum`. No kind is
       ever invented and `row_event` is never called with an empty `c_kind`.
   - **The partition field (r9 m-4).** `_log_event` adds no partition (`store.py:1119`), a
     compacted log's appends carry `partition: p` and live-shape appends carry none, and the row
     pass runs per partition. So each drop event carries the `partition` field of the
     `facts.log` appends it answers, exactly as they carry it (present with that value, or
     absent), never the vacuum's binding: 22.2 R9 step 4's rule
     ([[task-22.2-repair-then-remove#r9-dangling]]). Per orphan identity and per key from the
     rules above, ONE drop per DISTINCT partition field among that identity's logged appends on
     that key. `vacuum` finds those appends in ONE read-only scan of `facts.log` for the orphan
     identities (a set lookup per line; the same scan feeds the naming above). An identity with
     NO logged append logs no event (a rebuild cannot re-create it) and is counted
     `orphan_drop_unlogged` and printed.
   - **"Dead" is decided on the LOG timeline in a rebuild (d9bk; r8 s-1).** {#r5-timeline} Replay
     applies the op inside the ONE timestamp-ordered row pass of the rebuild, the one replay
     path (d9av, d9bu; [[task-22.2-repair-then-remove#r3]],
     [[task-16.6-learned-row-validation#r1d]]). `evidence_orphan_drop` at `T` deletes each copy appended at or before `T`
     whose `(linkage, c_kind, c, file, line, detail)` matches (the concept-side fields of
     `edge_records.row_key`, plus `detail`) AND whose own `(partition, e_kind, e)` was DEAD at
     `T`: its latest `tombstone` at or before `T` is at or after its latest `entity` event at or
     before `T`, or it has no `entity` event at or before `T`. Pass 2 already reads both
     timelines; the rule keeps them as a per-key sorted list of `ts` instead of only the latest,
     and nothing new is read. A matching copy whose entity was ALIVE at `T` is never deleted and
     is counted `orphan_drop_skipped_live` (16.6's `row_skips`). The materialized catalog is NOT
     the test: the rebuild materializes every surviving entity before the row pass, so "exists at
     that point" would mean "exists at the end of the log", and a re-created entity would keep
     its pre-vacuum copies (the doubling of AC-6b). There is no other replay path to give a
     catalog check to: the incremental path is deleted (16.6 R1f, d9bu; r9 s-2).
   - A copy whose entity the log still shows ALIVE at `T` because it was raw-deleted without a
     tombstone (bug-111's shape) is not dropped by the rebuild and is counted
     `orphan_drop_skipped_live`; the rebuild resurrects that entity anyway, which is 22.2 R9's
     named-tombstone domain ([[task-22.2-repair-then-remove#r9-dangling]]), not this op's.
   - `purge_entity` keeps deleting no evidence (round 6 stands; d9bk rejected purge removing
     its own evidence rows, which would widen every purge manifest).
   - After R3 and R4, learned rows stop becoming orphans on sync; step 3 drains the legacy ones
     and anything a non-plan-22 purge still leaves. Each drop is counted and printed by `vacuum`.
6. **R6 Every protection records its source, and the compactor keeps it (d9o, d9ab; r4 b-2).**
   {#r6}
   - **The field.** Every `protect` event, value `true` or `false`, carries `source`, set by the
     CALLER, never inferred:
     - `learner`: only `daemon._learn_grep_hits` (its `add_concept` and
       `upsert_entity(protected=True)` calls);
     - `user`: a CLI or MCP command (`rmx protect` / `unprotect` through `set_flag_by_selector`,
       `Store.set_flag_by_selector`; `rmx add-entity` / `add-concept` and their MCP tools; `link --protect`;
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
   - **The compactor keeps it (d9ab companion 1).** `Store.dump_catalog_to_log` emits `source` =
     `protect_source` on every `protect` event it writes, omitting the key when NULL. Without this
     the field lasts only until the next periodic compaction
     (`Daemon._compact_factslog_if_needed`; this repo compacted three times on 2026-10-14).
   - **The vocabulary is d9am's** (user, 2026-10-14): exactly `learner`, `user`, `system`,
     `removal`, set by the caller; round 3's `upsert` value is dropped (`rmx add-entity` also
     writes through `upsert_entity`, so the value could not tell the learner from the user).
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
     writes `fragments-repair-<stamp>-<kind>.jsonl`). That hotfix is MERGED (0.78.0, read at
     `3d3c798`); this task plans no second copy of it (d9ac). Since d9ae the LIVE merge is
     fenced: `daemon._op_partition_merge` answers only `dry_run=True`, and `rmx partition merge`
     runs `Store.merge_partition` offline with the daemon down; the helix plan redesigns the live
     merge.
   Until the helix plan takes them, both are unchanged, and `rmx removal audit --list` prints
   each as an unrouted merge path (`memory dedup`, `merge-partition`), so they are visible, not
   forgotten.
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
   | `ingest_gmd --as-memory`'s doc drop (at `7f2014a` a raw `DELETE FROM entities ... kind='doc'`, `ingest_gmd.py:891-896`; since 0.78.1 `store.purge_entity` per doc matched on name and path, in `ingest_gmd_paths`'s `as_memory` branch) | derived conversion (doc → memory for the same file) | the `purge_entity` half is DONE (bug-111): tombstoned, and its LINKS unlinked with their `unlink` events, so a rebuild cannot resurrect the doc or its links. What is left here: any learned row on that entity first goes to an R2-form cleanup manifest. `purge_entity` deletes NO `linkage_evidence` row (r6 s-3, corrected): the doc's own evidence rows are `vacuum` step 3's (R5), and other entities' evidence rows naming it as their concept become `dangling-evidence` members (22.1a, d9ar) that 22.2 R9 removes |
   | `merge_partition` (`Store.merge_partition`; live merge fenced, d9ae) | merge entry point, helix plan (d9ac) | R7 |
   | `fold_concept_dups` (`Store.fold_concept_dups`) | merge entry point, helix plan (d9o) | R7 |

   **What a purge leaves behind (r6 s-3, d9ar).** Round 5 said `purge_entity` leaves "links and
   evidence unlinked with their events". It unlinks LINKS only. Every `Store.purge_entity` /
   `Store._bulk_purge_ids` call, on every path in this table and in R1-R5, leaves (a) the purged
   entity's own evidence rows, for `vacuum` step 3 (R5), and (b) every evidence row of another
   entity that names it as its concept, a `dangling-evidence` member. 22.2's engine removes (b)
   before its own purges ([[task-22.2-repair-then-remove#r2]]); for the purges of paths outside
   the engine, (b) is drained by the `dangling-evidence` class
   ([[task-22.1a-provenance-free-classes#r1-dangling]]), never silently.

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
   **The file comes back (r7 b-1, d9av).** Continuing the fixture: the file is re-created with
   the same line, synced, and the same pattern is learned again (the identical learned row and
   sidecar row). A rebuild on a second copy equals the live store: 1 learned row, 1 sidecar row,
   `unresolved_provenance == 0`. Mutation "`evidence_remove` applied after all appends" FAILS it
   (the copy deletes the re-learned row and counts its provenance unresolved).
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
   row deletes nothing and counts `orphan_drop_skipped_live`. Each event carries `c_kind` (r8
   b-1). Mutation "delete without an event" FAILS the rebuild clause.

   **6b. Vacuum, then re-create: no doubling (d9bk; r8 s-1).** On a sandbox store: (1) ingest GMD
   doc `D` with one `rel:` evidence row (`D`'s entity end, a doc concept end); (2)
   `purge_path(D)` (it tombstones `D` and leaves the row orphaned, since purge deletes no
   evidence); (3) `vacuum` (one `evidence_orphan_drop`); (4) re-ingest `D`, which re-creates the
   same name and appends the identical row; (5) `rebuild_index_from_log` on a copy. The copy
   EQUALS live on `linkage_evidence` by name, as a multiset (1 copy each), and reports
   `orphan_drop_skipped_live == 0` and `evidence_unresolved == 0`. Mutation "orphan-drop checks the
   materialized catalog" FAILS it (the T2 drop sees the re-created `D` alive and skips: the copy
   holds 2). The `c_kind` half of the match is 16.6 AC-9d's (one `row_key`, one builder).
   *Variant on a compacted non-default partition (r9 m-4):* the same five steps in a sandbox
   store whose doc `D` lives in partition `p` (not the default), with `dump_catalog_to_log`
   (the compactor's call) run after step (1), so `D`'s `evidence` append carries
   `partition: p`. The `evidence_orphan_drop` event carries `partition: p`, and the copy holds 1
   copy, equal to live. Mutation "drop without the appends' partition field" FAILS it (the drop
   lands in the default partition's pass, matches nothing there, and the copy holds 2).

   **6c. Both ends dead (r9 s-1).** On a sandbox store, two orphan evidence rows whose concept
   is dead too: (a) concept end a DOC `N` whose `entity` event is in `facts.log`, then
   tombstoned, so 22.1a names it; (b) concept end a doc `Z` written with logging off and then
   raw-deleted, so no event names it (`unnamed:none`). Both entity ends are purged. After
   `vacuum`: both rows are gone from `linkage_evidence` and both are in the cleanup manifest;
   `facts.log` holds exactly ONE `evidence_orphan_drop`, keyed on `N`'s logged key (`c_kind:
   doc`, `c: N`); `vacuum` prints `orphan_drop_nameless: 1`; nothing raised. Then, on a copy,
   `N` and `Z` and both entity ends are re-created live by `upsert_entity` (no re-ingest, so no
   new append) and a rebuild runs: it holds neither
   row, equal to live, with `orphan_drop_skipped_live == 0`. Mutations, each FAILS it: "skip
   both-dead rows without a count" (the counter is 0); "key a dead concept's drop as
   `concept`" (the drop lands on a key no append resolves to, and the copy re-attaches `N`'s
   row to the re-created doc `N`); "call `_row_op_c_kinds` for a dead concept" (it has no
   `catalog_kind`: `row_event` raises and `vacuum` aborts).
7. **unprotect source (R6).** `rmx unprotect X` logs a `protect` event with `value=false,
   source=user`; a 22.2 restore that re-protects logs `source=removal`; a learn logs
   `source=learner`. Mutation "no source on value=false" FAILS it.

   **7b. The source survives compaction (r4 b-2, d9ab).** Protect L through `_learn_grep_hits`
   and U through `rmx protect U`; run `dump_catalog_to_log` (the compactor,
   `Daemon._compact_factslog_if_needed`'s call), then `rebuild_index_from_log` on a sandbox copy: `entities.protect_source` is
   `learner` for L and `user` for U, and the compacted log's two `protect` events carry those
   `source` values. Mutation "dump without `source`" FAILS it (both NULL after the rebuild, so
   22.2 R5 reads L as user-asserted).
8. **The merge paths are visible (R7; r4 m-6; d9ac).** `rmx removal audit --list` on a store
   prints `memory dedup` (MCP `rmx_memory` `dedup`) and `merge-partition` as unrouted merge paths.
9. **The remaining paths (R9).** The `ingest_gmd --as-memory` conversion of a doc that has a
   learned row writes a cleanup manifest holding it and logs a `tombstone` for the doc entity; a
   rebuild on a sandbox copy does not resurrect the doc entity. Mutations: "no learned-row
   manifest" FAILS it (the new half); "restore the raw DELETE" FAILS it (a regression guard: the
   tombstone half holds since 0.78.1).

   **9b. A purge leaves dead-concept evidence, and the class drains it (r6 s-3, d9ar).** Docs A
   and B, B carrying a `rel:` edge to A (an evidence row of B whose concept is A). A is dropped
   by each path that purges through `Store.purge_entity` outside 22.2's engine (the
   `--as-memory` conversion; `rmx untrack` of A's file through R2): immediately after, the test
   asserts that B's evidence row still names A's dead id (the corrected R9 sentence: purge does
   not delete evidence). Then `rmx removal audit` lists it `dangling-evidence`, and the confirmed
   apply leaves 0 `linkage_evidence` rows with a live entity and a dead concept; `vacuum` alone
   leaves the row (step 3 keys on the entity). Mutation "`vacuum` step 3 also deletes
   dead-concept rows without a manifest" FAILS it (the row disappears with no manifest record and
   no restore); mutation "drop the `dangling-evidence` sub-class" FAILS it (the row stays).

   **9c. Restoring a purge outside the engine re-attaches the rows that name it (r7 s-2).** As
   9b's first steps: concept `A` (kind `concept`) and doc `B`, `B` carrying a `rel:` evidence row
   whose concept is `A`; `A` is dropped by `rmx untrack` of its file (R2; its cleanup manifest
   holds only `A`'s own rows) and, in a second run, by the `--as-memory` conversion (R9). Before
   the `dangling-evidence` class runs, `removal restore` of that manifest re-creates `A` under a
   NEW id and, through 22.2 R4's `id_map` rule, updates `B`'s SURVIVING row to `A`'s new id in
   place, logs no `evidence` event for it, and counts it `restore_reattached`. Afterwards,
   compared by name, `B`'s evidence to `A` is present once, 0 `dangling-evidence` rows exist, and
   a rebuild on a copy holds the row once, with `evidence_unresolved == 0` and
   `evidence_skipped_dead == 0` (r8 m-4). Mutations, each FAILS it: "keep the recorded old id
   when the same manifest restores that entity" (`B`'s row still names the dead id: 1
   `dangling-evidence` row, which the class would later delete while `A` is alive); "log an
   `evidence` event for a re-attached surviving row" (the rebuilt copy holds the row twice).

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
| `src/refmatrix/store.py` | `purge_path(..., keep_learned=)`; R3 manifest + row-level removal of learned rows; `vacuum` steps 2-3 manifest + `evidence_orphan_drop` (with `c_kind`, through `row_event`; a live concept's kinds through `_row_op_c_kinds`, a dead concept's through 22.1a's `names_from_log` on the logged key, nameless counted `orphan_drop_nameless`; the appends' `partition` field from one log scan, unlogged counted `orphan_drop_unlogged`; [[#r5]], r9 s-1, m-4); `protect` events carry `source`; replay of `evidence_orphan_drop` in the one pass, the rebuild's dead-at-`T` rule on per-key `entity` / `tombstone` timelines ([[#r5-timeline]]) |
| `src/refmatrix/edge_records.py` | `evidence_orphan_drop` added to 16.6's `ROW_OPS` (the one op with a null entity end) |
| `scripts/factslog-restore.py` (plan-17 task 17.4's) | `evidence_orphan_drop` added to `FOLD_OPS` with its fold handling, in the same commit as the replay branch: 17.4's AST test pins `FOLD_OPS` to `rebuild_index_from_log`'s op set, and an op missing from it fails restore verification loudly (`unknown event op`) ([[task-17.4-factslog-backup-snapshot#r6-restore]]; ns17-r9-2) |
| `src/refmatrix/sync.py` | non-GMD edit and existing-unsupported branches call `purge_path(..., keep_learned=True)`; the GMD branch calls `purge_legacy_relpath_doc` behind the narrowed guard (R4) |
| `src/refmatrix/ingest.py` | the GMD legacy purge twin (`:1179-1180`): R4's GMD rule and guard |
| `src/refmatrix/ingest_gmd.py` | `--as-memory`: the raw DELETE becomes `purge_entity` with an R2-form manifest for learned rows (R9) |
| `src/refmatrix/daemon.py` | `forget` / `memory_forget` / `memory_bulk_forget` ops: preview or confirmed manifest only; `untrack` / `prune_noise` ops write the manifest first (R1, R2); `_learn_grep_hits` passes `protect_source='learner'` (R6) |
| `src/refmatrix/cli.py` (also) | `sync --invalidate` as a re-ingest (R4); `memory forget` without the `_store()` fallback (R1) |
| `src/refmatrix/store.py` (also) | `entities.protect_source` column + `protect_source` keyword on the protect writers; `dump_catalog_to_log` emits `source` (R6); `purge_legacy_relpath_doc` (R4) |
| `tests/test_removal_entry_points.py` (new) | AC-1..AC-9, AC-6b (and its partition variant), AC-6c, AC-9b, AC-9c |
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

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan16-22-spec-rereview-r6-0e77da3]] where it touches 22.6, and d9ar
([[plan-review-2026-10-14#t12-approvals]]); cites d9am ([[plan-review-2026-10-14#t11-approvals]]),
reflected since round 5 but not cited. Later rows win over round 5.

| finding / decision | answered in |
|---|---|
| r6 s-3 / d9ar (R9 said `purge_entity` unlinks evidence; purges leave dead-concept rows) | [[#r9]] `ingest_gmd` row corrected and "What a purge leaves behind"; [[#facts]] re-read; AC-9b + two mutations; the class is [[task-22.1a-provenance-free-classes#r1-dangling]], its removal [[task-22.2-repair-then-remove#r9-dangling]] |
| r6 m-5 (R4's lead names one call for both branches) | [[#r4]] lead: two different calls |
| r6 m-6 (`ingest_gmd` row and `merge_partition` stale since 0.78.1; line numbers) | [[#facts]] "Re-read at `3d3c798`"; [[#r9]] table; [[#r7]] (hotfix merged, live merge fenced, d9ae); [[#r1]], [[#r3]] (its existing-unsupported sub-bullet), [[#r6]], AC-7b cite by symbol |
| d9am (protection `source` vocabulary; `upsert` dropped) | [[#r6]] "The vocabulary is d9am's" |

rel: amends -> [[bsd-plan16-22-spec-rereview-r6-0e77da3]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan16-22-spec-rereview-r7-331b414]] where it touches 22.6 (b-1, s-2) and d9av
([[plan-review-2026-10-14#t12-approvals]]). Later rows win over round 6.

| finding / decision | answered in |
|---|---|
| r7 b-1 / d9av (R3's `evidence_remove` deleted, on a rebuild, a row re-learned after the file came back) | the replay order is fixed in [[task-22.2-repair-then-remove#r3]] and [[task-16.6-learned-row-validation#r1d]]; [[#r3]] "A file that comes back"; AC-4 clause + mutation "`evidence_remove` applied after all appends" |
| r7 s-2 (restoring `untrack`, R3 or the `--as-memory` conversion could not re-attach the rows that name the purged entity) | 22.2 R4's `id_map` rule ([[task-22.2-repair-then-remove#r4]]) covers SURVIVING rows; AC-9c (both entry points) + two mutations |

rel: amends -> [[bsd-plan16-22-spec-rereview-r7-331b414]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan16-22-spec-rereview-r8-23ad703]] where it touches 22.6 (b-1, s-1, m-5) and
d9bk, d9bl ([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at `23ad703`; `src/`
is unchanged from `23ad703` to the revision's HEAD. Later rows win over round 7.

| finding / decision | answered in |
|---|---|
| r8 b-1 / d9bl (`evidence_orphan_drop` spelled without `c_kind`) | [[#r5]] event built by `row_event` with `c_kind` (kinds through 22.2's `_row_op_c_kinds`), null entity end, op in `ROW_OPS`; AC-6 clause; [[#files-to-modify]] |
| r8 s-1 / d9bk ("entity does not exist at that point" cannot be evaluated by the rebuild's row pass; a vacuumed orphan comes back doubled) | [[#r5-timeline]] dead-at-`T` on the log timeline, match on `(linkage, c_kind, c, file, line, detail)`; incremental keeps the catalog check; raw-deleted entity counted; purge still deletes no evidence (d9bk); new AC-6b (the report's "AC-5c": that number is the `--invalidate` AC, so the vacuum AC's sibling is 6b) + mutation |
| r8 m-5 (pins shifted under 0.78.3) | [[#facts]] "Re-read at `23ad703`" |
| r8 m-4 (counters; 22.6 AC-9c among the `concept`-kind fixtures) | AC-6b and AC-9c assert the rebuild's counters; AC-9c keeps kind `concept` (22.2 AC-3c/3d/3f cover the doc kind) |

rel: amends -> [[bsd-plan16-22-spec-rereview-r8-23ad703]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-16.6-learned-row-validation#r1d-one-format]]

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan16-22-spec-diffcheck-r9-29e335a]] where it touches 22.6 (s-1, s-2, m-4) and
d9bu ([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at `428267f` (`src/`
unchanged since `23ad703`). Later rows win over round 8.

| finding / decision | answered in |
|---|---|
| r9 s-1 (an orphan whose concept is also dead has no name and no kind; 5,341 of cliquedb's 7,599 vacuum orphans) | [[#r5-both-dead]]: named by 22.1a's `names_from_log` (no second naming), the drop logged on each covering logged key with that key's `c_kind` and `c` (22.2 R9 step 4's keying); nameless logs no event and is counted `orphan_drop_nameless`; `_row_op_c_kinds` only for a live concept; AC-6c (named + nameless) with three mutations; [[#files-to-modify]] |
| r9 s-2 / d9bu (the incremental replay path has no caller) | [[#r5-timeline]]: "The incremental path keeps the catalog check" DROPPED; the rebuild is the one replay path (16.6 R1f deletes the incremental one) |
| r9 m-4 (no rule for the drop's `partition` field) | [[#r5]] "The partition field": the appends' field as they carry it (22.2 R9 step 4's rule, cited), one drop per distinct field, one log scan, `orphan_drop_unlogged` counted; AC-6b variant on a compacted non-default partition + mutation "drop without the appends' partition field" |
| ns17-r9-2 (coordinator: every new `facts.log` op this task adds is listed against 17.4's `scripts/factslog-restore.py` `FOLD_OPS`) | [[#files-to-modify]] `scripts/factslog-restore.py` row |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r9-29e335a]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
