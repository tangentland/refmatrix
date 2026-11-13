---
gmd: "0.1"
id: task-10.5-versioned-block-gate
title: "Task 10.5: the precondition for 10.2 — the pre-registered design replay (PASSED for names-only, v1 and v2) and a 50-probe read-back test (to run); history: 19.6's block diff judged NO-GO for these payloads"
tags: [task, plan-10, measurement, gate, pre-registration, dedupe]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 10.5: precondition for the names-only dedupe {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending. Part 1 (the design replay) PASSED for names-only; part 2 (the read-back probe)
> is to run, with its bands written below before any probe. The id keeps its first name
> (`versioned-block-gate`) because other docs address it; the block diff it first gated is closed
> ([[#history]]).
> Depends on: dd-10r's replay (done); 25.1's synthetic fixture memories for the probe; 25.1b
> merged for Part 1b and for the probe's line (revision round 6, [[#rev-round-6]]). Under L30
> the probe runs after T4, ahead of 10.6.

rel: part-of -> [[plan-10-injection-dedup]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13#design-replay]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13#design-replay-v2]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: motivates -> [[task-10.2-plan-10-injection-dedup]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache#ranges]]
rel: depends-on -> [[open-questions]]

## Why {#why}

Names-only takes an item the session already holds out of the payload and leaves only its name.
Two things must hold before it is built: that no labelled or explicitly used item stops being
visible (part 1), and that a model given only the name still uses what it was shown earlier
(part 2). {#why-lead}

## Part 1: the design replay — PASSED {#part-1}

dd-10r's pre-registered replay ([[measurement-injection-already-held-2026-11-13#design-replay]],
rule: every labelled use stays visible and at most 1 R12 explicit use is lost), 1,472 prompt calls,
11 labelled and 16 R12 uses on prompt channels:

| run | names-only, block bytes vs baseline | item-line bytes | labelled visible | R12 visible | verdict |
|---|---|---|---|---|---|
| v1 | 0.469 | — | 11/11 | 16/16 | acceptable, ranked first |
| v2 (the four held rules, dated addendum) | 0.470 | 0.872 | 11/11 | 16/16 | acceptable |

The same runs rejected 4+3 (10/11 labelled under block bytes; it passed v2's line arm by one item
only) and the block diff (7/11, 10/16); the non-human gate failed in every arm (Q10). Chosen:
names-only (Q13). 10.2 R8 re-runs this replay with the rules imported from `src/` and must
reproduce v2. {#part-1-result}

## Part 1b: the replay re-derived on 25.1b's pack (v3) — to run {#part-1b}

v1 and v2 scored names-only against 25.1 rev 7's pack, which renders whole bodies and drops the
rest. 25.1b replaces that with a degrade ladder (full, excerpt, pointer, names line) and a spill
page. It also owns the `still in play` line, whose members are held or over budget (L15, contra-b
CB-1). The baseline that names-only is measured against has therefore changed, and so has 10.2
R8's parity target. v3 re-derives both. {#part-1b-why}

rel: depends-on -> [[task-25.1b-hook-output-ladder-and-spill]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]

1. **R1b The run.** It is v2's replay: the same windows, the same 1,472 prompt calls, the same 11
   labelled and 16 R12 uses, and the same four held rules. The BASELINE changes: each call's
   recall payload is rendered by 25.1b's `recall_pack.pack`, imported from `src/` after 25.1b
   merges, on the call's retrieved rows. scan-prompt has no ladder under 25.1b, so v2's span
   arithmetic stands for it, and only its line's bytes come from 25.1b's line renderer. Names-only is rendered TIER-PINNED, as 10.2 h9 defines it: every
   non-held row keeps the tier the baseline gave it, and every held row's rendering is replaced by
   its name on the line. The held rules and that substitution stay the replay's own (v2's code),
   because 10.2 does not exist yet. That independence is what makes 10.2 R8 a parity check rather
   than a tautology: at 10.2's GREEN the replay is re-run with `stm.held_items` and
   `pack(held=…)` imported from `src/`, and both runs must agree. A retrieved row whose memory no
   longer exists in the store copy is counted and left out of BOTH arms, and the count is
   reported. "Held" is tier-aware (lead ruling 2026-11-13, 10.2 h15,
   [[task-10.2-plan-10-injection-dedup#open-held-tier]]): an item is held only at the tier it was
   shown and poorer ones. The replay applies that rule in its own code. The line is rendered by
   25.1b's line renderer, built in queue item 4 before 10.5 runs. The replay passes held members
   through the renderer's held slot (25.1b k2, which prints `·held`, 10.2 h16), so the line's
   bytes are the real ones without 10.2 existing (bsd-spec-t3ab B1). The line sits last in the
   payload (S2). {#r1b}
2. **R2b The rule is unchanged.** v1/v2's pre-registered rule applies as written: every labelled
   use stays visible and at most 1 R12 explicit use is lost. "Visible" means rendered at any
   tier, or named on the line. An item only on the spill page is NOT visible. The run reports
   block bytes against the v3 baseline, item-line bytes, labelled and R12 visible counts, and the
   share of held members that fell past the names cap. {#r2b}
3. **R3b The outcome.** If the rule holds, its figures are 10.2 R8's parity target and Part 1
   reads PASSED (v3). If it fails, Part 1 reads FAILED (v3), 10.2 is not built, and the result goes
   to the user with an id in `workflow/open-questions.md`. That is the existing precondition
   gate ("10.2 starts only on 10.5's GO"), so no new rule is added. {#r3b}
4. **R4b Order and re-run.** v3 runs in the measurement lane after 25.1b merges and before
   10.2's RED. Its result is appended to [[measurement-injection-already-held-2026-11-13]] as a
   dated `v3` addendum, with counts only.

   Q8 is decided as a: `workflow/` leaves at ingest (G22). v3 is therefore RE-RUN, on the same
   code and windows re-read from the post-exclusion store, after G22's ingest exclusion deploys
   ([[plan-10-injection-dedup#q8-b]]). The re-run's figures replace v3's as 10.2 R8's parity
   target. **10.5 also re-runs 10.2 R8's parity check against that new target** (r2 m5): the
   same replay in parity mode, with `stm.held_items` and 25.1b's `pack(held=…)` imported from
   the deployed `master`. It runs in the measurement lane, in the same session as the re-run,
   right after G22's ingest exclusion deploys, and both results go in the same dated addendum.
   If the re-run fails R2b's rule, Part 1 reads FAILED (v3, re-run): 10.2 is not built, or if it
   has already merged, the result goes to the user with an id, which is R3b's path. A parity
   mismatch is a defect: it is logged in `workflow/bug_registry.md` and fixed in 10.2's code or
   the replay before the addendum closes. {#r4b}

## Part 2: read-back probe — to run, bands written first {#part-2}

1. **R1 The probe.** 50 scripted sessions (25 per payload: `prompt-recall`, `scan-prompt`) in a
   SCRATCH Claude Code project (never this repo's settings, 25.1 R0's rule), on 25.1's synthetic
   fixture memories and code. Each session: a prompt whose hook output carries item X in full;
   1-7 filler prompts; then a prompt whose hook output names X only as a held member of 25.1b's
   `still in play` line (the payload's last block, marked `X·held`). It is rendered by 25.1b's
   line renderer through its held slot, which exists from queue item 4, so it is exactly what
   10.2 will print, and
   whose question needs a fact that appears only in X's earlier full rendering. Scored by a script:
   correct when the answer carries that fact, or the agent fetches X (`rmx memory get` / `Read` /
   `rmx context`) and then carries it, without asking. Synthetic text only; transcripts stay
   local; counts committed. {#r1}
2. **R2 Control.** The same 50 with X rendered in full on the last prompt (today's behaviour), so
   the probe measures the names line, not the task's difficulty. {#r2}
3. **R3 Bands, written here before any probe:** names-only correct ≥ 45/50 and within 3 of the
   control → GO for 10.2; 40-44, or 4-7 below the control → the user decides; < 40, or 8 or more
   below the control → NO-GO (10.2 is not built; payloads stay full). {#r3}

## Acceptance criteria {#acceptance}

1. **AC-1 Order.** R3's bands are in a commit older than the first commit holding any probe
   result. Mutation: a result committed in or before the bands' commit (the order check fails).
2. **AC-2 Scorer.** The scorer, run on 6 hand-labelled transcripts (3 correct, 3 not, synthetic),
   reproduces the labels. Mutations: the scorer counts a fetch without the fact as correct; it
   counts "asked the user" as correct.
3. **AC-3 Counts only.** No committed file holds prompt, answer or memory text. Mutation: a
   fixture prompt string written into the result file (a scan of committed files for the
   fixture's sentinel strings fails).
4. **AC-4 v3 independence (Part 1b).** A structural test parses the v3 replay script. It imports
   25.1b's `recall_pack.pack` and line renderer from `src/`, and it does NOT import
   `stm.held_items`, `stm.record_full` or `pack(held=…)`'s held path for the v3 run (only the R8
   parity mode may). Mutation: the v3 run imports `stm.held_items`. That is the tautology R1b
   warns against, and the test fails.
5. **AC-5 v3 arithmetic.** On a 3-call synthetic fixture with hand-computed held sets (one
   pointer-then-body item, one body-then-pointer item, one over-cap held item), the replay's
   tier-pinned payload, visible counts and block bytes equal the hand values. Mutations: tier
   ignored in held (the pointer-then-body item is named instead of bodied); a non-held row
   promoted into freed bytes.

## Files {#files}

| file | change |
|---|---|
| `eval/production/names_only/probe/` (new) | R1's scratch-project harness and scorer |
| `tests/test_task10_5_probe_scorer.py` (new) | AC-1, AC-2, AC-3 |
| `tests/test_task10_5_v3_replay.py` (new) | AC-4, AC-5 |
| `workflow/measurements/names-only-2026-11.md` (new; 10.2 appends its live run) | part 2's result and verdict |

## Definition of done {#done}

- Part 2's verdict written with its band named; anything handed to the user raised with an id in
  `workflow/open-questions.md`.
- Committed on branch `task-10.5-names-only-probe`; merged `--no-ff` to `master`.

## History: the block-diff gate, closed (Q11) {#history}

This task first gated 19.6's versioned injection (R5 / R6) on the two per-prompt payloads. Its
provisional replay below put the block diff at NO-GO under 19.6's confirmed bands; the user then
chose not to use 19.6's block diff for these payloads (Q11), and that NO-GO stands. Kept as the
record; nothing in it is to be built.

### The block-diff state definition (pre-registered at `308edc8`) {#state}

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

### Block-diff decisions {#decisions-block-diff}

| # | decision | reason |
|---|---|---|
| d1 | **ANSWERED by Q11 (block diff not used for these payloads).** Was: Judge the per-prompt blocks on Table B directly; record Table A, do not let it close them. {#d1} | Table A measures whole-block identity; a per-prompt block changes every prompt by construction (computed 2026-11-13: `prompt-recall` 0.00% / 3.32%, `scan-prompt` 0.00% / 0.00%, [[plan-10-injection-dedup#context-table-a]]); its < 3% band would close both ids ("NO-GO for that block id, closed") before Table B, which measures what an add-only delta saves, is consulted. Changing which table governs a block id is a band change and needs a decision-log row (19.6 R0). If the user declines, plan-10's dedupe ends here and 10.2 is not built |
| d2 | K stays 8 | user-confirmed for R6 (d9v); the reopened suppression's "k" IS K here: an item is omitted at most `K − 1` consecutive revs; units with ≥ 6 earlier deliveries (1,461 + 555 = 2,016, 27% of re-delivered units) are the chronic repeaters a keyframe re-shows once per 8 revs. A different K needs its own row |
| d4 | **ANSWERED by Q11 (became user question Q11; answered with design 4+3, then Q13 names-only).** Was: Under the confirmed bands the per-prompt blocks are NO-GO. Options: (a) accept NO-GO: plan-10 ships 10.4 (and 10.3 for 19.6), no per-prompt dedupe; (b) change three confirmed rules for these two ids only — Table B governs instead of Table A, the half-block rule is waived for add-only deltas, and Table B is judged on aggregate omitted bytes, not the median — then run R2-R4 formally (projected ~16-21% of item bytes, `x = 3` of 13 in the "user decides" band); (c) another design for these blocks (the withdrawn pointer, or a delta plus a names-only "in play" line), which Q7 steered away from {#d4} | the data does not support the context diff on per-prompt blocks as 19.6 pre-registered it; every route forward changes a user-confirmed rule or a user decision. Recommendation: (a) now — 10.4 removes injection on about half of all hook prompts with no new state; re-run this gate on human prompts only after 10.4's R5 (the measurement's human-only held share is 32.5%, against 48.0% overall), and choose (b) or (c) then if the saving still matters |
| d3 | The labelled-use check uses the existing lbl-215 pilot labels (13 used pairs) for a provisional verdict and is re-run final at ≥ 40 used pairs | n = 13 cannot separate 10% from 25% (the measurement's Wilson interval for 6 / 13 is 23-71%); a provisional verdict lets 10.2's RED start, the final one gates the deploy |

### Block-diff requirements (not run beyond the provisional replay) {#requirements-block-diff}

1. **R1 Table A, recorded.** Over two independent frozen session sets (19.6's worse-of-two rule;
   the 2026-11-13 windows are set 1, a later window ≥ 7 days after deploy of 10.4 is set 2), per
   block id: the share of emitted payload bytes whose `block_sha` equals the previous rev's, from
   21.1's events (hook calls with a session). Recorded with its band; under [[#d1]] = yes it does
   not decide. {#bd-r1}
2. **R2 Table B, delta size.** Replay each set's `delivered` events per (session, block) in time
   order under [[#state]], with compaction markers taken from the transcripts'
   `compact_boundary` records (the sessions' own files, read in place, counts only). Report per
   block id and per set: the median of `delta bytes / full bytes` over non-cadence revs (the
   quantity R6's half-block rule reads; bytes = the items' delivered span bytes, so headers and
   bodies are excluded and stated); the share of revs that become keyframes by cadence, by marker,
   by the half-block rule; the share of items and of item bytes omitted; the share of RE-DELIVERED
   items omitted (against the measurement's 46.7%); the cross-block re-deliveries (earlier delivery
   on the other block only), which this design never omits. {#bd-r2}
3. **R3 Table B, read-back correctness.** A probe set of 50 patched blocks (25 per block id),
   run in a SCRATCH Claude Code project (never this repo's settings, 25.1 R0's rule), on 25.1's
   synthetic fixture memories: each probe is a scripted session whose hook output is a keyframe
   followed by 1-7 deltas, then a question whose answer needs an item that the LAST delta omitted
   (present only in an earlier rev); scored by a script on whether the answer uses that item's
   content, or the agent fetches it, without re-asking. Correctness = scored-correct / 50, per
   block id and pooled. Synthetic text only; transcripts stay local; counts committed. {#bd-r3}
4. **R4 The labelled-use check (pre-registered here).** For each lbl-215 delivered pair labelled
   CAUSED or INFORMED (13 at 2026-11-13; matched to delivered units exactly as `dd-10r`'s
   `cost.py` matched them), decide whether [[#state]] would have OMITTED that unit (an earlier
   delivery of the same item on the same block, since the block's last keyframe, no marker
   between). `x` = omitted used units. {#bd-r4}
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
   commit of this spec named as the pre-registration. {#bd-r5}

### Provisional run, 2026-11-13 (after the pre-registration commit `308edc8`) {#provisional}

Read-only replay of [[#state]] over `dd-10r`'s delivered units (the 2026-11-13 windows: refmatrix
2026-10-20..11-13, cliquedb 2026-11-04..11-11), compaction boundaries from the sessions' own
transcripts (every session had one). Counts only; item span bytes (bodies and headers excluded;
`body_bytes` is null on every event); non-human prompts are still revs here (10.4 not built). Not
the formal R1-R3 run (one window per store, no read-back probe). Script: the session scratchpad
`arch10r/replay.py`. {#provisional-scope}

| | refmatrix | cliquedb |
|---|---|---|
| revs (both blocks) | 684 | 703 |
| keyframes by the half-block rule | 607 (89%) | 606 (86%) |
| delta / unchanged revs | 39 / 15 | 52 / 29 |
| **Table B median delta / full** | **1.000** (p25 0.901) | **1.000** (p25 0.863) |
| items omitted (bytes) | 2.8% (2.5%) | 5.7% (5.4%) |
| re-delivered items omitted | 266 of 4,170 (6.4%) | 347 of 3,193 (10.9%) |
| cross-block-only re-deliveries | 24 | 14 |

**R4, provisional (n = 13 used pairs, all matched): `x = 0`** → band "ON (provisional)".
{#provisional-result}

**Verdict under the pre-registered bands: NO-GO for both block ids.** Table A < 3% (0.00-3.32%)
closes them unless [[#d1]] says otherwise, and even then Table B's median is 1.000 (> 50% →
"NO-GO: keyframes only"). The mechanism: a per-prompt block's items are mostly new each prompt,
so the half-block rule fires on ~87% of revs, every such keyframe resets the state to one prompt's
items, and the add-only state never accumulates. {#provisional-verdict}

**Sensitivity, NOT pre-registered** (each row changes a user-confirmed d9v rule, so none is a
verdict):

| variant | median delta / full | items omitted (bytes) | re-deliveries omitted | R4 `x` of 13 |
|---|---|---|---|---|
| K = 8, half-block rule waived for add-only blocks | 0.930 / 0.861 | 16.7% (15.9%) / 21.0% (20.9%) | 38.4% / 40.2% | 3 (2 scan, 1 recall) |
| K = 4, half-block rule waived | 1.000 / 1.000 | 9.7% / 12.6% | 22.4% / 24.2% | 1 |

The half-block rule exists because a large PATCH is harder to apply than a keyframe; an add-only
delta is a subset of the keyframe's own lines, so for these blocks the rule costs bytes and resets
the state without a readability gain. Waiving it is the only variant that saves a fifth of the
bytes, and even then Table B's MEDIAN stays above 50% (most prompts are mostly new; the saving is
concentrated in a minority of revs), so Table B as written still says NO-GO; and `x = 3` sits in
the "user decides" band. {#provisional-sensitivity}

For comparison, the withdrawn per-item pointer (window N = 10) would have degraded about 68% of
re-deliveries (gaps 1-10, [[plan-10-injection-dedup#context-2026-11-13]]) to a line that still
names the item, against 38-40% omitted outright here at best.

## Revision round 6 (2026-11-13, spec wave, spec-t3b) {#rev-round-6}

Driven by G11 and L15 and L30 ([[plan-review-2026-11-13#lead]]), and by contra-b CB-1 ("R8 parity
figures re-derived"). Part 1b (v3) re-runs the v2 replay on 25.1b's pack, with the same rule. Its
figures become 10.2 R8's parity target, and a failure is the existing precondition gate. The probe
prints X the way 10.2 will, as a held member of 25.1b's line. Under L30 the probe runs after T4.

rel: derives-from -> [[plan-review-2026-11-13#lead]]

**bsd-spec-t3ab r1 folded (2026-11-13, lead rulings).** B1: v3 and the probe render the line
through 25.1b's held slot, which prints `·held`, so the gate runs before 10.2 exists. S2: the
line is last. S6: Q8 = a, so v3 is re-run after G22's ingest exclusion deploys (R4b). m4: AC-1 to
AC-3 gain mutations, and AC-4/AC-5 cover Part 1b. {#rev-round-6-bsd}

rel: derives-from -> [[bsd-spec-t3ab-ff1d453-369e0b5]]

**bsd-spec-t3ab r2 m5 folded (2026-11-13).** R4b's post-G22 re-run also re-runs 10.2 R8's parity
check against the new target. 10.5 runs it, in the measurement lane, right after G22 deploys.
{#rev-round-6-bsd-r2}
