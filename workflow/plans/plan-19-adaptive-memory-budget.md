---
gmd: "0.1"
id: plan-19-adaptive-memory-budget
title: "Plan 19: memory reaches the agent within budget, ranked by use, grouped by subject, and never lost"
tags: [plan, memory, recall, hooks, budget, memory-index, adaptive, stm]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
---

# Plan 19: adaptive memory under the context budgets {#root}

**Date:** 2026-10-07; revised 2026-10-14 after the Wave 0 decision log.
**Status:** Drafting. Task specs 19.0–19.6 are revised after
[[plan-review-2026-10-14]]; a spec re-review is next.
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
  user-level location, cleanup and surfaced errors), with a required `purpose` so writes raise
  instead of guessing and only labelled reads may fall back to the newest ring; every
  `latest_session` caller (scan-prompt's enrichment and composite, helix, promote) is routed, an
  AST test keeps it so; and the input hook snapshots the pre-prompt STM state as its first state
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
  the STM composite renders as an expand/collapse tree, returns re-warm from a topic cache, stable
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
| 19.6 | phased context, expand/collapse composite, topic cache, versioned injection (recall + scan-prompt) | 3 (tables CONFIRMED, d9v) | tables A–D; phase/cache/tree fixtures |

Task specs: `workflow/plans/plan-19-adaptive-memory-budget-tasks/`.

## Dependencies {#dependencies}

From [[plan-review-2026-10-14#t8-wave1]]: Wave 1 is 23.0 ∥ 23.4 → 23.2 → 23.1 (+ tick registry)
→ 23.3, with 19.0, 19.1 and 19.2 after 23.1, except **19.0, which needs only 23.0**.

| task | depends on |
|---|---|
| 19.0 | 23.0; bug-109 MERGED to `master` (d9s; its pointer and `verbs.resolve_session_source` are existing code R5 extends). Shares the resolver's deltas and `stm.pre_prompt_state` with 21.1 (specified in 21.1 R9); whichever merges first builds them |
| 19.1 | 23.0; 19.5 R1; 21.1 (R11's single emission site and R10's span fields must be merged FIRST: 19.1's pack returns spans to it; round-3 #m-1, an edge [[plan-review-2026-10-14#t10-waves]] lists as parallel bullets); scheduled after 23.1; deploys in the C11 hook window |
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
4. **The `replica_merge` offset row:** CLOSED: 23.1 R8 (the larger `offset_bytes` per
   `(queue, segment)`).
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
