---
gmd: "0.1"
id: task-22.1a-provenance-free-classes
title: "Task 22.1a: the audit's provenance-free classes (orphan-root, missing-file, duplicate, orphan-alias, stale-subject, dangling-link) and the read-only removal_audit verb"
tags: [task, audit, grep-learning, concepts, bug-086, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-15
---

# Task 22.1a: the provenance-free audit classes {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (revision round 8, 2026-10-15; [[#rev-round-8]]; round 7 in [[#rev-round-7]]; round 6 in
> [[#rev-round-6]], round 5
> in [[#rev-round-5]], round 3 in [[#rev-round-3]])
> Wave: 1, after 23.1 and 16.6's Wave-1 slice (d6d; #t8-amendments; #t8-wave1).
> Depends on: 23.0 (test sandbox), 16.6 Wave-1 slice (sidecar + backfill). NOT on 16.1.
> Feeds: 22.2 → 22.5 → 22.3; 22.6 (the selector mode of `removal_audit`).

Split out of 22.1 by d6d and #t8-amendments: these classes are decidable without learn-time
provenance (the 2026-10-07 probe decided `orphan-root` without it), so bug-086's repair is not
parked behind Wave 2 (22 #b-7, DL #b-3). The flag-sensitive classes stay in
[[task-22.1-audit-classes]].

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: depends-on -> [[task-23.4-option-a-measurement]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: related-to -> [[project_global_relative_rows_repair]]

## Requirements {#requirements}

1. **R1 Classes.** The unit of every class is stated; an entity-level class never silently splits
   into rows. {#r1}
   - `orphan-root` (unit: ENTITY) — a learned file entity whose name is a relative path in a store
     where learned rows are not relative to the store's project root, i.e. the global store
     (bug-086's shape: the producer wrote global rows relative to the cwd or to
     `Path(root).parent` = `$HOME`, `cli.py:667`, `daemon.py:2136`). Resolution procedure, named
     exactly (22 #b-4). Two walks are named, never confused: the PROBE's (a census reproduction,
     [[#r1-probe]]) and the CLASSIFIER's (the applied split, [[#r1-applied]]).
     - **The probe, recovered (r3 b-1).** {#r1-probe} The 2026-10-07 probe script was never
       committed, but its source survives verbatim in the session transcript
       `b38025a7-964a-49ec-bdbf-8f7e34918303.jsonl` (the Bash call at `2026-10-07T09:31:35Z` that
       `tee -a`'d `workflow/review-output/global-relative-resolve-probe.log`); it is reproduced in
       [[#appendix-probe]]. Its rules, read from that source (not inferred from a file count):
       - **population:** every entity whose `path` is non-empty and does not start with `/`,
         joined to EVERY `linkage_evidence` row of it (any `detail`) and its concept, grouped by
         `(id, path)` (1,087 at the probe);
       - **walk:** `os.walk` (default `followlinks=False`) over `$HOME/github`,
         `$HOME/claude_tools`, `$HOME/enduris`, pruning DIRECTORY NAMES in exactly `{node_modules,
         __pycache__, .git, .venv, .venv-eval, venv, .tox, build, dist, .refmatrix}`. Hidden
         files and every other hidden directory (`.claude/`, `.github/`, …) ARE walked;
       - **candidates:** `$HOME/<rel>` when it exists, PLUS every walked path with the same
         basename that ends with `"/" + rel.lstrip("./")`; de-duplicated by STRING equality (a
         Python set), not by `realpath`;
       - **line check:** the candidate is read with `read_text(errors="replace").splitlines()`;
         it verifies when, for any `(line, concept)` of the entity, `1 <= line <= len(lines)` and
         `re.search(pat, lines[line-1])` holds, case-sensitively, where `pat` is the concept name
         after `query/` (the whole name otherwise); on `re.error` the check is `pat in text`;
       - **outcome:** `verified@min(n, 2)` and `cands@min(n, 2)`.
       - **Measured 2026-10-14 (this revision, read-only `os.walk`, no store opened):** the
         probe's walk visits **973,157** files today against **972,849** at the probe (+308,
         +0.03%). The re-review's fitted rule (prune every hidden entry, `node_modules`,
         `__pycache__`) visits 975,474: close, but it is not the probe's rule and is superseded by
         the recovered source.
       - **Round 2's "`$HOME/<rel>` is NOT a candidate" is WITHDRAWN.** The walk pass added it
         (`if (H/rel).exists(): cands.add(str(H/rel))`). It stays out of the CLASSIFIER's
         candidate set ([[#r1-applied]]), where the same file is the readable-today attribute.
       - The reproduction is an OPERATOR census tool, never the classifier: this task commits the
         recovered source as `eval/spikes/global_relative_resolve_probe.py` (verbatim rules; only
         the catalog path and `$HOME` become arguments; a header names its origin). Its Python
         `re` line check reproduces a historical measurement; `src/` carries no copy of it and
         d-11 (one verifier for learned rows) governs every class this task assigns.
     - **The classifier's candidate set (the applied split).** {#r1-applied} For a relative entity
       name `rel`, the candidates are the files found by a suffix walk over the recorded
       `candidate_trees` (default the three trees above) under the PROBE's directory-name prune set
       (with `.venv*` as a glob), PLUS two path-prefix prunes: `<tree>/**/.claude/worktrees/`
       (worktree copies of the same tree; each turns `verified@1` into `verified@2`) and
       `$HOME/github/atollogy/bdep/_frameworks_and_libraries/` (vendored code), with
       `followlinks=False`. `$HOME/<rel>` is NOT a candidate here. The trees, the prune set and
       `home_base` are explicit inputs recorded in the plan manifest (`candidate_trees`,
       `walk_prunes`, `home_base`), defaulting to `Path.home()`-relative values in the DAEMON op
       only. The census ([[task-16.6-learned-row-validation#r7]]) runs with `HOME` redirected, so
       it never takes a default: it REFUSES a classifier census unless `--candidate-trees` and
       `--home-base` are given explicitly (the real home, read from
       `pwd.getpwuid(os.getuid()).pw_dir`), and prints both in its log header (r4 s-3). Without
       that, `home_base` would default to the redirect and move every `home-readable` entity into
       a removal class.
       The deploy tree `~/refmatrix` is not under any of the three trees.
     - **De-duplication (s-1).** Classifier candidates are de-duplicated by `os.path.realpath`
       before counting: one file reached two ways (a symlink, or overlapping trees) is ONE
       candidate, so it cannot turn a `verified@1` entity into `ambiguous:root`.
     - **Verification** per candidate: the file exists and at least one of the entity's recorded
       lines holds the `query/<pattern>` text under 16.6's permissive reading,
       `learned_verify.permissive_matching_lines(file_abs, pattern)`
       ([[task-16.6-learned-row-validation#r2-permissive]]: case-insensitive; literal OR regex;
       plus `identifier_variant_regex`, `store.py:786`; lines split on `b"\n"` as grep splits
       them, never `str.splitlines()`, r3 m-2). This needs no provenance, and 22.1a carries no
       matcher of its own. A candidate whose reading is `Unverifiable` does not count as verified
       and is recorded with its reason; the entity's outcome then follows [[#r1-outcome]]'s
       `unverifiable` rule, never the removal rule (r3 s-3).
     - **Readable today (d9b; re-review s-2).** Separately from the candidate count, every entity
       records whether `home_base/<rel>` exists and verifies under the same reading: that is
       where `grep_evidence` resolves global rows TODAY (`Path(root).parent`, `cli.py:667`,
       `daemon.py:2136`), so such a row is not bug-086's symptom. The attribute never changes the
       probe reproduction; it only routes the applied split ([[#r1-outcome]]).
     - **Outcome** per entity, applied split, in this order of precedence: {#r1-outcome}
       1. `verified@1` → `orphan-root:resolved` with the absolute path recorded for 22.5; when the
          entity is also readable today at a DIFFERENT realpath, it is `ambiguous:root` instead
          (two live readings, d6a).
       2. `verified@≥2` → `ambiguous:root` (kept, all candidates recorded; d6a).
       3. `verified@0` and readable today → `orphan-root:home-readable`: NOT a removal class. It is
          handed to 22.5 R1, which reports it as its own bucket and applies nothing to it until the
          user rules (d9b).
       4. **`verified@0`, not readable today, and at least one reading (at a candidate or at
          `home_base/<rel>`) returned `Unverifiable` → `orphan-root:unverifiable` (r3 s-3).** NOT a
          removal class: kept, counted by reason (`UNVERIFIABLE_REASONS`), and carried to 22.5 as
          held. An entity whose patterns are all in the permissive subset (`a\|b`,
          `[[:space:]]`, `\<x\>`) can never verify anywhere, so without this rule it would fall
          into the removal class below. The global log holds 26 such relative entities (of 2,999
          relative global learned entities; r3 `#ev-subset`); the count on the copy is measured by
          AC-5b, not assumed.
       5. `verified@0`, not readable today, every reading returned a set → `orphan-root:unresolved`
          (removal candidate).
     - The rows of a resolved entity travel with it, including any row that did not verify; they
       are re-checked by 22.1 in their new store, never dropped here.
   - `missing-file` (unit: ENTITY) — a learned file entity whose absolute path does not exist (the
     1,655 `pytest-of-*` tmp entities in the live global store, 22 #b-8, d1c). A relative path is
     never `missing-file`; it is `orphan-root`.
   - `duplicate` (unit: ROW IDENTITY) — more than one `linkage_evidence` row with the same
     identity `(linkage_id, concept_id, entity_id, file, line)` and a `detail` beginning
     `learned from grep`. The table has no primary key (`duckdb_catalog.py:162`), so identity is
     these five columns (22 #s-6).
   - `orphan-alias` (unit: CONCEPT) — an alias concept whose description is `alias of '<name>'`
     (`ingest.py:848`) with no `same_as` edge and no other edge. Sub-class
     `orphan-alias:repairable` when `<name>` names an existing concept by EXACT name that is not
     `noise` (22 #s-5); else `orphan-alias:unrepairable`. `canonical_name` is never used to find
     the target (it folds case and `_-`, `identifier.py:49`).
   - `stale-subject` (unit: ENTITY) — a compiled subject marked `stale` by plan-19's compile (d8a;
     the writer is plan-19's 19.4 R5). The audit only reports it.
   - `dangling-link` (unit: LINK ROW; d9an) and `dangling-evidence` (unit: EVIDENCE ROW; d9ar):
     a row with a dead endpoint. Such a row has no correct form: its other endpoint was deleted by
     a path that bypassed `purge_entity` (bug-111), or by a purge, since neither
     `Store.purge_entity` nor `Store._bulk_purge_ids` deletes a `linkage_evidence` row (read at
     `3d3c798`). 22.2 R9 removes both ([[task-22.2-repair-then-remove#r9-dangling]]). {#r1-dangling}
     - **The liveness predicate is the one `Store.repair_fragments` runs (r6 m-2)**, side by side
       for each column, in the code's order:

       | column | alive when (the repair, read at `3d3c798`) | NOT consulted |
       |---|---|---|
       | `entity_id` | in `entities` (the repair's `ent_part`) | `concepts` |
       | `linkage_id` | in `linkage_types` | — |
       | `concept_id` | in `entities` ∪ `concepts` (a typed edge's concept may be a doc, memory or code entity, bug-105 r2 #b2-2) | — |

       A link row is `dangling-link:entity` when its entity is dead (whatever its linkage and
       concept; the repair counts it `links_dead_entity`), else NOT a member and counted
       `dead-linkage` when its linkage is dead (the repair counts it under `links_skipped` only
       and never checks its concept), else `dangling-link:concept` when its concept is dead
       (`links_dead_concept`). Round 5's "`entities` ∪ `concepts` on the entity side" was not the
       code; the two differ only for a `concepts` row with no `entities` row, which the schema
       rules out by convention (the `concepts` DDL in `store.py`: `id` "equals entities.id where
       kind='concept'"; not an enforced key) and both stores hold 0 of. `dead-linkage` rows: 0 on both stores (r6); they are printed, never removed here.
     - **`dangling-evidence` (d9ar)** is a `linkage_evidence` row whose entity is ALIVE and whose
       concept is dead under the same predicate (any `detail`: a `rel:` edge's ingest evidence is
       the common case). A row whose ENTITY is dead is not a member: it is `vacuum` step 3's, made
       auditable by [[task-22.6-removal-entry-points#r5]].
     - **One shared predicate (r6 m-3; r7 m-2).** `store.link_liveness(con) -> LinkLiveness` loads,
       from any DuckDB connection (the writer's, a read snapshot's, a census copy's), the ONLY
       liveness and naming data either caller reads:
       - `entity: dict[int, tuple[partition_name, kind, name]]` (every `entities` row; the
         entity-side liveness set and the partition and name the audit records for a live end);
       - `concept_ids: frozenset[int]` (`entities` ∪ `concepts`, the concept-side set);
       - `linkage: dict[int, str]` (`linkage_types` id → canonical name).
       `LinkLiveness.dead_side(entity_id, linkage_id, concept_id) -> "entity" | "linkage" |
       "concept" | None` applies the table above; `linkage_id=None` skips the linkage column, for
       a fragment BIT, whose linkage is its fragment row's name. Both halves of
       `Store.repair_fragments` call it: the `entity_links` loop (today `ent_part` and
       `concept_ids` at `store.py:4360-4388`, read at `77ac38f`) and the bit loop (today
       `ent_part.get(bit & mask)` and `… not in concept_ids` at `:4428` and `:4433`), which reads
       the bit's live partition from `LinkLiveness.entity`. `removal_audit._classify_dangling(conn,
       inputs)` calls it and takes every linkage name, live-end partition and live-end name from
       its maps, so the module needs no SQL over those three tables at all (AC-8c).
     - **Store scope (r6 s-2).** `entity_links` and `linkage_evidence` have no partition column
       (`duckdb_catalog.py`'s DDL), a dead endpoint has no partition, and a both-dead row (7 on
       cliquedb) belongs to none. So both sub-classes are audited ONCE per store, whatever
       `inputs.partition` says, over the whole table, exactly as the repair counts. Each member
       records its LIVE end's partition, or `none` when both ends are dead; 22.2 R6 batches by it.
     - **Naming the dead end from `facts.log` (r6 b-1, d9aq).** For each dead id `D`, the audit
       reads the store's `facts.log` (read-only; the census reads its copy) and computes
       `names_from_log(D)`: the `(partition, kind, name)` keys that (i) have an `entity` event and
       no tombstone at or after their latest one, (ii) have no catalog row, and (iii) carry, for
       EVERY member row of `D` whose other end is alive, a last-wins `link` event (for a
       dangling-evidence row, an `evidence` event at the same `file`/`line`) with that row's
       linkage and live-end name on the other side, IN THE KEY'S OWN PARTITION (r7 m-3): the
       covering event's effective partition (its `partition` field, or the default partition
       when absent) equals the key's, because a rebuild resolves a `link` or `evidence` event
       only through its own partition's names. **Which key an event covers is decided by the
       one legacy rule (r8 m-2, d9bl).** {#r1-covering} The ENTITY end of an event always carries
       `e_kind`, so it covers `(p, e_kind, e)` exactly. Its CONCEPT end covers `(p, k, n)` iff its
       `c_kind == k`, or it is legacy (no `c_kind`) and
       `edge_records.resolve_legacy_kind(<kinds logged for n in p>)` returns `k`, where the kinds
       logged for `n` are every kind with an `entity` event for `(p, ·, n)`, tombstoned keys
       included, exactly the rebuild's Pass 2b `kinds_by_name` (the audit computes it with the
       same `edge_records.resolve_c_kind` the rebuild calls, 16.6
       [[task-16.6-learned-row-validation#r1d-one-format]]; no rule of its own). A legacy event
       the rule returns None for covers nothing and is counted `legacy_unresolved`. `D` is NAMED
       when exactly one key qualifies and no other dead id claims that key. Otherwise it is
       NAMELESS, in one of three labels counted apart (r7 m-1):
       - `unnamed:reborn` — at least one key that covers one of `D`'s live-end rows (by the rule
         above) satisfies (i) and (iii)'s partition rule but HAS a catalog row: the name was
         re-created under a new id. Its reborn entities are EVERY such live covering key, not
         one "best" key (r8 m-2: on the cliquedb copy 381 of the 896 evidence-side reborn ids are
         covered by more than one live key, and round 7's "the key that covers the most" broke
         ties by set order, so its 711 / 170 / 15 split moved between runs). 22.2 R9 tombstones
         nothing for it and logs an event only for a dead row a live covering key's entity does
         not hold, keyed on that key ([[task-22.2-repair-then-remove#r9-dangling]]);
       - `unnamed:ambiguous` — more than one key qualifies, or the one key is claimed by another
         dead id;
       - `unnamed:none` — every other case.
       "The default partition" is an explicit input, never discovered: the daemon op passes its
       store's bound partition (`rebuild_index_from_log` uses the same value, `store.py:7931`),
       and the census takes `--default-partition` and prints it in its header (r7 m-3). A
       both-dead row is named through its dead entity's other rows, when it has any.
     - Each member records `(entity_id, linkage, concept_id)` (plus `file`, `line`, `detail`,
       multiplicity for an evidence row), its weight (NULL kept), which side is dead, the live
       end's partition or `none`, and `names_from_log`. [[#r2]] does not exempt either sub-class:
       the dead side has no owner, so a row whose LIVE end is ingest-owned is still a member.
     - **Measured (r6 m-1),** on copies of the read snapshots, 2026-10-14 23:43-23:45
       (`bsd-plan16-22-spec-rereview-r6-0e77da3` `#ev-dangling`, `#ev-evidence-orphans`):

       | store | `dangling-link:entity` | of them both-dead | `dangling-link:concept` | `dangling-evidence` |
       |---|---|---|---|---|
       | cliquedb | 5,298 (64 dead ids) | 7 | 1 | 14,745 |
       | refmatrix | 0 | 0 | 0 | 5,920 |

       cliquedb's `:entity` rows by linkage: `mentions` 5,184, `part-of` 63, `related-to` 33,
       `amends` 7, `reinforces` 5, `depends-on` 5, `supersedes` 1 (379 with a NULL weight); its
       one `:concept` row is `part-of`. These equal the live daemon's `repair_fragments` counters
       (`links_dead_concept=1 links_dead_entity=5298`, its `rmxd.log` at 2026-10-14T23:43:03).
       Round 5's "8 `:concept` rows, all `part-of`" counted the 7 both-dead rows twice. Naming on
       the cliquedb copy (re-derived 2026-10-15 from the r6 auditor's copies, read-only): 56 of
       the 64 dead entity ids are NAMED, each by a distinct one of the 56 doc keys a rebuild would
       resurrect; 0 ambiguous; 0 would-resurrect keys unclaimed; and 8 `unnamed:reborn`, 0
       `unnamed:none` (r7 m-1). The 8 (ids 2791202-2791209) are `cliquedb/architecture-index` and
       its seven section concepts (`#root`, `#entry-points`, `#topic-docs`, `#adr`, `#concepts`,
       `#explorations`, `#tech-stack`), each LIVE again under a new id (3219330-3219337) that
       carries the same rows: 7 are fully covered by their name's `link` events (4/4, 10/10,
       81/81, 112/112, 9/9, 474/474, 13/13 rows held by the reborn entity), the eighth (`#adr`) on
       3,458 of its 3,459 rows (r7 `#spot-check`, `scratchpad/r7/naming3.log`). Round 6 called
       them "8 nameless … whose rows no single logged name covers"; that reason was false.
       Evidence side (measured for round 7 on the same r6 copies, read-only, `.venv-eval/bin/python
       -I`, `duckdb read_only=True`; script `scratchpad/r7-reviser/evreborn.py`): the 14,745
       dangling-evidence rows hang on 4,778 dead concept ids; 0 NAMED; 896 `unnamed:reborn` (843
       whose rows one logged `c` name covers fully, 53 partly; every one of those names is live
       in the catalog: 711 as `concept` only, 170 as `doc` only, 15 as both); 3,882 `unnamed:none` (no
       `evidence` event covers any of their rows).
       **Re-measured for round 8 by the one legacy rule (r8 m-2),** on the same r6 copy
       (`clique.duckdb`, `clique.facts.log`; read-only, `.venv-eval/bin/python -I`,
       `duckdb read_only=True`, `edge_records.resolve_legacy_kind` imported from the dev tree;
       scripts `scratchpad/r8/ev15c.py` to `ev15g.py`, logs beside them). The copy's log predates
       0.78.3: it holds 0 kinded `evidence` events, so every covering event is legacy. Per dead
       concept id: 3,882 `unnamed:none` and 896 `unnamed:reborn` (unchanged); 381 of the 896 are
       covered by more than one live key; 0 covering events are `legacy_unresolved`. Per row:
       14,733 distinct dead rows, 1,995 covered; of the `(row, live covering key)` pairs, 2,744 are
       held by that key's entity and 121 are not, on 47 dead ids. All 121 are LEGACY
       MISRESOLUTIONS: each covering name (10 names, e.g. `pseudocode-delta-merge`) is live as
       both a `doc` and a `concept`, the rule resolves it to `concept`, and the `doc` holds the
       row live (0 rows held by the `concept`). Round 7's "15 as both" was one draw of the
       tie-broken best key; with ties made explicit the best-key count of two-kind reborn ids is
       0, and the two-kind names sit only on tied ids. A rebuild of today's store would already
       re-attach those 121 rows to the `concept` (bug-117's legacy rule), whatever plan-22 does;
       22.2 R9 removes them from the `concept` key and counts them `legacy_misresolved`; a
       compaction (`dump_catalog_to_log`, kinded since 0.78.3) ends the case.
2. **R2 Ingest is out of scope.** No class selects an ingested evidence row (`detail` not
   `learned from grep…`), a `tracked_files` row, or an entity with an ingest link. A learned file
   entity that is also ingested is reported `shared` and never becomes `missing-file` or
   `orphan-root:unresolved` as a whole; only its learned rows are classified. The two dangling
   sub-classes are the stated exception ([[#r1-dangling]]): they select a row by its DEAD side,
   ingest-derived or not, and never touch the live end's other rows. {#r2}
3. **R3 Read-only, defined (22 #m-2).** The audit is a daemon READ op over the lock-free read
   snapshot. It writes no catalog row, no Lance version, no queue entry and no `facts.log` event.
   It enqueues NO `stale_seen` marks (those belong to 16.6's grep read path). Its only output is the
   plan manifest file `.refmatrix/removal/<id>.plan.jsonl` plus its sha256, which 22.2's apply
   requires (d8g). {#r3}
   - **One classifier, two callers (r3 s-6).** The classes are computed by ONE pure function,
     `removal_audit.classify_provenance_free(conn, inputs) -> AuditPlan`, where `conn` is a
     read-only DuckDB connection to a catalog file and `inputs` carries `store_root`, `partition`,
     `candidate_trees`, `walk_prunes`, `home_base`, `facts_path` and `default_partition` (the
     last two added in round 7, r7 m-3: the dangling naming reads them, and round 6 used
     `facts_path` without listing it). The dangling sub-classes ignore `partition` and read
     `facts_path` and `default_partition` instead ([[#r1-dangling]], store scope; r6 s-2); a
     missing `facts_path` or `default_partition` is an error for them, never a default. The daemon op passes the connection its
     read-snapshot ops already use; the operator census passes `duckdb.connect(<copy>,
     read_only=True)` through the ONE census procedure,
     [[task-16.6-learned-row-validation#r7]]. No census constructs `Daemon` or `Store`.
4. **R4 Verb and output (d6e as amended by d8g; 22 #m-6).** `removal_audit` is a verb exposed as
   `rmx removal audit --root R` and as the MCP tool `rmx_removal_audit`. Output: counts per class
   and per `query/*` pattern; `--list` for members; `--json` for the plan. The plan manifest
   records: store root, partition, catalog identity (active slot + snapshot version), the
   walk's `candidate_trees`, `walk_prunes` and `home_base`, every member with its class, its
   recorded resolution, its readable-today attribute and (for `orphan-root:unverifiable`) its
   `Unverifiable` reasons. A dangling member carries its own `partition` (live end, or `none`) and
   its `names_from_log`; the manifest's one `partition` field does not scope them (r6 s-2).
   Exit 0 when the scan completes; any unreadable input is counted and printed, never skipped
   silently. {#r4}

## Acceptance criteria {#acceptance}

1. **One row per class.** A sandbox fixture with one member of each class (incl.
   `ambiguous:root`, `orphan-root:home-readable`, `orphan-root:unverifiable`,
   `orphan-alias:repairable`,
   `orphan-alias:unrepairable`, `shared`) audits each
   member to exactly its class; the resolved `orphan-root` records the right absolute path.
2. **Case-variant canonical (22 #s-5).** An alias `alias of 'Store'` with only `store` existing
   classifies `orphan-alias:unrepairable`. Mutation: resolving through `canonical_name` must FAIL
   this AC.
3. **Permissive reading.** An `orphan-root` fixture whose line matches the pattern only
   case-insensitively resolves `verified@1`. Mutation: verifying case-sensitively must FAIL.
4. **Read-only.** With the daemon tick stopped, an audit leaves the catalog file hash, every Lance
   dataset version, the learn/mark queue files and `facts.log` byte-identical; only
   `.refmatrix/removal/` gains the plan file. Mutation: an audit that enqueues one mark must FAIL.
5. **Probe reproduced (22 #b-4, #m-1, s-1; r3 b-1, s-3).**
   - **5a, sandbox tests (gate).**
     - *Classifier.* A fixture global store and a fixture tree set: a relative entity whose file
       is reachable through a symlink AND directly resolves `verified@1` (mutation "no realpath
       de-dup" FAILS it: it reads `verified@2`); a `verified@0` entity whose `home_base/<rel>`
       verifies classifies `orphan-root:home-readable`, never `orphan-root:unresolved` (mutation
       "drop the readable-today attribute" FAILS it); a candidate under
       `<tree>/x/.claude/worktrees/` is not walked (mutation "drop the worktree prune" FAILS it:
       `ambiguous:root`); the fixture's applied split equals its hand-computed split exactly
       (mutation "add `home_base/<rel>` as a candidate" FAILS it).
     - *Unverifiable is never removed (r3 s-3).* A relative entity whose only pattern is `a\|b`
       (no candidate decides, `home_base/<rel>` absent) classifies `orphan-root:unverifiable`
       with reason `permissive-subset`, never `orphan-root:unresolved`. Mutation "Unverifiable
       counts as not verified" FAILS it.
     - *Reproduction script.* `eval/spikes/global_relative_resolve_probe.py` run on a fixture
       catalog and fixture trees gives the hand-computed probe-rule counts (`verified@*`,
       `cands@*`, walked file count). The fixture holds: a candidate that is a hidden FILE under a
       hidden directory other than the pruned names (walked: mutation "prune every hidden entry",
       the re-review's fitted rule, FAILS); a candidate under `.venv/` (pruned); an entity whose
       only candidate is `$HOME/<rel>` (counted: mutation "omit `$HOME/<rel>`" FAILS); a line that
       matches only case-insensitively (not verified: mutation "case-insensitive check" FAILS).
   - **5b, operator census (not a suite test; s-3, s-6).** On a copy of the global store's
     `catalog.read.duckdb` and `facts.log`, made and read by the ONE census procedure
     ([[task-16.6-learned-row-validation#r7]]), the operator runs, with `candidate_trees` = the
     probe's three real trees (walked read-only):
     1. **The reproduction:** the committed probe script on the copy. Printed: the walk's file
        count `W` and its drift from 972,849 (pre-registered tolerance ±1%; outside it the line
        reads `walk-drift`); run as `scripts/census_on_copy.py --census probe-reproduction`
        ([[task-16.6-learned-row-validation#r7]], which lists it), so the reproduction runs inside
        the ONE census procedure (r4 m-1); the six probe counts (`verified@0/1/2`, `cands@0/1/2`) beside the
        probe's (563 / 476 / 48; 417 / 518 / 152 of 1,087) and the per-bucket delta `Δ_b`.
     2. **The churn bound.** The probe recorded counts only, never per-entity outcomes, so a
        per-entity difference cannot be attributed. The census instead counts the entities whose
        inputs changed after the INSTANT `2026-10-07T09:29Z`, the mtime of the catalog snapshot
        the probe read (r4 m-2: not the run time `09:31:35Z`; the 2.5-minute gap is named, not
        ignored): `C` = population entities with any
        `entity`, `tombstone`, `evidence` or `unlink` event after that instant (read-only parse of
        the copied `facts.log`), plus entities that left or joined the population; `M` = entities
        with a classifier OR probe candidate whose mtime or birthtime is after it. An entity whose
        inputs did not change classifies identically under the same rules, and each changed
        entity moves at most one unit out of one bucket and into another, so the verdict is
        `reproduced` iff `Σ_b |Δ_b| ≤ 2·(C + M)` over the three `verified@` buckets, else `drift`.
        A candidate file DELETED since the probe is not observable today; the census says so in
        its output.
        **Compaction (r4 m-2, b-2).** `C` reads `tombstone`/`unlink` events and population
        leavers from the copied log, and the daemon's periodic compaction
        (`dump_catalog_to_log`, [[task-22.6-removal-entry-points#r6]]) erases both. The census
        prints the copied log's birth time and the last `facts.log compaction` line of the
        store's `rmxd.log` (read in place, read-only), and when either falls after the instant
        it labels `C` `undercounted (log compacted after the probe)` and prints the verdict as
        `reproduced (C undercounted)` or `drift (C undercounted)`. The global log's last
        compaction was 2026-10-07T01:13:11 local, before the instant (read 2026-10-14).
     3. **The applied split** (the classifier through `classify_provenance_free` on the same
        copy): every R1 outcome with entity and row counts, `orphan-root:unverifiable` by reason,
        and the per-bucket delta against the reproduction.
     The census gates on its OUTPUT being complete (items 1-3, the copy's sha256, mtime and
     size), never on equality: `reproduced` or `drift`, with the numbers, is shown to the user
     beside 22.5's dry run, and the applied split is what 22.5 and 22.3 use (and AC-6b recounts
     independently). Output: `workflow/review-output/22.1a-global-census.log`, cited in the
     summary.
6. **Independent recount (22 #m-1).** 6a: on sandbox fixture stores, each class count equals an
   independent SQL recount of its predicate, exactly. 6b (operator census, as 5b): on copies of
   this repo's and the global `catalog.read.duckdb`, each class count equals the independent
   recount on the same copy (copy and read per [[task-16.6-learned-row-validation#r7]]); the
   exploration's 9,182 orphan aliases is printed beside it as drift, not used as a bound.
7. **pytest rows.** 7a: a sandbox fixture entity under a `/pytest-of-<user>/` path classifies
   `missing-file`. 7b (operator census, as 5b): on the global copy, `missing-file` includes every
   entity whose path contains `/pytest-of-` (1,655 at the review; recount exact).
8. **Dangling rows (d9an, d9ar; r6 s-2, m-3).**
   - **8a, sandbox test.** A store with two partitions, `p1` (bound) and `p2`. Its `entity_links`
     holds: a row to a deleted entity whose live concept is in `p2`; a row to a deleted concept
     whose live entity is in `p2`; a row whose concept is a live DOC entity (no `concepts` row);
     a row with both endpoints dead; a row with a live entity and a `linkage_id` absent from
     `linkage_types`; a row whose entity id has a `concepts` row but no `entities` row (planted);
     and two rows of a second dead id `E2`, one to the first row's live concept `X` and one to a
     concept `Z` no logged name links. Its `linkage_evidence` holds a row of a live entity whose concept was
     purged with `purge_entity`, and a row whose entity is dead. Its `facts.log` names the first
     row's dead entity (an `entity` event, a matching `link` event, no tombstone). The audit, run
     with `partition = p1`, classifies them `dangling-link:entity` (partition `p2`, NAMED),
     `dangling-link:concept` (`p2`), not a member, `dangling-link:entity` (`none`), not a member
     (`dead-linkage=1`), `dangling-link:entity` (the planted id: the entity side ignores
     `concepts`), `dangling-link:entity` ×2 for `E2` (`unnamed:none`: no one name covers both
     rows), `dangling-evidence` (its entity's partition), and not a member (vacuum's).
     **Reborn and per-partition naming (r7 m-1, m-3).** Two more rows: a row of a dead id `R0`
     whose logged name `R` has an `entity` event and a covering `link` event AND a live catalog
     row (re-created) → `dangling-link:entity`, `unnamed:reborn`; a row of a dead id `P0` whose
     only covering `link` event carries no `partition` field (so the bound `p1`) while its name's
     `entity` event carries `partition: p2` → `unnamed:none` (the covering event is in another
     partition). Mutations, each FAILS it: "count reborn as `unnamed:none`" (the reborn count is
     0, the recount says 1); "ignore the covering event's partition" (`P0` reads NAMED).
     **Covering by the one legacy rule (r8 m-2).** A `linkage_evidence` row of a live entity
     whose concept is a dead id `K0`, and two logged `evidence` events covering it under name
     `N`: one LEGACY (no `c_kind`), one with `c_kind: doc`. `N` is live as both a `doc` and a
     `concept` (each with an `entity` event); the doc holds the row live, the concept does not.
     The audit labels `K0` `unnamed:reborn` with two live covering keys, `(doc, N)` from the
     kinded event and `(concept, N)` from the legacy one (the rule over logged kinds
     `{doc, concept}` returns `concept`), and reports one row to remove on `(concept, N)` and
     `legacy_misresolved = 1`. A third event, legacy, under a name logged as both `doc` and
     `code` (no `concept`) covers nothing and is counted `legacy_unresolved = 1`. Mutations, each
     FAILS it: "a legacy event covers every kind of its name" (`(doc, N)` is also reported from
     the legacy event, and the row count to remove changes); "a kinded event is resolved by the
     legacy rule" (the `c_kind: doc` event covers `(concept, N)`); "resolve over the LIVE
     catalog's kinds" (a tombstoned `concept M` with a live `doc M`: the legacy event covers
     `(doc, M)` instead of the dead `(concept, M)` the rebuild resolves to).
     Each class count equals an INDEPENDENT SQL recount written in the test (not imported from
     `src/`), and equals `repair_fragments(dry_run=True)`'s `links_dead_entity` /
     `links_dead_concept` on the same store. Mutations, each FAILS it: "concept alive =
     `concepts` only" (the live-doc row becomes a member); "entity alive = `entities` ∪
     `concepts`" (the planted id is no longer a member); "audit only the bound
     partition" (the `p2` and `none` members are missed and the recount differs);
     "name by any one row's link event" (`E2` takes the first row's name through `X`).
   - **8b, operator census (not a suite test; as 5b).** `--census dangling-link`
     ([[task-16.6-learned-row-validation#r7]]) on copies of cliquedb's and this repo's
     `catalog.read.duckdb` and `facts.log` prints, per store: the class counts (`:entity`,
     both-dead, `:concept`, `dead-linkage`, `dangling-evidence`); the naming counts, link side
     and evidence side apart (dead ids, `named`, `unnamed:reborn`, `unnamed:none`,
     `unnamed:ambiguous`); `would_resurrect` (keys with an untombstoned
     `entity` event and no catalog row) and how many of them a dead id claims
     (`would_resurrect_unclaimed` = the rest); and, beside the counts, the live repair's counters
     read from the latest `repair_fragments dry_run=` line of `<store_root>/rmxd.log` (written by
     `daemon._op_repair_fragments`; read in place, read-only, with that line's timestamp), labelled
     `equal`, `drift`, or `no-counter` when the log holds no such line. No `Store` is
     constructed for it. The run passes `--default-partition` (each store's bound partition, its
     own name for a project store) and the header prints it (r7 m-3). Reference reading for
     cliquedb ([[#r1-dangling]]): 5,298 / 7 / 1 / 0 / 14,745; link side 64 dead ids, 56 named, 8
     reborn, 0 none, 0 ambiguous; evidence side 4,778 dead concept ids, 0 named, 896 reborn
     (381 on more than one live key; 47 with a row to remove, 121 `(row, key)` pairs, all
     `legacy_misresolved`), 3,882 none, 0 ambiguous, 0 `legacy_unresolved`; 56 would-resurrect,
     0 unclaimed (r7 m-1: round 6's "8 nameless" were the 8 reborn; r8 m-2 for the evidence-side
     split). The census also prints the log's legacy and kinded edge-event counts (0 kinded on
     the r6 copy).
   - **8c, one predicate (mechanical, not review; r7 m-2).** An AST test asserts:
     - over the WHOLE `removal_audit` module (every function, helpers included, since a helper
       called from `_classify_dangling` could hold a second liveness set):
       `_classify_dangling` calls `store.link_liveness` and `LinkLiveness.dead_side`; no string
       constant holds an anti-join against those tables (case-insensitive `NOT IN (SELECT id
       FROM entities|concepts|linkage_types …)` or `NOT EXISTS (SELECT … FROM entities|concepts|
       linkage_types …)`); and no set, frozenset or dict is built from a WHOLE-TABLE id query
       (`SELECT [DISTINCT] id[, …] FROM entities|concepts|linkage_types` with no `WHERE`), which
       is what a liveness set is. Table names and filtered queries stay legal: the other classes
       of this module read `entities` for their own members;
     - in `Store.repair_fragments`: both the `entity_links` loop and the bit loop call
       `LinkLiveness.dead_side`, and the method holds no `SELECT id FROM concepts`, no `SELECT
       id, partition_id FROM entities` and no name `concept_ids` or `ent_part` of its own.
     Mutations, each FAILS it: "an inline `SELECT id FROM concepts` in `_classify_dangling`"; "a
     helper `_live_ids(conn)` in `removal_audit` that builds the id set and is called from
     `_classify_dangling`" (the per-function check of round 6 passed it); "the repair keeps its
     own `concept_ids` set for the bit loop" (the bit half, `store.py:4433` at `77ac38f`).

## Files to modify {#files-to-modify}

r4 m-1: this task's own file list.

| File | Change |
|------|--------|
| `src/refmatrix/removal_audit.py` (new) | `classify_provenance_free(conn, inputs) -> AuditPlan` (R1-R3); the plan manifest writer (R4); 22.1 and 22.6 extend it |
| `src/refmatrix/verbs.py` | the `removal_audit` verb (R4); `mcp.py` generates `rmx_removal_audit` from `verbs.VERBS` (`mcp.py:73-84`), so the verb-parity test covers it |
| `src/refmatrix/daemon.py` | the `removal_audit` read op over the read snapshot (R3) |
| `src/refmatrix/cli.py` | `rmx removal audit` (R4) |
| `eval/spikes/global_relative_resolve_probe.py` (new) | the recovered probe ([[#appendix-probe]]); only the catalog path and `$HOME` become arguments; a header names its origin and the sha256 above |
| `scripts/census_on_copy.py` (16.6's) | the `probe-reproduction` and `provenance-free` census names (16.6 R7 owns the script) |
| `tests/test_removal_audit.py` (new) | AC-1..AC-4, AC-5a, AC-6a, AC-7a, AC-8a, AC-8c |
| `src/refmatrix/store.py` | `link_liveness(con) -> LinkLiveness` and `LinkLiveness.dead_side`, the ONE endpoint predicate; `Store.repair_fragments` rewritten to call it ([[#r1-dangling]], AC-8c) |
| `src/refmatrix/removal_audit.py` (also) | `_classify_dangling(conn, inputs)`: both sub-classes, store scope, the `facts.log` naming ([[#r1-dangling]]) |
| `scripts/census_on_copy.py` (also) | the `dangling-link` census name (AC-8b; 16.6 R7 lists it) |

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): `$HOME`, the global root, the registry and
LaunchAgents redirected to a short `mkdtemp` before `refmatrix` is imported; in-process `Daemon` +
`Store`; no `rmx` subprocess; the 23.0 conftest guard fails any touch of `~/.refmatrix` or a live
store. No suite test reads a live catalog: AC-5b, 6b and 7b are OPERATOR census steps through the
ONE census procedure ([[task-16.6-learned-row-validation#r7]]: `cp` of the `catalog.read.duckdb`
snapshot into a short `/tmp` dir, read through `duckdb.connect(read_only=True)` by the production
classifier, no `Daemon`, no `Store()`, no `rmx`, no socket), logged under `workflow/review-output/`
and cited in the summary; AC-5a, 6a and 7a are the gating sandbox tests. Every listed mutation is
pre-registered and must turn its test RED.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered in |
|---|---|
| d6d, #t8-amendments (22.1a split, Wave 1) | [[#root]] |
| 22 #b-7, DL #b-3 | [[#root]] (no 16.1 dependency) |
| 22 #b-4 (candidate roots, units, the 48) | [[#r1]] `orphan-root`; AC-5 |
| d6a (48 kept) | [[#r1]] `ambiguous:root` |
| 22 #b-8, d1c (pytest entities) | [[#r1]] `missing-file`; AC-7; [[#test-strategy]] |
| 22 #s-5 | [[#r1]] `orphan-alias`; AC-2 |
| 22 #s-6 (row identity) | [[#r1]] `duplicate` |
| 22 #m-1 | AC-5, AC-6 |
| 22 #m-2 | [[#r3]], AC-4 |
| 22 #m-6, d6e/d8g | [[#r4]] |
| d8a | [[#r1]] `stale-subject` |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan16-22-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]]. Later rows win.

| finding / decision | answered in |
|---|---|
| re-review s-1 (candidate set is not the probe's; one file counted twice) / #t9-fixes "22.1a's candidate set matches the probe" | [[#r1]] candidate set = the walk only, no `$HOME` candidate; realpath de-dup; AC-5a + three mutations; AC-5b reproduces 476 / 48 / 563 |
| re-review s-2 / d9b (rows that read correctly today under no project store) | [[#r1-outcome]] `orphan-root:home-readable` (readable-today attribute; not a removal class; routed to 22.5's held-for-user bucket) |
| re-review s-3 (census ACs on live clones) / #t9-fixes "sandbox-safe catalog clones" | AC-5/6/7 split into sandbox tests (a) and operator census steps (b) on a `cp` of `catalog.read.duckdb`; [[#test-strategy]] |
| re-review b-4 (one verifier) | [[#r1]] verification calls 16.6's `permissive_matching_lines`; no matcher here |
| re-review m-3 item 7 (plan-19's `stale` mark) | [[#r1]] `stale-subject` names 19.4 R5 as the writer |
| plan-22 r1 b-4 (partial) | closed by the s-1 row |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan16-22-spec-rereview-r3-6091648]]. Later rows win over round 2.

| finding / decision | answered in |
|---|---|
| r3 b-1 (AC-5b gate unsatisfiable: the probe's walk had exclusions; the verification rule was unrecorded) | [[#r1-probe]] (probe source RECOVERED from the transcript: its exact prune set, `$HOME/<rel>` candidate, case-sensitive `re.search` line check; 973,157 files today vs 972,849); [[#appendix-probe]]; AC-5a reproduction-script fixtures + three mutations; AC-5b churn-bounded `reproduced`/`drift`, gating on completeness only |
| r3 b-1 (round 2's "`$HOME/<rel>` is not a candidate") | withdrawn in [[#r1-probe]]; it stays out of the classifier's set [[#r1-applied]] |
| r3 s-3 (an `Unverifiable`-only entity falls into a removal class; the subset is not rare) | [[#r1-outcome]] item 4 `orphan-root:unverifiable` (kept, held, counted by reason; 26 such relative global entities in the log); AC-1, AC-5a + mutation; 22.2 R9; 22.5 R1 |
| r3 s-6 (census "through a sandbox daemon" has no procedure) | [[#r3]] one pure classifier over a read-only connection; AC-5b/6b/7b and [[#test-strategy]] cite [[task-16.6-learned-row-validation#r7]] |
| r3 m-2 (line splitting) | [[#r1]] verification: lines split on `b"\n"` (16.6 R2) |
| r3 `#open-22` item 8 (walk exclusions: spec-settleable) | settled by [[#r1-probe]] / [[#r1-applied]]; the two walks are reported side by side in AC-5b |

rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan16-22-spec-rereview-r4-878647c]] where it touches 22.1a. Later rows win.

| finding / decision | answered in |
|---|---|
| r4 m-1 (appendix not byte-exact; probe outside the procedure; no file list) | [[#appendix-probe]] byte-exact with sha256, line and tool-use id; AC-5b item 1 runs as `--census probe-reproduction` (listed in [[task-16.6-learned-row-validation#r7]]); [[#files-to-modify]] |
| r4 m-2 (churn bound needs an uncompacted log; the instant is the snapshot) | AC-5b item 2: instant = `09:29Z` snapshot mtime; compaction check and the `undercounted` label |
| r4 s-3 (census `HOME` redirect empties `home_base`) | [[#r1-applied]]: the census refuses a classifier run without explicit `--candidate-trees` / `--home-base`; 16.6 R7 owns the script and its AC |
| r3 s-6 (partial: census procedure) | closed with s-3 in [[task-16.6-learned-row-validation#r7]] |

rel: amends -> [[bsd-plan16-22-spec-rereview-r4-878647c]]

## Revision: dangling-link (2026-10-14, d9an) {#rev-dangling}

| finding / decision | answered in |
|---|---|
| d9an; bug-111 r1 #1 (an unanchored deferral: no plan-22 class named `entity_links` rows with a dead endpoint) | [[#r1-dangling]]; AC-8; 22.2 R9 removes it |

rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan16-22-spec-rereview-r6-0e77da3]] where it touches 22.1a, and d9aq/d9ar
([[plan-review-2026-10-14#t12-approvals]]). Later rows win over round 5 and the d9an revision.

| finding / decision | answered in |
|---|---|
| r6 b-1 / d9aq (the removal needs the dead end's NAME; measure it first) | [[#r1-dangling]] "Naming the dead end from `facts.log`" (every-row intersection, injective, nameless counted); AC-8a naming mutation; AC-8b naming and would-resurrect counts |
| r6 s-2 (no partition; partition-scoped audit misses both-dead rows) | [[#r1-dangling]] "Store scope"; [[#r3]] and [[#r4]] partition notes; AC-8a two-partition fixture + mutation "audit only the bound partition" |
| r6 s-3 / d9ar (`dangling-evidence`) | [[#r1-dangling]] the sub-class; [[#r2]] exception; AC-8a evidence rows; 22.2 removes it |
| r6 m-1 (counts: 1 `:concept`, 7 both-dead; linkage split) | [[#r1-dangling]] "Measured" table and split |
| r6 m-2 (liveness text is not the code) | [[#r1-dangling]] predicate table, incl. `dead-linkage` |
| r6 m-3 (AC-8 compares a function with itself; 8b has no procedure) | AC-8a independent recount; AC-8c AST check + two mutations; AC-8b `--census dangling-link` reading `rmxd.log`; [[#files-to-modify]] |

rel: amends -> [[bsd-plan16-22-spec-rereview-r6-0e77da3]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Appendix: the recovered probe {#appendix-probe}

The heredoc body of the transcript's Bash call named in [[#r1-probe]], BYTE-EXACT (r4 m-1):
`b38025a7-964a-49ec-bdbf-8f7e34918303.jsonl` line 2687 (1-based; the r4 report counts it 0-based
as 2686), tool-use id `toolu_01AoQVrMA99DaazFFhpJEi53`, `2026-10-07T09:31:35.988Z`; its result is
line 2688. The body between the `<<'EOF'` line and the `EOF` terminator, with its final newline,
is 1,962 bytes, sha256 `c096e7ae6bb5491d0856f18a6d848b75dd29a89111a46f2cd0f773bad195598a`
(re-extracted and re-hashed for this revision). The fenced block below is exactly those bytes.
`S` was a scratch dir holding a `cp -L` of the global `catalog.read.duckdb`, taken by the call at
line 2659 (`toolu_015vVzPVkr2736oJwNYa41BB`, `09:30:06Z`), whose listing shows that snapshot's
mtime as `Oct  7 02:29` local (`09:29Z`). The committed census script keeps these rules and changes
only how `S` and `H` are supplied.

```python
import sys, re, os, time, duckdb
from pathlib import Path
from collections import Counter, defaultdict
S = Path(sys.argv[1]); H = Path.home()
con = duckdb.connect(str(S/".refmatrix/catalog.duckdb"), read_only=True)
rows = con.execute("""select e.id, e.path, ev.line, c.name from entities e
  join linkage_evidence ev on ev.entity_id=e.id join entities c on c.id=ev.concept_id
  where e.path is not null and e.path<>'' and substr(e.path,1,1)<>'/'""").fetchall()
ents = defaultdict(list)
for eid, path, line, cname in rows: ents[(eid, path)].append((line, cname))
t=time.time(); bybase = defaultdict(list); nfiles=0
SKIP = {"node_modules", "__pycache__", ".git", ".venv", ".venv-eval", "venv", ".tox", "build", "dist", ".refmatrix"}
for top in ("github", "claude_tools", "enduris"):
    for dp, dns, fns in os.walk(H/top):
        dns[:] = [d for d in dns if d not in SKIP]
        for f in fns:
            bybase[f].append(os.path.join(dp, f)); nfiles += 1
print(f"walked {nfiles} files in {time.time()-t:.1f}s")
def matches(text, pat):
    try: return re.search(pat, text) is not None
    except re.error: return pat in text
cache = {}
def lines_of(p):
    if p not in cache:
        try: cache[p] = Path(p).read_text(errors="replace").splitlines()
        except OSError: cache[p] = None
    return cache[p]
res = Counter()
for (eid, rel), evs in ents.items():
    # candidates: home-relative first, then suffix matches anywhere walked
    cands = set()
    if (H/rel).exists(): cands.add(str(H/rel))
    suf = "/" + rel.lstrip("./")
    for p in bybase.get(os.path.basename(rel), []):
        if p.endswith(suf): cands.add(p)
    ver = []
    for p in cands:
        L = lines_of(p)
        if L and any(1 <= (ln or 0) <= len(L) and matches(L[ln-1], cn.split("/",1)[1] if cn.startswith("query/") else cn) for ln, cn in evs):
            ver.append(p)
    res["verified@%d" % min(len(ver),2)] += 1
    res["cands@%d" % min(len(cands),2)] += 1
print(dict(res))
```

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan16-22-spec-rereview-r8-23ad703]] where it touches 22.1a (m-2) and d9bl
([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at `23ad703` (0.78.3,
`edge_records.resolve_legacy_kind`, rebuild Pass 2b). Later rows win over round 7.

| finding / decision | answered in |
|---|---|
| r8 m-2 (naming and reborn must use the one legacy rule; the 15 two-kind reborn names) | [[#r1-covering]] (an event covers by `c_kind`, or a legacy one by `resolve_legacy_kind` over the LOGGED kinds through the rebuild's own `edge_records.resolve_c_kind`; `legacy_unresolved`); `unnamed:reborn` now names every live covering key, not one best key; "Measured" re-measured (896 reborn, 381 on more than one live key, 47 ids / 121 rows to remove, all legacy misresolutions on 10 two-kind names; round 7's "15 as both" was a tie-break artefact); AC-8a covering row + three mutations; AC-8b reference reading |
| r8 b-1 / d9bl (one format, one resolver) | [[#r1-covering]] uses 16.6's resolver; the apply-side spelling is [[task-22.2-repair-then-remove#r3]] |

rel: amends -> [[bsd-plan16-22-spec-rereview-r8-23ad703]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: depends-on -> [[task-16.6-learned-row-validation#r1d-one-format]]

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan16-22-spec-rereview-r7-331b414]] where it touches 22.1a (m-1, m-2, m-3).
Code claims re-read at `77ac38f`. Later rows win over round 6.

| finding / decision | answered in |
|---|---|
| r7 m-1 (the 8 "nameless" ids are reborn; the audit had no label for it; the evidence side has the same shape) | [[#r1-dangling]] `unnamed:reborn` label; "Measured" corrected (8 reborn link-side; 896 reborn and 3,882 none evidence-side, measured for this round); AC-8a reborn row + mutation; AC-8b reference reading; the apply rule is [[task-22.2-repair-then-remove#r9-dangling]] |
| r7 m-2 (AC-8c too broad and too narrow; the names; the bit half) | [[#r1-dangling]] "One shared predicate": `LinkLiveness` carries the id→(partition, kind, name) and linkage id→name maps; both halves of `repair_fragments` (rows and bits) call `dead_side`; AC-8c over the whole module, forbidding `NOT IN (SELECT id …)` and id-set construction, three mutations |
| r7 m-3 (naming without a partition; "the store's default" undefined for a census; `facts_path` unlisted) | [[#r1-dangling]] condition (iii) per partition, the default partition an explicit input; [[#r3]] `inputs.facts_path`, `inputs.default_partition`; AC-8a partition row + mutation; AC-8b `--default-partition`; the census flag is in [[task-16.6-learned-row-validation#r7]] |
| r7 b-1 / d9av, s-1, s-2, s-3 | not this task's: [[task-22.2-repair-then-remove#rev-round-7]], [[task-22.3-bug-086-global-repair#rev-round-7]] |

rel: amends -> [[bsd-plan16-22-spec-rereview-r7-331b414]]
