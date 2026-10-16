---
gmd: "0.1"
id: bsd-plan16-22-spec-rereview-r6-0e77da3
title: "plan-16 + plan-22 spec re-review r6: round 5 closes 10 of 12 r4 findings, 2 are partial. d9an's dangling-link removal logs an event keyed by id that no replay reads, against 22.2 R3's own rule. A rebuild would bring the dead endpoints back (56 untombstoned doc entities and 1,129 link events in cliquedb's facts.log). The manifest form cannot record the rows, and the class has no partition. d9ak(b) is not in any spec."
severity: BULLSHIT
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-rereview-r6-16.1-16.6-22.1-22.6-d9an
round: 10 (plan-16) / 6 (plan-22)
tags: [bsd, audit, spec-review, removal, dangling-link, bug-111, facts-log, replay, provenance, d9an, d9ak]
---

# ch-bsd spec re-review r6: plans 16 and 22 after round 5 (`ef4abfa`) and d9an (`e07a17c`) {#root}

**Commit reviewed:** `0e77da3`, branch `wave0-spec-reviews`.
**Written:** 2026-10-14T23:54-0700.
**Author of the revisions:** Todd Holley / Opus 5.5 / orchestrator.

**Scope:**
- Every r4 finding: [[bsd-plan16-22-spec-rereview-r4-878647c]].
- The round-5 edits: 11 files, 733+/128−.
- d9an: 22.1a [[task-22.1a-provenance-free-classes#r1-dangling]], AC-8, and 22.2 [[task-22.2-repair-then-remove#r9]] with its new AC.
- The decisions d9z-d9an in [[plan-review-2026-10-14#t11-approvals]].

**Method (read-only):**
- **Store copies.** I made `cp -p` copies of cliquedb's and this repo's `catalog.read.duckdb`, plus cliquedb's `facts.log`, into the session scratchpad. They were read with `duckdb.connect(read_only=True)` or plain parsing from `.venv-eval/bin/python -I`.
- **Live logs, read in place.** cliquedb's `rmxd.log` and `cli.log`.
- **Transcript.** `b38025a7-….jsonl`, to check the appendix.
- **Source at HEAD.** `store.py`, `duckdb_catalog.py`, `ingest_gmd.py` and `daemon.py`.
- **What I did not touch.** I opened no `Store`, sent no daemon op, and edited no source, plan or spec.
- **Hook rewrites.** The PreToolUse hook rewrote two shell `grep` calls into the deployed `rmx grep`. One of them errored on a BRE `\|`. Both only read text.

rel: amends -> [[bsd-plan16-22-spec-rereview-r4-878647c]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[task-22.2-repair-then-remove#r3]]
rel: related-to -> [[bsd-bug111-r2-129366b]]

## Live evidence {#evidence}

### cliquedb's dangling rows, measured on a copy at 23:43 {#ev-dangling}

| measure | count |
|---|---|
| `entity_links` rows whose `entity_id` is not in `entities` (repair's `links_dead_entity`) | **5,298** (64 distinct dead ids) |
| ... of them with the concept also dead (both endpoints dead) | 7 |
| rows with a live entity and a dead concept (repair's `links_dead_concept`) | **1** |
| rows with a dead concept, counted regardless of the entity | 8 |
| dead-entity rows by linkage | `mentions` 5,184 · `part-of` 63 · `related-to` 33 · `amends` 7 · `reinforces` 5 · `depends-on` 5 · `supersedes` 1 |
| dead-entity rows with a NULL weight | 379 |
| entity ids that are in `concepts` but not in `entities` / rows with a dead `linkage_id` | 0 / 0 |
| this repo's store | 0 dangling rows of either kind |

The live daemon's own counters agree with the copy. Its `rmxd.log` line at 2026-10-14T23:43:03 reads `links_dead_concept=1 links_dead_entity=5298`. The spec's "8 `:concept` rows, all `part-of`" ([[#m-1]]) disagrees with both.

### facts.log still names the dead endpoints, and a rebuild brings them back {#ev-resurrect}

I parsed a copy of cliquedb's `facts.log` (201 MB; compacted 2026-10-08T02:17, last append 2026-10-08T17:56):
- **56 `(cliquedb, doc, name)` keys** have `entity` events, no tombstone, and no row in the catalog.
- Their names are memory slugs, for example `cliquedb-db-ops-gotchas`. That is the shape of bug-111's raw-DELETE as-memory drop.
- **1,129 `link` events** name one of these docs as `e`: `mentions` 1,022, `part-of` 56, `related-to` 33, `amends` 7, `depends-on` 5, `reinforces` 5, `supersedes` 1.

**What a rebuild does with them.** `rebuild_index_from_log` (`store.py:7883`) wipes the catalog and re-assigns every id through `upsert_entity`. It replays a link only when BOTH endpoint names resolve (`store.py:8076-8086`). So these 56 entities and their links come back. A removal event keyed by id can match nothing after that, because the ids are new.

**Why this has not happened yet.** The next compaction drops the entity events: `dump_catalog_to_log` emits only live entities, and its link query JOINs both endpoints (`store.py:7636-7650`). cliquedb's log is 201 MB, below the 256 MiB threshold, so it has not compacted again.

**Not filed.** The catalog is written daily, but cliquedb's `facts.log` has had no append since 2026-10-08T17:56. I did not find the cause. The orchestrator should confirm that the store logs at all before relying on a removal event there.

### purge never deletes evidence rows {#ev-evidence-orphans}

Neither `purge_entity` (`store.py:5990`) nor `_bulk_purge_ids` (`store.py:6363`) touches `linkage_evidence`. `vacuum` step 3 (`store.py:7307-7311`) deletes only rows whose ENTITY is dead.

| store | evidence rows, entity dead | evidence rows, concept dead and entity alive |
|---|---|---|
| cliquedb | 7,599 | **14,745** |
| refmatrix | 833,401 | **5,920** |

In both stores the dead-concept rows are mostly `rel:` edges: `depends-on`, `related-to`, `derives-from` and others.

### The appendix is now byte-exact {#ev-appendix}

- The fenced block in [[task-22.1a-provenance-free-classes#appendix-probe]] is 1,962 bytes, sha256 `c096e7ae…598a`, which is the value stated.
- The tool-use id `toolu_01AoQVrMA99DaazFFhpJEi53` is on transcript line 2687 (1-based), as stated.

## Round-4 findings: status {#prior-status}

| r4 id | status | the spec text that closes it, or what is missing |
|---|---|---|
| b-1 (hash on no line → `stale-line`) | **closed** | 22.1 [[task-22.1-audit-classes#r1]]: "The hash is a PAIRING key, never a staleness proof … no step below removes a row because of its hash; only step 4's leftovers are removable". Step 2: "none → the row FALLS THROUGH to step 3". New AC-5e, with the mutation "hash on no line of `N` → `stale-line`" (traced by hand: it removes row 10). Residue: [[#m-4]] |
| b-2 (compaction erases the sidecar, `source`, attribution) | **closed** | 16.6 R1d: "`dump_catalog_to_log` emits, per partition, one `learned_provenance` event per `learned_evidence` row … AFTER that partition's `evidence` events", plus AC-9b and its mutation. 22.6 R6: "emits `source` = `protect_source` on every `protect` event", plus AC-7b. 22.2 R5: "**Log adjacency is NEVER evidence** … WITHDRAWN". Plan-22 open item 9 is rewritten (line 253) |
| s-1 (GMD branch `purge_path` on every edit) | **partial** | The sub-bullet of 22.6 [[task-22.6-removal-entry-points#r4]] says "GMD … `purge_path` is NEVER called … `Store.purge_legacy_relpath_doc(rel, abs)`", and the guard skips all-learned entities (AC-5b, two mutations). But R4's lead sentence still says "Both edit branches … call `purge_path(abs, keep_learned=True)`" ([[#m-5]]) |
| s-2 (unclassified removal paths) | **closed, with stale text** | 22.6 [[task-22.6-removal-entry-points#r9]] table (pinned at `7f2014a`), R3 "Missing or ignored", R4 `--invalidate`, R7 `merge_partition` (d9ac). The `ingest_gmd` row describes code that 0.78.1 has already changed ([[#m-6]]) |
| s-3 (census `HOME` redirect) | **closed** | 16.6 R7 step 4: "the script's FIRST statement reads the real home from `pwd.getpwuid(os.getuid()).pw_dir` … An empty deny set is an error". Step 5: "REFUSES to run … unless `--candidate-trees` and `--home-base` are given". AC-5c (i)/(ii) with mutations |
| s-4 (confirm hash; direct-delete ops; fallback) | **closed** | 22.6 R1: "The confirm hash is the SELECTION, not the plan file … holds NO catalog identity". The `forget`/`memory_forget`/`memory_bulk_forget` ops "stop deleting on `dry_run=false`", and "No daemon-down fallback". AC-1b, AC-1c. `daemon.py` is in the file list |
| m-1 (appendix bytes; probe outside the procedure; no file list) | **closed** | Verified in [[#ev-appendix]]. 16.6 R7 lists `--census probe-reproduction`. 22.1a has its own files-to-modify |
| m-2 (churn bound under compaction; the instant) | **closed** | 22.1a AC-5b item 2: instant `09:29Z`, `undercounted (log compacted after the probe)` |
| m-3 (locale details) | **closed** | 16.6 R2 uses a `setlocale` probe in a child process (`UTF-8` loads). `rules_sha` has one `json.dumps(..., sort_keys=True, separators=(",",":"))`. 16.1 R10's lead-in list names `locale` |
| m-4 (rg `E`, `j`) | **closed** | 16.1 `#r1-clusters`: "rg `e f E g j m t T A B C d M r`", plus the `-E ENC` keep and `-j N` drop rows. 16.6 R2's lists match |
| m-5 (wave and test hand-over) | **closed** | 22.6 AC-5 "needs nothing from Wave 2". 22.6's file list rewrites 16.6 AC-11. Plan-22 `#dependencies` names d9t. New residue: [[#m-7]] |
| m-6 (`fold-concept-dups`) | **closed** | 22.6 R7: "`rmx memory dedup` (`cli.py:12628`) and MCP `rmx_memory` action `dedup` … there is no `rmx fold-concept-dups`" |

**Decisions.**
- d9z, d9ab and d9ac are reflected and cited.
- d9al (22.5 step 4, "A move is not a removal") and d9am (22.6 R6's four sources) are reflected but never cited.
- d9ak is neither cited nor reflected ([[#s-4]]).

## New findings {#findings}

### BULLSHIT b-1: a rebuild can undo d9an's removal, and its event breaks 22.2 R3's own rule {#b-1}

**The spec:**
- 22.2 [[task-22.2-repair-then-remove#r9]] (d9an): `remove_dangling_links(rows)` "logs one `link_remove{linkage, entity_id, concept_id}` event per row (by id: the dead endpoint has no name to key on)".
- Against it, 22.2 [[task-22.2-repair-then-remove#r3]]: "Add three ops, keyed by NAME (never by id)". R3 also gives the ONE post-evidence replay pass, which lists `learned_provenance`, `learned_provenance_move`, `evidence_remove`, `evidence_repoint`, `entity_rename` and `evidence_orphan_drop`. 16.6 R1d gives the same list. Neither list has `link_remove`.

**What is wrong:**

1. **No replay reads the event.** No replay path names `link_remove`, and no replay semantics are given. Pass 2 of `rebuild_index_from_log` ignores unknown ops. The event is written and never read.
2. **The event could not be replayed anyway.** Rebuild re-assigns every entity id (`upsert_entity` into a fresh catalog). A by-id event replayed after that matches nothing. Worse, it could match an unrelated row that now holds that id.
3. **The premise is false.** The dead endpoint DOES have a name, in `facts.log`. On cliquedb, 56 dead doc entities have `entity` events and no tombstone, and 1,129 `link` events name them ([[#ev-resurrect]]).
   - Rebuild re-creates all 56 entities and their links. The "removed" dangling rows return as LIVE rows on resurrected entities.
   - A compaction before the rebuild drops them instead. So whether the removal survives depends on the order of two unrelated daemon ticks.
4. **No AC checks this.**
   - 22.2 AC-3 (replay) has no dangling row in its fixture.
   - The dangling AC tests apply and restore, never a rebuild.
   - The sibling rule 22.6 [[task-22.6-removal-entry-points#r5]] (`evidence_orphan_drop`) avoided every one of these problems: `linkage`/`c` by NAME, explicit replay semantics, membership in the one pass, and AC-6 "no orphan resurrected".
5. **This is the pattern r4 b-2 named.** A new log event shipped without saying how replay and the compactor treat it. 22.6 R6 now requires "a `dump_catalog_to_log` clause and a compact-then-rebuild AC" for any new event or field.

**Why it is bullshit:** this removal is the declared owner of the bug-111 deferral, which `store.py:4383-4385` and `:4392-4393` cite as anchored. As written, a rebuild silently reverses it and brings back 56 deleted docs. The event it adds has no consumer.

**Fix (spec-only):**
- **R9.**
  - Name each dead endpoint from `facts.log` where the log can: the `link` events whose live end, linkage and other end identify it.
  - Log a `tombstone{kind, name}` (by NAME) for every dead endpoint whose `entity` event survives untombstoned. This is the record bug-111's raw DELETE never wrote.
  - Log the row removal as `unlink{linkage, c, e_kind, e}` by name when both names are known.
  - When the dead end has no name anywhere, state why: rebuild cannot recreate such a row, because link replay needs both names. Log no event for it.
- **R3.** Do not add a by-id op.
- **AC-3b, the dangling-link replay.**
  - Fixture: a sandbox store whose log holds a dead endpoint's `entity` event and two `link` events, with no tombstone, plus one row whose dead end is nameless.
  - Steps: `--apply`, then `rebuild_index_from_log` on a copy.
  - Expected: 0 dangling rows, the dead endpoint NOT resurrected, and `links_dead_*` = 0.
  - Mutations that must FAIL it: "log `link_remove` by id", and "no tombstone for the named dead endpoint".
- **Measure it first.** Have 22.1a AC-8b print, per store, how many dead ids the log can name, and how many entities a rebuild would resurrect (cliquedb today: 56 / 64).

rel: contradicts -> [[task-22.2-repair-then-remove#r3]]
rel: contradicts -> [[task-22.6-removal-entry-points#r6]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### SKETCHY s-1: 22.2 R4's manifest has no record form for a dangling row, and restoring by id after a rebuild attaches the row to the wrong entity {#s-1}

**The spec:**
- 22.2 R9: "writes each row (with its weight) to the apply manifest ([[task-22.2-repair-then-remove#r4]]) so restore re-inserts it".
- R4: the links are recorded as "every link (linkage name, other end by name, weight)", and "This is ONE record form for every manifest plan-22 writes". "Restored entities get new ids; restore is checked by NAME."

**What is wrong:**
- **The form cannot hold the row.** R4's record is per touched ENTITY, and it names the other end of a link by name. A dangling row's dead end has no catalog name, and both-dead rows (7 on cliquedb) touch no live entity at all. The one record form cannot express them.
- **The obvious workaround breaks after a rebuild.** An implementer will record raw ids. Restoring by raw id after an intervening rebuild or rename then re-attaches the row to whatever entity now holds the live endpoint's old id.
- **The AC cannot see it.** It restores on the same, quiet catalog.
- **The bits are not covered.** Restore says nothing about the fragment bits R9 removed. Not re-adding them is consistent with `repair_fragments`, but only by accident.

**Fix:**
- Add a `link_row` intent record: `{linkage, live_end: {partition, kind, name, old_id} | null, dead_end: {side, old_id, name_from_log | null}, weight}` (`weight` may be NULL; 379 such rows on cliquedb).
- Restore resolves the live end BY NAME and re-inserts with the dead id. It re-adds no bit, and says so.
- AC: apply, then a rename or a rebuild on a copy, then restore. The row re-attaches to the NAMED live entity. The mutation "restore by recorded live id" FAILS it.

rel: contradicts -> [[task-22.2-repair-then-remove#r4]]

### SKETCHY s-2: `dangling-link` has no partition, but the audit and the apply are partition-scoped {#s-2}

**The spec:**
- 22.1a [[task-22.1a-provenance-free-classes#r3]]: the classifier's inputs carry `partition`.
- R4: the plan records ONE partition.
- 22.2 R6: each batch "binds its partition".
- AC-8: the counts equal `repair_fragments`'s.

**What is wrong:**
- **No partition to assign.** `entity_links` has no partition column (`duckdb_catalog.py:115-121`). A dead endpoint has no partition, and a both-dead row (7 on cliquedb) belongs to no partition at all.
- **The counts cannot match.** `repair_fragments` counts across the whole store. cliquedb has two partitions, `cliquedb` and `sessions-cliquedb`. A partition-scoped audit never selects the 7 both-dead rows, so AC-8b reads `drift` on cliquedb forever. Summing two partition audits double-counts nothing, but still misses those 7.
- **The bits can be anywhere.** "Any fragment bit they still own" has no partition either. bug-105 showed that a dead id's bit can sit in ANY partition's fragment row.

**Fix:**
- Declare `dangling-link` a STORE-scope class. It is audited once per store whatever `partition` says. Each member records its live endpoint's partition, or `none`.
- The apply binds that partition per batch, or runs a `none` batch with the rows deleted by key.
- `remove_dangling_links` clears the bit from every partition's fragment row.
- AC-8a gains a two-partition fixture with a both-dead row. The audit count must equal the repair's. The mutation "audit only the bound partition" FAILS it.

rel: contradicts -> [[task-22.1a-provenance-free-classes#r3]]

### SKETCHY s-3: evidence rows whose concept is dead belong to no class, purges keep creating them, and 22.6 R9 says purge removes evidence when it does not {#s-3}

**The spec:**
- d9an covers `entity_links` only.
- 22.6 [[task-22.6-removal-entry-points#r5]] covers evidence rows whose ENTITY is gone.
- 22.1a R2 excludes ingest evidence.
- 22.6 R9 says `purge_entity` leaves "links and evidence unlinked with their events, so a rebuild cannot resurrect the row".

**What is wrong ([[#ev-evidence-orphans]]):**
- **The R9 claim is false.** Neither purge deletes a `linkage_evidence` row.
- **Every purge of a concept or doc leaves a row behind.** That includes the purges this plan adds: 22.2 R2, 22.6 selector members and 22.5 moves. Each evidence row that names the purged entity as its concept stays, with a dead concept.
- **Nothing removes those rows.** 14,745 (cliquedb) and 5,920 (refmatrix) such rows with a live entity exist today, and no class, vacuum step or entry point owns them.
- **They are the same defect.** They come from the same bug-111 mechanism as the dangling links, one table over.

**Fix:**
- Either widen 22.6 R5 to `concept_id NOT IN entities`, with its event keyed by the live `e` by name, the dead concept id and the manifest id. Or add a `dangling-evidence` sub-class to 22.1a with the same predicate and partition rule as [[#s-2]].
- Correct R9's sentence.
- AC: purging a doc that is another doc's `rel:` target leaves 0 evidence rows naming the dead id, after the class or vacuum runs.

rel: contradicts -> [[task-22.6-removal-entry-points#r9]]

### SKETCHY s-4: d9ak(b) is in no spec, and 22.2 R5 says it is not a rule {#s-4}

**The decision:** [[plan-review-2026-10-14#t11-approvals]] d9ak: "(b) a `cli.log` `rmx grep P` record counts as learner evidence for concept `query/P` (217 here, 90 global …)". The user approved it ("7 a and b").

**The spec:** 22.2 [[task-22.2-repair-then-remove#r5]] still reads "For information only (not a rule): treating a `cli.log` `rmx grep PATTERN` record as a learner record … would attribute 217 … and 90", and "Only `protect_source = 'learner'` … makes a learned-only entity purgeable".

**What is wrong:**
- No plan-22 file cites d9ak, d9al or d9am.
- d9ak(a), d9al and d9am happen to match the text. d9ak(b) is contradicted.
- Built as written, 22.2 keeps all 217 + 90 entities that the user ruled purgeable.

**Fix:**
- Make R5 rule (b):
  - define the record: a `cli.log` row whose argv is a grep with pattern `P`, matched to the concept `query/P`;
  - define its scope: it attributes only the learned-only entities that carry that concept's `mentions` link;
  - recount it: 217 / 90.
- Add an AC with the mutation "ignore `cli.log` grep records", which must FAIL it.
- Add revision rows citing d9ak, d9al and d9am.

rel: contradicts -> [[plan-review-2026-10-14#t11-approvals]]

### MEH m-1: the measured numbers in 22.1a and d9an are wrong {#m-1}

- **The `:concept` count.** [[task-22.1a-provenance-free-classes#r1-dangling]] says "5,298 `:entity` rows … and 8 `:concept` rows, all `part-of`", and the d9an row says "8 dead-concept". Under the spec's own rule ("a row with both dead is `:entity`"), 7 of the 8 are `:entity`, so `:concept` = **1**, as the live repair reports.
- **"All `part-of`".** That holds only for the 8 dead-concept rows. The 5,298 dead-entity rows are 5,184 `mentions`, 63 `part-of`, 33 `related-to` and 18 across four other verbs ([[#ev-dangling]]).
- **Fix:** restate the counts as `5,298 :entity (7 with both ends dead) + 1 :concept`, with the per-linkage split.

### MEH m-2: the liveness text is not the code it claims to equal {#m-2}

- **The entity side.** The spec says the `entity_id` side is alive if it is in `entities` ∪ `concepts`, and that this is "EXACTLY `Store.repair_fragments`'s definition". The repair checks the entity side against `entities` ONLY (`ent_part.get(eid)`, `store.py:4382`).
- **When it matters.** The two differ only for a `concepts` row with no entity. The schema forbids that (`store.py`: "equals entities.id where kind='concept'"), and both stores have 0 today.
- **Dead linkage ids.** The repair counts a row with a dead `linkage_id` under `links_skipped` and never checks its concept. The spec's predicate is silent on linkage.
- **Fix:** state the predicate the code runs, side by side for each endpoint, including the dead-linkage case.

### MEH m-3: AC-8's equality cannot fail, and 8b has no procedure {#m-3}

- **The equality is guaranteed.** AC-8a mandates ONE shared predicate in `store.py`. Its "counts equal `repair_fragments`'s" then compares a function with itself.
- **One mutation is not a test.** "A second liveness definition … is refused by review" is a review step that cannot turn a test RED.
- **8b cannot run as written.** AC-8b prints "the repair's counters" on COPIES, but 16.6 R7 forbids constructing a `Store` in a census. Neither 16.6 R7 nor 22.1a's file list names a `dangling-link` census.
- **Fix:**
  - Compare against an independent SQL recount, as AC-6b does.
  - Add a mechanical sharing check: an AST test that `removal_audit.py` holds no `FROM concepts` or `FROM entities` liveness SQL and calls the store function.
  - For 8b, read the live repair counters from the store's `rmxd.log` line, read-only.
  - Add `--census dangling-link` to 16.6 R7.

### MEH m-4: two of 22.1's new mutation claims are wrong, and 5e's set class is undefined {#m-4}

- **A mutation that changes nothing.** "Mutation 'fixed point by line only, ignoring a differing hash' FAILS 5b" is false. In 5b, `N = {10, 29}` and only row 10's line is in `N`, with an equal hash. The mutation gives the same result. It fails AC-2 (the swap) instead.
- **5e's set has no class.** Row 10 is a step-3 STAY: neither a fixed point nor a re-point. The four set classes (`shrunk` / `grown` / `moved` / `ok`, where `ok` means every row is a fixed point) then classify nothing. AC-5e accepts "`ok` or `moved`".
- **Fix:**
  - Attach that mutation to AC-2.
  - Define `ok` as "every row is a fixed point or a stay".
  - Make AC-5e assert `ok`.

### MEH m-5: 22.6 R4's first sentence still gives the r4 s-1 defect {#m-5}

- **The contradiction.** [[task-22.6-removal-entry-points#r4]] opens "Both edit branches of sync (the GMD dispatch's legacy purge … and the non-GMD …) call `purge_path(abs, keep_learned=True)`". Its own sub-bullet says the GMD branch NEVER calls `purge_path`. AC-5b pins the sub-bullet, but the requirement contradicts itself.
- **Fix:** rewrite the lead so it names the two different calls.

### MEH m-6: claims about current code went stale with the 0.78.1 merge {#m-6}

- **`ingest_gmd`.** 22.6 R9 says `ingest_gmd --as-memory` does "a raw `DELETE FROM entities … kind='doc'` (`ingest_gmd.py:891-896`)". Since 0.78.1 (bug-111) it is `purge_entity` (`ingest_gmd.py:897-910`), so only the learned-row manifest is left to build.
- **`merge_partition`.** 22.6 R7 says it builds on the bug-105 hotfix "once the hotfix is MERGED TO MASTER". It is merged, and d9ae fenced live merge (`daemon.py:4051`).
- **Line numbers.** The citations not pinned to a sha are now ~300 lines off:

  | symbol | cited | actual |
  |---|---|---|
  | `dump_catalog_to_log` | `store.py:7210` | 7527 |
  | `_bulk_purge_ids` | `6032` | 6363 |
  | `vacuum` | `6943` | 7260 |
  | `set_flag_by_selector` | `6003` | 6286 |
  | `_compact_factslog_if_needed` | `daemon.py:2274` | 2307 |

- **Fix:** re-pin each citation to a sha, or cite it by symbol. Update the `ingest_gmd` and R7 rows.

### MEH m-7: bookkeeping for d9an and the wave order {#m-7}

- **The plan document.** Plan-22's task table (line 156) and `#scope` do not list `dangling-link`.
- **The new AC.** 22.2's dangling AC is an unnumbered bullet placed before AC-1, so nothing can cite it by number.
- **The new method.** `remove_dangling_links` is a new `Store` method, but no file list names it. 22.2 has no files-to-modify section.
- **The wave order.** It reads `22.2 → (22.5 ∥ 22.6)` (line 169), while 22.2 R5 needs 22.6 R6's `protect_source`. Only a footnote at line 188 says this. Name the split: 22.6 R6 lands in 22.2's slice.

## Conflicts with `repair_fragments` and the other classes {#conflicts}

- **No write conflict.** `repair_fragments` only counts dangling rows and leaves them in place (`store.py:4380-4395`). Its apply drops their bits into its own manifest, and 22.2 R9 deletes the rows. Running both in either order is safe. After a 22.2 restore, the row is back without its bit, which matches what the repair keeps.
- **No cascade into vacuum.** On cliquedb, removing the 5,298 rows leaves 0 concepts without a live link (checked on the copy). So `vacuum` step 1 would purge nothing more. The class has no hidden cascade today.
- **The ingest overlap is handled.** A dangling row whose live end is ingest-owned is selected on purpose, and 22.1a states this.
- **The real conflict is with replay** ([[#b-1]]) and with the manifest's one record form ([[#s-1]]).

## Verdict {#verdict}

**Plan-16: APPROVABLE** for 16.1-16.6. Every r4 item in plan 16 is closed, and nothing new touches it except [[#m-3]]'s census name.

**Plan-22: NEEDS-REVISION.**
- 22.2: [[#b-1]], [[#s-1]], [[#s-4]].
- 22.1a: [[#s-2]], [[#m-1]], [[#m-2]], [[#m-3]].
- 22.6: [[#s-3]], [[#m-5]], [[#m-6]].
- 22.1: [[#m-4]].
- Plan: [[#m-7]].

| | r4 closed | partial | open | new B | new S | new M |
|---|---|---|---|---|---|---|
| plan-16 | 3 (m-3, m-4, plus shared items) | 0 | 0 | 0 | 0 | 0 |
| plan-22 | 7 | 2 (s-1, s-2 stale) | 0 | 1 | 4 | 7 |

**Totals.**
- **r4 ids:** 10 closed, 2 partial (s-1, s-2), 0 open.
- **New:** 12 findings, 1 BULLSHIT, 4 SKETCHY, 7 MEH.
