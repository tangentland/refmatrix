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
> Status: Pending (spec drafted 2026-11-09 in revision round 2, [[#rev-round-2]])
> Bug: bug-174 (logged 2026-11-09 from [[bsd-plan25-spec-r1-2f4a1df#m8]])
> Depends on: [[task-25.4-grep-bre-translation]] merged (it builds `grep_dialect.bre_to_py`,
> `UntranslatableBRE`, the `grep_first` delegation and the grouped `-w` / `-x` this task reuses).

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-25.4-grep-bre-translation]]
rel: derives-from -> [[bug_registry#registry]]
rel: derives-from -> [[bsd-plan25-spec-r2-5b8ed15]]
rel: depends-on -> [[project_grep_surface_defect_family]]
rel: related-to -> [[plan-14-grep-learning-measurement]]

## Why {#why}

`rmx grep` defaults to `--substring` (`cli.py`, the `grep` command's `--regex/--substring` option).
In that mode `rmx grep 'a.b' file` matches only the literal `a.b`; grep's BRE reads `.` as any
character, and likewise `*`, `[…]`, `^` and `$`. A drop-in call therefore misses lines grep
returns, silently: the same family as bug-167 ([[project_grep_surface_defect_family]]). 25.4 fixes
patterns that contain a backslash and deliberately leaves backslash-free patterns on the substring
path (its b6), because changing them moves every plain call. {#why-lead}

Two legs have different contracts:

- **Drop-in legs** (explicit file arguments, stdin pipe): `rmx grep` IS grep there, the wrappers
  and the PreToolUse rewrite rely on grep's answer, and correctness needs no measurement.
- **Path-less index leg**: answered from the concept index by name, where substring matching (and
  the identifier-spelling expansion) is rmx's own semantics and drives learning. Switching it to
  BRE can lose index answers. Whether that cost is worth it is a measurement, pre-registered
  below ([[feedback_go_no_go_ranges_not_predrop]]).

## Requirements {#requirements}

1. **R1 One trigger.** `grep_dialect.has_bre_meta(pattern) -> bool`: True when a backslash-free
   pattern contains an unescaped `.`, `*`, `[`, a `^` at the start or a `$` at the end. Defined
   beside `bre_to_py`, never re-implemented in `cli.py`. {#r1}
2. **R2 Drop-in legs read BRE.** On the explicit-file and stdin legs, with no `-E` / `-F` /
   `--regex` / `-P` / `--substring` given explicitly, a pattern for which `has_bre_meta` holds is
   translated by `bre_to_py` and takes the regex path, exactly as 25.4 R2 does for backslash
   patterns (same entry point, before the stdin branch and the `-w` / `-x` wrapping).
   `UntranslatableBRE` → the real grep (25.4 R3). An explicit `--substring` keeps the literal
   reading. {#r2}
3. **R3 Measure before deciding the index leg** (pre-registered; run before GREEN for R4, counts
   only, nothing raw committed, [[feedback_no_raw_prompts_in_public_repo]]). Over every `kind=grep`
   row in the local `query.log` files of refmatrix and cliquedb (and any other store with a
   `query.log` the user names), compute in-process:
   - (a) the share of grep calls whose pattern satisfies `has_bre_meta`;
   - (b) among the path-less ones, the share whose answer CHANGES: the pattern is replayed against
     a frozen snapshot of the store's indexed tree under both readings (substring-on-index as
     today, BRE via `bre_to_py`), and the result sets differ;
   - (c) among the path-less ones, the share that today is answered by the index
     (`answered_by`, plan-14's field) and would fall to the tree floor under BRE.
   Written to `workflow/measurements/grep-substring-bre-metas.md` as counts and percentages only. {#r3}
4. **R4 The path-less index leg follows the pre-registered bands** (written 2026-11-09, before the
   data exists):
   - **(b) ≥ 5%** → GO: the path-less leg reads BRE too (R2's rule on every leg).
   - **1% ≤ (b) < 5%** → GO only if (c) ≤ 20%; otherwise NO-GO.
   - **(b) < 1%** → NO-GO.
   - On NO-GO, the path-less leg keeps substring and, when `has_bre_meta` holds, prints one stderr
     note `# rmx grep: '<pattern>' read as a literal substring on the index; pass -G for grep's
     BRE reading` and records `bre_meta_literal: true` on the `query.log` row, so the deviation
     is visible and counted, never silent. `-G` (grep's own "basic regex" flag) forces R2's reading
     on this leg. {#r4}
5. **R5 bug-174's row** closes as `fixed` (GO) or stays open with the measured numbers and the
   NO-GO band named (NO-GO), never as an unmeasured won't-fix. {#r5}

## Acceptance criteria {#acceptance}

Production path: the `rmx grep` CLI as the wrappers and the PreToolUse rewrite invoke it, in
23.0's sandbox; oracles `/usr/bin/grep` (reference) and GNU grep, `LC_ALL` pinned as in 25.4.
{#acceptance-lead}

1. **AC-1 Drop-in differential.** For each of `a.b`, `a*b`, `^ab`, `ab$`, `[ab]c`, `x.*y`, `.`,
   `[[:digit:]]`, `a.b.c`, `*lead` (literal `*`), on the file leg and the stdin leg, each with
   `-n`, `-c`, `-i`, `-w`, `-x`, `-v`: `rmx grep` stdout and exit equal `/usr/bin/grep`'s. RED at
   HEAD for every row except `*lead` (literal either way, recorded).
2. **AC-2 Explicit substring.** `rmx grep --substring 'a.b' file` matches only the literal line
   (unchanged), and `-F 'a.b'` likewise.
3. **AC-3 Measurement exists before the index-leg decision.** The R3 file holds (a), (b), (c) per
   store with the row counts behind each, and the band R4 selects; the implementation summary
   quotes it. A GREEN for R4 without this file is not accepted.
4. **AC-4 Index leg per the band.** GO: a path-less `rmx grep 'a.b'` in a fixture project returns
   the same file:line set as `grep -rn 'a.b'` over the indexed files. NO-GO: it returns today's
   substring answer, prints the R4 note on stderr, and its `query.log` row has
   `bre_meta_literal: true`; `-G` gives the grep answer.
5. **AC-5 Mutations that must FAIL a test:** `has_bre_meta` ignoring `[` (AC-1 `[ab]c`); the
   trigger re-implemented in `cli.py` (a structural check like 25.2 AC-6); R2 applied after the
   stdin branch (AC-1 stdin rows); on NO-GO, the note or the row field missing (AC-4).

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/grep_dialect.py` | `has_bre_meta` |
| `src/refmatrix/cli.py` (`grep`) | R2 trigger at 25.4's entry point; R4 per band; `-G` |
| `workflow/measurements/grep-substring-bre-metas.md` (new) | R3's counts |
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
| f2 | Index-leg bands | as pre-registered in R4 (5% / 1% / 20%); a result in a band is acted on, not re-argued |
| f3 | Flag to force BRE on the index leg under NO-GO | `-G`, grep's own name for basic regex |

## Revision round 2 (2026-11-09) {#rev-round-2}

Created by revision round 2 of plan-25.

| finding | change | anchor |
|---|---|---|
| bsd r2 U6 / orchestrator Q6: bug-174 has no task | this task: drop-in legs read BRE through 25.4's translator; the index leg follows a pre-registered measurement of real calls (counts only) | [[#r2]], [[#r3]], [[#r4]] |
