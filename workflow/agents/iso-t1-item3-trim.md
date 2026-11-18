---
gmd: "0.1"
id: agent-brief-iso-t1-item3-trim
title: "Isolated agent brief: T1 step 1 follow-up — trim item 3's source-text lines"
tags: [agent-brief, isolated, t1, test-hygiene]
metadata:
  node_type: brief
  created: 2026-11-18
---

# T1 step 1 follow-up: trim item 3's source-text lines {#root}

You are an isolated small-fix agent (L174/L176) in your own clone. Read `CLAUDE.md`
`#test-discipline` (rules 4 and 5) first.

rel: implements -> [[plan-of-plans#queue]]

## The edit {#edit}

`tests/test_plan4_remedy_r2.py::test_foreground_start_refuses_a_busy_daemon_without_reaping_it` is a
real behaviour test (a silent, busy daemon: `refuse_unsupervised_start` raises `busy` within 4 s, does
not reap it, leaves the socket) whose LAST three lines read `src/` text
(`source_of(dm, "serve_foreground")` or similar). Remove only those source-text lines, and any import
or helper that becomes unused in this file because of it (`inspect`, `source_of`), nothing else. Keep
every behaviour assertion. If the source-text lines guard a stated rule that no behaviour assertion
covers, stop and say which rule in REPORT.md instead of deleting them.

## Verify {#verify}

`PYTHONPATH=src ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider tests/test_plan4_remedy_r2.py
2>&1 | tee ../item3.log`, before and after: the same collected count, all passing. Any background wait
you start has a deadline. One commit: `T1 step 1 follow-up: item 3 keeps its behaviour, drops its
source-text lines`.

## Report {#report}

In the REPORT.md the prompt names: the commit sha, the removed lines (quoted), the before/after counts.
