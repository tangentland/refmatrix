---
gmd: "0.1"
id: plan-10-injection-dedup
title: "Names-only dedupe of the per-prompt payloads: an item the session already holds is named on one 'still in play' line instead of re-sent, on every prompt, human or not"
tags: [plan, scan-prompt, memory-recall, context, hooks, injection, dedupe]
metadata:
  node_type: plan
  status: drafting
  created: 2026-09-15
  updated: 2026-11-13
---

# Proposed Plan: names-only dedupe of the per-prompt payloads {#root}

**Date:** 2026-09-15; reopened 2026-11-13.
**Status:** DRAFTING (reopened). 10.1 (2026-09-15) measured consecutive-call overlap at median
**0.000** and stopped the plan; that result stands as history. The 2026-11-13 re-measurement
([[measurement-injection-already-held-2026-11-13]]) found **48.0%** of delivered items already
held by the session, almost all by re-delivery. A pre-registered replay of five designs chose
names-only (Q13); non-human turns get the same dedupe, no separate gate (Q10). The specs go
through a ch-bsd spec review before this plan moves to `approved`.
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
# rmx recall · prompt_recall · 9 hits · budget 4000 B
still in play: feedback_push_from_dev_not_deploy, project_0820_release_fleet_hooks (+0)
- <the non-held hits, in their original rank order, as 25.1 renders them>
```

- **Held** = delivered FULL on `scan_prompt`, `prompt_recall` or `session_start` on an EARLIER
  prompt of the session, after the last compaction marker (cross-block).
- Held items are taken out of the payload and named on ONE line (cap 15, then `(+N)`); non-held
  items render in full in their original order; nothing new is pulled in.
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

A per-session live A/B, `dedupe` vs `full`, drawn from one arm table shared with the handhold
outcome experiment ([[task-10.2-plan-10-injection-dedup#r7]]). A later arm, 4+3b (baseline-delivered
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
([[task-10.5-versioned-block-gate#part-2]]).

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Repeat rate (consecutive calls) | Pre-registered >= 0.40. **Measured 0.000.** Plan stopped at 10.1. | 2026-09-15 |
| Q2 | Ledger location | Moot — not built. | 2026-09-15 |
| Q3 | scan-prompt vs grep | Moot for dedup. Separate finding: 28% of scan-prompt calls return nothing. | 2026-09-15 |
| Q1' | Already-held share (against the session) | **48.0%** held, ≥ 30% band → reopen | 2026-11-13 |
| D1 | Repeat rendering | ~~one-line pointer, never suppress~~ — superseded (Q7, then Q13) | 2026-11-13 |
| R2' | Degrade-only | reopened (open-questions `#pre-ledger`); names-only removes held items from the payload but always names them | 2026-11-13 |
| Q7 | Dedupe mechanism | context diff over pointer; tried as 19.6 R5/R6, provisionally NO-GO | 2026-11-13 |
| Q11 | Design for the two payloads | 4+3; 19.6's block diff not used for them; its NO-GO stands | 2026-11-13 |
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

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 10.1 | **Measure the overlap** — consecutive-call replay (complete; history) | plan 9 |
| 10.4 | **Non-human predicate** — focus graph, family label on hook rows | 25.1 merged |
| 10.4b | **Curator status**: silent on non-human turns (Q9), change-only on human ones; its own hook entry; in [[task-10.4-non-human-prompt-gate#r4]] | 10.4; 10.3 |
| 10.3 | **Compaction marker** — 19.6 R8a's writer; the only reset of the held set | `master` |
| 10.5 | **Precondition** — the design replay (PASSED, v1/v2) and a 50-probe read-back test (to run) | dd-10r's replay (done) |
| 10.6 | **Injection presentation** — kind labels on every item, kind-labelled headers, rank order kept; the STM composite sends `rev N unchanged` | 25.1 merged; 10.3 |
| 10.2 | **Names-only dedupe** + the live A/B | 25.1 merged; 10.3; 10.4; 10.6; 10.5 GO |

**Order:** 10.3 and 10.5's probe can start now; 25.1 → 10.6 → 10.4 (+10.4b) → 10.2. 10.6 lands
before 10.2 so the names line is labelled from its first commit. {#order}

## Execution contract {#execution}

TDD per [[tdd-governance]]. Plan-specific gates:

- **10.1 is pre-registered and closed.** Its negative result is history.
- **No build before the precondition.** 10.2 starts only on 10.5's GO; 10.5's probe bands are
  committed before any probe result.
- **Nothing removed without a trace.** A held item is always named or counted (`(+N)`); the names
  line is reserved in the budget; a missing or unreadable state file means everything renders
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
