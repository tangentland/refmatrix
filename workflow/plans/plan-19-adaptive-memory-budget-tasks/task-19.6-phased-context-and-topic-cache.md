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
> its versioned blocks (`block_id`, `rev`, `unchanged` in 21.1's events). `derive_snapshots`,
> `match_snapshots`, `topic_hubs`, `snapshot_eligible` and `member_jaccard` (R9) are pure
> functions of their arguments, and the cache file carries `schema: 1` (R3), so helix can
> recompute identity, including WHICH live cluster each snapshot stands for, from the cache alone
> by importing `stm.match_snapshots` (round-9 #s9-1); `topic_match` is `dict[str, str]` keyed by
> `stm.cluster_cid(members)`, a missing cache file reads as the empty cache, and the file holds at
> most 64 records (round-10 #m10-1); a change to any of these signatures or to
> the cache schema after merge needs a decision-log row naming helix.
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
     cluster's previous member set, computed by `stm.member_jaccard`, and the share exactly
     unchanged), which shows how much of the
     collapsed lines' stability comes from R9's frozen snapshots rather than from the clustering;
   - the share of non-selected live clusters represented by a snapshot they share exactly TWO
     members with, and of those the share where exactly ONE shared member is not a hub (the
     residual R9 states under d9bm), so a stability figure produced by the identity rule rather
     than by the clustering is visible (round-6 #s-2; round-7 #s-1, d9ax; round-8 #ns-1, d9bm).
     "Hub" is R9's cache-relative definition, computed at each replayed turn by calling
     `stm.topic_hubs(cache)` on that turn's replayed cache; WHICH snapshot represents a live
     cluster is `stm.match_snapshots(live, cache)` on that turn's replayed input cache (round-9
     #s9-1). The replay script imports `stm.match_snapshots`, `stm.member_jaccard` and
     `stm.topic_hubs`, and defines no hub, identity, assignment or Jaccard computation of its own
     (AC-7i's import check). The replay also records, per session, the maximum cache record
     count and cache file size, and how many records R3's record cap evicted (round-10 #m10-1),
     so the cap of 64 is checked against real sessions. A one-member representation and a hub-only representation
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
     copied (`stm.derive_snapshots(graph, cache) -> (cache, topic_match)`, a pure function of
     those two values; `topic_match` is R9's completed assignment, below) are added, and the
     cache is written into BOTH `pre.json`'s `topic_cache` and the cache file, with
     `topic_match` beside it in `pre.json`;
   - **after the input record:** this prompt's eviction, restore, expansion and re-collapse,
     which a reader never sees for this prompt.
   `pre_prompt_state` on its `live` path (no matching `pre.json`, the reader ran first) calls the
   same `derive_snapshots` on the live graph and cache in memory and writes nothing, so every
   ordering of the hooks sees the same snapshot set and the same `topic_match`
   (`PrePromptState.topic_match`, round-9 #s9-1).
   **Cache file contract (round-9 #s9-1; helix reads it).** The file is
   `{"schema": 1, "snapshots": [...]}`; each record holds its member set (sorted), `<cid>`, frozen
   label, first-collapse `turn` and a `state` field (`collapsed` / `expanded`). Expansion flips
   `state`; it never removes the record (only R3's LRU bound decides what a `return` restores).
   **`state` does not affect eligibility** (round-10 #m10-1): every record, `collapsed` or
   `expanded`, is a candidate in `match_snapshots` (R9), so an expanded cluster maps to its own
   snapshot on the next prompt (AC-7i H6); `state` only decides whether the render shows the
   record as a collapsed line.
   **Record cap** (round-10 #m10-1). The ONLY removal of a record: the file holds at most
   `TOPIC_CACHE_MAX = 64` records (= 8 × `N`, adding no free constant; R1's replay records the
   per-session maximum count and file size against it). The input hook's SECOND write (after the
   input record, beside the LRU update) evicts, while the cache holds more than 64, the
   `collapsed` record with the oldest first-collapse `turn` (ties by the smaller `<cid>`) that
   this prompt's `topic_match` does not map to; an `expanded` record is never evicted. Each
   eviction is counted `topic-cache-evicted` on the input hook's event, never silently. Eviction
   runs outside `derive_snapshots`, which stays pure; between prompts the file holds at most 64
   records plus that prompt's new snapshots. With 64 > 8 records kept, eviction never touches the
   8 newest, so it never moves `topic_hubs`.
   The writer always writes `schema: 1`; ONE reader, `stm.load_topic_cache(raw: dict | None,
   where: str) -> dict`, applies the check for every reader (`pre_prompt_state` for both the file
   and `pre.json`'s copy, `derive_snapshots`'s callers, helix):
   - a MISSING cache file (`raw is None`; a session's first prompt) is the empty cache
     `{"schema": 1, "snapshots": []}`;
   - the empty object `{}` (exactly no keys) is `pre.json`'s pre-19.6 sentinel (21.1 R9 writes
     `topic_cache = {}` until 19.6) and is read as the empty cache; 19.6 code never writes it;
   - any other object whose `schema` is missing or not 1 raises `ValueError` naming `where` and
     the value it found, and never reinterprets the records (AC-7i2). 19.6 extends `snapshot_pre_prompt` and
   `pre_prompt_state` (21.1 R9) for this; scan-prompt and the render write no STM file. A return (Jaccard overlap of the prompt's terms with a cached
   cluster ≥ the threshold, logged raw) restores that cluster as the active focus and spends the
   budget as warm. A cache entry and R9's collapsed snapshot of the same cluster are ONE record
   (member set, frozen label, `<cid>`, first-collapse time; round-4 #s-3). The LRU bound `N`
   applies to what a `return` can restore; the collapsed set keeps every snapshot until its
   cluster is expanded or the record cap above evicts it, showing `C` and counting the rest in `+<m> more` (R9).
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
       the graph it is copying (R3; round-6 #s-2), never by the render: member set, `<cid>` =
       `stm.cluster_cid(members) -> str`, the ONE member-set hash (the first 8 hex chars of
       sha256 over the sorted member names, the formula 19.4 R6 uses for unlabeled subjects;
       round-10 #m10-1), `<label>` = its head member
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
         the set of refs that are members of **≥ 4** (`stm.HUB_MIN_SNAPSHOTS`) of the cache's
         **8 newest** snapshots (newest by first-collapse `turn`, ties by the smaller `<cid>`).
         4 = ⌈8/2⌉ over the cache bound `N = 8` (R3; CONFIRMED, d9v), so the rule adds no
         constant. **Its input is every snapshot record in the cache, whatever its `state`**
         (round-9 #s9-1): a snapshot whose cluster is expanded leaves the collapsed SET but stays
         a record (R3's cache contract) and still counts toward the 8 newest. A cache with fewer
         than 4 snapshot records has no hubs. The hub set is computed ONCE per `derive_snapshots` call (inside
         its one `match_snapshots` call) from the cache AS PASSED IN, before that call adds any snapshot, so the result does not
         depend on the order in which live clusters are matched, and `derive_snapshots(graph,
         cache)` stays a pure function of its two arguments (no read, no clock).
       - **One Jaccard.** `stm.member_jaccard(a: frozenset, b: frozenset) -> float` is the only
         member-set Jaccard (0.0 for two empty sets); `snapshot_eligible`, the assignment
         below and R1's replay call it (round-9 #s9-1).
       - **One predicate.** `stm.snapshot_eligible(live: frozenset, snap: frozenset, hubs:
         frozenset) -> bool` is the only place the three conditions live; only
         `match_snapshots` calls it, and nothing carries its own copy (AC-7i's import check).
       - **One assignment** (round-9 #s9-1). `stm.match_snapshots(live: list[frozenset], cache)
         -> dict[int, str | None]` maps each index of `live` to the `<cid>` of the snapshot
         that represents it, or `None` (snapshot as new). It is the ONLY home of the
         assignment, and it is pure:
         1. it computes `topic_hubs(cache)` ONCE, on the cache as passed in;
         2. it processes the live clusters in a DEFINED order: descending member count, ties by
            the sorted member tuple (lexicographic), whatever order `live` arrives in;
         3. for each live cluster in that order, the eligible snapshots (`snapshot_eligible`)
            not yet taken are ranked by `member_jaccard` descending, ties to the newest
            first-collapse `turn`, then the smaller `<cid>`; the first is assigned and taken.
            Each snapshot represents at most one live cluster per prompt; a later live cluster
            whose best snapshot is taken goes on down its own list.
         `derive_snapshots(graph, cache)` clusters the graph, calls `match_snapshots` once,
         snapshots every `None` entry as new, and returns the new cache with `topic_match:
         dict[str, str]`: the completed map, keyed by `stm.cluster_cid(members)` of each live
         cluster (the same hash that names `<cid>`; no tuple keys, so it is a plain JSON object
         in `pre.json`; round-10 #m10-1), valued by the `<cid>` of the snapshot that represents
         it (existing or new). `topic_match` is carried in `pre.json` and on
         `PrePromptState.topic_match` (R3), because the render sees only the POST-derive cache,
         whose hub set may differ from the input cache's, so a render-side recomputation could
         disagree with the writer. The render reads `topic_match` to know which snapshot stands
         for the EXPANDED cluster and leaves it out of the collapsed set on this prompt (the
         cache's own expansion update is written after the input record, so it does not yet
         show it). R1's replay calls `match_snapshots` on each replayed input cache. Helix
         imports it (plan-19 header, interface 2). No other code assigns live clusters to
         snapshots (AC-7i's import check).
       - **History.** The round-5 rule "shares at least one member" is
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
   | H5 (one hub set per call) | S1-S3 (no hubs) | TWO live clusters in one call, N1 = {`hub1`, `hub2`, `n1`..`n8`} (10 members; J = 2/11 with each Si: own line, a NEW snapshot holding `hub1`/`hub2`) and {`hub1`, `hub2`, `b`}, run in BOTH input orders through the graph's cluster list (round-10 #s10-1): (a) N1 first, (b) {`hub1`, `hub2`, `b`} first. A per-cluster `derive_snapshots` (one `match_snapshots([c], cache_so_far)` per cluster in ITS input order, adding each snapshot before the next call) gives `b` its own line in order (a): N1 adds S4 and the recompute makes `hub1`/`hub2` hubs; order (b) cannot see it, so (a) is the killing leg and (b) pins that the result is order-free | in BOTH orders: N1 own line; {`hub1`, `hub2`, `b`} represented by S3: the hub set is the INPUT cache's (3 snapshots, empty), not the 4 the call produces |
   | H4 (window) | 10 snapshots; `hub1` and `hub2` are members of the 2 OLDEST and the 2 NEWEST only (4 of 10, 2 of the 8 newest), each other snapshot a disjoint triple | {`hub1`, `hub2`, `b`} | represented by the newest snapshot holding both: they are not hubs in the 8-newest window |

   For each leg the test asserts `stm.topic_hubs(cache)` on the input cache (H1, H2: {`hub1`,
   `hub2`}; H3, H4, H5: empty) and the `stm.match_snapshots` map before asserting the render.
   H6 (the expanded cluster's snapshot; round-9 #s9-1): the H3 cache with the phase `warm` on
   {`hub1`, `hub2`, `b`}: `topic_match` maps it to S3, and the collapsed block holds S1 and S2
   and NOT S3 on this same prompt (the cache's own `state` flip is written after the input
   record); on the NEXT prompt, with S3's `state` now `expanded`, the same live cluster still
   maps to S3 (`state` does not affect eligibility, R3; round-10 #m10-1). H7 (the cache contract): the H1 cache with S2's `state` = `expanded` still yields
   `topic_hubs` = {`hub1`, `hub2`}. H8 (the defined order): one snapshot S = {`a`, `b`, `c`,
   `d`}; `live` passed as [{`a`, `b`, `y`}, {`a`, `b`, `c`, `x`}] (both eligible: J = 2/5 and
   3/5). The map is {1: S's `<cid>`, 0: `None`}: the 4-member cluster is processed first and
   takes S, the 3-member one gets its own line; the same map results with `live` reversed.
   **Import check** (round-9 #s9-1; AST over R1's replay script, `composite.py` and every
   `src/refmatrix` module except `stm.py`):
   - the replay script's `from refmatrix.stm import …` set EQUALS {`match_snapshots`,
     `member_jaccard`, `topic_hubs`} (round-10 #m10-1); `composite.py` imports none of `match_snapshots`, `snapshot_eligible`,
     `topic_hubs` or `member_jaccard` and reads `topic_match` from `PrePromptState`;
   - no call of `snapshot_eligible` outside `stm.match_snapshots`;
   - no expression of the shape `len(A & B) / len(A | B)` (or `.intersection` / `.union`)
     outside `stm.py`, and no module outside `stm.py` references `HUB_MIN_SNAPSHOTS`
     (round-10 #m10-1: the round-9 clause "the literal `4` against a snapshot count" is
     dropped, an AST check cannot decide it);
   - in `stm.py` (round-10 #s10-1): the body of `derive_snapshots` contains exactly ONE call of
     `match_snapshots`, and that call is not inside a `for`, a `while` or a comprehension.
   **The check can fail:** run on a fixture module holding `len(a & b) / len(a | b)`, it
   reports that line; run on a fixture calling `snapshot_eligible` directly, it reports that
   call; run on a fixture `derive_snapshots` that calls `match_snapshots` inside a `for` over
   the clusters, it reports that call. RED at HEAD: no collapsed render exists.
7i2. **Cache schema** (R3; round-9 #s9-1). The cache file the input hook writes has
   `schema == 1`. A cache file with `schema: 2`, and one with no `schema` key
   (`{"snapshots": []}`, not the empty object), each make
   `pre_prompt_state` raise `ValueError` naming the path and the value found; the file's bytes
   are unchanged afterwards (no reader rewrote it). **Missing and sentinel legs** (round-10
   #m10-1): with NO cache file, `pre_prompt_state` raises nothing and returns an empty
   `topic_cache` and an empty `topic_match` (`{}`); a `pre.json` whose `topic_cache` is `{}`
   (21.1's pre-19.6 sentinel) reads as the empty cache, not a raise. **Record-cap leg:** a
   cache of 64 records (one `expanded`, the oldest) plus a prompt that snapshots 2 new clusters
   leaves 64 records after the input hook's second write: the 2 OLDEST `collapsed` records are
   gone, the `expanded` one is kept, and the event counts `topic-cache-evicted` = 2.
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
   - (round 10, #s10-1) `derive_snapshots` calling `match_snapshots` per live cluster, adding
     each snapshot before the next call (AC-7i H5, the N1-first order: {`hub1`, `hub2`, `b`}
     gets its own line; AC-7i's import check: the call sits in a loop);
   - (round 9, #s9-1) `match_snapshots` processing `live` in input order instead of the
     defined order (AC-7i H8: the 3-member cluster takes S);
   - an expanded snapshot dropped from `topic_hubs`'s input (AC-7i H7: the hub set loses
     `hub1`/`hub2`);
   - the render showing the expanded cluster's snapshot as a collapsed line (AC-7i H6);
   - the render recomputing the assignment on the post-derive cache instead of reading
     `topic_match` (AC-7i's import check);
   - a reader accepting an unknown cache `schema` (AC-7i2);
   - (round 10, #m10-1) a missing cache file or the `{}` sentinel raising (AC-7i2's missing and
     sentinel legs); no record cap, or the cap evicting an `expanded` record (AC-7i2's
     record-cap leg); `match_snapshots` skipping `expanded` records (AC-7i H6's next prompt:
     the expanded cluster gets a new `<cid>`);
   - the replay script or the render carrying its own identity predicate, assignment or
     Jaccard (AC-7i's import check);
   - the marker written only by the PreCompact recall command (AC-7f with the recall entry
     removed);
   - `session_start` / `precompact` randomized across arms (AC-7b);
   - expanding the top cluster on cold (AC-7e);
   - a non-selected cluster rendered with its members (AC-7c);
   - the window state not reset by the PreCompact marker (AC-7f).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | phase classification over `pre_prompt_state` (R2) with the thresholds; the topic cache (snapshot, LRU, restore), whose entries are R9's frozen snapshots and whose ONLY writer is the input hook (R3; round-6 #s-2): `derive_snapshots(graph, cache) -> (cache, topic_match)` (pure; calls `match_snapshots` once), `match_snapshots(live, cache) -> {idx: cid or None}` (pure; the ONE assignment: hubs once, defined order, highest J, tie-breaks, one live cluster per snapshot; round-9 #s9-1), `member_jaccard(a, b)` (the ONE member-set Jaccard), `topic_hubs(cache)` (pure; ≥ 4 of the 8 newest snapshot records, any `state`) and `snapshot_eligible(live, snap, hubs)` (≥ 2 shared members, ≥ 1 of them not a hub, AND Jaccard ≥ `j_return`, d9ax amended by d9bm), each the only copy of its rule; the cache file's `schema: 1` and its ONE reader check `load_topic_cache` (missing file and the `{}` sentinel read as the empty cache; round-10 #m10-1); `cluster_cid(members)` (the ONE member-set hash: `<cid>` and `topic_match`'s keys); the record cap `TOPIC_CACHE_MAX = 64` (eviction in the second write, counted `topic-cache-evicted`); called and stored by `snapshot_pre_prompt` and called in memory by `pre_prompt_state`'s live path; eviction / restore / expansion / re-collapse written after the input record |
| `src/refmatrix/composite.py` | the expand/collapse composite render (R9; the render lives here, `composite.py:63`, not in `stm.py`; round-4 #b-2): frozen snapshots read from `pre_prompt_state(…).topic_cache` and the assignment from `PrePromptState.topic_match` (the expanded cluster's snapshot left out of the collapsed set; round-9 #s9-1), never written here (round-6 #s-2), stable cluster ids, frozen labels, the cap `C`; the two blocks `stm-topic-expanded` / `stm-topic-collapsed` (R5); its graph from `pre_prompt_state` on prompt-time calls (R2) |
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

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan19-21-spec-diffcheck-r9-ebccb20#s9-1]] and the 19.6 part of
[[bsd-plan19-21-spec-diffcheck-r9-ebccb20#m9-7]]. Edit-level; no decision. This unblocks the
helix topic-cache interface. No code fact is new: no collapsed render exists at HEAD.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]]

| finding | answered at |
|---|---|
| r9 #s9-1 (the identity ASSIGNMENT has no single home; the import check demands dead imports; H5's kill is order-dependent; `topic_hubs`'s input and the cache schema unstated) | R9 "One Jaccard" (`stm.member_jaccard`), "One assignment" (`stm.match_snapshots(live, cache) -> {idx: cid or None}`: hubs once, defined order by descending size then sorted members, highest J, tie-breaks, one live cluster per snapshot); `derive_snapshots` returns `(cache, topic_match)`; the render reads `PrePromptState.topic_match` rather than recomputing on the post-derive cache (why stated); `topic_hubs` counts every snapshot record whatever its `state`; R3 cache contract (`schema: 1`, `state` field, reader raises on another schema); R1 (the replay imports `match_snapshots`, `member_jaccard`, `topic_hubs`); header (helix interface); AC-7i H5 (the defined order processes N1 first; "each of the two matching orders" dropped), H6 (expanded snapshot left out of the collapsed set), H7 (expanded records count toward hubs), H8 (order leg); import check rewritten with its own failing control; AC-7i2 (schema); mutations; [[#files-to-modify]] |
| r9 #m9-7 (stale "K = 8" note) | R9 hub bullet: the parenthetical deleted (d9bm now reads `N = 8`) |
| user rule: converge repeated shapes into one function, each with a bypass check that can fail | `match_snapshots` and `member_jaccard` are the one assignment and the one Jaccard; AC-7i's import check reports a planted intersection-over-union expression and a direct `snapshot_eligible` call |

## Revision round 10 (2026-10-15) {#rev-round-10}

Answers [[bsd-plan19-21-spec-diffcheck-r10-f6400aa#s10-1]] and
[[bsd-plan19-21-spec-diffcheck-r10-f6400aa#m10-1]]. Edit-level; no decision. Helix-facing: the
`topic_match` key type, the missing-file semantics and the record bound are fixed here, before
merge, so the plan-19 header's freeze rule applies to them from merge on. No code fact is new: no
collapsed render or topic cache exists at HEAD.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r10-f6400aa]]

| finding | answered at |
|---|---|
| r10 #s10-1 (H5 put {`hub1`, `hub2`, `b`} first, the one order in which the only possible mutant, a per-cluster `derive_snapshots`, survives; no AC asserted one `match_snapshots` call) | AC-7i H5 runs BOTH input orders (N1 first kills the per-cluster mutant; the other pins order-freedom); AC-7i import check: `derive_snapshots`'s body holds exactly one `match_snapshots` call, outside any `for` / `while` / comprehension, with a planted looping fixture as its failing control; mutation restated |
| r10 #m10-1 (`topic_match` serialization, a missing cache file and the `{}` sentinel, no record bound, eligibility vs `state`; an undecidable import-check clause) | R9: `topic_match: dict[str, str]` keyed by `stm.cluster_cid(members)`, the one member-set hash that also names `<cid>`; R3: `state` does not affect eligibility; the record cap `TOPIC_CACHE_MAX = 64` (= 8 × `N`; oldest `collapsed` unmatched record evicted in the second write, `expanded` never, counted `topic-cache-evicted`); the ONE reader `stm.load_topic_cache` (missing file and `{}` read as the empty cache; anything else without `schema: 1` raises); R1 records the per-session maximum record count and file size; AC-7i H6 next-prompt leg; AC-7i2 missing-file, sentinel and record-cap legs; AC-7i import check: the literal-`4` clause dropped, replaced by "no `HUB_MIN_SNAPSHOTS` outside `stm.py`" and the replay's exact `stm` import set; mutations; header; [[#files-to-modify]] |
| user rule: converge repeated shapes into one function, with a bypass check that can fail | `cluster_cid` (one member-set hash for `<cid>` and the map's keys), `load_topic_cache` (one reader check for the file and `pre.json`); the one-call AST check has its own planted failing fixture |
