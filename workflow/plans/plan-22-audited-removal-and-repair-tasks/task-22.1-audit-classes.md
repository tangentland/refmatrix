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
> Status: Pending (revision round 3, 2026-10-14; [[#rev-round-3]])
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
rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
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
   - **The set rule: pair, never test membership (r3 b-2).** A real edit shifts every later line,
     so "a row whose line is not in `N`" says nothing about whether its text survived (delete
     line 20 of hits `{10, 20, 30}`: the third hit is now line 29, and BOTH 20 and 30 are outside
     `N = {10, 29}` while the pattern still matches). So no row is classified by `line ∉ N`. Every
     set is paired, in this order, with every line numbered by 16.6's `split_lines` (`b"\n"`,
     r3 m-2):
     1. **Fixed points.** A row of `O` whose line is in `N` stays, if it has no `line_hash` or its
        hash equals `hash_line` of that line. A hashed row whose line is in `N` but whose hash
        differs is NOT a fixed point (another hit landed on its line; its own text moved).
     2. **Hashed rows** left over pair with the unclaimed line of `N` whose hash equals theirs:
        exactly one such line → re-point; several → `ambiguous` (kept); none → `stale-line`
        regardless of what else matches (its text is gone from the file).
     3. **Unhashed rows** left over pair with the unclaimed lines of `N` in line order, i-th to
        i-th, up to the shorter of the two lists → re-point. Without a hash the old text is not
        known, so a pairing may land a row on a NEW hit instead of its moved text; the row then
        still names a line that matches, nothing is removed, and the unpaired line is reported.
     4. **Leftovers.** Rows of `O` still unpaired (more old rows than unclaimed lines) are
        `stale-line`, labelled `out-of-range` when their recorded line is past the end of the file
        (r3 m-3: this is 22.1's ONLY use of `out-of-range`; 16.6's per-row verdict of the same
        name feeds its marks, never this classification). Lines of `N` still unclaimed are
        REPORTED, never added (adding is learning, which grep does on real use).
   - **Set classes** (precedence top to bottom): `shrunk` — at least one row is `stale-line` /
     `out-of-range`; `grown` — none, and at least one line of `N` is reported; `moved` — neither,
     and at least one row is re-pointed; `ok` — every row is a fixed point. `ambiguous` and
     `unverifiable` rows are kept inside any class. A row is removed by 22.2 only as `stale-line`
     or `out-of-range`.
   - `stale-line` (row) — unpaired after step 4, or a hashed row whose hash is on no line of `N`.
     With the union rule above, the pattern may still match elsewhere in the file; those lines
     are already claimed by other rows or reported.
   - `unverifiable` — 16.6's verifier returned `Unverifiable(reason)` for a reading the row needs,
     with `reason` in `learned_verify.UNVERIFIABLE_REASONS` (`no-rules`, `bin-missing`, `timeout`,
     `tool-error`, `permissive-subset`, `unreadable`, `locale-missing`): one definition shared
     with 16.6 (m-4). Kept, counted by reason, never removed.
   - `ambiguous` (row-level) — a hashed row whose hash appears on several unclaimed lines of `N`.
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
     reading returned a set and the set rule leaves it unpaired. The subset is NOT rare (r3 s-3):
     1,511 of 31,608 distinct learned rows in this repo's log (4.8%) and 69 of 495 global
     `query/*` concepts hold a subset construct, some taught after 0.65.1 because
     `cli.py:6168-6178` never refused POSIX classes or `-E` escapes. Those rows are `unverifiable`
     until re-taught under recorded rules: kept, never auditable; R4 prints their count per
     reason so the size of that blind spot is always visible. The reading stays stable because
     16.6 R1d keeps provenance through a rebuild (no row loses its rules later).
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
   `moved`/`grown`/`shrunk` set, the old and new line sets and every row's action (stay,
   re-point `a → b`, `stale-line`, `out-of-range`, `ambiguous`, `unverifiable`) with the pairing
   step that decided it; each `unverifiable` row with its reason; each marked row with its marks
   ([[#r1-marks]]). {#r4}
7. **R5 One classifier, two callers (r3 s-6).** The classes are computed by ONE pure function,
   `removal_audit.classify_flag_sensitive(conn, inputs) -> AuditPlan` over a read-only DuckDB
   connection, as [[task-22.1a-provenance-free-classes#r3]] states for 22.1a's classes; the
   daemon op passes its read-snapshot connection, the census passes the copy's
   ([[task-16.6-learned-row-validation#r7]]). {#r5}

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

   **4b. Readings union (m-5; r3 s-4).** The readings must DISAGREE, or the AC cannot fail: the
   `none` reading is case-insensitive and regex-or-literal, so it alone would hold the line. Two
   sets, each row with readings `-F` and `-E` of one pattern: set 1, `a.c` on a line `abc` (only
   `-E` holds it); set 2, `a+c` on a line `x a+c y` (only `-F` holds it). Both sets are `ok`.
   Readings are consulted in ascending `rules_sha` (16.6 R2), so one set has its matching reading
   first and the other last; the test asserts both orders occur. A third set with one reading
   returning `Unverifiable` and a line of `O` absent from the other reading's set classifies that
   row `unverifiable`, never `stale-line`. Mutations "`N` from the first reading only" and "`N`
   from the last reading only" each FAIL it.

   **4c. Marks are read (b-3).** A fixture row with `stale_seen = 2`, `last_mark = missing-file`
   appears in the plan manifest with its mark and "at least 2"; it is verified before an unmarked
   set of the same store; a marked row whose file is back and matching classifies `ok` (the mark
   decided nothing). Mutation "ignore the sidecar marks" FAILS the listing; mutation "class from
   `last_mark`" FAILS the last clause.
5. **Shifts with a changed hit count (r3 b-2).** Real deletion and insertion, never a line blanked
   in place:
   - **5a, delete, unhashed.** Hits `{10, 20, 30}`; line 20 is DELETED (the third hit becomes
     29): `shrunk`, rows end at `{10, 29}`: one fixed point, one re-point, exactly one
     `stale-line`, 0 `ambiguous`.
   - **5b, delete, hashed.** The same edit with hashes recorded: row 10 stays, row 30 re-points to
     29 by its hash, row 20 is `stale-line` (its hash is on no line).
   - **5c, insert plus a new hit.** Hits `{10, 20}`; one line is inserted at the top and a new hit
     is appended at the end (`N = {11, 21, 50}`): `grown`, two re-points (`10 → 11`, `20 → 21`),
     line 50 reported, 0 rows removed, 0 rows added.
   - **5d, past the end.** Hits `{10, 20}` in a file truncated to 15 lines that still holds the
     first hit: row 10 stays, row 20 is labelled `out-of-range` (a leftover past EOF).
   Mutation "`line ∉ N` → `stale-line`" FAILS 5a (two removed) and 5c (both rows removed);
   mutation "fixed point by line only, ignoring a differing hash" FAILS 5b.
6. **`empty-learned` can fail (22 #b-6, #m-1; s-3).**
   - **6a, sandbox test.** A concept with one `ok` row and df 1 is NOT a member; a concept whose
     only rows are `missing-file` IS; on a sandbox fixture store the count equals an independent
     SQL+file recount exactly.
   - **6b, operator census.** Through the ONE census procedure
     ([[task-16.6-learned-row-validation#r7]]: a `cp` of this repo's `catalog.read.duckdb`
     snapshot, read by `classify_flag_sensitive` over a read-only connection; no `Daemon`, no
     `Store()`, no `rmx`), the audit's count equals the independent recount on the same copy; the
     result goes to
     `workflow/review-output/22.1-empty-learned-census.log` and the summary. No presumed bound (the
     "747" is withdrawn).
7. **Read-only** as 22.1a AC-4.

## Test strategy {#test-strategy}

All tests run inside task 23.0's sandbox (d1a/d1b): redirected `$HOME`/global root/registry before
import, in-process `Daemon` + `Store` on a short `mkdtemp`, no `rmx` subprocess, the 23.0 guard
active, real `/usr/bin/grep` and `rg` (16.6's verifier re-runs them). No test reads a live catalog:
AC-6b is an OPERATOR census through [[task-16.6-learned-row-validation#r7]]'s procedure, logged under
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

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan16-22-spec-rereview-r3-6091648]]. Later rows win over round 2.

| finding / decision | answered in |
|---|---|
| r3 b-2 (`grown`/`shrunk` has no shift rule; AC-5's fixture shifts) | [[#r1]] "The set rule: pair, never test membership" (fixed points, hash pairing, order pairing, leftovers); AC-5a-5d with real deletion/insertion + two mutations |
| r3 s-3 ("safe because 0.65.1 refuses BRE escapes" is false) | [[#r1-verify]] the measured counts; R4 prints the blind spot per reason |
| r3 s-4 (union AC cannot fail) | AC-4b: `-F`/`-E` readings that disagree, both orders, two mutations |
| r3 m-2 (line splitting) | [[#r1]] every line numbered by 16.6's `split_lines` |
| r3 m-3 (`out-of-range` two predicates) | [[#r1]] step 4: 22.1's `out-of-range` is a label on leftover rows; 16.6's per-row verdict feeds its marks only |
| r3 s-6 (census procedure) | [[#r5]]; AC-6b; [[#test-strategy]] |
| r3 s-1 (locale) | `UNVERIFIABLE_REASONS` gains `locale-missing` (16.6 R2's tuple, unchanged here) |

rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]

