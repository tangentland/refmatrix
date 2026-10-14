---
gmd: "0.1"
id: plan-21-agent-context-usage
title: "Plan 21: the agent uses rmx context because it answers — telemetry, precise identifiers, a nudge, NL ranking"
tags: [plan, context, agent, telemetry, ranking]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
  updated: 2026-10-14
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

- **C7, one recall-event schema.** 21.1 R6–R9 define it for every consumer, in a NEW append-only
  `recall-events.jsonl` written lock-free like `query.log` (d4a). The field set closes bsd #b-1
  (`session`, `turn`, `query_id`), #b-2 (`name` + `entity_id` + `kind`; `channel` is a closed
  SURFACE enum, separate from `invocation`), #s-1 (`delivered` = emitted, with `offset_bytes` /
  `bytes` / `payload_bytes`, so `seen` is derived against any cap), #s-2 (phase fields: `arm`,
  `policy`, the raw phase inputs, `restored_cluster_id`), d8e (`scope`), and the versioned-injection
  fields `block_id`, `rev`, `unchanged` ([[exploration-session-phased-context#vi-evidence]]).
  - **Consumers:** 19.2's counters fold the file into DuckDB through plan-23's drain with the
    offset committed in the same transaction (d2a), using 23.1's non-consuming tail reader and
    tick registry (d4a amendment; plan-21 is a listed consumer). 19.5 compares `delivered` with
    derived `seen`. 19.6 reads the phase fields (d5b). 21.3 AC-4 and 21.1's report read `session`.
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

- **d4a** — the sink: 21.1 R6.
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
- **d8e** — `scope` on every event; a global hit is counted in the global store: 21.1 R7, R8.

## Dependencies {#dependencies}

- **21.1** needs only **23.0** (the shared test sandbox, d1a/d1b), per
  [[plan-review-2026-10-14#t8-wave1]]. It runs in Wave 1. It is the instrument 19.2, 19.5 and 19.6
  consume; it does not wait on plan-23's queue (d4a).
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

Gaps this revision found that the decision log does not settle. Listed, not decided.

1. **Legacy rows without `cwd`.** d8d's predicate keys on a row's cwd or root. `query.log` rows at
   HEAD carry neither (`telemetry.log_query.__exit__`), so the 235 legacy fixture rows in
   `~/.refmatrix/query.log` cannot be matched by it. 21.1 R5 adds `cwd`/`root` to new rows and
   counts unattributable legacy rows separately; whether legacy rows are then excluded by shape
   (e.g. the `alpha|beta` body) or left counted is open.
2. **Who emits transcript-derived `used` evidence.** 21.1 emits `used` for the evidences it can see
   at call time (`context_by_name`, `memory_get_by_name`, `focus_note`). `file_read` and
   `cited_in_answer` need a transcript scorer; d5b gives 19.6 the phasing and says "plan-21 only
   measures", but no row names the scorer's owner.
3. **Exploration corrections.** bsd #s-4 and #s-8 ask that
   [[exploration-agent-context-usage#telemetry]] (the `-E` bullet) and `#replay` (the reranker
   caveat) be corrected, and #s-3 that its "68 recalls" read 34. That file is outside this
   revision's edit set.
4. **plan-13's pointer.** d4b marks plan-13's sessions question dormant "by pointer"; this plan
   carries the pointer ([[#consolidations]]), but plan-13's own header and its plan-of-plans row
   still say "re-scoped onto 21.4".
5. **19.2 R3's channel enum.** bsd #b-2 asks that 19.2 R3 adopt 21.1's surface enum
   (`invocation` separate). That edit belongs to the plan-19 revision.
6. **The 21.4 source log.** d8f settles what is committed; this revision names the project's
   `.refmatrix/query.log` as the draw source (the global log holds other trees' queries, bsd
   decision-log #s-8). The user has not confirmed project-only.
7. **MCP tools beyond context and recall.** 21.1 R4 narrows the report to context, grep and recall
   (bsd #s-5's first option). Logging every MCP verb at `mcp._verb_tool` is not planned.

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
