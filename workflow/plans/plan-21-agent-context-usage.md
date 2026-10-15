---
gmd: "0.1"
id: plan-21-agent-context-usage
title: "Plan 21: the agent uses rmx context because it answers — telemetry, precise identifiers, a nudge, NL ranking"
tags: [plan, context, agent, telemetry, ranking]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
  updated: 2026-10-15
---

# Plan 21: agent context usage {#root}

**Date:** 2026-10-07 (revised 2026-10-14 after the Wave 0 decision log)
**Status:** Drafting. Task specs 21.1–21.4 were revised against the plan-21 spec review r1
(`3104a81`, NEEDS-REVISION, 3B/13S/7M) and the 2026-10-14 decision log; the next step is the
re-review of this revision.
**Origin:**
- The user, 2026-10-07: "given we're making grep passive, we should look into how to expand your
  rmx context usage" ([[exploration-agent-context-usage]]).
- The tasks were first specced as plan-16's 16.7–16.10, then split out by the plan review (C8,
  approved by the user 2026-10-07), so their review loop and the grep shim's do not block each
  other.
- The user, 2026-10-14: phased context and the topic cache ([[exploration-session-phased-context]])
  are measured by 21.1's events; plan-19's 19.6 owns the mechanism (d5b). Plan-21 only measures.

rel: derives-from -> [[exploration-agent-context-usage]]
rel: derives-from -> [[plan-review-2026-10-07]]
rel: derives-from -> [[plan-review-2026-10-14]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[bsd-decision-log-review-a192ba2]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[plan-16-invisible-grep-shim]]
rel: related-to -> [[exploration-session-phased-context]]
rel: related-to -> [[plan-19-adaptive-memory-budget]]

## Why {#why}

