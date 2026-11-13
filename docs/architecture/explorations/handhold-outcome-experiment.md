---
gmd: "0.1"
id: exploration-handhold-outcome-experiment
title: "Exploration: does refmatrix reduce the backtrack-to-rebuild-understanding tax? An outcome experiment, injection on vs off"
tags: [exploration, charter, recall, scan-prompt, telemetry, experiment, plan-21]
metadata:
  node_type: exploration
  status: proposed
  created: 2026-11-13
---

# Exploration: an outcome experiment for refmatrix's handholds {#root}

**Date:** 2026-11-13
**Status:** Proposed. Runs after the user's decision on task 21.5; nothing is built yet.
**Motivation:** The user, 2026-11-13, after the 21.5 measurements: asked: does phase 1 debunk the premise?. The answer was no: the
measurements refute one delivery mechanism (ambient push injection) and one measurement method
(attribution by term or clique overlap), not the charter. The user: asked for the exploration. This
document designs the experiment that COULD confirm or refute the premise.

rel: related-to -> [[project_refmatrix_mission_charter]]

rel: derives-from -> [[measurement-task-21.5-r12-pilot-2026-11-13]]
rel: derives-from -> [[measurement-task-21.5-term-clique-2026-11-13]]
rel: derives-from -> [[measurement-task-21.5-relation-gaps-2026-11-13]]
rel: derives-from -> [[measurement-task-21.5-usage-weight-2026-11-13]]
rel: related-to -> [[task-21.5-tool-used-signal]]
rel: related-to -> [[exploration-session-phased-context]]
rel: related-to -> [[plan-25-cliquedb-field-report]]

## The question, in one sentence {#question}

Do refmatrix's handholds make an agent spend less effort re-deriving understanding a prior session
already held, and which handholds carry that effect: the ones pushed at it on every prompt, or the
ones it pulls?

