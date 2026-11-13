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
  outcomes (2)-(5), the `used` outcome within the A cells, and 10.2's nested outcomes. A session's
  cell is drawn once, at SessionStart, and fixed for the whole session
  ([[task-28.1-session-arms-and-push-switch#r2]]). It is recorded on the session's telemetry, so
  arms are compared within the same projects and weeks.
- **Paired re-entry leg.** Each paired task is a real handoff that a prior session left
  mid-flight. Fresh agents resume it on isolated littlebig clones at the same starting commit,
  under each paired cell (`A+dedupe`, `B`, `C`) and each trigger, a **new session** and **after
  `/clear`** (Q3, folded fully per L20). It measures outcome (1), the primary. This leg isolates
  continuity, which session-level randomisation dilutes. The runner sets each run's cell
  explicitly; no period record is used. Later knowledge is guarded on three paths, the same in
  every cell:
  - the clone is cut at the start commit, with no later commit reachable or present;
  - the memory snapshot holds only memories older than the start;
  - every memory read, global store included, is filtered to the start time.

  A run whose transcript shows a read outside its clone is excluded as `leak_suspect`
  ([[task-28.2-paired-reentry-runner#r2]], [[task-28.2-paired-reentry-runner#r5]]).
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
6. **Used (session leg, within the A cells only; L18, L27, r1 #b1):** R12 explicit uses plus
   `cited_in_answer` on delivered memory items (19.6's scope) per 100 human prompts, with
   names-line items apart. 21.5's tool legs are never counted. `cited_in_answer` carries weight
   only if its 50-pair blind precision is at least 0.80 with a Wilson lower bound of at least
   0.65 (r1 #s5); otherwise (6) is R12 explicit uses only. Outcome (6) depends on what was
   delivered, so it is never compared between cells with and without push. In `B` it is
   reported descriptively.
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

How the CI enters a reading is P-8.

**Push (`A+dedupe` vs `B`, session leg; P-11, r1 #b1).** This compares the deployable default
with no push, on outcomes (2)-(4) only. If `A+dedupe` is better than `B` on none of them (no
session-bootstrap CI that excludes 0 in A's favour), while costing more on (5), the reading is
`shrink`: shrink ambient injection to a gated or pointer-only form. Outcome (6) is not an input,
because it counts uses of delivered items and B delivers nothing per prompt. 28.3 AC-8 holds a
synthetic result set where `shrink` fires.

**Nested (10.2 R7, `A+dedupe` vs `A+full`):** 10.2's own bands (dedupe cuts bytes per human
prompt ≥ 30% with used within −5% of `full` → keep; …), read on outcome 7.
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
4. **During the period:** items 8-11 build and deploy. A deploy that touches `scan.py`,
   `recall_pack.py`, `hook_budget.py`, context rendering, the hooks generator or `arms.py`
   lands only while no record is active. **Pausing (P-12, r1 #s8)** is a user-gated step: one
   commit sets the active record's `end` to now, and it is deployed. Sessions in flight keep
   their cell. Resuming is a new record (new id, new salt) at the user's go. Readings are
   stratified by record id, and the end rule counts only active days. Every deploy sha in the
   period is recorded, with its date and record id.
5. **At the end:** scoring, readings, the report and its ch-bsd round. Then the goal stops for
   the user's charter decision (G18). The T3 re-plan and the plan-24 re-plan (D-Q5) follow it.
{#ordering-body}

## Task list {#tasks}

| task | what | builds | depends on |
|---|---|---|---|
| [[task-28.1-session-arms-and-push-switch]] | the session-leg record; the cell fixed at SessionStart; the paired-run override (cell, run, as-of) and the as-of memory filter; arm B's push-off switch; the per-prompt `session_arm` field | `src/` | 10.2 |
| [[task-28.2-paired-reentry-runner]] | R0 probe; the paired task set; the runner (clones cut at the start sha, stores, memory snapshots, env pinning, triggers, archive, teardown, leak control); arm C's generated bare profile | `eval/production/handhold/` | 28.1 |
| [[task-28.3-outcome-scorer]] | the ONE scorer for outcomes 1-7, blinding, blind labeller agents, `cited_in_answer`, and the ONE reading module | `eval/production/handhold/` | 28.1 |
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

- **10.2 R7 (settled with spec-t3b, 2026-11-13).** 10.2 creates `arms.py`: the full cell table
  (`C` at weight 0), the store-scoped `draw(session_id, *, root, now=None)`, and the default
  `A+dedupe` outside a period. Plan-28 owns the period's values, the user-gated start, arm B's
  push-off, the scorer and the deletion
  ([[task-28.1-session-arms-and-push-switch#ownership]]). 10.2's outcome follows L27. 10.2 R7
  also builds the session cell fixed at SessionStart (one draw, `stm/<session>.arm.json`,
  `arms.session_cell`), and its verb and scan-prompt read only that (spec-t3b `151c81e`); 28.1
  R2 extends the file's fields. 10.2 R7 says C runs only on the paired leg (spec-t3b
  `46b21fa`, r1 #m7).
- **25.1 R8 (unchanged; r1 #m1).** "Never empty" holds on every call that packs. In cell `B`,
  SessionStart and PreCompact still pack; the per-prompt hooks do not pack.
- **19.6 `cited_in_answer`.** 28.3 implements 19.6's clause once, and 19.6's `score_readback.py`
  imports it when 19.6 is unfrozen (one implementation).
{#cross-plan-body}

rel: related-to -> [[task-10.2-plan-10-injection-dedup]]
rel: related-to -> [[task-25.1-recall-hook-byte-budget#r8]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache#ranges]]

## Under Q8 b {#q8-b}

"Q8" here is the save-state question of the open-questions ledger, session 37b7498f. It is not
the bug-216 confirm of session f0521bff. This plan holds under Q8 a or c, where save-states stay bridged as `session/recall-state` rows. Under
Q8 b (save-states and digests out at ingest), these lines change, and nothing else does:
- [[task-28.2-paired-reentry-runner#r2]]'s memory snapshot: save-states before the start are
  still copied into the clone's memory dir, but the bridge no longer ingests them, so in arms A
  and B they reach the agent only through `rmx recall-state` and grep, not through SessionStart
  recall.
- [[#arms]]'s "boundary" column: SessionStart recall no longer returns `session/recall-state`
  rows in any cell. The arms still differ in exactly the same handholds, so the design holds,
  but the boundary cells deliver less than under a or c. The frozen pre-registration
  (28.4) records which Q8 answer was live at the start.

## Lead rulings on the P-items (2026-11-13; frozen by 28.4) {#open}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

**Decision rows.** No D-Q or L-row settled these choices. The lead ruled on the user's pattern
and chose option (a) on all ten. The user is told and may overturn any of them, which would be
a dated revision before 28.4 freezes the pre-registration. 28.4 copies each value into the
frozen file, with this section cited. The options are kept below as the record. {#p-rulings}

| item | ruling |
|---|---|
| P-1 | equal thirds `A+dedupe` / `A+full` / `B` (`C` at 0) |
| P-2 | the primary comparison is `B` vs `C` |
| P-3 | the banded scalar for orientation cost is tool calls; tokens and wall time are printed |
| P-4 | W = 3 prompts |
| P-5 | **overridden by the lead's r1 #s5 ruling:** 50 blind `cited_in_answer` labels first; it carries weight only at precision ≥ 0.80 with a Wilson lower bound ≥ 0.65 (21.5's bar); otherwise outcome 6 counts R12 explicit uses only |
| P-6 | the paired leg's A cell is `A+dedupe` only |
| P-7 | the curator status line stays on in `B` |
| P-8 | "holds" and "holds weakly" need the effect's 95% CI to exclude 0 |
| P-9 | Cohen's κ < 0.6 makes that outcome report-only |
| P-10 | `C` runs only in the paired leg |
| P-11 (r1 #s8, #b1) | the push reading compares `A+dedupe` (the deployable default) with `B`, on outcomes (2)-(4) only |
| P-12 (r1 #s8) | the pause is a user-gated commit that sets the active record's `end` to now; sessions in flight keep their cell; resuming is a new record |
| contradiction 7 | every transcript the experiment uses is archived locally, outside the repo and every watched tree, never committed; the archive's creation is announced to the user ([[task-28.2-paired-reentry-runner#r2]], [[task-28.5-run-and-report#r5]]) |
{#p-rulings-table}

1. **P-1 cell weights (session leg). RULED (a).** (a) equal thirds `A+dedupe` / `A+full` / `B`; (b) `B` one
   half and each A cell one quarter, which gives A vs B more power and 10.2 less. {#p-1}
2. **P-2 the primary comparison. RULED (a).** (a) `B` vs `C`, the charter's named handholds with no
   multiple-comparison inflation; (b) the better of `A+dedupe` and `B` against `C`. {#p-2}
3. **P-3 orientation cost's banded scalar. RULED (a).** (a) tool calls (tokens include injected bytes,
   which bias against A); (b) tokens; (c) wall time. {#p-3}
4. **P-4 churn window W. RULED (a).** (a) 3 prompts (21.5's plateau `k`); (b) 2. {#p-4}
5. **P-5 `cited_in_answer` precision. RULED (a), then OVERRIDDEN by the lead's r1 #s5 ruling (see the table above).** (a) 50 cited pairs labelled with R12's rubric before its
   counts enter outcome 6; if the Wilson upper bound is below 0.50, outcome 6 is R12 explicit only
   and `cited_in_answer` is reported apart. It is whole-token matching in agent text, the same
   mechanism and prompt-echo confound that sank `bash_name`. (b) count it unchecked, as L18/L27
   say. {#p-5}
6. **P-6 the paired leg's A cell. RULED (a).** (a) `A+dedupe` only, the shipped default after 10.2; (b) both
   A cells, at 1.5× the runs. {#p-6}
7. **P-7 the curator status line in `B`. RULED (a).** (a) it stays on: it reports state and retrieves
   nothing; (b) off with the rest of the per-prompt output. {#p-7}
8. **P-8 the CI rule for a band. RULED (a).** (a) "holds" and "holds weakly" need the effect's 95% CI to
   exclude 0, otherwise the reading is the third row; (b) the point estimate alone. {#p-8}
9. **P-9 label agreement. RULED (a).** (a) Cohen's κ < 0.6 on the 20% second-rater set makes that outcome
   report-only; (b) no threshold. {#p-9}
10. **P-10 arm C in the session leg. RULED (a).** The exploration says "arm C is opt-in per session". (a)
    Not built: an opt-in session is not randomised and could not be compared, and 10.2 R7 already
    says C is never drawn; (b) build an opt-in switch whose sessions are reported descriptively
    only. {#p-10}
11. **P-11 which A the push reading compares (r1 #s8). RULED by the lead:** `A+dedupe`, the
    deployable default, against `B`, on outcomes (2)-(4) only (r1 #b1). {#p-11}
12. **P-12 what a pause is (r1 #s8). RULED by the lead:** a user-gated commit that sets the
    active record's `end` to now; sessions in flight keep their cell; resuming is a new record.
    {#p-12}

## Revision r1 (2026-11-13, `bsd-spec-t3c` DIRTY 1B/9S/11M; lead rulings) {#rev-r1}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| b1 the push reading could not fail: (6) is larger in A by construction | (6) leaves the push reading and is read within the A cells only; push = `A+dedupe` vs `B` on (2)-(4); 28.3 AC-8 is a set where `shrink` fires | [[#outcomes]], [[#bands]], [[task-28.3-outcome-scorer#r9]] |
| s1 the paired leg leaks later knowledge, and unequally | the clone is cut at the start sha; the as-of filter covers every memory read, global included, in every cell; leak control | [[#legs]], [[task-28.2-paired-reentry-runner#r2]], [[task-28.1-session-arms-and-push-switch#r4]] |
| s2 the paired cell cannot be pinned through a record | the runner sets the cell by env; records serve the session leg only | [[task-28.1-session-arms-and-push-switch#r3]] |
| s3 phase M re-measures on the pilot's data | handled in 21.5 R14 | [[task-21.5-tool-used-signal#r14-window]] |
| s4, s5 `cited_in_answer`'s scope, tokeniser and bar | memory items only, a boundary rule that keeps `/` and `#`, and precision ≥ 0.80 with a lower bound ≥ 0.65 | [[#outcomes]], [[task-28.3-outcome-scorer#r7]] |
| s7 the session-leg archive ran only at the end | a daily incremental sweep | [[task-28.5-run-and-report#r3]] |
| s8 which A; what a pause is | P-11, P-12 | [[#open]], [[#ordering]] |
| s9 the calibration powers the wrong contrast | `B` vs `C` | [[task-28.4-preregistration-freeze#r1]] |
| m1 "in B the pack is not called" | corrected; the edge to 25.1 R8 is `related-to` | [[#cross-plan]] |
| m2, m3, m5, m9, m10, m11 | folded into 28.1-28.5 (session-fixed cell; a mutation per AC; blind labeller agents; the slug check; who re-specs after R0; the limits) | the task specs' `#rev-r1` |
| m7 10.2 calls C "opt-in" | a request to spec-t3b | [[#cross-plan]] |
