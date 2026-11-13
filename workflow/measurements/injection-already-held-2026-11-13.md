---
gmd: "0.1"
id: measurement-injection-already-held-2026-11-13
title: "Already-held share of injected context (2026-11-13): 48.0% of delivered items the session already held, almost all re-delivery; cost check trips (6 of 13 used items were re-deliveries)"
tags: [measurement, plan-10, injection, dedupe, recall, scan-prompt]
metadata:
  node_type: measurement
  status: provisional
  created: 2026-11-13
---

# Already-held share of injected context, 2026-11-13 {#root}

Run by `dd-10r` (brief `workflow/agents/dd-10r.md`, bands pre-registered by the lead before any
number) after the user asked whether injected context is deduped against the session's running
representation (it is not). Reopens plan-10 as a measurement: task 10.1
([[injection-overlap]]) stopped plan-10 on consecutive-call overlap and never compared injections
with what the session already held. Persisted by the lead from the agent's text; counts only.
**Provisional** until ch-bsd.

rel: amends -> [[injection-overlap]]
rel: evidence-for -> [[plan-10-injection-dedup]]
rel: related-to -> [[exploration-handhold-outcome-experiment]]
rel: related-to -> [[measurement-task-21.5-r12-pilot-2026-11-13]]

## Pre-registration {#prereg}

Unit: one `delivered` event on scan_prompt, prompt_recall, session_start or precompact in a
session with a ring. Already held at delivery: (a) the same item delivered earlier in the session;
(b) its file read, edited or named by an earlier main-loop tool call (D15 rules); (c) in
`focus_view(g, top=30)` of the ring replayed to the prompt. Bands: ≥ 30% reopen plan-10 (dedupe
against the session representation); 15-30% dedupe re-deliveries only; < 15% stop. Cost check: if
more than 25% of labelled CAUSED+INFORMED pairs were already held, the action needs the user.

## Result {#result}

| | held by count | held by bytes (item lines only) |
|---|---|---|
| **pooled** | **7,641 / 15,934 = 48.0%** | **432,478 / 921,762 = 46.9%** |
| refmatrix (2026-10-20..11-13) | 4,353 / 9,769 = 44.6% | 43.3% |
| cliquedb (2026-11-04..11-11) | 3,288 / 6,165 = 53.3% | 52.1% |

