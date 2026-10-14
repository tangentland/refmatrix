---
gmd: "0.1"
id: task-19.6-phased-context-and-topic-cache
title: "Task 19.6: the per-prompt budget (recall and scan-prompt) is spent by STM phase, a returning topic re-warms from a cache, and stable blocks are versioned instead of re-sent"
tags: [task, memory, scan-prompt, stm, budget, phasing, topic-cache, versioned-injection, plan-19]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
---

# Task 19.6: phased context, topic cache and versioned injection {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 3 (d5b).
> Depends on: 19.0 (clean STM clusters, envelope session; d5e); 19.1 (the packer with an
> allocation knob, and d8a's subject exclusion); 19.5 R1 (per-hook vs per-event cap) and 19.5 R4
> (the fixed baseline); 21.1 (the recall-event fields this task reads, listed in R7); 23.0
> (sandbox). 19.2 is needed only for the `used` read-back that scores the comparison.

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: derives-from -> [[exploration-session-phased-context]]
rel: implements -> [[exploration-session-phased-context#topic-cache]]
rel: implements -> [[exploration-session-phased-context#versioned-injection]]
rel: depends-on -> [[task-19.0-stm-cluster-hygiene]]
rel: depends-on -> [[task-19.1-pack-recall-under-budget]]
rel: depends-on -> [[task-19.5-measure-delivery]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: depends-on -> [[project_helix_phase2_decision_criterion]]
rel: related-to -> [[plan-10-injection-dedup]]

## Why {#why}

The per-prompt budget is fixed (~10k chars delivered whole); today it is spent the same way on
turn 1 and turn 40. A cold start wants a map (handoff Next, active plans, open bugs); a warm
session wants depth on its topic; a return from a sidetrack wants the depth it already earned, not
a broad rescan ([[exploration-session-phased-context#shape]], #topic-cache). And the stable blocks
(the STM composite, recall packs, topic restores) are re-sent near-identical every turn, although
a hook can only append ([[exploration-session-phased-context#vi-premise]]). Whether any of this
pays is unmeasured; this task measures first and builds against pre-registered ranges. {#why-body}

## Requirements {#requirements}

0. **R0 Pre-registration.** The comparison criteria and the go/no-go tables of
   [[#ranges]] are part of this spec BEFORE any measurement runs; changing a band after R1 starts
   needs a decision-log row ([[feedback_go_no_go_ranges_not_predrop]],
   [[project_helix_phase2_decision_criterion]]).
1. **R1 Measure the stable blocks first** ([[exploration-session-phased-context#vi-evidence]]).
   Over a frozen set of real sessions (kept local per d8f; only hashes and counts committed), for
   each stable block id (`stm-topic-composite`, the recall pack, scan-prompt's bundle): the share
   of emitted bytes byte-identical to the previous rev of the same id, and the delta-size
   distribution (delta bytes / block bytes). Table A decides R5/R6.
2. **R2 Phase classification, against the STM state BEFORE this prompt.** The recall hook runs in
   parallel with `focus hook --event input`, so the phase reads the ring as it stood before the
   prompt; tests do not assume an ordering.
   - **cold**: no focus topics yet, or the prompt carries no concrete terms;
   - **warm**: the prompt's terms overlap the active topic cluster;
   - **return**: they overlap a CACHED inactive cluster (R3);
   - **new**: they overlap neither.

   Raw inputs (overlap scores, the matched cluster, thresholds) are logged on every event. **Turn
   count is logged and is never a phase signal** (d5b).
3. **R3 Topic cache** (#topic-cache). Every cluster that loses focus is snapshotted, keyed by its
   member set, in a per-session LRU of `N = 8` clusters, keyed by the envelope `session_id` (19.0
   R5; never `latest_session`). A return (Jaccard overlap of the prompt's terms with a cached
   cluster ≥ the threshold, logged raw) restores that cluster as the active focus and spends the
   budget as warm.
4. **R4 The whole per-prompt budget is allocated by phase**, across memory recall AND
   scan-prompt (d5b). If 19.5 R1 found the cap per event, the phase decides the split of the one
   budget between the two hooks; if per hook, it decides each hook's internal spend (pointers vs
   bodies vs breadth, through 19.1's allocation knob). cold/new → breadth, pointers over bodies;
   warm/return → depth, bodies and anchors over pointers.
5. **R5 Versioned blocks** (#vi-versioned, #vi-unchanged) — built only in the bands of Table A
   that say so. Every injected stable block carries a stable `id`, a `rev` and the line
   "supersedes earlier revs of `<id>`". A block whose content hash equals the last emitted rev
   for this session emits `<id> rev N unchanged`. A topic return emits
   `re-activate <cluster-id> (rev N)` when that rev is in the window, else the body. The
   session's last-emitted state resets at compaction, and the newest rev is re-sent in full once
   (#vi-compaction).
6. **R6 Deltas, keyframe + delta** (#vi-delta) — built only in the bands of Table B that say so. A
   delta `<id> rev k = rev k-1 + {add: …, drop: …}` only against a rev known to be in the window;
   a full keyframe every `K = 8` revs and after any compaction; a delta over half the block size
   is sent as a keyframe.
7. **R7 Instrumented through 21.1's schema** (C7). Every injection event carries `arm`
   (fixed / phased / phased+cache), `policy`, the raw phase inputs, the restored cluster id on a
   return, `block_id`, `rev`, `unchanged: bool`, and `turn` (logged only). Each arm is a
   configuration, so sessions can be assigned to an arm.
8. **R8 Verify the compaction lever.** Whether a PreCompact hook can steer the compaction summary
   is checked (with 19.5 R1(c)'s scratch project) before any requirement relies on it; the result
   is recorded.

## Pre-registered go/no-go ranges {#ranges}

Each verdict takes the worse of two independent frozen session sets (d4d's quiet/loaded rule
applied to session sets). Read-back = a later tool call or answer in the same session cites an
injected row (its name, path or anchor).

**Table A — unchanged lines (R1's byte-identical share, per block id):** {#ranges-a}

| share | verdict |
|---|---|
| ≥ 30% | GO: R5 for that block id |
| 10–30% | GO, gated: R5 only for the composite and the session-start pack; report bytes saved |
| 3–10% | NOT YET: measure Table B's delta sizes; build R6 if Table B says GO, else re-measure after 19.0 |
| < 3% | NO-GO for that block id (closed; recorded) |

**Table B — deltas (median delta / block, and read-back correctness of a patched state on a
probe set of 50 patched blocks):** {#ranges-b}

| condition | verdict |
|---|---|
| median ≤ 25% and correctness ≥ 95% | GO: R6 |
| median ≤ 50% and correctness 80–95% | GO, gated: add-only deltas; drops go as keyframes |
| correctness < 80% | NO-GO for deltas; "unchanged" lines only |
| median > 50% | NO-GO: keyframes only |

**Table C — phased vs fixed, then phased+cache vs phased (read-back citations per 1k delivered
chars, n ≥ 200 prompts per arm, against 19.5 R4's fixed baseline):** {#ranges-c}

| relative lift | verdict |
|---|---|
| ≥ +20% | GO: the arm becomes the default |
| +5% to +20% | GO, gated: the arm only on the phases where its lift holds; re-measure with n doubled |
| −5% to +5% | NOT YET: keep the current default; report; re-measure once after 19.2's `used` read-back exists |
| < −5% | NO-GO: the arm is closed (recorded) |

## Acceptance criteria {#acceptance}

1. Tables A–C and the criteria are committed in this spec before R1's first run (git history
   shows the order).
2. R1's table and each verdict are in the implementation summary, computed by a script from the
   frozen sets (hashes committed, sessions local).
3. **Phase fixtures** (sandbox, fixture rings from 19.0's redacted fixture): an empty ring →
   cold; a prompt overlapping the active cluster → warm; a prompt overlapping a cluster that lost
   focus three topics ago → return, with that cluster restored; a disjoint prompt → new. A
   turn-40 prompt on a new topic is `new`, not warm.
4. **Session scope.** Two sessions' caches in one STM dir: a return in session A never restores
   session B's cluster.
5. **LRU bound.** Ten clusters lose focus; the cache holds 8; the oldest two are evicted and
   counted.
6. **Unchanged** (if Table A says GO). Emitting the same block twice in a session yields one body
   and one `<id> rev N unchanged` line; after a compaction marker the next emission is a full
   body.
7. **Events.** Every injection event carries the R7 fields; `turn` is never read by the phase
   code (a test sets `turn` to random values and the phases are unchanged).
8. **Isolation.** 23.0's guard records 0 live connects for this task's test files.
9. **Mutations that must FAIL a test:**
   - phase driven by turn count (AC-7);
   - the cache keyed by `latest_session` (AC-4);
   - no LRU bound (AC-5);
   - "unchanged" emitted after a compaction (AC-6);
   - a delta against a rev not in the window (if R6 is built).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | phase classification; the topic cache (snapshot, LRU, restore) |
| `src/refmatrix/scan.py` | phase-aware allocation of scan-prompt's spend; block ids and revs |
| `src/refmatrix/cli.py` / `verbs.py` (`memory recall`) | phase-aware pack allocation; block ids and revs |
| `src/refmatrix/hooks.py` | pass the envelope to both hooks; arm selection |
| `eval/production/phased_context/` | R1 and Table C scripts; committed hashes and counts only |

## Test strategy {#test-strategy}

- **Sandbox:** task 23.0 (tmp `HOME`, global root, registry; injected store roots; spawned `rmx`
  children refuse sockets outside the tmp root; the conftest guard).
- **RED:** AC-3 and AC-4 on fixture rings fail today (no phase, no cache).
- Measurements (R1, Table C) are scripts over frozen session sets, not pytest; their raw inputs
  stay local (d8f).

## Out of scope {#out-of-scope}

- **Expanding a subject hit into its members** (d8a): not planned. `rmx memory recall --subject
  <slug>` is the expansion; recall excludes subject rows (19.1 R2).
- Dedup of scan-prompt's RANKED entries across turns: measured and closed by plan-10 (median
  carried 0.000 against 0.40, [[plan-10-injection-dedup]]).
- Retracting or replacing earlier context: a hook can only append (#vi-premise).

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| d5b (task created; Wave 3; recall AND scan-prompt; deps 19.0, 19.1, d8a, 19.5 probe + baseline, 21.1 fields; turn logged, never a signal) | header, R2, R4, R7, AC-7 |
| d5b: pre-registered go/no-go ranges | R0, [[#ranges]], AC-1 |
| exploration #topic-cache | R3, AC-3, AC-4, AC-5 |
| exploration #versioned-injection, #vi-delta, #vi-compaction | R5, R6, R8, AC-6 |
| exploration #vi-evidence | R1, Table A |
| exploration #prereqs (19.0, instrument, pre-registration) | header, R0, R7 |
| d8a (subject expansion listed here, not left unowned); decision-log #b-6 item 3 | [[#out-of-scope]] |
| 19 #s-10 (phase field, scan-prompt owner) | R4, R7 |
| 19 #placement (phase sees the pre-prompt state) | R2 |
| d8f | R1, [[#test-strategy]] |
