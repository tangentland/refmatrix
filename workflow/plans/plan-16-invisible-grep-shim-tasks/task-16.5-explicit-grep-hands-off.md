---
gmd: "0.1"
id: task-16.5-explicit-grep-hands-off
title: "Task 16.5: explicit `rmx grep` hands off to the real grep (rmx options parsed from the raw argv, one table per route); rmx answers only plain path-less index reads"
tags: [task, grep, drop-in, simplification]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  revised: 2026-10-14
---

# Task 16.5: the explicit command stops re-rendering grep {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision 5, after spec review r4 `bsd-plan16-spec-review-r4-33809ab`)
> Depends on: [[task-16.1-argv-faithful-learner]], [[task-16.2-invisible-shim]] (16.2 provides its
> differential fixture and its spawn rules)

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: depends-on -> [[task-16.2-invisible-shim]]
rel: derives-from -> [[bsd-r1-remedy-r4-4d54f6a]]
rel: amends -> [[bsd-plan16-spec-review-r3-c8278b1]]
rel: amends -> [[bsd-plan16-spec-review-r4-33809ab]]

## Revision 5 changelog {#revision-5}

Answers spec review r4 ([[bsd-plan16-spec-review-r4-33809ab]]). The `-f/--flags` bundle was
removed in code by `d559567` (plan d-4, user 2026-10-07), so the r4 rows that rest on it are
re-stated against HEAD, not patched.