In 14 days (2026-09-23 to 2026-10-07T11:06) the CLI ran `rmx context` 3 times against 1,119 agent
greps, and MCP `rmx_context` calls were not logged at all. Identifier lookups are ~55% of the
agent's greps. A replay of 9 identifiers gave 4 hits, 4 partials (no line number) and 1 miss. NL
queries missed 5 of 6. All 20 replay rows ran on the CLI REPLICA route, which has never been given
a reranker (`cli.py:5100`, no `reranker=`); `2cd73b9` fixed only the daemon route's no-anchor
hand-off, so the replay says nothing about reranked ranking (bsd #s-8). Once grep is passive
(plan-16), the index reaches the agent only when asked by name. {#why-body}

## Tasks {#tasks}

| task | wave | what | acceptance (summary) | depends on |
|---|---|---|---|---|
| 21.1 | 1 | agent-usage telemetry: `mcp` + `agent` sources with a stated precedence, one `query.log` row per context route with `session`/`query_id`/`cwd`, `grep-stdin` cardinality, `rmx telemetry --agent-usage`, and the ONE recall-event schema written to `recall-events.jsonl` by named emitters | each route writes exactly one row; a real `scan-prompt` and a real per-prompt recall write `retrieved`/`delivered` events; the frozen fixture reports 3 / 1,119 / 34 exactly | 23.0 only |
| 21.2 | 3 | precise identifier context: `path:line` on DEFINED BY, one id form, labels checked against emission direction, TESTED BY defined, no helix on code anchors, `--brief` | the frozen 9-name replay goes from the recorded baseline to ≥ 8 of 9 gold `path:line` hits | 21.1, 23.0 |
| 21.3 | 3 | PostToolUse nudge for an identifier-shaped grep naming an indexed symbol with callers/tests, built per the band R0's measured hook wall time lands in | R0's band recorded before code; one line on indexed symbols, none on others; usage per session before/after | 16.1, 16.2, 21.1, 21.2, 23.0 |
| 21.4 | 3 | the frozen NL question set (code + doc strata; the ONE ranking-eval harness, C9), both routes measured, ranking fixes kept only on a pre-registered win, then one rule on all five surfaces | the R2 table; every shipped change wins by the pre-registered margin; generated surfaces agree | 21.1, 21.2, 23.0 |

Task specs: `workflow/plans/plan-21-agent-context-usage-tasks/`. Waves follow
[[plan-review-2026-10-14#t8-wave1]] (21.1 needs only 23.0) and the 2026-10-07 order
([[plan-review-2026-10-07#order]]: the old 16.8–16.10 sit in Wave 3).

## Consolidations this plan carries (plan review) {#consolidations}

- **C7, one recall-event schema.** 21.1 R8–R12 (with R10a's `kind` map) define it for every
  consumer, in a NEW append-only
  `recall-events.jsonl` written lock-free like `query.log` (d4a). The field set closes bsd #b-1
  (`session`, `turn`, `query_id`), #b-2 (`name` + `entity_id` + `kind`; `channel` is a closed
  SURFACE enum, separate from `invocation`), #s-1 (`delivered` = emitted, with `offset_bytes` /
  `bytes` / `payload_bytes`, so `seen` is derived against any cap), #s-2 (phase fields: `arm`,
  `policy`, the raw phase inputs, `restored_cluster_id`), d8e (`scope`), and the versioned-injection
  fields `block_id`, `rev`, `unchanged` ([[exploration-session-phased-context#vi-evidence]]).
  Round 2 adds `partition`, `cwd`, `root` (re-review #b-1), byte spans with a separate body span
  (ONE unit, bytes), ONE emission site that owns `delivered` (19.1's pack supplies spans only),
  and the `used` matcher / lookup / global destination (21.1 R5, R9-R12). Round 3 adds ONE
  session resolver, ONE pre-prompt snapshot read (`stm.pre_prompt_state`) for every phase
  input, the catalog→event `kind` map with `concept`, the recall channel rule, and the attached
  memory body as its own `kind=memory` item (21.1 R9-R12). Round 5 (d9s): the resolver is
  bug-109's existing `verbs.resolve_session_source` and pid pointer, EXTENDED (a required
  `purpose`, the SessionStart writer, a user-level pointer location, surfaced errors), never
  rebuilt; the snapshot is the input hook's first state access, before its in-flight sweep; and
  every event's `ts` is UTC.
  - **Consumers:** 19.2's counters fold the file into DuckDB through plan-23's drain with the
    offset committed in the same transaction (d2a), using 23.1's non-consuming tail reader and
    tick registry (d4a amendment; plan-21 is a listed consumer); it counts `kind=memory` events on
    21.1's channel enum (19.2 R3). 19.5 R2 is the only deriver of `seen` and compares it with
    `delivered`. 19.6 reads the phase fields (d5b). 21.3 AC-4 and 21.1's report read `session`.
  - **21.1's emission does not depend on plan-23** (d4a): it appends to a file; only the fold does.
  - The file is the retained replay source and is never rotated away before it is folded
    (d2a amendment).
- **C9, one ranking-eval harness.** 21.4's frozen NL question set is the shared harness for:
  21.4's own ranking candidates, and ADR-0004's sentence co-location rerank (which needs bug-075
  fixed first). Its gold covers code AND doc sections (d4b), reported per stratum. **Sessions are
  out** (d4b): plan-13's session-inclusion question is NOT judged by this harness and stays dormant;
  the pointer is this anchor.

{#consolidations-body}

## Decisions this plan carries (2026-10-14) {#decisions}

- **d4a** — the sink: 21.1 R8.
- **d4b** — code + doc gold, sessions out, minimum win and n: 21.4 R1, AC-3; this plan
  [[#consolidations]].
- **d4c**, constrained by **d8f** — the question set is drawn from real `query.log` NL queries by an
  agent that never reads the ranking code, approved by the user, its hash committed before tuning;
  raw queries stay local and gitignored, only the hash and a redacted fixture are committed:
  21.4 R1, AC-1.
- **d4d** with the [[plan-review-2026-10-14#t4-nudge-ranges]] table and the close-out amendment —
  21.3 R0 and its conditional R6.
- **d4e** — no habit memory. `feedback_rmx_first_retrieval` exists, and a voluntary rule is the
  channel that goes unused; the nudge (21.3) is the mechanism. Closes bsd #m-7.
- **d4f** — the `agent` invocation source: 21.1 R2.
- **d8d** — one shared pytest-temp-dir predicate for every `query.log` / `recall-events.jsonl`
  reader: 21.1 R5.
- **d8e** — `scope` on every event; a global hit is counted in the global store: 21.1 R8, R10,
  R12.

## Dependencies {#dependencies}

- **21.1** needs **23.0** (the shared test sandbox, d1a/d1b), per
  [[plan-review-2026-10-14#t8-wave1]], and **bug-109 merged to `master`** (d9s): R9 extends its
  session pointer and resolver as existing code (merged at `0c7d0e0`, 0.78.0). It runs in Wave 1.
  It is the instrument 19.2, 19.5 and 19.6 consume, and 19.1 must merge AFTER it (19.1's pack
  returns byte spans to 21.1 R11's single emission site; [[plan-review-2026-10-14#t10-waves]]
  orders 21.1 → 19.1). It does not wait on plan-23's queue (d4a).
- **21.2** needs 21.1 (to measure) and 23.0. Its replica reads rely on ch-bsd r9's partition
  binding (`09db9a6`).
- **21.3** needs 16.1 (the argv parser), 16.2 (the shim removes the old stderr hint), 21.1 (the
  `session` field and the `nudge` channel), 21.2 (TESTED BY and the answer it points at), and
  23.0.
- **21.4** needs 21.1 (the `internal` source and the pytest-temp predicate the draw filters with),
  21.2, and 23.0. Its replica-route rerank candidate relies on r9's real budget (`with_budget`).
- **Every test in every task runs inside 23.0's sandbox** (`$HOME`, global root, registry and
  LaunchAgents redirected before import; spawned `rmx` children refuse sockets outside the tmp
  dir) and asserts that the live `.refmatrix/query.log`, `~/.refmatrix/query.log` and any live
  `recall-events.jsonl` line counts are unchanged (bsd #s-7: no test writes the log it measures).
- **C11 (batch hook deploys, bsd #m-5):** 21.3 regenerates hooks and 21.4 regenerates
  `.refmatrix/CLAUDE.md` through `install-hooks`. Both ship in the same `install-hooks --apply
  --force` window as 16.2/16.3 and 19.1 R3 where the waves allow; neither runs its own
  regeneration window.

{#dependencies-body}

## Open after revision {#open-after-revision}

Round 2 status of the round-1 list ([[bsd-plan19-21-spec-rereview-32dde06#open-21]]):

1. **Legacy rows without `cwd`:** SETTLED. Legacy rows are counted with a printed
   `legacy_unattributed` count; the 235 `alpha|beta` fixture rows are excluded by exact shape as
   `legacy_fixture_rows` (d9g): 21.1 R5, AC-6, AC-7.
2. **Transcript-scorer owner:** SETTLED. 19.6's `score_readback.py`
   ([[task-19.6-phased-context-and-topic-cache#ranges]]), offline, never appending to the live
   log; 21.1 R12 reserves the evidence names.
3. **Exploration corrections** ([[exploration-agent-context-usage#telemetry]] `-E` bullet,
   `#replay` reranker caveat, "68 → 34"): CLOSED. Made in `69c5dc4` (round-3 #m-1 verified the
   diff: 34 recalls, the `-E` claim struck, the replica-route reranker caveat).
4. **plan-13's pointer:** CLOSED. `69c5dc4` edited plan-13's header and its plan-of-plans row.
5. **19.2 R3's channel enum:** SETTLED in 19.2 R3 (21.1's enum verbatim; `cli`/`mcp` removed).
6. **21.4 source log:** SETTLED, project log only (d9h): 21.4 R1.
7. **MCP tools beyond context and recall:** CLOSED by the narrowing (bsd r1 #s-5 option 1).

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding or decision | answered at |
|---|---|
| bsd #b-1, #b-2, #b-3, #s-1, #s-2 | [[#consolidations]]; 21.1 R6–R9 |
| bsd #s-7 / d1a, d1b | [[#dependencies]]; every task's test strategy |
| bsd #s-8 | [[#why]]; 21.4 `#why` |
| bsd #s-9 / d4b | [[#consolidations]]; 21.4 R1, AC-3 |
| bsd #m-4 / d4a | [[#tasks]], [[#dependencies]] (21.1 needs only 23.0; the sink is a file) |
| bsd #m-5 (C11) | [[#dependencies]] |
| bsd #m-7 / d4e | [[#decisions]] |
| d4a, d4c, d4d, d4f, d8d, d8e, d8f | [[#decisions]] |
| decision-log #s-3 (tail reader, tick registry) | [[#consolidations]] (consumer edge; owner 23.1) |
| decision-log #b-6, #s-9 (d4d last band, symbol-set owner) | 21.3 R0, R6 |
| decision-log #m-2 (`CLAUDECODE` precedence) | 21.1 R2 |
| decision-log #m-6 (MEH ids enumerated) | each task's revision table lists m-1..m-7 by id |
| #t8-wave1 | [[#tasks]], [[#dependencies]] |
| unsettled gaps | [[#open-after-revision]] |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]] /
[[plan-review-2026-10-14#t9-fixes]].

| finding / decision | answered at |
|---|---|
| re-review #b-1 (schema side) | [[#consolidations]]; [[task-21.1-context-usage-telemetry#rev-round-2]] |
| re-review #b-2; d9g | 21.1 R5, AC-6, AC-7; [[#open-after-revision]] 1 |
| re-review #b-5 (emitter side) | 21.1 R12, AC-11a-d |
| re-review #s-1, #s-2, #s-3 | 21.1 R9-R11, AC-8, AC-8b; 19.1 R8; 19.5 R2 |
| re-review #s-7, #m-6 | [[task-21.3-indexed-symbol-nudge#rev-round-2]] |
| re-review #m-4; d9h | [[task-21.4-surfaces-and-nl-ranking#rev-round-2]] |
| re-review #open-21 items 1-7 | [[#open-after-revision]] |
| #t9-fixes "d8d's predicate owned by 21.1 in `telemetry.py`" | 21.1 R5 (`row_provenance`, `is_test_artifact_row`, exact signatures) |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan19-21-spec-rereview-r3-6091648]]. No plan-21 item needs the user
([[bsd-plan19-21-spec-rereview-r3-6091648#open-21]]).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r3-6091648]]

| finding / decision | answered at |
|---|---|
| round-3 #b-1 (21.1 R9/R12: the MCP server's session id is frozen at spawn) | [[task-21.1-context-usage-telemetry#rev-round-3]] (R1, R9 resolver + pid pointer, R12, AC-1, AC-1b, AC-4); [[#consolidations]] |
| round-3 #b-2 (21.1 R10 sibling phase inputs racy) | 21.1 R9 pre-prompt state, R10, AC-8b |
| round-3 #b-3 (AC-8 mutations vacuous; channel rule; scan-prompt partition) | 21.1 R11, AC-8, AC-8c, AC-8d; [[task-21.3-indexed-symbol-nudge#rev-round-3]] (the nudge leg) |
| round-3 #s-1 (`kind` map; concept-anchored memory body) | 21.1 R10a, R11, R12, AC-11e, AC-12 |
| round-3 #s-3 (`row_provenance` two test bases; `malformed`) | 21.1 R5, AC-7 |
| round-3 #m-1 (stale R-numbers; open items 3 and 4) | [[#consolidations]] (R8-R12); [[#decisions]] (d4a R8; d8e R8, R10, R12); [[#open-after-revision]] items 3 and 4 CLOSED |
| round-3 #m-7 (focus-note edge cases) | 21.1 R12, AC-11f |

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan19-21-spec-rereview-r4-878647c]] and d9s of
[[plan-review-2026-10-14#t11-approvals]]. No plan-21 item needs the user.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r4-878647c]]

| finding / decision | answered at |
|---|---|
| round-4 #b-1, #b-2, #s-1, #s-2, #m-1, #m-2 (21.1 side) | [[task-21.1-context-usage-telemetry#rev-round-5]] |
| round-4 #s-1 (dependency on the merge, not a sha) | [[#dependencies]] (21.1); [[#consolidations]] |
| round-4 #m-3 | not a plan-21 item (19.6; the decision log's wave list) |
| round-3 #b-1, #b-2 (partial) | as round-4 #s-1, #b-1 |
| d9s | [[#dependencies]]; [[#consolidations]]; 21.1 R1, R9 |

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan19-21-spec-rereview-r6-0e77da3]]. No round-6 decision-log row names plan 21
([[plan-review-2026-10-14#t12-approvals]]); nothing here needs the user.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r6-0e77da3]]

| finding / decision | answered at |
|---|---|
| round-6 #b-1, #m-1 (21.1 side: bug-109 read at r1; D3/D6/D7; AC-4/4b; stale lines) | [[task-21.1-context-usage-telemetry#rev-round-6]] |
| round-6 #s-1 (21.1 side: the sweep step gives swept calls an origin) | [[task-21.1-context-usage-telemetry#rev-round-6]]; built in 19.0 |
| round-6 #m-2 (19.1 missing as a consumer; one-sided edge) | [[#dependencies]] (21.1 bullet names 19.1 as merging after it); 21.1 `rel: related-to -> [[task-19.1-pack-recall-under-budget]]` |
| round-6 #b-2, #s-2, #s-3 | not plan-21 items ([[plan-19-adaptive-memory-budget#rev-round-6]]) |

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan19-21-spec-rereview-r7-331b414]]. The user took the recommended one-shot
migration for #s-3 ([[plan-review-2026-10-14#t12-approvals]], round-7 item 2); no other plan-21
item needed a decision (d9ax and d9ay are plan-19's).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r7-331b414]]

| finding / decision | answered at |
|---|---|
| round-7 #s-2 (the user-level error log and its watermark have no scope) | [[task-21.1-context-usage-telemetry#rev-round-7]] (D6 scoped reader, three clauses, per-owner watermark; D7; D8 scoped writer; AC-4b (vii), (viii)) |
| round-7 #s-3 (two "for one release" legacy reads with no removal task); one-shot migration | [[task-21.1-context-usage-telemetry#rev-round-7]] (D3, D6 migration; AC-4b (ii), (vi)) |
| round-7 #s-4 (21.1 side: the miss row pinned for `event` only) | [[task-21.1-context-usage-telemetry#rev-round-7]] (R9 "Order"; AC-4 read and write legs) |
| round-7 #m-1 (21.1 side: SessionStart writer) | 21.1 test strategy (file work only; 19.0 AC-6f's `session-start` leg) |
| round-7 #m-4 (a), (b) | [[task-21.1-context-usage-telemetry#rev-round-7]] (AC-4b (iii-b); `rmx focus topics` as the surface) |
| round-7 #s-1, #m-2, #m-3, #m-4 (c), (d); d9ax, d9ay | not plan-21 items ([[plan-19-adaptive-memory-budget#rev-round-7]]) |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]]. No plan-21 item needed a user decision:
#ns-2's fix restores the round-6 intent (an automatic SessionStart surface) inside round 7's
scope rule. d9bm and d9bi are plan-19's; d9bi makes 21.1 part of the helix substrate (its events
and its pre-prompt state), named in [[plan-19-adaptive-memory-budget#root]]'s header.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]

| finding / decision | answered at |
|---|---|
| round-8 #ns-2 (per-owner SessionStart surfacing reaches only the same process) | [[task-21.1-context-usage-telemetry#rev-round-8]] (D6 two sets, `ended_sessions`, per-root watermark, `owner_alive`; D7; AC-4b (ix)) |
| round-8 #nm-1 (`ps-failed` rows unmatchable) | [[task-21.1-context-usage-telemetry#rev-round-8]] (D6 unowned rule; AC-4b (vii) sub-leg) |
| round-8 #nm-2 (unlocked machine-wide log; migration race and order) | [[task-21.1-context-usage-telemetry#rev-round-8]] (D8 one locked writer; D6 migration claim; AC-4b (x), (xi), (xii)) |
| round-8 #nm-4 (21.1 side) | [[task-21.1-context-usage-telemetry#rev-round-8]] (D9 one hook-envelope reader) |
| round-8 #nm-5 (a budget skip is invisible) | [[task-21.1-context-usage-telemetry#rev-round-8]] (R3, R4 `outcome` / `budget_s`, R7, AC-2b); [[task-21.3-indexed-symbol-nudge#rev-round-8]] (deadline as `timeout`, `retries=0`; `skipped_budget`) |
| round-8 #nm-7 (21.1 cites) | [[task-21.1-context-usage-telemetry#rev-round-8]] |
| round-8 #ns-1, #nm-3, #nm-6; d9bm, d9bi | not plan-21 items ([[plan-19-adaptive-memory-budget#rev-round-8]]) |

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]] (edit-level, no decision). Each touched task
carries its own `#rev-round-9` table.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]]

| finding | answered at |
|---|---|
| r9 #s9-2, #s9-4, #m9-1 to #m9-5; the `CALL_OUTCOMES` sibling (the existing `outcome` values) | [[task-21.1-context-usage-telemetry#rev-round-9]] |
| r9 #s9-1 (21.1 side: `PrePromptState.topic_match`) | [[task-21.1-context-usage-telemetry#rev-round-9]]; the rule itself is [[task-19.6-phased-context-and-topic-cache#rev-round-9]] |
| sibling of r9 #s9-3 (21.3 AC-5's second `sitecustomize`) | [[task-21.3-indexed-symbol-nudge#rev-round-9]] (needs 23.0's preload interface) |
| r9 #s9-3, #m9-6, #m9-7 | not plan-21 items ([[plan-19-adaptive-memory-budget#rev-round-9]]) |
