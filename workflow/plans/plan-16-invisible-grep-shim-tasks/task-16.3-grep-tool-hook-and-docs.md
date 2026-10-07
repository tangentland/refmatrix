---
gmd: "0.1"
id: task-16.3-grep-tool-hook-and-docs
title: "Task 16.3: the Grep-tool hook teaches through the same learner with the tool's real argv; every doc says grep is observed"
tags: [task, grep, hooks, docs]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
  revised: 2026-10-07
---

# Task 16.3: Grep-tool hook on the learner, and the docs {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision 2, after ch-bsd spec review `bsd-plan16-spec-review-b587621`)
> Depends on: [[task-16.1-argv-faithful-learner]]

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]

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
The hook calls `rmx grep-learn --tool rg --bin "$(command -v rg)" --cwd "$CWD" -- <argv>`, where
argv is:

| source | rg argv |
|---|---|
| always (tool constant) | `--hidden`, `--glob !<d>` for each VCS dir the tool excludes, `--max-columns 500` |
| `pattern` | `-e PATTERN` |
| `path` (default: the cwd) | trailing operand |
| `glob` | `-g GLOB` |
| `type` | `-t TYPE` |
| `-i: true` | `-i` |
| `multiline: true` | `-U --multiline-dotall` |
| `output_mode`, `-n`, `-A`, `-B`, `-C`, `context`, `head_limit`, `offset`, `-o` | ignored: shaping or paging only. `head_limit`/`offset` page the TOOL's output, while the learner teaches the full corpus-filtered result under its own cap. |

- **The constants and the VCS-dir list are read from the binary on this machine at build time.**
  The summary records the extraction command and its output, because an rmx version must not
  silently encode a stale list. A test fails if the rendered hook's constant set differs from a
  checked-in fixture of that extraction, so a Claude Code upgrade is a visible diff.
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
2. **Dot-directory hit.** A fixture hit under `.github/x.yml` is taught. It is in the corpus only if
   `corpus.is_relevant` allows it; otherwise it is counted `out_of_corpus`, and the test asserts
   whichever the predicate says, explicitly.
3. **Paging inputs do not kill the teach.** A payload with `offset`, `context`, `-o` and
   `head_limit` teaches.
4. **Unknown field.** An extra field gives `skipped reason=unknown-input:<name>`.
5. **The constant set is pinned.** The rendered hook's constants equal the checked-in extraction
   fixture. Changing one fails the test.
6. **The hook never touches the tool result.** It exits 0 within 100 ms while the learner sleeps
   (16.2 AC-3's stand-in).
7. **No stale claims.** A test scans the rendered templates, the briefing, the PRIMER header,
   `README.md` and the `--help` strings for `rich`, `RMXGREP_MODE` and "answers from the index" in a
   grep/rg context, and fails on any.
8. **GMD lint 0 errors; `install-hooks --check` clean.**

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/search_hooks.py` | `TEACH_TEMPLATE` → learner with the full argv; docstring + headers |
| `src/refmatrix/hooks.py`, `src/refmatrix/cli.py` | briefing, bashrc, `--help`, docstrings |
| PRIMER generator, `README.md`, `docs/{INTEGRATION,SYSTEM,ARCHITECTURE}.md`, `workflow/development_resources.md` | prose |
| `tests/test_grep_tool_teach.py`, `tests/fixtures/grep_tool_*.json`, `tests/fixtures/grep_tool_constants.txt` (new) | AC-1..7 |

## Test strategy {#test-strategy}

- The rendered `TEACH_TEMPLATE` script is run with each captured payload on stdin, using the real
  rg and a real `store_root`. Assertions are on the learner's log and queue, compared against the
  captured `tool_response`.
- Pre-registered mutations:
  - drop `--hidden`: AC-2 fails;
  - drop the `glob` mapping: AC-1 fails on a glob payload;
  - add `offset` to unknown: AC-3 fails. {#tests}
