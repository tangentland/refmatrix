---
gmd: "0.1"
id: task-19.6-phased-context-and-topic-cache
title: "Task 19.6: the per-prompt budget (recall and scan-prompt) is spent by STM phase, a returning topic re-warms from a cache, and stable blocks are versioned instead of re-sent"
tags: [task, memory, scan-prompt, stm, budget, phasing, topic-cache, versioned-injection, plan-19]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-15
---

# Task 19.6: phased context, topic cache and versioned injection {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: pulled from Wave 3 to directly after its own dependencies (d9bi, 2026-10-15; was Wave 3,
> d5b). **Helix substrate (d9bi):** the helix plan (Wave 4 draft) builds on this task's frozen
> snapshots (`<cid>`, label, first-collapse `turn`), its topic cache (one writer, one home) and
> its versioned blocks (`block_id`, `rev`, `unchanged` in 21.1's events). `derive_snapshots` and
> `topic_hubs` (R9) are pure functions of (graph, cache), so helix can recompute identity from
> the cache alone; a change to either signature after merge needs a decision-log row naming helix.
> Depends on: 19.0 (clean STM clusters, envelope session; d5e); 19.1 (the packer with an
> allocation knob, and d8a's subject exclusion); 19.5 R1 (per-hook vs per-event cap) and 19.5 R4
> (the fixed baseline); 21.1 (the recall-event fields this task reads, listed in R7); 23.0
> (sandbox). The user CONFIRMED [[#ranges]] as written (d9v, settling d9f), so no confirmation
> gate remains.
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

0. **R0 Pre-registration, CONFIRMED (d9v).** The comparison criteria, the go/no-go tables of
   [[#ranges]] (A, B, C, D), the phase thresholds of [[#ranges-thresholds]], `N = 8`, `K = 8` and
   the collapsed-line cap `C = 6` (R9) are CONFIRMED as written by the user (d9v, 2026-10-14,
   settling d9f); the numbers are unchanged from the round-3 text. Changing a band now needs a
   new decision-log row ([[feedback_go_no_go_ranges_not_predrop]],
   [[project_helix_phase2_decision_criterion]]).
1. **R1 Measure the stable blocks first** ([[exploration-session-phased-context#vi-evidence]]).
   Over a frozen set of real sessions (kept local per d8f; only hashes and counts committed), for
   each stable block id (the composite's two blocks `stm-topic-expanded` and
   `stm-topic-collapsed` (R9), the recall pack, scan-prompt's bundle): the share of emitted bytes
   byte-identical to the previous rev of the same id, and the delta-size distribution (delta
   bytes / block bytes). Table A decides R5/R6; "the composite" in Table A's rows means both of
   its blocks, each judged on its own share. Recorded beside it, for the composite (round-4
   #s-3), by REPLAYING R9's render over each frozen ring turn by turn:
   - the per-turn share of collapsed lines byte-identical to the previous turn's;
   - the per-turn persistence of non-selected LIVE clusters' member sets (Jaccard with the same
     cluster's previous member set, and the share exactly unchanged), which shows how much of the
     collapsed lines' stability comes from R9's frozen snapshots rather than from the clustering;
   - the share of non-selected live clusters represented by a snapshot they share exactly TWO
     members with, and of those the share where exactly ONE shared member is not a hub (the
     residual R9 states under d9bm), so a stability figure produced by the identity rule rather
     than by the clustering is visible (round-6 #s-2; round-7 #s-1, d9ax; round-8 #ns-1, d9bm).
     "Hub" is R9's cache-relative definition, computed at each replayed turn by calling
     `stm.topic_hubs(cache)` on that turn's replayed cache; the replay script imports
     `stm.topic_hubs` and `stm.snapshot_eligible` and defines no hub or identity predicate of its
     own (AC-7i's import check). A one-member representation and a hub-only representation
     cannot occur under R9's rule (≥ 2 shared members, ≥ 1 of them not a hub); AC-7i pins both,
     so neither is a measured residual.
   These are recorded figures; Table A's bands and verdicts are unchanged (d9v). The round-7
   measurement that motivated d9ax (copies of the 59 live focus graphs, 2026-10-15: 111 of 238
   clusters have ≤ 3 members; in 163 of 493 same-graph pairs the sizes sum to ≤ 6, so ONE shared
   member reached J ≥ 0.20) is why the rule needs two members, not a band on this figure: the
   user chose option (a), which needs no new number
   ([[bsd-plan19-21-spec-rereview-r7-331b414#s-1]]). The round-8 measurement that motivated
   d9bm (copies of the 60 live focus graphs, 2026-10-15, hubs approximated as refs in ≥ 20% of
   the graphs): of the 426 cross-session pairs d9ax still represented, 310 (73%) shared hub
   members only, 136 of 217 (63%) with noise stripped; the hub rule cuts 426 to 116 on that
   proxy ([[bsd-plan19-21-spec-rereview-r8-23ad703#ns-1]]). The cache-relative hub figure is
   this R1's to record.
2. **R2 Phase classification, against the STM state BEFORE this prompt** (round-3 #b-2). The
   recall and scan hooks run in parallel with `focus hook --event input`, and `Stm.record` appends
   the input event AND ingests the prompt's terms into `focus.json` in one call
   (`stm.py:246-282`); if the input hook wins, this prompt's own terms are already members of the
   active cluster and every prompt would read `warm` by construction. So the phase, its overlap
   scores, the matched cluster and the cache lookup are ALL computed from ONE
   `stm.pre_prompt_state(root, session, prompt, *, t0)` call (specified in
   [[task-21.1-context-usage-telemetry#req-session]] 21.1 R9; written by 19.0 R7's
   `snapshot_pre_prompt` as the input hook's FIRST state access, before its in-flight sweep and
   before the input record; round-4 #b-1). Its `graph` and `topic_cache` are the state before
   this prompt whichever hook ran first; no phase code, and no prompt-time composite render (R9,
   `composite.build_topic_composite` called from scan-prompt with `graph=` from this call; 19.0
   R5), reads `focus.json`, the ring or the cache file directly (round-4 #b-2). The event logs
   `stm_source`.
   - **cold**: no focus topics yet, or the prompt carries no concrete terms;
   - **warm**: the prompt's terms overlap the active topic cluster;
   - **return**: they overlap a CACHED inactive cluster (R3);
   - **new**: they overlap neither.

   "Overlap" uses the CONFIRMED thresholds of [[#ranges-thresholds]] (d9v), applied in that table's
   order. Raw inputs (overlap scores, the matched cluster, thresholds) are logged on every event.
   **Turn count is logged and is never a phase signal** (d5b).
3. **R3 Topic cache** (#topic-cache). Every cluster that loses focus is snapshotted, keyed by its
   member set, in a per-session LRU of `N = 8` clusters, keyed by the session of 19.0 R5's
   resolver (never `latest_session`). **One writer, one home** (round-6 #s-2): the cache file is
   written only by the input hook, and it is the ONLY home of R9's collapsed snapshots (the round-5
   phrase "stored in the session's last-emitted state" is WITHDRAWN). Two writes, in the input
   hook's order (21.1 R9):
   - **in step 2, `snapshot_pre_prompt`:** the new snapshots R9 derives from the graph being
     copied (`stm.derive_snapshots(graph, cache) -> cache`, a pure function of those two values)
     are added, and the result is written into BOTH `pre.json`'s `topic_cache` and the cache file;
   - **after the input record:** this prompt's eviction, restore, expansion and re-collapse,
     which a reader never sees for this prompt.
   `pre_prompt_state` on its `live` path (no matching `pre.json`, the reader ran first) calls the
   same `derive_snapshots` on the live graph and cache in memory and writes nothing, so every
   ordering of the hooks sees the same snapshot set. 19.6 extends `snapshot_pre_prompt` and
   `pre_prompt_state` (21.1 R9) for this; scan-prompt and the render write no STM file. A return (Jaccard overlap of the prompt's terms with a cached
   cluster ≥ the threshold, logged raw) restores that cluster as the active focus and spends the
   budget as warm. A cache entry and R9's collapsed snapshot of the same cluster are ONE record
   (member set, frozen label, `<cid>`, first-collapse time; round-4 #s-3). The LRU bound `N`
   applies to what a `return` can restore; the collapsed set keeps every snapshot until its
   cluster is expanded, showing `C` and counting the rest in `+<m> more` (R9).
4. **R4 The whole per-prompt budget is allocated by phase**, across memory recall AND
   scan-prompt (d5b). If 19.5 R1 found the cap per event, the phase decides the split of the one
   budget between the two hooks; if per hook, it decides each hook's internal spend (pointers vs
   bodies vs breadth, through 19.1's allocation knob). cold/new → breadth, pointers over bodies;
   warm/return → depth, bodies and anchors over pointers.
5. **R5 Versioned blocks** (#vi-versioned, #vi-unchanged) — built only in the bands of Table A
   that say so. Every injected stable block carries a stable `id`, a `rev` and the line
   "supersedes earlier revs of `<id>`". A block whose content hash equals the last emitted rev
   for this session emits `<id> rev N unchanged`. **The versioned unit is the block, and the STM
   composite is TWO blocks** (round-4 #s-3): `stm-topic-expanded` (the expanded cluster's
   header with its event count and `L<a>–L<b>` range, members and `rel:` lines; it changes on
   most warm turns) and `stm-topic-collapsed` (the collapsed lines and the `+<m> more` line, with
   no count, range, turn or age anywhere in it). Each is hashed and versioned on its own, so a
   moving expanded header never costs the collapsed block its `unchanged`. A topic return emits
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
   marker is also written by the `rmx focus hook --event session-start` command (21.1 R9 D4,
   built by 19.0 or 21.1) when the SessionStart envelope's `source` is `compact` and R8's probe
   shows the harness sends one. That dispatch inside `--event session-start` is THIS task's
   change (round-4 #m-3; [[#files-to-modify]]). A test asserts the generated config
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
   - **Collapsed** (round-3 #s-4; round-4 #s-3): every other cluster, up to a cap, renders as
     ONE line holding ONLY its frozen label and its stable cluster id:
     `▸ topic: <label>  (id <cid>)`. Nothing else moves with it: no event count, no ring line
     range, no turn counter, timestamp, rank or relative age.
     - **A collapsed line renders a FROZEN SNAPSHOT, not the live clustering.** The live member
       set of an untouched cluster is not stable: every recorded input decays every node by
       `DECAY = 0.85` (`stm.py:37-38`), `focus_graph(top=30)` cuts to the 30 best-scoring nodes,
       and `cluster_focus` runs label propagation in score order, so an untouched cluster gains
       or loses members turn to turn. So every live cluster of the pre-prompt graph that no
       snapshot represents is snapshotted by the INPUT HOOK, inside `snapshot_pre_prompt`, from
       the graph it is copying (R3; round-6 #s-2), never by the render: member set, `<cid>` = a
       hash of that member set (as 19.4 R6 names unlabeled subjects), `<label>` = its head member
       by focus weight in that graph, and its first-collapse time = that graph's integer `turn`
       (not a clock, so the writer and a live-path reader derive the same value). A cluster that
       loses focus is R3's cache entry and gets its snapshot the same way. Later turns render the
       snapshot; decay, the top-30 cut and label propagation order cannot change its bytes. The
       render (`composite.py`) reads snapshots only from `pre_prompt_state(…).topic_cache`.
     - **Which live cluster a snapshot stands for** (round-6 #s-2; round-7 #s-1, d9ax; round-8
       #ns-1, d9bm, which AMENDS d9ax). A snapshot is ELIGIBLE for a live cluster only when the
       two member sets share **at least 2 members, AT LEAST ONE of which is not a hub, AND**
       Jaccard(live member set, snapshot member set) ≥ `j_return` (0.20, CONFIRMED in
       [[#ranges-thresholds]], d9v; the threshold a `return` already uses to say "this cached
       cluster is that topic"). All three conditions are required; one shared member never
       establishes identity, whatever the Jaccard, and neither do shared hubs alone.
       - **Hub, defined cache-relatively (d9bm).** `stm.topic_hubs(cache) -> frozenset[str]` is
         the set of refs that are members of **≥ 4** of the cache's **8 newest** snapshots
         (newest by first-collapse `turn`, ties by the smaller `<cid>`). 4 = ⌈8/2⌉ over the
         cache bound `N = 8` (R3; CONFIRMED, d9v), so the rule adds no constant. (d9bm's text
         writes "K = 8"; in this spec `K` is R6's keyframe interval and the cache bound is `N`,
         also 8: the number is the same, the name here is `N`.) A cache with fewer than 4
         snapshots has no hubs. The hub set is computed ONCE per `derive_snapshots` call from
         the cache AS PASSED IN, before that call adds any snapshot, so the result does not
         depend on the order in which live clusters are matched, and `derive_snapshots(graph,
         cache)` stays a pure function of its two arguments (no read, no clock).
       - **One predicate.** `stm.snapshot_eligible(live: frozenset, snap: frozenset, hubs:
         frozenset) -> bool` is the only place the three conditions live; `derive_snapshots`,
         `pre_prompt_state`'s live path (through `derive_snapshots`) and R1's replay script call
         it, and none carries its own copy (AC-7i's import check). Among eligible snapshots the live cluster is
       represented by the highest-Jaccard one; ties go to the newest first-collapse time, then
       the smaller `<cid>`. Each snapshot represents at most one live cluster per prompt (the
       highest-Jaccard one; the others go on down their own lists). A live cluster with no
       eligible snapshot is snapshotted as new. The round-5 rule "shares at least one member" is
       WITHDRAWN: hub refs (`src/refmatrix/cli.py`, `daemon.py`) sit in most clusters of this
       repo, so one shared member hid every later topic behind an old line. Jaccard alone
       (round 6) did not close it for small clusters: with ONE shared member, J ≥ 0.20 exactly
       when |A| + |B| ≤ 6 (union ≤ 5; the round-6 text's "total ≤ 5" was misstated), and 47% of
       this repo's live clusters have ≤ 3 members (round-7 #s-1). **`j_return`'s second use,
       acknowledged (d9ax):** d9v confirmed 0.20 as the prompt-terms-vs-cached-cluster `return`
       threshold; d9ax makes the same number the member-set identity threshold too, so a change
       to `j_return` now moves both rules and needs a decision-log row that names both.
       **Residual, stated (d9bm):** the round-7 residual, two clusters sharing two HUB members
       and one other member each ({hub1, hub2, a} vs {hub1, hub2, b}, J = 2/4), now gets its own
       line. What remains is a pair resting on one hub and ONE non-hub ({hub1, a, x} vs
       {hub1, a, y}, J = 2/4), which shares a real topic member; and a ref that is a hub by
       frequency in the whole repo but in fewer than 4 of the 8 newest snapshots counts as a
       non-hub. R1 records the share of representations resting on exactly one non-hub
       member.
     - **Re-collapse** (round-4 #s-3). When a snapshot's cluster is expanded (warm on it, or a
       `return` restores it), the snapshot leaves the collapsed set. When that cluster collapses
       again, it gets a NEW snapshot: its member set at that moment, a new `<cid>` and label, and a
       first-collapse time = the graph's `turn` at the re-collapse. So the cluster that just lost focus, the
       likeliest `return`, is always among the `C` shown.
     - **Counts and ranges move to the expanded view.** The event count and the `L<a>–L<b>` range
       are printed only on the EXPANDED cluster's header line (block `stm-topic-expanded`, R5)
       and by `rmx focus topics`, never on a collapsed line.
     - **Cap.** At most `C = 6` collapsed lines (CONFIRMED with the other numbers, d9v): the `C`
       snapshots with the most recent first-collapse times, rendered in a stable order
       (first-collapse time, oldest first, ties by `<cid>`), so each shown line keeps its bytes
       while it stays shown. Beyond `C`, one line `▸ +<m> more topics (rmx focus topics)`; that
       line changes when `m` changes and is versioned with its block (not claimed byte-stable).
   - **Cold** (and `new`, which spends breadth): every cluster collapsed (up to `C`); no expanded
     cluster.
   - **The collapsed line is the topic cache's re-expand handle** (R3), and it is BYTE-STABLE
     across turns until its snapshot leaves the shown set (expanded, or pushed past `C`), so
     versioned injection (R5) can send the `stm-topic-collapsed` block as "unchanged" on any turn
     in which no snapshot entered or left the shown `C` and `m` did not change.
   - **Where the render lives.** `composite.build_topic_composite` (`composite.py:63`), called by
     scan-prompt (`scan.py:888-894`), not `stm.py`; it reads its graph AND its snapshots from the
     one `pre_prompt_state` call on that prompt-time call (R2, R3; 19.0 R5), and writes nothing.
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

## Pre-registered go/no-go ranges, CONFIRMED (d9v) {#ranges}

**Status: CONFIRMED (d9v).** Every number in this section, plus `N = 8` (R3), `K = 8` (R6) and
`C = 6` (R9), was confirmed as written by the user on 2026-10-14 (d9v, settling d9f; R0).
Changing one needs a new decision-log row. Each verdict takes the worse of two independent frozen
session sets (d4d's quiet/loaded rule applied to session sets).

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

| phase | rule, applied in this order | confirmed number (d9v) |
|---|---|---|
| cold | the session has 0 focus topics, or the prompt has 0 concrete terms (terms surviving `scan._PROMPT_STOPWORDS` and 19.0's code-noise set) | — |
| warm | shared terms with the ACTIVE cluster's members ≥ `w_min`, or Jaccard(prompt terms, active members) ≥ `j_warm` | `w_min = 2`, `j_warm = 0.15` |
| return | not warm, and Jaccard(prompt terms, a CACHED cluster's members) ≥ `j_return`, the highest-Jaccard cached cluster wins (ties: most recently cached) | `j_return = 0.20`; second use (d9ax, acknowledged by the user 2026-10-15; amended by d9bm): R9's snapshot identity, together with ≥ 2 shared members of which ≥ 1 is not a hub (hub: member of ≥ 4 of the cache's 8 newest snapshots, R9) |
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
   confirming decision-log row (d9v, settling d9f) exists, before R1's first run (git history
   shows the order: d9v is at `224495c`).
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
   after it finishes, stopped after `Stm.snapshot_pre_prompt` only, and stopped after the snapshot
   AND `inflight_sweep()` (21.1 AC-8b's (iv)). Every fixture's seeded in-flight sidecar holds one
   call parked 120 s ago whose refs overlap the prompt's terms, so the sweep alone would move the
   overlap (round-4 #b-1). All four give the same `phase`, the same `overlap` scores, the same
   matched cluster and the same `restored_cluster_id`; all but the reader-first run log
   `stm_source=snapshot`. The scan-prompt composite rendered on the same runs is byte-identical
   across the four (its graph comes from the same `pre_prompt_state` call; round-4 #b-2), and
   this is asserted on the composite BYTES for two fixtures in particular (round-6 #s-2): the
   evicting `return` fixture, and a fixture whose pre-prompt graph holds a non-selected cluster no
   snapshot represents yet, so its snapshot is derived on this prompt. On the second, in the run
   stopped after `snapshot_pre_prompt`, `pre.json`'s `topic_cache` already holds that cluster's
   snapshot, and the reader-first run (no `pre.json` match) renders the same line from its
   in-memory derivation. The warm fixture's
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
7d. **Tree: collapsed line byte-stable** (R9; round-3 #s-4; round-4 #s-3). Consecutive turns
   render a collapsed cluster's line byte-identically (compared as bytes), although between them:
   THAT cluster is re-touched (a tool event adds to its event count and moves its line range) and
   its member weights reorder so a different member would be the head by weight; the turn count
   changes; the active cluster changes; and, on a DECAY-ONLY turn (one input that touches none of
   its members), one of its members falls below the `focus_graph(top=30)` cut and label
   propagation re-forms the live cluster without it (pre-checked: the live member set differs).
   The line changes only when its snapshot leaves the collapsed set: after the cluster is expanded
   and collapses again, it renders a new `<cid>` and a new frozen label.
   7d2. **Re-collapse is the newest** (round-4 #s-3). With `C` snapshots shown, a cluster expanded
   by a `return` and then collapsed again (focus moves elsewhere) is rendered among the `C`
   shown, at the end of the first-collapse order, and the oldest shown snapshot moves into
   `+<m> more`.
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
7h. **Two composite blocks, versioned apart** (R5; round-4 #s-3; if Table A says GO for the
   composite). Over three warm turns on one active cluster, each of which re-touches it (its
   event count and line range move) and changes no collapsed snapshot, `stm-topic-expanded`
   emits a new rev each turn and `stm-topic-collapsed` emits its body once and then
   `stm-topic-collapsed rev N unchanged` twice. A turn that adds a new snapshot to the shown set
   emits a new rev of `stm-topic-collapsed`.
7i. **A shared hub member does not merge topics** (R9 identity; round-6 #s-2). With a snapshot
   S = {`src/refmatrix/cli.py`, `a`, `b`, `c`}: a new live cluster {`src/refmatrix/cli.py`, `x`,
   `y`, `z`} (Jaccard 1/7) renders its OWN collapsed line, with its own `<cid>` and label; a live
   cluster {`a`, `b`, `c`, `d`} (Jaccard 3/5) is represented by S (no new line). Each leg below
   is its own fixture with ONE snapshot and ONE live cluster (round-7 #s-1, d9ax: ≥ 2 shared
   members AND J ≥ `j_return`):

   | snapshot | live cluster | shared | Jaccard | expected |
   |---|---|---|---|---|
   | {`hub`, `a`} | {`hub`, `b`} | 1 | 1/3 | own line (one member never establishes identity) |
   | {`a`, `b`, `c`} | {`a`, `d`, `e`} | 1 | 1/5 = 0.20 | own line (flipped from round 6) |
   | {`a`, `b`, `c`} | {`a`, `d`, `e`, `f`} | 1 | 1/6 | own line |
   | {`a`, `b`, `c`} | {`a`, `b`, `d`} | 2 | 2/4 | represented |
   | {`a`..`f`} (6) | {`a`, `b`, `g`..`j`} (6) | 2 | 2/10 = 0.20 | represented (the threshold, exactly) |
   | {`a`..`d`, `e1`..`e8`} (12) | {`a`..`d`, `f1`..`f9`} (13) | 4 | 4/21 ≈ 0.190 | own line |
   | {`a`..`g`} (7) | {`a`, `b`, `h`..`k`} (6) | 2 | 2/11 ≈ 0.182 | own line |

   The test computes each pair's shared count and Jaccard from the fixture and asserts them
   against the table's columns before asserting the render, so a fixture typo cannot pass. Each
   of these legs has ONE snapshot, so `topic_hubs` is empty (fewer than 4 snapshots) and the hub
   condition is inert in them; the hub legs below pin it.

   **Hub legs** (round-8 #ns-1, d9bm). The cache is the fixture; the live cluster is one:

   | leg | cache (first-collapse order, oldest first) | live cluster | expected |
   |---|---|---|---|
   | H1 | 4 snapshots S1 = {`hub1`, `hub2`, `a`}, S2 = {`hub1`, `hub2`, `p`}, S3 = {`hub1`, `hub2`, `q`}, S4 = {`hub1`, `hub2`, `r`} | {`hub1`, `hub2`, `b`} | own line: vs every Si 2 shared, both hubs, J = 2/4 |
   | H2 | the H1 cache | {`hub1`, `a`, `c`} | represented by S1: shared {`hub1`, `a`}, `a` not a hub, J = 2/4; S2-S4 share 1 member |
   | H3 (control) | S1-S3 only (3 snapshots: no hubs) | {`hub1`, `hub2`, `b`} | represented (by S3, the newest of the J = 2/4 ties): with 3 snapshots `hub1`/`hub2` are not hubs |
   | H5 (one hub set per call) | S1-S3 (no hubs) | TWO live clusters in one call, run with each of the two matching orders (the spec's result is the same in both; the mutant's differs when N1 is matched first): N1 = {`hub1`, `hub2`, `n1`..`n8`} (10 members; J = 2/11 with each Si: own line, a NEW snapshot holding `hub1`/`hub2`), then {`hub1`, `hub2`, `b`} | N1 own line; {`hub1`, `hub2`, `b`} represented by S3: the hub set is the INPUT cache's (3 snapshots, empty), not the 4 the call produces |
   | H4 (window) | 10 snapshots; `hub1` and `hub2` are members of the 2 OLDEST and the 2 NEWEST only (4 of 10, 2 of the 8 newest), each other snapshot a disjoint triple | {`hub1`, `hub2`, `b`} | represented by the newest snapshot holding both: they are not hubs in the 8-newest window |

   For each leg the test asserts `stm.topic_hubs(cache)` on the input cache (H1, H2: {`hub1`,
   `hub2`}; H3, H4, H5: empty) before asserting the render. **Import check:** a test parses R1's replay script and
   `composite.py` and asserts each imports `topic_hubs` / `snapshot_eligible` from `stm` and
   defines no function computing a member-set Jaccard or a hub set of its own. RED at HEAD: no
   collapsed render exists.
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
   - collapsed lines rendered from the live clustering instead of the frozen snapshot (AC-7d's
     decay-only turn: a new `<cid>`);
   - a re-collapsed cluster keeping its old first-collapse time (AC-7d2: it lands behind
     `+<m> more`);
   - the composite versioned as ONE block (AC-7h: the collapsed block never reads `unchanged`);
   - the composite's prompt-time graph read live instead of from `pre_prompt_state` (AC-3c: the
     input-hook-first run's composite differs);
   - the snapshot taken after the in-flight sweep (AC-3c: the sweep's refs move the overlap);
   - collapsed lines carrying the event count or line range (AC-7c's regex; AC-7d's re-touch);
   - the label taken live from the head member by weight instead of frozen (AC-7d's reorder);
   - no cap on collapsed lines, or a cap ordered by recent activity (AC-7g);
   - any phase input read from `focus.json` / the ring / the cache file instead of
     `pre_prompt_state` (AC-3c: the input-hook-first run reads `warm`);
   - the cache updated before `snapshot_pre_prompt` (AC-3c's evicting `return` fixture);
   - snapshots written by the render in scan-prompt instead of by `snapshot_pre_prompt` (AC-3c's
     new-cluster fixture: `pre.json`'s `topic_cache` lacks the snapshot);
   - `pre_prompt_state`'s live path not deriving snapshots (AC-3c's new-cluster fixture: the
     reader-first composite lacks the line, so its bytes differ);
   - the snapshot identity rule back to "≥ 1 shared member" (AC-7i: the hub-sharing cluster has
     no line of its own);
   - the identity rule back to Jaccard ≥ `j_return` alone, without the ≥ 2 shared members
     (AC-7i: the {`hub`, `a`} / {`hub`, `b`} and 1/5 legs are represented);
   - the member condition raised to ≥ 3 shared (AC-7i: the 2/4 leg gets its own line);
   - the identity threshold raised one step to 0.21 (AC-7i: the 2/10 leg gets its own line);
   - the identity threshold lowered to 0.19 (AC-7i: the 4/21 leg is represented) or to 0.18
     (round-7 #s-1: the 2/11 leg is represented; at round 6 this mutant survived, no pair sat in
     (1/6, 0.20));
   - (round 8, d9bm) the hub exclusion dropped, i.e. d9ax's rule (AC-7i H1: represented);
   - hubs excluded from the shared COUNT, i.e. ≥ 2 shared NON-hub members required (AC-7i H2:
     own line);
   - the hub threshold lowered to 3 (AC-7i H3: own line) or raised to 5 (AC-7i H1:
     represented);
   - hubs counted over every cached snapshot instead of the 8 newest (AC-7i H4: own line);
   - the hub set recomputed after each snapshot `derive_snapshots` adds in the same call (AC-7i
     H5: the second live cluster gets its own line);
   - the replay script or the render carrying its own identity predicate (AC-7i's import
     check);
   - the marker written only by the PreCompact recall command (AC-7f with the recall entry
     removed);
   - `session_start` / `precompact` randomized across arms (AC-7b);
   - expanding the top cluster on cold (AC-7e);
   - a non-selected cluster rendered with its members (AC-7c);
   - the window state not reset by the PreCompact marker (AC-7f).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | phase classification over `pre_prompt_state` (R2) with the thresholds; the topic cache (snapshot, LRU, restore), whose entries are R9's frozen snapshots and whose ONLY writer is the input hook (R3; round-6 #s-2): `derive_snapshots(graph, cache)` (pure; the identity rule through `snapshot_eligible`: ≥ 2 shared members, ≥ 1 of them not a hub, AND Jaccard ≥ `j_return`, d9ax amended by d9bm), `topic_hubs(cache)` (pure; ≥ 4 of the 8 newest snapshots) and `snapshot_eligible(live, snap, hubs)`, each the only copy of its rule, called and stored by `snapshot_pre_prompt` and called in memory by `pre_prompt_state`'s live path; eviction / restore / expansion / re-collapse written after the input record |
| `src/refmatrix/composite.py` | the expand/collapse composite render (R9; the render lives here, `composite.py:63`, not in `stm.py`; round-4 #b-2): frozen snapshots read from `pre_prompt_state(…).topic_cache`, never written here (round-6 #s-2), stable cluster ids, frozen labels, the cap `C`; the two blocks `stm-topic-expanded` / `stm-topic-collapsed` (R5); its graph from `pre_prompt_state` on prompt-time calls (R2) |
| `src/refmatrix/cli.py` (`focus hook`), `hooks.py` | `--event compact-marker` and its own generated PreCompact entry (R8a); the marker dispatch inside `--event session-start` when `source=compact` (R8a; round-4 #m-3) |
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

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan19-21-spec-rereview-r4-878647c]] (the 19.6 side of every id, plus round-3
#s-4, marked partial) and d9v of [[plan-review-2026-10-14#t11-approvals]]. Code facts re-read at
write time at HEAD `39dffbb`: `stm.py:37-38` (`DECAY`), `composite.py:63`, `:100-106`,
`scan.py:889-894`, `cli.py:1971-1981`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r4-878647c]]

| finding / decision | answered at |
|---|---|
| round-4 #b-1 (the snapshot follows the sweep) | R2 (snapshot = the input hook's first state access, before the sweep); AC-3c (a parked call per fixture; four orderings); mutation |
| round-4 #b-2 (19.6 side: the composite reads the newest ring and the live graph; the render lives in `composite.py`) | R2 (no prompt-time composite render reads `focus.json`); R9 "Where the render lives"; AC-3c (the composite byte-identical across orderings); [[#files-to-modify]] (`composite.py`); mutation. The routing itself is 19.0 R5 ([[task-19.0-stm-cluster-hygiene#rev-round-5]]) |
| round-4 #s-3 (member set unstable for an untouched cluster; one versioned block; re-collapse undefined) | R9 (collapsed lines render frozen snapshots; which live cluster a snapshot stands for; re-collapse = new snapshot, newest first-collapse time); R3 (the cache entry is the snapshot); R5 (the composite is two blocks, versioned apart); R1 (collapsed-line persistence and live member-set persistence recorded, Table A unchanged); AC-7d (decay-only turn), AC-7d2, AC-7h; mutations; [[exploration-session-phased-context#tree-render]] |
| round-4 #m-3 (marker dispatch owner; status lines) | R8a and [[#files-to-modify]] (`--event session-start` dispatch on `source=compact` is this task's); status lines flipped (next row). The wave-list item is the decision log's, not this file's |
| d9v (tables, thresholds, `N`, `K`, `C` CONFIRMED as written) | header; R0; R2; R9 cap; [[#ranges]] heading and status; [[#ranges-thresholds]] column; AC-1. No number changed |
| round-3 #s-4 (partial) | as round-4 #s-3 |
| round-3 #b-2 (partial) | as round-4 #b-1 |

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan19-21-spec-rereview-r6-0e77da3#s-2]] (the only round-6 finding on 19.6). No
round-6 decision-log row names plan 19; the identity rule reuses `j_return`, a number already
CONFIRMED by d9v, so no band or threshold changes. Code facts read at write time at HEAD
`3d3c798`: `composite.py:63`, `:103`; `scan.py:888-894`; `stm.py:38` (`DECAY`), `:692` (`turn`),
`:705-710`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r6-0e77da3]]

| finding / decision | answered at |
|---|---|
| round-6 #s-2 (two writers and two homes for the frozen snapshot; "≥ 1 shared member" merges new topics into old lines through hub refs) | R3 ("One writer, one home": the input hook only, the topic cache only; `derive_snapshots` in `snapshot_pre_prompt`, and in memory on `pre_prompt_state`'s live path; "last-emitted state" withdrawn as a snapshot home); R9 (snapshot creation by the input hook from the copied graph; first-collapse time = the graph's `turn`; identity by Jaccard ≥ `j_return` with ties; the round-5 rule withdrawn; residual stated; "Where the render lives": reads and writes nothing else); R1 (one-member representation share recorded); AC-3c (composite bytes asserted on the evicting `return` and a new-cluster fixture; `pre.json` holds the derived snapshot); AC-7i (hub-only share gets its own line; 0.20 / 1/6 boundary); mutations; [[#files-to-modify]] (`stm.py`, `composite.py`) |
| round-6 #b-1, #b-2, #s-1, #s-3, #m-1, #m-2 | not 19.6 items: [[task-19.0-stm-cluster-hygiene#rev-round-6]], [[task-19.3-subject-tiered-index#rev-round-6]], [[task-19.4-keep-derived-layers-current#rev-round-6]], [[plan-19-adaptive-memory-budget#rev-round-6]] |

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan19-21-spec-rereview-r7-331b414#s-1]] (the only round-7 finding on 19.6) with
the user's decision d9ax ([[plan-review-2026-10-14#t12-approvals]], option (a)). No code fact is
new: the identity rule is spec-only (no collapsed render exists at HEAD `77ac38f`, whose `src/`
equals the round-7 review's `331b414`).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r7-331b414]]
rel: implements -> [[plan-review-2026-10-14#t12-approvals]]

| finding / decision | answered at |
|---|---|
| round-7 #s-1; d9ax (one hub member still merges small clusters; residual misstated; R1 figure with no decision; `j_return` reused unacknowledged; the 0.18 mutant survives) | R9 "Which live cluster a snapshot stands for" (eligible only with ≥ 2 shared members AND J ≥ `j_return`; the one-member bound corrected to a size sum ≤ 6, union ≤ 5; `j_return`'s second use acknowledged; the residual restated as two shared hub members); [[#ranges-thresholds]] `return` row (second use, d9ax); R1 (the recorded figure is now the two-shared-member share; the one-member case is closed by construction, not banded: option (a) needs no new number); AC-7i (one fixture per leg: {hub, a}/{hub, b} and the 1/5 pair now get their own line, 2/4 and 2/10 represented, 4/21 and 2/11 own line; shared count and Jaccard asserted from the fixture); mutations (Jaccard alone; ≥ 3 shared; 0.21; 0.19; 0.18) |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703#ns-1]] (the only round-8 finding on 19.6) with
decision d9bm ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until its ch-bsd loop is
clean), which AMENDS d9ax, and records d9bi (19.6 is the helix substrate and moves up the wave
order). No code fact is new: no collapsed render exists at HEAD `23ad703`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]
rel: implements -> [[plan-review-2026-10-14#t12-approvals]]

| finding / decision | answered at |
|---|---|
| round-8 #ns-1; d9bm (d9ax's stated residual, two shared HUB members, is 63-73% of its matches; "hub" undefined for R1) | R9 "Which live cluster a snapshot stands for" (≥ 2 shared, ≥ 1 not a hub, J ≥ `j_return`; hub = member of ≥ 4 of the cache's 8 newest snapshots, computed once per call from the cache as passed in; `stm.topic_hubs` and `stm.snapshot_eligible` the only copies; d9bm's "K" named `N` here, same number; residual restated); R1 (the figure defined through `stm.topic_hubs` on the replayed cache; the round-8 proxy measurement recorded); [[#ranges-thresholds]] `return` row (d9bm); AC-7i (hub legs H1-H5 with `topic_hubs` asserted; import check); mutations (hub exclusion dropped; hubs excluded from the count; threshold 3 / 5; all snapshots instead of 8 newest; hub set recomputed mid-call (H5); private predicate); [[#files-to-modify]] (`stm.py`) |
| d9bi (plan 19 is the helix substrate; 19.6 pulled forward) | header (wave; the helix-facing interfaces named, and the rule that changing them after merge needs a decision row) |
| user rule: converge repeated shapes into one function | R9 (`topic_hubs`, `snapshot_eligible`: one copy each, used by the input-hook writer, `pre_prompt_state`'s live path and R1's replay; AC-7i import check) |
