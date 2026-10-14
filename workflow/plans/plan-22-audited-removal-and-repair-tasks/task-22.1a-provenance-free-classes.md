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
> Status: Pending (revision round 2, 2026-10-14; [[#rev-round-2]])
> Wave: 1, after 23.1 and 16.6's Wave-1 slice (d6d; #t8-amendments; #t8-wave1).
> Depends on: 23.0 (test sandbox), 16.6 Wave-1 slice (sidecar + backfill). NOT on 16.1.
> Feeds: 22.2 → 22.5 → 22.3.

Split out of 22.1 by d6d and #t8-amendments: these classes are decidable without learn-time
provenance (the 2026-10-07 probe decided `orphan-root` without it), so bug-086's repair is not
parked behind Wave 2 (22 #b-7, DL #b-3). The flag-sensitive classes stay in
[[task-22.1-audit-classes]].

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
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
     exactly (22 #b-4):
     - **Candidate set = the probe's, exactly (s-1).** For a relative entity name `rel`, the
       candidates are the files found by a suffix walk over the three trees `~/github`,
       `~/claude_tools` and `~/enduris` (the 2026-10-07 probe,
       `workflow/review-output/global-relative-resolve-probe.log`, `walked 972849 files`) whose
       path ends with `/rel`. `$HOME/<rel>` is NOT added as a candidate (the probe's walk pass did
       not add it; its 476 / 48 / 563 split is the walk's). The trees and the home directory are
       explicit inputs recorded in the plan manifest (`candidate_trees`, `home_base`), defaulting
       to `Path.home()`-relative values in production, so a sandbox daemon reading a copied catalog
       can walk the real trees read-only.
     - **De-duplication (s-1).** Candidates are de-duplicated by `os.path.realpath` before
       counting: one file reached two ways (a symlink, or overlapping trees) is ONE candidate, so
       it cannot turn a `verified@1` entity into `ambiguous:root`.
     - **Walk exclusions** (pre-registered, OFF for the probe reproduction, ON for the applied
       split, the two splits reported side by side): `.git/`, `.venv*/`, `node_modules/`,
       `__pycache__/`, `.refmatrix/`, `.claude/worktrees/`,
       `~/github/atollogy/bdep/_frameworks_and_libraries/`. The deploy tree `~/refmatrix` is not
       under any of the three trees.
     - **Verification** per candidate: the file exists and at least one of the entity's recorded
       lines holds the `query/<pattern>` text under 16.6's permissive reading,
       `learned_verify.permissive_matching_lines(file_abs, pattern)`
       ([[task-16.6-learned-row-validation#r2-permissive]]: case-insensitive; literal OR regex;
       plus `identifier_variant_regex`, `store.py:786`). This needs no provenance, and 22.1a
       carries no matcher of its own. A candidate whose reading is `Unverifiable` does not count
       as verified and is recorded with its reason.
     - **Readable today (d9b; re-review s-2).** Separately from the candidate count, every entity
       records whether `home_base/<rel>` exists and verifies under the same reading: that is
       where `grep_evidence` resolves global rows TODAY (`Path(root).parent`, `cli.py:667`,
       `daemon.py:2136`), so such a row is not bug-086's symptom. The attribute never changes the
       probe-reproduction counts; it only routes the applied split ([[#r1-outcome]]).
     - **Outcome** per entity, applied split: {#r1-outcome}
       - `verified@1` → `orphan-root:resolved` with the absolute path recorded for 22.5; when the
         entity is also readable today at a DIFFERENT realpath, it is `ambiguous:root` instead
         (two live readings, d6a).
       - `verified@≥2` → `ambiguous:root` (kept, all candidates recorded; d6a).
       - `verified@0` and readable today → `orphan-root:home-readable`: NOT a removal class. It is
         handed to 22.5 R1, which reports it as its own bucket and applies nothing to it until the
         user rules (d9b).
       - `verified@0` and not readable today → `orphan-root:unresolved` (removal candidate).
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
   walk's `candidate_trees`, `home_base` and exclusions, every member with its class, its recorded
   resolution and its readable-today attribute.
   Exit 0 when the scan completes; any unreadable input is counted and printed, never skipped
   silently. {#r4}

## Acceptance criteria {#acceptance}

1. **One row per class.** A sandbox fixture with one member of each class (incl.
   `ambiguous:root`, `orphan-root:home-readable`, `orphan-alias:repairable`,
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
5. **Probe reproduced (22 #b-4, #m-1, s-1).**
   - **5a, sandbox test (gates).** A fixture global store and a fixture tree set: a relative
     entity whose file is reachable through a symlink AND directly resolves `verified@1`
     (mutation "no realpath de-dup" FAILS it: it reads `verified@2`); a `verified@0` entity whose
     `home_base/<rel>` verifies classifies `orphan-root:home-readable`, never
     `orphan-root:unresolved` (mutation "drop the readable-today attribute" FAILS it); with
     exclusions OFF and `home_base` unused, the fixture's split equals its hand-computed split
     exactly (mutation "add `home_base/<rel>` as a candidate" FAILS it).
   - **5b, operator census (not a suite test; s-3).** The operator copies
     `~/.refmatrix/catalog.read.duckdb` with `cp` into a short tmp dir off every watched tree (the
     procedure of [[task-23.4-option-a-measurement#r1]]: never the writer slot, no `Store()` on a
     live root, no `rmx` call, no socket), records its mtime and size, and runs the audit on the
     copy through a sandbox daemon with `candidate_trees` = the probe's three real trees (walked
     read-only). With exclusions OFF the audit reports the 2026-10-07 split 476 / 48 / 563 of
     1,087; every difference is listed by entity with its cause: created or tombstoned after
     2026-10-07 (named from a read-only parse of the global `facts.log`), or a file changed since
     (mtime after 2026-10-07). An unexplained difference fails the census and blocks 22.5/22.3.
     Beside it the audit prints the APPLIED split (exclusions ON, the readable-today routing) and
     the delta between the two, per bucket; the applied split is the one 22.5 and 22.3 use. Output:
     `workflow/review-output/22.1a-global-census.log`, cited in the summary.
6. **Independent recount (22 #m-1).** 6a: on sandbox fixture stores, each class count equals an
   independent SQL recount of its predicate, exactly. 6b (operator census, as 5b): on copies of
   this repo's and the global `catalog.read.duckdb`, each class count equals the independent
   recount on the same copy; the exploration's 9,182 orphan aliases is printed beside it as drift,
   not used as a bound.
7. **pytest rows.** 7a: a sandbox fixture entity under a `/pytest-of-<user>/` path classifies
   `missing-file`. 7b (operator census, as 5b): on the global copy, `missing-file` includes every
   entity whose path contains `/pytest-of-` (1,655 at the review; recount exact).

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): `$HOME`, the global root, the registry and
LaunchAgents redirected to a short `mkdtemp` before `refmatrix` is imported; in-process `Daemon` +
`Store`; no `rmx` subprocess; the 23.0 conftest guard fails any touch of `~/.refmatrix` or a live
store. No suite test reads a live catalog: AC-5b, 6b and 7b are OPERATOR census steps on a `cp`
of the `catalog.read.duckdb` lock-free snapshot (23.4 R1's procedure), read through a sandbox
daemon pointed at the copy, logged under `workflow/review-output/` and cited in the summary (s-3);
AC-5a, 6a and 7a are the gating sandbox tests. Every listed mutation is pre-registered and must turn
its test RED.

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
