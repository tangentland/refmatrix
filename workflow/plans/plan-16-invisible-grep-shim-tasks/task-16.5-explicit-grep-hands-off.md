---
gmd: "0.1"
id: task-16.5-explicit-grep-hands-off
title: "Task 16.5: explicit `rmx grep` hands off to the real grep (rmx options translated); rmx answers only plain path-less index reads"
tags: [task, grep, drop-in, simplification]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  revised: 2026-10-07
---

# Task 16.5: the explicit command stops re-rendering grep {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision 2, after spec review r3 `bsd-plan16-spec-review-r3-c8278b1`, which found
> 2 BULLSHIT, 10 SKETCHY and 6 MEH)
> Depends on: [[task-16.1-argv-faithful-learner]], [[task-16.2-invisible-shim]] (16.2 provides its
> differential fixture and its spawn rules)

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: depends-on -> [[task-16.2-invisible-shim]]
rel: derives-from -> [[bsd-r1-remedy-r4-4d54f6a]]
rel: amends -> [[bsd-plan16-spec-review-r3-c8278b1]]

## Why {#why}

When paths are named or stdin is a pipe, explicit `rmx grep PAT file…` re-implements grep's output
in Python on top of `rg`. That covers argument ordering, per-file `-c` rows with directory
expansion, the filename prefix, `-o`, context lines, exit codes, a hand-written stdin filter, and a
delegate for flags rmx could not express.

Most of the drop-in defect family lives there:
- bug-058, 059, 060, 062, 063, 064, 066 and 079;
- round 4's #b-2, #b-3, #b-4 and #m-4;
- r5 #s-2 (the delegate mis-teaching `-c`/`-h` output).

