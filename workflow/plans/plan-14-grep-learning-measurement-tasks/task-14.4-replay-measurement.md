---
gmd: "0.1"
id: task-14.4-replay-measurement
title: "Task 14.4: replay the corpus against both arms and report what learning bought"
tags: [task, measurement, eval, grep, learning]
metadata:
  node_type: task
  status: in-progress
  created: 2026-10-05
---

# Task 14.4: the replay, and the number it produces {#root}

> Plan: [plan-14-grep-learning-measurement](../plan-14-grep-learning-measurement.md)
> Status: In Progress
> Depends on: Task 14.1, Task 14.2

rel: part-of -> [[plan-14-grep-learning-measurement]]
rel: depends-on -> [[task-14.1-answered-by-telemetry]]
rel: depends-on -> [[task-14.2-learning-toggle]]

## Requirements {#requirements}

Replay this project's real grep history against two stores built identically from one corpus
snapshot, differing only in the toggle, and report what the learning loop bought. {#req-lead}

- **Corpus**: the project tree, ingested through the PRODUCTION path (`rmx ingest`), not a bespoke
  loader — the benchmark path IS the production path
  (`.claude/PROJECT_PROFILE.md#constraints`, [[feedback_measure_the_path_users_run]]).
- **Workload**: the `kind="grep"` rows of `.refmatrix/query.log`, in timestamp order, patterns
  replayed as the exploration calls they were (1,148 unique of 1,536 as of 2026-10-05). Order is
  load-bearing: learning is sequential, so a shuffled replay measures a different system.
- **Arms**: arm A toggle ON, arm B toggle OFF, two stores under a SHORT `mkdtemp()` root (macOS
  `sun_path` ≈ 104 bytes), each with its own daemon. **Never the live store**
  (CLAUDE.md#development-commands).
- **Primary outcome**: the `answered_by` distribution per arm over *eligible* calls — `index` vs
  `floor`. Arm B's `index` count is the ingest-only baseline; the difference is what the read-path
  teach added, which is the quantity this whole plan exists to produce.
- **Secondary outcome**: retrieval quality on the learned rows. For each pattern the index answered
  in arm A, score its rows against a real-tool control (`rg`/`grep`) over the same corpus: does the
  learned answer contain what grep would have returned? A loop that answers from the index with
  WORSE rows has made retrieval worse, not better, and the primary number alone cannot see it.
- **Cost, restated not assumed**: total learn-queue depth, drain time, and bytes added to the
  catalog per arm. The cost side already has a measured history
  ([[project_grep_learn_wall_and_queue]]); the replay reports it again under its own conditions
  rather than citing the old number for new code
  ([[feedback_measure_the_outcome_not_the_wall]]).

## Acceptance criteria {#acceptance}

1. The harness lives in `eval/production/` and runs end to end from one command, capturing output
   to a log under `workflow/review-output/`.
2. Both arms are driven through the same code path; the ONLY difference is the toggle state, and the
   report asserts that from the `learn` field of the rows each arm wrote (task 14.1 Q5), not from
   the harness's own bookkeeping.
3. The report states the `index`/`floor`/`dropin`/`stdin`/`none` counts per arm, over eligible calls
   and over all calls separately.
4. The secondary outcome is reported per pattern, with the real-tool control's row set alongside.
5. The pre-registered negative threshold from
   [[plan-14-grep-learning-measurement#negative-criterion]] is evaluated EXPLICITLY in the report —
   stated as met or not met, before any interpretation.
6. The live store is untouched: the report names the `mkdtemp()` roots used, and
   `rmx daemon status` on the live store shows the same pid before and after.

## Files to create {#files-to-create}

| File | Purpose |
|------|---------|
| `eval/production/grep_learning_replay.py` | the two-arm replay harness |
| `docs/measurements/grep-learning-replay.md` | the report (GMD, with the threshold verdict) |

## Implementation notes {#implementation-notes}

Replay the patterns as EXPLORATION calls (no paths), because that is the only shape the index is
eligible to answer ([[plan-14-grep-learning-measurement#eligibility]]). Historical rows cannot tell
us which original calls named paths, so the replay does not pretend to reproduce the original mix —
the report must SAY that it measures the eligible subset, and that the eligible share of live
traffic is a forward measurement that only the shipped `answered_by` field can supply. {#eligible-only}

The `dropin` and `stdin` buckets should therefore be ~0 in the replay. If they are not, the harness
is constructing calls it did not intend to, and that is a harness bug, not a finding. {#sanity}

Learning is asynchronous: the broker enqueues and the DAEMON drains on its tick. A replay that
fires N patterns and reads the result immediately measures the queue, not the graph. Each arm must
drain to empty (bounded, and the drain's own report checked) before the index is scored.
rel: derives-from -> [[project_grep_learn_wall_and_queue]] {#drain-first}

## Test strategy {#test-strategy}

The harness gets a smoke test with a handful of synthetic patterns against a tiny corpus, asserting
that arm A ends with more learned `query/*` concepts than arm B and that arm B has exactly zero —
the floor case that proves the toggle actually gated the write. The REPORT's numbers are a
measurement, not a test, and are not asserted in the suite. {#tests}
