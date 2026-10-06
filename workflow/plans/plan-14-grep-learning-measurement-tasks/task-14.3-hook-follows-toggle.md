---
gmd: "0.1"
id: task-14.3-hook-follows-toggle
title: "Task 14.3: the rewrite hook and the wrapper follow the toggle"
tags: [task, hooks, grep, toggle]
metadata:
  node_type: task
  status: complete
  created: 2026-10-05
---

# Task 14.3: toggle off ⇒ bare grep passes straight through {#root}

> Plan: [plan-14-grep-learning-measurement](../plan-14-grep-learning-measurement.md)
> Status: Complete
> Depends on: Task 14.2

rel: part-of -> [[plan-14-grep-learning-measurement]]
rel: depends-on -> [[task-14.2-learning-toggle]]

## Requirements {#requirements}

With the toggle OFF, the PreToolUse rewrite does not fire: a bare `grep` stays a real `grep`, so the
arm measures no routing and no learning (user decision 2026-10-05,
[[plan-14-grep-learning-measurement#decisions]] Q3). With the toggle ON, behaviour is exactly what
ships today. {#req-lead}

The check lives in the hook GENERATOR (`search_hooks.py`) and in the `bin/rmxgrep` wrapper, because
those are what the installed copies are rendered from. The generated hook must answer the question
with a file test and an env read only — no `rmx` subprocess, no import of the package. A rewrite
hook that pays a Python import on every tool call is a per-prompt tax, and this one runs on EVERY
bare grep in every session. {#req-cheap}

`rmx install-hooks --check` must be clean after regeneration (CLAUDE.md#before-commit): installed
config equals generated config. {#req-check}

## Acceptance criteria {#acceptance}

1. Toggle ON: the generated rewriter rewrites `grep -rn PAT src/` to the wrapper, unchanged from
   today.
2. Toggle OFF (env, per-store marker, and global marker each tested): the same input is returned
   untouched, exit 0, and nothing is written to the learn queue.
3. The pipe short-circuit still wins regardless of the toggle — a grep READING A PIPE is a filter
   and stays byte-exact (bug-005's rule).
4. The toggle check costs no subprocess and no package import: asserted by reading the generated
   script, not by timing it.
5. `rmx install-hooks --check` is clean after the change.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/search_hooks.py` | the generated rewriter consults the toggle before rewriting |
| `bin/rmxgrep` | the wrapper execs the real tool when the toggle is off |

## Out of scope — and this matters {#out-of-scope}

**bug-066 is NOT fixed here.** That row says the installed rewriter resolves a STALE wrapper copy
(`.venv/bin/rmxgrep`, 4,760 B) while the deployed wrapper is `bin/rmxgrep` (5,714 B), and that the
`RMXGREP_MODE=plain` bypass the user ordered removed is still live on that copy. It needs a user
decision on the config, and its fix is a deploy-sync change. {#bug-066}

The consequence for THIS task, stated so the next reader is not misled: a toggle added to
`bin/rmxgrep` reaches the live path only after bug-066's sync, so until then the authoritative check
is the one in the generated hook. The task is complete when both carry it and the hook test proves
the generated artifact honours it — not when the live wrapper does. Claiming otherwise would be the
"fix verified on a path the defect does not take" shape
([[feedback_verify_fix_reachable_from_master]]). {#bug-066-consequence}

## Test strategy {#test-strategy}

Extend `tests/test_rmxgrep.py` / the hook-render tests: render the rewriter with the generator, run
the rendered script as a subprocess against a fabricated PreToolUse payload in all four toggle
states, and assert on the returned command. The ON case must be asserted too — a test that only
checks the OFF case passes against a rewriter that never rewrites anything. {#tests}