bug-061 and bug-065 are NOT drop-in bugs. bug-076, 077 and 078 live in the index read, which this
task KEEPS. Four audit rounds found a new sibling branch in this code each time. The user decided on
2026-10-07 to delete it rather than patch it again. {#why-lead}

## Decision d-4 (user, 2026-10-07): rmx's own options are TRANSLATED (option B) {#d-4}

`rmx grep` keeps its own options, and `-f/--flags` stays rmx's flag BUNDLE. Before the hand-off,
rmx translates them. grep's own pattern-file option is reachable only as `--file=FILE` (spec review
r3 #b-r3-1: `-f` is two different flags).

| rmx option | on the hand-off route |
|---|---|
| `-f BUNDLE` / `--flags=BUNDLE` | expanded into grep flags (`-f '-c -i'` → `-c -i`) by the existing `_parse_grep_flags` letters; an unknown letter refuses, as today |
| `--regex` / `--substring` | `-E` / `-F` |
| `--learn` / `--no-learn` | honoured (the learner spawns or does not) and stripped |
| `--limit`, `-k/--kind`, `--linkage`, `--fallback/--no-fallback`, `--via-replica` | index-only: **refused**, exit 2, with one stderr line naming the option and why. They are never silently dropped and never passed to grep. |
| `--file=FILE` | passed to grep as is (grep's pattern file) |
| anything else | passed to grep verbatim (bare grep flags, as since 0.25.7) |

The translation is ONE function, `translate_rmx_options(argv) -> (grep_argv, learn, refusals)`. It
is the only code that changes argv before the exec.

## Requirements {#requirements}

**R1. Named paths: exec the real grep on the translated argv.**
- `/usr/bin/grep` is resolved once, as an absolute path.
- stdout, stderr and the exit code are the tool's. rmx adds nothing: no banner, no provenance.
- Before the exec, rmx spawns 16.1's learner under 16.2's learn-switch, slot and throttle rules.
- **Behaviour change, stated:** `rmx grep PAT dir` without `-r` now does what grep does
  (`Is a directory`, exit 2).

**R2. Piped stdin: exec the real grep on the translated argv; no teach.**
- `_grep_stdin` and `_grep_stdin_addendum` are DELETED.
- The documented `git diff | rmx grep -f '-c' "^+"` becomes `grep -c "^+"` and prints a count. That
  is an acceptance case.

**R3. Path-less: the index answers ONLY a plain pattern (#b-r3-2, #s-r3-2).** `rmx grep PAT` with
no paths and no pipe goes to the index read only when BOTH hold:
1. The pattern has no BRE metacharacter (`\ ^ $ . * [ ]`), or `--substring`/`-F` was given. A BRE
   pattern means a dialect the index cannot honour (bug-081).
2. Every flag is index-expressible: `-i`, `-w`, `-n`, `-l`, `-c`, `-F`/`-E`/`--regex`/`--substring`
   (`-E` sends the pattern to the index's regex), `--limit`, `-k`, `--linkage`, `--no-fallback`,
   `--learn`/`--no-learn`.

Otherwise, and on an index miss, the FLOOR runs:
`grep -r <16.1 R1b pruning flags FIRST> <caller's translated flags> PAT <project_root>`.
- That is the real grep with every caller flag (`-A/-B/-C`, `--include`, `-m`, `-x`, `-v`, `-L`,
  `-o`, `-NUM`, …), so bug-077's case rule and BRE are the tool's own.
- The floor teaches through 16.1's path.
- The `\|` refusal at `cli.py` (pre-0.65.1) is DELETED, because grep handles `\|` itself.

The index answer itself is unchanged: bug-073/074/076/077/078/083/084 rules, the resolved printed
path from r5 #b-1, and the cap note.

**R4. Delete the re-implementation.**
- Deleted: `argv_order_index`, `argv_rank`, `order_triples_by_argv`, `argv_count_rows`,
  `_walk_files`, the named-path branches of `_resolve_output_shape` and `_grep_rg_fallback`,
  `_grep_delegate`, `_grep_stdin`, `_grep_stdin_addendum`, the `\|` refusal, and the rmxrg `-E`
  injection.
- Every removed test is listed in the summary with its reason.
- A test that pinned a defect class becomes an R5 differential case.

**R5. Differential, 100%, no allowlist.**
- For each invocation in 16.2's `tests/fixtures/grep_differential.txt` that names paths or pipes
  stdin, `rmx grep RMX_ARGS` vs `/usr/bin/grep translate(RMX_ARGS)` must match byte-for-byte on
  stdout, stderr and the exit code.
- A second column holds the expected `translate` output for every row that uses an rmx option, so
  the translation itself is asserted and not assumed.
- The corpus gains: `-rc zzz sub`, `-c` over a dir with a binary file, an unreadable subdir,
  `-rn alpha ./sub sub`, `-rl` with two spellings, `-l alpha f0.txt nosuch.txt`,
  `-L alpha f0.txt nosuch.txt`, `-c zzz nosuch.txt`, `-A 2`, `-B 1`, `-C 1`, a dotfile in a walked
  dir, bug-081's `\b` and `^| 15 |`, and `-f '-c' "^+"` over a pipe.

**R6. Telemetry stays (#m-r3-5).** Before the exec, rmx writes the `query.log` row with
`answered_by = dropin` (paths) or `stdin` (pipe), so those values stay live and plan-14's harness
keeps working.

**R7. Documented callers (#s-r3-5).** Updated with this task:
- `docs/agent-doc-primer.md:49-52` (`rmx grep "FIXME" src/ tests/` needs `-r`);
- the `rmx grep` docstring examples in `cli.py`;
- `hooks.py`'s "bare grep/rg flags OK" comment;
- README grep examples.

A test greps `docs/`, `README.md` and the templates for `rmx grep` examples that name a directory
without `-r`, and fails on any it finds.

**R8. bug registry, precisely (#s-r3-4).**
- `superseded by task-16.5 (code deleted)`: bug-058, 059, 060, 062, 063, 064, 066, 079; r4 #b-2,
  #b-3, #b-4, #m-4; r5 #s-2.
- `fixed by task-16.5 R3`: bug-081.
- bug-076, 077, 078, 083 and 084 stay as they are, because their code is kept.

## Acceptance criteria {#acceptance}

1. **R5's differential passes at 100%, with power.** Before the change, every case is run against
   the CURRENT `rmx grep`, and the differing cases are recorded. At least round 4's cases, bug-081's
   two and the `-f '-c'` pipe case must differ.
2. **No added bytes.** Named-path and pipe runs write nothing beyond the tool's bytes, with learning
   on and off.
3. **Translation.**
   - Each table row has a unit case.
   - `--limit 5 PAT file` exits 2 with the named refusal, and grep is never run.
   - `-f '-c -i'` expands.
   - `--file=pats.txt` reaches grep.
4. **The learner, really (#m-r3-4).** A named-path run against a FIFO operand returns at once with
   grep's own exit. The REAL learner's `grep-learn.log` record (`outcome=timeout`) appears within the
   timeout plus 2 s. A pipe run writes no record.
5. **The path-less routing (R3).**
   - A plain pattern answers from the index.
   - `rmx grep 'alpha$'`, `rmx grep -A2 alpha` and `rmx grep --include='*.py' alpha` go to the floor
     and equal `grep -r <pruning> … alpha <root>`.
   - `rmx grep -i ERROR` still answers case-insensitively from the index.
   - A mutation that routes BRE patterns to the index fails the `alpha$` case.
6. **The deletions are real.** `rg -w` over `src/ tests/ bin/` for each deleted symbol returns
   nothing. That catches in-function imports, which `--collect-only` misses. The grep section's line
   count before and after goes in the summary.
7. **Telemetry.** A named-path and a pipe run each leave a `query.log` row with `answered_by` set to
   `dropin` and `stdin` respectively.
8. **Docs.** R7's scan finds no directory example without `-r`.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/cli.py` | `translate_rmx_options`; routing (named/pipe → grep; plain path-less → index; else floor); deletions per R4; telemetry before the exec |
| `src/refmatrix/grep_learn.py` | the Python spawn function, shared with R1 (16.2 R2b holds the shell twin and the parity test) |
| `tests/test_grep_*.py` | deleted-code tests removed or converted (listed); R5 cases; translation units |
| `docs/agent-doc-primer.md`, `README.md`, `src/refmatrix/hooks.py` | R7 |
| `workflow/bug_registry.md` | R8 |

## Test strategy {#test-strategy}

Real `/usr/bin/grep`, `shell=False`, list argv. Pre-registered mutations:

| mutation | must fail |
|---|---|
| re-add a stderr banner | AC-2 |
| render named-path output in Python | AC-1 |
| pass `--limit` to grep instead of refusing | AC-3 |
| treat `-f` as grep's pattern file | AC-3 and the `-f '-c'` pipe case |
| floor with `rg -F` | AC-5 `alpha$` |
| floor drops the caller's `-i` | AC-5 (case cases in the differential) |
| skip the pre-exec telemetry row | AC-7 |

{#tests}
