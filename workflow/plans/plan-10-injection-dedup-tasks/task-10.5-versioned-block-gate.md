---
gmd: "0.1"
id: task-10.5-versioned-block-gate
title: "Task 10.5: before any build, judge the two per-prompt blocks (prompt-recall, scan-prompt) on 19.6's Tables A and B under an add-only keyframe state, run Table B's read-back probe, and a pre-registered labelled-use check that decides whether omission is switched on"
tags: [task, plan-10, measurement, versioned-injection, gate, pre-registration]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-11-13
---

# Task 10.5: gate for versioned per-prompt blocks {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending. Bands and definitions below were committed BEFORE any of R2-R4's numbers were
> computed (git history shows the order).
> Depends on: the user's answer to [[#d1]]; 21.1's events (released 0.80.0); lbl-215's labels.

rel: part-of -> [[plan-10-injection-dedup]]
rel: depends-on -> [[task-19.6-phased-context-and-topic-cache#ranges]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: motivates -> [[task-10.2-plan-10-injection-dedup]]

## Why {#why}

19.6 builds R5 (`unchanged` lines) and R6 (keyframe + delta) only in the bands of its
pre-registered Tables A and B, confirmed by the user (d9v). Plan-10 pulls R5 / R6 forward onto the
two per-prompt blocks (Q7). The 2026-11-13 already-held share (48.0%) is an ITEM statistic; it is
neither Table A's (whole-block byte identity between consecutive revs) nor Table B's (median delta
size, and read-back correctness of a patched state), so the bands are still unmeasured for these
blocks. And the reopened suppression question needs its own pre-registered check against labelled
use before omission is switched on. {#why-lead}

## The state definition, fixed before any number {#state}

Per (session, block id), for `prompt-recall` and `scan-prompt` only:

- **rev:** every emission of the block increments it (a call that emits nothing is not a rev; a
  gated call, 10.4 / 25.2, emits nothing).
- **keyframe** at: the session's first rev of the block; `rev − keyframe_rev ≥ K` (`K = 8`,
  d9v); the first rev after a compaction marker (19.6 R8a); a delta whose bytes exceed half of
  the full render's bytes (19.6 R6). A keyframe renders the current prompt's whole block and the
  state becomes exactly its items.
- **delta:** the items of the current prompt NOT in the state are added (rendered as the full
  form would render them); items already in the state are OMITTED; nothing is dropped (add-only,
  Table B's gated band). The state becomes state ∪ added.
- **unchanged:** a delta with nothing to add renders `<id> rev N unchanged` (R5).
- **item identity:** `(scope, entity_id)`, else `(scope, kind, name)` (441 hook deliveries on the
  2026-11-13 windows carry no `entity_id`).
- Cross-block: an item in `scan-prompt`'s state is NOT omitted from `prompt-recall`, and the
  reverse (one block, one state, as 19.6 versions blocks; the two hooks run concurrently on one
  prompt and cannot see each other's state).

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| d1 | **NEEDS THE USER.** Judge the per-prompt blocks on Table B directly; record Table A, do not let it close them. {#d1} | Table A measures whole-block identity; a per-prompt block changes every prompt by construction (computed 2026-11-13: `prompt-recall` 0.00% / 3.32%, `scan-prompt` 0.00% / 0.00%, [[plan-10-injection-dedup#context-table-a]]); its < 3% band would close both ids ("NO-GO for that block id, closed") before Table B, which measures what an add-only delta saves, is consulted. Changing which table governs a block id is a band change and needs a decision-log row (19.6 R0). If the user declines, plan-10's dedupe ends here and 10.2 is not built |
| d2 | K stays 8 | user-confirmed for R6 (d9v); the reopened suppression's "k" IS K here: an item is omitted at most `K − 1` consecutive revs; units with ≥ 6 earlier deliveries (1,461 + 555 = 2,016, 27% of re-delivered units) are the chronic repeaters a keyframe re-shows once per 8 revs. A different K needs its own row |
| d3 | The labelled-use check uses the existing lbl-215 pilot labels (13 used pairs) for a provisional verdict and is re-run final at ≥ 40 used pairs | n = 13 cannot separate 10% from 25% (the measurement's Wilson interval for 6 / 13 is 23-71%); a provisional verdict lets 10.2's RED start, the final one gates the deploy |

## Requirements {#requirements}

1. **R1 Table A, recorded.** Over two independent frozen session sets (19.6's worse-of-two rule;
   the 2026-11-13 windows are set 1, a later window ≥ 7 days after deploy of 10.4 is set 2), per
   block id: the share of emitted payload bytes whose `block_sha` equals the previous rev's, from
   21.1's events (hook calls with a session). Recorded with its band; under [[#d1]] = yes it does
   not decide. {#r1}
2. **R2 Table B, delta size.** Replay each set's `delivered` events per (session, block) in time
   order under [[#state]], with compaction markers taken from the transcripts'
   `compact_boundary` records (the sessions' own files, read in place, counts only). Report per
   block id and per set: the median of `delta bytes / full bytes` over non-cadence revs (the
   quantity R6's half-block rule reads; bytes = the items' delivered span bytes, so headers and
   bodies are excluded and stated); the share of revs that become keyframes by cadence, by marker,
   by the half-block rule; the share of items and of item bytes omitted; the share of RE-DELIVERED
   items omitted (against the measurement's 46.7%); the cross-block re-deliveries (earlier delivery
   on the other block only), which this design never omits. {#r2}
3. **R3 Table B, read-back correctness.** A probe set of 50 patched blocks (25 per block id),
   run in a SCRATCH Claude Code project (never this repo's settings, 25.1 R0's rule), on 25.1's
   synthetic fixture memories: each probe is a scripted session whose hook output is a keyframe
   followed by 1-7 deltas, then a question whose answer needs an item that the LAST delta omitted
   (present only in an earlier rev); scored by a script on whether the answer uses that item's
   content, or the agent fetches it, without re-asking. Correctness = scored-correct / 50, per
   block id and pooled. Synthetic text only; transcripts stay local; counts committed. {#r3}
4. **R4 The labelled-use check (pre-registered here).** For each lbl-215 delivered pair labelled
   CAUSED or INFORMED (13 at 2026-11-13; matched to delivered units exactly as `dd-10r`'s
   `cost.py` matched them), decide whether [[#state]] would have OMITTED that unit (an earlier
   delivery of the same item on the same block, since the block's last keyframe, no marker
   between). `x` = omitted used units. {#r4}
   - **Provisional bands (n = 13):** `x ≤ 1` → omission ON (provisional); `2 ≤ x ≤ 3` → the user
     decides; `x ≥ 4` → omission OFF.
   - **Final bands (≥ 40 used pairs):** `x / n ≤ 10%` → ON; 10-25% → the user decides; > 25% → OFF.
   - **OFF means the floor:** 10.2 is built with keyframes and `unchanged` lines only; a delta
     still renders every item of the current prompt (nothing is omitted), so no labelled use can be
     lost and the saving is whatever whole-block identity gives. Any middle form (for example a
     delta that names held items by rev) is a new design the user decides on, not a default.
5. **R5 The verdict.** GO for a block id when: [[#d1]] = yes; Table B (R2's median, R3's
   correctness) is "GO: R6" or "GO, gated: add-only deltas"; R4 is ON (provisional allows 10.2's
   RED and GREEN; final is required before deploy). Table B NO-GO or R4 OFF → the floor (R4).
   Written to `workflow/measurements/versioned-block-gate-2026-11.md` (GMD), counts only, with the
   commit of this spec named as the pre-registration. {#r5}

## Acceptance criteria {#acceptance}

1. **AC-1 Order.** This spec's bands are in a commit older than the first commit holding any R2-R4
   number.
2. **AC-2 One replay.** R2 and R4 use ONE replay function over [[#state]] (one script, imported by
   both), and 10.2's offline before / after imports the same function's rules from `src/` once
   10.2 lands, so the gate and the product cannot diverge silently.
3. **AC-3 Hand-checked replay.** A fixture of 3 sessions × 2 blocks × 12 revs with hand-computed
   keyframes (cadence, marker, half-block), omissions and medians; the replay reproduces them.
4. **AC-4 Counts only.** No committed file holds prompt, message, memory or answer text; the
   measurement file holds counts, bytes, hashes.

## Files {#files}

| file | change |
|---|---|
| `eval/production/versioned_blocks/replay.py` (new) | [[#state]]'s replay; R1, R2, R4 |
| `eval/production/versioned_blocks/probe/` (new) | R3's scratch-project harness and scorer |
| `tests/test_task10_5_replay.py` (new) | AC-2, AC-3 |
| `workflow/measurements/versioned-block-gate-2026-11.md` (new) | R1-R5 |

## Definition of done {#done}

- The verdict per block id written, each band's outcome named, and anything handed to the user
  raised with an id in `workflow/open-questions.md`.
- Committed on branch `task-10.5-versioned-block-gate`; merged `--no-ff` to `master`.
