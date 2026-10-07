---
gmd: "0.1"
id: task-16.3-grep-tool-hook-and-docs
title: "Task 16.3: the Grep-tool hook teaches through the same learner; every doc says grep is observed"
tags: [task, grep, hooks, docs]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
---

# Task 16.3: Grep-tool hook on the learner, and the docs {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending
> Depends on: [[task-16.1-argv-faithful-learner]]

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]

## Why {#why}

`grep-tool-teach.sh` (PostToolUse(Grep), rendered from `search_hooks.TEACH_TEMPLATE`) teaches
Claude Code's dedicated Grep tool by firing a detached `rmx grep -E --limit 3 PATTERN` from the
project root. That is the same flag-stripped ping 16.1 replaces, with two further losses:

- it drops the tool's `path`, `glob`, `type` and `-i` inputs, so it searches a different corpus
  under different rules;
- it runs through rmx's floor rather than through rg, which is the engine the Grep tool itself
  uses. {#why-lead}

## Requirements {#requirements}

**R1. The tool input becomes rg argv, and the call goes through 16.1's entry point.**

The hook calls `rmx grep-learn --tool rg --cwd "$CWD" -- <argv>`, where argv is built from
`tool_input`:

| tool_input | rg argv |
|---|---|
| `pattern` | `-e PATTERN` |
| `path` (file or dir; default the cwd) | trailing operand |
| `glob` | `-g GLOB` |
| `type` | `-t TYPE` |
| `-i: true` | `-i` |
| `multiline: true` | `-U --multiline-dotall` |
| `output_mode`, `-n`, `-A/-B/-C`, `head_limit` | ignored: shaping only |

- The field names are read from the hook payload of a REAL Grep call captured on this machine,
  not from memory. A fixture holds that payload.
- An unrecognised input field is recorded by the learner as `unknown-input:<name>` and teaches
  nothing. It is not silently ignored.
- The throttle stamp stays in the hook, as it is today. {#r1}

**R2. Docs say the same thing everywhere.**
- `search_hooks` module docstring;
- the `GUARD_TEMPLATE` and `TEACH_TEMPLATE` headers;
- the agent bashrc comment;
- the `.refmatrix/CLAUDE.md` briefing that `install-hooks` writes;
- the PRIMER header generator's "WHY THIS over raw grep" text;
- `docs/INTEGRATION.md` (hook surface);
- `docs/SYSTEM.md`, wherever it describes the rewrite.

Each of these says: grep/rg run as themselves and teach in the background; ask the index by name
with `rmx context`, `rmx grep` or `rmx_search`. None of them may say the rewrite answers from the
index. {#r2}

**R3. The no-bypass record is updated.** `feedback_rmxgrep_no_plain_escape` is amended, not
rewritten: its rule (no env opt-out from teaching) stands, and its edge to
`feedback_grep_is_observed_not_answered` already exists from the plan's decision. This task checks
that the memory bridge has ingested both, by recalling a phrase unique to each
(`feedback_verify_memory_by_recall_not_get`). {#r3}

## Acceptance criteria {#acceptance}

1. **Field mapping.** For a captured real Grep payload, and for each mapped field, the taught
   `(file, line)` set equals `rg -nH --null <mapped argv>` run in the test. `glob`, `type`, `-i`
   and `path` are each a RED case first.
2. **Unknown fields are recorded.** A payload with an extra field gives `outcome=skipped`,
   `reason=unknown-input:<name>`.
3. **The hook never touches the tool result.** It exits 0 within 100 ms, measured, while the
   learner sleeps; this reuses 16.2 AC-2's stand-in.
4. **No doc still claims index answers.** `rmx install-hooks --check` is clean. A test scans the
   rendered templates, the briefing and the PRIMER header for the strings `rich`, `RMXGREP_MODE`
   and "answers from the index" in the context of grep/rg, and fails on any of them.
5. **GMD lint is clean.** `./scripts/lint-gmd.sh` reports zero errors.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/search_hooks.py` | `TEACH_TEMPLATE` → learner; docstring + headers |
| `src/refmatrix/hooks.py` | briefing + bashrc comments |
| PRIMER generator (located by `rmx context primer` at build time) | header text |
| `docs/INTEGRATION.md`, `docs/SYSTEM.md` | hook surface prose |
| `tests/test_grep_tool_teach.py` (new), `tests/fixtures/grep_tool_payload.json` (new) | AC-1..3 |

## Test strategy {#test-strategy}

- The rendered `TEACH_TEMPLATE` script is run with the fixture payload on stdin, the real rg, and
  a real store root. The test asserts on the learner's log and queue, not on the script's text.
- Pre-registered mutation: drop the `glob` mapping, and AC-1's glob case must fail. {#tests}