This is the charter's claim ([[project_refmatrix_mission_charter]]: "kill the
backtrack-to-rebuild-understanding tax"). Attribution (did a tool call touch a delivered item) is
not the claim; it is one weak proxy for it. {#question-note}

## What the 21.5 measurements established (2026-11-13) {#evidence}

- **Push injection is mostly unused.** R12 pilot: of `scan_prompt` headline pairs, 8 of 113
  CAUSED+INFORMED (0.07); 90% of headline credits are touches the agent would have made anyway, or
  coincidences ([[measurement-task-21.5-r12-pilot-2026-11-13#verdict]]). `scan_prompt` is most of
  the ~8,000 delivered units in three weeks.
- **Pulled and boundary handholds look better, on tiny samples:** prompt_recall 2/4, context 1/3,
  session_start 1/1 CAUSED+INFORMED ([[measurement-task-21.5-r12-pilot-2026-11-13#breakdowns]]).
- **Topical overlap is not use.** Term and clique overlap (three clique sources) add nothing over
  the control after stratification ([[measurement-task-21.5-term-clique-2026-11-13#not-signal]]).
  (The first placebo design was biased toward the placebo; corrected by ch-bsd, real work scores
  above the placebo, so the placebo is no longer cited as evidence.)
- **Typed structure predicts relevance; vocabulary does not.** Code-structure 2-hop paths beat
  chance 2-3×; co-mention reach sits at chance
  ([[measurement-task-21.5-relation-gaps-2026-11-13#shortlist]]). About two thirds of GMD `rel:`
  edges bind a same-named path-less concept instead of the doc they cite (bug-216), so the
  GMD-provenance combos measured co-citation and are re-measured after that fix
  ([[measurement-task-21.5-relation-gaps-2026-11-13#gmd-gap-correction]]).
- **Not measured at all:** cross-session continuity (save-state / recall-state / focus), behaviour
  a feedback memory changes without being named, and any outcome (time, tokens, re-derivation,
  repeated mistakes).

## Design {#design}

### Arms {#arms}

| arm | push (scan_prompt, prompt_recall per prompt) | boundary (SessionStart, recall-state, PreCompact) | pull (MCP / CLI context, memory get) |
|---|---|---|---|
| A: full (today) | on | on | on |
| B: no push | off | on | on |
| C: bare | off | off | pull tools available, no primer, no hooks |

A vs B tests ambient injection. B vs C tests the handholds the charter names. A full off-switch
for push already exists in the hook layer's budget gates; arm C needs a hook-less settings
profile, never hand-edited (generated, per [[constitution#no-workarounds]] and the hook rules).
{#arms-note}

### Units and assignment {#assignment}

- **Session-level randomisation for a fixed period** (user decision, Q-4: randomised, not opt-in)
  across real work sessions in refmatrix and cliquedb (Q-5), arm drawn at SessionStart and
  recorded in the session's telemetry, so the comparison is within the same projects and weeks.
- **Paired re-entry tasks** as a second, controlled leg: a task that a prior session left
  mid-flight (a real handoff), resumed after `/clear` under each arm by fresh agents on isolated
  clones. Same task, same starting commit, different arm. This isolates continuity, which
  session-level randomisation dilutes.

### Outcome measures (pre-registered before any run) {#outcomes}

Each is a proxy for the backtrack-to-rebuild tax, read from transcripts and telemetry:

1. **Orientation cost:** tool calls, tokens and wall time from a session (re)start — a new session
   or a `/clear`, one measure with two triggers (user decision, Q-3: both are relevant) — to the
   first productive edit or the first correct statement of the resume point.
2. **Exploratory churn:** Read / Grep / Glob / `rmx grep` calls that touch a file and are not
   followed by an edit or a citation of that file within W prompts.
3. **Re-derivation:** facts a memory or handoff already held that the agent re-establishes by
   search (labelled on a sample: a fact present in a memory body, re-found by tool calls).
4. **Repeated mistakes:** violations of a feedback memory's rule (labelled: the rule existed and
   applied, and the agent broke it), per 100 prompts.
5. **Cost of the handholds themselves:** injected bytes per prompt, hook latency, and the share of
   hook output budget consumed (plan-25's byte budget).

Primary outcome: (1) on the paired re-entry leg. Secondary: (2)-(4) on the session leg; (5) is a
baseline, not a gate ([[feedback_measurable_benefit_is_not_the_reason]]).

### Labels and blinding {#labels}

Outcomes (3) and (4) need judgement. Labellers see a transcript excerpt with the arm and every
injected block removed, use one rubric, and a second rater labels 20% for agreement (the R12 pilot
had one rater and one uneven call).

### Bands, written before the run {#bands}

| result on the primary outcome (B or A vs C) | reading | action |
|---|---|---|
| handholds cut orientation cost ≥ 30% | premise holds | keep; tune what to push |
| 10-30% | premise holds weakly | keep boundary + pull; review push |
| < 10% or C better | premise in trouble for this kind of work | re-examine the charter's mechanisms with the user |

And for push (A vs B): if A is not better than B on any outcome while costing (5), the
recommendation is to shrink ambient injection to a gated or pointer-only form (25.1's d3 already
moved prompt_recall to pointers).

## Constraints {#constraints}

- Real sessions are the user's work: an arm must never block work. Arm C is opt-in per session
  and the user can flip it.
- Clone-based paired runs follow the littlebig isolation rule
  ([[feedback_isolate_work_in_littlebig_clones]]); no live store writes from experiment agents.
- Raw prompts and transcripts stay local; committed results are counts and labels
  ([[feedback_no_raw_prompts_in_public_repo]]).
- Sample size: write the minimum detectable effect for the paired leg before running (paired
  tasks are expensive; 10-20 pairs per arm is the likely ceiling).

## Decisions (user, 2026-11-13) {#open}

Asked as Q-3 to Q-5 in [[open-questions]]: the primary outcome is orientation cost at a session
(re)start, new session and `/clear` alike; real sessions are randomised into arms for a fixed
period; the projects are refmatrix and cliquedb.

## Sequence {#sequence}

After the user's decision on 21.5 (ch-bsd over the four 21.5 measurements first). bug-216's fix
should land before arm A's baseline is taken, so the graph the handholds draw from is the one
authors wrote.
