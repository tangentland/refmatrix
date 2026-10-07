---
gmd: "0.1"
id: task-16.5-explicit-grep-hands-off
title: "Task 16.5: explicit `rmx grep` with paths or a pipe execs the real grep; rmx renders only the path-less index read"
tags: [task, grep, drop-in, simplification]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 16.5: the explicit command stops re-rendering grep {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (added 2026-10-07 by user decision after ch-bsd round 4: "simplify, go with
> option 1")
> Depends on: [[task-16.1-argv-faithful-learner]]

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: derives-from -> [[bsd-r1-remedy-r4-4d54f6a]]

## Why {#why}

Decision d-1 says the SHIM observes grep and does not answer it. The explicit `rmx grep PAT file…`
still answers. When paths are named, or stdin is a pipe, it re-implements grep's output in Python
on top of `rg`. That covers argument ordering, per-file `-c` rows with directory expansion, the
filename-prefix rule, `-o`, context, exit codes, and a hand-written stdin filter.

That re-implementation is where the drop-in defect family lives:
- bug-058 to bug-066 and bug-076 to bug-079;
- round 4's #b-2 (`-c` walk), #b-3 (directory spellings) and #b-4 (`-l`/`-L` exit 2);
- the pre-existing `-A/-B/-C` drop and dotfile skip (round 4 #m-4);
- bug-081's false negatives (BRE read as fixed strings by `rg -F`).

Four audit rounds in a row found a new sibling branch in it. The user's decision on 2026-10-07
deletes the code rather than patching it a fifth time. {#why-lead}

## Requirements {#requirements}

**R1. Named paths: exec the real grep, verbatim.**
- When `rmx grep` receives file or directory operands, it runs `/usr/bin/grep` with the caller's
  argv untouched. The binary is resolved once, absolute, and recorded.
- stdout, stderr and the exit code are the tool's. rmx adds nothing to stdout or stderr: no
  "delegated" banner and no provenance line, the same contract as the invisible shim.
- Before the exec, rmx spawns 16.1's learner (`--tool grep --bin … --cwd …`) under the same
  learn-switch, slot and throttle rules as the shim, through ONE shared function.
- **Behaviour change, stated:** `rmx grep PAT dir` without `-r` now does what grep does
  (`Is a directory`, exit 2). rmx no longer walks a directory on the caller's behalf.

**R2. Piped stdin: exec the real grep, verbatim.** A piped stdin with no paths runs `grep` with the
argv untouched and teaches nothing (the filter rule).
- `_grep_stdin` (rmx's Python filter) is DELETED.
- `_grep_stdin_addendum`, the stderr index note on a pipe, is DELETED. It was also the last caller
  dropping `-i`/`-w` (round 4 MEH).

**R3. Path-less: the index read stays, and its floor becomes grep.**
- `rmx grep PAT` with no paths and no pipe keeps the index-first read (`Store.grep_evidence`, with
  bug-073/074/076/077/078/083/084's rules), its rendering, and its cap note. That is the one place
  rmx answers, by name.
- On an index miss, the floor is `grep -rnH <16.1 R1b pruning flags> PAT <project_root>`. That is
  the same corpus-equivalent pruning the learner uses, and BSD BRE natively (bug-081 closed).
- Floor hits are taught through 16.1's path (not a second broker).
- The floor output is printed in grep's own format. The only shaping is the `-l`/`-c`/`-n` flags
  the caller passed, handed to grep itself.

**R4. Delete the re-implementation.** Each item is removed with its tests, and every removed test
is listed in the summary with the reason. A test that pinned a defect class of the deleted code
becomes a differential case in R5 instead.
- `argv_order_index`, `argv_rank`, `order_triples_by_argv`, `argv_count_rows`, `_walk_files`.
- The named-path branches of `_resolve_output_shape` and `_grep_rg_fallback`.
- `_grep_delegate` (its flag-routing job is subsumed by R1).
- `_grep_stdin`, `_grep_stdin_addendum`.
- The `rmxrg`-dialect `-E` injection.

**R5. Differential, 100%, no allowlist.** For every invocation in 16.2's
`tests/fixtures/grep_differential.txt` that names paths or pipes stdin, `rmx grep ARGS` vs
`/usr/bin/grep ARGS` match byte-for-byte on stdout, stderr and the exit code. The corpus gains:
- round 4's cases: `-rc zzz sub`, `-c` over a dir with a binary file, an unreadable subdir,
  `-rn alpha ./sub sub`, `-rl` with two spellings, `-l alpha f0.txt nosuch.txt`, `-A 2`;
- bug-081's `\b` and `^| 15 |`.

**R6. bug registry.**
- bug-076 to bug-079's drop-in rows, and round 4's #b-2/#b-3/#b-4/#m-4, are marked `superseded by
  task-16.5 (code deleted)` once it lands, not "fixed".
- bug-081 is marked fixed by R3.

## Acceptance criteria {#acceptance}

1. **R5's differential passes at 100%.** Before the change, the same corpus is run against the
   CURRENT `rmx grep`, and the summary records which cases differ there (power). At least round 4's
   five cases and bug-081's two must differ.
2. **Named paths and pipes.** `rmx grep` with paths, and with a pipe, writes NOTHING beyond the
   real tool's bytes, on stdout and stderr, under learning on and off.
3. **The learner is spawned for named paths and not for pipes.** Proven by `grep-learn.log`
   records with 16.1's fields, using a stand-in that sleeps (16.2 AC-3's) so the caller is not
   delayed.
4. **The path-less index read still answers from the index, with the cap note.** On a miss the
   floor answers in grep's format, using BRE natively:
   - `rmx grep 'alpha$'` on a fixture finds what `grep -rn 'alpha$' .` finds (bug-081);
   - the floor's out-of-corpus dirs are pruned (16.1 AC-5 fixture).
5. **The deletions are real.** `rg -l` for each deleted symbol in `src/` returns nothing, and the
   line count of `cli.py`'s grep section drops. Both numbers go in the summary.
6. **No orphaned test.** `pytest --collect-only` shows no test importing a deleted symbol.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/cli.py` | `grep()` routes paths/pipe → real grep + learner; path-less → index + grep floor; deletions per R4 |
| `src/refmatrix/grep_learn.py` | the shared spawn function R1 and the shims both use |
| `tests/test_grep_*.py` | deleted-code tests removed or converted (listed); R5 differential cases added |
| `workflow/bug_registry.md` | R6 |

## Test strategy {#test-strategy}

- Real `/usr/bin/grep`, `shell=False`, list argv. Pre-registered mutations:
  - re-add the "delegated" banner on stderr: AC-2 fails;
  - render named-path output through Python: AC-1's round 4 cases fail;
  - floor with `rg -F`: AC-4's `alpha$` fails. {#tests}
