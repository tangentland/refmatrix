---
gmd: "0.1"
id: task-16.3-grep-tool-hook-and-docs
title: "Task 16.3: the Grep-tool hook teaches through the same learner with the tool's real argv; every doc says grep is observed"
tags: [task, grep, hooks, docs]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
  revised: 2026-10-14
---

# Task 16.3: Grep-tool hook on the learner, and the docs {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision after the 2026-10-14 decision log; revision 6, answering spec review
> r5 `bsd-plan16-spec-review-r5-cd7c923`)
> **Wave:** 2 ([[plan-16-invisible-grep-shim#waves]]).
> Depends on: [[task-16.1-argv-faithful-learner]]. Tests run in plan-23 task 23.0's sandbox.

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]
rel: amends -> [[bsd-plan16-spec-rereview-42a5521]]
rel: amends -> [[bsd-plan16-spec-review-r3-c8278b1]]
rel: amends -> [[bsd-plan16-spec-review-r4-33809ab]]
rel: amends -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: derives-from -> [[plan-review-2026-10-14#t7]]

## Revision 6 changelog {#revision-6}

Answers spec review r5 ([[bsd-plan16-spec-review-r5-cd7c923]]), which found 16.3 needing no change
of its own (AC-9's mutation was probed able to fire), and the 2026-10-14 decision log.

| finding / decision | answered in |
|---|---|
| r5 s-r5-6 / #t7-fixes (`spawned_by` on learner records, so 16.4 can join Grep-tool records to Grep `tool_use`s) | R1 [[#r1]] (`--spawned-by grep-tool-hook`); AC-1 asserts it; mutation |
| d1a/d1b (tests sandboxed by task 23.0) | [[#test-strategy]] |

## Revision 5 changelog {#revision-5}

Answers spec review r4 ([[bsd-plan16-spec-review-r4-33809ab]]).

| finding | answered in |
|---|---|
| s-r4-4 `<epoch> no-rg` in the `busy` log, from a hook with no `store_root` | R1 binary resolution [[#r1]]: the hook always calls the learner; a missing rg is the learner's `skipped reason=no-binary` record. AC-5c |
| m-r4-2 glob cell "contains `{`" vs "BOTH `{` and `}`" | R1 glob row: one rule (BOTH) |
| m-r4-4 the single-file branch has no AC | AC-9 + mutation |

## Why {#why}

`grep-tool-teach.sh` (PostToolUse(Grep)) teaches Claude Code's Grep tool by firing a detached
`rmx grep -E --limit 3 PATTERN` from the project root. It drops the tool's `path`, `glob`, `type` and
`-i` inputs, and it runs through rmx's floor rather than the rg the tool itself ran.

Revision 1 of this spec mapped the tool inputs from memory. The ch-bsd review read the Claude Code
binary and found that the Grep tool always passes `--hidden`, a `--glob !<vcs dir>` for each VCS
directory and `--max-columns 500`. It also accepts `offset`, `context` and `-o`, which revision 1's
table left out. So every dot-directory hit went untaught, and every call that carried one of those
inputs was killed (#b-3). {#why-lead}

## Requirements {#requirements}

**R1. Rebuild the tool's own rg argv, from the tool's own code, pinned by a captured payload.**
The hook calls `rmx grep-learn --tool rg --bin "$RG_ABS" --cwd "$CWD" --spawned-by grep-tool-hook
-- <argv>`. `--spawned-by grep-tool-hook` lets 16.4 join this record to the Grep `tool_use`, not
read it as route 2 (s-r5-6).

**Binary resolution (#s-n5).** `TEACH_TEMPLATE` is a bash script, and hooks inherit `BASH_ENV`.
Measured: `bash -c 'command -v rg'` prints `rg`, the agent-bashrc FUNCTION. So:
- `RG_ABS` is `type -P rg`, which resolves PATH only and never a function (probed: prints
  `/opt/local/bin/rg` under `BASH_ENV`).
- **A missing rg is the learner's record, not a second log format (s-r4-4).** The hook ALWAYS
  calls the learner. If `RG_ABS` is empty (rg not on PATH) it passes `--bin ""`; the learner, which
  resolves `store_root` from `--cwd` (R2), writes its one JSONL record `outcome=skipped
  reason=no-binary` (16.1 R1) and runs nothing. The hook writes nothing itself and needs no
  `store_root`; the shim's `busy`/`throttled` files keep their single meaning (16.2 R3).
- The `rmx` call runs under `env -u BASH_ENV`.
- The test runs with `BASH_ENV` set to a file that defines `rg()`, so a function-resolving build
  fails it.

**Single-file `path` (#s-r3-10).** When `path` names a FILE, the Grep tool applies `glob`/`type`
itself and returns nothing on a mismatch, while rg 15.1.0 ignores globs on a named file. So when
`path` is a file and `glob` or `type` is set, the learner teaches nothing
(`reason=single-file-filter`). This is counted. The exact filter is not modelled.

**Paging (#s-r3-8).** The tool's default `head_limit` is 250, with pagination. A response that
carries the pagination marker is INCOMPLETE for 16.4's oracle, and AC-1's captured fixtures are
recorded below that limit.

**Builtin vs system rg (#s-n5). The Grep tool runs Claude Code's BUILTIN ripgrep with
`--no-config`; the learner re-runs the SYSTEM rg (`/opt/local/bin/rg`, 15.1.0) with `--no-config`
added. That is a stated divergence, not a claim of sameness. The build records both versions in the
summary, and AC-1 (which compares against the tool's own response) is what catches a behavioural
difference.

The argv is:

| source | rg argv |
|---|---|
| always (tool constant) | `--no-config`, `--hidden`, `--glob=!<d>` for each VCS dir the tool excludes (`.git .svn .hg .bzr .jj .sl` in 2.1.292), `--max-columns=500` |
| `pattern` | `-e PATTERN` |
| `path` (default: the cwd) | trailing operand |
| `glob` | the tool's own SPLIT (#s-n4): split on whitespace; then a piece that contains BOTH `{` and `}` is kept whole, and every other piece is split on commas (#m-r3-3, read from the binary; m-r4-2: this is the only rule). One `--glob=<piece>` per piece. `*.ts,*.tsx` and `*.py *.md` become two globs; `*.{ts,tsx}` stays one; `a{,b` (no `}`) splits on its comma. |
| `type` | `-t TYPE` |
| `-i: true` | `-i` |
| `multiline: true` | `-U --multiline-dotall` |
| `output_mode`, `-n`, `-A`, `-B`, `-C`, `context`, `head_limit`, `offset`, `-o` | ignored: shaping or paging only. `head_limit`/`offset` page the TOOL's output, while the learner teaches the full corpus-filtered result under its own cap. |

- **The constants (the VCS-dir list, `--max-columns`, the glob split rule) are extracted from the
  binary.** The extraction is anchored on CONTENT, not on minified identifiers.
  - `"--max-columns","500"` occurs once in the binary (probed), so it is a sound anchor.
  - The VCS list is the array referenced next to the `--glob` `!`-exclusion emitter. A member
    search finds three arrays, one of them a different 8-member list, so member matching alone is
    ambiguous (#s-n6/#m-r3-3).
  - The 33 s scan of the 235 MB binary is cached, keyed on (path, size, mtime). The result is checked in as
  `tests/fixtures/grep_tool_constants.txt`.
- **AC-5 re-extracts from the INSTALLED binary on every run (#s-n6)**, from
  `$CLAUDE_CODE_EXECPATH`, else `~/.local/bin/claude`. It compares both the fixture and the
  rendered hook with that extraction. When the binary auto-updates (it is `versions/2.1.292`,
  installed 2026-10-06), the suite FAILS until the fixture is refreshed. When no binary is present
  it skips with a printed reason.
- **Unmodelled, named as divergence (#s-n6):** the tool's DYNAMIC exclusions are not modelled:
  permission-deny `--iglob` patterns, orphaned-plugin globs and task-output globs. The deny list is
  empty on this machine today. A taught hit inside one of them is a hit the tool did not return,
  and AC-1 measures that.
- **An unrecognised input field** gives `outcome=skipped reason=unknown-input:<name>`. With the full
  table, that now means a genuinely new field. {#r1}

**R2. The learn switch is the learner's (#b-4).** The hook does no switch check of its own and calls
the learner with `--cwd`. The learner resolves `store_root` and checks it (16.1 R5). This route has
no other check, so 16.1 AC-10 7b covers it. {#r2}

**R3. Docs and help say "observed" everywhere (#s-12).** Each of these is updated, and the summary
lists them with line refs:
- `search_hooks` module docstring, `GUARD_TEMPLATE` and `TEACH_TEMPLATE` headers;
- the agent bashrc comment;
- the `.refmatrix/CLAUDE.md` briefing;
- the PRIMER header generator;
- `README.md` (rich/plain prose ~209-213, `RMXGREP_MODE` env block ~257, ~412);
- `rmx grep`'s docstring;
- the install-hooks `--help` ("(+ RMXGREP_MODE)");
- the `learn` group docstring;
- `docs/INTEGRATION.md`, `docs/SYSTEM.md`, `docs/ARCHITECTURE.md` (~398);
- `workflow/development_resources.md` (~36, "`RMXGREP_MODE=rich` the only value").

The message in each: grep/rg run as themselves and teach in the background; ask the index by name
with `rmx context`, `rmx grep` or `rmx_search`; route 3 (Claude Code's own `grep()`) is not
observed. {#r3}

**R4. Memories.** Confirm that `feedback_rmxgrep_no_plain_escape` and
`feedback_grep_is_observed_not_answered` are both in the store, with a recall for a phrase unique to
each (`feedback_verify_memory_by_recall_not_get`). {#r4}

## Acceptance criteria {#acceptance}

1. **Fidelity against the TOOL's output, not the mapping's (#b-3).**
   - A captured real Grep `tool_input` + `tool_response` pair is held as fixtures, recorded on this
     machine in `files_with_matches` and `content` modes.
   - The taught `(file, line)` set equals what the tool RETURNED (content mode, line-addressed),
     corpus-filtered. In files mode, the taught file set equals the returned file set.
   - The control is the tool's response. It is never `rg` run on the mapped argv.
   - The learner's record carries `spawned_by=grep-tool-hook` (s-r5-6).
2. **Dot-directory hit.** A fixture hit under `.github/x.yml` is taught. It is in the corpus only if
   `corpus.is_relevant` allows it; otherwise it is counted `out_of_corpus`, and the test asserts
   whichever the predicate says, explicitly.
3. **Glob split (#s-n4).** Payloads with `glob: "*.ts,*.tsx"`, `glob: "*.py *.md"` and
   `glob: "*.{ts,tsx}"` each teach what the tool returned. RED: a single-`-g` mapping teaches
   nothing for the first two.
3b. **Paging inputs do not kill the teach.** A payload with `offset`, `context`, `-o` and
   `head_limit` teaches.
4. **Unknown field.** An extra field gives `skipped reason=unknown-input:<name>`.
5. **The constant set tracks the installed binary.** The fixture, the rendered hook and a live
   re-extraction from the installed Claude Code binary all agree. Changing any one of them fails
   the test.
5b. **Binary resolution.** With `BASH_ENV` defining `rg()`, the learner's log record carries an
   ABSOLUTE `bin`.
5c. **No rg (s-r4-4).** With `PATH` holding no `rg`, a payload yields exactly one learner record
   `outcome=skipped reason=no-binary` in `<store_root>/grep-learn.log`, and the shim's
   `.rmxgrep-teach/busy` file is unchanged.
6. **The hook never touches the tool result.** It exits 0 within 100 ms while the learner sleeps
   (16.2 AC-3's stand-in).
7. **No stale claims.** A test scans the rendered templates, the briefing, the PRIMER header,
   `README.md` and the `--help` strings for `rich`, `RMXGREP_MODE` and "answers from the index" in a
   grep/rg context, and fails on any.
8. **GMD lint 0 errors; `install-hooks --check` clean.**
9. **Single-file filter (m-r4-4).** Two captured-shape payloads: `{path: <file>, glob: "*.nomatch"}`
   and `{path: <file>, type: "rust"}` on a `.py` file that contains the pattern. The tool returns
   nothing for both; each yields `outcome=skipped reason=single-file-filter`, nothing queued. A third
   payload, `{path: <file>}` alone, teaches (the branch is narrow).

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/search_hooks.py` | `TEACH_TEMPLATE` → learner with the full argv; docstring + headers |
| `src/refmatrix/hooks.py`, `src/refmatrix/cli.py` | briefing, bashrc, `--help`, docstrings |
| PRIMER generator, `README.md`, `docs/{INTEGRATION,SYSTEM,ARCHITECTURE}.md`, `workflow/development_resources.md` | prose |
| `tests/test_grep_tool_teach.py`, `tests/fixtures/grep_tool_*.json`, `tests/fixtures/grep_tool_constants.txt` (new) | AC-1..7 |

## Test strategy {#test-strategy}

- **Sandbox (d1a/d1b).** Every test runs inside plan-23 task 23.0's shared sandbox (`$HOME`,
  global root, registry and LaunchAgents dir in a tmp dir before `refmatrix` is imported; spawned
  `rmx` children refuse sockets outside it; the conftest guard fails any touch of `~/.refmatrix` or
  a registered live store), with `store_root` in a tmp project under a SHORT `mkdtemp()` root.
- The rendered `TEACH_TEMPLATE` script is run with each captured payload on stdin, using the real
  rg and a real `store_root`. Assertions are on the learner's log and queue, compared against the
  captured `tool_response`.
- Pre-registered mutations:
  - drop `--hidden`: AC-2 fails;
  - drop the `glob` mapping: AC-1 fails on a glob payload;
  - add `offset` to unknown: AC-3b fails;
  - drop the glob split: AC-3 fails;
  - remove the single-file-filter branch: AC-9 fails (the `.py` hits are taught);
  - write `no-rg` from the hook instead of calling the learner: AC-5c fails;
  - use `command -v` for `RG_ABS`: AC-5b fails;
  - hardcode a stale VCS list: AC-5 fails against the live extraction;
  - omit `--spawned-by grep-tool-hook`: AC-1's `spawned_by` assertion fails. {#tests}
