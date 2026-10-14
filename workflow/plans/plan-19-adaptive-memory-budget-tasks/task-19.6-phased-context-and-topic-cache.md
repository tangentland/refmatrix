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
> (sandbox); and the user's confirmation of the PROPOSED [[#ranges]] (d9f), before any work starts.
> 19.2 is not needed: read-back is scored from 21.1's `used` events and this task's transcript
> scorer ([[#ranges]]), not from 19.2's counters.

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

0. **R0 Pre-registration, PROPOSED until the user confirms** (d9f). The comparison criteria,
   the go/no-go tables of [[#ranges]] (A, B, C, D), the phase thresholds of [[#ranges-thresholds]],
   `N = 8`, `K = 8` and the collapsed-line cap `C = 6` (R9) are PROPOSED numbers. The user confirms or amends them in a decision-log
   row BEFORE 19.6 starts (Wave 3, after 19.5's baseline exists); no measurement or code of this
   task runs before that row. After confirmation, changing a band needs a new decision-log row
   ([[feedback_go_no_go_ranges_not_predrop]], [[project_helix_phase2_decision_criterion]]).
1. **R1 Measure the stable blocks first** ([[exploration-session-phased-context#vi-evidence]]).
   Over a frozen set of real sessions (kept local per d8f; only hashes and counts committed), for
   each stable block id (`stm-topic-composite`, the recall pack, scan-prompt's bundle): the share
   of emitted bytes byte-identical to the previous rev of the same id, and the delta-size
   distribution (delta bytes / block bytes). Table A decides R5/R6.
2. **R2 Phase classification, against the STM state BEFORE this prompt** (round-3 #b-2). The
   recall and scan hooks run in parallel with `focus hook --event input`, and `Stm.record` appends
   the input event AND ingests the prompt's terms into `focus.json` in one call
   (`stm.py:246-282`); if the input hook wins, this prompt's own terms are already members of the
   active cluster and every prompt would read `warm` by construction. So the phase, its overlap
   scores, the matched cluster and the cache lookup are ALL computed from ONE
   `stm.pre_prompt_state(root, session, prompt, *, t0)` call (specified in
   [[task-21.1-context-usage-telemetry#req-session]] 21.1 R9; written by 19.0 R7's
   `snapshot_pre_prompt` before the input hook touches the ring, the graph or the cache). Its
   `graph` and `topic_cache` are the state before this prompt whichever hook ran first; no phase
   code reads `focus.json`, the ring or the cache file directly. The event logs `stm_source`.
   - **cold**: no focus topics yet, or the prompt carries no concrete terms;
   - **warm**: the prompt's terms overlap the active topic cluster;
   - **return**: they overlap a CACHED inactive cluster (R3);
   - **new**: they overlap neither.

   "Overlap" uses the PROPOSED thresholds of [[#ranges-thresholds]], applied in that table's
   order. Raw inputs (overlap scores, the matched cluster, thresholds) are logged on every event.
   **Turn count is logged and is never a phase signal** (d5b).
3. **R3 Topic cache** (#topic-cache). Every cluster that loses focus is snapshotted, keyed by its
   member set, in a per-session LRU of `N = 8` clusters, keyed by the session of 19.0 R5's
   resolver (never `latest_session`). The cache file is updated only by the input hook, AFTER
   `snapshot_pre_prompt` has copied the previous cache into `pre.json` (R2), so a reader never
   sees this prompt's own eviction or restore. A return (Jaccard overlap of the prompt's terms with a cached
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
   return, `block_id`, `rev`, `unchanged: bool`, and `turn` (logged only).
   **Arm assignment is PER PROMPT** (re-review #s-4): `arm = ["fixed", "phased",
   "phased+cache"][int(sha256(session_id + "\0" + sha256(prompt_text)), 16) % 3]`, computed
   identically by both UserPromptSubmit hooks from the same envelope, so one prompt's recall and
   scan-prompt share an arm, and topic and day are balanced across arms within each session. The
   `fixed` arm is a LIVE concurrent arm, not a historical baseline.
   - **Channels without a prompt** (round-3 #m-5). `session_start` and `precompact` have no
     prompt text, so the per-prompt formula is undefined for them. They are NOT randomized: they
     always run the `fixed` allocation and log `arm = "fixed"`, `policy = "fixed-v0"`, and Table C
     counts only `prompt_recall` and `scan_prompt` deliveries.
   - **Carryover, a known limit, stated in Table C's report.** All three arms share ONE context
     window per session: a body delivered under `phased` on prompt 7 is still in the window when
     prompt 8 runs under `fixed`, and a read-back on prompt 8 may be caused by either. Per-prompt
     assignment balances this across arms but does not remove it; the report states it and also
     prints the lift restricted to read-backs whose delivering prompt and reading prompt share an
     arm.
8a. **R8a "In the window", defined** (re-review #m-5). A hook cannot see the context window.
   "In the window" means: emitted for this session since the last COMPACTION MARKER this session
   recorded. The marker is written into the session's last-emitted state (R5) by a dedicated
   command, `rmx focus hook --event compact-marker` (round-3 #m-5: the writer is named), which
   this task adds as its OWN generated PreCompact hook entry, separate from the PreCompact recall
   and summarize entries, so it survives if 19.5 R1(c) removes the PreCompact recall; the same
   command runs from 19.0 R5's `session-start` hook when the SessionStart envelope's `source` is
   `compact` and R8's probe shows the harness sends one. A test asserts the generated config
   holds the marker entry with and without the PreCompact recall (AC-7f). Every R5 / R6 "known to be in the window" check reads that state; after a
   marker, nothing is in the window and the next emission of each block is a full body.
8. **R8 Verify the compaction lever.** Whether a PreCompact hook can steer the compaction summary
   is checked (with 19.5 R1(c)'s scratch project) before any requirement relies on it; the result
   is recorded, together with whether a post-compaction SessionStart carries `source=compact`
   (R8a).
9. **R9 The STM composite renders as an expand/collapse tree** (the user, 2026-10-14;
   [[exploration-session-phased-context#tree-render]]).
   - **Expanded:** exactly the cluster the phase selects (warm: the overlapping cluster; return:
     the restored one), rendered as today: members plus `rel:` lines under the current depth
     rules (lift-ranked co-occurs, sparse-first LTM).
   - **Collapsed** (round-3 #s-4): every other cluster, up to a cap, renders as ONE line holding
     ONLY its frozen label and its stable cluster id: `▸ topic: <label>  (id <cid>)`. Nothing
     else moves with it: no event count, no ring line range, no turn counter, timestamp, rank or
     relative age.
     - **Unchanged, defined.** A cluster is unchanged while its MEMBER SET is unchanged. `<cid>` is
       a hash of that member set (as 19.4 R6 names unlabeled subjects). `<label>` is FROZEN when
       the cluster is first rendered collapsed (the head member by focus weight at that moment)
       and stored with the cluster in the session's last-emitted state; a reorder of member
       weights (`topic_composites` sorts by `weight`, `stm.py:790-813`) does not change it, and a
       member-set change mints a new `<cid>` and a new frozen label. So the line's bytes are a
       function of the member set alone.
     - **Counts and ranges move to the expanded view.** The event count and the `L<a>–L<b>` range
       are printed only on the EXPANDED cluster's header line and by `rmx focus topics`, never on
       a collapsed line.
     - **Cap.** At most `C = 6` collapsed lines (PROPOSED with the other numbers, d9f): the `C`
       clusters most recently first-collapsed, rendered in a stable order (first-collapsed time,
       oldest first, ties by `<cid>`), so each shown line keeps its bytes while it stays shown. Beyond `C`, one line
       `▸ +<m> more topics (rmx focus topics)`; that line changes when `m` changes and is
       versioned like any other block line (not claimed byte-stable).
   - **Cold** (and `new`, which spends breadth): every cluster collapsed (up to `C`); no expanded
     cluster.
   - **The collapsed line is the topic cache's re-expand handle** (R3), and it is BYTE-STABLE
     across turns while its member set is unchanged, so versioned injection (R5) can send it as
     "unchanged".
   - **Single-expand vs expand-top-2** is decided by R10's measurement against Table D, not
     assumed.
   - **Prerequisite:** a collapsed line is only its label, so label quality depends on 19.0; a
     junk label (`re.searc`) makes the line useless. 19.0 is a hard prerequisite (header).
10. **R10 Measure cross-cluster overlap first.** Before R9's expand rule is chosen, a script over
    the frozen session sets of R1 records, for every prompt, how many of the session's live STM
    clusters its terms hit under [[#ranges-thresholds]]'s warm threshold: 0, 1, or ≥ 2. Table D
    decides single-expand vs expand-top-2. This is a NEW measurement: the near-zero overlap
    figure (median carried 0.000) is plan-10's, between CONSECUTIVE scan-prompt content hits
    ([[plan-10-injection-dedup]]), not between STM clusters, and is not cited as an STM-cluster
    number here.

## Pre-registered go/no-go ranges, PROPOSED (d9f) {#ranges}

**Status: PROPOSED.** Every number in this section, plus `N = 8` (R3), `K = 8` (R6) and `C = 6`
(R9), awaits the
user's confirmation in a decision-log row before 19.6 starts (R0). Each verdict takes the worse of
two independent frozen session sets (d4d's quiet/loaded rule applied to session sets).

**Read-back, ONE definition** (re-review #s-4; settles plan-21 open item 2). A delivered memory
item is READ BACK when, later in the same session, any of these points at it by `name` (or, for a
file, its path or `doc-id#anchor`): a 21.1 R12 `used` event (`memory_get_by_name`,
`context_by_name`, `focus_note`) whose `ref_query_id` is the delivering call; a later tool call
whose input names it (`file_read`); or a later assistant message that contains it as a whole token
(`cited_in_answer`). The last two come from the transcript scorer, which is this task's
`eval/production/phased_context/score_readback.py`: it reads local transcripts (d8f), writes only
its report (hashes and counts committed), and NEVER appends to `recall-events.jsonl`, so no live
counter depends on it. Metric: `readback_per_1k = read-back items / (delivered payload bytes /
1000)`, per arm.

**Phase thresholds (R2, R3):** {#ranges-thresholds}

| phase | rule, applied in this order | proposed number |
|---|---|---|
| cold | the session has 0 focus topics, or the prompt has 0 concrete terms (terms surviving `scan._PROMPT_STOPWORDS` and 19.0's code-noise set) | — |
| warm | shared terms with the ACTIVE cluster's members ≥ `w_min`, or Jaccard(prompt terms, active members) ≥ `j_warm` | `w_min = 2`, `j_warm = 0.15` |
| return | not warm, and Jaccard(prompt terms, a CACHED cluster's members) ≥ `j_return`, the highest-Jaccard cached cluster wins (ties: most recently cached) | `j_return = 0.20` |
| new | none of the above | — |

**Table A — unchanged lines (R1's byte-identical share, per block id):** {#ranges-a}

| share | verdict |
|---|---|
| ≥ 30% | GO: R5 for that block id |
| 10–30% | GO, gated: R5 only for the composite and the session-start pack; report bytes saved |
| 3–10% | NOT YET: measure Table B's delta sizes; build R6 if Table B says GO; else re-measure ONCE on the next frozen session set collected ≥ 30 days after R1's run, and that second result is final (the old "after 19.0" trigger is void: 19.0 is a hard prerequisite and is already done) |
| < 3% | NO-GO for that block id (closed; recorded) |

**Table B — deltas (median delta / block, and read-back correctness of a patched state on a
probe set of 50 patched blocks):** {#ranges-b}

| condition | verdict |
|---|---|
| median ≤ 25% and correctness ≥ 95% | GO: R6 |
| median ≤ 50% and correctness 80–95% | GO, gated: add-only deltas; drops go as keyframes |
| correctness < 80% | NO-GO for deltas; "unchanged" lines only |
| median > 50% | NO-GO: keyframes only |

**Table C — phased vs fixed, then phased+cache vs phased (`readback_per_1k`, arms assigned per
prompt by R7 and run CONCURRENTLY, n ≥ 200 prompts per arm):** {#ranges-c}

Validity check before any verdict: the live `fixed` arm's median delivered bytes and distinct
memories per channel must lie within ±15% of 19.5 R4's `baseline-fixed.json`; outside it, the run
is invalid (recorded) and repeated, because the fixed path itself has drifted. The baseline holds
no read-back and is never the comparison's denominator.

| relative lift | verdict |
|---|---|
| ≥ +20% | GO: the arm becomes the default |
| +5% to +20% | GO, gated: the arm only on the phases where its lift holds; re-measure with n doubled |
| −5% to +5% | NOT YET: keep the current default; report; re-measure once with n doubled, and that result is final |
| < −5% | NO-GO: the arm is closed (recorded) |

**Table D — cross-cluster overlap (R10: share of non-cold prompts whose terms hit ≥ 2 clusters at
the warm threshold):** {#ranges-d}

| share hitting ≥ 2 clusters | verdict |
|---|---|
| < 15% | single-expand: only the selected cluster is expanded |
| 15–40% | expand-top-2: the two highest-overlap clusters expanded when the prompt hits ≥ 2; single otherwise |
| > 40% | NOT YET: clusters overlap too much to separate; re-check 19.0's clustering, re-measure once, then apply this table again |

## Acceptance criteria {#acceptance}

1. Tables A–D, the thresholds and the criteria are committed in this spec, AND the user's
   confirming decision-log row (d9f) exists, before R1's first run (git history shows the
   order).
2. R1's table and each verdict are in the implementation summary, computed by a script from the
   frozen sets (hashes committed, sessions local).
3. **Phase fixtures** (sandbox, fixture rings from 19.0's redacted fixture): an empty ring →
   cold; a prompt overlapping the active cluster → warm; a prompt overlapping a cluster that lost
   focus three topics ago → return, with that cluster restored; a disjoint prompt → new. A
   turn-40 prompt on a new topic is `new`, not warm.
3b. **Thresholds bite** (re-review #s-4). Boundary fixtures under the confirmed numbers: a prompt
   sharing exactly `w_min` terms with the active cluster is warm, one sharing `w_min − 1` (and
   Jaccard below `j_warm`) is not; a cached cluster at Jaccard `j_return` is restored, one at
   `j_return − 0.01` is not. Mutation: any threshold changed by one step flips one of them.
3c. **The phase does not depend on which hook ran first** (round-3 #b-2). For each of the four
   AC-3 fixtures, and for a `return` fixture whose prompt would also evict the active cluster
   into the cache, the same envelope is classified three ways, as 21.1 AC-8b orders them: the
   input hook (the generated `focus hook --event input`) completed before the classifier starts,
   after it finishes, and stopped after `Stm.snapshot_pre_prompt` only. All three give the same
   `phase`, the same `overlap` scores, the same matched cluster and the same
   `restored_cluster_id`; the first and third log `stm_source=snapshot`. The warm fixture's
   prompt terms are chosen so that, read from the post-ingest `focus.json`, they WOULD exceed
   `w_min` against a cluster they do not overlap before the prompt (a non-vacuous fixture,
   pre-checked by reading `focus.json` after the input hook).
4. **Session scope.** Two sessions' caches in one STM dir: a return in session A never restores
   session B's cluster.
5. **LRU bound.** Ten clusters lose focus; the cache holds 8; the oldest two are evicted and
   counted.
6. **Unchanged** (if Table A says GO). Emitting the same block twice in a session yields one body
   and one `<id> rev N unchanged` line; after a compaction marker the next emission is a full
   body.
7. **Events.** Every injection event carries the R7 fields; `turn` is never read by the phase
   code (a test sets `turn` to random values and the phases are unchanged).
7b. **Arm per prompt.** The recall hook and the scan-prompt hook fed the same envelope log the
   same `arm`; over 300 synthetic prompts in 3 sessions each arm gets 100 ± 25 prompts, and every
   session has prompts in all three arms. The generated SessionStart and PreCompact recall runs
   log `arm = "fixed"` on every event (round-3 #m-5).
7c. **Tree: non-selected clusters are one line** (R9). On a warm fixture with 4 clusters, the
   composite has exactly one expanded cluster (a header with its event count and line range,
   then members + `rel:` lines) and exactly 3 collapsed lines, each exactly
   `▸ topic: <label>  (id <cid>)` (a regex over the whole line; no digits outside `<cid>` and the
   label).
7d. **Tree: collapsed line byte-stable** (R9; round-3 #s-4). Two consecutive turns in which a
   non-selected cluster's MEMBER SET does not change render that cluster's collapsed line
   byte-identically (compared as bytes), although between them: THAT cluster is re-touched (a
   tool event adds to its event count and moves its line range) and its member weights reorder
   so a different member would be the head by weight; the turn count changes; the active cluster
   changes. A third turn that adds one member to it renders a new `<cid>` (and a new frozen
   label line).
7e. **Tree: cold expands nothing** (R9). On a cold fixture (no concrete terms) every cluster
   renders collapsed and no `rel:` or member line appears.
7f. **Window marker** (R8a). After the GENERATED PreCompact marker entry
   (`rmx focus hook --event compact-marker`) runs, a block emitted earlier in the session is
   re-sent in full, and a topic return emits the body, not `re-activate`. The generator test
   asserts that the marker entry is present both with and without the PreCompact recall entry
   (round-3 #m-5).
7g. **Tree: collapsed lines are capped** (R9). With 10 non-selected clusters, exactly `C`
   collapsed lines and one `▸ +4 more topics` line render; the `C` shown are the most recently
   first-collapsed, in first-collapsed order; adding an 11th cluster drops the oldest shown line
   and leaves the other `C − 1` lines byte-identical.
8. **Isolation.** 23.0's guard records 0 live connects for this task's test files.
9. **Mutations that must FAIL a test:**
   - phase driven by turn count (AC-7);
   - the cache keyed by `latest_session` (AC-4);
   - no LRU bound (AC-5);
   - "unchanged" emitted after a compaction (AC-6);
   - a delta against a rev not in the window (if R6 is built);
   - arm chosen per session instead of per prompt (AC-7b);
   - a threshold moved one step (AC-3b);
   - collapsed lines carrying a turn number or relative age (AC-7d);
   - collapsed lines carrying the event count or line range (AC-7c's regex; AC-7d's re-touch);
   - the label taken live from the head member by weight instead of frozen (AC-7d's reorder);
   - no cap on collapsed lines, or a cap ordered by recent activity (AC-7g);
   - any phase input read from `focus.json` / the ring / the cache file instead of
     `pre_prompt_state` (AC-3c: the input-hook-first run reads `warm`);
   - the cache updated before `snapshot_pre_prompt` (AC-3c's evicting `return` fixture);
   - the marker written only by the PreCompact recall command (AC-7f with the recall entry
     removed);
   - `session_start` / `precompact` randomized across arms (AC-7b);
   - expanding the top cluster on cold (AC-7e);
   - a non-selected cluster rendered with its members (AC-7c);
   - the window state not reset by the PreCompact marker (AC-7f).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | phase classification over `pre_prompt_state` (R2) with the thresholds; the topic cache (snapshot, LRU, restore; written after `snapshot_pre_prompt`, R3); the expand/collapse composite render (R9): stable cluster ids, frozen labels, the cap `C` |
| `src/refmatrix/cli.py` (`focus hook`), `hooks.py` | `--event compact-marker` and its own generated PreCompact entry (R8a) |
| `src/refmatrix/scan.py` | phase-aware allocation of scan-prompt's spend; block ids and revs |
| `src/refmatrix/cli.py` / `verbs.py` (`memory recall`) | phase-aware pack allocation; block ids and revs |
| `src/refmatrix/hooks.py` | pass the envelope to both hooks; arm selection (prompt channels only, R7) |
| `eval/production/phased_context/` | R1, R10 (cross-cluster overlap) and Table C scripts; `score_readback.py` (the ONE transcript scorer); committed hashes and counts only |

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
  carried 0.000 against 0.40, [[plan-10-injection-dedup]]). That number is consecutive
  scan-prompt CONTENT overlap; it says nothing about overlap between STM clusters (R10).
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

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]], [[plan-review-2026-10-14#t9]] (d9f) and the
user's 2026-10-14 tree-render addition ([[exploration-session-phased-context#tree-render]]).

| finding / decision | answered at |
|---|---|
| d9f (tables A-C, N=8, K=8 PROPOSED; user confirms before 19.6 starts) | R0; [[#ranges]] status line; AC-1 |
| re-review #s-4 (baseline lacks read-back; two read-back definitions; per-session confounding; no thresholds; expired anchor) | R7 (per-prompt arm, live `fixed` arm); [[#ranges]] (one read-back definition, `score_readback.py`), [[#ranges-thresholds]] (PROPOSED numbers), [[#ranges-c]] (baseline as validity check only), [[#ranges-a]] (concrete re-measure trigger); AC-3b, AC-7b; mutations |
| plan-21 open item 2 (transcript scorer owner) | [[#ranges]] read-back paragraph (`score_readback.py`, never appends to the live log) |
| re-review #m-5 ("in the window") | R8a, R8; AC-7f |
| user, 2026-10-14: expand/collapse tree; measure overlap first; three ACs; 19.0 prerequisite | R9, R10, [[#ranges-d]] (PROPOSED); AC-7c, AC-7d, AC-7e; mutations |
| correction: plan-10's 0.000 is consecutive scan-prompt content overlap, not STM clusters | R10; [[#out-of-scope]] |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan19-21-spec-rereview-r3-6091648]]. Code facts re-read at `636b210` (read-only):
`stm.py:246-282` (append then ingest in one call), `:405-445` (`focus.json` by tmp +
`replace`), `:790-813` (`topic_composites` sorts by `weight`); `hooks.py:318-345` (the PreCompact
entries). The tables, thresholds, `N`, `K` and the new `C` stay PROPOSED (d9f).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r3-6091648]]

| finding / decision | answered at |
|---|---|
| round-3 #b-2 (19.6 R2 "reads the ring as it stood before the prompt" had no mechanism; the race biases toward `warm` and inflates `return`) | R2 (every phase input from ONE `stm.pre_prompt_state` call; 21.1 R9 / 19.0 R7); R3 (cache updated after the snapshot); AC-3c (three orderings, an evicting `return` fixture, a non-vacuous warm fixture); mutations |
| round-3 #s-4 (collapsed line not byte-stable; label moves; AC-7d held the wrong thing fixed; no cap) | R9 Collapsed (label + id only; label frozen at first collapse; counts and ranges on the expanded header; cap `C = 6`, PROPOSED); R0 and [[#ranges]] status (C added); AC-7c (whole-line regex), AC-7d (re-touch and weight reorder of THAT cluster), AC-7g (cap); mutations; exploration [[exploration-session-phased-context#tree-render]] updated to match |
| round-3 #m-5 (marker writer unnamed; arm for non-prompt channels; carryover) | R8a (`focus hook --event compact-marker`, its own PreCompact entry); R7 (session_start / precompact always `fixed`; carryover stated, same-arm lift printed); AC-7b, AC-7f; mutations |
| round-3 #m-6 (exploration `#shape` `shift` row; `#decisions` stale) | [[exploration-session-phased-context#shape]] (row replaced by return/new), [[exploration-session-phased-context#decisions]] (closed by d5b) |
| d9f (tables stay PROPOSED) | R0; [[#ranges]] (unchanged numbers; `C` added as PROPOSED) |
