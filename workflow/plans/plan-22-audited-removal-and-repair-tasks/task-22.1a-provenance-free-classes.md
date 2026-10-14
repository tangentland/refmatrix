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
> Status: Pending (revision round 5, 2026-10-14; [[#rev-round-5]]; round 3 in [[#rev-round-3]])
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
2. **R2 Ingest is out of scope.** No class selects an ingested evidence row (`detail` not
   `learned from grep…`), a `tracked_files` row, or an entity with an ingest link. A learned file
   entity that is also ingested is reported `shared` and never becomes `missing-file` or
   `orphan-root:unresolved` as a whole; only its learned rows are classified. {#r2}
3. **R3 Read-only, defined (22 #m-2).** The audit is a daemon READ op over the lock-free read
   snapshot. It writes no catalog row, no Lance version, no queue entry and no `facts.log` event.
   It enqueues NO `stale_seen` marks (those belong to 16.6's grep read path). Its only output is the
   plan manifest file `.refmatrix/removal/<id>.plan.jsonl` plus its sha256, which 22.2's apply
   requires (d8g). {#r3}
   - **One classifier, two callers (r3 s-6).** The classes are computed by ONE pure function,
     `removal_audit.classify_provenance_free(conn, inputs) -> AuditPlan`, where `conn` is a
     read-only DuckDB connection to a catalog file and `inputs` carries `store_root`, `partition`,
     `candidate_trees`, `walk_prunes` and `home_base`. The daemon op passes the connection its
     read-snapshot ops already use; the operator census passes `duckdb.connect(<copy>,
     read_only=True)` through the ONE census procedure,
     [[task-16.6-learned-row-validation#r7]]. No census constructs `Daemon` or `Store`.
4. **R4 Verb and output (d6e as amended by d8g; 22 #m-6).** `removal_audit` is a verb exposed as
   `rmx removal audit --root R` and as the MCP tool `rmx_removal_audit`. Output: counts per class
   and per `query/*` pattern; `--list` for members; `--json` for the plan. The plan manifest
   records: store root, partition, catalog identity (active slot + snapshot version), the
   walk's `candidate_trees`, `walk_prunes` and `home_base`, every member with its class, its
   recorded resolution, its readable-today attribute and (for `orphan-root:unverifiable`) its
   `Unverifiable` reasons.
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
| `tests/test_removal_audit.py` (new) | AC-1..AC-4, AC-5a, AC-6a, AC-7a |

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
