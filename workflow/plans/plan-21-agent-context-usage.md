---
gmd: "0.1"
id: plan-21-agent-context-usage
title: "Plan 21: the agent uses rmx context because it answers — telemetry, precise identifiers, a nudge, NL ranking"
tags: [plan, context, agent, telemetry, ranking]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
---

# Plan 21: agent context usage {#root}

**Date:** 2026-10-07
**Status:** Drafting. Task specs 21.1–21.4 are written; spec review is next.
**Origin:**
- The user, 2026-10-07: "given we're making grep passive, we should look into how to expand your
  rmx context usage" ([[exploration-agent-context-usage]]).
- The tasks were first specced as plan-16's 16.7–16.10, then split out by the plan review (C8,
  approved by the user 2026-10-07), so their review loop and the grep shim's do not block each
  other.

rel: derives-from -> [[exploration-agent-context-usage]]
rel: derives-from -> [[plan-review-2026-10-07]]
rel: depends-on -> [[plan-16-invisible-grep-shim]]

## Why {#why}

In 14 days the CLI ran `rmx context` 3 times against ~1,100 agent greps, and MCP `rmx_context`
calls were not logged at all. Identifier lookups are ~55% of the agent's greps. A replay gave
4 hits, 4 partials (no line number) and 1 miss. NL queries missed 5 of 6 (unreranked on 0.76.2).
Once grep is passive (plan-16), the index reaches the agent only when asked by name. {#why-body}

## Tasks {#tasks}

| task | what | acceptance (summary) |
|---|---|---|
| 21.1 | agent-usage telemetry: MCP sets `RMX_INVOCATION_SOURCE=mcp`, caller-side `query.log` rows, `-E` cardinality, `rmx telemetry agent-usage`, and the ONE recall-event schema (C7) | an MCP `rmx_context` logs one `invocation=mcp` row; the exploration's counts reproduce |
| 21.2 | precise identifier context: `path:line` on DEFINED BY, one id form, correct labels, no helix on code anchors, `--brief` | the 9-identifier replay goes from 4 to ≥ 8 hits with a line |
| 21.3 | PostToolUse nudge for an identifier-shaped grep that names an indexed symbol with callers/tests | one line on indexed symbols, none on others; usage measured before/after |
| 21.4 | the frozen NL question set (the ONE ranking-eval harness, C9), both routes measured, ranking fixes kept only if they win, then one rule on all five surfaces | the R2 table; the surfaces agree |

Task specs: `workflow/plans/plan-21-agent-context-usage-tasks/`.

## Consolidations this plan carries (plan review) {#consolidations}

- **C7, one recall-event schema.** 21.1 defines it for every consumer, so 19.2 (usage counts) and
  19.5 (delivery measurement) count the same events once. The fields are
  `{ts, channel, invocation, query_id, memory|entity id, rank, stage}`, where
  `stage ∈ {retrieved, delivered, used}`.
  - **retrieved:** returned by retrieval.
  - **delivered:** inside the payload the agent received (19.1's pack).
  - **used:** fetched by name, or cited later.

  19.2 counts `delivered` and `used`; 19.5 compares `retrieved` with `delivered`.
- **C9, one ranking-eval harness.** 21.4's frozen NL question set is the shared harness for:
  21.4's own ranking candidates; ADR-0004's sentence co-location rerank (which needs bug-075
  fixed first); and plan-13's session-inclusion question (plan-13 is dormant until it is
  re-scoped onto this harness).

{#consolidations-body}

## Dependencies {#dependencies}

- 21.1 depends on nothing and runs in wave 1. It is the instrument 19.5 reuses.
- 21.2's replica reads rely on ch-bsd r9's partition binding (`09db9a6`).
- 21.3 depends on 16.2 (the shim removes the old stderr hint), and on 21.2.
- 21.4's replica-route rerank relies on r9's real budget (`with_budget`).

{#dependencies-body}
