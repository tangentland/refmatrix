---
gmd: "0.1"
id: plan-10-injection-dedup
title: "Per-prompt dedupe through 19.6's versioned blocks (keyframe + add-only delta), gated by 10.5 (provisionally NO-GO); non-human prompts get no per-prompt injection"
tags: [plan, scan-prompt, memory-recall, context, versioned-injection, hooks, injection, dedupe]
metadata:
  node_type: plan
  status: drafting
  created: 2026-09-15
  updated: 2026-11-13
---

# Proposed Plan: versioned per-prompt blocks, and no injection on non-human prompts {#root}

**Date:** 2026-09-15; reopened 2026-11-13.
**Status:** DRAFTING (reopened). 10.1 (2026-09-15) measured consecutive-call overlap at median
**0.000** and stopped the plan; that result stands as history. The 2026-11-13 re-measurement
([[measurement-injection-already-held-2026-11-13]], provisional until ch-bsd) found **48.0%** of
delivered items already held by the session, almost all by re-delivery, and about half of all
hook prompts non-human. The dedupe is 19.6's versioned injection (R5 / R6) applied to the two
per-prompt blocks, pulled forward ahead of the rest of 19.6 (context diff over pointer, Q7); a
pre-build gate (10.5) decides whether it is built. The specs go through a ch-bsd spec review
before this plan moves to `approved`.
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
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: realizes -> [[task-19.6-phased-context-and-topic-cache]]
rel: implements -> [[exploration-session-phased-context#versioned-injection]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[task-25.2-thin-prompt-gate]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: related-to -> [[task-21.5-tool-used-signal]]
rel: depends-on -> [[open-questions]]

## Context {#context}

`scan-prompt` and the per-prompt recall fire on every `UserPromptSubmit`; the agent cannot
decline them. Over a long session the same items come back turn after turn.

**2026-11-13 numbers** ([[measurement-injection-already-held-2026-11-13#result]]): 7,641 of
15,934 delivered units (48.0%; 46.9% of item bytes) were already held when delivered; re-delivery
alone 46.7%; hook channels only 43.2% / 51.9% (refmatrix / cliquedb); compaction-aware 42.1%.
Repeats are spread across the session: re-delivery gaps 1 prompt 1,168; 2-3 1,811; 4-10 2,049;
≥ 11 2,293; earlier deliveries per re-delivered unit 1 → 2,515; 2 → 1,221; 3-5 → 1,634; 6-20 →
1,461; ≥ 21 → 555. Cost check: 6 of 13 labelled used items were re-deliveries. {#context-2026-11-13}

**Whole blocks never repeat.** 19.6's Table A statistic (the share of a block's emitted bytes
byte-identical to its previous rev, from 21.1's `block_sha`), computed read-only on the same
windows on 2026-11-13: `prompt-recall` 0.00% (refmatrix, 338 calls) and 3.32% (cliquedb, 332
calls, 10 identical consecutive packs); `scan-prompt` 0.00% / 0.00% (362 / 369 calls). The
repetition is at the ITEM level, inside blocks whose whole content changes every prompt.
{#context-table-a}

## The failure mode this plan is designed around {#hazard}

A hook cannot see the context window. Whatever this plan omits because "the session already
holds it" may have been compacted or edited away. The design answer is 19.6's
([[exploration-session-phased-context#vi-delta]]): omit only against a rev KNOWN to be in the
window (since the last compaction marker), re-send everything in a full KEYFRAME every `K = 8`
revs and after any compaction, and count every omission. The labelled-use gate in 10.5 decides
whether omission is safe enough to switch on at all.

## Proposed Approach {#proposed-approach}

### The dedupe is 19.6's versioned injection on the per-prompt blocks {#versioned}

The two per-prompt payloads are 21.1's block ids `prompt-recall` (25.1's pack) and `scan-prompt`.
Each becomes a versioned block ([[task-10.2-plan-10-injection-dedup]]):

```
keyframe:   # rmx recall · prompt_recall · 9 hits · budget 4000 B · prompt-recall rev 9 keyframe
            supersedes earlier revs of prompt-recall
            <25.1's pack, unchanged>
delta:      # prompt-recall rev 10 = rev 9 + {add: 2}
            <25.1's hook lines for the 2 items not already in the block since rev 9>
unchanged:  prompt-recall rev 11 unchanged
```

The block's STATE is every item it carried since its last keyframe (add-only). A delta carries
only items not in that state; a keyframe re-renders the current prompt's whole pack and resets the
state to it. That is Table B's "add-only deltas" band, and it is where the reopened suppression
question lands: an item omitted from a delta is suppressed for at most `K − 1` revs and re-shown
at the next keyframe or after any compaction ([[#decisions-log]] R2'). No per-item pointer and no
separate ledger: the state is 19.6's "last-emitted state", one small file per session and block,
written by the block's own hook.

### Per-item pointer: withdrawn {#degrade}

The first 2026-11-13 draft rendered a held item as a one-line pointer and never suppressed it.
Withdrawn the same day: context diff over pointer (Q7); degrade-only reopened (open-questions
`#pre-ledger`). Kept as an anchor for the briefs that cite it.

### The gate comes first {#gate}

19.6 builds R5 / R6 only in the bands of its pre-registered Tables A and B (user-confirmed, d9v).
The 48.0% figure is an item-level held share; it is neither Table A's statistic nor Table B's,
so it satisfies neither. As written, Table A sends both per-prompt blocks to NO-GO ([[#context-table-a]]),
before Table B is consulted. 10.5 ([[task-10.5-versioned-block-gate]]) therefore needs a user
decision to judge per-prompt blocks on Table B directly, then runs Table B (delta size and
read-back correctness) and a pre-registered labelled-use check, and only its GO starts 10.2.

**Provisional result (2026-11-13, after the pre-registration commit):** NO-GO under the confirmed
bands. Table B's median delta / full is 1.000 on both stores: the half-block rule fires on ~87% of
revs and resets the add-only state each time, so only 6.4% / 10.9% of re-deliveries would be
omitted. Waiving the half-block rule (not pre-registered) omits 38-40% of re-deliveries and ~16-21%
of item bytes, but the median still exceeds 50% and 3 of 13 labelled used items would have been
omitted ([[task-10.5-versioned-block-gate#provisional]]). The way forward is the user's
([[task-10.5-versioned-block-gate#d4]]). {#gate-provisional}

### Non-human prompts get no per-prompt injection {#non-human}

User decision (arch-10r brief, 2026-11-13; unchanged by Q7): scan-prompt and the per-prompt
recall inject nothing on teammate, agent, cross-session, bus or task-notification turns. One
predicate (`terms.ambient_family`, behind `stm.is_ambient_text`) through 25.2's one prompt gate
([[task-10.4-non-human-prompt-gate]]). A gated call writes a `skipped_non_human` row.

## Open Questions {#open-questions}

### Q1: Does the repeat actually happen, and how much? {#q1}
**Status:** RESOLVED twice; the second answer governs.

- **2026-09-15 (10.1, history):** median consecutive-call overlap **0.000** against a
  pre-registered 0.40; the plan stopped ([[injection-overlap]]).
- **2026-11-13:** 48.0% held, band ≥ 30% → reopen
  ([[measurement-injection-already-held-2026-11-13#result-band]]).

### Q2: Where does the state live? {#q2}
**Status:** RESOLVED 2026-11-13 — 19.6's last-emitted state, one file per (session, block) under
`stm/<session>.emitted/`, plus the compaction marker in the same directory (19.6 R8a)
([[task-10.2-plan-10-injection-dedup#r2]], [[task-10.3-plan-10-injection-dedup#r1]]).

### Q3: Is scan-prompt even the right target? {#q3}
**Status:** RESOLVED 2026-11-13 — both per-prompt blocks: scan_prompt held 42.2% / 45.6%,
prompt_recall 57.6% / 77.3%. `session-start` stays fixed (prompt-less, as 19.6 R7).

### Q4: What is a non-human prompt, exactly? {#q4}
**Status:** RESOLVED 2026-11-13 by a read-only census ([[task-10.4-non-human-prompt-gate#census]]).

### Q5: Does Table A's NO-GO close the per-prompt blocks? {#q5}
**Status:** OPEN — needs the user ([[task-10.5-versioned-block-gate#d1]], and after the provisional
run [[task-10.5-versioned-block-gate#d4]]: accept NO-GO, change three confirmed rules for these two
ids, or another design).

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Repeat rate (consecutive calls) | Pre-registered >= 0.40. **Measured 0.000.** Plan stopped at 10.1. | 2026-09-15 |
| Q2 | Ledger location | Moot — not built. | 2026-09-15 |
| Q3 | scan-prompt vs grep | Moot for dedup. Separate finding: 28% of scan-prompt calls return nothing. | 2026-09-15 |
| Q1' | Already-held share (against the session) | **48.0%** held, ≥ 30% band → reopen; cost check tripped → the user decides | 2026-11-13 |
| D1 | What a re-delivered item becomes | ~~one-line pointer, never suppress~~ — SUPERSEDED by R1', R2' | 2026-11-13 |
| D2 | Non-human prompts | **No per-prompt injection** on teammate / agent / cross-session / bus / task-notification turns; counted as `skipped_non_human`; stands after Q7 | 2026-11-13 |
| R2' | "Degrade, never suppress" | degrade-only reopened (open-questions `#pre-ledger`); folded into the delta model: omission from a delta, bounded by keyframe and compaction, gated by 10.5's pre-registered labelled-use check | 2026-11-13 |
| R1' | The dedupe mechanism | context diff over pointer (Q7): 19.6 R5 / R6 on `prompt-recall` and `scan-prompt`, pulled forward; no per-item pointer, no separate ledger | 2026-11-13 |
| Q2' | State location | 19.6's last-emitted state (per session, per block); marker in the same store | 2026-11-13 |
| Q3' | Which blocks | `prompt-recall`, `scan-prompt`; `session-start`, `precompact`, explicit pulls stay full | 2026-11-13 |
| Q4 | Non-human predicate | `terms.ambient_family`, seven harness openings, behind `stm.is_ambient_text`; called through 25.2's `terms.prompt_gate` | 2026-11-13 |
| P1' | Task split | 10.4 gate; 10.5 pre-build measurement (Tables A/B on per-prompt blocks + labelled-use check); 10.3 the compaction marker (19.6 R8a's writer); 10.2 the versioned blocks, only on 10.5's GO | 2026-11-13 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 10.1 | **Measure the overlap** — consecutive-call replay (complete; history) | plan 9 |
| 10.4 | **Non-human prompt gate** — one predicate through 25.2's gate | 25.1, 25.2 merged |
| 10.5 | **Gate for versioned per-prompt blocks** — Table A / B on `prompt-recall` and `scan-prompt`, read-back correctness probe, labelled-use check; GO / NO-GO for 10.2 | the user's Q5 answer; 21.1's events (exist) |
| 10.3 | **Compaction marker** — 19.6 R8a's writer (PreCompact + SessionStart `compact\|clear`) into the last-emitted state | none beyond master; before 10.2 |
| 10.2 | **Versioned per-prompt blocks** — 19.6 R5 / R6 on 25.1's pack and scan-prompt; live before / after | 25.1 merged; 10.3; 10.4; 10.5 GO |

**Order:** 25.1 → 25.2 → 10.4 proceeds regardless. 10.5's provisional run says NO-GO, so 10.2
waits on the user's d4; 10.3 is useful to 19.6 either way and can be built now. Recommended: ship
10.4, then re-run 10.5 on human prompts only before deciding d4. 10.4 lands before 10.2 so that non-human prompts never become revs
(a gated prompt emits nothing), and 10.2's keyframe cadence counts human prompts from its first
commit. {#order}

## Execution contract {#execution}

TDD per [[tdd-governance]]. Plan-specific gates:

- **10.1 is pre-registered and closed.** Its negative result is history; it is not re-scored.
- **No build before the gate.** 10.2 starts only on 10.5's GO; 10.5's bands are committed before
  any of its numbers are computed.
- **Omission is bounded and counted.** An item is omitted only against a rev known to be in the
  window (after the last marker, since the block's last keyframe); every omission is counted on the
  call's row and as a `retrieved` event carrying the rev that holds it; a missing or unreadable
  state file means a keyframe.
- **The saving is re-measured live**, with `rmx telemetry --context` before and after, on the same
  corpus, after the fleet has been busy ([[impression_bsd_cost_measured_idle]]), plus an offline
  replay of the 2026-11-13 corpus through the GREEN functions.
- **Counts only.** Measurements read transcripts, rings and logs read-only and report counts,
  bytes and harness prefixes, never prompt or message text; user decisions are cited by id
  ([[open-questions]]), never quoted ([[feedback_no_raw_prompts_in_public_repo]]).

## Revision 2026-11-13 (reopening) {#rev-2026-11-13}

Reopened on the already-held measurement; specs by `arch-10r` (brief `workflow/agents/arch-10r.md`).
First draft (`d9c62cf`) specified a per-item pointer and a delivery-log ledger; superseded the
same day by Q7 (context diff over pointer) and the degrade-only reopening.

rel: derives-from -> [[agent-brief-arch-10r]]

| change | anchor |
|---|---|
| dedupe = 19.6 R5 / R6 on the per-prompt blocks; pointer and ledger withdrawn | [[#versioned]], [[#decisions-log]] R1' |
| suppression folded into delta omission, gated by 10.5 | [[#decisions-log]] R2', [[#gate]] |
| Table A computed on the corpus: 0.00-3.32%; Q5 opened | [[#context-table-a]], [[#q5]] |
| 10.5 added; 10.3 writes the marker into the last-emitted state; order fixed | [[#task-breakdown]], [[#order]] |
