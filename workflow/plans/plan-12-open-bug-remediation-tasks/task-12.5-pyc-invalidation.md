---
gmd: "0.1"
id: task-12.5-pyc-invalidation
title: "Task 12.5: the suite refuses timestamp-invalidated bytecode"
tags: [task, plan-12, tests, bytecode]
metadata:
  node_type: task
  status: pending
  plan: plan-12-open-bug-remediation
---

# Task 12.5: the suite refuses timestamp-invalidated bytecode {#root}

> Plan: [[plan-12-open-bug-remediation]]
> Status: Pending
> Bug: bug-037
> Depends on: —

rel: part-of -> [[plan-12-open-bug-remediation]]

## Requirements {#requirements}

- bug-037: a mutation check edited `"45"` -> `"20"` (same byte length), the source was restored from
  a backup, and the `.pyc` written from the MUTATED source kept being served. `PROBE_TIMEOUT_S` read
  20.0 at runtime while the file on disk read 45. Two tests failed for a reason that had nothing to
  do with the code under test, and a GREEN run in the same state would have been just as wrong.
- CPython validates a timestamp `.pyc` against the source's `(mtime, size)`. A same-length edit
  removes size as a discriminator; a restore that preserves mtime removes the other. **Hash-based
  invalidation (PEP 552, `checked-hash`) validates against the source's hash and cannot be fooled
  by either.**
- `tests/conftest.py` gains a session-scoped guard that, before any test runs, verifies every
  `src/refmatrix/**/__pycache__/*.pyc` is either absent or **hash-based and checked**, and fixes it
  in place (`compileall --invalidation-mode checked-hash` over `src/refmatrix`) rather than failing
  the run. It PRINTS what it recompiled — a silent repair on a memory-adjacent path is exactly the
  failure `no-silent-failures` names.
- The guard is scoped to the dev tree's own `src/`, never to site-packages, never to the deploy
  tree: recompiling somebody else's install is not this suite's business.
- `RMX_PYC_GUARD=0` opts out for a run that deliberately wants the default behaviour.
- The 16-byte `.pyc` header is read directly (magic, then the flags word: bit 0 = hash-based,
  bit 1 = check_source). No `importlib` private API.

## Files to Create / Modify {#files}

- modify `tests/conftest.py` (session guard)
- create `tests/test_pyc_invalidation.py`
- modify `workflow/bug_registry.md` (bug-037 -> fixed, with the mechanism)

## Test Strategy (RED first) {#test-strategy}

`tests/test_pyc_invalidation.py`, all over a tmp package, never the real `src/`:
- a timestamp `.pyc` (flags bit 0 clear) is DETECTED as unsafe by the header reader
- a `checked-hash` `.pyc` is detected as safe; an `unchecked-hash` one is NOT (it skips validation
  entirely, which is worse than a timestamp pyc, not better)
- **the incident replay**: write module `m.py` with `X = 45`, import it, mutate to `X = 20` (SAME
  byte length), restore the original bytes AND the original mtime, then import in a fresh
  interpreter — with timestamp pycs the stale value is served (the bug reproduces), and after the
  guard recompiles with `checked-hash` the restored value is served. If the stale read cannot be
  reproduced on this interpreter the test FAILS LOUD rather than passing vacuously, because a
  guard proven against a bug that did not happen proves nothing.
- the guard reports the files it recompiled and returns a count; a clean tree recompiles zero
- `RMX_PYC_GUARD=0` skips the guard entirely
- mutation check: making the header reader always return "safe" turns the replay test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation noted in the implementation summary.
- `workflow/implementation_summaries/task-12.5-pyc-invalidation.md`.
- Branch `task-12.5-pyc-invalidation`, merged `--no-ff` to `master`.
