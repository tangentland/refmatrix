---
gmd: "0.1"
id: task-31.2-learned-evidence-agreement
title: "Task 31.2: purge, vacuum, compaction and replay agree about evidence; an edit keeps learned rows; nothing drops evidence unlogged (bug-107, bug-247, 22.6 R4)"
tags: [task, plan-31, learned-rows, evidence, purge, vacuum, replay, facts-log, bug-107, bug-247]
metadata:
  node_type: task
  status: drafting
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
---

# Task 31.2: learned evidence agreement {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t2]])
> Status: drafting (ch-architect on Fable, 2026-11-15; ch-bsd spec review next)
> Depends on: 29.5 released ([[task-29.5-split-giant-modules]]): the purge code is then in
> `store_removal.py` and the replay in `store_replay.py`. Written against that layout
> ([[#layout]]).
> Closes: bug-107, bug-247 ([[bug_registry#registry]]). Carries 22.6 R4
> ([[task-22.6-removal-entry-points#r4]]; [[freeze-triage-2026-11-15]] row 13).
> Grep learning stays off (`~/.refmatrix/learn.off`) until this is deployed; turning it on is
> not this task.
> Base for every measurement here: `f3a508f`, and a copy of the dev store's read snapshot
> taken 2026-11-15 02:34.

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t2]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]]
rel: derives-from -> [[task-22.6-removal-entry-points#r4]]
rel: depends-on -> [[task-29.5-split-giant-modules]]
rel: depends-on -> [[bug_registry#registry]]
rel: depends-on -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[measurement-learned-rows-cli-store-2026-11-14]]
rel: depends-on -> [[orchestration#release]]
rel: depends-on -> [[plan-31b-spec-census]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_no_silent_failures]]

## Why {#why}

Four pieces of code decide whether an evidence row exists, and no two agree. A purge deletes
an entity and its links and leaves its evidence rows behind, pointing at nothing. `vacuum`
deletes those rows later and says nothing. The log compaction writes a new `facts.log`
without them and says nothing. A rebuild from `facts.log` replays every evidence event whose
two names are alive at the end, so the evidence of a file that was purged and re-created
under the same name comes back. Learned rows are the part of this that is knowledge: a
grep-learned row is written once, cannot be re-derived from the file, and is deleted by the
purge that every edit of its file runs. The user classified these paths on 2026-10-14
([[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]]): an edit keeps
learned rows; a deleted or ignored file's learned rows leave through a manifest; `vacuum`'s
orphan delete is logged, with a manifest. This task builds that classification with the
pieces the freeze admits, and makes the four agree. {#why-body}

## Measured (2026-11-15) {#baseline}

Scripts and outputs: [[plan-31b-spec-census]]. Store reads are on a copy of
`catalog.read.duckdb`, opened read-only. {#baseline-how}

### What the code does at `f3a508f` {#baseline-code}

| Path | Evidence rows of the purged entity | `facts.log` |
|---|---|---|
| `Store.purge_entity` (`store.py:6783`) and `_bulk_purge_ids` (`:7236`) | **left in place** (no `DELETE` on `linkage_evidence`); the DuckDB table has no cascade | `unlink` per link (`purge_entity` only), `tombstone`; nothing for evidence |
| `Store.vacuum` step 3 (`:8291`) | `DELETE … WHERE entity_id NOT IN (SELECT id FROM entities)`: the entity side only | **nothing**; not in the result either |
| `Store.dump_catalog_to_log` (`:8647`), the compaction | emits evidence only where both ends exist: the orphans are left out of the new log | n/a |
| `Store.rebuild_index_from_log` (`:9180`) | replays every `evidence` event whose two **names** are alive at the end of the log; a `tombstone` in between does not stop it | n/a |
{#baseline-code-table}

The callers that purge, counted at `f3a508f`:

| Caller | Meaning | Purges learned rows today |
|---|---|---|
| `sync.py:249` | the path is, or became, ignored | yes |
| `sync.py:253` | the path is missing, **or** exists with an unsupported extension | yes |
| `sync.py:271`, twin `ingest.py:1509` | GMD file with a relpath-named `doc` row: `purge_path` of the whole path | yes, and the doc-id row, its anchors and the inbound `rel:` edges from other docs |
| `sync.py:281` | a non-GMD file that already has its row: purge before re-add (**every edit**) | yes |
| `cli.py:9014` (`rmx sync --invalidate`, in `_sync_in_process`; no daemon op named `purge_path` exists at base, and R0 lists how `-i` is routed when a daemon answers) | re-ingest on request | yes |
| `store.py:8287` (`vacuum` step 2) | tracked paths no longer on disk | yes |
| `store.py:8197` (`untrack_by_path`), `:7183` (`forget_by_selector`), `:3256` / `:3486` (memory forget), `:8361` (`prune-noise --drop`), `:6970` (`fold_concept_dups`), `ingest_gmd.py:1486` (doc → memory), `:8836` (replica merge applying a `tombstone`) | removal on request, a merge, or a replay | not edit paths; they follow [[#r2]] only |
{#baseline-callers-table}

### What a learned row is {#baseline-learned}

One writer, `daemon._learn_grep_hits`: a protected concept `query/<pattern>`; the file's own
`code` or `doc` entity (named by its path relative to the project), which it marks protected;
a `mentions` link between them; one evidence row per hit with `detail = "learned from grep
'<pattern>'"`, `file` = the entity's name, and the line. On the read path
`store.verify_evidence_rows` serves a row only if its line still holds the pattern. On the
store copy: 2,204 protected entities: 1,711 `query/` concepts, 405 `code` / `doc` entities
and 88 memories. All 405 carry a learned row, and no unprotected entity does. {#baseline-learned-body}

### The orphans {#baseline-orphans}

`orphan_census.py`, output `workflow/review-output/spec31b-orphan-census-refmatrix.log`:

| Measure | Rows |
|---|---|
| `linkage_evidence` | 1,715,353 |
| entity gone (`vacuum` step 3's set) | 1,268,561 (74%): learned 30,131; `rel:` 17,062; other ingest-derived 1,221,368 |
| concept gone (step 3 does not look) | 34,451 |
| learned rows | 107,574: attached 77,443 on 405 entities; **orphaned 30,131 (28%)** |
{#baseline-orphans-table}

The lead's count on 2026-11-14 was 28,164 orphaned and 628 attached entities
([[measurement-learned-rows-cli-store-2026-11-14]]): 0.84.0's reingest and a day of syncs
orphaned 1,967 more. Of the 30,131 learned orphans:

| Measure | Value |
|---|---|
| the file is on disk | 30,131 (411 files) |
| a live `code` / `doc` entity of that name exists (the row can re-attach) | 30,078 |
| the `query/` concept still exists | 30,120 |
| the current file holds the pattern on the recorded line | 9,749 as a literal, 3,318 more as a regex: 13,067 (43%) |
| distinct `(concept, file)` pairs / with a live file entity / linked today | 2,728 / 2,717 / 2 |
| files whose live entity lost its `protected` flag | 383 of 411 |
| top files | `cli.py` 14,639; `daemon.py` 1,860; `store.py` 1,337; `bug_registry.md` 1,042 |
{#baseline-learned-orphans-table}

- Almost every orphan can go back where it was: the file and its entity exist, and so does
  the concept. What was lost is the association: 2,717 `query → file` pairs, of which 2 exist
  today. {#fact-reattachable}
- 43% of the rows still point at a line that holds their pattern; the read path would serve
  those and drop the rest, as it does for any learned row after an edit. {#fact-verifies}
- Fleet stores were not measured: each has its own orphans, and the same census runs on a
  copy of each before its store event ([[#r9]]). {#fact-fleet}

### What the order probe showed {#baseline-probe}

The probe on the unmerged branch `spec-29-7-learned-rekey` (`a63d120`,
`workflow/measurements/task-29.7-order-probe/order_probe.py`, read in
`/Volumes/littlebig/refmatrix-spec-29-7`) ran a sync over one deleted file and one file changed
in place, each with a learned row: learned evidence 2 → 0, both `mentions` links and both
`protected` flags gone, the two `query/` concepts left behind. A rebuild from `facts.log`
then brought the changed file's purged row back (3 rows where the live store had 2):
bug-247. This task's RED reuses that fixture. {#baseline-probe-body}

### Cost of the deletes {#baseline-cost}

On a writable scratch copy, each inside a transaction that was rolled back (statement time
only; commit and checkpoint not measured): one `DELETE` of the evidence at either end of the
1,063 entities of `cli.py` (10,350 rows) 2 ms; of `store.py`'s 500 entities (23,136 rows)
2 ms; of all 1,286,125 rows with either end gone 18 ms. `linkage_evidence` is indexed on
`entity_id` and on `(linkage_id, concept_id, entity_id)`. {#baseline-cost-body}

## The rule {#rule}

Two invariants, stated once; every requirement below is one of them applied to a path.

- **I1. An evidence row exists only while both its ends exist.** Whatever removes an entity
  removes the evidence at either end in the same step. {#i1}
- **I2. The catalog and a rebuild from `facts.log` hold the same evidence.** A `tombstone`
  ends the evidence of that incarnation in the replay as the purge ends it live; anything
  else that removes evidence writes an event the replay applies. {#i2}

And one classification, the user's (d9o, d9p):

| What happens to the file | Ingest-derived rows | Learned rows |
|---|---|---|
| edited, re-ingested, or `--invalidate`d while it exists | purged and re-derived | **kept**, on the same entity, unverified ([[#r3]]) |
| exists with an unsupported extension | purged | **kept** ([[#r3]]) |
| deleted, or now ignored | purged | written to a manifest, then purged ([[#r4]]) |
| already orphaned by the old code | dropped by `vacuum`, counted and logged ([[#r5]]) | `plan-31 D14` ([[#r7]]) |
{#rule-table}

## Requirements {#requirements}

### R0: re-measure at base {#r0}

At the task's base (after 29.5): run `orphan_census.py` on a fresh read-only copy; run the
order probe's fixture; time [[#r5]]'s step 3 and [[#r7]]'s re-attach end to end, **with
commit**, on a writable scratch copy of the dev store's snapshot, and record the store-lock
hold it implies. Bands, stated now: under 30 s, as specified; 30 to 120 s, the step runs only
in the announced store event and the summary says so; over 120 s, step 3 is chunked by file
with lock yields and the spec returns to the lead. Re-read 29.5's landed module map and
correct [[#layout]]'s file names in the summary. {#r0-body}

### R1: one definition of "learned" {#r1}

`edge_records.py` holds the two literals and the predicates: the evidence `detail` prefix
`learned from grep ` and the concept prefix `query/`; `is_learned_evidence(detail)`,
`is_learned_concept(name)`. The writer (`daemon._learn_grep_hits`) builds its strings from
them; the purge, `vacuum`, the replay and the census read them. A **learned file entity** is
a `code` or `doc` entity with at least one learned evidence row, or one that is `protected`
(today the same 405 rows, [[#baseline-learned-body]]). {#r1-body}

### R2: a purge takes the evidence with the entity (I1) {#r2}

`purge_entity` and `_bulk_purge_ids` delete the `linkage_evidence` rows whose `entity_id` or
`concept_id` is a purged id, in the same commit as the entity rows, in one statement per
purge call or per chunk, never one per entity. No new log event: the `tombstone` each already
writes is the event ([[#r6]]). This closes the source of orphans for every caller in
[[#baseline-callers-table]]. {#r2-body}

### R3: an edit keeps learned rows (22.6 R4) {#r3}

`purge_path(abs_path, keep_learned=True)`: every entity at the path is purged as today
**except** a learned file entity ([[#r1]]). That entity keeps its id, its `protected` flag,
its learned evidence rows and its `mentions` links from `query/` concepts. Its other links
are unlinked (logged as today) and its other evidence rows are deleted, with one
`evidence_clear {partition, kind, name, keep: "learned"}` event ([[#r6]]). No `tombstone` is
written for it. The kept rows are not re-verified: the read path judges them
([[#baseline-learned-body]]). The count of kept rows is returned. {#r3-body}

| Site | After |
|---|---|
| `sync.py:281`, non-GMD edit | `purge_path(abs, keep_learned=True)`; the `upsert_entity` that follows finds the kept row (it only ratchets `protected` upward) |
| `sync.py:253`, split | missing → [[#r4]]; exists with an unsupported extension → `keep_learned=True` |
| `sync.py:271` and `ingest.py:1509`, GMD legacy purge | **never `purge_path`.** `Store.purge_legacy_relpath_doc(rel, abs)` touches only the relpath-named `doc` row: its non-learned links and evidence go (logged); the row itself is purged only if no learned row is left on it. The doc-id row, its anchors and the inbound `rel:` edges are not touched |
| the guard of those two sites | fires only when the relpath-named row has at least one non-learned row (a link, an evidence row, or a `tracked_files` row at its path); a row that is all learned does not fire it |
| `rmx sync --invalidate P` (`cli.py:9014`, and whatever route R0 finds for a live daemon) | an existing path: `keep_learned=True`; a missing path: [[#r4]] |
{#r3-sites}

These are 22.6 R4's rules and its "two branches are not the same call"
([[task-22.6-removal-entry-points#r4]]), without its sidecar rows: 16.6's sidecar is not built
and stays post-mod. {#r3-source}

### R4: a deleted or ignored file's learned rows leave through a manifest {#r4}

`purge_path(abs_path)` (the default, `keep_learned=False`) for a missing or ignored path
(`sync.py:249`, the missing half of `:253`, `vacuum` step 2, a missing `--invalidate` path):
when the path holds learned rows, a cleanup manifest is written and synced to disk **before**
anything is deleted; then the purge runs as today, with [[#r2]]. {#r4-body}

- **The manifest** is `.refmatrix/removal/<UTC stamp>-<n>.cleanup.jsonl`, format
  `rmx-cleanup/1`: a header line (`format`, `reason` = `purge-path` or `vacuum`, `partition`,
  `path`, `created`), then one line per row with every column by **name**, never by id
  (`{"row": "entity", kind, name, path, protected}`,
  `{"row": "link", linkage, c_kind, c, e_kind, e, weight}`,
  `{"row": "evidence", linkage, c_kind, c, e_kind, e, file, line, span_end, detail}`), then a
  closing line with the row count. It holds the learned file entity, its learned evidence and
  its `query/` links. Ingest-derived rows are not in it: the file is gone and they cannot be
  restored to anything. {#r4-manifest}
- **Logged:** one `learned_cleanup {partition, path, manifest, entities, links, evidence}`
  event, then the `tombstone`s. The replay needs only the `tombstone`s ([[#r6]]); the event is
  the record that the drop was audited. {#r4-event}
- **Fail closed.** If the manifest cannot be written, the learned rows of that path are kept
  (the path is purged with `keep_learned=True`), the failure is counted on the store and
  reported like a refused sync path. {#r4-fail}
- **A file that comes back** (a branch switch) starts with no learned rows; rows learned after
  the purge are appended after the `tombstone` and survive live and in the replay. {#r4-back}
- **No restore command.** 22.2's `removal_restore` is post-mod. The manifest is complete and
  self-describing so that it, or a person, can re-apply it. {#r4-restore}

### R5: `vacuum` says what it drops {#r5}

Step 3 becomes "evidence with either end gone" (the concept side too: 34,451 rows today).
After [[#r2]] no new orphan is made, so this step only ever meets rows the old code left.
{#r5-body}

- **Ingest-derived orphans** (1,238,430 here) are deleted. Before the delete a manifest
  records them **as counts** per `(file, linkage, kind of row)`, not row by row: each row
  points at nothing and is re-derived by the next ingest of its file. {#r5-derived}
- **Learned orphans** follow `plan-31 D14` ([[#r7]]). {#r5-learned}
- **Result and output.** `vacuum()` returns, and `rmx vacuum` prints,
  `evidence_dropped: {derived, rel, learned}`, `learned_reattached`, and the manifest path.
  One `evidence_orphan_drop {partition, derived, rel, learned, manifest}` event is logged.
  {#r5-report}
- **`rmx vacuum --dry-run`** (and the op's `dry_run`) runs every step's selection and prints
  the same counts, writing nothing. It is the audited path's first half. {#r5-dry-run}
- **Step 2** (dead tracked paths) goes through [[#r4]]. Step 1 (empty concepts) follows
  [[#r2]]. {#r5-steps}

### R6: the replay agrees (I2) {#r6}

`rebuild_index_from_log` applies, in log order:

- a `tombstone` of `(partition, kind, name)` drops every evidence event before it that has
  that name at either end. The entity may be created again later; evidence appended after
  the `tombstone` attaches to the new incarnation. This is bug-247's fix; {#r6-tombstone}
- `evidence_clear {kind, name, keep: "learned"}` drops every non-learned evidence event
  before it with that name at the entity end; {#r6-clear}
- `learned_cleanup` and `evidence_orphan_drop` change nothing in the replay (their rows are
  already ended by a `tombstone`, or were never in a state the replay rebuilds). {#r6-records}

`_apply_event_body` (the incremental consumer, replica merge) applies `evidence_clear` the
same way; its `tombstone` already calls `purge_entity`, which now takes the evidence
([[#r2]]). `dump_catalog_to_log` is unchanged: with I1 there is no orphan for it to leave
out. {#r6-consumers}

### R7: the rows already orphaned (`plan-31 D14`) {#r7}

Written for the recommended option (a). Under (a), `vacuum` step 3 treats a learned orphan
whose concept and same-named `code` / `doc` entity both exist, in the concept's partition, as
**re-attachable**: {#r7-body}

- its evidence rows are re-pointed to the live entity's id, in one set-based statement;
- the `mentions` link from the concept is restored if absent, and the entity is marked
  `protected` if it is not (both logged by the existing `link` and `protect` events);
- one `evidence` event per re-pointed row is appended, with the live names, so the replay
  holds them after the old incarnation's `tombstone`;
- a learned orphan that is not re-attachable (53 without an entity, 11 without a concept
  here) goes to the manifest in full ([[#r4-manifest]]'s form) and is deleted.

This leaves the store as [[#r3]] would have left it had the fix existed when the edits
happened: the rows on their file, unverified, served only where the line still holds the
pattern. {#r7-why}

| Option | `vacuum` step 3 does, for a re-attachable learned orphan | Spec text that changes |
|---|---|---|
| (a) re-attach | as above | none |
| (b) drop with a manifest | writes it to the manifest in full and deletes it | the four bullets above become one; AC-7 asserts the manifest and the delete |
| (c) keep | leaves it in place and counts it (`learned_orphans_kept`) | I1 is then false for learned rows by decision; AC-7 asserts the count; [[#ac-9]] excludes them |
{#r7-options}

### R8: every path reports {#r8}

The sync report gains `learned_kept` and `learned_manifested` (rows), added to the sync log
line when non-zero; `rmx sync` prints them. `rmx vacuum`'s line is [[#r5-report]]. A manifest
that could not be written is reported per [[#r4-fail]]. {#r8-body}

### R9: the store event {#r9}

The code changes no row until a `vacuum` runs. For the dev store, in the release: copy the
snapshot and run `orphan_census.py`; `rmx vacuum --dry-run`; the user's go; back up
`catalog.read.duckdb`, `facts.log` and `active`; `rmx vacuum`; the census again on a fresh
copy ([[#ac-9]]). Every other store is a separate user go, with its own census first
([[orchestration#release]] step 4). Until a store is vacuumed its orphans stay as they are.
{#r9-body}

## Where the code is after 29.5 {#layout}

Requirements name `Store` methods, which 29.5 does not rename. By
[[task-29.5-split-giant-modules#map-store-table]]: `purge_entity`, `purge_path`,
`_bulk_purge_ids`, `untrack_by_path`, `vacuum` and the new `purge_legacy_relpath_doc` are in
`store_removal.py`; `rebuild_index_from_log`, `_apply_event_body`, `dump_catalog_to_log` in
`store_replay.py`; `add_evidence`, `clear_rel_evidence` in `store_links.py`. If 29.5 lands
with other file names, only [[#files]] changes: R0 re-reads the landed map and the summary
lists the real files. A new store module is not created. If this task were to run before
29.5, the same methods are in `store.py` and nothing else differs; the plan's order says it
does not. {#layout-body}

## Acceptance criteria {#acceptance}

New tests live in `tests/test_bug107_learned_evidence.py` unless said otherwise. Stores are
throwaway, under a short `mkdtemp` root. "The fixture" is the order probe's: a file deleted
and split in two, a file changed in place, one learned pattern on each. {#acceptance-intro}

- **AC-1: an edit keeps learned rows.** The fixture's changed file through `_sync_paths`: the
  file entity has the same id; its learned evidence row, its `query/` link and its
  `protected` flag are there; its per-function entities are re-created; its ingest evidence
  is the new version's. Also for a learned row on an existing file with an unsupported
  extension, and through `rmx sync --invalidate`. **RED** at base (E line: learned evidence
  1 → 0). {#ac-1}
- **AC-2: a GMD edit keeps the doc graph.** Two GMD docs, A and B; B has a `rel:` line to an
  anchor of A; A also has a learned row on its relpath-named `doc` row. A is edited and
  synced: A's doc-id row and anchors keep their ids; B's edge to A's anchor is still live;
  the learned row is kept. The same through `rmx ingest` (the twin). With a relpath row that
  is all learned, the guard does not fire (no purge call, asserted by the row's id and an
  unchanged `facts.log` tombstone count). **RED** at base (E lines: the anchor has a new id;
  B's edge is gone). {#ac-2}
- **AC-3: a deleted file's learned rows are in a manifest before they go.** The fixture's
  deleted file, and a file that became ignored: a `rmx-cleanup/1` manifest exists holding the
  entity, the link and the evidence row by name; a `learned_cleanup` event names it; the rows
  are gone from the catalog; the sync report says `learned_manifested: 1`. **RED** at base
  (E line: no manifest; the rows are orphaned). {#ac-3}
- **AC-4: the manifest fails closed.** With `.refmatrix/removal` made unwritable, the same
  sync keeps the learned rows, reports the failure, and exits non-zero on the CLI route.
  **RED** at base (no such path). {#ac-4}
- **AC-5: no purge leaves an orphan.** After each caller of [[#baseline-callers-table]] is
  driven once on a store with ingest evidence and learned evidence (sync edit, sync delete,
  `untrack`, `forget`, `prune-noise --drop`, `vacuum` steps 1 and 2, the doc → memory
  conversion), the count of evidence rows with either end gone is 0. Parametrised by caller.
  **RED** at base for every caller (E line: the orphan count). {#ac-5}
- **AC-6: `vacuum` reports and logs.** A store seeded with orphans of the three kinds (by
  deleting entity rows directly, the state the old code left): `vacuum(dry_run=True)` returns
  the counts and changes nothing; `vacuum()` returns the same counts, the counts manifest
  exists, one `evidence_orphan_drop` event is logged, and `rmx vacuum` prints the line. Rows
  whose **concept** is gone are dropped too. **RED** at base (E lines: no such keys; the
  concept-side rows remain). {#ac-6}
- **AC-7: the legacy learned orphans, per `plan-31 D14`.** On that seeded store, option (a):
  a re-attachable row is on the live entity, the link and the flag are back, an `evidence`
  event with the live names is logged; a row with no live entity is in the manifest and
  gone. Options (b) and (c) change the assertions as [[#r7-options]] says. **RED** at base
  (E line: the rows are deleted silently). {#ac-7}
- **AC-8: the replay agrees.** For each scenario of AC-1, AC-2, AC-3, AC-6 and AC-7, and for
  the order probe's Q3, the multiset of evidence rows by `(linkage, concept name, entity
  name, file, line, detail)`, the links and the `protected` flags are equal between the live
  store and a second store rebuilt from its `facts.log`, and equal again after
  `dump_catalog_to_log` and a rebuild. **RED** at base (E line: the changed file's purged row
  is back, 3 rows against 2, as in the probe). {#ac-8}
- **AC-9: the dev store after its `vacuum`.** `orphan_census.py` on a fresh copy: evidence
  with either end gone 0; under (a), learned rows attached ≥ 107,500 and `(concept, file)`
  pairs linked ≥ 2,717 more than before; the counts printed by the run equal the dry run's.
  **Measurement**, after the user's go. {#ac-9}
- **AC-10: the lock hold is bounded.** R0's timing, against its bands. **Measurement.**
  {#ac-10}
- **AC-11: one definition.** A static test over the string constants of `src/refmatrix/*.py`
  (docstrings excluded): the literal `learned from grep` occurs in `edge_records.py` only.
  A unit test: for patterns holding quotes, spaces and a `/`, the detail and the concept
  name the writer's helpers build satisfy `is_learned_evidence` and `is_learned_concept`.
  The `query/` prefix also appears in help text and is not counted. **RED** at base
  (`daemon.py:4581` and `:4610` hold the literal). {#ac-11}
- **AC-12: the incremental consumer.** A replica that applies the log delta of AC-1's and
  AC-3's scenarios through `apply_log_delta` holds the same evidence as the writer. **RED**
  at base (E line: the replica keeps the purged entity's evidence, or lacks the op). {#ac-12}

## Must-fail mutations {#mutations}

| # | Mutation | Must turn RED |
|---|---|---|
| 1 | `sync.py`'s edit branch calls `purge_path` without `keep_learned` | AC-1 |
| 2 | `keep_learned` keeps the entity but drops its `query/` links | AC-1 |
| 3 | `keep_learned` keeps the entity's ingest evidence too | AC-1 (ingest evidence is the new version's), AC-8 |
| 4 | the GMD site calls `purge_path(…, keep_learned=True)` instead of `purge_legacy_relpath_doc` | AC-2 (anchor ids, B's edge) |
| 5 | the guard fires on an all-learned relpath row | AC-2's last leg |
| 6 | the manifest is written after the delete | AC-3 with a write that fails: AC-4 |
| 7 | drop the evidence `DELETE` from `purge_entity` | AC-5 (the `purge_entity` callers), AC-8 |
| 8 | drop it from `_bulk_purge_ids` | AC-5 (`untrack`, `forget`, `vacuum`) |
| 9 | step 3 looks at the entity side only | AC-6's concept-side leg |
| 10 | `vacuum` logs no `evidence_orphan_drop` | AC-6 |
| 11 | `dry_run` deletes | AC-6 |
| 12 | re-attach appends no `evidence` event | AC-8 (the AC-7 scenario) |
| 13 | the replay ignores a `tombstone` for evidence | AC-8 (the probe's Q3) |
| 14 | the replay ignores `evidence_clear` | AC-8 (the AC-1 scenario) |
| 15 | `_apply_event_body` ignores `evidence_clear` | AC-12 |
| 16 | re-attach binds to an entity of the same name in another partition | AC-7, with a two-partition leg |
{#mutations-table}

## Caller census {#census}

The purge callers are [[#baseline-callers-table]]. Others:

| Function | Callers | Change |
|---|---|---|
| `Store.vacuum` | `daemon._op_vacuum`, `cli.vacuum` | `dry_run`; the new result keys; the CLI line |
| `rebuild_index_from_log` | `rmx rebuild`'s command and the daemon's repair path (listed by grep at R0) | the two replay rules |
| `_apply_event_body` | `apply_log_delta` (replica merge) | `evidence_clear` |
| `dump_catalog_to_log` | the daemon's `facts.log` rotation tick; the bootstrap command | none; AC-8 pins the round trip |
| `daemon._learn_grep_hits` | the learn-queue drain, `_op_learn_from_grep`, `_op_context`'s grep backstop | builds its strings from [[#r1]]'s constants |
| `verify_evidence_rows` | the grep and context read paths | none |
| readers of the sync report | `cli` sync rendering, `daemon` watch and async-flush, `append_sync_log` | two new keys |
{#census-table}

A consumer of `facts.log` that ignores an unknown op is safe for the three new ops
(`evidence_clear`, `learned_cleanup`, `evidence_orphan_drop`); R0 lists every reader of the
log by grep and the summary says which ignore, which fail and which were changed. {#census-ops}

## Files {#files}

By 29.5's map ([[#layout]]): `src/refmatrix/store_removal.py` (R2, R3, R4, R5, R7),
`src/refmatrix/store_replay.py` (R6), `src/refmatrix/edge_records.py` (R1; the manifest
writer), `src/refmatrix/sync.py` and `src/refmatrix/ingest.py` (R3's sites, R8),
`src/refmatrix/daemon.py` (`_learn_grep_hits`, `_op_vacuum`),
the `cli` module that holds `vacuum` and `_sync_in_process`. New
`tests/test_bug107_learned_evidence.py`. `docs/SYSTEM.md` (the evidence lifecycle, the
manifest format) and `docs/INTEGRATION.md` (`rmx vacuum --dry-run`). `workflow/bug_registry.md`
(bug-107, bug-247, and the rows for [[#decisions-findings]]), the implementation summary.
`task-22.6-removal-entry-points` gains one amends line saying its R4 is built here and its R3
and R5 are narrowed by this task's manifest form; the lead adds it at the merge. {#files-list}

## Risks {#risks}

- **`vacuum` under the store lock.** `_op_vacuum` holds the lock for the whole call. The
  one-time drain is 1.27 million deletes, 30 thousand re-pointed rows and as many log lines.
  The statement times measured are milliseconds, uncommitted; R0 measures the real hold and
  [[#r0]]'s bands decide. {#risk-lock}
- **A transaction that rolls back** leaves its log events and bitmap bits (bug-248,
  post-mod). `_sync_paths` runs in one transaction, so a rolled-back sync can leave a
  manifest and a `learned_cleanup` event for rows that were not deleted. The manifest then
  over-reports and loses nothing. Not fixed here. {#risk-rollback}
- **Old logs.** The new `tombstone` rule applies to every log, including events written
  before this task. For ingest-derived evidence that is the fix. For learned evidence under
  (a), the re-attach appends fresh events; a store rebuilt from its log **before** its
  `vacuum` would not have the legacy learned rows. The release note says: vacuum before any
  rebuild. {#risk-old-logs}
- **Stale lines stay.** Kept and re-attached learned rows may name a line that no longer
  holds the pattern. The read path drops them; they still count in table sizes. Their
  verification or removal is 16.6 and 22.1, post-mod. {#risk-stale-lines}
- **Protection widens the keep.** A file entity a user protected by hand is kept across
  edits like a learned one. None exists in the dev store today. {#risk-protected}
- **Manifests accumulate** under `.refmatrix/removal/`, one per purge that held learned rows.
  A branch switch over many learned files writes many small files. Nothing prunes them here.
  {#risk-manifests}
- **29.5's names.** See [[#layout]]. {#risk-layout}

## Out of scope {#out-of-scope}

- Turning grep learning back on; the shim and the learner's redesign (plan-16, post-mod).
- 16.6's provenance sidecar and verifier; 22.1's set rule; 22.2's engine and
  `removal_restore`; `forget` and `bulk-forget` as plan-22 entry points; the rest of 22.6
  ([[plan-of-plans#post-mod]]).
- bug-219's count repairs beyond I1; bug-248.
- Re-keying learned rows to new lines or new files (task 29.7, dropped by ruling L115).
- Any store but the dev store.
{#out-of-scope-list}

## Decisions {#decisions}

**For the user: `plan-31 D14`.** The 30,131 learned evidence rows already orphaned in the dev
store (and their like in each other store):

- **(a) recommended: re-attach.** 30,078 of them (99.8%) have their file, a live entity of
  the same name and their concept; re-attaching restores 2,717 `query → file` associations of
  which 2 exist today, and 13,067 rows (43%) still hold their pattern on the recorded line
  and are served again. The rest stay on their file unserved, exactly as an edit leaves a
  learned row under the fixed code. It removes nothing, and it makes the store what the fix
  would have left. The 53 rows that cannot re-attach go to a manifest.
- (b) drop with a manifest. All 30,131 are written to a manifest and deleted; the 2,717
  associations are a recorded loss, as L115 recorded the `cli.py` / `store.py` rows.
- (c) keep. They stay as orphans, counted at each `vacuum`. No loss and no repair; the
  catalog and a rebuild from the log then differ by these rows for good.
{#d14}

**Taken in this spec** (for the lead to register): evidence follows its entity at every
purge, with the `tombstone` as its event ([[#r2]], [[#r6-tombstone]]); a learned file entity
is one with a learned row or the `protected` flag ([[#r1]]); 22.6 R4 is taken whole, without
the sidecar ([[#r3-source]]); the manifest form `rmx-cleanup/1`, with no restore command
([[#r4-manifest]], [[#r4-restore]]); ingest-derived orphans are recorded as counts, not rows
([[#r5-derived]]): the ADR asks for a manifest before the change and does not fix its grain,
and 22.6 R5's row-level streaming manifest (834,201 rows then, 1.24 million now) restores
nothing a re-ingest does not; `vacuum` gains a dry run and is the store event ([[#r5-dry-run]],
[[#r9]]); the manifest fails closed ([[#r4-fail]]). {#decisions-taken}

**Findings for the lead's registry** (no ids allocated here): (1) the compaction
(`dump_catalog_to_log`) is a third unlogged drop of orphan evidence
([[#baseline-code-table]]); (2) `vacuum` step 3 never looked at the concept side: 34,451
rows; (3) `_apply_event_body` does not apply `rel_evidence_clear`, so a replica keeps `rel:`
evidence the writer cleared (read at `f3a508f`, not probed); (4) the orphan count grew from
28,164 to 30,131 in a day with learning off: every edit of a learned file still orphans its
rows. {#decisions-findings}