| finding | answered in |
|---|---|
| b-r4-1 rmx options on the path-less floor | [[#d-4]] (one table, three routes), R3 [[#r3]], AC-5 [[#acceptance]] rows 5c-5g, mutations [[#test-strategy]] |
| b-r4-2 click's leftover argv | R0 [[#r0]] (raw argv, one parser, `--` kept, repeats refused), R0b [[#r0b]] (routing split on 16.1's grep table, all `-e`s), R5 rows [[#r5]], AC-3 |
| s-r4-1 bundle `I`/`r`/`R`, help text, `--file=` message | [[#d-4]] note "the bundle is gone"; R4 deletes the letter parser; AC-3 `-I`/`-r`/`-R` rows; R7 help scan |
| s-r4-2 AC-5 oracle and empty-store mutation | AC-5 literal file sets + seeded rows; mutation "always add the pruning `--include`s" |
| s-r4-3 AC-4 FIFO hang/race | AC-4 rewritten: a slow regular file + `RMX_GREP_LEARN_TIMEOUT_S=1` |
| s-r4-6 tests not sandboxed from the live store | [[#sandbox]] |
| m-r4-3 `cli.log` exit record lost on exec | R6 [[#r6]] (`handed-off` record before the exec) |
| m-r4-5 `$PWD` vs `getcwd` | R1 (Python spawn uses 16.2 R2b's cwd rule) |
| m-r4-6 habitual no-op flags; BRE concepts write-only | R3 [[#r3]] (`-r -R -H -s` index no-ops; the BRE-concept reader named) |

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

## Decision d-4 (user, 2026-10-07; re-stated for HEAD in revision 5) {#d-4}

**The bundle is gone (`d559567`, user: "change the grep to not use -flags").** `--flags` and
`--flags=` are refused with exit 2 and a pointer to bare flags, on every route. `-f FILE`,
`-fFILE`, `--file FILE` and `--file=FILE` are grep's pattern file, verbatim. There is therefore no
letter expansion and no rmx meaning for `-I`, `-r` or `-R`: each reaches grep with GREP's meaning
(`-I` = skip binary files) on every route that runs grep (s-r4-1). Verified at HEAD:
`_parse_grep_flags` is called from `src/` only as `_parse_grep_flags(None)` (defaults).

rmx's remaining options keep the d-4 principle: **never silently dropped, never passed to grep.**
Every route has a row. "Refused" is exit 2 with ONE stderr line `rmx grep: <option> <why>` and grep
never runs.

| rmx option | named paths / pipe (R1, R2) | path-less, index answers (R3) | path-less, grep floor (R3) |
|---|---|---|---|
| `--flags`, `--flags=` | refused (`d559567`) | refused | refused |
| `--regex` / `--substring` | `-E` / `-F`, inserted before the first grep token | regex / substring read | `-E` / `-F` on the floor argv |
| `--learn` / `--no-learn` | the learner spawns or does not; stripped | as today (the floor's teach) | the learner spawns or does not; stripped |
| `--limit N` | refused | caps index rows (default 100; 0 = none), as today | caps the floor's stdout at N LINES (default 100; 0 = none), as today; a truncation prints `# rmx: floor output truncated at N lines (--limit)` on stderr and exits 0 |
| `-k/--kind`, `--linkage` | refused | filters the index read | **the floor never runs.** An index miss prints `rmx grep: no indexed matches (-k/--linkage: no grep floor)` and exits 1. A call that R3 routes straight to the floor is refused (the floor cannot honour the filter) |
| `--no-fallback` | refused | no floor: an index miss prints `rmx grep: no indexed matches` and exits 1 (today's text) | a call that R3 routes straight to the floor is refused (the caller forbade the floor) |
| `--fallback` | refused | default; no-op | default; no-op |
| `--via-replica` | refused | selects the read slot, as today | no effect on grep; one stderr line `# rmx: --via-replica: answered by grep, no index read` |

The `-k/--linkage` floor rows are this spec's reading of d-4 ("never silently dropped"), listed in
the plan's `#decisions-needed` for the user to confirm or overrule; they are not a new user
decision.

## Requirements {#requirements}

**R0. ONE parser, on the RAW argv (b-r4-2).** {#r0}
- Probed on click 8.3.3 (revision 5, a replica of `grep()`'s context settings): click DROPS `--`
  (`-- -x f.txt` reaches the command as `-x f.txt`; `-i foo -- --limit 3` as `-i foo --limit 3`),
  keeps only the LAST of a repeated option (`--limit 5 --limit 7` → 7, silently), and splits a
  short cluster (`-ik code foo` → `kind=code`, argv `-i foo`).
- So the `grep` command is a `click.Command` subclass whose `parse_args(ctx, args)` stores
  `list(args)` (the raw tail after the `grep` token, `--` included; probed: the override receives
  it) in `ctx.meta` BEFORE click parses. rmx's options are NOT declared to click (only `--help`
  and the `argv` catch-all), so there is exactly ONE parser: `parse_rmx_grep_argv(raw) ->
  (rmx_opts, grep_argv, refusals)`. The options are documented in the docstring.
- Rules, left to right:
  - rmx options are recognised in the spellings click accepted: `--limit N`, `--limit=N`,
    `--kind X`, `--kind=X`, `-k X`, `-kX`, `--linkage X`, `--linkage=X`, and the flags
    `--regex --substring --fallback --no-fallback --learn --no-learn --via-replica`.
  - **`--` ends rmx's options AND stays in `grep_argv` at its position.** Everything after it is
    grep's, verbatim.
  - The value of a grep value-flag is never read as an rmx option (`-e --limit` is the pattern
    `--limit`). Which grep flags take a value is read from 16.1 R1's grep table (its `value` column),
    the ONE table; `_GREP_VALUE_FLAGS` is deleted (R4).
  - **A repeated rmx option is refused** (exit 2, naming it). Click's last-wins is not kept.
  - `-k` inside a cluster with other letters (`-ik`) is refused (exit 2: "pass -k separately");
    grep has no `-k`, so the cluster has no other reading.
  - Every other token goes to `grep_argv` unchanged and in order.

**R0b. The routing split works on `grep_argv` with grep's own value flags (b-r4-2).** {#r0b}
- It replaces `_split_grep_argv`'s use of `_GREP_VALUE_FLAGS`. Value flags come from 16.1 R1's
  table. Probed on BSD 2.6.0 (revision 5), the space-form value flags are: `-e --regexp -f --file
  -m --max-count -A --after-context -B --before-context -C -d --directories -D --devices --label
  --binary-files --include --exclude --exclude-dir --include-dir`. `--context` and `--color` take a
  value ONLY as `=` (probed: `--context 1 alpha a.py` reads `1` as the pattern), so they are not
  space-value flags; the old set wrongly had `--context`, and had rg's `-g -t -T --glob --iglob
  --type-not`.
- It honours `--` (the first non-flag after it is the pattern unless `-e`/`-f` supplied one).
- It collects EVERY `-e`/`--regexp` value. `-f`/`--file` marks the patterns as file-supplied.
- Named paths = any operand left after the pattern (or any operand at all when `-e`/`-f` gave the
  pattern).
- **A path-less call with more than one `-e`, or any `-f`/`--file`, is not index-expressible** and
  goes to the floor (R3), so the index never answers one of several patterns.

**R1. Named paths: exec the real grep on `grep_argv` (after the d-4 named-path rows).**
- `/usr/bin/grep` is resolved once, as an absolute path.
- stdout, stderr and the exit code are the tool's. rmx adds nothing: no banner, no provenance.
- Before the exec, rmx spawns 16.1's learner under 16.2's learn-switch, slot and throttle rules,
  through `grep_learn.spawn()`. Its `--cwd` follows 16.2 R2b's cwd rule (`$PWD` when it resolves
  to `os.getcwd()`, else `os.getcwd()`; m-r4-5), so the throttle key matches the shim's.
- **Behaviour change, stated:** `rmx grep PAT dir` without `-r` now does what grep does
  (`Is a directory`, exit 2).

**R2. Piped stdin: exec the real grep on `grep_argv`; no teach.**
- `_grep_stdin` and `_grep_stdin_addendum` are DELETED.
- The documented example is now `git diff | rmx grep -c "^+"` (bare flags since `d559567`); it
  prints grep's count. That is an acceptance case. (`d559567` found the old stdin filter counted 0
  here, bug-081 seen 3.)

**R3. Path-less: the index answers ONLY a plain pattern; otherwise the floor (#b-r3-2, #s-r3-2,
b-r4-1).** {#r3}
`rmx grep PAT` with no paths and no pipe goes to the index read only when ALL hold:
1. The pattern has no BRE metacharacter (`\ ^ $ . * [ ]`), or `--substring`/`-F` was given ON
   THE COMMAND LINE (R0 knows; there is no click default to confuse it).
2. Exactly one pattern, from the operand or one `-e`; no `-f`/`--file` (R0b).
3. Every grep flag is index-expressible: `-i`, `-w`, `-n`, `-l`, `-c`, `-F`, `-E`, and the
   no-ops `-r`, `-R`, `-H`, `-s` (m-r4-6: the index is always recursive over the corpus, always
   prints `path:line`, and prints no per-file errors, so the habitual `rmx grep -rn x` stays on the
   index). `-h`, `--color` and `-I` are NOT (they change the bytes or the file set) and go to the
   floor.

Otherwise, and on an index miss when [[#d-4]] allows a floor, the FLOOR runs:
`grep -r <16.1 R1b pruning flags FIRST> <-E/-F from d-4> <grep_argv> <project_root>`.
- That is the real grep with every caller flag (`-A/-B/-C`, `--include`, `-m`, `-x`, `-v`, `-L`,
  `-o`, `-NUM`, …), so bug-077's case rule and BRE are the tool's own.
- The floor runs as a CHILD (not an exec), because `--limit` caps its stdout ([[#d-4]]). stderr is
  passed through; the exit code is grep's unless the cap truncated (then 0, with the note).
- The floor teaches through 16.1's path (the learner spawn with the floor's argv), unless
  `--no-learn`.
- The `\|` refusal at `cli.py` (pre-0.65.1) is DELETED, because grep handles `\|` itself.

The index answer itself is unchanged: bug-073/074/076/077/078/083/084 rules, the resolved printed
path from r5 #b-1, and the cap note.

**BRE concepts are not read by `rmx grep` (m-r4-6), stated.** A taught `query/<pattern>` concept
whose pattern carries a BRE meta is never read by `rmx grep`, because condition 1 floors that
pattern. It is reached by exact name through `rmx context` / `rmx neighbors` / `rmx query`
(`context.py` resolves a ref to its learned `query/<ref>` concept), and its protected file entities
and `mentions` edges feed the graph either way. This is accepted; 16.4 reports the share of taught
concepts with a BRE meta beside `forgone_index_share`.

**R4. Delete the re-implementation.**
- Deleted: `argv_order_index`, `argv_rank`, `order_triples_by_argv`, `argv_count_rows`,
  `_walk_files`, the named-path branches of `_resolve_output_shape` and `_grep_rg_fallback`,
  `_grep_delegate`, `_grep_stdin`, `_grep_stdin_addendum`, the `\|` refusal, the rmxrg `-E`
  injection, `_GREP_VALUE_FLAGS` (R0b), and the letter-bundle branch of `_parse_grep_flags`
  (dead since `d559567`; the defaults dict stays).
- Every removed test is listed in the summary with its reason (`tests/test_grep_flags.py`'s letter
  cases included).
- A test that pinned a defect class becomes an R5 differential case.

**R5. Differential, 100%, no allowlist.** {#r5}
- For each invocation in 16.2's `tests/fixtures/grep_differential.txt` that names paths or pipes
  stdin, `rmx grep RMX_ARGS` vs `/usr/bin/grep EXPECTED_GREP_ARGV` must match byte-for-byte on
  stdout, stderr and the exit code.
- A second column holds `EXPECTED_GREP_ARGV` literally (written by hand, not computed by
  `parse_rmx_grep_argv`) for every row that uses an rmx option or `--`, so the parser is asserted
  and not assumed.
- The corpus gains: `-rc zzz sub`, `-c` over a dir with a binary file, an unreadable subdir,
  `-rn alpha ./sub sub`, `-rl` with two spellings, `-l alpha f0.txt nosuch.txt`,
  `-L alpha f0.txt nosuch.txt`, `-c zzz nosuch.txt`, `-A 2`, `-B 1`, `-C 1`, a dotfile in a walked
  dir, bug-081's `\b` and `^| 15 |`, and `-c "^+"` over a pipe.
- **b-r4-2 rows:** `-- -x f.txt` (grep argv keeps `--`; named route), `-c -- -foo f.txt`,
  `--file=pats.txt f.txt` (named), `-f pats.txt f.txt`, `-f pats.txt -f pats2.txt f.txt`,
  `-e a -e b f.txt`, `-d skip alpha f.txt sub`, `--binary-files text alpha f.txt`,
  `--label L -H alpha` over a pipe, `-i foo -- --limit 3` (`--limit` and `3` are operands).
  Refusal rows (exit 2, grep not run): `--flags=-c x f.txt`, `--limit 5 --limit 7 x f.txt`,
  `-ik code x f.txt`, `--limit 5 x f.txt`.

**R6. Telemetry stays, and the exec is recorded (#m-r3-5, m-r4-3).** {#r6}
- Before the exec, rmx writes the `query.log` row with `answered_by = dropin` (paths) or `stdin`
  (pipe), so those values stay live and plan-14's harness keeps working.
- `cli_entry` writes its `cli.log` record in a `finally` that `os.execv` never reaches. So, also
  before the exec, rmx writes that `cli.log` record itself through the same telemetry writer, with
  `outcome = "handed-off"`, `handed_off_to = <abs grep>`, `exit_code = null` and `latency_ms` up to
  the exec. The grep's own exit code and duration are recorded NOWHERE; that is stated in the
  summary and in `rmx learn status --help`, not hidden.
- A floor run (a child, R3) keeps the normal `cli_entry` record with the real exit.

**R7. Documented callers (#s-r3-5).** Updated with this task:
- `docs/agent-doc-primer.md:49-52` (`rmx grep "FIXME" src/ tests/` needs `-r`);
- the `rmx grep` docstring examples in `cli.py`, which now also document rmx's options (R0) and say
  `-i` is OFF by default (case-SENSITIVE, as grep);
- `hooks.py`'s "bare grep/rg flags OK" comment;
- README grep examples.

A test greps `docs/`, `README.md`, the templates and `rmx grep --help` for `rmx grep` examples that
name a directory without `-r`, for `-f '-` / `--flags`, and for "ignore-case (default ON", and fails
on any it finds.

**R8. bug registry, precisely (#s-r3-4).**
- `superseded by task-16.5 (code deleted)`: bug-058, 059, 060, 062, 063, 064, 066, 079; r4 #b-2,
  #b-3, #b-4, #m-4; r5 #s-2.
- `fixed by task-16.5 R3`: bug-081.
- bug-076, 077, 078, 083 and 084 stay as they are, because their code is kept.

## Acceptance criteria {#acceptance}

1. **R5's differential passes at 100%, with power.** Before the change, every case is run against
   the CURRENT `rmx grep`, and the differing cases are recorded. At least round 4's cases, bug-081's
   two, the `-c "^+"` pipe case, `-- -x f.txt` and `-i foo -- --limit 3` must differ.
2. **No added bytes.** Named-path and pipe runs write nothing beyond the tool's bytes, with learning
   on and off.
3. **Parser and translation (R0, R0b, d-4).**
   - Each d-4 cell has a unit case asserting `(rmx_opts, grep_argv, refusals)` literally.
   - `--limit 5 PAT file` exits 2 with the named refusal, and grep is never run.
   - `--` survives: `-- -x f.txt` gives `grep_argv == ['--', '-x', 'f.txt']` and routes NAMED.
   - A repeated rmx option and `-ik` are refused; `-e --limit f` keeps `--limit` as the pattern.
   - `-e a -e b` path-less routes to the floor; `--file=pats.txt` path-less routes to the floor;
     `--file=pats.txt f.txt` routes named.
   - `-I`, `-r`, `-R`: named route passes each to grep verbatim; path-less `-r`/`-R` stay on the
     index; path-less `-I` goes to the floor (s-r4-1).
4. **The caller never waits for the learner (s-r4-3).** No FIFO (a writerless FIFO blocks the
   caller's own grep in `open`; probed 3.0 s). Instead:
   - a 4 MB regular corpus file of non-matching text and the pattern `\(.*\)\1Z` (probed:
     about 2.2 s per 2 MB with no match on BSD 2.6.0); the test first measures `T_bare`, the bare
     `/usr/bin/grep` wall on it, and requires `T_bare ≥ 3 s` (else it grows the file);
   - `RMX_GREP_LEARN_TIMEOUT_S=1`, learning ON, in the sandbox of [[#sandbox]];
   - `rmx grep -c '\(.*\)\1Z' big.txt` returns grep's own bytes and exit within
     `T_bare × 1.2 + 0.5 s`, and the REAL learner's `grep-learn.log` record (`outcome=timeout`)
     appears within `1 + 2 s` of the spawn. Both read a regular file independently: no race.
   - A pipe run writes no record.
5. **The path-less routing (R3, d-4) — on a SEEDED store (s-r4-2).** Before the routing cases, the
   real learner + drain (16.1 AC-13's path) teaches `query/alpha` AND `query/alpha$` rows on the
   tmp store, so a misrouted call would answer from the index and differ.
   - 5a. A plain `alpha` answers from the index (`answered_by=index`).
   - 5b. `rmx grep 'alpha$'`, `rmx grep -A2 alpha`, `rmx grep --include='*.py' alpha` go to the
     floor. Each is compared to a LITERAL expected output written in the test (not to a command
     built by the implementation's helper): `--include='*.py'` returns ONLY the fixture's `.py`
     files, never its `.md`/`.txt` ones.
   - `rmx grep -i ERROR` still answers case-insensitively from the index.
   - 5c. `--limit 2` on a floor call with 5 matching lines prints 2 lines, the truncation note,
     exit 0.
   - 5d. `-k code alpha_missing` (index miss) prints the d-4 line and exits 1; the floor did not run
     (no learner record, no grep child).
   - 5e. `-k code 'alpha$'` (straight to the floor) is refused, exit 2.
   - 5f. `--no-fallback alpha_missing` exits 1 with today's line; `--no-fallback -A2 alpha` is
     refused, exit 2.
   - 5g. `--via-replica -A2 alpha` runs the floor and prints the one d-4 note.
6. **The deletions are real.** `rg -w` over `src/ tests/ bin/` for each deleted symbol returns
   nothing. That catches in-function imports, which `--collect-only` misses. The grep section's line
   count before and after goes in the summary.
7. **Telemetry.** A named-path and a pipe run each leave a `query.log` row with `answered_by` set to
   `dropin` and `stdin` respectively, AND a `cli.log` record with `outcome=handed-off` and
   `exit_code=null` (m-r4-3).
8. **Docs.** R7's scan finds no directory example without `-r`, no `--flags`, and no "default ON"
   ignore-case claim.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/cli.py` | raw-argv `click.Command` subclass; `parse_rmx_grep_argv`; routing split on 16.1's table; routing (named/pipe → exec; plain path-less → index; else floor child); d-4 refusals; deletions per R4; `query.log` + `cli.log` records before the exec |
| `src/refmatrix/grep_learn.py` | the Python spawn function with 16.2 R2b's cwd rule; the grep table's `value` column exported for R0/R0b |
| `tests/test_grep_*.py` | deleted-code tests removed or converted (listed); R5 cases; parser units; the sandbox guard in `tests/conftest.py` |
| `docs/agent-doc-primer.md`, `README.md`, `src/refmatrix/hooks.py` | R7 |
| `workflow/bug_registry.md` | R8 |

## Test sandbox (s-r4-6) {#sandbox}

16.2's sandbox rule covers the wrappers; 16.5's spawn is `grep_learn.spawn()` inside `rmx grep`,
which a PATH-`rmx` guard cannot see, and `_root()` from the repo cwd resolves the LIVE
`.refmatrix/` (`92c374c`). So:
- Every 16.5 test runs with its cwd in a tmp project (a SHORT `mkdtemp()` root, its own
  `.refmatrix/`), via `monkeypatch.chdir` for in-process `CliRunner` calls and `cwd=` for
  subprocesses. Tests where learning is not the subject also set `RMX_LEARN=0`.
- A `tests/conftest.py` autouse guard wraps `grep_learn.spawn` (call-through, test-side only) and
  FAILS the test when the resolved `store_root` is this repo's `.refmatrix/` or `~/.refmatrix/`.
  Subprocess tests cannot be wrapped, so each sets `cwd=` to the tmp project, and the guard's own
  test proves it fires (a spawn from the repo cwd fails).
- A live-queue byte-size sentinel was considered and rejected: concurrent agent sessions in this
  tree grep through the live shim, so the live queue grows during any suite run.

## Test strategy {#test-strategy}

Real `/usr/bin/grep`, `shell=False`, list argv, inside [[#sandbox]]. Pre-registered mutations:

| mutation | must fail |
|---|---|
| re-add a stderr banner | AC-2 |
| render named-path output in Python | AC-1 |
| pass `--limit` to grep instead of refusing | AC-3 |
| parse rmx options from click's `argv` (drops `--`) | AC-3 `--` case, AC-1 `-- -x f.txt` |
| keep the last of a repeated rmx option | AC-3 |
| route on `_GREP_VALUE_FLAGS` (`--context` as a value flag) | AC-3 / R5 rows |
| keep only the last `-e` on a path-less call | AC-3 (`-e a -e b` must floor) |
| floor with `rg -F` | AC-5b `alpha$` |
| floor drops the caller's `-i` | AC-5 (case cases in the differential) |
| route BRE patterns to the index | AC-5b on the SEEDED store |
| always add the pruning `--include`s (ignore the caller's `--include`) | AC-5b `--include='*.py'` literal set |
| run the floor under `-k` | AC-5d |
| run the floor under `--no-fallback` | AC-5f |
| skip the pre-exec telemetry rows | AC-7 |
| remove the sandbox guard's store check | the guard's own test |

{#tests}
