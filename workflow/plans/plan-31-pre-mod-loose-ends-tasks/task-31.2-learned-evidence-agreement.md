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
> Status: drafting (revision 2 after ch-bsd r2, ruling L147; fold tables at [[#rev-r1]] and
> [[#rev-r2]])
> Depends on: 29.5 released ([[task-29.5-split-giant-modules]]): the purge code is then in
> `store_removal.py` and the replay in `store_replay.py`. Written against that layout
> ([[#layout]]).
> Closes: bug-107, bug-247, bug-259, bug-260, bug-262 ([[bug_registry#registry]]; bug-259 and
> bug-260 folded in by ruling L132, bug-262 by L144, [[plan-of-plans#rulings]]). bug-264, the
> GMD-dispatch half of R3, moved to 31.1 by L144 ([[#r3-gmd]]). Carries 22.6 R4
> ([[task-22.6-removal-entry-points#r4]]; [[freeze-triage-2026-11-15]] row 13), stated without
> 16.6's sidecar ([[#r3-source]]), and the learned-row halves of 22.6 R3 and R5 that
> [[plan-31-pre-mod-loose-ends#t2]] names ([[#scope-22-6]]).
> Decision: `plan-31 D14`, decided by the user in [[plan-of-plans#decisions]] ([[#r7]]).
> Takes bug-203 (ruling L136 (2): this task routes `rmx sync -i` to the writer; Q39 is
> withdrawn).
> Open with the user: Q38 (what "resolved" means in D14, [[#r7-line]]), in
> [[plan-of-plans#questions]]. The text that depends on it is marked conditional.
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
rel: depends-on -> [[plan-of-plans#decisions]]
rel: depends-on -> [[plan-of-plans#questions]]
rel: related-to -> [[task-22.2-repair-then-remove#r4]]
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

`resolvable_split.py` applies [[#r7-rule]]'s match rule to the same copy, against the dev
tree as it stands when the script runs (output
`workflow/review-output/spec31b-resolvable-split-refmatrix.log`). Run twice on 2026-11-15:

| Class | First run | Second run | Detail (second run) |
|---|---|---|---|
| **resolvable** (re-attached) | 30,078 | **29,824** (99.0%) | 2,697 `(concept, entity)` pairs on 407 files; 9 rows equal a row already attached to that entity |
| not resolvable: the concept is gone (C) | 11 | 11 | `cli.py` 9, `store.py` 2 |
| not resolvable: no entity of the learner's kind and that name (E) | 42 | 42 | `workflow/bullshit/last_run.log` 23, `pyproject.toml` 19 (files the ingest does not index) |
| not resolvable: the file is not on disk (F) | 0 | 254 | `workflow/plan-review-2026-10-14.md` 207, `workflow/plan-review-2026-10-07.md` 47 |
| **deleted with a manifest** | 53 | **307** | |
| of the resolvable: the recorded line still holds the pattern | not split | 12,647 (literal 9,635, regex only 3,012) | the rest, 17,177, no longer hold it; these three counts are from the run of the committed log, taken later the same day |
{#baseline-split-table}

- **The split moves with the tree.** Between the two runs the dev tree's `master` removed
  the two plan-review files (commit `903f7f5`, archived). The catalog copy is the same; 254
  rows that named a file on disk in the morning name none now. That is the rule working: a
  file that is gone takes its learned rows to the manifest ([[#r4]]). The numbers in the POP
  (30,078 and 53) are the first run's. The store event counts again, and the dry run's count
  is the one that binds ([[#r9]]). {#fact-split-moves}
- The POP's D14 row also quotes the lead's count of 2026-11-14, 28,164 orphans; the copy of
  2026-11-15 holds 30,131. {#fact-split}

### What the order probe showed {#baseline-probe}

The probe on the unmerged branch `spec-29-7-learned-rekey` (`a63d120`,
`workflow/measurements/task-29.7-order-probe/order_probe.py`, read in
`/Volumes/littlebig/refmatrix-spec-29-7`) ran a sync over one deleted file and one file changed
in place, each with a learned row: learned evidence 2 → 0, both `mentions` links and both
`protected` flags gone, the two `query/` concepts left behind. A rebuild from `facts.log`
then brought the changed file's purged row back (3 rows where the live store had 2):
bug-247. This task's RED reuses that fixture. {#baseline-probe-body}

### The "legacy" relpath row is made again by every sync {#baseline-relpath}

ch-bsd r1 S6, probed there and again here (`sync_refusal_probe.py`,
`workflow/review-output/spec31b-sync-refusal-probe.log`):

- Every sync of a GMD file runs the markdown semantic pass over it, which upserts a `doc`
  row named by the file's **relpath** and stamps `tracked_files`. So the row
  `_sync_one`'s guard looks for (`sync.py:269-271`) exists after the first sync of any GMD
  doc, whether or not anything was ever learned on it. It is not legacy. {#fact-relpath-remade}
- On the next edit the guard therefore fires and `purge_path` takes the whole path: the
  doc-id row and every anchor get new ids (`adoc` 1 → 14, `adoc#sec` 3 → 16 here), and the
  inbound `rel:` edges of the anchors are deleted with them. The citing doc is unchanged, so
  nothing writes them back: in the probe `b`'s two edges to `adoc#sec` go to 0 on a plain
  edit of `a`. This happens today on every edit of every synced GMD doc, with learning off.
  It is registered as **bug-264** and, by ruling L144, fixed in 31.1
  ([[task-31.1-frontmatter-type-refusal#r6]]), which ships before this task. {#fact-inbound-lost}
- 22.6 R4 called the row legacy and built its guard on a `tracked_files` clause that is
  always true. [[#r3-gmd]] states the rule against what the code does. {#fact-guard-premise}

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
| already orphaned by the old code | dropped by `vacuum`, counted and logged ([[#r5]]) | re-attached when resolvable, else deleted with a manifest (`plan-31 D14`, [[#r7]]) |
{#rule-table}

## Requirements {#requirements}

### R0: re-measure at base {#r0}

At the task's base (after 29.5): run `orphan_census.py` and `resolvable_split.py` on a fresh
read-only copy; run the
order probe's fixture; time [[#r5]]'s step 3 and [[#r7]]'s re-attach end to end, **with
commit**, on a writable scratch copy of the dev store's snapshot, and record the store-lock
hold it implies. **Then time it again under load** (ch-bsd r1 M6): a second process runs a
sync or flush loop against the same scratch store through its daemon while `vacuum` runs,
and the summary records how long that writer waited; `_op_vacuum` holds the store lock for
the whole call. The bands are judged on the loaded number. Bands, stated now: under 30 s, as
specified; 30 to 120 s, the step runs only in the announced store event and the summary says
so; over 120 s, step 3 is chunked by file with lock yields and the spec returns to the lead. Re-read 29.5's landed module map and
correct [[#layout]]'s file names in the summary. {#r0-body}

### R1: one definition of "learned" {#r1}

`edge_records.py` holds the two literals and the predicates: the evidence `detail` prefix
`learned from grep ` and the concept prefix `query/`; `is_learned_evidence(detail)`,
`is_learned_concept(name)`. The writer (`daemon._learn_grep_hits`) builds its strings from
them; the purge, `vacuum`, the replay and the census read them. A **learned file entity** is
a `code` or `doc` entity with at least one learned evidence row, or one that is `protected`
(today the same 405 rows, [[#baseline-learned-body]]). {#r1-body}

- **The learner's kind rule is the third thing defined once** (ch-bsd r1 M12). The learner
  decides `code` or `doc` from a literal suffix set of its own (`daemon.py:4598`), which is
  not `ingest.CODE_EXTS`: `.sh`, for one, is code to the ingest and a doc to the learner.
  [[#r7-rule]]'s condition E depends on that set, and `resolvable_split.py` copies it by
  hand. The set moves into `edge_records.py` as `learner_kind(path)`; the learner, the
  re-attach and the census script import it, and the script's copy goes at R0. The rule
  itself is not changed here. {#r1-kind}
- **A consequence that is already in the store:** all 8 `code` / `doc` pairs that share a
  name are `.sh` files, a protected learner `doc` twin beside the ingest's `code` row. The
  twin is a defect of its own, registered as bug-266 and not fixed here. Condition E
  matches the learner's twin, which is where a new learn of that file would write.
  {#r1-twin}

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
| `sync.py:271` and `ingest.py:1509`, the GMD dispatch's purge | **never `purge_path`**; `Store.purge_legacy_relpath_doc(rel, abs)` instead ([[#r3-gmd]]) |
| `rmx sync --invalidate P` (`cli.py:9014`, and whatever route R0 finds for a live daemon) | an existing **GMD** file: the GMD dispatch, never a whole-path purge ([[#r3-invalidate-gmd]]); any other existing path: `keep_learned=True`; a missing path: [[#r4]] |
{#r3-sites}

These are 22.6 R4's rules and its "two branches are not the same call"
([[task-22.6-removal-entry-points#r4]]), **stated without 16.6**. R4's text also keeps
"sidecar rows" and its AC-5 reads `learned_verify.matching_lines`; both belong to 16.6's
Wave-1 slice, which is post-mod and not built. Nothing in the keep rule needs them. It reads
only what is on `master` today: the evidence `detail` prefix `learned from grep `, the
`query/` concept namespace, `entity_links` and `entities.protected`. A sidecar row, when 16.6
exists, is keyed by the entity id this rule keeps unchanged, so 16.6 adds its clause without
changing this one. {#r3-source}

- **Composition with the memory-anchor keep (26.2).** `purge_path` already keeps the anchors a
  memory owns and raises `MemoryOwnershipError` before it deletes anything when ownership
  cannot be read. The order is: read the rows at the path; the memory-anchor keep (which may
  raise, leaving the path untouched and writing no manifest); the learned keep or the
  [[#r4]] manifest; the purge of the rest. A memory-owned anchor is never purged and never
  written to a manifest. {#r3-memory}
- **The GMD dispatch (ch-bsd r1 S6; split by ruling L144).** The relpath-named `doc` row is
  the semantic pass's own row for the file, made again by every sync
  ([[#fact-relpath-remade]]); the word "legacy" in the method's name is not a premise.
  **31.1 builds the method and the two call sites** (bug-264,
  [[task-31.1-frontmatter-type-refusal#r6]]): there it purges the relpath row whole and
  touches nothing else. **This task keeps the learned-row half:** it changes what the method
  does to a relpath row that carries a learned row, and narrows the guard. After this task
  `purge_legacy_relpath_doc(rel, abs)`:
  - touches only that one row: its non-learned links are unlinked and its non-learned
    evidence deleted (logged, with `evidence_clear`), so the semantic pass that follows
    writes this version's and none is doubled;
  - purges the row itself only when no learned row is on it; the semantic pass then makes it
    again. A row with a learned row keeps its id, its learned rows, its `query/` links and
    its `protected` flag;
  - never touches the doc-id row, its anchors or their inbound `rel:` edges;
  - never deletes the `tracked_files` row and logs no `untrack`: the path is the doc-id
    row's path too.

  The guard fires when the relpath row has at least one non-learned link or evidence row.
  22.6's third clause, "or a `tracked_files` row at its path", is dropped: it is always true.
  {#r3-gmd}
- **`rmx sync -i` runs on the writer (bug-203; ruling L136 (2)).** With a daemon up, `-i`
  reaches a store proxy that has no `purge_path` and falls through to the read replica. This
  requirement rewrites what `-i` does, so it also routes it: through the daemon's sync op
  family when a daemon answers, in-process otherwise, never the replica. T4's adopt list
  drops bug-203. {#r3-invalidate}
- **`-i` on an existing GMD file is a forced re-derive, not a purge** (ch-bsd r2 M4).
  `purge_path(abs, keep_learned=True)` on a GMD file would purge its doc-id row and every
  anchor with their inbound edges from unchanged citers: bug-264's shape, which 31.1 removed
  from the sync and ingest dispatch, and which AC-14's writer routing would otherwise make
  reachable on the daemon route. So for an existing GMD file `-i` takes the GMD dispatch:
  `purge_legacy_relpath_doc` (31.1's narrow purge, with this task's learned keep), then the
  GMD pass with the doc's content-hash and mtime gates bypassed, including 31.1's
  removed-anchor rule ([[task-31.1-frontmatter-type-refusal#r6-removed]]). The doc-id row,
  the anchors the text still has, and their inbound edges keep their ids. {#r3-invalidate-gmd}

### R4: a deleted or ignored file's learned rows leave through a manifest {#r4}

`purge_path(abs_path)` (the default, `keep_learned=False`) for a missing or ignored path
(`sync.py:249`, the missing half of `:253`, `vacuum` step 2, a missing `--invalidate` path):
when the path holds learned rows, a cleanup manifest is written and synced to disk **before**
anything is deleted; then the purge runs as today, with [[#r2]]. {#r4-body}

- **One manifest per batch, not per path** (ch-bsd r1 B2). `_sync_paths`, `vacuum`, a
  `sync -i` call and the code+docs markdown pass each open one manifest scope; every purge
  inside it that removes learned rows appends its records to that one file, and the file is
  created only when the first such record is written. A purge outside any scope opens its
  own. So a branch switch over many learned files writes one file, and a batch that removes
  no learned row writes none. {#r4-scope}
- **Retention.** No code deletes a manifest: it is the record of what was removed, and
  plan-22's manifests have no retention rule either. The file count is bounded by the
  number of batches that removed learned rows. A retention rule for `.refmatrix/removal/`
  is not built here: it is **bug-263**, post-mod, and [[#risk-manifests]] points at it.
  {#r4-retention}

- **The manifest** is `.refmatrix/removal/<id>.cleanup.jsonl`, the path and the record form
  22.6 R2 and 22.2 R4 give a cleanup manifest ([[task-22.6-removal-entry-points#r2]],
  [[task-22.2-repair-then-remove#r4]]), so that `removal_restore`, when it is built, reads
  these files and no second form exists. One `intent` record per learned file entity, with
  its before-state: the whole `entities` row with its id as `old_id` and its partition by
  name; every learned evidence row (`linkage`, the concept end by partition, kind and name,
  `file`, `line`, `span_end`, `detail`, multiplicity); every `query/` link (linkage, the other
  end by name, weight); and `reason` (`purge-path` or `vacuum`) with the path. A `commit`
  record follows once the delete has committed. Fields 22.2 lists that do not exist at base
  are absent (`protect_source`, sidecar rows). Ingest-derived rows are not in it: the file is
  gone and they cannot be restored to anything. {#r4-manifest}
- **An orphan row** (no live entity to hang an `intent` record on) is one `orphan_evidence`
  record: `{linkage, concept: {partition, kind, name, old_id} | null, dead_entity_id, file,
  line, span_end, detail, multiplicity, reason}`. It mirrors 22.2's `evidence_row` record,
  whose dead end is the concept; here the dead end is the entity. {#r4-orphan-record}
- **No vectors file, and the record says so.** 22.2's manifest also saves the vector of each
  removed entity. The vector of a file entity is derived from the file, and is not written
  here. Each `intent` record carries `vector: "not-saved: derived"` beside the row's
  `vectors_updated_at`, so that 22.2's reader, when it exists, re-embeds a restored file
  and does not read the absence as `vector_missing_at_intent`. ch-bsd accepted the
  departure on that condition (r1 M13). {#r4-vectors}
- **Logged:** one `learned_cleanup {partition, path, manifest, entities, links, evidence}`
  event, then the `tombstone`s. The replay needs only the `tombstone`s ([[#r6]]); the event is
  the record that the drop was audited. {#r4-event}
- **Fail closed.** If the manifest cannot be written, the learned rows of that path are kept
  (the path is purged with `keep_learned=True`), the failure is counted on the store and
  reported like a refused sync path. {#r4-fail}
- **A file that comes back** (a branch switch) starts with no learned rows; rows learned after
  the purge are appended after the `tombstone` and survive live and in the replay. {#r4-back}
- **No restore command.** 22.2's `removal_restore` is post-mod. The manifest is complete, in
  22.2's form, so that it, or a person, can re-apply it. {#r4-restore}

### R5: `vacuum` says what it drops {#r5}

Step 3 becomes "evidence with either end gone" (the concept side too: 34,451 rows today).
After [[#r2]] no new orphan is made, so this step only ever meets rows the old code left.
{#r5-body}

- **Ingest-derived orphans** (1,238,430 here) are deleted. Before the delete a manifest
  records them **as counts** per `(file, linkage, kind of row)`, not row by row: each row
  points at nothing and is re-derived by the next ingest of its file. The counts manifest
  is written and synced before the delete, and it fails closed like every other: if it
  cannot be written, step 3 deletes nothing and reports it (ch-bsd r1 M7). {#r5-derived}
- **Learned orphans** follow `plan-31 D14` as decided ([[#r7]]). {#r5-learned}
- **Result and output.** `vacuum()` returns, and `rmx vacuum` prints,
  `evidence_dropped: {derived, rel, learned}`, `learned_reattached`, and the manifest path.
  One `vacuum_evidence_drop {partition, derived, rel, learned, reattached, manifest}` event
  is logged. It is a summary, and is named apart from 22.6 R5's per-key `evidence_orphan_drop`
  so that op keeps its meaning for the day it is built. {#r5-report}
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
- `learned_cleanup` and `vacuum_evidence_drop` change nothing in the replay (their rows are
  already ended by a `tombstone`, or were never in a state the replay rebuilds). {#r6-records}

`_apply_event_body` (the incremental consumer, replica merge) applies `evidence_clear` the
same way; its `tombstone` already calls `purge_entity`, which now takes the evidence
([[#r2]]). `dump_catalog_to_log` is unchanged: with I1 there is no orphan for it to leave
out. {#r6-consumers}

**The two clears the replica never applied** (bug-260 and its sibling; ch-bsd r1 S4).
`_apply_event_body` has no case for `rel_evidence_clear` or for `pending_refs_clear`; both
are counted as `skipped_unresolved`. Reproduced by ch-bsd: after a `rel:` line is
re-targeted the writer holds 2 `rel:` evidence rows and a replica that applied the delta
holds 4 (`bsd31b-r1-bug260-probe.log`); a full rebuild agrees with the writer. Both events
get a case in `_apply_event_body`, each with the predicate `rebuild_index_from_log` uses for
it. `pending_refs_clear` is a second defect, registered as **bug-262** and fixed here.
{#r6-replica-clears}

### R7: the rows already orphaned (`plan-31 D14`, decided) {#r7}

Decided by the user on 2026-11-15, entered in [[plan-of-plans#decisions]] as `plan-31 D14`:
"migrate them if they can be resolved, if not, delete them". Resolvable rows are re-attached
to their current entity; the rest are deleted with a manifest, never silently. {#r7-body}

**The match rule.** A learned orphan is an evidence row whose `detail` is learned
([[#r1]]) and whose `entity_id` names no entity. It is **resolvable** when all three hold:

| # | Condition | Read from |
|---|---|---|
| C | its concept row exists and is a `query/` concept | `entities` by the row's `concept_id` |
| F | the file is on disk | the row's `file`, against the project root unless absolute |
| E | exactly one entity has the concept's partition, the kind the learner gives the row's `file` (`learner_kind`, [[#r1-kind]]) and `name` equal to the row's `file` | `entities`; the same `(kind, name)` a new learn of that file would write to |
{#r7-rule}

A row that fails is **not resolvable**; its reason is the first failing condition in the
order **C, F, E**. F is tested before E on purpose (ch-bsd r1 M16): `vacuum`'s step 2 purges
the entities of files that are gone before step 3 runs, so in the product such a row has no
entity either; with E first the dry run would say E where the census script, which reads a
catalog copy and the disk, says F. With F first both give the same reason, and [[#ac-9]]
compares the counts by reason, not only the totals. {#r7-reason}

**Conditional on Q38** ([[plan-of-plans#questions]], open with the user): whether the line
is part of "resolved". Both readings are written; the answer selects one and the other is
struck. {#r7-line}

| | Q38 (a): matched to the current entity (the lead's recommendation) | Q38 (b): the line still holds the pattern |
|---|---|---|
| The rule | C, F, E | C, F, E and **L**: the recorded line of the current file holds the row's pattern, by the read path's own test (`store.verify_evidence_rows`) |
| Is it testable as written | yes: three conditions on catalog rows and the disk | **not yet** (ch-bsd r1 M11). `verify_evidence_rows` takes `regex`, `ignore_case`, `word` and `variants` per call, and a learned row stores only its pattern, so L's flags are undefined. If (b) is chosen, the spec must first name the exact call and flags for a stored learned row, and `resolvable_split.py` must import that function; its count today (a literal match, else a regex match) is an estimate of L, not L |
| A resolvable row whose line moved | re-attached, and left for the read path, which serves a learned row only where the line still matches, as it treats a row an edit kept ([[#r3]]) | not resolvable, reason L: to the manifest, then deleted |
| Split on the second run | 29,824 re-attached, 307 deleted | 12,647 re-attached, 17,484 deleted |
| `(concept, entity)` pairs restored | 2,697 | counted at R0 (not split here) |
| What else changes | nothing | [[#r7-rule]] gains row L; AC-7 gains a row of class L; mutation "condition L dropped" is added; [[#r3]] is unchanged (an edit still keeps a learned row whose line moved, and the two rules then differ on purpose) |
{#r7-line-table}

Until Q38 is answered, [[#r7-reattach]], [[#ac-7]] and [[#ac-9]] below are written for (a).
{#r7-line-default}

**What `vacuum` step 3 does with them**, after step 2 has purged the entities of files that
are gone (so E is judged against what is left):

- **Resolvable:** the row's `entity_id` is set to the matched entity's id, in one set-based
  statement for the whole step; the `mentions` link from the concept is restored if absent
  and the entity is marked `protected` if it is not (the existing `link` and `protect`
  events); one `evidence` event per re-attached row is appended with the live names, so the
  replay holds the row after the old incarnation's `tombstone`. Rows are moved as they are,
  with their multiplicity: a row equal to one already attached (9 here) is still moved, as a
  second learn of the same hit would have added it. {#r7-reattach}
- **Not resolvable:** one `orphan_evidence` record per row ([[#r4-orphan-record]]) with its
  reason, written and synced to disk before the delete; then the delete; then the `commit`
  record. If the manifest cannot be written, no learned orphan is deleted and the step
  reports the failure ([[#r4-fail]]). {#r7-delete}
- **Counted:** `learned_reattached`, `learned_deleted` by reason, and the manifest id, in the
  result, in `rmx vacuum`'s output and in the `vacuum_evidence_drop` event; the dry run
  prints the same numbers and writes nothing. {#r7-counts}

Under Q38 (a) this leaves the store as [[#r3]] would have left it had the fix existed when
the edits happened. "The audited removal path" in the POP's D14 row is defined by ruling L134
(4): a dry run whose counts equal the measured split, the manifest written first in 22.6
R2's path and 22.2 R4's record form, a logged event, and the lead's backed-up run
([[#r9]]). plan-22's engine and its `--confirm` stay post-mod. {#r7-why}

### R8: every path reports {#r8}

The sync report gains `learned_kept` and `learned_manifested` (rows), added to the sync log
line when non-zero; `rmx sync` prints them. `rmx vacuum`'s line is [[#r5-report]]. A manifest
that could not be written is reported per [[#r4-fail]]. {#r8-body}

### R9: the store event {#r9}

The code changes no row until a `vacuum` runs. The store write is the lead's, announced and
backed up, never an agent's. **`vacuum` comes before any rebuild** (ch-bsd r1 M9): under the
new `tombstone` rule a rebuild from the log does not bring back a learned row that an old
purge orphaned, so a rebuild run first would lose the rows D14 keeps. `rmx rebuild
--from-log`, and the daemon op that calls `rebuild_index_from_log`, therefore count the
learned orphans of the current catalog first and refuse while there are any, naming
`rmx vacuum`; `--force` overrides, and when the catalog cannot be read the count is reported
as unknown and only `--force` proceeds. For the dev store, in the release: copy the snapshot and run
`orphan_census.py` and `resolvable_split.py`; `rmx vacuum --dry-run`, whose counts must equal
the split's; back up `catalog.read.duckdb`, `facts.log` and `active`; `rmx vacuum`; the
census again on a fresh copy and a read of the manifest ([[#ac-9]]). D14 is the user's go
for the dev store's orphans. Every other store is a separate user go, with its own census first
([[orchestration#release]] step 4). Until a store is vacuumed its orphans stay as they are.
{#r9-body}

## What this takes from 22.6, and what it leaves {#scope-22-6}

| 22.6 | Here | Left for 22.6, post-mod |
|---|---|---|
| R4 (an edit keeps learned rows) | whole: both branches, the guard, the ingest twin, `--invalidate`, the existing-unsupported file ([[#r3]]) | the sidecar clause, once 16.6 exists |
| R3 (a missing or ignored file) | the learned rows go to a manifest before the purge ([[#r4]]) | removal through 22.2's row primitives with one `evidence_remove` event per row; `removal_restore` |
| R5 (`vacuum`'s orphan delete) | counted, logged as one summary event, learned orphans by D14, a manifest for the learned rows it deletes ([[#r5]], [[#r7]]) | the per-key `evidence_orphan_drop` events, the key timeline and the revivable predicate; a row-level manifest of ingest-derived orphans |
| R1, R2, R6, R7, R9, R10 | nothing | all of it |
{#scope-22-6-table}

The plan's own text for this task ([[plan-31-pre-mod-loose-ends#t2]]) names the deleted
file and `vacuum`'s log, which are the learned-row halves of R3 and R5; they are taken in
the narrowed form above. Ruling L134 (2): that is within `#t2`'s scope and not a new
admission, and the freeze line now says so ([[plan-of-plans#freeze]]). {#scope-22-6-body}

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
  the learned row is kept. **Then A is edited and synced a second time**, through the real
  `_sync_paths` with its semantic pass (the relpath row exists after the first sync whatever
  the fixture did): the ids are still the first ones, B's edge is still live, the relpath
  row's semantic links are this version's and none is doubled, and the `tracked_files` row
  was never deleted (no `untrack` event in `facts.log`). The same through `rmx ingest` (the
  twin). The first draft's last leg, "a relpath row that is all learned does not fire the
  guard", is dropped: that state cannot be reached through a sync
  ([[#fact-relpath-remade]]). **RED** at base (E lines: the anchor has a new id; B's edge is
  gone) **only for the learned row**: after 31.1 the stable ids, B's live edge and the
  untouched `tracked_files` row already hold at this task's base, and those assertions are
  **characterization** here (31.1's AC-11 is their RED). What is RED here is that the
  learned row, its `query/` link and the `protected` flag on the relpath row survive both
  edits (E line: learned evidence 1 → 0). {#ac-2}
- **AC-3: a deleted file's learned rows are in a manifest before they go.** The fixture's
  deleted file, and a file that became ignored: a cleanup manifest exists whose `intent` record
  holds the entity, the link and the evidence row by name and the marker
  `vector: "not-saved: derived"`, with a `commit` record after it
  ([[#r4-manifest]]); a `learned_cleanup` event names it; the rows
  are gone from the catalog; the sync report says `learned_manifested: 1`. **RED** at base
  (E line: no manifest; the rows are orphaned). {#ac-3}
- **AC-4: the manifest fails closed.** With `.refmatrix/removal` made unwritable, the same
  sync keeps the learned rows, reports the failure, and exits non-zero on the CLI route.
  **RED** at base (no such path). {#ac-4}
- **AC-5: no purge leaves an orphan.** After each caller of [[#baseline-callers-table]] is
  driven once on a store with ingest evidence and learned evidence (sync edit, sync delete,
  `untrack`, `forget`, `prune-noise --drop`, `vacuum` steps 1 and 2, the doc → memory
  conversion), the count of evidence rows with either end gone is 0. Parametrised by caller.
  Every fixture carries evidence whose **`concept_id`** is the purged entity (a `rel:` row's
  concept is the citing doc, so purging the citer makes one): at base `vacuum`'s own step 3
  deletes entity-side orphans in the same call, and a `vacuum` leg with entity-side evidence
  only would pass at base (ch-bsd r1 M8). **RED** at base for every caller (E line: the
  orphan count). {#ac-5}
- **AC-6: `vacuum` reports and logs.** A store seeded with orphans of the three kinds (by
  deleting entity rows directly, the state the old code left): `vacuum(dry_run=True)` returns
  the counts and changes nothing; `vacuum()` returns the same counts, the counts manifest
  exists, one `vacuum_evidence_drop` event is logged, and `rmx vacuum` prints the line. Rows
  whose **concept** is gone are dropped too. With `.refmatrix/removal` unwritable, `vacuum`
  deletes no orphan of any kind and reports the failure. **RED** at base (E lines: no such
  keys; the concept-side rows remain). {#ac-6}
- **AC-7: resolvable rows are re-attached; the rest are in the manifest before they go
  (`plan-31 D14`).** On that seeded store, with one learned orphan of each class of
  [[#r7-rule]] (resolvable; concept gone; no entity of the learner's kind; file not on disk)
  and one resolvable row equal to an attached row:
  - the resolvable rows are on the matched entity, the `mentions` link and the `protected`
    flag are back, and an `evidence` event with the live names is logged for each;
  - each of the other three is gone from the catalog and is one `orphan_evidence` record in
    the cleanup manifest, by name, with its reason and multiplicity; the manifest's record
    count equals `learned_deleted`; its `commit` record is last;
  - the manifest is on disk **before** the delete: with the delete made to fail after the
    write, the manifest holds the three records and no `commit`, and the rows are still in
    the catalog;
  - with `.refmatrix/removal` unwritable, no learned orphan is deleted or re-attached and the
    failure is reported;
  - `vacuum(dry_run=True)` returns the same `learned_reattached` and `learned_deleted` and
    changes nothing.

  **RED** at base (E line: the rows are deleted with no manifest and no count). {#ac-7}
- **AC-8: the replay agrees.** For each scenario of AC-1, AC-2, AC-3, AC-6 and AC-7, and for
  the order probe's Q3, the multiset of evidence rows by `(linkage, concept name, entity
  name, file, line, detail)`, the links and the `protected` flags are equal between the live
  store and a second store rebuilt from its `facts.log`, and equal again after
  `dump_catalog_to_log` and a rebuild. **RED** at base (E line: the changed file's purged row
  is back, 3 rows against 2, as in the probe). {#ac-8}
- **AC-9: the dev store after its `vacuum`.** The run's `learned_reattached` and
  `learned_deleted`, **by reason**, equal the dry run's and `resolvable_split.py`'s on the copy taken just
  before (29,824 and 307 on the second run of 2026-11-15, under Q38 (a); the tree will have
  moved again). On a fresh copy afterwards: evidence with either end gone 0; learned orphans
  0; `(concept, file)` pairs linked up by the split's pair count (2,697 on that run). The
  manifest holds one record per deleted row. **Measurement**, on the
  lead's run. {#ac-9}
- **AC-10: the lock hold is bounded.** R0's timing, against its bands. **Measurement.**
  {#ac-10}
- **AC-11: one definition.** A static test over the string constants of `src/refmatrix/*.py`
  (docstrings excluded): the literal `learned from grep` occurs in `edge_records.py` only,
  and so does the learner's code-suffix set ([[#r1-kind]]).
  A unit test: for patterns holding quotes, spaces and a `/`, the detail and the concept
  name the writer's helpers build satisfy `is_learned_evidence` and `is_learned_concept`.
  The `query/` prefix also appears in help text and is not counted. **RED** at base
  (`daemon.py:4581` and `:4610` hold the literal). {#ac-11}
- **AC-12: the incremental consumer.** A replica that applies the log delta of AC-1's and
  AC-3's scenarios through `apply_log_delta` holds the same evidence as the writer. **RED**
  at base (E line: the replica keeps the purged entity's evidence, or lacks the op). Two
  more legs, for [[#r6-replica-clears]]: (i) the writer re-targets a doc's `rel:` line; the
  replica holds the writer's `rel:` evidence rows and no others. **RED** at base (E line: 4
  rows against the writer's 2, as ch-bsd's probe). (ii) the writer re-ingests a doc whose
  pending `rel:` line is gone; the replica's `pending_refs` equal the writer's. **RED** at
  base (E line: the cleared pending row is still on the replica). The replica lives under a
  project directory of the same name as the writer's: a copy under another name re-scopes
  the events to another partition and fakes the result (ch-bsd r1, Q5). {#ac-12}
- **AC-13: the memory-anchor keep still wins.** A path that holds a memory-owned anchor and a
  learned row: the anchor survives a purge with and without `keep_learned` and is in no
  manifest; with the memory's metadata made unreadable, `purge_path` raises
  `MemoryOwnershipError`, nothing at the path changes and no manifest is written.
  **Characterization** for the anchor, **RED** for "no manifest" (no manifest exists at
  base). {#ac-13}
- **AC-14: `rmx sync -i` reaches the writer (bug-203; ruling L136 (2)).** With a throwaway
  daemon up,
  `rmx sync -i <existing file>` keeps the file's learned rows and re-derives its ingest rows
  on the writer store, and `-i <missing file>` writes the [[#r4]] manifest. **A GMD leg**
  (ch-bsd r2 M4): docs `a` and `b` as in 31.1's AC-11, `a` unchanged on disk; `rmx sync -i a`
  through the daemon and in-process: `adoc` and `adoc#sec` keep their ids, `b`'s edges to
  `adoc#sec` are live, `a`'s content-hash stamp is rewritten (the pass ran in spite of the
  unchanged file), and a learned row on `a`'s relpath row is kept. **RED** at base
  (E line: the purge goes to the replica, or the learned rows are gone; for the GMD leg, the
  anchor has a new id and `b`'s edges are 0). {#ac-14}
- **AC-15: a manifest can be re-applied** (ch-bsd r1 M7, condition 1). A test reads the
  cleanup manifest AC-3 wrote and the one AC-7 wrote and re-applies each with store methods
  that exist today (`upsert_entity`, `link`, `add_evidence`, `set_entity_flag`): the
  learned evidence rows, the `query/` links and the `protected` flags it restores equal, as
  a multiset by name, what was there before the removal. This is what "complete, by name"
  means, proved by a test; it is not a restore command. **RED** at base (no manifest
  exists). {#ac-15}
- **AC-16: no rebuild before the vacuum** (ch-bsd r1 M9). On a store with one resolvable
  learned orphan, `rmx rebuild --from-log --yes` exits non-zero naming `rmx vacuum` and the
  count, and the catalog is untouched; with `--force` it rebuilds; after `rmx vacuum` it
  rebuilds without `--force` and the re-attached row is in the rebuilt catalog. The daemon
  op that calls `rebuild_index_from_log` refuses the same way. **RED** at base (E line: the
  rebuild runs). {#ac-16}

## Must-fail mutations {#mutations}

| # | Mutation | Must turn RED |
|---|---|---|
| 1 | `sync.py`'s edit branch calls `purge_path` without `keep_learned` | AC-1 |
| 2 | `keep_learned` keeps the entity but drops its `query/` links | AC-1 |
| 3 | `keep_learned` keeps the entity's ingest evidence too | AC-1 (ingest evidence is the new version's), AC-8 |
| 4 | the GMD site calls `purge_path(…, keep_learned=True)` instead of `purge_legacy_relpath_doc` | AC-2 (anchor ids, B's edge) |
| 5 | the GMD site's guard fires on the `tracked_files` row alone | AC-2 (a doc with no semantic links is purged and its events logged on every sync; asserted by an unchanged tombstone count) |
| 6 | the manifest is written after the delete | AC-3 with a write that fails: AC-4 |
| 7 | drop the evidence `DELETE` from `purge_entity` | AC-5 (the `purge_entity` callers), AC-8 |
| 8 | drop it from `_bulk_purge_ids` | AC-5 (`untrack`, `forget`, `vacuum`) |
| 9 | step 3 looks at the entity side only | AC-6's concept-side leg |
| 10 | `vacuum` logs no `vacuum_evidence_drop` | AC-6 |
| 11 | `dry_run` deletes | AC-6 |
| 12 | re-attach appends no `evidence` event | AC-8 (the AC-7 scenario) |
| 13 | the replay ignores a `tombstone` for evidence | AC-8 (the probe's Q3) |
| 14 | the replay ignores `evidence_clear` | AC-8 (the AC-1 scenario) |
| 15 | `_apply_event_body` ignores `evidence_clear` | AC-12 |
| 16 | re-attach binds to an entity of the same name in another partition | AC-7, with a two-partition leg |
| 17 | condition C dropped (a row whose concept is gone is re-attached) | AC-7 |
| 18 | condition E matches any `code` / `doc` entity of that name, not the learner's kind | AC-7, with a `doc` entity named like a `.py` file |
| 30 | E is tested before F | AC-7 (the file-gone row's reason is E where F is asserted) |
| 31 | the `intent` record omits the `vector` marker | AC-3, AC-15 |
| 32 | the learner keeps its own suffix set | AC-11's static leg (the set occurs outside `edge_records.py`) |
| 19 | the delete of the non-resolvable rows runs before the manifest write | AC-7's failing-delete leg |
| 20 | the learned keep runs before the memory-anchor keep | AC-13's unreadable-metadata leg (a manifest is written) |
| 21 | `-i` calls `purge_path` on whatever store it is handed | AC-14 |
| 33 | `-i` on an existing GMD file calls `purge_path(…, keep_learned=True)` | AC-14's GMD leg (new anchor id; `b`'s edges 0) |
| 34 | `-i` on a GMD file drops the relpath row and leaves the hash gate on | AC-14's GMD leg (the stamp is not rewritten; nothing was re-derived) |
| 22 | `_apply_event_body` ignores `rel_evidence_clear` | AC-12 (i) |
| 23 | `_apply_event_body` ignores `pending_refs_clear` | AC-12 (ii) |
| 24 | `purge_legacy_relpath_doc` deletes the `tracked_files` row | AC-2 (an `untrack` event appears) |
| 25 | `purge_legacy_relpath_doc` keeps the row's non-learned links | AC-2's second edit (the semantic links are doubled or stale) |
| 26 | each purge opens its own manifest inside a sync batch | AC-3, with two deleted learned files in one batch (two files where one is asserted) |
| 27 | the counts manifest is written after step 3's delete | AC-6's unwritable leg |
| 28 | the manifest omits the `query/` links | AC-15 |
| 29 | the rebuild does not count learned orphans | AC-16 |
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
(`evidence_clear`, `learned_cleanup`, `vacuum_evidence_drop`); R0 lists every reader of the
log by grep and the summary says which ignore, which fail and which were changed. {#census-ops}

## Files {#files}

By 29.5's map ([[#layout]]): `src/refmatrix/store_removal.py` (R2, R3, R4, R5, R7),
`src/refmatrix/store_replay.py` (R6), `src/refmatrix/edge_records.py` (R1; the manifest
writer), `src/refmatrix/sync.py` and `src/refmatrix/ingest.py` (R3's sites, R8),
`src/refmatrix/daemon.py` (`_learn_grep_hits`, `_op_vacuum`),
the `cli` module that holds `vacuum` and `_sync_in_process`. New
`tests/test_bug107_learned_evidence.py`. `docs/SYSTEM.md` (the evidence lifecycle, the
manifest format) and `docs/INTEGRATION.md` (`rmx vacuum --dry-run`). `workflow/bug_registry.md`
(bug-107, bug-247, bug-203, bug-259, bug-260, bug-262), the implementation summary.
22.6's own note that its R4 is built here, and its R3 and R5 in part, is written by 22.6's
freshness revision from [[#scope-22-6-table]]; this task does not edit 22.6. {#files-list}

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
  before this task. For ingest-derived evidence that is the fix. For learned evidence, the
  re-attach of D14 appends fresh events; a store rebuilt from its log **before** its
  `vacuum` would not have the legacy learned rows. The release note says: vacuum before any
  rebuild. {#risk-old-logs}
- **Stale lines stay.** Kept and re-attached learned rows may name a line that no longer
  holds the pattern. The read path drops them; they still count in table sizes. Their
  verification or removal is 16.6 and 22.1, post-mod. {#risk-stale-lines}
- **Protection widens the keep.** A file entity a user protected by hand is kept across
  edits like a learned one. None exists in the dev store today. {#risk-protected}
- **Manifests accumulate** under `.refmatrix/removal/`: one per batch that removed learned
  rows ([[#r4-scope]]), none otherwise. No code prunes them; the retention rule is bug-263,
  post-mod ([[#r4-retention]]). {#risk-manifests}
- **The rebuild guard reads the catalog it is about to wipe.** If that catalog is damaged
  the count is unknown and the rebuild needs `--force` ([[#r9]]). The daemon's repair path
  must pass it deliberately; R0 lists that caller and the summary says what it does.
  {#risk-rebuild-guard}
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

## Revision 1: fold of ch-bsd r1 (ruling L139) and of L136 {#rev-r1}

The review read `a4d245a`; D14, the manifest form and bug-260's leg had already changed at
`d788602` and `da184bd`.

| Finding | Fold | Where |
|---|---|---|
| B2 manifest retention is a deferral with no anchor | one manifest per batch, none when nothing learned is removed; retention named, with a registry row for the lead | [[#r4-scope]], [[#r4-retention]], [[#risk-manifests]], mutation 26 |
| S4 bug-260 folded by L132 but not in the spec | both replica clears get a case; AC-12 has both legs, RED by bsd's probe; two mutations; the sibling's own registry row | [[#r6-replica-clears]], [[#ac-12]], mutations 22, 23 |
| S5 D14 not written as decided; the rule not exact | decided (at `d788602`): the key is `file` = entity `name`, the learner's kind, the concept's partition, exactly one; the duplicate rule; the 11 are inside the 53. The line stays conditional on Q38 (L139) | [[#r7-rule]], [[#r7-reattach]], [[#r7-line]], [[#ac-7]], mutations 17, 18 |
| S6 the GMD-site guard assumes the relpath row is legacy | the row is re-made by every sync; the `tracked_files` clause is dropped; no untrack; AC-2 runs two real syncs and loses its unreachable leg | [[#baseline-relpath]], [[#r3-gmd]], [[#ac-2]], mutations 5, 24, 25 |
| M6 the lock hold is not timed under load | a second timing with a concurrent writer; the bands are judged on it | [[#r0]] |
| M7 "no restore command", two conditions | a test re-applies a manifest with existing store APIs; `vacuum`'s manifests fail closed, the counts manifest included | [[#ac-15]], [[#r5-derived]], [[#r7-delete]], [[#ac-6]], [[#ac-7]], mutations 27, 28 |
| M8 AC-5's vacuum legs pass at base without concept-side evidence | every fixture carries evidence whose `concept_id` is the purged entity | [[#ac-5]] |
| M9 "vacuum before any rebuild" is only a release note | the rebuild counts learned orphans and refuses without `--force` | [[#r9]], [[#ac-16]], mutation 29, [[#risk-rebuild-guard]] |
| M11 (updated report) Q38 (b) is not testable as written | both readings kept; the table says what (b) would need first | [[#r7-line-table]] |
| M12 the learner's kind rule is a second definition | `learner_kind` in `edge_records.py`; the `.sh` twin named for a registry row | [[#r1-kind]], [[#r1-twin]], [[#ac-11]], mutation 32 |
| M13 the vectors departure, one condition | the `intent` record says the vector was not saved because it is derived | [[#r4-vectors]], [[#ac-3]], mutation 31 |
| M14 Q39 withdrawn | folded at `9637f17` | [[#r3-invalidate]], [[#ac-14]] |
| M16 the reason order | C, F, E in the rule and the script; AC-9 compares by reason | [[#r7-reason]], [[#ac-9]], mutation 30 |
| L144: bug-264 moves to 31.1; bug-262, bug-263 registered | R3's GMD dispatch is split: 31.1 builds the method and the sites, this task keeps the learned-row half; AC-2's graph assertions become characterization; the ids are cited | [[#r3-gmd]], [[#ac-2]], [[#fact-inbound-lost]], [[#r6-replica-clears]], [[#r4-retention]] |
| M1 decisions not written as decided | D14 cited as decided; closures updated | header, [[#d14]] |
| L136 (2) | bug-203 unconditional | [[#r3-invalidate]], [[#ac-14]], mutation 21 |
| L134 (2), (4), (5) | folded at `da184bd` | [[#scope-22-6-body]], [[#r7-why]], [[#r4-vectors]] |
{#rev-r1-table}

## Revision 2: fold of ch-bsd r2 (ruling L147) {#rev-r2}

| Finding | Fold | Where |
|---|---|---|
| M4 `rmx sync -i` on an existing GMD file is still bug-264's shape | it takes the GMD dispatch (31.1's narrow purge with this task's learned keep, then a forced re-derive with the removed-anchor rule); a GMD leg on AC-14; two mutations | [[#r3-sites]], [[#r3-invalidate-gmd]], [[#ac-14]], mutations 33, 34 |
{#rev-r2-table}

## Decisions {#decisions}

Decisions live in [[plan-of-plans#decisions]] and [[plan-of-plans#rulings]]; this section
cites them and records none of its own. {#decisions-rule}

- **`plan-31 D14`, decided by the user (2026-11-15):** "migrate them if they can be resolved,
  if not, delete them". Amended into [[#r7]], [[#r5-learned]], [[#ac-7]] and [[#ac-9]]. The
  spec adds the match rule the decision needs ([[#r7-rule]]) and its measured split
  ([[#baseline-split-table]]). {#d14}
- **Q38, open with the user** ([[plan-of-plans#questions]]): what "resolved" means. (a)
  matched to the current entity: 29,824 re-attached and 307 deleted on the second run
  (30,078 and 53 on the first, the numbers the question quotes). (b) the line must still hold
  the pattern: 12,647 re-attached and 17,484 deleted (the question quotes 13,067 and 17,064,
  taken before the line count was split by resolvable row). Both are written at
  [[#r7-line-table]]. {#q38}
- **Ruling L136 (2):** Q39 is withdrawn. This task routes `rmx sync -i` to the writer
  (bug-203), unconditionally ([[#r3-invalidate]], [[#ac-14]], mutation 21). {#l136}
- **Ruling L147:** ch-bsd r2's finding here folds ([[#rev-r2]]). {#l147}
- **Ruling L144:** bug-264 is fixed in 31.1; this task keeps the learned-row halves of R3;
  bug-262 is fixed here; bug-263 is post-mod. {#l144}
- **Ruling L139:** all of ch-bsd r1 folds ([[#rev-r1]]); "no restore command" is accepted on
  its two conditions ([[#ac-15]]; [[#r5-derived]] and [[#ac-6]]'s unwritable leg). {#l139}
- **Ruling L132:** two departures from approved text go to ch-bsd to judge: ingest-derived
  orphans are recorded in the manifest as counts, not rows ([[#r5-derived]]; 22.6 R5 asked for
  every row, 834,201 then and 1.24 million now, and a row that points at nothing is
  re-derived by the next ingest of its file); and there is no restore command
  ([[#r4-restore]]). bug-259 and bug-260 fold in here by the same ruling. {#l132}
- **Ruling L134:** (2) the learned-row halves of 22.6 R3 and R5 are within `#t2`
  ([[#scope-22-6-body]]); (4) "the audited removal path" is defined ([[#r7-why]]); (5) the
  missing vectors file is a third departure for ch-bsd ([[#r4-vectors]]). {#l134}

**Design proposed by this spec, for review** (not ledger decisions): evidence follows its
entity at every purge, with the `tombstone` as its event ([[#r2]], [[#r6-tombstone]]); a
learned file entity is one with a learned row or the `protected` flag ([[#r1]]); conditions
C, E and F of the match rule ([[#r7-rule]]); `vacuum` gains a dry run and is the store event
([[#r5-dry-run]], [[#r9]]); the manifest fails closed ([[#r4-fail]]). {#decisions-proposed}

