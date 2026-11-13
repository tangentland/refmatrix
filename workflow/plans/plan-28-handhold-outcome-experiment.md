---
gmd: "0.1"
id: plan-28-handhold-outcome-experiment
title: "Plan 28: the handhold outcome experiment: do refmatrix's handholds cut the backtrack-to-rebuild-understanding tax, and which ones (push, boundary, pull)? Randomised real sessions plus paired re-entry runs, with 10.2's dedupe A/B nested"
tags: [plan, experiment, charter, recall, scan-prompt, telemetry, handhold, plan-21, plan-10]
metadata:
  node_type: plan
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
---

# Plan 28: the handhold outcome experiment {#root}

**Date:** 2026-11-13
**Status:** Drafting (spec wave 2026-11-13, G17). Written from
[[exploration-handhold-outcome-experiment]] and the plan review's decisions. Not approved: the
lead sets `approved` after a clean ch-bsd round (the d9co route, [[plan-review-2026-11-13#goal-horizon]]).
**Location:** `workflow/plans/plan-28-handhold-outcome-experiment.md`; tasks in
`workflow/plans/plan-28-handhold-outcome-experiment-tasks/`.
**Queue:** item 7 of [[plan-review-2026-11-13#queue]]. The m1 confirm (L36) and 21.5 phase M come
first. The experiment then runs at least 14 days in the background while items 8-11 build. **The goal
stops** at its charter decision (G18).
**Depends on:** bug-216 live; 10.2 built (its `arms.py` and the dedupe it nests, L20); 21.5
phase M reported (D-Q4); the m1 r2-lite confirm CLEAN or MEH-only (G32, L36).

rel: derives-from -> [[exploration-handhold-outcome-experiment]]
rel: derives-from -> [[plan-review-2026-11-13#d-q4]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: depends-on -> [[open-questions]]
rel: depends-on -> [[task-10.2-plan-10-injection-dedup]]
rel: depends-on -> [[task-21.5-tool-used-signal#r14]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph]]
rel: depends-on -> [[constitution]]
rel: related-to -> [[project_refmatrix_mission_charter]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache#ranges]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: reinforces -> [[feedback_measurable_benefit_is_not_the_reason]]
rel: reinforces -> [[feedback_isolate_work_in_littlebig_clones]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]
rel: specifies -> [[task-28.1-session-arms-and-push-switch]]
rel: specifies -> [[task-28.2-paired-reentry-runner]]
rel: specifies -> [[task-28.3-outcome-scorer]]
rel: specifies -> [[task-28.4-preregistration-freeze]]
rel: specifies -> [[task-28.5-run-and-report]]

## Context {#context}

### The question {#question}

Do refmatrix's handholds make an agent spend less effort re-deriving understanding that a prior
session already held, and which handholds carry the effect: the ones pushed at it on every
prompt, or the ones it pulls? This is the charter's claim ("kill the
backtrack-to-rebuild-understanding tax"). Attribution, meaning whether a tool call touched a
delivered item, is one weak proxy for it, and the R12 pilot found that proxy measured proximity, not use
([[measurement-task-21.5-r12-pilot-2026-11-13#verdict]]). {#question-body}

### What is already decided {#decided}

| source | decision | where it lands |
|---|---|---|
| Q3 (user, 2026-11-13) | the primary outcome is orientation cost at a session (re)start, one measure with two triggers: a new session and `/clear` | [[#legs]], [[#outcomes]] |
| Q4 (user) | real sessions are randomised into arms for a fixed period, not opt-in | [[#legs]] |
| Q5 (user) | the projects are refmatrix and cliquedb | [[#legs]] |
| D-Q4 (user) | 21.5 decision → this experiment; no 21.5 build until it reports | [[#ordering]] |
| L20 (lead, CB-12, CB-15) | Q3 folded fully: a new-session trigger on the paired leg. Arm B's push-off switch is specified by extending `arms.SESSION_ARMS`, and the "switch already exists" premise is struck. 10.2's A/B is nested: arm A splits into `A+dedupe` / `A+full`, so 10.2 is built before the start and its ≥ 14-day A/B IS this run | [[#arms]], [[task-28.1-session-arms-and-push-switch]] |
| L18, L27 (lead, CB-9) | "used" counts only R12 explicit uses + `cited_in_answer`, never 21.5's unbuilt legs | [[#outcomes]], [[task-28.3-outcome-scorer]] |
| L36 (lead) | the m1 r2-lite confirm runs before this plan draws its bands | [[task-28.4-preregistration-freeze]] |
| L45 (lead) | the start is user-gated: it randomises live sessions for ≥ 14 days in refmatrix and cliquedb | [[task-28.5-run-and-report]] |
| G18 | the charter decision on the result is the user's; the goal stops there | [[task-28.5-run-and-report]] |
{#decided-table}

## Design {#design}

### Arms and cells {#arms}

| cell | push (per-prompt `scan_prompt`, `prompt_recall`) | boundary (SessionStart, recall-state, PreCompact) | pull (CLI / MCP context, memory get, recall) | where |
|---|---|---|---|---|
| `A+dedupe` | on, 10.2's names-only dedupe | on | on | session leg (drawn); paired leg |
| `A+full` | on, no dedupe (10.2's `full`) | on | on | session leg (drawn) |
| `B` | **off** ([[task-28.1-session-arms-and-push-switch#r3]]) | on | on | session leg (drawn); paired leg |
| `C` | off | off: no rmx hook, no primer | tools available | paired leg only; never drawn |

A vs B tests ambient push. B vs C tests the handholds the charter names (boundary + pull).
`A+dedupe` vs `A+full` is 10.2 R7's A/B, nested. **No push-off switch existed before this plan.**
The exploration's "a full off-switch for push already exists in the hook layer's budget gates" is
struck: no such switch is in `hooks.py` or `scan.py`, and 25.1 R8 says the pack is "never empty"
(contra-b CB-15). Arm B's switch is built by 28.1 on 10.2's `arms` table. Arm C is a
hook-less settings profile generated by the runner, never hand-edited (28.2). {#arms-note}

### Two legs {#legs}

- **Session leg.** Real work sessions in refmatrix and cliquedb, randomised at SessionStart into
  `A+dedupe`, `A+full` or `B` by `arms.draw` (a pure function of the session id, the period salt
  and the store; [[task-28.1-session-arms-and-push-switch#r2]]). The period lasts at least 14 days
  and at least 40 sessions per cell per store, whichever is later (10.2 R7's minimum). It measures
  outcomes (2)-(5), the `used` outcome, and 10.2's nested outcomes. The cell is recorded on the
  session's telemetry, so arms are compared within the same projects and weeks.
- **Paired re-entry leg.** Each paired task is a real handoff that a prior session left
  mid-flight. Fresh agents resume it on isolated littlebig clones at the same starting commit,
  under each paired cell (`A+dedupe`, `B`, `C`) and each trigger, a **new session** and **after
  `/clear`** (Q3, folded fully per L20). It measures outcome (1), the primary. This leg isolates
  continuity, which session-level randomisation dilutes. Fresh agents see only the memories and
  handoffs that existed at the task's start, so no later knowledge leaks in
  ([[task-28.2-paired-reentry-runner#r3]]).
{#legs-body}

### Outcomes {#outcomes}

Each outcome is a proxy for the backtrack-to-rebuild tax, read from transcripts and telemetry
by ONE scorer ([[task-28.3-outcome-scorer]]):

1. **Orientation cost (primary, paired leg, both triggers pooled):** tool calls, tokens and wall
   time from the (re)start to the first productive edit or the first correct statement of the
   resume point. P-3 settles which of the three is the banded scalar.
2. **Exploratory churn (session leg):** Read / Grep / Glob / `rmx grep` calls that touch a
   project file and are not followed within W prompts by an edit or a citation of that file, per
   100 prompts (W per P-4).
3. **Re-derivation (session leg, labelled):** facts that a memory or handoff already held and the
   agent re-establishes by search, per 100 prompts.
4. **Repeated mistakes (session leg, labelled):** violations of a feedback memory's rule that
   existed and applied, per 100 prompts.
5. **Cost of the handholds (both legs):** injected bytes per prompt, hook latency, and the share
   of the hook output budget. This is a baseline, not a gate
   ([[feedback_measurable_benefit_is_not_the_reason]]).
6. **Used (session leg; L18, L27):** R12 explicit uses plus `cited_in_answer` per 100 human
   prompts, with names-line items apart. 21.5's tool legs are never counted. The precision
   check on `cited_in_answer` is P-5.
7. **10.2's nested outcomes:** injected bytes per human prompt, and used per 100 human prompts
   under rule 6, split by 10.4's `prompt_family`. 10.2 R7 owns their bands, and this plan reads
   them.
{#outcomes-list}

### Bands (frozen in 28.4 before the start) {#bands}

The primary reading compares the handhold cell named by P-2 against `C` on outcome (1):

| result on the primary outcome | reading | action, for the user's charter decision |
|---|---|---|
| handholds cut orientation cost ≥ 30% | premise holds | keep; tune what to push |
| 10-30% | premise holds weakly | keep boundary + pull; review push |
| < 10%, or C better | premise in trouble for this kind of work | re-examine the charter's mechanisms with the user |

How the CI enters a reading is P-8. **Push (A vs B, session leg):** if A is not better than B
on any of outcomes (2)-(4) and (6) while costing (5), the recommendation is to shrink ambient
injection to a gated or pointer-only form. **Nested (10.2 R7):** 10.2's own bands (dedupe cuts
bytes per human prompt ≥ 30% with used within −5% of `full` → keep; …), read on outcome 7.
{#bands-body}

### Inputs to the charter decision that are not outcomes {#charter-inputs}

21.5 phase M's band reading ([[task-21.5-tool-used-signal#r14-bands]]) and the `denotes`
evaluation's reading ([[task-bug216-denotes-fold-evaluation#r4]]), if that has run, are handed to the user
beside this plan's result. They are recorded; nothing here reads them as a band. {#charter-inputs-body}

## Ordering and gates {#ordering}

1. 28.1, 28.2 and 28.3 build after 10.2 is merged (queue item 6). 28.1 extends 10.2's `arms.py`.
2. 28.4 freezes the pre-registration after: bug-216 is live; 21.5 phase M has reported; the m1
   r2-lite confirm (G32) is CLEAN or MEH-only; 28.2's probe and calibration are recorded; and
   a ch-bsd round over the pre-registration is CLEAN or MEH-only.
3. **28.5 starts only on the user's go** (L45), with the period's salt and dates deployed.
4. **During the period:** items 8-11 build and deploy. A deploy that changes what any cell
   delivers pauses the period: one touching `scan.py`, `recall_pack.py`, `hook_budget.py`,
   context rendering, the hooks generator or `arms.py`. The pause is recorded, and the period
   extends by the paused days. Every deploy sha in the period is recorded with its date.
5. **At the end:** scoring, readings, the report and its ch-bsd round. Then the goal stops for
   the user's charter decision (G18). The T3 re-plan and the plan-24 re-plan (D-Q5) follow it.
{#ordering-body}

## Task list {#tasks}

| task | what | builds | depends on |
|---|---|---|---|
| [[task-28.1-session-arms-and-push-switch]] | the handhold cells in `arms.SESSION_ARMS`, a store-scoped draw, arm B's push-off switch, the per-prompt `session_arm` field | `src/` | 10.2 |
| [[task-28.2-paired-reentry-runner]] | R0 probe; the paired task set; the runner (clones, stores, memory snapshots, arm pinning, triggers, teardown); arm C's generated bare profile | `eval/production/handhold/` | 28.1 |
| [[task-28.3-outcome-scorer]] | the ONE scorer for outcomes 1-7, blinding, label samplers, `cited_in_answer` | `eval/production/handhold/` | 28.1 |
| [[task-28.4-preregistration-freeze]] | the calibration, the MDE, every P-item value, and the frozen pre-registration with its sha | measurement file | 28.1-28.3, G32, 21.5 phase M, bug-216 live |
| [[task-28.5-run-and-report]] | the user-gated start, the period, the paired runs, the readings, the report, the cleanup | measurement file | 28.4, the user's go |

## Acceptance for the plan {#acceptance}

- The run reaches its minimums, or its readings say report-only. Every band is read as frozen,
  and nothing is re-specified after an outcome is seen.
- Committed results are counts, labels and hashes only. Transcripts and prompts stay local.
- No experiment agent writes to a live store. Paired runs happen only in littlebig clones.
- The report is through ch-bsd, and the charter decision is put to the user with the readings.
- `arms.py` and arm B's branch are deleted after the period, per 10.2's deferral row, unless
  the charter decision keeps an arm.
{#acceptance-list}

## Cross-plan effects {#cross-plan}

- **10.2 R7 (amended by 28.1).** `arms.draw(session_id)` has no store scope, but the period
  covers two stores. 28.1 R2 adds the scope, and 10.2's outcome text is read under L27.
- **25.1 R8 (amended by 28.1).** "Never empty" holds wherever the pack runs. In cell `B` the pack
  is not called.
- **19.6 `cited_in_answer`.** 28.3 implements 19.6's clause once, and 19.6's `score_readback.py`
  imports it when 19.6 is unfrozen (one implementation).
{#cross-plan-body}

rel: amends -> [[task-10.2-plan-10-injection-dedup]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r8]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache#ranges]]

## Open for the lead (P-items, frozen by 28.4) {#open}

Choices no D-Q or L-row settles. The tasks are written to option (a), the recommendation, so
they are buildable; 28.4 freezes the final value.

1. **P-1 cell weights (session leg).** (a) equal thirds `A+dedupe` / `A+full` / `B`; (b) `B` one
   half and each A cell one quarter, which gives A vs B more power and 10.2 less. {#p-1}
2. **P-2 the primary comparison.** (a) `B` vs `C`, the charter's named handholds with no
   multiple-comparison inflation; (b) the better of `A+dedupe` and `B` against `C`. {#p-2}
3. **P-3 orientation cost's banded scalar.** (a) tool calls (tokens include injected bytes,
   which bias against A); (b) tokens; (c) wall time. {#p-3}
4. **P-4 churn window W.** (a) 3 prompts (21.5's plateau `k`); (b) 2. {#p-4}
5. **P-5 `cited_in_answer` precision.** (a) 50 cited pairs labelled with R12's rubric before its
   counts enter outcome 6; if the Wilson upper bound is below 0.50, outcome 6 is R12 explicit only
   and `cited_in_answer` is reported apart. It is whole-token matching in agent text, the same
   mechanism and prompt-echo confound that sank `bash_name`. (b) count it unchecked, as L18/L27
   say. {#p-5}
6. **P-6 the paired leg's A cell.** (a) `A+dedupe` only, the shipped default after 10.2; (b) both
   A cells, at 1.5× the runs. {#p-6}
7. **P-7 the curator status line in `B`.** (a) it stays on: it reports state and retrieves
   nothing; (b) off with the rest of the per-prompt output. {#p-7}
8. **P-8 the CI rule for a band.** (a) "holds" and "holds weakly" need the effect's 95% CI to
   exclude 0, otherwise the reading is the third row; (b) the point estimate alone. {#p-8}
9. **P-9 label agreement.** (a) Cohen's κ < 0.6 on the 20% second-rater set makes that outcome
   report-only; (b) no threshold. {#p-9}
10. **P-10 arm C in the session leg.** The exploration says "arm C is opt-in per session". (a)
    Not built: an opt-in session is not randomised and could not be compared, and 10.2 R7 already
    says C is never drawn; (b) build an opt-in switch whose sessions are reported descriptively
    only. {#p-10}
