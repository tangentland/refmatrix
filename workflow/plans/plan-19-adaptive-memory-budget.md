---
gmd: "0.1"
id: plan-19-adaptive-memory-budget
title: "Plan 19: memory reaches the agent within budget, ranked by use, grouped by subject, and never lost"
tags: [plan, memory, recall, hooks, budget, memory-index, adaptive, stm]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
  updated: 2026-10-15
---

# Plan 19: adaptive memory under the context budgets {#root}

**Date:** 2026-10-07; revised 2026-10-14 after the Wave 0 decision log.
**Status:** Drafting. Task specs 19.0–19.6 are revised after
[[plan-review-2026-10-14]]; a spec re-review is next.
**Helix substrate (d9bi, the user 2026-10-15: "I want the context adaptive/variable stm
handling in-place so we can build helix on top of that substrate").** Plan 19 LEADS Wave 1 after
23.0 (19.0 and 21.1 → 19.1 → 19.2 ahead of plans 16/17/22), and 19.6 is pulled from Wave 3 to
directly after its own dependencies. The helix plan (a Wave 4 draft, not yet a file) consumes
four interfaces this plan fixes, so every spec choice below is made with them in view:
1. `stm.pre_prompt_state` / `PrePromptState` and the pre-prompt snapshot (19.0 R7, 21.1 R9): the
   race-free STM state before a prompt;
2. 19.6's topic cache and frozen snapshots (`<cid>` = hash of the member set, frozen label,
   first-collapse `turn`; one writer, one home; the cache file carries `schema: 1` and each
   record a `state`), with identity decided by the pure `stm.derive_snapshots(graph, cache) ->
   (cache, topic_match)`, `stm.match_snapshots(live, cache) -> {idx: cid or None}` (the ONE
   assignment: hubs once, defined order, highest J, one live cluster per snapshot),
   `stm.topic_hubs(cache)`, `stm.snapshot_eligible` and `stm.member_jaccard` (d9ax amended by
   d9bm; round-9 #s9-1), so helix can recompute topic identity, including which live cluster
   each snapshot stands for, from the cache alone by importing `match_snapshots`;
3. 21.1's recall events, including the versioned-injection fields (`block_id`, `block_sha`,
   `rev`, `unchanged`) that 19.6 fills;
4. 19.2's usage record (raw per-evidence counts, read-time decay).
A change to any of the four after it merges needs a decision-log row that names helix.

**Origin:** the user, 2026-10-07: "we need a way to automatically optimize memory storage and
retrieval to make it adaptive to keep more than the byte limit". Decisions are recorded in
[[exploration-adaptive-memory-budget]]: B + A + D now, a new plan, and first after the remedy merge.

