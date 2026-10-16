---
gmd: "0.1"
id: exploration-agent-context-usage
title: "Exploration: making `rmx context` the agent's lookup once grep is passive (plan-16)"
tags: [exploration, context, grep, agent, telemetry, plan-16]
metadata:
  node_type: exploration
  status: in-progress
  created: 2026-10-07
---

# Exploration: expanding the agent's `rmx context` usage {#root}

**Date:** 2026-10-07
**Status:** Research Complete. Decisions are pending with the user ([[#decisions]]).
**Motivation:** The user, 2026-10-07: "given we're making grep passive, we should look into how to
expand your rmx context usage". Plan-16 makes every grep exec the real tool and only LEARN in the
background, which gives up the index's 18.5–31.7% answer share. After that, the graph reaches the
agent only when the agent asks for it by name.

rel: depends-on -> [[plan-16-invisible-grep-shim]]
rel: related-to -> [[task-16.3-grep-tool-hook-and-docs]]
rel: related-to -> [[feedback_rmx_first_retrieval]]
rel: related-to -> [[feedback_grep_is_observed_not_answered]]

## Background: how the agent searches today (14 days, 2026-09-23 to 10-07) {#background}

| surface | calls | p50 / p95 ms | note |
|---|---|---|---|
| agent greps (grep-replica rows) | 1,107 | 9 / 26 | 825 drop-in, 21 index-answered |
| `rmx context` from the CLI | **3** | 825 / 859 | 418–596 tokens per answer |
| MCP `rmx_context` | **0** in transcripts | — | not logged at all (below) |
| `rmx memory recall` (agent) | 34 (corrected 2026-10-14; 68 counted the intent rows twice) | 41 / 872 | |
| scan-prompt hook | 200 | 2,448 / 9,774 | ~1.6k tokens per prompt |

In transcripts, Bash commands contained `grep` 983 times and `rmx context` at most 29 times
(an upper bound: it counts mentions). This session matches: the agent used `rmx grep` and file reads
throughout and called context almost never. **The habit is part of the problem, not only the
tooling.** {#usage}

**What the agent greps for** (~70 recent patterns):
- exact identifier: ~55%;
- a regex in a known file: ~20%;
- log/shape triage: ~13% (`^(FAILED|E  )…`);
- concept-ish ORs: ~12% (`helix|concept|cull|merge`).

{#classes}

## Findings {#findings}

**Replay**, 15 recent patterns through `rmx context` on the DEPLOYED 0.76.2:
- **Identifiers: 4 hits, 4 partial, 1 miss.**
  - A partial means DEFINED BY named the file with **no line number**.
  - The miss was `_drop_lance_for_purge`: only a test was shown.
  - Each call took 330–1,130 ms, against 5–10 ms for grep.
- **Natural-language queries: 0 hits, 1 partial, 5 misses.** Memory and handoff prose crowded out
  the code. Examples: "fold duplicate concepts" did not surface `fold_concept_dups`, and "where does
  query.log get written" missed `telemetry.py:48`.
- **Caveat:** deployed 0.76.2 still has the defect the r7 remedy found and fixed on the branch
  (`2cd73b9`). A phrase with no graph anchor skipped the reranker, so these NL results are
  UNRERANKED. The replay must be re-run on the branch before the NL verdict stands.
  Correction (plan-21 spec review s-8, 2026-10-14): the replay ran on the REPLICA route, which has
  never had a reranker; `2cd73b9` fixed only the daemon route. Re-running on the branch stays
  unreranked until the replica route gets one (21.4 R3).

{#replay}

**Output friction:**
- No `path:line` on DEFINED BY.
- Each test appears twice, under two id forms.
- Edge direction looks inverted (tests listed under CALLS).
- `[helix]` "last worked … then:" headers on code lookups are noise to an agent.
- The JSON form is 2.4x the text form.

{#friction}

**The steering surfaces disagree:**
- **CLAUDE.md** frames context as symbol-only, in a ladder, with no trigger for questions.
- **PRIMER** promises "plain english … never empty", which the replay contradicts.
- **`.refmatrix/CLAUDE.md`** routes "where is X used" to `neighbors` and "docs and code" to `query`.
- **MCP `rmx_context`** gives no when-to-use.
- **Plan-16** points agents at MCP `rmx_search`, a federated DSL across projects, not a concept
  search.
- **The grep-rewrite hook** emits nothing to the agent. Plan-16 removes the stderr provenance hints,
  the only cue that the index knew something.

{#surfaces}

**Telemetry cannot measure the change we want:**
- `invocation` is `unknown` on every agent grep and context row.
- The MCP server never sets `RMX_INVOCATION_SOURCE`.
- MCP `_op_context` writes no `query.log` row.
- ~~`cardinality` reads 0 on `-E` alternation greps that matched.~~ Did not reproduce (plan-21 spec
  review s-4, 2026-10-14): none of the zero-cardinality `-E` rows ended `ok`. The real gap is
  `grep-stdin`, whose cardinality is null on every row (`cli.py:6202`).

{#telemetry}

## Option A: make context worth calling for identifiers {#option-a}

Precision first:
- `path:line` on DEFINED BY;
- one id form per entity;
- correct edge direction;
- no `[helix]` block on code anchors unless asked;
- a compact `--brief` (definition + callers + tests, ≤ 200 tokens).

Identifiers are 55% of what the agent searches for. If context matches grep's precision and adds
callers and tests, it is the better tool for that class, despite costing ~100x the latency (still
under 1.2 s). **Measure:** re-run the identifier replay; the target is hit-with-line on ≥ 8 of 9.
{#option-a-body}

## Option B: fix natural-language ranking {#option-b}

- Code before memory prose for a query that names no memory: either a `--code` scope or a
  kind-aware prior.
- Re-measure with the branch's reranker hand-off fix in place.
- Do NOT promise "plain english" in the PRIMER until it passes.

**Measure:** a fixed set of ~30 NL questions with known code answers. These can come from this
session's own greps (the concept-OR class) and their eventual answers. Report hit@5 against an
`rg -n` baseline the agent would write. {#option-b-body}

## Option C: a passive nudge where grep used to answer {#option-c}

A PostToolUse(Bash) hook. When an identifier-shaped grep pattern names an indexed symbol, it adds ONE
line to the agent's context, such as
`rmx: <symbol> is indexed: 3 callers, 2 tests (rmx context <symbol>)`. This replaces the stderr hint
plan-16 removes. It is cheap (one index lookup), and the agent sees it in the same turn. **Risk:**
noise. Gate it on the symbol having callers or tests, and rate-limit it per session. {#option-c-body}

## Option D: one rule on every surface, and telemetry that can count it {#option-d}

- **Rule:** "Identifier or 'what calls X' → `rmx context` (MCP `rmx_context` from the agent). Regex
  in a known file, or log triage → grep."
- **Surfaces:** CLAUDE.md, PRIMER, `.refmatrix/CLAUDE.md`, the MCP description, plan-16 R3 /
  task 16.3. Correct the plan-16 `rmx_search` mention.
- **Telemetry:** the MCP server sets `RMX_INVOCATION_SOURCE=mcp`; `_op_context` writes a
  `query.log` row; `cardinality` is fixed for `-E`.

**Measure:** context and grep calls per session, before and after. {#option-d-body}

## Recommendation {#recommendation}

**D's telemetry first**: it is small, and nothing else can be judged without it. Then **A**,
then **C**. **B** is gated on re-running the NL replay against the branch, because the replay ran
without rerank. The surfaces (D's rule) change only after A lands, so the docs never promise what
the tool cannot do. The agent-side habit is addressed by A + C. A tool that answers precisely, plus
a nudge in the turn it would have helped, works better than a rule the agent has to remember.
{#rec-body}

## Decisions for the user {#decisions}

- **d-1. Scope:** fold this into plan-16, as new tasks after 16.3, or its own plan? (Plan-16 is in
  spec review r5.)
- **d-2. Nudge (Option C):** acceptable as a PostToolUse hook that adds one line to the agent's
  context?
- **d-3. Latency budget for `--brief`:** is ≤ 1 s acceptable, or must identifier lookups approach
  grep (≤ 100 ms, which means an index-only path that skips the bundle builder)?
- **d-4. Habit:** should a feedback memory record now that identifier lookups go to `rmx_context`
  (MCP) first?

## Transition Summary {#transition-summary}

**Status:** IN PROGRESS. User decision, 2026-10-07: **new tasks with the nudge** (first in plan-16; moved to plan-21 by the 2026-10-07 plan review, C8).

- **21.1** telemetry: MCP invocation source, a `query.log` row for `_op_context`, `-E`
  cardinality.
- **21.2** precise identifier answers: `path:line` on DEFINED BY, one id form, edge direction,
  `--brief`, no helix block on code anchors.
- **21.3** the PostToolUse nudge.
- **21.4** surfaces + NL ranking: after the branch NL replay; docs change last.
- **Order:** after plan-19.
