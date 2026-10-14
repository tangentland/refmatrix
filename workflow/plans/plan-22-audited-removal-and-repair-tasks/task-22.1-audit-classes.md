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
> Status: Pending (revision round 2, 2026-10-14; [[#rev-round-2]])
> Wave: 2 (d6d). The provenance-free classes moved to [[task-22.1a-provenance-free-classes]]
> (Wave 1).
> Depends on: 22.1a (verb, plan manifest format), 22.2 (engine), 16.6 Wave-1 slice (sidecar +
> backfill + THE verifier `learned_verify` + read-time marks), 16.1's learn-time provenance write
> (tool + dialect + flags + line hash; d6d moved it into 16.1).

rel: part-of -> [[plan-22-audited-removal-and-repair]]
rel: depends-on -> [[task-22.1a-provenance-free-classes]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: derives-from -> [[plan-review-2026-10-14#t6-fixes]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: depends-on -> [[task-23.4-option-a-measurement]]

## Requirements {#requirements}

1. **R1 Learned-row classes, per `(concept, file)` SET (22 #b-1).** The learner writes a row for
   EVERY hit line (`_learn_grep_hits`, `daemon.py:4295`); 97.7% of distinct learned rows in this
   repo's log sit in a multi-line pair. So classification is per `(concept, file)` set, never per
   row: the pattern is re-run over the file under the verification rule ([[#r1-verify]]), giving
   the current matching line set `N`; the recorded set is `O`. {#r1}
   - **`N` across readings (m-5).** A set's rows can carry several sidecar readings (`none` plus a
     recorded one, or `-i` plus plain). `N` is the UNION over every reading present on the set's
     rows of 16.6's `matching_lines` (recorded rules) and `permissive_matching_lines` (`none`). If
     any reading returns `Unverifiable`, `N` is partial: a line of `O` found in the partial union
     is still `ok`, but no line of `O` may be called `stale-line`, and the set is not `moved`,
     `grown` or `shrunk`: its unmatched rows are `unverifiable` with that reading's reason.
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
   - `unverifiable` — 16.6's verifier returned `Unverifiable(reason)` for a reading the row needs,
     with `reason` in `learned_verify.UNVERIFIABLE_REASONS` (`no-rules`, `bin-missing`, `timeout`,
     `tool-error`, `permissive-subset`, `unreadable`): one definition shared with 16.6 (m-4). Kept,
     counted by reason, never removed.
   - `ambiguous` (row-level remainder) — a hashed row whose hash appears on several lines of `N`.
     Kept.
2. **R1-verify The verifier is 16.6's (b-4; 16 #b-r5-1; #t6-fixes; #t9-fixes).** {#r1-verify}
   - This task carries NO matcher and NO dialect translation. Every row is decided by
     [[task-16.6-learned-row-validation#r2]]'s `learned_verify` module, by these exact calls:
     `learned_verify.matching_lines(file_abs, rules)` for each recorded reading (`Rules` built from
     the sidecar row), `learned_verify.permissive_matching_lines(file_abs, pattern)` for a `none`
     reading, and `learned_verify.hash_line(raw)` for hash pairing. The line set `N` of [[#r1]] is
     built from those returns, not from per-row verdicts.
   - **Rows with recorded rules** are re-run with the recorded tool and only its pattern-semantics
     tokens (16.6 [[task-16.6-learned-row-validation#r2-argv]]): a BRE `\|`, a POSIX class, `\<`,
     a `-l`/`-m` cutoff and a caller's `--exclude` all verify as the caller's grep read them. An
     exit ≥ 2 is `unverifiable` (`tool-error`), never `stale-line`.
   - **Pre-provenance rows** (`rules_sha=none`: every row learned before 16.1;
     `_broker_learn_from_grep`, `cli.py:613`, sent no flags, and `query/<pattern>` is shared by
     `-i`, plain and `-E` callers) use 16.6's MOST PERMISSIVE reading
     ([[task-16.6-learned-row-validation#r2-permissive]]): case-insensitive; literal OR regex; plus
     `identifier_variant_regex` (`store.py:786`); a pattern with a construct Python reads
     differently is `unverifiable` (`permissive-subset`). A row is `stale-line` only if every
     reading returned a set and none holds the line. This reading is safe for these rows because
     the teach path has refused BRE escapes since 0.65.1 (`cli.py:6168-6178`), and it stays safe
     because 16.6 R1d keeps provenance through a rebuild (no row loses its rules later).
   - Mutation (pre-registered): "translate the pattern to Python `re` and match with
     `evidence_line_matches`" FAILS AC-4.
3. **R1-marks 16.6's read-time marks are read here (b-3).** {#r1-marks}
   - The audit reads `stale_seen`, `last_mark` and `last_verified_at` from the sidecar
     ([[task-16.6-learned-row-validation#r4-reader]]). Sets holding a row with `stale_seen > 0` or a
     non-NULL `last_mark` are verified FIRST (so a bounded or interrupted audit covers them), and
     each such row is listed in the plan manifest with its `last_mark` and its `stale_seen` printed
     as "at least N".
   - The report prints, per class, the count and age distribution (min / median / max, and "never")
     of `last_verified_at`.
   - **A mark never decides a class.** Every row is re-verified through 16.6's verifier regardless
     of its marks, and its class comes from that run. `stale_seen` is a LOWER BOUND
     ([[task-16.6-learned-row-validation#r4-lower-bound]]): it is never compared to a threshold and
     never read as an exact count.
4. **R2 `empty-learned`, redefined so it can fail (22 #b-6, d6c).** A protected `query/*` concept
   ALL of whose learned evidence rows classify `stale-line`, `out-of-range` or `missing-file`
   (none `ok`, `moved`, `grown`, `shrunk`, `ambiguous`, `unverifiable`), and that has no link other
   than learned `mentions`. A `query/*` concept with df ≤ 1 and one `ok` row is NOT a member
   (d6c); no df or counter enters the predicate. {#r2}
5. **R3 Read-only**, exactly as [[task-22.1a-provenance-free-classes#r3]]. {#r3}
6. **R4 Output** extends the `removal_audit` plan manifest with these classes and, for each
   `moved`/`grown`/`shrunk` set, the old and new line sets; each `unverifiable` row with its
   reason; each marked row with its marks ([[#r1-marks]]). {#r4}

## Acceptance criteria {#acceptance}

1. **Two-hit shift (22 #b-1).** A file with hits at lines 10 and 20 gains two lines at the top:
   the set classifies `moved`, and after 22.2's apply both rows sit at 12 and 22 with 0 rows
   `ambiguous` and 0 rows deleted. Mutation: a per-row "exactly one other line" rule must FAIL.
2. **Hash pairing.** With hashes recorded, swapping the two hit lines re-points by hash (each row
   follows its own text). Mutation: pairing by order when hashes exist must FAIL.
3. **Pre-provenance `-i` row (22 #b-2).** A row without provenance whose line matches only
   case-insensitively classifies `ok`, not `stale-line`. Mutation: verifying under the defaults
   must FAIL.
4. **Dialect, through 16.6's verifier (b-4).** Provenance rows recorded by 16.1 R10
   (`tool=grep`, `bin=/usr/bin/grep`, `dialect=bre`) verify `ok`: BRE `foo\|bar` on a line holding
   `bar`; `[[:digit:]]` on `a1`; `\<foo\>` on `foo bar`. A row whose recorded `bin` now rejects
   its pattern (grep `a\{`, exit 2) classifies `unverifiable` (`tool-error`) and is in no removal
   list. Mutation "translate to Python `re` and match with `evidence_line_matches`" FAILS it (the
   POSIX-class and `\<…\>` rows become `stale-line`); mutation "a second matcher inside 22.1"
   is detected by the test asserting that `learned_verify.matching_lines` is the only call that
   decided a recorded-rules row (call recorded through the module, not a mock of it).

   **4b. Readings union (m-5).** A set whose rows carry readings `none` and `-i`, where a line matches
   only case-insensitively under `-i`, is `ok`; a set with one reading returning `Unverifiable`
   and a line of `O` absent from the other readings' sets classifies that row `unverifiable`,
   never `stale-line`. Mutation "`N` from the first reading only" FAILS it.

   **4c. Marks are read (b-3).** A fixture row with `stale_seen = 2`, `last_mark = missing-file`
   appears in the plan manifest with its mark and "at least 2"; it is verified before an unmarked
   set of the same store; a marked row whose file is back and matching classifies `ok` (the mark
   decided nothing). Mutation "ignore the sidecar marks" FAILS the listing; mutation "class from
   `last_mark`" FAILS the last clause.
5. **`grown`/`shrunk`.** Deleting one of three hit lines yields `shrunk` with exactly one
   `stale-line` row; adding a hit yields `grown` with the new line reported and no row added.
6. **`empty-learned` can fail (22 #b-6, #m-1; s-3).**
   - **6a, sandbox test.** A concept with one `ok` row and df 1 is NOT a member; a concept whose
     only rows are `missing-file` IS; on a sandbox fixture store the count equals an independent
     SQL+file recount exactly.
   - **6b, operator census.** On a `cp` of this repo's `catalog.read.duckdb` snapshot (the
     procedure of [[task-23.4-option-a-measurement#r1]]; never the writer slot, no `Store()` on a
     live root, no `rmx` call), read through a sandbox daemon, the audit's count equals the
     independent recount on the same copy; the result goes to
     `workflow/review-output/22.1-empty-learned-census.log` and the summary. No presumed bound (the
     "747" is withdrawn).
7. **Read-only** as 22.1a AC-4.

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): redirected `$HOME`/global root/registry before
import, in-process `Daemon` + `Store` on a short `mkdtemp`, no `rmx` subprocess, the 23.0 guard
active, real `/usr/bin/grep` and `rg` (16.6's verifier re-runs them). No test reads a live catalog:
AC-6b is an OPERATOR census on a `cp` of the `catalog.read.duckdb` snapshot, logged under
`workflow/review-output/` and cited in the summary (s-3). Each mutation is pre-registered and must
turn its test RED.

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

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan16-22-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]]. Later rows win.

| finding / decision | answered in |
|---|---|
| re-review b-4 (Python translation contradicts 16.6 R2) / #t9-fixes "22.1 calls 16.6's verifier, which returns the matching line set" | [[#r1-verify]] (no matcher, no translation; exact calls named); [[#r1]] `N` from `matching_lines`; AC-4 + mutations |
| re-review b-3 (marks have no reader) | [[#r1-marks]]; AC-4c + two mutations |
| re-review b-2 (rebuild would strip provenance and send rows to the permissive reading) | [[#r1-verify]] "stays safe because 16.6 R1d" (the fix is 16.6's) |
| re-review m-4 (`unverifiable` had three definitions; `stale` vs `stale-line`) | [[#r1]] `unverifiable` = 16.6's `UNVERIFIABLE_REASONS`; class names shared with 16.6 R2 |
| re-review m-5 (which reading defines `N`) | [[#r1]] "`N` across readings"; AC-4b |
| re-review s-3 (census AC on a live clone) / #t9-fixes "sandbox-safe catalog clones" | AC-6 split (6a sandbox, 6b operator census on a copied read snapshot); [[#test-strategy]] |
| plan-22 r1 b-2 (partial) | closed by the b-4 row |
