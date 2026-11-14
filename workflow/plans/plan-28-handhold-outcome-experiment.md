---
gmd: "0.1"
id: plan-28-handhold-outcome-experiment
title: "Plan 28: the handhold outcome experiment: do refmatrix's handholds cut the backtrack-to-rebuild-understanding tax, and which ones (push, boundary, pull)? One leg: paired re-entry runs by fresh agents on real handoffs, with 10.2's dedupe A/B nested (L83)"
tags: [plan, experiment, charter, recall, scan-prompt, telemetry, handhold, plan-21, plan-10]
metadata:
  node_type: plan
  status: approved
  created: 2026-11-13
  updated: 2026-11-14
---

# Plan 28: the handhold outcome experiment {#root}

**Date:** 2026-11-13
**Status:** Approved (2026-11-14, [[#approval]]); spec wave G17; amended by L83 ([[#rev-l83]],
pending a confirm-lite). Its tasks are `pending`, which means approved to build. **The START
(28.5): the orchestrator starts the paired series when plan-28's Depends-on holds and tells the
user first (L78, L80).** Pausing the series and G18 stay user-gated. Written from
[[exploration-handhold-outcome-experiment]] and the plan review's decisions. The lead set
`approved` on the d9co route after a clean (MEH-only) ch-bsd round
([[plan-review-2026-11-13#goal-horizon]]).
**Location:** `workflow/plans/plan-28-handhold-outcome-experiment.md`; tasks in
`workflow/plans/plan-28-handhold-outcome-experiment-tasks/`.
**Queue:** item 7 of [[plan-review-2026-11-13#queue]]. The m1 confirm (L36) and 21.5 phase M come
first. **There is ONE leg, the paired re-entry series (L83; the user, 2026-11-14, Q14: "drop the
live part").** It is not time-boxed: it ends when its frozen n is reached or the user pauses it.
It runs in littlebig clones while items 8-11 build. **The user's own sessions are never assigned
to an arm.** **The goal stops** at its charter decision (G18).
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
| Q4 (user) | real sessions are randomised into arms for a fixed period, not opt-in. **Superseded by Q14 / L83:** no real session is randomised | history |
| Q5 (user) | the projects are refmatrix and cliquedb; under L83 they are the sources of the paired tasks (their real handoffs) | [[#legs]] |
| D-Q4 (user) | 21.5 decision → this experiment; no 21.5 build until it reports | [[#ordering]] |
| L20 (lead, CB-12, CB-15) | Q3 folded fully: a new-session trigger on the paired leg. Arm B's push-off switch is specified on 10.2's `arms`, and the "switch already exists" premise is struck. 10.2's A/B is nested: arm A splits into `A+dedupe` / `A+full`, so 10.2 is built before the start and its A/B is read from this experiment (from the paired series since L83) | [[#arms]], [[task-28.1-session-arms-and-push-switch]] |
| L18, L27 (lead, CB-9) | "used" counts only R12 explicit uses + `cited_in_answer`, never 21.5's unbuilt legs | [[#outcomes]], [[task-28.3-outcome-scorer]] |
| L36 (lead) | the m1 r2-lite confirm runs before this plan draws its bands | [[task-28.4-preregistration-freeze]] |
| L45 (lead), as delegated by L78 (the user, 2026-11-14) | L45 made the start user-gated; under L78 and L80, the orchestrator starts the paired series when plan-28's Depends-on holds and tells the user first. Pausing the series and G18 stay user-gated | [[task-28.5-run-and-report]] |
| L79 (the user, 2026-11-14: "the plan 28 arms should only be 3 days"; Q11 answered (a)) | the live session leg ran 3 calendar days. **Superseded by L83**, which removed that leg; L79's text is kept only as history in [[#rev-l79]] | history |
| L83 (the user, 2026-11-14, Q14: "drop the live part"; measured rates refmatrix ~0.5 sessions/day, cliquedb ~0.1/day) | ONE leg, the paired re-entry series. Every reading (primary, push, 10.2's nested) comes from it, each against its own pre-registered minimum n of paired tasks per cell. It is not time-boxed, and below a minimum n a reading is "underpowered, no verdict". The live session leg, live randomisation, the 3-day period and `end`/`after_end` are removed. The user's own sessions are never assigned to an arm | [[#legs]], [[#bands]], [[#ordering]], [[#rev-l83]] |
| G18 | the charter decision on the result is the user's; the goal stops there | [[task-28.5-run-and-report]] |
{#decided-table}

## Design {#design}

### Arms and cells {#arms}

Every cell runs only in paired runs, set explicitly by the runner (L83); no session is drawn.

| cell | push (per-prompt `scan_prompt`, `prompt_recall`) | boundary (SessionStart, recall-state, PreCompact) | pull (CLI / MCP context, memory get, recall) |
|---|---|---|---|
| `A+dedupe` | on, 10.2's names-only dedupe | on | on |
| `A+full` | on, no dedupe (10.2's `full`) | on | on |
| `B` | **off** ([[task-28.1-session-arms-and-push-switch#r5]]) | on | on |
| `C` | off | off: no rmx hook, no primer | tools available |

A vs B tests ambient push. B vs C tests the handholds the charter names (boundary + pull).
`A+dedupe` vs `A+full` is 10.2 R7's A/B, nested. **No push-off switch existed before this plan.**
The exploration's "a full off-switch for push already exists in the hook layer's budget gates" is
struck: no such switch is in `hooks.py` or `scan.py`, and 25.1 R8 says the pack is "never empty"
(contra-b CB-15). Arm B's switch is built by 28.1 on 10.2's `arms`. Arm C is a hook-less
settings profile generated by the runner, never hand-edited (28.2). {#arms-note}

### One leg: the paired re-entry series (L83) {#legs}

- **What a paired task is.** A real handoff that a prior session in refmatrix or cliquedb left
  mid-flight. Fresh agents resume it on isolated littlebig clones, all at the same starting
  commit. Each task runs under every cell (`A+dedupe`, `A+full`, `B`, `C`) and each trigger, a
  **new session** and **after `/clear`** (Q3, folded fully per L20).
- **Every reading comes from this series.** That covers the primary (`B` vs `C`), push
  (`A+dedupe` vs `B`) and 10.2's nested `A+dedupe` vs `A+full`. Each reading is checked against
  its own pre-registered minimum n of paired tasks per cell (28.4). Below it, the reading is
  "underpowered, no verdict".
- **Not time-boxed.** The series ends when the frozen n is reached, or when the user pauses it.
- **The runner sets each run's cell explicitly** through `arms` (28.1). No session is drawn,
  and the user's own sessions are never assigned to an arm.
- **Later knowledge is guarded on three paths, the same in every cell:**
  - the clone is cut at the start commit, with no later commit reachable or present;
  - the memory snapshot holds only memories older than the start;
  - every memory read, global store included, is filtered to the start time.

  A run whose transcript shows a read outside its clone is excluded as `leak_suspect`
  ([[task-28.2-paired-reentry-runner#r2]], [[task-28.2-paired-reentry-runner#r5]]).
{#legs-body}

### Outcomes {#outcomes}

Each outcome is a proxy for the backtrack-to-rebuild tax, read from the paired runs' transcripts
and telemetry by ONE scorer ([[task-28.3-outcome-scorer]]):

1. **Orientation cost (primary, both triggers pooled):** tool calls, tokens and wall time from
   the (re)start to the first productive edit or the first correct statement of the resume
   point. P-3 settles which of the three is the banded scalar.
2. **Exploratory churn:** Read / Grep / Glob / `rmx grep` calls that touch a project file and
   are not followed within W prompts by an edit or a citation of that file, per 100 prompts of
   the run (W per P-4).
3. **Re-derivation (labelled):** facts that a memory or handoff already held and the agent
   re-establishes by search, per 100 prompts.
4. **Repeated mistakes (labelled):** violations of a feedback memory's rule that existed and
   applied, per 100 prompts.
5. **Cost of the handholds:** injected bytes per prompt, hook latency, and the share of the hook
   output budget. This is a baseline, not a gate
   ([[feedback_measurable_benefit_is_not_the_reason]]).
6. **Used (within the A cells only; L18, L27, r1 #b1):** R12 explicit uses plus
   `cited_in_answer` on delivered memory items (19.6's scope) per 100 prompts, with names-line
   items apart. 21.5's tool legs are never counted. `cited_in_answer` carries weight only if its
   50-pair blind precision is at least 0.80 with a Wilson lower bound of at least 0.65 (r1 #s5);
   otherwise (6) is R12 explicit uses only. Outcome (6) depends on what was delivered, so it is
   never compared between cells with and without push. In `B` it is reported descriptively.
7. **10.2's nested outcomes:** injected bytes per prompt, and used per 100 prompts under rule 6,
   `A+dedupe` vs `A+full`, split by 10.4's `prompt_family`. 10.2 R7 owns their bands, and this
   plan reads them from the paired series (L83).
{#outcomes-list}

### Bands (frozen in 28.4 before the start) {#bands}

The primary reading compares the handhold cell named by P-2 against `C` on outcome (1):

| result on the primary outcome | reading | action, for the user's charter decision |
|---|---|---|
| handholds cut orientation cost ≥ 30% | premise holds | keep; tune what to push |
| 10-30% | premise holds weakly | keep boundary + pull; review push |
| < 10%, or C better | premise in trouble for this kind of work | re-examine the charter's mechanisms with the user |

How the CI enters a reading is P-8.

**Push (`A+dedupe` vs `B`; P-11, r1 #b1).** This compares the deployable default with no push, on
outcomes (2)-(4) only, paired by task. If `A+dedupe` is better than `B` on none of them (no
Holm-adjusted test across the three, with a bootstrap over tasks, rejecting in A's favour;
r2-m5), while costing more on (5), the reading is `shrink`: shrink ambient injection to a gated
or pointer-only form. Outcome (6) is not an input, because it counts uses of delivered items and
B delivers nothing per prompt. 28.3 AC-8 holds a synthetic result set where `shrink` fires.

**Nested (10.2 R7, `A+dedupe` vs `A+full`):** 10.2's own bands (dedupe cuts bytes per prompt
≥ 30% with used within −5% of `full` → keep; …), read on outcome 7 from the paired series.

**Underpowered (L79, L83).** Every reading above, the primary, push and nested readings
included, first checks the pre-registered minimum n of paired tasks per cell for the cells it
uses (28.4 R2). Below the minimum, the reading is "underpowered, no verdict": neither pass nor
fail, and no default changes. The report states the n reached per cell.
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
3. **28.5 starts the paired series when plan-28's Depends-on holds** (L78, L80): the
   orchestrator tells the user first, then runs the frozen series. Nothing is deployed to start
   it, and no live session is touched.
4. **During the series:** items 8-11 build and deploy. Every run records the deployed `rmx` sha
   it ran with. A deploy that touches `scan.py`, `recall_pack.py`, `hook_budget.py`, context
   rendering, the hooks generator or `arms.py` changes what a cell delivers, so it lands only
   while the series is paused. **Pausing (P-12)** is user-gated: on the user's word, the runner
   finishes or aborts the run in flight (recorded) and starts no new one. Resuming is also on
   the user's word. Readings are stratified by deploy sha when a series spans more than one.
5. **The series ends** when the frozen n of paired tasks per cell is reached, or the user stops
   it (L83). Scoring, readings, the report and its ch-bsd round follow. Then the goal stops for
   the user's charter decision (G18). The T3 re-plan and the plan-24 re-plan (D-Q5) follow it.
{#ordering-body}

## Task list {#tasks}

| task | what | builds | depends on |
|---|---|---|---|
| [[task-28.1-session-arms-and-push-switch]] | the paired-run override (run, as-of; the cell from 10.2's `arms.cell()`); the as-of memory filter; arm B's push-off switch; the paired rows' `session_arm` fields. No SessionStart draw (L83) | `src/` | 10.2 |
| [[task-28.2-paired-reentry-runner]] | R0 probe; the paired task set; the runner (clones cut at the start sha, stores, memory snapshots, env pinning of all four cells, triggers, archive, teardown, leak control); arm C's generated bare profile | `eval/production/handhold/` | 28.1 |
| [[task-28.3-outcome-scorer]] | the ONE scorer for outcomes 1-7 over the paired runs, blinding, blind labeller agents, `cited_in_answer`, and the ONE reading module | `eval/production/handhold/` | 28.1 |
| [[task-28.4-preregistration-freeze]] | the calibration, the minimum n of paired tasks per cell for every reading (with a power note), every P-item value, and the frozen pre-registration with its sha | measurement file | 28.1-28.3, G32, 21.5 phase M, bug-216 live |
| [[task-28.5-run-and-report]] | the orchestrator's start of the paired series (L78; the user is told first), the series, the readings, the report, the cleanup | measurement file | 28.4; Depends-on (L78) |

## Acceptance for the plan {#acceptance}

- Each reading whose cells reached their pre-registered minimum n of paired tasks is read as
  frozen. Each that did not reads "underpowered, no verdict", and the report states the n
  reached per cell (L79, L83). Nothing is re-specified after an outcome is seen.
- The user's own sessions are never assigned to an arm (L83).
- Committed results are counts, labels and hashes only. Transcripts and prompts stay local.
- No experiment agent writes to a live store. Paired runs happen only in littlebig clones.
- The report is through ch-bsd, and the charter decision is put to the user with the readings.
- `arms.py`'s measurement branches are deleted after the series, per 10.2's deferral row,
  unless the charter decision keeps an arm.
{#acceptance-list}

## Cross-plan effects {#cross-plan}

- **10.2 R7 (L83; the shape set by spec-t3b, 2026-11-14).** 10.2 creates `arms.py` with
  `CELLS = ("A+dedupe", "A+full", "B", "C")` (no weights) and `arms.cell()`. `arms.cell()`
  runs in the client process only and is the ONE reader of `RMX_HANDHOLD_CELL`: unset gives
  `A+dedupe`; a value outside `CELLS` gives an `Error:` line, `arm_error` and `A+dedupe`. Its
  verb and scan-prompt read the dedupe factor from `arms.cell()`. There is no draw, period
  record, salt, scope, arm file, `session_cell` or SessionStart write in 10.2 (L83). 10.2's rows
  carry `handhold_cell` when the env is set (L86; spec-t3b `5559d20`). 28.1 adds
  `paired_override` (run, as-of), `push_on` (reads `arms.cell()`), the as-of filter and the
  paired rows. Plan-28 owns the start (the orchestrator's under L78), arm B's push-off, the
  scorer and the deletion ([[task-28.1-session-arms-and-push-switch#ownership]]). 10.2's
  outcome follows L27. Its nested reading is read from the paired series against the minimum
  n of paired tasks per cell that 28.4 SETS (L86), which 10.2 cites.
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
| P-1 | equal thirds `A+dedupe` / `A+full` / `B` (`C` at 0). **Superseded by L83:** no session is drawn, so there are no draw weights; every paired task runs under all four cells |
| P-2 | the primary comparison is `B` vs `C` |
| P-3 | the banded scalar for orientation cost is tool calls; tokens and wall time are printed |
| P-4 | W = 3 prompts |
| P-5 | **overridden by the lead's r1 #s5 ruling:** 50 blind `cited_in_answer` labels first; it carries weight only at precision ≥ 0.80 with a Wilson lower bound ≥ 0.65 (21.5's bar); otherwise outcome 6 counts R12 explicit uses only |
| P-6 | the paired leg's A cell is `A+dedupe` only. **Superseded by L83:** the paired series runs `A+dedupe` AND `A+full`, because 10.2's nested reading now comes from it |
| P-7 | the curator status line stays on in `B` |
| P-8 | "holds" and "holds weakly" need the effect's 95% CI to exclude 0 |
| P-9 | Cohen's κ < 0.6 makes that outcome report-only |
| P-10 | `C` runs only in the paired leg (since L83, every cell does) |
| P-11 (r1 #s8, #b1) | the push reading compares `A+dedupe` (the deployable default) with `B`, on outcomes (2)-(4) only |
| P-12 (r1 #s8; restated by L83) | the pause is user-gated: on the user's word the runner finishes or aborts the run in flight (recorded) and starts no new run; resuming is on the user's word. The period-record form (an `end`-now commit, a new record to resume) went with the live leg |
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

## Revision r2 (2026-11-13, `bsd-spec-t3c` r2; lead rulings) {#rev-r2}

| finding | disposition | where |
|---|---|---|
| r2-s1, r2-s2 | the as-of argument is carried client to store, never read from env by a store process; C's env keeps the filter on; the run-id format | [[task-28.1-session-arms-and-push-switch#rev-r2]], [[task-28.2-paired-reentry-runner#rev-r2]] |
| r2-s3 | `attribute_explicit_use` moves into `src/` in 21.5 phase B | [[task-28.3-outcome-scorer#rev-r2]] |
| r2-m3 | the record's own start, pause and end commits are exempt from the pause ban | [[#ordering]] |
| r2-m5 | the push reading is Holm-adjusted across (2)-(4) | [[#bands]], [[task-28.3-outcome-scorer#r9]] |

## Approval (2026-11-14) {#approval}

rel: derives-from -> [[bsd-spec-t3c-r3-c5d1b79]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]

**Decision row (2026-11-14):** approved by the lead on the user's pattern (d9co) after ch-bsd `bsd-spec-t3c` r3 came back MEH-only (0B/0S/2M at `c5d1b79`), with both MEHs folded (r3 m1, m2). The ch-bsd rounds were r1 DIRTY 1B/9S/11M, r2 DIRTY 0B/3S/7M and r3 MEH-only; every finding is folded, as each spec's revision tables show. Plan-28 is `approved`, and tasks 28.1-28.5 are `pending`: approved to build in queue order. The experiment's START: the orchestrator starts the experiment when plan-28's Depends-on holds and tells the user first (L78) (28.5 R1, L80). Every pause, the end, G18 and the other user steps the tasks name stay user-gated. {#approval-row}

## Revision L79 (2026-11-14, the user: "the plan 28 arms should only be 3 days"; Q11 answered (a)) {#rev-l79}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

The status stays `approved` pending a confirm-lite ch-bsd round. Ruling L79 (dev master `acb1667`):
- the session leg runs 3 calendar days, concurrently;
- the n-floor no longer extends it;
- below a pre-registered minimum n, a reading is "underpowered, no verdict";
- the paired leg is unchanged.

| change | where |
|---|---|
| queue line, the L45 row, a new L79 row | header, [[#decided]] |
| the session leg's period, 3 calendar days; "weeks" → "days" | [[#legs]] |
| "underpowered, no verdict" for every reading below its minimum n | [[#bands]] |
| the end rule, 3 calendar days; the paired leg not time-boxed | [[#ordering]] |
| the plan acceptance | [[#acceptance]] |
| 28.2 R3, 28.3 R9/AC-10, 28.4 R2, 28.5 R3/R4/AC-2 | each task's `#rev-l79` |
| the exploration doc's nested-arm line and assignment | [[exploration-handhold-outcome-experiment#arms-nested]] |


**Refinement (dev master `8d88d29`; the user, the same day: "3 real days will be sufficent", Q11 a):** the period is 3 CALENDAR days from its start, with the arms concurrent. A pause does NOT extend it: the period ends 3 calendar days (72 hours) after the start, whatever was paused, and paused time is not made up. The "active days" wording is replaced. The rest of L79 is unchanged. {#rev-l79-refined}

## Revision L80 (2026-11-14, `bsd-spec-t3c` L79 confirm-lite 0B/1S/4M; lead ruling L80) {#rev-l80}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| S1 L78 delegated the start, but the specs still required the user's go | the status line, the L45 row, #ordering item 3, the task table, #cross-plan and #approval-row now read "the orchestrator starts the experiment when plan-28's Depends-on holds and tells the user first (L78)"; pause, end and G18 stay user-gated | header, [[#decided]], [[#ordering]], [[#approval]] |
| m3 the L79 row says "Q11 assumed" | "Q11 answered (a)" | [[#decided]], [[#rev-l79]] |


## Revision L82 (2026-11-14, `bsd-spec-t3c` L80 confirm-lite MEH-only 0B/0S/2M; lead ruling L82) {#rev-l82}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

| finding | disposition | where |
|---|---|---|
| m1 the task table's 28.5 row still said "the user's go" | "28.4; Depends-on (L78)" | [[#tasks]] |
| m2 the end waited on a late commit | 28.5's start commit writes `end = start + 72 h`; the scorer drops sessions at or after `end` | [[task-28.5-run-and-report#rev-l82]] |

## Approval of the L79/L80/L82 amendment (2026-11-14, d9co) {#approval-l79-2026-11-14}

| decision | basis | status |
|---|---|---|
| The 3-calendar-day session period (L79, Q11 answered a), the orchestrator-run start under L78 (L80) and the end committed with the start (L82) are approved by the lead on the user's pattern (d9co) after the L80 confirm-lite MEH-only (0B/0S/2M), folded at `49a603c` per L82 with no further round | `workflow/bullshit/2026-11-14-0200-spec-t3c-r5-l80-d42c72b.md` (with the L79 confirm-lite `2026-11-14-0150-spec-t3c-r4-l79-7758d2a.md`, over `spec-wave-t3c` `be03148..d42c72b`) | status unchanged; Q14 (where the verdicts come from) may amend this plan again |

rel: derives-from -> [[bsd-spec-t3c-r5-l80-d42c72b]]

## Revision L83 (2026-11-14, the user, Q14: "drop the live part"; lead ruling L83) {#rev-l83}

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[open-questions]]

L83 (dev master `715e356`): plan-28 has ONE leg, the paired re-entry series. Measured session
rates (refmatrix ~0.5/day, cliquedb ~0.1/day) put every live reading below its minimum. The
status stays `approved` pending a confirm-lite ch-bsd round.

| change | where |
|---|---|
| ONE leg: every reading (primary `B` vs `C`, push `A+dedupe` vs `B`, 10.2's nested `A+dedupe` vs `A+full`) comes from the paired series, each against its own pre-registered minimum n of paired tasks per cell; not time-boxed; below a minimum, "underpowered, no verdict" | header, [[#legs]], [[#outcomes]], [[#bands]], [[#acceptance]] |
| REMOVED: the live session leg, live SessionStart randomisation, the 3-day period (L79's period text, kept as history in [[#rev-l79]]), `end` and `after_end` (L82 m2, kept as history in [[#rev-l82]]), and every live-leg outcome. The user's own sessions are never assigned to an arm | everywhere; the Q4 and L79 rows are marked superseded in [[#decided]] |
| KEPT: the L78/L80 start rule, applied to the paired series; pausing and G18 stay user-gated; the series ends when its frozen n is reached or the user pauses or stops it | header, [[#ordering]] |
| the paired cells are now all four (`A+dedupe`, `A+full`, `B`, `C`); P-1 and P-6 are superseded, P-12 is restated | [[#arms]], [[#open]] |
| deploys of the treatment modules land only while the series is paused; every run records its deployed `rmx` sha | [[#ordering]] |
| `arms` shape for 10.2, as set by spec-t3b (2026-11-14): `CELLS` plus `arms.cell()`, the one reader of `RMX_HANDHOLD_CELL`; no draw, period, salt, scope, arm file, `session_cell` or `session_arm` row. 28.1 adds `paired_override` (run, as-of), `push_on`, the as-of filter and the paired rows. 10.2's nested minimum n is frozen in 28.4, and 10.2 cites it | [[#cross-plan]], [[task-28.1-session-arms-and-push-switch#ownership]], [[task-28.4-preregistration-freeze#r2]] |
| 28.1-28.5 and the exploration doc follow | each task's `#rev-l83` |

## Revision L86 (2026-11-14, lead ruling L86 on the crossed 10.2 / 28.1 arms shapes) {#rev-l86}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

L86: (1) 10.2's approved `arms.cell()` is the ONE reader of `RMX_HANDHOLD_CELL`, and the
constant-return `session_cell` is dropped as a placeholder under #no-mocks; (2) 28.4 SETS the
paired-task minimum for every reading. This fold sits on top of `15bc71a`, which had already
mirrored spec-t3b's shape after `e0a351a`; L86 confirms that shape.

| change | where |
|---|---|
| 10.2's rows carry `handhold_cell`; 28.1 adds no second cell field | [[#cross-plan]], [[task-28.1-session-arms-and-push-switch#r6]] |
| 28.4 SETS each reading's minimum n from a stated detectable effect, clamped to the exploration's 10-20 pairs per arm, with a power note; 10.2 cites it | [[#cross-plan]], [[task-28.4-preregistration-freeze#r2]] |

