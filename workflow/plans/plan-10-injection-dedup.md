---
gmd: "0.1"
id: plan-10-injection-dedup
title: "Names-only dedupe of the per-prompt payloads: an item the session already holds is named on one 'still in play' line instead of re-sent, on every prompt, human or not"
tags: [plan, scan-prompt, memory-recall, context, hooks, injection, dedupe]
metadata:
  node_type: plan
  status: approved
  created: 2026-09-15
  updated: 2026-11-13
---

# Proposed Plan: names-only dedupe of the per-prompt payloads {#root}

**Date:** 2026-09-15; reopened 2026-11-13.
**Status:** APPROVED 2026-11-14 ([[#approval]]), not started. The build order is [[#order]]: 10.3
early, the rest after T4. Reopened 2026-11-13. 10.1 (2026-09-15) measured consecutive-call overlap at median
**0.000** and stopped the plan; that result stands as history. The 2026-11-13 re-measurement
([[measurement-injection-already-held-2026-11-13]]) found **48.0%** of delivered items already
held by the session, almost all by re-delivery. A pre-registered replay of five designs chose
names-only (Q13); non-human turns get the same dedupe, no separate gate (Q10). The specs go
through a ch-bsd spec review, which came back CLEAN at r4 ([[#approval]]). Revision round 6 (2026-11-13,
spec wave, [[#rev-round-6]]) re-specs 10.2 against 25.1b, which owns the `still in play` line
(L15). It also gates 10.6's composite part on Table A (L17), sets the build order (L30) and marks
Q7 and Q11 superseded (L23).
**Location:** `workflow/plans/plan-10-injection-dedup.md` — permanent home; stage is `metadata.status`.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: depends-on -> [[plan-9-context-cost-telemetry]]
rel: reinforces -> [[feedback_prefer_existing_infra]]
rel: contradicts -> [[project_helix_log_confounded]]
rel: specifies -> [[task-10.1-plan-10-injection-dedup]]
rel: specifies -> [[task-10.2-plan-10-injection-dedup]]
rel: specifies -> [[task-10.3-plan-10-injection-dedup]]
rel: specifies -> [[task-10.4-non-human-prompt-gate]]
rel: specifies -> [[task-10.5-versioned-block-gate]]
rel: specifies -> [[task-10.6-injection-presentation]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13#design-replay]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13#design-replay-v2]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache#split-plan-10]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[task-25.1b-hook-output-ladder-and-spill]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: related-to -> [[task-21.5-tool-used-signal]]
rel: related-to -> [[exploration-handhold-outcome-experiment]]
rel: depends-on -> [[open-questions]]

## Context {#context}

`scan-prompt` and the per-prompt recall fire on every `UserPromptSubmit`; the agent cannot
decline them. Over a long session the same items come back turn after turn.

**2026-11-13 numbers** ([[measurement-injection-already-held-2026-11-13#result]]): 7,641 of
15,934 delivered units (48.0%; 46.9% of item bytes) were already held when delivered; re-delivery
alone 46.7%; hook channels only 43.2% / 51.9% (refmatrix / cliquedb). Repeats are spread across
the session (re-delivery gaps 1 prompt 1,168; 2-3 1,811; 4-10 2,049; ≥ 11 2,293) and arrive on
different words. Cost check: 6 of 13 labelled used items were re-deliveries, so nothing may be
removed without a trace. {#context-2026-11-13}

**Whole blocks never repeat.** 19.6's Table A statistic on the same windows: `prompt-recall`
0.00% / 3.32%, `scan-prompt` 0.00% / 0.00%. The repetition is at the ITEM level, inside payloads
whose whole content changes every prompt. {#context-table-a}

## The failure mode this plan is designed around {#hazard}

A hook cannot see the context window. Whatever this plan stops re-sending may have been compacted
or edited away. The design keeps every held item NAMED (one `still in play` line), resets "held"
at every compaction marker, and counts every name; nothing is removed by rule.

## Proposed Approach {#proposed-approach}

### Names-only dedupe {#names-only}

On every prompt, human or not ([[task-10.2-plan-10-injection-dedup]]):

```
<25.1b's header>
<the non-held hits, at the tier the full run gives them, in rank order, as 25.1b renders them>
<25.1b's `still in play` line, LAST: held members (this plan, marked `·held`) and over-budget
 members (25.1b), one rank order, ending with the spill page's fetch command>
```

The line comes LAST, after the hits, under the user-agreed presentation rule "most important
first" (bsd-spec-t3ab S2, lead ruling). scan-prompt's line is likewise its last block.

The line, its format, its cap of 15, its overflow and its spill page belong to 25.1b (L15,
contra-b CB-1). Plan-10 adds only the held members. {#names-only-owner}

rel: depends-on -> [[task-25.1b-hook-output-ladder-and-spill]]

- **Held** = rendered on its own (above the line) on `scan_prompt`, `prompt_recall` or
  `session_start` on an EARLIER prompt of the session, after the last compaction marker
  (cross-block). It is held only at the tier it was shown and poorer ones (10.2 h15, lead ruling):
  an item seen as a pointer still gets its body when the `full` run would give one. Held names are
  marked `·held` on the line (h16).
- Held items are taken out of the payload and named on ONE line, 25.1b's. Non-held items keep
  the tier and rendering the `full` run gives them, in their original order (tier-pinned,
  10.2 h9 and h13). Nothing new is pulled in, and freed bytes are not re-spent.
- The names line is visible but never makes an item held; compaction is the only reset.
- State: one small file per writing channel under `stm/<session>.emitted/`, beside 10.3's marker.
  21.1's events measure it; they are not its state.

**Why this design.** dd-10r's pre-registered replay (1,472 prompt calls; 11 labelled and 16 R12
explicit uses) scored five designs ([[measurement-injection-already-held-2026-11-13#design-replay]],
v2 [[measurement-injection-already-held-2026-11-13#design-replay-v2]]): names-only kept 11/11 and
16/16 visible at 0.469-0.470 of baseline block bytes; the per-item pointer also passed (0.477);
4+3 (novelty-first plus the names line) lost a labelled use under block bytes; 19.6's block diff
lost 4 labelled and 6 R12 uses. {#why-names-only}

### Per-item pointer: withdrawn {#degrade}

The first 2026-11-13 draft rendered a held item as a one-line pointer. Withdrawn the same day
(context diff over pointer, Q7; then names-only, Q13). Kept as an anchor for the briefs that cite
it.

### 19.6's block diff: not used for these payloads {#block-diff}

Plan-10 then planned 19.6 R5 / R6 (keyframe + delta) on the two payloads; the provisional replay
put it at NO-GO under 19.6's confirmed bands (Table B median delta / full 1.000;
[[task-10.5-versioned-block-gate#history]]), and the user chose not to use it for these payloads
(Q11). That NO-GO stands. 19.6 keeps R5 / R6 for its own blocks; plan-10 builds only R8a's marker
writer for it ([[task-19.6-phased-context-and-topic-cache#split-plan-10]]).

### Non-human turns {#non-human}

No separate gate (Q10): the full gate lost 10 R12 explicit uses in the with/without comparison
([[measurement-injection-already-held-2026-11-13#gate-comparison]]) and failed in every replay arm,
while names-only on those turns kept every use. What remains of 10.4 is a predicate
(`terms.ambient_family`) that keeps those turns out of the focus graph (lead decision), silences
curator status on them (Q9), and labels every hook row with the prompt family
([[task-10.4-non-human-prompt-gate]]).

### Measured after ship {#ab}

A per-session live A/B, `dedupe` vs `full`, NESTED in the handhold outcome experiment as a
declared factor: arm A splits into `A+dedupe` / `A+full` (L20). 10.2 is built before the
experiment starts, and the experiment's 3-calendar-day run (L79) IS this A/B
([[task-10.2-plan-10-injection-dedup#r7]]). Its "used" outcome counts only R12 explicit uses plus
`cited_in_answer` (L27). A later arm, 4+3b (baseline-delivered
non-held first, then new candidates, then held into leftover budget, the rest named), is recorded
for a future A/B and not built (Q13).

## Open Questions {#open-questions}

### Q1: Does the repeat actually happen, and how much? {#q1}
**Status:** RESOLVED twice; the second answer governs. 2026-09-15 (10.1, history): consecutive
overlap 0.000 ([[injection-overlap]]). 2026-11-13: 48.0% held, band ≥ 30% → reopen
([[measurement-injection-already-held-2026-11-13#result-band]]).

### Q2: Where does the state live? {#q2}
**Status:** RESOLVED — `stm/<session>.emitted/`: one held file per writing channel (10.2 h6) and
10.3's marker.

### Q3: Which payloads? {#q3}
**Status:** RESOLVED — `scan-prompt` and the per-prompt recall dedupe; `session_start` records
but never dedupes; PreCompact and explicit pulls neither.

### Q4: What is a non-human prompt? {#q4}
**Status:** RESOLVED by a read-only census ([[task-10.4-non-human-prompt-gate#census]]).

### Q5: Before build {#q5}
**Status:** OPEN (not a user question): 10.5's 50-probe read-back test, bands written first
([[task-10.5-versioned-block-gate#part-2]]); 10.5's v3 replay on 25.1b's pack
([[task-10.5-versioned-block-gate#part-1b]]); 10.6 R0's Table A on the composite
([[task-10.6-injection-presentation#r0]]).

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Repeat rate (consecutive calls) | Pre-registered >= 0.40. **Measured 0.000.** Plan stopped at 10.1. | 2026-09-15 |
| Q2 | Ledger location | Moot — not built. | 2026-09-15 |
| Q3 | scan-prompt vs grep | Moot for dedup. Separate finding: 28% of scan-prompt calls return nothing. | 2026-09-15 |
| Q1' | Already-held share (against the session) | **48.0%** held, ≥ 30% band → reopen | 2026-11-13 |
| D1 | Repeat rendering | ~~one-line pointer, never suppress~~ — superseded (Q7, then Q13) | 2026-11-13 |
| R2' | Degrade-only | reopened (open-questions `#pre-ledger`); names-only removes held items from the payload but always names them | 2026-11-13 |
| Q7 | Dedupe mechanism | ~~context diff over pointer; tried as 19.6 R5/R6, provisionally NO-GO~~ — **superseded** by Q11, then Q13 (names-only) and Q10 (L23) | 2026-11-13 |
| Q11 | Design for the two payloads | ~~4+3~~ — **superseded** by Q13 (names-only) after the replay rejected 4+3, and by Q10 for non-human turns (L23). Still standing from Q11: 19.6's block diff is not used for these payloads, and its NO-GO stands | 2026-11-13 |
| Q12 | How to choose | replay-score the designs first (dd-10r, pre-registered) | 2026-11-13 |
| Q13 | Design after the replay | names-only now; 4+3b a later A/B arm | 2026-11-13 |
| D2 | Non-human prompts | direction: less injection on non-human turns — refined by Q10 | 2026-11-13 |
| Q10 | Non-human turns | no separate gate; same dedupe as human prompts | 2026-11-13 |
| Q9 | Curator status on non-human turns | silent (10.4 R4, the 10.4b row) | 2026-11-13 |
| L1 | Agent-message turns and the focus graph (lead) | not STM input turns, same principle as `is_ambient_text` | 2026-11-13 |
| L2 | Envelope origin field (lead) | read before the prefix table when present | 2026-11-13 |
| L3 | Held rules (lead) | cross-block from earlier prompts; compaction the only reset; names line never refreshes held; scan in item units | 2026-11-13 |
| L4 | "Earlier prompt" (architect) | by `prompt_sha` and `PRE_PROMPT_SKEW_S`, not the STM turn (agent-message turns get payloads but are not STM turns) | 2026-11-13 |
| P1 | Presentation (user-agreed rules) | kind label on every item, kind-labelled headers, rank order kept; the composite uses 19.6 R5's `unchanged` line (whole-block versioning fits it; Table A failed only for the per-prompt lists) — task 10.6 | 2026-11-13 |
| P2 | Curator status (user-agreed rule) | prints only when its content changed since its last print in the session (10.4 R4) | 2026-11-13 |
| W1 | With/without (user asked) | offline: the gate failed (Q10); live: 10.2's `dedupe` vs `full` A/B, nested with the handhold experiment | 2026-11-13 |
| L15 | The `still in play` line (plan review, lead) | 25.1b owns it; its members are held (10.2) or over budget (25.1b); 10.2 re-specced against it, R8 parity re-derived (10.5 v3) | 2026-11-13 |
| L17 | 10.6's composite (plan review, lead; contra-b CB-7) | Table A runs on the composite before 10.6 R3, under 19.6's confirmed bands (10.6 R0) | 2026-11-13 |
| L23 | Spec review and merge (plan review, lead) | plan-10 rev 5 gets its ch-bsd spec review, then the revival branch merges to master before any 10.x builds; Q7 and Q11 marked superseded | 2026-11-13 |
| L27 | The A/B's outcome (plan review, lead) | only R12 explicit uses + `cited_in_answer`, never 21.5's unbuilt legs | 2026-11-13 |
| h15 | Which 25.1b tier makes an item held (lead ruling on 10.2 `#open-held-tier`) | (a) tier-aware: held only at the tier shown and poorer ones; the richest tier since the marker counts | 2026-11-13 |
| h16 | Held names on the line (lead ruling on 10.2 `#open-held-mark`) | (a) marked `·held`, inside the line's bytes; one rank order with over-budget members | 2026-11-13 |
| A1 | Plan approval | approved by the lead on the user's pattern (d9co) after ch-bsd bsd-spec-t3ab r4 CLEAN (2026-11-13/14); 10.2-10.6 approved to build; 10.1 stays complete ([[#approval]]) | 2026-11-14 |
| L79 | Experiment period (user, 2026-11-14) | plan-28's session leg runs 3 calendar days (72 h), arms concurrent, never extended; 10.2's 40 per cell per store is a minimum n, and below it the reading is "underpowered, no verdict" ([[task-10.2-plan-10-injection-dedup#rev-round-7]]) | 2026-11-14 |
| L30 | Build order (plan review, lead) | only 10.3 builds early; 10.5 probe → 10.6 → 10.4 → 10.2 after T4, ahead of the experiment | 2026-11-13 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 10.1 | **Measure the overlap** — consecutive-call replay (complete; history) | plan 9 |
| 10.4 | **Non-human predicate** — focus graph, family label on hook rows | 25.1 merged; 25.1b merged (its curator entry goes through R12's shared emitter) |
| 10.4b | **Curator status**: silent on non-human turns (Q9), change-only on human ones; its own hook entry; in [[task-10.4-non-human-prompt-gate#r4]] | 10.4; 10.3 |
| 10.3 | **Compaction marker** — 19.6 R8a's writer; the only reset of the held set | `master` |
| 10.5 | **Precondition** — the design replay (PASSED, v1/v2; v3 on 25.1b's pack to run) and a 50-probe read-back test (to run) | dd-10r's replay (done); 25.1b merged (v3, the probe's line) |
| 10.6 | **Injection presentation** — kind labels on every item at every 25.1b tier, kind-labelled headers, rank order kept; the STM composite sends `rev N unchanged` only if R0's Table A says GO | 25.1 merged; 25.1b merged; 10.3 |
| 10.2 | **Names-only dedupe** (held members on 25.1b's line, tier-pinned) + the live A/B nested in the handhold experiment | 25.1b merged; 10.3; 10.4; 10.6; 10.5 GO (v3 and the probe) |

**Order (L30, plan-review queue items 4 and 6):** only 10.3 builds early. It follows the revival
branch's merge (L23) in item 4, ahead of 25.1b and 25.3, which read its marker. Everything else
moves after T4 (item 6): 10.5's probe (and v3 in the measurement lane once 25.1b has merged) →
10.6 (after its R0 Table A) → 10.4 (+10.4b; install window) → 10.2. 10.2 lands before the
handhold experiment starts, because the experiment nests 10.2's A/B (L20). 10.6 lands before 10.2
so held members are labelled from 10.2's first commit. {#order}

rel: derives-from -> [[plan-review-2026-11-13#queue]]

## Execution contract {#execution}

TDD per [[tdd-governance]]. Plan-specific gates:

- **10.1 is pre-registered and closed.** Its negative result is history.
- **No build before the precondition.** 10.2 starts only on 10.5's GO: v3 PASSED and the probe
  GO. 10.5's probe bands are committed before any probe result, and 10.6 R0's bands before its
  result.
- **Nothing removed without a trace.** A held item is always named on 25.1b's line, or put on
  25.1b's spill page and counted. The line is reserved in the budget; a missing or unreadable state file means everything renders
  full; an unreadable marker means nothing is held.
- **The saving is re-measured live** after the fleet has been busy
  ([[impression_bsd_cost_measured_idle]]), plus an offline parity run of the replay through the
  GREEN functions.
- **Measurement switches are temporary.** The A/B's arm switch exists only for its period and is
  then deleted; correctness never depends on it.
- **Counts only.** Measurements read transcripts, rings and logs read-only and report counts,
  bytes and harness prefixes; user decisions are cited by id ([[open-questions]]), never quoted
  ([[feedback_no_raw_prompts_in_public_repo]]).

## Revision 2026-11-13 (reopening) {#rev-2026-11-13}

Specs by `arch-10r` (brief `workflow/agents/arch-10r.md`), four designs in one day: per-item
pointer (`d9c62cf`), 19.6 block diff (`308edc8`, provisional NO-GO `1e4c6bb`), a non-human policy
table (`ff8ca4d`), names-only with no gate (this revision, Q13, Q10).

rel: derives-from -> [[agent-brief-arch-10r]]

| change | anchor |
|---|---|
| names-only dedupe; pointer and block diff withdrawn | [[#names-only]], [[#degrade]], [[#block-diff]] |
| no non-human gate; the predicate's three uses | [[#non-human]] |
| live A/B `dedupe` vs `full`; 4+3b a later arm | [[#ab]] |
| 10.5 = replay (passed) + read-back probe | [[#task-breakdown]] |

## Q8 {#q8}

**Q8 is decided: a, as amended by Q9 (user, 2026-11-13; L60).** `workflow/` STAYS ingested.
G22 rev 2 adds ONE operational gate: `workflow/` docs, save-states and digests are dropped from
pagerank, concept weights and co-occurrence, and ranked LAST in default `rmx context` and the push
hooks unless the query names them. No plan-10 rule changes. Per-prompt recall already excludes `session/*` in hook modes (25.1
R2/R2b), so no save-state is ever held, named or spilled, and `session_start` records only what it
rendered. {#q8-body}

**The figures move, the rules do not.** {#q8-b}

- Once G22 rev 2's operational gate deploys, scan-prompt and recall rank `workflow/` hits last.
  So what the push hooks deliver, and in what order, changes.
- The 2026-11-13 held share (48.0%), the v1/v2 replay and 10.5's v3 were all computed under the
  old ranking.
- **The re-run trigger:** v3 is re-run after G22 rev 2's operational gate deploys (L60)
  ([[task-10.5-versioned-block-gate#r4b]]).
- R7's live run measures whatever store state exists while it runs.

The anchor keeps its name because earlier commits cite it. The trigger was keyed first to Q8 b,
then to "G22's ingest exclusion" (bsd-spec-t3ab S6). Q9 / L60 superseded the exclusion
(bsd-spec-t3ab r3 S3, lead ruling): `workflow/` stays, and the re-run is still needed because
ranking changes.

rel: depends-on -> [[plan-review-2026-11-13#d-q1]]

## Approval (2026-11-14) {#approval}

`metadata.status: approved` per CLAUDE.md `#plans-pre-written`. Gate checked at `5a2e6e2`: every
task in [[#task-breakdown]] has its spec under `workflow/plans/plan-10-injection-dedup-tasks/`.
That is task-10.1-plan-10-injection-dedup (`complete`, history), task-10.2-plan-10-injection-dedup,
task-10.3-plan-10-injection-dedup, task-10.4-non-human-prompt-gate,
task-10.5-versioned-block-gate and task-10.6-injection-presentation (each `pending`): 6 of 6, and
each frontmatter `id` equals its file stem. {#approval-gate}

- **Review basis:** the joint ch-bsd spec review of spec-wave-t3a and spec-wave-t3b. r1 was DIRTY
  1B/10S/10M, r2 DIRTY 0B/2S/8M and r3 DIRTY 0B/3S/3M; r4 (confirm-lite) was final CLEAN at
  `97dc7fa` / `5a2e6e2` (0B/0S/0M). The report is persisted as
  `workflow/bullshit/2026-11-14-0015-spec-t3ab-r4.md`. {#approval-basis}
- **Who approved:** the lead, on the user's pattern (d9co: a CLEAN ch-bsd round over the spec,
  then `approved` set by the orchestrator with the decision row written), 2026-11-13/14; decision
  row A1. {#approval-who}
- **What approval does not change:**
  - the build order stays [[#order]] (L30): 10.3 early, after the revival branch merges (L23);
    10.5 probe → 10.6 → 10.4 → 10.2 after T4, ahead of the handhold experiment;
  - 10.2 still builds only on 10.5's GO (v3 PASSED and the probe GO), and 10.6 R3 only on R0's
    Table A band;
  - every user-gated step in the specs stays with the user: the install windows for 10.3 (with
    25.1b) and 10.4, 10.5's FAIL route, and the experiment's start (plan-28);
  - every task still records RED at its base before GREEN ([[tdd-governance]]).
  {#approval-unchanged}

rel: derives-from -> [[bsd-spec-t3ab-r4-451112c-29ad4a5]]
rel: derives-from -> [[plan-review-2026-11-13#goal-horizon]]

## Revision round 6 (2026-11-13, spec wave, spec-t3b) {#rev-round-6}

This round is driven by [[plan-review-2026-11-13#spec-gaps]] G11 and by the lead rows L15, L17,
L23, L27 and L30 ([[plan-review-2026-11-13#lead]]). It folds contra-b CB-1, CB-6 (10.3's side)
and CB-7. The plan stays `drafting` until its ch-bsd spec review.

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[agent-brief-spec-wave]]

| change | driver | anchor |
|---|---|---|
| 25.1b owns the `still in play` line; 10.2 supplies held members only, tier-pinned on 25.1b's ladder; R8 parity re-derived by 10.5 v3 | L15, CB-1 | [[#names-only-owner]], [[task-10.2-plan-10-injection-dedup#rev-round-6]] |
| 10.6 R0: Table A on the composite before R3, under 19.6's confirmed bands; the exploration's `#vi-evidence` revised | L17, CB-7 | [[task-10.6-injection-presentation#r0]], [[exploration-session-phased-context#vi-evidence-2026-11-13]] |
| A/B nested in the handhold experiment; the outcome is R12 explicit + `cited_in_answer` only | L20, L27 | [[#ab]], [[task-10.2-plan-10-injection-dedup#r7]] |
| Only 10.3 builds early; the rest follow T4 | L30 | [[#order]] |
| Tier-aware held (h15); held names marked `·held` (h16) | lead rulings, 2026-11-13 | [[task-10.2-plan-10-injection-dedup#open-held-tier]], [[task-10.2-plan-10-injection-dedup#open-held-mark]] |
| Q7 and Q11 marked superseded by Q13 / Q10 | L23 | [[#decisions-log]] |
| 10.3's reader list includes 25.1b R14 and 25.3 R7 (helix reset, L16) | L16, CB-6 | [[task-10.3-plan-10-injection-dedup#r2]] |
| 10.4's curator entry goes through 25.1b R12's shared emitter | L15 | [[task-10.4-non-human-prompt-gate#rev-round-6]] |
