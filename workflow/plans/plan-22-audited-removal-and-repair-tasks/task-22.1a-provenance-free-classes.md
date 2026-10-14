---
gmd: "0.1"
id: task-22.1a-provenance-free-classes
title: "Task 22.1a: the audit's provenance-free classes (orphan-root, missing-file, duplicate, orphan-alias, stale-subject) and the read-only removal_audit verb"
tags: [task, audit, grep-learning, concepts, bug-086, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
---

# Task 22.1a: the provenance-free audit classes {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 1, after 23.1 and 16.6's Wave-1 slice (d6d; #t8-amendments; #t8-wave1).
> Depends on: 23.0 (test sandbox), 16.6 Wave-1 slice (sidecar + backfill). NOT on 16.1.
> Feeds: 22.2 → 22.5 → 22.3.

Split out of 22.1 by d6d and #t8-amendments: these classes are decidable without learn-time
provenance (the 2026-10-07 probe decided `orphan-root` without it), so bug-086's repair is not
parked behind Wave 2 (22 #b-7, DL #b-3). The flag-sensitive classes stay in
[[task-22.1-audit-classes]].

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
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
     exactly (22 #b-4):
     - **Candidate roots** = `$HOME` (where the current producer resolves global rows) plus every
       file found by a suffix walk over `~/github`, `~/claude_tools` and `~/enduris`, the probe's
       three trees (`workflow/review-output/global-relative-resolve-probe.log`).
     - **Walk exclusions** (pre-registered, reported as their own delta): `.git/`, `.venv*/`,
       `node_modules/`, `__pycache__/`, `.refmatrix/`, `.claude/worktrees/`,
       `~/github/atollogy/bdep/_frameworks_and_libraries/`. The deploy tree `~/refmatrix` is not
       under any of the three trees.
     - **Verification** per candidate: the file exists and at least one of the entity's recorded
       lines holds the `query/<pattern>` text under the permissive reading of
       [[task-22.1-audit-classes#r1-verify]] (case-insensitive; literal OR regex; plus
       `identifier_variant_regex`, `store.py:786`). This module-level reading needs no
       provenance.
     - **Outcome** per entity: `verified@1` → `orphan-root:resolved` with the absolute path recorded
       for 22.5; `verified@≥2` → `ambiguous:root` (kept, all candidates recorded; d6a);
       `verified@0` → `orphan-root:unresolved` (removal candidate).
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
   - `stale-subject` (unit: ENTITY) — a compiled subject marked `stale` by plan-19's compile (d8a).
     The audit only reports it; the class is inert until plan-19 writes the mark.
2. **R2 Ingest is out of scope.** No class selects an ingested evidence row (`detail` not
   `learned from grep…`), a `tracked_files` row, or an entity with an ingest link. A learned file
   entity that is also ingested is reported `shared` and never becomes `missing-file` or
   `orphan-root:unresolved` as a whole; only its learned rows are classified. {#r2}
3. **R3 Read-only, defined (22 #m-2).** The audit is a daemon READ op over the lock-free read
   snapshot. It writes no catalog row, no Lance version, no queue entry and no `facts.log` event.
   It enqueues NO `stale_seen` marks (those belong to 16.6's grep read path). Its only output is the
   plan manifest file `.refmatrix/removal/<id>.plan.jsonl` plus its sha256, which 22.2's apply
   requires (d8g). {#r3}
4. **R4 Verb and output (d6e as amended by d8g; 22 #m-6).** `removal_audit` is a verb exposed as
   `rmx removal audit --root R` and as the MCP tool `rmx_removal_audit`. Output: counts per class
   and per `query/*` pattern; `--list` for members; `--json` for the plan. The plan manifest
   records: store root, partition, catalog identity (active slot + snapshot version), the
   walk's candidate trees and exclusions, every member with its class and recorded resolution.
   Exit 0 when the scan completes; any unreadable input is counted and printed, never skipped
   silently. {#r4}

## Acceptance criteria {#acceptance}

1. **One row per class.** A sandbox fixture with one member of each class (incl.
   `ambiguous:root`, `orphan-alias:repairable`, `orphan-alias:unrepairable`, `shared`) audits each
   member to exactly its class; the resolved `orphan-root` records the right absolute path.
2. **Case-variant canonical (22 #s-5).** An alias `alias of 'Store'` with only `store` existing
   classifies `orphan-alias:unrepairable`. Mutation: resolving through `canonical_name` must FAIL
   this AC.
3. **Permissive reading.** An `orphan-root` fixture whose line matches the pattern only
   case-insensitively resolves `verified@1`. Mutation: verifying case-sensitively must FAIL.
4. **Read-only.** With the daemon tick stopped, an audit leaves the catalog file hash, every Lance
   dataset version, the learn/mark queue files and `facts.log` byte-identical; only
   `.refmatrix/removal/` gains the plan file. Mutation: an audit that enqueues one mark must FAIL.
5. **Probe reproduced (22 #b-4, #m-1).** On an APFS clone of the global catalog (never the live
   store), the audit with exclusions OFF reports the 2026-10-07 split 476 / 48 / 563 of 1,087,
   with every difference explained by an entity created or tombstoned after 2026-10-07 (named from
   `facts.log`) or a file changed since; the exclusions-ON split is reported beside it as the one
   22.5/22.3 apply.
6. **Independent recount (22 #m-1).** On clones of this repo's catalog and the global catalog, each
   class count equals an independent SQL recount of its predicate on the same clone, exactly. The
   exploration's 9,182 orphan aliases is printed beside the recount as drift, not used as a bound.
7. **pytest rows.** On the global clone, `missing-file` includes every entity whose path contains
   `/pytest-of-` (1,655 at the review; recount exact).

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): `$HOME`, the global root, the registry and
LaunchAgents redirected to a short `mkdtemp` before `refmatrix` is imported; in-process `Daemon` +
`Store`; no `rmx` subprocess; the 23.0 conftest guard fails any touch of `~/.refmatrix` or a live
store. AC-5..7 run on clones under the scratch dir, read through a sandbox daemon pointed at the
clone. Every listed mutation is pre-registered and must turn its test RED.

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