rel: derives-from -> [[exploration-adaptive-memory-budget]]
rel: depends-on -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: related-to -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[plan-21-agent-context-usage]]
rel: amends -> [[plan-review-2026-10-14#t5]]
rel: specified-by -> [[bsd-plan19-spec-review-3104a81]]
rel: specified-by -> [[bsd-decision-log-review-a192ba2]]
rel: related-to -> [[exploration-session-phased-context]]

## Why {#why}

Memory reaches the agent through budgeted channels, and today most of what they produce never
arrives:
- **SessionStart recall** (`hooks.py:277`, `--session-start --k 10 --json`) emitted **26,567 B**
  in October and 16,629 B on 2026-10-14.
- **Per-prompt recall** (`hooks.py:313`, `--stdin-json --k 5 --json`) emitted **16,347 B**
  (15,153 B on a 2026-10-14 sample).
- Claude Code delivers hook output whole only up to about **10k chars**
  ([[reference_hook_output_10k_cap]]). Above that, the agent gets a ~2 KB preview.
- What does arrive is often noise: on `"whats next?"` all 5 per-prompt hits were label-only
  compiled `subject_*` rows.
- **`MEMORY.md`** holds 22,368 / 24,000 chars (2026-10-14). It folds projects by **file mtime**
  (`memory_index.py:275`), never by value; feedback never folds.
- **Nothing records which memories are used**: no recall count, no last-recalled, and 0
  memory-recall rows in `query.log`.
- The STM clusters that phased context would key on are led by script-body junk, a subagent's
  tool calls and typos (bug-103, bug-104).

These figures drift; every AC freezes its own baseline at RED time on a sandbox copy.
{#why-body}

## Goal {#goal}

Every injection channel delivers as much memory as fits under its real budget, chosen by measured
use, and grouped so one line can stand for many memories. Nothing is lost: a memory that does not
fit is reachable by a printed command that, when run, returns it; decay only demotes
([[feedback_decay_never_loses_knowledge]]); derived subject nodes are marked, never reaped
(ADR-0004 #rule-no-delete).

## Design {#design}

- **Clean STM clusters first (19.0).** Refs come from command lines, not script bodies (fixed at
  `cli._tool_event_fields`, where the junk enters); subagent events are matched by the envelope's
  `tool_use_id` and stay out of the parent's focus; hand-backs are ambient; typos never label a
  cluster; the session comes from one resolver (bug-100), bug-109's
  `verbs.resolve_session_source` EXTENDED (d9s): the hook envelope, then a pointer keyed by the
  Claude process (bug-109's, written by the input hook; 19.0/21.1 add the SessionStart writer, a
  user-level location whose error rows are scoped to their root and owner, a one-shot migration
  of bug-109's per-root files, cleanup and surfaced errors), with a required `purpose` so writes raise
  instead of guessing and only labelled reads may fall back to the newest ring; every
  `latest_session` caller (scan-prompt's enrichment and composite, helix, promote) is routed, and
  so is every command behind the CLI helper `_resolve_stm_session`, which now takes a required
  `purpose` (the Stop and PreCompact hooks' per-turn `focus summarize --promote` resolves from
  its stdin envelope as a `write`); an AST test keeps it so; a subagent's call swept as abandoned
  gets an origin like any other; and the input hook snapshots the pre-prompt STM state as its first state
  access, before its in-flight sweep, so prompt-time readers never race it.
- **Pack, don't truncate; no subject noise (19.1).**
  - `memory recall --pack` emits one hook line per hit, whole bodies for the top hits while the
    budget allows, and a mode-specific trailer naming what was left out.
  - The budget is in UTF-8 bytes (one unit with the event offsets), defaults to
    `RMX_HOOK_BUDGET_BYTES` or a built-in constant set by 19.5's probe; the hook argv never
    interpolates a variable. The pack returns byte spans; 21.1's single emission site emits.
  - `mtype=subject` rows are excluded from recall by default (opt-in flag); `--subject` reaches
    members.
- **Count use, exactly (19.2).** A name-keyed record of RAW per-evidence counts that never decay,
  plus raw per-day counts; recency (under a read-time half-life), weights, the nonzero floor and
  the asserted floor are all computed at READ time (d9e), so no stored value depends on a
  parameter or on how events were batched. Events are 21.1's `recall-events.jsonl` rows, folded by a
  non-consuming tail reader on plan-23's tick, the offset committed in the batch transaction
  (d2a). Global hits are counted in the global store (d8e).
- **Subject-tiered, value-ranked index (19.3).** One line per live subject; fold by score in tiers
  (rest → curated-inbound → feedback, d8b); reachability is checked by running each printed
  command; renders read a score snapshot, not the clock; index files are written atomically under
  one lock.
- **Keep the derived layers current (19.4).** Compile runs as a step on plan-17's nightly tick
  (no save-state fallback, C6), names unlabeled clusters stably, marks stale subjects, and
  regenerates the index; the bridge regenerates it on every memory write.
- **Measure delivery, not production (19.5).** The probe settles per-hook vs per-event and
  PreCompact (d5d); delivery is read from 21.1's events; the fixed baseline is committed for 19.6.
- **Phase the per-prompt budget (19.6, Wave 3).** Recall and scan-prompt spend by STM phase,
  the STM composite renders as an expand/collapse tree (a frozen collapsed line stands for a live
  cluster only when they share ≥ 2 members, at least one of them not a hub, AND Jaccard ≥
  `j_return`; d9ax amended by d9bm, hub = member of ≥ 4 of the cache's 8 newest snapshots),
  returns re-warm from a
  topic cache, stable
  blocks are versioned — each built only in the band a pre-registered table allows; the tables
  were CONFIRMED as written by the user (d9v).

{#design-body}

## What we give up {#tradeoffs}

- **The hooks stop emitting JSON.** `--json` stays for programmatic callers; the hooks switch to
  `--pack` text. No consumer parses hook JSON: the output goes only to the agent's context.
- **Bodies are no longer always inline.** The top hits carry bodies; the rest carry a hook line
  and a fetch pointer.
- **Subject rows leave recall.** A label-only subject row is reachable by name and through
  `--subject`, not as a recall hit.

{#tradeoffs-body}

## Tasks {#tasks}

| task | what | wave | acceptance (summary) |
|---|---|---|---|
| 19.0 | STM cluster hygiene (bug-100, bug-103, bug-104) | 1 (after 23.0; no later than 2) | redacted-fixture replay: no listed junk in the top-5 composites, listed thread terms lead; RED at HEAD |
| 19.1 | `--pack` / `--max-bytes`, subjects excluded, hooks use it | 1 (after 23.1) | payload ≤ budget; ≥ 5x distinct memories; 0 subject rows; argv runs with the env unset |
| 19.2 | exact lifetime + raw per-day counts (recency at read time), folded from `recall-events.jsonl` | 1 (after 23.1, 21.1) | sum not dedupe; recall ≠ use; drop-and-replay identical; global hits in global store; floor > 0 |
| 19.3 | subject-tiered, value-ranked `MEMORY.md` | 2 | executed reachability; tier fold order; clock-free check; atomic triple |
| 19.4 | compile on 17.2's tick; stale marked; index on write and after compile | 2 (after 17.2) | stale subject kept, hidden; stable slugs; new memory indexed without save-state |
| 19.5 | probe (first) + delivery measurement + fixed baseline | R1: Wave 1, before 19.1 (a manual probe, no code dependency); R2–R4 after 19.1–19.3 | per-hook/per-event and PreCompact verdicts; `seen` derived from byte spans; before/after from C7 events |
| 19.6 | phased context, expand/collapse composite, topic cache, versioned injection (recall + scan-prompt) | directly after its dependencies (d9bi; was 3); tables CONFIRMED, d9v | tables A–D; phase/cache/tree fixtures |

Task specs: `workflow/plans/plan-19-adaptive-memory-budget-tasks/`.

## Dependencies {#dependencies}

From [[plan-review-2026-10-14#t8-wave1]]: Wave 1 is 23.0 ∥ 23.4 → 23.2 → 23.1 (+ tick registry)
→ 23.3, with 19.0, 19.1 and 19.2 after 23.1, except **19.0, which needs only 23.0**.

| task | depends on |
|---|---|
| 19.0 | 23.0; bug-109 MERGED to `master` (d9s; its pointer and `verbs.resolve_session_source` are existing code R5 extends). Shares the resolver's deltas and `stm.pre_prompt_state` with 21.1 (specified in 21.1 R9); whichever merges first builds them |
| 19.1 | 23.0; 19.5 R1; 21.1 (R11's single emission site and R10's span fields must be merged FIRST: 19.1's pack returns spans to it; round-3 #m-1; [[plan-review-2026-10-14#t10-waves]] orders 21.1 → 19.1 since `734dc5f`, and both task specs carry the edge); scheduled after 23.1; deploys in the C11 hook window |
| 19.2 | 19.1; 23.0; 23.1 (`bind(partition_name)`, `tail(log, offset)`, tick registry, offset in transaction); 23.2 (recorder); 21.1 (schema) |
| 19.3 | 19.2; 23.0 (static catalog copy; no 19.4, no 22.2) |
| 19.4 | 19.3; 17.2; 23.0 |
| 19.5 | R1: none. R2–R4: 19.1–19.3, 21.1, 23.0 |
| 19.6 | 19.0; 19.1 (incl. d8a); 19.5 R1 + R4; 21.1 fields; 23.0 (the d9f confirmation is given: d9v) |

Every test in every task runs in task 23.0's sandbox (d1a/d1b) and asserts 0 live connects.

## Decisions {#decisions}

| # | decision | source |
|---|---|---|
| d-1 | B (packing) + A (usage) + D (subjects) now | user, 2026-10-07 |
| d-2 | budget = just under the harness's whole-delivery limit (~10k chars), measured, configurable | user, 2026-10-07 |
| d-3 | low-value feedback may fold behind a floor; never lost | user, 2026-10-07 |
| d-4 | own plan; subjects compiled on plan-17's tick | user, 2026-10-07 |
| d8a | subjects excluded from recall by default (opt-in); compile MARKS stale subjects, protected and hidden; removal only via plan-22; expansion listed in 19.6 out-of-scope (replaces d5a) | user, 2026-10-14 |
| d5b | task 19.6, Wave 3, phasing + topic cache + versioned injection over recall AND scan-prompt; turn logged, never a signal; pre-registered ranges | user, 2026-10-14 |
| d8b | FLOOR keeps ADR-0004 #rule-asserted-floor; FOLD ORDER tier feedback → curated-inbound → rest (replaces d5c) | user, 2026-10-14 |
| d5d | 19.5's probe decides PreCompact; until then PreCompact is `retrieved`, never `delivered` | user, 2026-10-14 |
| d5e | task 19.0, STM cluster hygiene, before 19.6, no later than Wave 2 | user, 2026-10-14 |
| d8e | global hits counted in the global store, keyed by name; event carries `scope`; drop-and-replay AC | user, 2026-10-14 |
| d2a/d4a | 19.2 folds `recall-events.jsonl` through plan-23's drain, offset in the batch transaction; sum `merge_fn` | user, 2026-10-14 |
| d8f | raw STM rings and prompt sources stay local; hashes and redacted fixtures are committed | user, 2026-10-14 |
| d8h | 19.0 R2 differentiates subagents by a ladder: envelope id → match against `<session>/subagents/agent-*.jsonl` (meta.json label) → `origin: unattributed`; `agent:<id>` events kept in the ring, out of the parent's focus. Round 2 (#t9-fixes): the match is by the envelope's `tool_use_id`; digest + window (from the PreToolUse park time) only when no id exists | user, 2026-10-14 |
| d9e | 19.2 stores raw per-evidence counts; weights and floors at read time; `base` 0.25, `asserted_floor` 1.0, weights 1/2 are tunable starting defaults | user, 2026-10-14 |
| d9f | 19.6's tables and N=8/K=8 PROPOSED; the user confirms before 19.6 starts | user, 2026-10-14 |
| d9i | one ADR-0004 amendment (floor formula; removal-path scoping), drafted by the orchestrator for the user's approval | user, 2026-10-14 |
| d9k | the ADR-0004 amendment is APPROVED and folded into `#rule-floor`, `#rule-no-delete`, `#rule-asserted-floor` (`3021cd6`) | user, 2026-10-14 |
| d9r | user-asserted memory, for the decay floor = `metadata.type` `user` or `guardrail` (19.2 R7, AC-9) | user, 2026-10-14 |
| d9s | MCP session attribution fixed now as bug-109, ahead of 19.0 R5 / 21.1 R9; the specs extend that code | user, 2026-10-14 |
| d9v | 19.6's ranges, thresholds, `N = 8`, `K = 8`, `C = 6` CONFIRMED as written (settles d9f) | user, 2026-10-14 |
| d9ax | 19.6 R9 snapshot identity = ≥ 2 shared members AND Jaccard ≥ `j_return` (0.20); `j_return` (d9v) now has a second use, acknowledged | user, 2026-10-15 |
| d9ay | d9ao's retirement extends to 19.2 R6 / AC-10 (slot merge); [[#open-after-revision]] item 4 corrected | user, 2026-10-15 |
| d9bi | plan 19 is the helix substrate: it leads Wave 1 after 23.0; 19.6 moves to directly after its dependencies; helix consumes 19.x's outputs (header) | user, 2026-10-15 |
| d9bm | AMENDS d9ax: identity needs ≥ 2 shared members, ≥ 1 of them NOT a hub, AND J ≥ `j_return`; hub = member of ≥ ⌈8/2⌉ = 4 of the cache's 8 newest snapshots; the cache bound `N` = 8 (19.6 R3); `derive_snapshots` stays pure. PROVISIONAL until its ch-bsd loop is clean | orchestrator on the user's pattern, 2026-10-15, from ch-bsd r8 #ns-1 |

## Out of scope {#out-of-scope}

- Concept-level counters and helix age tiers: ADR-0004's helix plan (they import 19.2's library).
- Changing what memories ARE (the GMD format, MEMORY-RULES): this plan changes selection and
  delivery only.
- Removing any memory or subject row: plan-22's audited path only.
- Expanding a subject hit into its members: not planned (19.6 out-of-scope, d8a).

## Open after revision {#open-after-revision}

Round 2 status of the round-1 list ([[bsd-plan19-21-spec-rereview-32dde06#open-19]]):

1. **ADR-0004 #rule-floor's formula text:** SETTLED by d9k (`3021cd6`): `#rule-floor` now reads
   `base * (1 + log1p(hits + 2*used))`, at read time over raw counts, which 19.2 R7 implements.
2. **21.1's uncommitted revision:** MOOT. 21.1 is committed; round 2 re-read the producer
   field by field (19.2 R3, AC-16).
3. **`used` evidence weights:** SETTLED by d9e: raw per-evidence counts, weights at read time
   (19.2 R1, R7, AC-17).
4. **The `replica_merge` offset row:** RETIRED, not closed by 23.1 R8 (round 7, d9ay; the
   earlier text "CLOSED: 23.1 R8 (the larger `offset_bytes` per `(queue, segment)`)" was made
   false by d9ao). 23.1 R8 / AC-13 are RETIRED (d9ao, [[task-23.1-queue-and-drain#r8]]) and 19.2
   R6 / AC-10 with them (d9ay, [[task-19.2-memory-usage-record#rev-round-7]]): writer rotation is
   dropped (`_refresh_replica_now`, `daemon.py:2862` at `23ad703`, a no-op), so nothing produces diverged
   slots, and bug-113 breaks `replica_merge` on every real store. No slot-merge rule is owed by
   plan 19; a plan that revives slot merging writes one for its tables then.
5. **19.6's bands, `N = 8`, `K = 8`, `C = 6` and the phase thresholds:** CONFIRMED as written
   by the user (d9v, settling d9f; 19.6 R0, [[task-19.6-phased-context-and-topic-cache#ranges]]).
6. **19.2 R7's constants** (`base = 0.25`, `asserted_floor = 1.0`, weights 1/2): ACCEPTED by d9e
   as tunable starting defaults; the 91%-at-asserted-floor interaction is recorded in 19.2 R7 and
   made visible by `at_floor`.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 19 #b-1; d8a | [[task-19.1-pack-recall-under-budget#requirements]] R2; [[task-19.4-keep-derived-layers-current#requirements]] R5 |
| 19 #b-2 | [[task-19.1-pack-recall-under-budget#requirements]] R1, R4 |
| 19 #b-3 | [[task-19.3-subject-tiered-index#requirements]] R4 |
| 19 #b-4 | [[task-19.2-memory-usage-record#requirements]] R7; 19.3 R2–R3; [[#open-after-revision]] 1 |
| 19 #b-5; d2a; d4a | 19.2 R5 |
| 19 #b-6 | 19.2 R3 |
| 19 #b-7; d1a/d1b | every task's test strategy; [[#dependencies]] |
| 19 #s-1; d5d | 19.5 R1(c); 19.1 R4; 19.2 R3 |
| 19 #s-2 | 19.5 R1(b); 19.1 R1 |
| 19 #s-3 | 19.1 R3, R7, AC-2 |
| 19 #s-4; d8e | 19.2 R1, R4, R5, AC-6, AC-8; 19.1 R6 |
| 19 #s-5; d8b | 19.3 R3, AC-3 |
| 19 #s-6 | [[#dependencies]]; task headers |
| 19 #s-7; d8a | 19.4 R3, R5, R6; 19.3 R1 |
| 19 #s-8 | 19.3 R5, R8; 19.4 R2 |
| 19 #s-9 | 19.3 R7 |
| 19 #s-10; d5b | [[task-19.6-phased-context-and-topic-cache#requirements]] R4, R7 |
| 19 #m-1 | 19.3 Why (`:351`); 19.4 Why (`cli.py:12695`) |
| 19 #m-2 | [[#why-body]]; 19.1 #why-baselines; 19.3 AC-1 |
| 19 #m-3 | [[#design-body]] (save-state fallback removed) |
| 19 #m-4 | 19.1 header (C11 window) |
| 19 #m-5 | 19.1 R3(d) |
| 19 #m-6 | 19.5 R2 |
| 19 #placement | 19.6 R2 (pre-prompt state), R0 (pre-registration), R4 (scan-prompt owner) |
| d5b | 19.6 |
| d5e; #t5-stm-hygiene; d5e amendments | [[task-19.0-stm-cluster-hygiene#requirements]] |
| d8h | 19.0 R0, R2, R6, AC-4..AC-4d |
| d8f | 19.0 R6; 19.1 AC-2; 19.5 R4; 19.6 R1 |
| decision-log #b-1 | 19.4 R5, AC-4 |
| decision-log #b-2 | 19.2 R7 (floor keeps the ADR definition); 19.3 R3 (separate fold tier); 19.3 header (no 22.2 dependency) |
| decision-log #b-6 item 3 | 19.6 out-of-scope |
| decision-log #s-1 | 19.2 R5 (retention), R6 (`replica_merge`) |
| decision-log #s-3 | 19.2 R5 (tail reader, tick registry) |
| decision-log #s-4 | 19.2 R4 |
| decision-log #s-10 | 19.0 R0, R5, R6, AC-1, AC-2 |
| decision-log #m-1 | 19.0 R4 |
| decision-log #m-6 | this table enumerates 19 #m-1..#m-6 by id |
| #t8-wave1 | [[#dependencies]], [[#tasks]] |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]], [[plan-review-2026-10-14#t9]] (d9e, d9f, d9i) and
[[plan-review-2026-10-14#t9-fixes]]. Each task carries its own `#rev-round-2` table.

| finding / decision | answered at |
|---|---|
| re-review #b-1 (19.2 side) | [[task-19.2-memory-usage-record#rev-round-2]] |
| re-review #b-3, #b-4 | [[task-19.0-stm-cluster-hygiene#rev-round-2]] |
| re-review #b-5 (19.2 side) | 19.2 R3, R4, AC-8 |
| re-review #s-1, #s-2 | 19.1 R1, R8; 19.2 R3; 19.5 R2 |
| re-review #s-4; d9f | [[task-19.6-phased-context-and-topic-cache#rev-round-2]] |
| re-review #s-5; d9e | 19.2 R7; [[#open-after-revision]] 6 |
| re-review #s-6 | [[task-19.4-keep-derived-layers-current#rev-round-2]] |
| re-review #m-1 | 19.1 AC-3, header; [[#tasks]] (19.5 R1 in Wave 1) |
| re-review #m-2, #m-3 | 19.2 R1, R3; 19.5 R1 |
| re-review #m-5 | 19.6 R8a |
| re-review #open-19 items 1-6; d9i | [[#open-after-revision]] |
| user, 2026-10-14: expand/collapse composite | [[#design-body]]; 19.6 R9, R10, Table D |
| prior partials 19 r1 #b-4, #b-6 | 19.2 R7 (+ d9i pending ADR text); 21.1 R12 + 19.2 R3 |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan19-21-spec-rereview-r3-6091648]], [[plan-review-2026-10-14#t9-approvals]]
(d9k) and the 23+17 round-3 note on 19.4 ([[bsd-plan23-17-spec-rereview-r3-6091648#nm17-r3-5]]).
Each touched task carries its own `#rev-round-3` table.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r3-6091648]]

| finding / decision | answered at |
|---|---|
| round-3 #b-1 (19.0 R5: the MCP server's session id is frozen at spawn) | [[task-19.0-stm-cluster-hygiene#rev-round-3]] (R5, R0, AC-6b, AC-6c); the resolver is specified once in 21.1 R9; [[#design-body]] |
| round-3 #b-2 (19.6 phase inputs read a graph the input hook already changed) | [[task-19.0-stm-cluster-hygiene#rev-round-3]] (R7, AC-6d); [[task-19.6-phased-context-and-topic-cache#rev-round-3]] (R2, R3, AC-3c) |
| round-3 #s-2 (decay vs a sum `merge_fn`; `H` not read-time) | [[task-19.2-memory-usage-record#rev-round-3]]; [[#design-body]]; [[#tasks]] |
| round-3 #s-3 (19.2 side) | 19.2 R5, AC-16 |
| round-3 #s-4 (19.6 collapsed line) | [[task-19.6-phased-context-and-topic-cache#rev-round-3]] (R9, AC-7c, AC-7d, AC-7g; `C` PROPOSED) |
| round-3 #m-1 (`--max-chars`, "character budget", pending ADR wording, user-asserted floor, 21.1 → 19.1 edge) | [[#tasks]] (`--max-bytes`); 19.1 title; [[#open-after-revision]] item 1 and [[#decisions]] d9k; 19.2 R7; [[#dependencies]] (19.1 row) |
| round-3 #m-2, #m-4 | 19.0 R1, R2, R0; AC-1d, AC-4f |
| round-3 #m-3 | 19.1 AC-1, AC-6 |
| round-3 #m-5, #m-6 | 19.6 R7, R8a, AC-7b, AC-7f; [[exploration-session-phased-context#shape]], `#decisions`, `#tree-render` |
| round-3 #m-8 | 19.5 R1(a), R2; 19.1 AC-2 |
| round-3 [[bsd-plan19-21-spec-rereview-r3-6091648#open-19]] item 5 (19.6 numbers) | still a user decision (d9f), now over a well-defined classifier (#b-2, #s-4 fixed first); `C = 6` joins the PROPOSED set |
| round-3 #open-19 "tell the user" (MCP-route session attribution is broken TODAY) | not a spec item: reported to the orchestrator for the user. Today an MCP `rmx_focus_note` / `rmx_save_state` / `rmx_task` resolves through `RMX_SESSION` → `latest_session` (`verbs.py:519-530`), which is right only while one session is active; 19.0 R5 fixes it |
| nm17-r3-5 (19.4 AC-2 vs `requires_arming=True`) | [[task-19.4-keep-derived-layers-current#rev-round-3]] |

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan19-21-spec-rereview-r4-878647c]] and d9r / d9s / d9v of
[[plan-review-2026-10-14#t11-approvals]]. Each touched task carries its own `#rev-round-5` table.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r4-878647c]]

| finding / decision | answered at |
|---|---|
| round-4 #b-1 (snapshot after the sweep) | [[task-19.0-stm-cluster-hygiene#rev-round-5]] (R7, AC-6d); [[task-19.6-phased-context-and-topic-cache#rev-round-5]] (R2, AC-3c); [[#design-body]] |
| round-4 #b-2 (three unrouted `latest_session` callers) | [[task-19.0-stm-cluster-hygiene#rev-round-5]] (R5 caller table, AC-6, AC-6c, AC-6e); 19.6 R2, R9, Files; [[#design-body]] |
| round-4 #s-1 (bug-109 owns the pointer) | 19.0 header, R5, AC-6b, AC-6c, test strategy; [[#dependencies]] (19.0 row); [[#decisions]] d9s |
| round-4 #s-2 (`day` on a zone-less `ts`) | [[task-19.2-memory-usage-record#rev-round-5]] (R1, R7, AC-6) |
| round-4 #s-3 (collapsed line vs unstable member set; one versioned block) | [[task-19.6-phased-context-and-topic-cache#rev-round-5]] (R9 snapshots, re-collapse; R5 two blocks; R1; AC-7d, AC-7d2, AC-7h) |
| round-4 #m-1, #m-2 | 19.0 R0, R5, R7, AC-6d, AC-6e (and 21.1 R9) |
| round-4 #m-3 | 19.6 R8a + Files (marker dispatch); status lines flipped (d9v). The `#t10-waves` bullet is the decision log's: handed back to the orchestrator |
| round-3 #b-1, #b-2, #s-4 (partial) | as round-4 #s-1, #b-1, #s-3 |
| d9r | 19.2 R7 (already so); [[#decisions]] |
| d9s | 19.0 R5 (bug-109's deferred items listed); [[#decisions]] |
| d9v | 19.6 R0, [[task-19.6-phased-context-and-topic-cache#ranges]]; [[#design-body]], [[#tasks]], [[#dependencies]], [[#open-after-revision]] item 5; [[#decisions]] |

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan19-21-spec-rereview-r6-0e77da3]]. No round-6 decision-log row names plan 19
([[plan-review-2026-10-14#t12-approvals]]: d9ao-d9ar are plans 16/17/22/23); nothing here needs
the user. Each touched task carries its own `#rev-round-6` table; code facts were read at HEAD
`3d3c798` (`src/` = `master` `c7129e6`, bug-109 r1-r4 merged).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r6-0e77da3]]

| finding / decision | answered at |
|---|---|
| round-6 #b-1 (bug-109 read at r1, not as merged) | [[task-19.0-stm-cluster-hygiene#rev-round-6]] (header, R0, R5 "Existing code" and deferred items, Files); the deltas and their ACs: [[task-21.1-context-usage-telemetry#rev-round-6]] |
| round-6 #b-2 (the CLI helper's 15 callers unrouted, the Stop hook's promote among them) | [[task-19.0-stm-cluster-hygiene#rev-round-6]] (R5 helper + table, AC-6c, AC-6e, mutations); [[#design-body]] |
| round-6 #s-1 (swept calls bypass the origin ladder) | [[task-19.0-stm-cluster-hygiene#rev-round-6]] (R2 "Swept calls", AC-4g, AC-4h); 21.1 R9 step 3; [[#design-body]] |
| round-6 #s-2 (frozen snapshot: two writers; "≥ 1 shared member") | [[task-19.6-phased-context-and-topic-cache#rev-round-6]] (R3, R9, R1, AC-3c, AC-7i) |
| round-6 #s-3 (in-daemon render reads the stale replica; bug-112) | [[task-19.3-subject-tiered-index#rev-round-6]] (R5); [[task-19.4-keep-derived-layers-current#rev-round-6]] (R2, R3, AC-1-AC-3) |
| round-6 #m-1 (citations stale since the merge) | 19.0, 19.4 and 21.1 `#rev-round-6` tables |
| round-6 #m-2 (21.1 → 19.1 edge one-sided; stale clause) | [[#dependencies]] (19.1 row: the "parallel bullets" clause replaced); 21.1 `rel: related-to -> [[task-19.1-pack-recall-under-budget]]` |

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan19-21-spec-rereview-r7-331b414]] and the user's round-7 decisions d9ax (19.6
identity, option (a)) and d9ay (19.2's slot-merge path retired), plus the one-shot migration
choice for #s-3 ([[plan-review-2026-10-14#t12-approvals]]). Each touched task carries its own
`#rev-round-7` table; code facts were read at HEAD `77ac38f`, whose `src/` equals the review's
`331b414`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r7-331b414]]
rel: implements -> [[plan-review-2026-10-14#t12-approvals]]

| finding / decision | answered at |
|---|---|
| round-7 #s-1; d9ax (one hub member merges small clusters; `j_return` reused) | [[task-19.6-phased-context-and-topic-cache#rev-round-7]] (R9, R1, `#ranges-thresholds`, AC-7i, mutations); [[#design-body]]; [[#decisions]] d9ax |
| round-7 #s-2 (the user-level error log and watermark unscoped) | [[task-21.1-context-usage-telemetry#rev-round-7]] (D6-D8, AC-4b (vii), (viii)); [[task-19.0-stm-cluster-hygiene#rev-round-7]] (R5 deferred items, Files); [[#design-body]] |
| round-7 #s-3 (two "one release" legacy reads); the user's one-shot migration | [[task-21.1-context-usage-telemetry#rev-round-7]] (D3, D6, AC-4b (ii), (vi)); 19.0 Files and R5 deferred items |
| round-7 #s-4 (a `write` miss never pinned to its row) | [[task-19.0-stm-cluster-hygiene#rev-round-7]] (R5 Stop row, AC-6c); [[task-21.1-context-usage-telemetry#rev-round-7]] (AC-4 read and write legs) |
| round-7 #m-1 (sweep unbounded in total; "no daemon calls" unasserted; user note: bug-115/116 in 0.78.2) | [[task-19.0-stm-cluster-hygiene#rev-round-7]] (R2 `SWEEP_READ_CAP`, AC-4d, AC-6f); 21.1 test strategy |
| round-7 #m-2, #m-3, #m-4 (b)-(d) | [[task-19.0-stm-cluster-hygiene#rev-round-7]] |
| round-7 #m-4 (a), (b) (21.1 side) | [[task-21.1-context-usage-telemetry#rev-round-7]] |
| d9ay (19.2 R6 / AC-10 retired; "CLOSED: 23.1 R8" corrected) | [[task-19.2-memory-usage-record#rev-round-7]]; [[#open-after-revision]] item 4; [[#decisions]] d9ay |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]] (2 SKETCHY, 7 MEH), decision d9bm (#ns-1,
option (a); PROVISIONAL until its ch-bsd loop is clean) and d9bi (helix substrate)
([[plan-review-2026-10-14#t12-approvals]]). Each touched task carries its own `#rev-round-8`
table; code facts were read at HEAD `23ad703`, by symbol, then line.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]
rel: implements -> [[plan-review-2026-10-14#t12-approvals]]

| finding / decision | answered at |
|---|---|
| round-8 #ns-1; d9bm (hub-only matches are most of d9ax's identity matches; "hub" undefined) | [[task-19.6-phased-context-and-topic-cache#rev-round-8]] (R9 hub rule and `topic_hubs` / `snapshot_eligible`; R1; `return` row; AC-7i H1-H5; mutations); [[#design-body]]; [[#decisions]] d9bm |
| round-8 #ns-2 (an ended session's rows surface on no SessionStart) | [[task-21.1-context-usage-telemetry#rev-round-8]] (D6 `ended_sessions`, per-root watermark, AC-4b (ix)); 19.0 R5's Stop row holds ([[task-19.0-stm-cluster-hygiene#rev-round-8]]) |
| round-8 #nm-1, #nm-2 | [[task-21.1-context-usage-telemetry#rev-round-8]] (D6 unowned rule; D8 one locked writer; migration claim and order) |
| round-8 #nm-3, #nm-4 | [[task-19.0-stm-cluster-hygiene#rev-round-8]] (AC-6f; envelope rows; falsy session); 21.1 D9 (one envelope reader) |
| round-8 #nm-5 | 21.1 R3/R4/R7, AC-2b; [[task-19.5-measure-delivery#rev-round-8]] (`skipped_budget` = attempted, 0 delivered); [[task-19.2-memory-usage-record#rev-round-8]] (AC-12 `max_hold_s` ≤ 0.5 s); 21.3 R3 |
| round-8 #nm-6 | [[task-19.4-keep-derived-layers-current#rev-round-8]] |
| round-8 #nm-7 (cite drift) | the `#rev-round-8` tables of 19.0, 19.1, 19.2, 19.3, 19.4 and 21.1; [[#open-after-revision]] item 4 (`daemon.py:2862`) |
| d9bi (helix substrate; 19.6 pulled forward) | header ("Helix substrate": the four interfaces and the decision-row rule); [[#tasks]] 19.6 wave; [[#decisions]] d9bi; [[task-19.6-phased-context-and-topic-cache#rev-round-8]] header |
| user rule: converge repeated shapes into one function | 19.6 `topic_hubs` / `snapshot_eligible`; 21.1 `owner_alive`, `_append_error_rows`, `read_hook_envelope`, `CALL_OUTCOMES`; each with an AST or import bypass check |

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]] (4 SKETCHY, 7 MEH; edit-level, no decision).
Each touched task carries its own `#rev-round-9` table.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]]

| finding | answered at |
|---|---|
| r9 #s9-1 (the identity assignment has no single home; helix-facing) | [[task-19.6-phased-context-and-topic-cache#rev-round-9]]; header interface 2 (`match_snapshots`, `member_jaccard`, `topic_match`, cache `schema: 1`); 21.1 R9 `PrePromptState.topic_match` ([[task-21.1-context-usage-telemetry#rev-round-9]]) |
| r9 #s9-2, #s9-4, #m9-1 to #m9-5 | [[task-21.1-context-usage-telemetry#rev-round-9]] |
| r9 #s9-3 (a second `sitecustomize` collides with 23.0's) | [[task-19.0-stm-cluster-hygiene#rev-round-9]] (AC-6f uses 23.0's one sandbox hook through `$RMX_SANDBOX_CONNECT_LOG`; two control legs) |
| r9 #m9-6 | [[task-19.2-memory-usage-record#rev-round-9]] |
| r9 #m9-7 | [[#decisions]] d9bm (the "K = 8" parenthetical deleted); 19.6 R9; [[task-19.0-stm-cluster-hygiene#rev-round-9]] (AC-6 RED sentences split; AC-6f `--event say`) |
| user rule: converge repeated shapes into one function, each with a bypass check that can fail | 19.6 `match_snapshots`, `member_jaccard`; 21.1 `liveness_available`, `errors_log_path`, `HOOK_PROMPT_KEYS`, `read_hook_envelope(prose_ok=)`, `CALL_OUTCOMES` validated in `log_query`; 23.0's one sandbox hook; each check carries a control leg that makes it fail |