Band: ≥ 30% → reopen plan-10. `body_bytes` is null on every delivered event, so bytes cover item
lines only; bodies would add to the saving. {#result-band}

## Cost check {#cost}

13 labelled CAUSED+INFORMED delivered pairs: 6 already held (46.2%, Wilson 23-71%), all by
re-delivery (a); refmatrix 2 of 7, cliquedb 4 of 6. Above 25% → the action needs the user (a
small-n trip: the lower bound is under 25%). Explicit R12 used events on primary channels: 8 of 16
held. CONSISTENT 36 of 94 held; UNRELATED 16 of 54.

## Breakdowns {#breakdowns}

- **By criterion (overlapping):** (a) re-delivered 46.7%; (b) already touched 1.3%; (c) in focus
  1.3%. (b) and (c) add 201 units beyond (a). Restricting (a) to hook channels: 43.2% / 51.9%.
- **By channel:** scan_prompt 42.2% / 45.6%; prompt_recall 57.6% / 77.3%; session_start 46.5% /
  58.8%; precompact 20.0% / —. Agent-pulled channels, reported apart: `context` 96.9% (of 3,455) /
  23.6%; `recall` 16.7% / 0%.
- **By item kind:** memory 58.1% / 77.3%; doc anchor 38.3% / 58.8%; code 55.0% / 30.6%; term 44.9%
  / 30.9%.
- **Per session:** refmatrix 4.0-50.4% (median 39.8%, 7 sessions; the three largest 44.5-50.4%);
  cliquedb 46.0-59.6% (3 sessions).
- **Repeated prompt words?** Of 7,386 prompt-channel re-deliveries, the item's name is in both
  prompts in 142 (1.9%); the prompts share a scan candidate term in 3,682 (49.9%); the earlier
  delivery was at the preceding prompt in 1,168 (15.8%). Gap: same prompt 29, 1 prompt 1,168, 2-3
  1,811, 4-10 2,049, ≥ 11 2,293. Earlier deliveries per re-delivered unit: 1 → 2,515; 2 → 1,221;
  3-5 → 1,634; 6-20 → 1,461; ≥ 21 → 555. Earlier channel: scan_prompt 5,351, prompt_recall 1,999.
  The same items come back across a session, on different words.
- **Human vs non-human delivering prompt** (not pre-registered): about 64% of prompt-channel units
  were delivered on NON-human prompts (teammate, bus, task-notification turns), held 54.0% /
  59.9%; human prompts 27.7% / 40.4%; pooled human-only 32.5%.
- **Compaction-aware variant** (not pre-registered; (a)/(b) evidence must fall after the last
  compaction): 42.1% pooled (refmatrix 40.0%, cliquedb 45.4%).

## Deviations and limits {#limits}

Primary channels exclude the agent-pulled `context` and `recall`; global-scope items (100) have no
path; (a) excludes a key repeated within one call (196 units); deliveries before the window count
as earlier. cliquedb: 3 of 6 delivering sessions have a ring (80 events excluded). Focus replay:
topic count equals the logged value for 90.6% / 94.4% of prompt units. Held is not attended (the
compaction variant is the partial correction); a subagent's `rmx context` counts as held by the
session. Name matching and the human / non-human split are heuristic. Scripts stay in the session
scratchpad (`dd/`).

## Addendum: with / without the non-human gate (plan-10 task 10.4) {#gate-comparison}

User asked for a with/without comparison of the non-human gate. Pre-registered at 13:01 (rule: SAFE
if labelled + R12 explicit uses lose at most 1 use with no human-prompt delivery of the same key
before it). Classifier: exact prefix of the delivering query.log row (`<agent-message`,
`<cross-session-message`, `<task-notification`, `<channel`, `[SYSTEM NOTIFICATION`); ring
cross-check agrees 607/608 and 572/579. Distinct delivering prompts: refmatrix plain 350,
agent-message 257, task-notification 77; cliquedb 274 / 286 / 143. {#gate-setup}

| | with gate removes | units | bytes |
|---|---|---|---|
| refmatrix | 62.0% | 9,663 → 3,676 | 538,964 → 206,881 |
| cliquedb | 62.8% | 6,148 → 2,286 | 377,986 → 140,419 |
| pooled | 62.3% | 15,811 → 5,962 | 916,950 → 347,300 |

- **Labelled uses:** of 13 CAUSED+INFORMED pairs, 11 on prompt channels: 10 human, 1 non-human, and
  that item had already been delivered on a human prompt — 0 labelled uses lost.
- **R12 explicit uses:** 16 on prompt channels; 10 rode non-human prompts (9 agent-message, 1
  task-notification; all scan_prompt concept items), and NONE had any earlier delivery of the same
  key — 10 lost. Only 2 were used within ~4 minutes; 8 came 1.7-107 h later (weak attribution); 9
  of 10 are lead sessions, where agent-message turns are teammate reports read by the main loop.
- **Removed deliveries:** 57.5% were already held; 42.5% (242,668 B) were not.
- **Verdict:** 10 lost > 1 → the user decides (Q10). Near-term only: 2 lost, still > 1. {#gate-verdict}

## Addendum: dedupe design replay (Q11, Q12) {#design-replay}

Pre-registered 13:22 (`dd/PREREG_designs.txt`): held = delivered FULL on a hook channel on an
earlier prompt, after the last compaction; candidates = the call's retrieved + delivered events in
rank order; ACCEPTABLE = every labelled use stays visible and ≤ 1 R12 explicit use lost; rank by
novelty density. 1,472 prompt calls; 15,713 baseline items; 28,779 candidates; 11 labelled and 16
R12 uses on prompt channels. Item-line bytes (the registered unit) are 4-8% of a payload and
cannot rank designs; a block-bytes arm (deviation: an item's span to the next item, ~95% of the
payload) is reported, and the bands do not depend on bytes. {#design-setup}

| design | block bytes vs baseline | new items / call | labelled visible | R12 visible | verdict |
|---|---|---|---|---|---|
| 0 baseline | 1.000 (10,311 B/call) | 0 | 11/11 | 16/16 | — |
| 1 pointer | 0.477 | 0 | 11/11 | 16/16 | acceptable |
| 3 names-only (cap 15) | 0.469 | 0 | 11/11 | 16/16 | acceptable, ranked first |
| 4+3 novelty rank | 0.977 | 1.98 | 10/11 | 16/16 | NOT acceptable |
| 4+3b (post hoc: baseline-delivered non-held first) | 0.984 | 1.87 | 11/11 | 16/16 | passes, post hoc only |
| 5 diff + keyframe K = 8 | 0.524 | 0 | 7/11 | 10/16 | NOT acceptable |

4+3's lost use: a non-held prompt_recall item at candidate 6 of 15 lost its budget to
higher-ranked candidates that were retrieved but never delivered at baseline.

**Non-human turns** (847 calls; human calls under 4+3): `none` (the gate) loses the same 10 R12
uses (fails); `4+3` keeps 1/1 labelled and 10/10 R12 at 0.982 bytes; `full` keeps all. Applying
the dedupe there keeps every use; the gate does not. {#design-verdict}

**v2 (2026-11-13, the four held rules as a dated pre-registration addendum, run after v1 was
reported):** held = full delivery on scan_prompt / prompt_recall / session_start from an EARLIER
prompt (prompt clock: 1,472 / 1,472 anchored); compaction the only reset; names and pointer lines
visible but never setting held; scan in item units, recall in bytes. Line arm: 4+3 11/11 labelled,
16/16 R12 — ACCEPTABLE by one item (ratio 1.345, 1.76 new/call); block arm: 4+3 10/11 — not
acceptable. 4+3b (post hoc) 11/11 and 16/16 in both arms (block 0.978, 1.76 new/call). Names-only
0.872 line / 0.470 block, 11/11, 16/16; pointer 1.011 / 0.478, acceptable; design 5 fails (7/11,
10/16). The non-human gate fails in every arm (R12 6/16 overall). 4+3's verdict flips on one
prompt_recall item with the byte model; 4+3b does not. {#design-replay-v2}
