---
gmd: "0.1"
id: impl-task-6.4-plan-6-deferrals-docs-benchmark
title: "Task 6.4: the perma-red was a stale fake, three registry rows added, and 'every file' was not every file"
tags: [implementation-summary, plan-6, mock-registry, bug-034, retroactive]
metadata:
  node_type: implementation-summary
  status: complete
  plan: plan-6-deferrals-docs-benchmark
  task: task-6.4-plan-6-deferrals-docs-benchmark
  created: 2026-10-19
---

# Task 6.4: the perma-red was a stale fake, three registry rows added, and "every file" was not every file {#root}

rel: implements -> [[task-6.4-plan-6-deferrals-docs-benchmark]]
rel: part-of -> [[plan-6-deferrals-docs-benchmark]]
rel: evidence-for -> [[bsd-plan6-deferrals-docs-benchmark-r1-e0b7df6#s-2]]
rel: related-to -> [[bsd-plan6-deferrals-docs-benchmark-r1-e0b7df6#b-2]]
rel: related-to -> [[plan-review-2026-10-14#t11-folded-waves]]
rel: related-to -> [[bug-registry#registry]]

## Written retroactively {#retroactive}

This summary was written on 2026-10-19 in the W1-d bookkeeping sweep
([[plan-review-2026-10-14#t11-folded-waves]]), not when the task closed on 2026-09-16. The task
spec's `#done` names this file and `CLAUDE.md#task-completion-workflow` step 8 calls it mandatory;
its absence is ch-bsd plan-6 r1 `#s-2`. Everything below is read from commits, the task spec's
`#closing` note, the bug registry and the r1 ledger. Where none of them recorded a value, this
summary says "not recorded" rather than reconstructing one. {#retroactive-body}

## What the task asked for {#asked}

Two requirements: full suite 0 failures; the mock registry lists every test file that
monkeypatches an external boundary. Four work items: make `verbs.py` `memory_partition`'s partition
detect loud, fix the `tests/test_graph_landing.py` stub daemon (`_st`), add registry rows for
external mocks, and log the "perma-red" test in `workflow/bug_registry.md`. {#asked-body}

## What was built, and where it landed {#shipped}

There is no `task-6.4-plan-6-deferrals-docs-benchmark` branch and no commit that names task 6.4 as
its subject. The work landed in four commits, three of them under other headings — which is what
the task spec's `#closing` note says. All four are ancestors of this branch's HEAD. {#shipped-lead}

- **Loud partition detect (`verbs.py` `memory_partition`)** — already done before plan-6 reached
  it. The replica-unavailable `debug` line came in `7507584` (plan-2 round 9, 2026-09-15); the
  `warning` when `partition_list` answers an error, naming root, error and the fallback partition,
  came in `a035117` (plan-3 r5, 2026-09-15). The r1 audit confirmed both branches are real and the
  silent guess is gone. {#shipped-verbs}
- **The "perma-red" (`tests/test_graph_landing.py`)** — `89b179a` (bug-034, 2026-09-16).
  `test_context_op_honors_partition_under_ambient_drift` was never a partition bug: a hand-rolled
  `class D` pinned `d.store` after `_op_context` moved to `d._st()`, so it raised
  `AttributeError`. The same commit fixed the other four idle-machine failures; bug-034's row
  records that none of the five was a product bug. {#shipped-perma-red}
- **Attribution of the perma-red** — `9a3b5d8` (2026-09-16) re-ran the seven idle-machine failures
  against master and named `test_graph_landing` as "the perma-red already named in plan-6 task
  6.4". The r1 ledger lists `89b179a` and `9a3b5d8` together as the 6.4 / bug-034 commits.
  {#shipped-attribution}
- **Mock registry rows and the closing note** — `1f65b0d` (task 6.1's commit, 2026-09-17, merged
  via `8efef73`): "tasks 6.4 and 6.5 closed out: three unregistered external-boundary mocks added
  to the mock registry". The three files were `test_daemon_liveness.py` (OS socket + pid),
  `test_hub_plist_devtree.py` (launchd + subprocess) and `test_sync_and_extras.py` (`tldr`
  binary, `shutil.which`, launchd, daemon ping). `test_surface_parity.py` was judged
  configuration-only (env vars) and given no row. {#shipped-registry}
- **Bug registry entry** — bug-034, written in `89b179a`. {#shipped-bug}

## Verification {#verification}

| gate | result | source |
|---|---|---|
| RED | not recorded — the spec's strategy was "existing suite + registry lint", no new tests | task spec `#test-strategy` |
| GREEN (bug-034) | 46 passed across the five suites (`pytest-bug034-green.log`) | `89b179a` message |
| Mutations (bug-034) | four, each killing its test; "dropping the explicit partition bind" is the one that fails `test_graph_landing` (1 fail) | `89b179a` message, bug-034 row |
| Mutation on the `verbs.py` log branches | not recorded — no test asserts the `warning` fires | r1 `#s-2` |
| Full suite at the task's close | 2071 passed, 854 s | `1f65b0d` message |
| Full suite, independent | 2238 passed, 0 failed at `e0b7df6` | r1 ledger `#suite` |
| Registry lint | not built — no test reads `workflow/test_mock_registry.md` | r1 `#b-2` |

The full-suite clause holds; the r1 audit measured it itself. {#verification-note}

## What is still open {#open}

The registry clause does not hold. ch-bsd plan-6 r1 graded task 6.4 **FAIL**: {#open-lead}

- **`#b-2` (BULLSHIT)** — "registry lists every file that monkeypatches an external boundary" is
  disproved by one grep: six files patch an external boundary with no row
  (`test_fork_safety_reexec.py`, `test_read_surface_grammar.py`, `test_reupsert_staleness.py`,
  `test_grep_stdin_dialect.py`, `test_learn_queue.py`, `test_session_raw_link.py`). Four were in
  the tree before the task closed. The ledger counted 89 test files calling `monkeypatch.setattr`
  against 55 registry names. The fix is the six rows plus a lint test that every
  monkeypatching test file is registered; a one-time sweep cannot satisfy "every file".
  {#open-b2}
- **`#s-2` (SKETCHY)** — no implementation summary, and no test or recorded mutation for the two
  new `verbs.py` log branches. This file is the summary. The second half, a test that asserts the
  `warning` fires on an answered-error `partition_list`, is still open. {#open-s2}

**Owner: W2-a**, the plan-6 remedy in [[plan-review-2026-10-14#t11-folded-waves]]: r1 `#b-1`,
`#b-2`, `#s-1`, `#s-3`, `#m-1..#m-5`, and todo G8. W2-a closes plan-6. Two of those items are also
listed in the W1-d sweep: plan-6 r1 `#m-4` (the `_log_event` docstring) and the bug-008 row's
"NOT verified live" (`#m-1`). {#open-owner}

## Not verified here {#not-verified}

- The three 2026-09-16 registry rows were read from `1f65b0d`'s message and the task spec's
  `#closing` note. This sweep did not re-check their classifications.
- The r1 ledger's six-file list and its 89/55 counts are quoted from the ledger. This sweep did not
  re-grep `tests/`, and the tree has moved since `e0b7df6`.
{#not-verified-body}
