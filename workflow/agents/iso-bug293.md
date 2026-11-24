---
gmd: "0.1"
id: agent-brief-iso-bug293
title: "Isolated agent brief: bug-293 — the rerank-budget stub server's reply thread handles a client hang-up"
tags: [agent-brief, isolated, bug-293, tests]
metadata:
  node_type: brief
  created: 2026-11-23
---

# bug-293: the stub server's reply thread handles a hang-up {#root}

You are an isolated small-fix agent (L174/L176) in your own clone: one agent writes the test and
the fix, test seen failing first. Read `CLAUDE.md` `#test-discipline` and bug-293's row in
`workflow/bug_registry.md`.

rel: implements -> [[bug_registry]]

## The bug {#bug}

`tests/test_rerank_budget_real_clients.py`: the stub models server's per-connection thread
`one()` (around line 433) catches failures of `recv_frame` but not of `send_frame`. When the
client under test gives up on its budget and closes the socket while the stub sleeps
`_info_delay`, the reply write raises `BrokenPipeError` in a daemon thread, which pytest reports
only as `PytestUnhandledThreadExceptionWarning` during
`test_a_header_that_eats_the_budget_sends_no_rerank`. Test-side only. {#bug-body}

## Do {#do}

1. RED: make the hang-up observable. Have the stub record a client hang-up (e.g. a `hangups`
   counter it bumps when `send_frame` raises `OSError`), and assert in
   `test_a_header_that_eats_the_budget_sends_no_rerank` that the budget path closed the
   connection (hangups >= 1). Also make the file fail on an unhandled thread exception (e.g.
   `pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")` on that
   test). Run it: it must FAIL at base for the intended reason; keep the E line.
2. GREEN: `one()` treats an `OSError` from `send_frame` as the client hanging up: count it and
   return. No `except: pass`.
3. Run `tests/test_rerank_budget_real_clients.py tests/test_wallclock_census.py
   tests/test_budget_outcome_census.py tests/test_suite_discipline.py` with
   `PYTHONPATH=src ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee ../bug293.log`,
   all green. Any background wait has a deadline.
4. Update bug-293's row: fix text and status `fixed` (cite your commit in a second commit).

## Report {#report}

In the REPORT.md the prompt names: commit shas, the RED E line, the GREEN counts.
