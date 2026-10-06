---
gmd: "0.1"
id: plan-14-grep-learning-measurement
title: "Does funnelling grep through rmx actually teach the graph anything? Instrument it, give it an off switch, and replay the corpus against both arms"
tags: [plan, grep, learning, telemetry, measurement, instrumentation]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-10-05
  revised: 2026-10-05
---

# Plan 14: measure the grep→rmx learning loop {#root}

**Date:** 2026-10-05
**Status:** In progress — 14.1/14.2/14.3 complete; 14.4's replay running. bug-067 was found BY the instrument and fixed before the measurement was taken (`[[impl-plan-14-grep-learning-instrumentation]]`).
**Location:** `workflow/plans/plan-14-grep-learning-measurement.md` — permanent home; stage is
`metadata.status`.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[project_grep_learn_wall_and_queue]]
rel: derives-from -> [[project_grep_surface_defect_family]]
rel: related-to -> [[plan-9-context-cost-telemetry]]
rel: related-to -> [[feedback_measure_the_outcome_not_the_wall]]
rel: related-to -> [[feedback_causal_story_before_evidence]]

## Why this plan exists {#why}

Every bare `grep` on this machine is rewritten to `rmx grep`, and every `rmx grep` that falls to
the tool floor teaches the graph a `query/PATTERN` concept. That loop has been writing for weeks:
**~1,621 learned `query/*` concepts** in this project's store and **46,837 `learned from grep`
events** in `facts.log`. Its COST is measured and bounded — the 30 s wall
([[project_grep_learn_wall_and_queue]]), `LEARN_DRAIN_BUDGET_S`, `LEARN_BROKER_TIMEOUT_S`, a
capped queue. Its BENEFIT has never been measured at all. {#lead}

The gap is instrumental, not analytical. `query.log`'s grep rows carry
`kind/body/source/invocation/cardinality/latency_ms/outcome/error`, and `source` is
`grep-replica` for all 1,536 of them. **Nothing in the record says whether the index answered the
call or the tool floor did** — which is precisely the quantity learning claims to move. 35
learn-path tests exist and every one of them tests the mechanism (the queue is bounded, coalescing,
non-lossy, marks hits protected); none asserts that a later lookup got better. {#gap}

An observational pass over `query.log` (2026-10-05) found 25.3% of grep calls repeat an earlier
pattern, and repeated patterns' later calls run at a 86 ms median against a 171 ms first-call
median. **That number is not evidence for learning** and this plan does not treat it as such: the
page cache, replica warmth and differing flags all confound it, and 67 of 121 repeated patterns
returned a different cardinality between calls, so the corpus moved too. It is recorded here only
as the reason to build an instrument instead of arguing from the log we have.
rel: reinforces -> [[feedback_causal_story_before_evidence]] {#not-evidence}

## The finding that shapes the instrument {#eligibility}

`_index_may_answer(paths)` in `src/refmatrix/cli.py` is `return not paths`. So the learned index
answers **exploration only** (`rmx grep PATTERN`), and a drop-in read that names files
(`grep PAT file.py`) can never be served from it — by design, because grep's contract is to read
the corpus it was handed (bug-058: a learned index served 1000 rows covering ~100 of a file's 500
matching lines). {#eligibility-fact}

Therefore a two-valued `index | floor` field would be a **misleading instrument**: it would score
every drop-in read as a learning miss and make the loop look dead where the tool floor is the
correct answer. The field must separate *the index was consulted and had nothing* from *the index
was never eligible*. This is the whole reason task 14.1 ships a five-valued taxonomy rather than a
boolean. {#eligibility-consequence}

A second consequence: **the existing 1,536 rows cannot be re-scored.** `body` holds the pattern and
nothing holds the paths, so eligibility is unrecoverable for historical rows. Pre-change history
can bound the repeat rate and nothing else; the answer has to come from forward data and from the
replay in task 14.4. {#no-backfill}

## Decisions {#decisions}

| Q | Decision | Why |
|---|----------|-----|
| Q1 | `answered_by` is five-valued: `index`, `floor`, `dropin`, `stdin`, `none` | see [[#eligibility]] — a boolean scores a correct drop-in read as a learning miss |
| Q2 | The toggle is a **marker file + env override**, not a store/config key | a bash rewrite hook and a CLI with a dead daemon must both read it with no store access and no Python import |
| Q3 | Toggle OFF ⇒ the rewrite hook passes bare `grep` **straight through**, and no site learns | user decision 2026-10-05: measure the WHOLE funnel (routing + learning), not learning alone |
| Q4 | The A/B replays against **two throwaway stores under a short `mkdtemp()` root**, never the live store | CLAUDE.md#development-commands — a dev-venv `rmx` against the live store trips the hub version handshake |
| Q5 | Grep rows also carry `learn` (the EFFECTIVE toggle state) | without it a replayed log cannot say which arm wrote a row; the arm must be readable from the record itself |

## Tasks {#tasks}

| # | Task | Spec |
|---|------|------|
| 14.1 | `answered_by` + `learn` on every grep telemetry row | `plan-14-grep-learning-measurement-tasks/task-14.1-answered-by-telemetry.md` |
| 14.2 | One learning toggle, honoured by every learn site | `plan-14-grep-learning-measurement-tasks/task-14.2-learning-toggle.md` |
| 14.3 | The rewrite hook and the wrapper follow the toggle | `plan-14-grep-learning-measurement-tasks/task-14.3-hook-follows-toggle.md` |
| 14.4 | Replay both arms; report what learning bought | `plan-14-grep-learning-measurement-tasks/task-14.4-replay-measurement.md` |

rel: specifies -> [[task-14.1-answered-by-telemetry]]
rel: specifies -> [[task-14.2-learning-toggle]]
rel: specifies -> [[task-14.3-hook-follows-toggle]]
rel: specifies -> [[task-14.4-replay-measurement]]

## What would make this plan a negative result {#negative}

Pre-registered, so the threshold cannot move after the number is in
([[feedback_causal_story_before_evidence]]): if the replay shows the learned index answering
**under 5% of eligible exploration calls**, or answering them with rows whose hit@1 against the
real-tool control is no better than the floor's, then the loop is not paying for itself and that
ships as the finding — with the cost already measured — rather than as a lowered bar. A negative
result here is a result: it would make the case for retiring the teach on the read path and keeping
only ingest-time indexing. {#negative-criterion}

## Out of scope {#out-of-scope}

- bug-062/063/064 (the rg fallback's argv construction) and bug-066 (the hook invoking a stale
  wrapper copy). Task 14.3 touches the same two files as bug-066 and MUST NOT silently absorb it:
  that row needs a user decision on `RMX_REWRITE_MODE`, and this plan's hook change is additive.
- Any change to what the learn path WRITES. This plan instruments and gates the loop; it does not
  retune it. A retune is only honest after 14.4 reports.
