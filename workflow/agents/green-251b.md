---
gmd: "0.1"
id: agent-brief-green-251b
title: "Brief: green-251b — resume task 25.1 GREEN from the uncommitted clone (ch-implementer)"
tags: [agent-brief, dispatch]
---

# Brief: green-251b — resume task 25.1 GREEN {#root}

You resume the task 25.1 GREEN that `green-251` left uncommitted. Everything in
`workflow/agents/green-251.md` applies (where, read-first, lead decisions a3/a4/a5/a12/a13,
merge-conflict hygiene, hard rules, verify, deliverables, Amendments 1 and 2). Read it in full
first, in the dev repo: `/Users/tholley/claude_tools/refmatrix/workflow/agents/green-251.md`.

rel: amends -> [[agent-brief-green-251]]

## State at resume (2026-11-13) {#state}

- Clone `/Volumes/littlebig/refmatrix-plan25-1`, branch `task-25.1-recall-hook-byte-budget`, tip
  `45d8abf`. The GREEN is UNCOMMITTED in the working tree: modified `.claude/settings.json`,
  `src/refmatrix/{cli,handoff,hooks,mcp,recall,scan,verbs}.py`; new
  `src/refmatrix/hook_budget.py`, `src/refmatrix/recall_pack.py` (+975/-523). INSPECT IT FIRST —
  it is the work; do not discard or rewrite it wholesale.
- Its full-suite run finished: `workflow/review-output/plan25/25.1-green-full-wip.log` —
  **41 failed, 4360 passed**. 7 are in `tests/test_task25_1_recall_budget.py` (AC-5, expected
  until 26.4 merges, plus the six of Amendment 2). About 34 are elsewhere, clustered in
  `test_task21_1_used_events.py` (9), `test_task21_1_recall_skip.py` (3),
  `test_task21_1_emitters.py` (2), `test_task21_1_agent_usage_report.py` (2), `test_plan2_remedy_r6/r7`,
  `test_rerank_*`, `test_docs_generated`, `test_bigop_nonblocking`, `test_task3_7_remedy_*`.

## What to do {#do}

1. Triage the ~34 non-25.1 failures by E LINE against the 0.82.0 release run
   `/Users/tholley/claude_tools/refmatrix/workflow/review-output/release-0.82.0-full.log`
   (known there: bug-127/168, bug-168 x9, bug-170, bug-196 x2). Every failure that is new is
   either a regression in the GREEN (fix it in `src/`) or a test whose contract the 25.1 spec
   changed (e.g. `prompt_recall` became pointer-only by rule d3 — 21.1's used/emitter tests may
   read the old payload). Do NOT edit tests: list each contract-change case with the spec line
   that changes it, for the lead and the test engineer. `test_docs_generated` failures mean the
   generated docs need regenerating with the clone's interpreter.
2. Re-run the RED files and the family; then commit the GREEN by pathspec.
3. Finish the remaining deliverables of green-251: AC-14 / AC-4 (i) / AC-15 mutations
   (Amendment 1 map), `workflow/measurements/plan-25-hook-bytes.md`, the a12 bare
   `rmx recall-state` probe (throwaway store), `#green` with Amendment 2's six measured.
4. Full suite once more at the end, log `25.1-green-full.log`; report by E line.

## Deliverables {#deliverables}

As green-251, plus the triage table: test, E line, pre-existing / regression-fixed /
contract-change (spec line).
