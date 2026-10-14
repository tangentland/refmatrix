---
gmd: "0.1"
id: task-22.1-audit-classes
title: "Task 22.1: the audit's flag-sensitive classes — moved per (concept, file) set, stale-line, out-of-range, unverifiable, empty-learned"
tags: [task, audit, grep-learning, concepts, wave-2]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  revised: 2026-10-14
---

# Task 22.1: the flag-sensitive audit classes {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 2 (d6d). The provenance-free classes moved to [[task-22.1a-provenance-free-classes]]
> (Wave 1).
> Depends on: 22.1a (verb, plan manifest format), 22.2 (engine), 16.6 Wave-1 slice (sidecar +
> backfill), 16.1's learn-time provenance write (tool + dialect + flags + line hash; d6d moved it
> into 16.1).

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: derives-from -> [[plan-review-2026-10-14#t6-fixes]]

## Requirements {#requirements}

1. **R1 Learned-row classes, per `(concept, file)` SET (22 #b-1).** The learner writes a row for
   EVERY hit line (`_learn_grep_hits`, `daemon.py:4295`); 97.7% of distinct learned rows in this
   repo's log sit in a multi-line pair. So classification is per `(concept, file)` set, never per
   row: the pattern is re-run over the file under the verification rule ([[#r1-verify]]), giving
   the current matching line set `N`; the recorded set is `O`. {#r1}
   - `ok` — every line of `O` still matches.
   - `moved` — `|N| = |O|`, `N ≠ O`. Repair pairs `O` to `N` in line order (i-th to i-th). When
     every row of the set carries 16.6's recorded line hash, the pairing is by hash instead, and
     the set is `moved` only if every hash finds exactly one line in `N`; a row without a hash
     never blocks the set (the hash is an extra check only on rows that have one).
   - `grown` / `shrunk` — `|N| ≠ |O|`. Lines of `O` still in `N` stay; lines of `O` with no match
     anywhere in the file are `stale-line` rows; new lines of `N` are REPORTED, not added (adding is
     learning, which grep does on real use).
   - `stale-line` — the pattern matches nowhere in the file under any permitted reading.
   - `out-of-range` — a recorded line is past the end of the file and the pattern matches nowhere.
   - `unverifiable` — the row's recorded dialect cannot be translated to the verifier (or the
     pattern does not compile in it). Kept, counted, never removed.
   - `ambiguous` (row-level remainder) — a hashed row whose hash appears on several lines of `N`.
     Kept.
2. **R1-verify The verifier (22 #b-2; 16 #b-r5-1; #t6-fixes).** {#r1-verify}
   - Rows with 16.1/16.6 provenance are verified under their recorded tool, dialect and flags,
     using the existing `evidence_line_matches` (`store.py:759`) as the one matcher, with the
     pattern first translated from the recorded grep dialect (BRE / ERE / fixed / rg) to Python
     `re`. No second matcher.
   - Pre-provenance rows (every row learned before 16.1; `_broker_learn_from_grep`,
     `cli.py:613`, sent no flags, and `query/<pattern>` is shared by `-i`, plain and `-E` callers)
     are verified under the MOST PERMISSIVE reading: case-insensitive; literal OR regex; plus
     `identifier_variant_regex` (`store.py:786`). A row is `stale-line` only if every reading
     fails.
3. **R2 `empty-learned`, redefined so it can fail (22 #b-6, d6c).** A protected `query/*` concept
   ALL of whose learned evidence rows classify `stale-line`, `out-of-range` or `missing-file`
   (none `ok`, `moved`, `grown`, `shrunk`, `ambiguous`, `unverifiable`), and that has no link other
   than learned `mentions`. A `query/*` concept with df ≤ 1 and one `ok` row is NOT a member
   (d6c); no df or counter enters the predicate. {#r2}
4. **R3 Read-only**, exactly as [[task-22.1a-provenance-free-classes#r3]]. {#r3}
5. **R4 Output** extends the `removal_audit` plan manifest with these classes and, for each
   `moved`/`grown`/`shrunk` set, the old and new line sets. {#r4}

## Acceptance criteria {#acceptance}

1. **Two-hit shift (22 #b-1).** A file with hits at lines 10 and 20 gains two lines at the top:
   the set classifies `moved`, and after 22.2's apply both rows sit at 12 and 22 with 0 rows
   `ambiguous` and 0 rows deleted. Mutation: a per-row "exactly one other line" rule must FAIL.
2. **Hash pairing.** With hashes recorded, swapping the two hit lines re-points by hash (each row
   follows its own text). Mutation: pairing by order when hashes exist must FAIL.
3. **Pre-provenance `-i` row (22 #b-2).** A row without provenance whose line matches only
   case-insensitively classifies `ok`, not `stale-line`. Mutation: verifying under the defaults
   must FAIL.
4. **Dialect.** A provenance row recorded as BRE `foo\|bar` verifies `ok` on a line holding `bar`;
   a row whose dialect does not compile classifies `unverifiable` and is not in any removal list.
5. **`grown`/`shrunk`.** Deleting one of three hit lines yields `shrunk` with exactly one
   `stale-line` row; adding a hit yields `grown` with the new line reported and no row added.
6. **`empty-learned` can fail (22 #b-6, #m-1).** A concept with one `ok` row and df 1 is NOT a
   member; a concept whose only rows are `missing-file` IS. On a clone of this repo's catalog the
   count equals an independent SQL+file recount exactly; no presumed bound (the "747" is withdrawn).
7. **Read-only** as 22.1a AC-4.

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): redirected `$HOME`/global root/registry before
import, in-process `Daemon` + `Store` on a short `mkdtemp`, no `rmx` subprocess, the 23.0 guard
active. Clone-based ACs read a scratch clone through a sandbox daemon. Each mutation is
pre-registered and must turn its test RED.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered in |
|---|---|
| 22 #b-1 (hash nobody records; per-row uniqueness) | [[#r1]]; AC-1, AC-2 |
| 22 #b-2, 16 #b-r5-1 (flags, dialect, permissive re-check) | [[#r1-verify]]; AC-3, AC-4 |
| 22 #b-6, d6c (`empty-learned`) | [[#r2]]; AC-6 |
| 22 #b-7, d6d (split, Wave 2) | [[#root]] |
| 22 #m-1 | AC-6 |
| 22 #m-2 | [[#r3]] |
| #t6-fixes (line hash from 16.6; set repair; tool+dialect+hash) | [[#r1]], [[#r1-verify]] |
