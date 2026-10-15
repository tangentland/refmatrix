---
gmd: "0.1"
id: bsd-plan16-22-spec-rereview-r7-331b414
title: "plan-16 + plan-22 spec re-review r7: round 6 closes 9 of 12 r6 findings and leaves 2 partial. The link side is now replay-safe, verified against the code, and the cliquedb naming counts reproduce (64/56/8). New BULLSHIT: R3's one replay pass applies evidence_remove after EVERY evidence append, later ones included. The reviser names this in r9-dangling and routes around it there, but the new R2 rule and 22.6 R3 use evidence_remove anyway, so a rebuild deletes rows the live store holds."
severity: BULLSHIT
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-rereview-r7-16.6-22.1-22.1a-22.2-22.5-22.6
round: 11 (plan-16) / 7 (plan-22)
tags: [bsd, audit, spec-review, removal, dangling-link, dangling-evidence, replay, facts-log, d9aq, d9ar, d9ak]
---

# ch-bsd spec re-review r7: plans 16 and 22 after round 6 (`331b414`) {#root}

**Commit reviewed:** `331b414` on branch `wave0-spec-reviews`. HEAD has since moved to `0611d2f`, a hooks fix, but no plan-16, plan-22 or `store.py` byte differs between the two.
**Written:** 2026-10-15T00:32-0700.
**Author of the revisions:** Todd Holley / Opus 5.5 / spec-reviser (Wave 0 revision round 6).

