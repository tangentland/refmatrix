---
gmd: "0.1"
id: task-12.5-pyc-invalidation-summary
title: "Implementation summary: the suite refuses timestamp-invalidated bytecode"
tags: [summary, plan-12, tests, bytecode]
metadata:
  node_type: summary
  task: task-12.5-pyc-invalidation
  created: 2026-09-16
---

# Implementation summary: task 12.5 (bug-037) {#root}

rel: implements -> [[task-12.5-pyc-invalidation]]
rel: part-of -> [[plan-12-open-bug-remediation]]

## What shipped {#shipped}

- `tools/pyc_guard.py` — `pyc_flags`, `pyc_is_safe`, `scan_unsafe`, `stale_timestamp_pycs`,
  `enforce`, and a `__main__` so it runs by hand after a mutation batch.
- `tests/conftest.py` — `pytest_sessionstart` enforces `src/refmatrix` before any test runs.
- `tests/test_pyc_invalidation.py` — 10 tests, including the incident replay.

## The mechanism, reproduced {#mechanism}

CPython validates a timestamp `.pyc` against the source's `(mtime, size)`. The replay test writes
`X = 45`, imports it, mutates to `X = 20` (same byte length), imports again so the `.pyc` records
the mutant, then restores the ORIGINAL bytes and `utime`s the source onto the mtime the `.pyc`
recorded. A fresh interpreter serves **20** from a file that says **45**. That is bug-037.

Two things the build found that the spec did not predict:

1. **The bug is cheaper than recorded.** The first draft of the replay did not touch mtimes at all
   and still reproduced — two writes inside the same mtime SECOND make a same-length edit invisible
   with no restore involved. The test now moves the mutant off the original's second explicitly, so
   it demonstrates the recorded mechanism rather than an easier one.
2. **"No timestamp pyc exists" is not an assertable invariant.** `importlib` writes a timestamp pyc
   for every module it compiles and has no hook to do otherwise (`SOURCE_DATE_EPOCH` reaches
   `py_compile`, never the import machinery). The invariant that holds is: bytecode present at
   session start is converted to `checked-hash`, and anything written afterwards came from the
   source this process just read. `stale_timestamp_pycs` asserts the on-disk half of that.

## RED / GREEN / mutation {#evidence}

- RED: `workflow/review-output/red-task-12.5.log` — 9 failed (no `tools/pyc_guard.py`).
- GREEN: `workflow/review-output/green-task-12.5.log` — 10 passed.
- Mutation A (`pyc_is_safe` -> always True): 6 failed — `workflow/review-output/mutation-task-12.5.log`.
- Mutation B (conftest does not call `enforce`): `test_the_repo_tree_is_enforced_by_conftest` RED.
  The FIRST version of the wiring assertion survived this mutation — it read an env var conftest
  set itself, so it proved the hook ran, not that the guard did. The evidence moved inside
  `enforce` (`RMX_PYC_GUARD_ROOTS`), and the mutation then killed it.
- `__pycache__` cleared after every mutation restore, per the lesson bug-037 itself taught.

## Live effect {#live}

First enforced run on the dev tree converted **12** timestamp pycs under `src/refmatrix`.
