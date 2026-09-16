---
gmd: "0.1"
id: task-12.6-cli-startup-gap
title: "Task 12.6: give the 8.5 s a name"
tags: [task, plan-12, performance, measurement]
metadata:
  node_type: task
  status: pending
  plan: plan-12-open-bug-remediation
---

# Task 12.6: give the 8.5 s a name {#root}

> Plan: [[plan-12-open-bug-remediation]]
> Status: Pending
> Bug: bug-033
> Depends on: [[task-12.5-pyc-invalidation]]

rel: part-of -> [[plan-12-open-bug-remediation]]
rel: derives-from -> [[feedback_causal_story_before_evidence]]

## Requirements {#requirements}

- bug-033: `build_context` warm is 0.45 s on the LongMemEval store, of which BM25 over 406,885
  concepts plus the graph walk is 0.37 s. The full daemonless `rmx context` CLI is 9.0 s. The
  ~8.5 s between them is UNATTRIBUTED, and only 2.8 s of it is CPU — which means most of it is
  waiting, not computing.
- This task MEASURES. It does not fix, and it does not propose a mechanism before it has one
  ([[feedback_causal_story_before_evidence]] — the 62.9 s retraction is the cost of getting that
  order wrong).
- Three cuts, in this order:
  1. `python -X importtime -m refmatrix.cli context <q>` — import cost, cumulative, top 20.
  2. Wall-clock splits inside the CLI path: process start -> click dispatch -> store bind ->
     replica open -> `build_context` entry -> return -> render -> exit. Instrumented behind
     `RMX_TIME_PHASES=1` so the splits are reproducible by anyone, not a one-off script.
  3. The same three on a SMALL store, to separate "cost of this store" from "cost of starting up".
- Each measurement is taken twice, minutes apart, on a quiet fleet AND under ordinary load, because
  a single quiet-window number is how bug-031 became a retraction.
- Output: `workflow/measurements/cli-startup-gap-0916.md` with the splits and an attribution that
  says which component owns which seconds — or says plainly that it does not yet know and what the
  next cut would be.
- The registry row is updated with the attribution. Whether bug-033 closes depends on what the
  numbers say; a fix, if one is warranted, gets its own task.

## Files to Create / Modify {#files}

- modify `src/refmatrix/cli.py` (`RMX_TIME_PHASES` splits on the context path)
- create `workflow/measurements/cli-startup-gap-0916.md`
- modify `workflow/bug_registry.md` (bug-033 attribution)

## Test Strategy (RED first) {#test-strategy}

- `tests/test_cli_time_phases.py`: with `RMX_TIME_PHASES=1` the phase splits are emitted to stderr
  (never stdout — stdout is the hook payload and a stray line corrupts an injection), every phase
  name appears exactly once, and the splits sum to within 5% of the measured total.
- With the env unset, NOTHING is emitted and the byte count on stdout is unchanged (asserted, since
  plan-9 counts those bytes).
- mutation check: dropping one phase marker turns the "every phase appears" test RED.

## Definition of done {#done}

- RED run recorded, GREEN run recorded.
- The measurement file exists, with both quiet and loaded runs.
- `workflow/implementation_summaries/task-12.6-cli-startup-gap.md`.
- Branch `task-12.6-cli-startup-gap`, merged `--no-ff` to `master`.