**Scope:**
- Every r6 finding: [[bsd-plan16-22-spec-rereview-r6-0e77da3]].
- The round-6 edits: 8 files, 623+/113-.
- The decisions d9aq, d9ar and d9ak(b), in [[plan-review-2026-10-14#t12-approvals]] and [[plan-review-2026-10-14#t11-approvals]].

**Method (read-only):**
- **Source at HEAD.** `store.py` (`rebuild_index_from_log`, `_apply_event_body`, `_log_event`, `link`/`unlink`/`add_evidence` logging, `repair_fragments`, `_clear_purged_bits`, `purge_entity`, `_bulk_purge_ids`, `dump_catalog_to_log`, id sequences), `daemon.py`, `telemetry.py`, `ingest_gmd.py`.
- **Store copies.** The naming counts were re-derived on the r6 auditor's scratch copies (`scratchpad/r6/clique.duckdb` and `clique.facts.log`) with `.venv-eval/bin/python -I` and `duckdb read_only=True`. Scripts and logs are in `scratchpad/r7/`.
- **Live files, read in place.** cliquedb's `rmxd.log` (read in place, never opened as a store) and this repo's `cli.log`.
- **What I did not touch.** I opened no `Store` and no socket, edited no spec or source, and made no commit. The PreToolUse hook rewrote my shell `grep` calls to the deployed `rmx grep`, which only reads text.

rel: amends -> [[bsd-plan16-22-spec-rereview-r6-0e77da3]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[task-22.2-repair-then-remove#r3]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

## Code facts verified {#code-facts}

| claim in the specs | at HEAD | verdict |
|---|---|---|
| rebuild drops an entity when a tombstone's `ts >=` the key's latest `entity` event | `store.py:7978-7981` collects, `:8043-8045` skips | true |
| link/unlink is last-wins per `(partition, linkage, c, e_kind, e)` | `:7992-7996`, materialized `:8076-8085` | true |
| an event's partition is `ev.partition or` the store's bound partition | `:7931`, `:7953`, `:8088` | true. The specs call it "the store's default"; it is the rebuild's binding |
| `_log_event` adds no `partition` | `:1117-1131` (`{"ts", "op", **fields}`) | true. Only `dump_catalog_to_log` writes one (`:7591-7690`) |
| incremental replay resolves by name and counts misses | `_apply_event_body` `:7813-7839`; `apply_log_delta` returns `skipped_unresolved` | true. A tombstone for an absent key returns False and is counted |
| `_clear_purged_bits(bits_by_ln, ids)` clears every partition | `:6315-6361` | true. The signature matches |
| repair liveness: entity side `entities` only; dead linkage counted `links_skipped` only; concept side `entities` ∪ `concepts` | `:4360-4395` | matches the 22.1a predicate table exactly |
| `purge_entity` / `_bulk_purge_ids` delete no `linkage_evidence` | `:5990-6090`, `:6363-6440` (no such DELETE) | true |
| `link_liveness` / `LinkLiveness.dead_side` | not in `src/` | PROPOSED, and listed in 22.1a's file list. Not a false existence claim |
| `rmxd.log` carries `repair_fragments dry_run=` lines | `daemon.py:5331`; cliquedb has 7, latest 23:43:03 `links_dead_concept=1 links_dead_entity=5298` | true |
| `cli.log` records hold `argv` with `argv[0] == "grep"`, no rotation | `telemetry.py:253-290`; this repo has 32,154 grep records of 94,903 | true |
| learner concept is `query/{pattern}` verbatim | `daemon.py:4244` | true |
| round-6 line pins in 22.6 `#facts` | `dump_catalog_to_log` 7527, `_bulk_purge_ids` 6363, `vacuum` 7260, `set_flag_by_selector` 6286, `purge_entity` 5990, `_compact_factslog_if_needed` 2307, `_learn_grep_hits` 4237 | all exact |
| 17.1 R1 defines `invoked_by="removal_restore"` | `task-17.1` lines 82-108 (6db632b) | consistent with 22.2 R4 / AC-4b |

**Not in any spec, but load-bearing for item 2.** Rebuild resolves a link's or an evidence row's `c` ONLY as kind `concept`:
- rebuild: `name_to_id.get(("concept", c))`, `store.py:8080` and `:8090`;
- incremental replay: `get_entity("concept", …)`, `:7827` and `:7841`;
- the cause: `link` and `add_evidence` log `c = name` with no kind (`:4663-4667`, `:5587-5592`).

So a typed edge whose concept is a doc or memory entity is never rebuilt, whether that edge is a `rel:` link or a `rel:` evidence row. On cliquedb, every one of the 14,745 dangling-evidence rows has a `rel:` detail. This is a pre-existing gap and not filed here. It does mean a tombstone cannot be what stops such an evidence row from replaying, because the row never replays.

## Spot-check of the reviser's cliquedb numbers {#spot-check}

`scratchpad/r7/naming.py`, `naming.log`, `naming3.log`:

| measure | spec | re-derived |
|---|---|---|
| dead entity ids / rows | 64 / 5,298 | 64 / 5,298 |
| `:concept` rows | 1 | 1: `(724972, part-of, 2791209)` |
| would-resurrect keys | 56 | 56, all `(cliquedb, doc, *)` |
| named / ambiguous / nameless / unclaimed | 56 / 0 / 8 / 0 | 56 / 0 / 8 / 0 |

**What the spec gets wrong about the 8.** It says the nameless ids are "ids 2791202-2791209, whose rows no single logged name covers". That is false:
- 7 of the 8 are FULLY covered by one logged name, and the 8th is covered on 3,458 of its 3,459 rows.
- The names are `cliquedb/architecture-index` and its seven section concepts (`#root`, `#entry-points`, `#topic-docs`, `#adr`, `#concepts`, `#explorations`, `#tech-stack`).
- Each name is LIVE again in the catalog under a new id (3219330-3219337), and the reborn entity carries the same rows (4/4, 10/10, 81/81, 112/112, 3458/3459, 9/9, 474/474, 13/13).
- They are nameless only because of naming condition (ii): the key has a catalog row. They are *reborn*, not unnamed. See [[#m-1]].

**The evidence side** (`evname.py`, `evname.log`, `evname2.log`): 14,745 dangling-evidence rows over 4,778 dead concept ids, and 0 of the ids are NAMED.
- 843 are covered by a logged `c` name, but that name is a live `concept` entity, reborn, that already holds the identical rows.
- The other 3,935 have no covering `evidence` event.

So on cliquedb today, d9ar's tombstone branch applies to no id at all.

## Round-6 findings: status {#prior-status}

| r6 id | status | the spec text that closes it, or what is missing |
|---|---|---|
| b-1 (id-keyed `link_remove`; a rebuild resurrects) | **closed** | 22.2 [[task-22.2-repair-then-remove#r3]]: "No op keyed by id, ever … `link_remove{linkage, entity_id, concept_id}` is WITHDRAWN". [[task-22.2-repair-then-remove#r9-dangling]] step 4: "one `tombstone{kind, name}` carrying the `partition` field exactly as its surviving `entity` event carries it … one `unlink{linkage, c, e_kind, e}`". Step 5: "A NAMELESS dead endpoint logs nothing, by design". I traced AC-3b against `store.py:7950-8085`: "log `link_remove` by id" leaves no tombstone, so `D` resurrects with both links (FAILS). "No tombstone" lets `D` resurrect (FAILS). "Tombstone without partition" is keyed on `p1` while the entity event is keyed on `p2`, so `D` survives in `p2` (FAILS). The counts reproduce ([[#spot-check]]). Residue: [[#b-1]], [[#m-1]], [[#m-3]] |
| s-1 (no manifest form; restore by id) | **partial** | `link_row` / `evidence_row`: "Restore … resolves the live end BY NAME … re-inserts the row with the recorded DEAD id unchanged". AC-4c mutation "restore by recorded live id" FAILS (traced). But the recorded DEAD id is not re-checked, and after a rebuild it can name a live entity ([[#s-1]]) |
| s-2 (no partition) | **closed** | 22.1a `#r1-dangling` "Store scope … audited ONCE per store … Each member records its LIVE end's partition, or `none`". 22.2 R6 "Store-scope members". 22.1a AC-8a's mutation "audit only the bound partition" FAILS on the `p2` and `none` members. 22.2 AC-14's mutations "clear the bit in the bound partition only" and "skip the `none` batch" both FAIL |
| s-3 (dead-concept evidence) | **closed** | 22.1a `dangling-evidence`. 22.6 [[task-22.6-removal-entry-points#r9]]: "It unlinks LINKS only". 22.2 R2's purge rule. AC-3c and 22.6 AC-9b: the mutation "`vacuum` step 3 also deletes dead-concept rows" makes "vacuum alone leaves the row" FAIL. Residue: [[#b-1]], [[#s-2]], [[#m-4]] |
| s-4 (d9ak(b) in no spec) | **partial** | 22.2 [[task-22.2-repair-then-remove#r5-grep-record]] gives the record, scope, precedence and 217 / 90. AC-6c: "ignore grep records" leaves G kept (FAILS); "case-insensitive" purges H (FAILS); "grep beats user record" purges U (FAILS). But 22.3 and R5's own earlier sentence still say no existing entity is purged ([[#s-3]]) |
| m-1 (counts) | **closed** | 22.1a "Measured" table: 5,298 / 7 / 1 / 14,745, the linkage split, and 379 NULL weights. Residue: the reason given for the 8 ([[#m-1]]) |
| m-2 (liveness text vs code) | **closed** | The predicate table matches `store.py:4360-4395` line for line, `dead-linkage` included |
| m-3 (AC-8 tautological; 8b procedure) | **closed** | AC-8a "INDEPENDENT SQL recount written in the test". AC-8c's AST check, with two mutations. 16.6 R7 `--census dangling-link` reads `rmxd.log` in place. Residue: [[#m-2]] |
| m-4 (22.1 mutations; `ok`) | **closed** | `ok` = "every row is a fixed point (step 1) or a stay (step 3)". AC-2: with lines swapped, "fixed point by line only" leaves each row on the other's text (FAILS). AC-5e: "a stay counts as a re-point" reads `moved` (FAILS) |
| m-5 (22.6 R4 lead) | **closed** | "through two DIFFERENT calls (r6 m-5): … `purge_path(abs, keep_learned=True)`, and … `Store.purge_legacy_relpath_doc(rel, abs)`" |
| m-6 (stale code claims) | **closed** | 22.6 `#facts` "Re-read at `3d3c798`". Every pin is exact ([[#code-facts]]). The `ingest_gmd` and `merge_partition` rows are corrected |
| m-7 (bookkeeping) | **closed** | Plan-22 `#scope` and the task table name both sub-classes. AC-14 is numbered. 22.2 now has a `#files-to-modify`. The wave split is named: "22.2 (with 22.6 R6)" |

**Totals for the r6 ids:** 9 closed, 2 partial (s-1, s-4), 0 open.

## Item 2: the `dangling-evidence` design choice {#design-choice}

**The choice.** For a `dangling-evidence` row with a NAMED dead concept, 22.2 [[task-22.2-repair-then-remove#r9-dangling]] step 4 logs only the concept's `tombstone`, and no `evidence_remove`. The reason it gives: "`evidence_remove` is applied in the one pass AFTER every `evidence` append whatever their order (R3), so it would also delete an identical row a later re-ingest writes under a re-created name".

**The premise is true of R3 as written.** R3's pass runs "after the `evidence` appends". Rebuild also sorts every event by `ts` (`store.py:7926`) before it collects. So given R3, tombstone-only is the locally safer choice: it never deletes a later, legitimate, re-ingested row.

**Does a later re-ingest of the same concept resurrect the row?**
- **Concept of kind `concept`: yes, and the spec intends it.** The new `entity` event outlives the tombstone, the concept is rebuilt, and B's OLD `evidence` event re-attaches to it. The spec says so: "they then name a LIVE concept and are ordinary evidence, not dangling".
- **That is a live/rebuild divergence.** The live store does not hold that row. Re-creating A does not re-create B's evidence. Only a re-ingest of B does.
- **Nothing pins it.** No AC covers the case.
- **Concept of kind `doc` or `memory`: no.** That is the common `rel:` case: all 14,745 dangling-evidence rows on cliquedb carry a `rel:` detail. Rebuild never resolves such a `c` ([[#code-facts]]), so the row cannot come back. The tombstone only stops the doc entity itself from resurrecting.
- **Today's data is unaffected.** On cliquedb the branch applies to 0 ids ([[#spot-check]]).

**Verdict on the choice:** it is sound only as a workaround. The premise it routes around is a defect in R3, and the same round adds two more users of `evidence_remove` that walk into that defect ([[#b-1]]). With R3 fixed, `evidence_remove` by name becomes correct for this row too, and both divergences disappear. The tombstone branch also has no AC that can fail: in AC-3c's fixture `purge_entity` has already tombstoned A.

## New findings {#findings}

### BULLSHIT b-1: R3 replays `evidence_remove` after later appends, so a rebuild deletes rows the live store holds. Round 6 documents this in one place and uses `evidence_remove` in two more {#b-1}

**The spec:**
- 22.2 [[task-22.2-repair-then-remove#r3]]: "Both replay paths apply, after the `evidence` appends, ONE pass … `evidence_remove`, `evidence_repoint`, `entity_rename` …". The same pass is stated in [[task-16.6-learned-row-validation#r1d]].
- Round 6's own text, in [[task-22.2-repair-then-remove#r9-dangling]] step 4: "`evidence_remove` is applied in the one pass AFTER every `evidence` append whatever their order, so it would also delete an identical row a later re-ingest writes under a re-created name, which the live store keeps".
- Round 6 still adds or keeps `evidence_remove` here:
  - 22.2 [[task-22.2-repair-then-remove#r2]] (new): the engine removes concept-side evidence "through `remove_evidence(identity, keep=0)`, which logs `evidence_remove` by name" before every purge.
  - 22.6 [[task-22.6-removal-entry-points#r3]]: for a deleted file, it removes the learned rows "through 22.2's row-level primitives (`remove_evidence` with `keep=0` …), so each removal has its `evidence_remove` event".

**The trace.** The scenario is a branch switch, which deletes and re-creates files, and it is common:
1. **T1.** File F is gone, so sync's R3 removes learned row `(mentions, query/P, F, F, 12)` and logs `evidence_remove` and `tombstone F`.
2. **T2.** F is back and the user greps P. The learner writes the identical row: `entity F` + `evidence` + `learned_provenance` events.
3. **Live:** one row, with its sidecar row.
4. **`rebuild_index_from_log`:** F is alive (its `entity` ts T2 is later than its tombstone). Both `evidence` appends are applied. Then the one pass runs `evidence_remove`(T1), which deletes every copy of the identity together with its sidecar rows. Then `learned_provenance`(T2) finds no row and is counted `unresolved_provenance`.
5. **Result:** the rebuilt catalog has lost a live row and its provenance.

The same thing happens through R2's new rule:
1. The engine purges concept A, which removes B's `rel:` evidence to A.
2. A is re-created, and B is edited and re-synced, which writes the identical evidence row.
3. A rebuild deletes it.

**Why no AC catches it:** 22.2 AC-3, 22.6 AC-4 and AC-3c all rebuild with no re-creation after the removal.

**Why it is bullshit:**
- The reviser derived exactly this mechanism and wrote it into the spec as a reason to avoid `evidence_remove` in one place.
- They left the replay rule unchanged, and in the same commit extended `evidence_remove` to ingest `rel:` evidence.
- A documented correctness gap with no fix and no task is an unanchored deferral (rule 9a).
- The specs assert "rebuild reproduces post-apply", and this violates it after the most ordinary workflow there is.

**Fix (spec-only):**
- **R3 and 16.6 R1d, in lockstep.** The one pass replays `evidence` appends TOGETHER with the row-level ops, in `ts` order, with ties broken by log position. An `evidence_remove` at T then deletes only the copies appended at or before T, so a later append survives.
  - Learned provenance still follows its evidence row, because the same call logs it later.
  - Compaction is unaffected: its synthetic evidence `ts` is `GREATEST(c.updated_at, e.updated_at)` (`store.py:7660-7680`), and a compacted log holds no `evidence_remove`.
- **R9-dangling step 4.** Then also log `evidence_remove` by name for a named dangling-evidence row, and drop the "re-created name re-attaches" caveat.
- **New AC-3d.** Remove a learned row, re-create the file, re-learn the identical row, then rebuild on a copy. The copy equals live: 1 row, its sidecar row, `unresolved_provenance` = 0.
  - Mutation "`evidence_remove` applied after all appends" FAILS it.
  - Add a second fixture through R2: purge concept A, re-create A, re-ingest B.
- **The tombstone branch needs an AC that can fail.** Add a fixture where the dead concept is untombstoned (bug-111's raw-DELETE shape), is NAMED, and is of kind `concept`. Mutation "no tombstone for a named dead concept" must then FAIL.

rel: contradicts -> [[task-22.2-repair-then-remove#r3]]
rel: contradicts -> [[task-16.6-learned-row-validation#r1d]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### SKETCHY s-1: restore re-inserts the recorded dead id without re-checking it, and after a rebuild that id can belong to a live entity {#s-1}

**The spec:** 22.2 [[task-22.2-repair-then-remove#r4]]: restore "re-inserts the row with the recorded DEAD id unchanged, so the restored row is the dangling row it was". AC-4c runs a rebuild, then a restore, and expects "its `entity_id` is the recorded dead id … the both-dead row comes back with both recorded dead ids".

**What is wrong:**
- **The id can be live after a rebuild.** A rebuild creates a fresh catalog whose `seq_entities_id` starts at 1 (`duckdb_catalog.py:50`, `:254-265`), and `upsert_entity` hands out dense ids. A dead id recorded from the old catalog is "dead" only relative to that catalog.
- **AC-4c's fixture is where it bites.** The fixture purges two entities created before `X`, so a small dead id is very likely a LIVE id in the rebuilt copy. The restored row is then a live, wrong link.
- **It does not stay hidden.** `repair_fragments` adds bits for live rows (`added_from_links`), so the wrong link becomes queryable.
- **Both-dead rows are worse.** Restoring both recorded ids can join two unrelated live entities.
- **On cliquedb the risk is lower.** Its dead ids sit near 2.79M and its live ids are far fewer, but that is luck, not a rule.

**Fix:**
- Before re-inserting, restore checks every recorded dead id with the shared predicate (`LinkLiveness.dead_side`). An id that is live now is counted `restore_dead_id_reused` and the row is not inserted.
- AC-4c asserts that each restored row is still dangling.
- Add a fixture whose recorded dead id is live after the rebuild. Mutation "re-insert without the dead-id check" FAILS it.

rel: contradicts -> [[task-22.2-repair-then-remove#r4]]

### SKETCHY s-2: restoring an engine purge brings the concept back under a NEW id and its inbound evidence rows back under the OLD one {#s-2}

**The spec:**
- 22.2 [[task-22.2-repair-then-remove#r2]] (new): before purging a concept, the engine records the concept-side rows "in the intent record (R4's `evidence_row` form, with the concept named …)" and removes them.
- R4's `evidence_row` restore "re-inserts the row with the recorded DEAD id unchanged".
- R4's main rule: a restored entity gets a NEW id.

**What is wrong:**
- **Engine purges.** One `removal_restore` of an engine purge of A re-creates A under a new id, and puts B's `rel:` evidence back naming A's OLD id. The row is dangling again the moment restore finishes.
- **No AC sees it.** AC-4 ("restore equal by name incl. evidence") does not seed a concept-side row. AC-3c's second fixture does not restore.
- **Purges outside the engine have the same gap.** 22.6 R2 `untrack`, R3, and the `--as-memory` conversion record only the purged entity's own rows. AC-9b says so: B's row stays, naming the dead id. Restoring A therefore cannot re-attach B's row, and the `dangling-evidence` class later deletes it while A is alive.

**Fix:**
- Restore maps every recorded old id through the restore's own `id_map` (it already builds one for `vectors_restore`). That applies to the dead side of `link_row` / `evidence_row`, and to every surviving `entity_links` / `linkage_evidence` row that still names a restored old id.
- AC: purge A through the engine, restore it, and B's evidence names A by name. Run the same check for `untrack`.
- Mutation "keep the recorded old id when the same manifest restores that entity" FAILS it.

rel: contradicts -> [[task-22.2-repair-then-remove#r4]]

### SKETCHY s-3: d9ak(b) stops at 22.2. 22.3's live global apply and R5's own earlier sentence still say no existing entity is purged {#s-3}

**The spec:**
- 22.2 [[task-22.2-repair-then-remove#r5]] keeps "So under d9ab NO existing protection is learner-attributed: … no existing entity is purged as a class member". The very next sentences say that under (c), "217 here and 90 global are learner-attributed".
- [[task-22.3-bug-086-global-repair]] R3 (last touched `ef4abfa`): "(d9ab) no existing global entity is purged by this class apply".
- 22.3 AC-5's mutation "purge a learned-only entity whose `protect_source` is NULL FAILS it".

**What is wrong:**
- **22.3 contradicts the rule.** Under rule (c), a NULL-source global entity with a matching `rmx grep` record in `~/.refmatrix/cli.log` IS purgeable. Up to 90 of them are, if they are class members of 22.3's apply.
- **The live run will disagree with its spec.** 22.3's live global run either purges entities its spec says it will not, or the implementer drops rule (c) to make 22.3 pass.
- **AC-5's mutation now tests the opposite of the rule.**
- **The changes do not mention 22.3.** 22.3 has no `#rev-round-6`, and plan-22's round-6 table never names it.

**Fix:**
- Rewrite 22.3 R3 and AC-5 for d9ak(b): count the class members that rule (c) attributes and list them `purged: learner (cli.log grep)`. Restate the mutation as "purge a NULL-source entity with no grep record and no command record".
- Delete R5's stale sentence.
- The user should see the 22.3 count before the live apply ([[#user-decisions]]).

rel: contradicts -> [[plan-review-2026-10-14#t11-approvals]]

### MEH m-1: the 8 "nameless" ids are reborn names, and the spec gives the wrong reason {#m-1}

- **What the spec says.** 22.1a `#r1-dangling` and 22.2 `#r9-dangling` both say "8 nameless (ids 2791202-2791209, whose rows no single logged name covers)". R9 step 5 says "No `entity` event that a rebuild would act on names it".
- **What is true.** One logged name covers each of them, and that name is live again in the catalog with the same rows ([[#spot-check]]).
- **Today's outcome is still right.** Delete by key and log nothing; the rebuild converges on the reborn entity.
- **Three gaps:**
  1. The audit has no label for this case. Its `name_reborn` counter exists only at apply time, so AC-8b's reference reading ("8 nameless") will count reborn ids as `unnamed:none`.
  2. A reborn key whose live entity LACKS a dead row while the log's last word for it is `link` would have that link revived onto the reborn entity by a rebuild. No rule logs the `unlink` it needs. cliquedb has 0 such rows today.
  3. The evidence side has the same shape: 843 reborn and 0 named.
- **Fix:**
  - Add `unnamed:reborn` to the naming counts: 8 link-side and 843 evidence-side on cliquedb.
  - Correct both "Measured" sentences and step 5's reason.
  - For a reborn key, log `unlink` by name only for a dead row the reborn entity does not hold.

### MEH m-2: AC-8c is too broad and too narrow at once {#m-2}

- **Too broad.** AC-8c says `_classify_dangling` "holds no string constant naming `entities`, `concepts` or `linkage_types`". But `#r1-dangling` requires it to record linkage NAMES, the live end's partition, and the live end's name (for naming). Those need `FROM entities` and `FROM linkage_types` SQL, unless `LinkLiveness` also carries the names, and the spec does not say it does.
- **Too narrow.** The check is per function, so a helper called from `_classify_dangling` can hold a second liveness set and pass.
- **The other half of the shared predicate.** `repair_fragments` also gates fragment BITS on concept liveness (`store.py:4433`). Making it build "no `concept_ids` set" requires that half to go through `dead_side` too. That is fine, but it is not stated.
- **Fix:**
  - Give `LinkLiveness` the id→(partition, kind, name) and linkage id→name maps.
  - Run the AST check over the whole `removal_audit` module, and forbid `NOT IN (SELECT id FROM …)` and id-set construction rather than table names.
  - Name the bit half.

### MEH m-3: the partition rules for `unlink`, the naming match, and "the store's default" {#m-3}

- **R9 and R6 disagree on `unlink`'s partition.** 22.2 R9 step 4 gives `unlink` "that same partition rule", meaning the dead endpoint's `entity` event. R6 says R9's events "carry the partition of the `facts.log` event they answer", meaning the `link` event. The two differ when a compacted `entity` event carries `partition` but later live `link` events do not (`_log_event` never adds one).
  - In that case an `unlink` keyed on the entity's partition does not override the live-shape `link` key.
  - That is harmless while D stays tombstoned. If D is later re-created in the default partition, the old links revive.
- **The naming rule has no partition.** Condition (iii) in 22.1a does not say which partition the covering `link` event must be in.
- **"The store's default" is undefined for a census.** The census has no `Store`; rebuild uses its bound partition (`store.py:7931`).
- **Fix:**
  - Key each `unlink` to the partition field of the last-wins `link` event it answers, with one `unlink` per distinct key.
  - State condition (iii) per partition.
  - Have the census take `--default-partition` (printed in the header).
  - Add `inputs.facts_path`, which 22.1a R3 uses but R3's field list omits.

### MEH m-4: R2's concept-side rule calls a primitive that refuses ingest rows {#m-4}

- **The guard.** 22.2 R2: "every learned-row primitive also requires `detail LIKE 'learned from grep%'`, so ingest evidence is never matched".
- **The conflict.** The new bullet removes concept-side rows "through `remove_evidence(identity, keep=0)`". Those rows are ingest `rel:` evidence: 14,745 of 14,745 on cliquedb. Either the guard leaves them in place, in which case AC-3c's second fixture FAILS and the implementer has to break a rule to pass, or the guard is silently relaxed.
- **Fix:** name the exception, as 22.1a R2 does for the dangling sub-classes. `remove_evidence(identity, keep=0, ingest_ok=True)` is called only by the concept-side rule and by `remove_dangling_evidence`. Its event's identity includes `detail` so replay matches the same row.

### MEH m-5: plan-23's census definition trails plan-22 {#m-5}

- **The stale count.** [[task-23.4-option-a-measurement]] (at `6db632b`, d9ap) still cites "5,298 dead-entity + 8 dead-concept rows on cliquedb". That is the count r6 m-1 corrected to 7 both-dead + 1.
- **The missing case.** Its dangling definition omits 22.1a's `dead-linkage` case (live entity, `linkage_id` absent). The resolver would meet that row without a rule: 0 such rows today.
- **No other cross-plan conflict.** 23.4 does not hash `linkage_evidence`, so d9ar does not reach it. 17.1's `removal_restore` value agrees with 22.2.
- **Fix:** plan-23's owner updates the count and adds the `dead-linkage` row to the census.

rel: related-to -> [[task-23.4-option-a-measurement]]

## Decisions the user should make {#user-decisions}

1. **[[#b-1]]: fix R3's replay order, or accept the divergence?** Replaying `evidence` appends and row ops in `ts` order changes 16.6 R1d's text as well as 22.2 R3. That touches the plan-16 slice Wave 1 builds first. The other option is to record, as a decision, that a rebuild may drop a row re-created after its removal. I recommend fixing it.
2. **[[#s-3]]: may 22.3's live global apply purge up to 90 learned-only global entities whole under d9ak(b)?** d9ak(b) says yes in general, but 22.3 still promises the opposite. The user should confirm 22.3 inherits it and see the count first.

## Verdict {#verdict}

**Plan-16: APPROVABLE in substance. Its round-6 edits are correct and every r6 item touching it is closed.** One edit is still needed: [[#b-1]]'s fix rewrites the one-pass sentence in 16.6 R1d, which 16.6's own Wave-1 slice implements. Approve plan-16 only together with that lockstep R1d edit. Otherwise its implementer builds the replay pass that b-1 says is wrong.

**Plan-22: NEEDS-REVISION.**
- 22.2: [[#b-1]], [[#s-1]], [[#s-2]], [[#s-3]] (R5 sentence), [[#m-1]], [[#m-3]], [[#m-4]].
- 22.3: [[#s-3]].
- 22.1a: [[#m-1]], [[#m-2]], [[#m-3]].
- 22.6: [[#b-1]] (its R3 uses `evidence_remove`), [[#s-2]] (restore of the outside-engine purges).
- 23.4: [[#m-5]], owned by plan-23.

| | r6 closed | partial | open | new B | new S | new M |
|---|---|---|---|---|---|---|
| plan-16 | 2 (m-3, m-6 parts) | 0 | 0 | 0 (b-1's R1d edit is shared) | 0 | 0 |
| plan-22 | 9 | 2 (s-1, s-4) | 0 | 1 | 3 | 5 |

**Totals.**
- **r6 ids:** 9 closed, 2 partial, 0 open.
- **New:** 9 findings, 1 BULLSHIT, 3 SKETCHY, 5 MEH.
