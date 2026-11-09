---
gmd: "0.1"
id: task-25.5-substring-bre-metas
title: "Task 25.5: an unescaped BRE metacharacter (. * [ ^ $) is read the way grep reads it on the drop-in legs, through 25.4's translator; the path-less index leg follows a pre-registered measurement of how many real calls change (bug-174)"
tags: [task, plan-25, bug-174, grep, bre, drop-in, substring, measurement]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-09
  updated: 2026-11-09
---

# Task 25.5: substring mode and unescaped BRE metas {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-09 in revision round 2, [[#rev-round-2]]; first reviewed
> in r3 and revised in [[#rev-round-3]]; a short r4-lite confirm is next)
> Bug: bug-174 (logged 2026-11-09 from [[bsd-plan25-spec-r1-2f4a1df#m8]])
> Depends on: [[task-25.4-grep-bre-translation]] merged (it builds `grep_dialect.bre_to_py`,
> `UntranslatableBRE`, the `grep_first` delegation and the grouped `-w` / `-x` this task reuses).

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-25.4-grep-bre-translation]]
rel: derives-from -> [[bug_registry#registry]]
rel: derives-from -> [[bsd-plan25-spec-r2-5b8ed15]]
rel: derives-from -> [[bsd-plan25-spec-r3-2f64edb]]
rel: amends -> [[task-25.4-grep-bre-translation#acceptance]]
rel: depends-on -> [[project_grep_surface_defect_family]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: related-to -> [[plan-14-grep-learning-measurement]]

## Why {#why}

`rmx grep` defaults to `--substring` (`cli.py`, the `grep` command's `--regex/--substring` option).
In that mode `rmx grep 'a.b' file` matches only the literal `a.b`; grep's BRE reads `.` as any
character, and likewise `*`, `[…]`, `^` and `$`. A drop-in call therefore misses lines grep
returns, silently: the same family as bug-167 ([[project_grep_surface_defect_family]]). 25.4 fixes
patterns that contain a backslash and deliberately leaves backslash-free patterns on the substring
path (its b6), because changing them moves every plain call. {#why-lead}

Two legs have different contracts:

- **Drop-in legs** (explicit PATH arguments, files or directories, and the stdin pipe): `rmx
  grep` IS grep there, the wrappers and the PreToolUse rewrite rely on grep's answer, and
  correctness needs no measurement. The boundary is `_index_may_answer` (`cli.py:6606`, `return
  not paths`), so `rmx grep -rn PAT dir/` is a drop-in call too (r3 #m1 c). The measured
  drop-in zero-result rate supports the switch: 131 of 350 (37%) for patterns with `* [ ^ $`
  against 155 of 1,477 (10.5%) for plain ones, on refmatrix's `query.log`
  ([[bsd-plan25-spec-r3-2f64edb#probes]]); a caller who writes a meta mostly means grep's
  reading.
- **Path-less index leg**: answered from the concept index by name, where substring matching (and
  the identifier-spelling expansion) is rmx's own semantics and drives learning. Switching it to
  BRE can lose index answers. Whether that cost is worth it is a measurement, pre-registered
  below ([[feedback_go_no_go_ranges_not_predrop]]).

## Requirements {#requirements}

1. **R1 One trigger.** `grep_dialect.has_bre_meta(pattern) -> bool`: True when a backslash-free
   pattern contains an unescaped `.`, `*`, `[`, a `^` at the start or a `$` at the end. Defined
   beside `bre_to_py`, never re-implemented in `cli.py`. {#r1}
2. **R2 Drop-in legs read BRE.** On the explicit-path legs (files or directories) and the stdin
   leg, with no `-E` / `-F` / `--regex` / `-P` / `--substring` given explicitly (detected with
   `ctx.get_parameter_source("regex")`), a pattern for which `has_bre_meta` holds is translated by
   `bre_to_py` and takes the regex path, exactly as 25.4 R2 does for backslash patterns (same
   entry point, before the stdin branch and the `-w` / `-x` wrapping). `UntranslatableBRE` → the
   real grep (25.4 R3). An explicit `--substring` keeps the literal reading.
   - **Locale (inherited, r3 #s2).** 25.4 b10 applies unchanged: under a non-UTF-8 `LC_CTYPE`
     `bre_to_py` raises `UntranslatableBRE("non-UTF-8 locale")`, so every meta pattern on a
     drop-in leg goes to the real grep there.
   - **The documented default changes with it** (r3 #m1 b). The `--regex/--substring` help text
     (`cli.py:6296-6301`: "Default is a case-SENSITIVE substring, as in grep") and the `grep`
     docstring (`cli.py:6324-6345`) are rewritten to say: on explicit paths and stdin a pattern
     is read as grep's BRE; on the path-less index leg it is a substring (or per R4's band).
   - **25.4 AC-4's `a.b` clause is superseded** (r3 #m1 a), the way 25.4 R5 supersedes
     `test_bre_alternation_fails_loud`: the assertion in `tests/test_task25_4_grep_bre.py` that
     `rmx grep 'a.b'` keeps substring semantics is rewritten to the drop-in BRE reading, with a
     docstring naming this task and bug-174; the path-less half follows R4. {#r2}
3. **R3 Measure before deciding the index leg** (pre-registered 2026-11-09, revised in r3 BEFORE
   any replay was run; counts only, nothing raw committed,
   [[feedback_no_raw_prompts_in_public_repo]]). Stores: refmatrix and cliquedb (and any other
   store with logs the user names).
   - **Source (r3 #s3).** `query.log` alone cannot replay a call: no row records the grep flags,
     and `cwd` is on 136 refmatrix / 513 cliquedb rows only. The population is therefore built
     from **`cli.log`** (argv and cwd, 32,588 refmatrix grep calls) **joined to `query.log`'s
     `answered_by` by pid and ts**. A path-less call is one whose argv has no path argument AND
     whose joined row says it was not a stdin call (`answered_by` ∈ {`index`, `floor`, `none`});
     `cli.log`'s own "no path argument" set also covers stdin pipes and is not used alone. Calls
     whose `query.log` row has no `answered_by` (1,592 refmatrix, 351 cliquedb rows predate the
     field) or that fail the join are EXCLUDED and COUNTED.
   - **Replay.** Each path-less call is replayed with its logged flags (`-i`, `-w`, `-x`, …) from
     its logged cwd (the fallback root is `Path.cwd()`) against a frozen scratch snapshot of the
     store's indexed tree, under both readings (substring-on-index as today, BRE via
     `bre_to_py`); rows with no flags in argv are recorded as such.
   - **Numbers.** Let M = path-less calls (joined, replayable) whose pattern satisfies
     `has_bre_meta`, summed across stores.
     - (a) the share of ALL joined grep calls whose pattern satisfies `has_bre_meta` (context
       only; it decides nothing);
     - (b) numerator: calls in M whose result set differs between the two readings;
       **denominator: M**;
     - (c) numerator: calls in M that today are answered by the index (`answered_by` = `index`)
       and would fall to the tree floor under BRE; **denominator: M**.
     Every number is written with its numerator and denominator, per store and summed.
   - **Minimum.** M ≥ 30. At r3 the path-less `query.log` rows were 35 in refmatrix (3 with a
     meta, all `floor`, all from 2026-10) and 0 in cliquedb ([[bsd-plan25-spec-r3-2f64edb#probes]]),
     so the first run is EXPECTED to fall below it.
   Written to `workflow/measurements/grep-substring-bre-metas.md`, counts and percentages only. {#r3}
4. **R4 The path-less index leg follows the pre-registered bands** (written 2026-11-09, before the
   data exists; denominators and minimum added in r3, still before any replay):
   - **M < 30** → "insufficient data" → **NO-GO by default** (the NO-GO behaviour below). The
     measurement file says so with M's value, and the re-measure below is scheduled.
   - **(b) ≥ 5%** → GO: the path-less leg reads BRE too (R2's rule on every leg).
   - **1% ≤ (b) < 5%** → GO only if (c) ≤ 20%; otherwise NO-GO.
   - **(b) < 1%** → NO-GO.
   - On NO-GO, the path-less leg keeps substring and, when `has_bre_meta` holds, prints one stderr
     note `# rmx grep: '<pattern>' read as a literal substring on the index; pass -G for grep's
     BRE reading` and records `bre_meta_literal: true` on the `query.log` row (with the call's
     flags and cwd, so a later replay needs no `cli.log` join), so the deviation is visible and
     counted, never silent.
   - **Re-measure.** R3 re-runs over the `bre_meta_literal: true` rows when they reach 30, or at
     the first plan-of-plans review after 2026-12-31, whichever comes first; the bands above
     decide again, unchanged. The re-run is a bug-174 row update, not a new task.
   - **`-G` is a parsed flag** (r3 #m1 d). Today `-G` is not index-expressible:
     `_grep_bare_flags` puts it in `delegate` (`cli.py:5970`), so a path-less `-G` call already
     goes to the real tool, which never learns. R4 makes `-G` a parsed flag that sets "BRE
     reading" and keeps the call on the index / fallback leg (which learns); on the drop-in legs
     `-G` is the default reading and changes nothing. {#r4}
5. **R5 bug-174's row** closes as `fixed` (GO) or stays open with the measured numbers and the
   NO-GO band named (NO-GO), never as an unmeasured won't-fix. {#r5}

## Acceptance criteria {#acceptance}

Production path: the `rmx grep` CLI as the wrappers and the PreToolUse rewrite invoke it, in
23.0's sandbox; oracles `/usr/bin/grep` (reference) and GNU grep, `LC_ALL` pinned as in 25.4.
{#acceptance-lead}

1. **AC-1 Drop-in differential.** For each of `a.b`, `a*b`, `^ab`, `ab$`, `[ab]c`, `x.*y`, `.`,
   `[[:digit:]]`, `a.b.c`, `*lead` (literal `*`), on the file leg and the stdin leg, each with
   `-n`, `-c`, `-i`, `-w`, `-x`, `-v`: `rmx grep` stdout and exit equal `/usr/bin/grep`'s. RED at
   HEAD for every row except `*lead` (literal either way, recorded). The fixture holds a non-dot
   line, an `axb` line, a leading `ab` line and the `café x` line. Every row runs under
   `LC_ALL=en_US.UTF-8` and `LC_ALL=C`; under C the meta rows are delegated (25.4 b10, stderr note
   `non-UTF-8 locale`), and `-x .` on the `café x` line is among them. The file leg is run with an
   explicit FILE and with an explicit DIRECTORY (`-rn PAT dir/`).
2. **AC-2 Explicit substring.** `rmx grep --substring 'a.b' file` matches only the literal line
   (unchanged), and `-F 'a.b'` likewise.
3. **AC-3 Measurement exists before the index-leg decision.** The R3 file holds (a), (b), (c) per
   store with the row counts behind each, and the band R4 selects; the implementation summary
   quotes it. A GREEN for R4 without this file is not accepted.
4. **AC-4 Index leg per the band.** GO: a path-less `rmx grep 'a.b'` in a fixture project returns
   the same file:line set as `grep -rn 'a.b'` over the indexed files. NO-GO: it returns today's
   substring answer, prints the R4 note on stderr, and its `query.log` row has
   `bre_meta_literal: true` plus the call's flags and cwd; `rmx grep -G 'a.b'` (path-less) gives
   the grep answer FROM the index / fallback leg (asserted: no delegation note on stderr, and the
   learned concept `query/a.b` exists afterwards). RED at HEAD: `-G` is delegated (`cli.py:5970`),
   so the answer is right but the delegation note prints and nothing is learned.
5. **AC-4b Documentation.** `rmx grep --help` no longer says the default is a substring "as in
   grep" without naming the leg; a test asserts the help names both readings (r3 #m1 b).
6. **AC-5 Mutations that must FAIL a test:** `has_bre_meta` ignoring `[` (AC-1 `[ab]c`); the
   trigger re-implemented in `cli.py` (a structural check like 25.2 AC-6); R2 applied after the
   stdin branch (AC-1 stdin rows); on NO-GO, the note or the row field missing (AC-4); R2 limited
   to file arguments (AC-1 directory rows); `-G` left in `delegate` (AC-4: delegation note
   present); translate under C (AC-1 C rows, inherited from 25.4).

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/grep_dialect.py` | `has_bre_meta` |
| `src/refmatrix/cli.py` (`grep`, help text `:6296-6301`, docstring `:6324-6345`; `_grep_bare_flags` `:5857`, `-G` at `:5970`) | R2 trigger at 25.4's entry point; R4 per band; `-G` parsed; help and docstring rewritten |
| `tests/test_task25_4_grep_bre.py` | 25.4 AC-4's `a.b` assertion superseded (R2) |
| `workflow/measurements/grep-substring-bre-metas.md` (new) | R3's counts, with numerators, denominators, M, excluded counts |
| `tests/test_task25_5_substring_bre.py` (new) | AC-1..AC-5 |
| `workflow/bug_registry.md` | bug-174 per R5 |

## Test strategy {#test-strategy}

- RED first on AC-1 at HEAD (after 25.4 merges).
- The oracle is the real grep; no mock of `grep_dialect` or the CLI.
- R3 reads `query.log` in-process and writes counts only; the replay snapshot is a scratch copy,
  never the live store.

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| f1 | Drop-in legs switch without measurement | yes: grep's answer is the contract there; the differential test is the gate |
| f2 | Index-leg bands | as pre-registered in R4 (5% / 1% / 20%, denominator M, minimum M ≥ 30); a result in a band is acted on, not re-argued |
| f4 | Below the minimum (r3 #s3, decided as the user would) | NO-GO by default with R4's counted note; the `bre_meta_literal` rows accumulate the population; re-measure at 30 rows or after 2026-12-31 |
| f3 | Flag to force BRE on the index leg under NO-GO | `-G`, grep's own name for basic regex |

## Revision round 2 (2026-11-09) {#rev-round-2}

Created by revision round 2 of plan-25.

| finding | change | anchor |
|---|---|---|
| bsd r2 U6 / orchestrator Q6: bug-174 has no task | this task: drop-in legs read BRE through 25.4's translator; the index leg follows a pre-registered measurement of real calls (counts only) | [[#r2]], [[#r3]], [[#r4]] |

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan25-spec-r3-2f64edb]] (DIRTY 0B/4S/9M at `2f64edb`; this task's first review,
[[bsd-plan25-spec-r3-2f64edb#task-25-5]]). S3 was decided in the report as the user would and is
adopted here. The bands were revised BEFORE any replay ran, so they are still pre-registered.

rel: derives-from -> [[bsd-plan25-spec-r3-2f64edb]]

| finding | change | anchor |
|---|---|---|
| S3 bands cannot decide: denominators unstated, 35 / 0 path-less rows, no flags to replay | source = `cli.log` argv + cwd joined to `query.log`'s `answered_by` by pid and ts, unjoined / pre-field rows excluded and counted; (b) and (c) both over M (path-less meta calls); minimum M ≥ 30; below it NO-GO by default with the counted note (f4); NO-GO rows log flags + cwd; re-measure from `bre_meta_literal` rows at 30 or after 2026-12-31; replay with logged flags | [[#r3]], [[#r4]], f2, f4 |
| S2 (25.5 half) C locale | inherits 25.4 b10: meta patterns delegate under a non-UTF-8 locale; AC-1 runs both locales incl. `-x .` on `café x`; mutation | [[#r2]], AC-1, AC-5 |
| M1 (a) 25.4 AC-4 superseded silently | R2 supersedes it explicitly; `tests/test_task25_4_grep_bre.py` in the files | [[#r2]], [[#files]] |
| M1 (b) documented default goes stale | help text (`cli.py:6296-6301`) and `grep` docstring (`cli.py:6324-6345`) rewritten; AC-4b | [[#r2]], AC-4b |
| M1 (c) "file arguments" narrower than the leg | "explicit PATH arguments, files or directories" (`_index_may_answer`, `cli.py:6606`); AC-1 directory rows; mutation | [[#why]], [[#r2]], AC-1, AC-5 |
| M1 (d) `-G` delegated today | `-G` becomes a parsed flag that keeps the call on the learning leg; AC-4 asserts no delegation note and a learned concept, RED at HEAD | [[#r4]], AC-4, AC-5 |

