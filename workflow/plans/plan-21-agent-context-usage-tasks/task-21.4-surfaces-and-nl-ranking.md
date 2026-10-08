---
gmd: "0.1"
id: task-21.4-surfaces-and-nl-ranking
title: "Task 21.4: measure and fix natural-language context ranking, then rewrite every steering surface to one rule"
tags: [task, context, ranking, docs, agent]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 21.4: NL ranking, then the surfaces {#root}

> Plan: [plan-21-agent-context-usage](../plan-21-agent-context-usage.md)
> Status: Pending
> Depends on: 21.1, 21.2. The docs change LAST, so they never promise what the tool cannot do.

rel: part-of -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[exploration-agent-context-usage]]

## Why {#why}

**Natural-language replay.** On deployed 0.76.2, 6 NL questions gave 0 hits, 1 partial and 5
misses: memory and handoff prose crowded out code. That replay ran WITHOUT the reranker, because
the no-anchor hand-off dropped it until `2cd73b9`. The branch now reranks NL phrases on the daemon
route (r8 #s-2 moved that off the writer lock), and nobody has measured the result. The CLI's
replica branch still never reranks, so the two routes may order differently.

**Steering surfaces disagree:**
- CLAUDE.md frames context as symbol-only.
- The PRIMER promises "plain english … never empty".
- `.refmatrix/CLAUDE.md` routes "where is X used" to `neighbors`.
- The MCP description has no when-to-use.
- Plan-16 R3 points at `rmx_search`, a federated DSL, not a concept search.

{#why-body}

## Requirements {#requirements}

**This set is the ONE ranking-eval harness** (plan review C9). It is also the judge for
ADR-0004's sentence co-location rerank (after bug-075) and for plan-13's session-inclusion
   question. It lives at `eval/production/context_nl/` with a stable runner API so those callers
   reuse it rather than building their own.

1. **R1 An NL question set.** ~30 questions with known code answers, drawn from this project's
   concept-OR greps and their eventual answers. It is built and frozen BEFORE any ranking change,
   by someone other than the person tuning (pre-registration).
2. **R2 Measure both routes.** hit@1/@5 for the daemon route (reranked) and the CLI replica route
   (not reranked), against an `rg -n` baseline the agent would have written.
3. **R3 Fix what the measurement shows.** Candidates, each measured on R1 and kept only if it wins:
   - a kind-aware prior (code before memory prose for a query that names no memory);
   - a `--code` scope;
   - the replica route reranking under the same budget as the daemon route.
4. **R4 One rule on every surface, written after R3:** "identifier, or what-calls-X →
   `rmx context` (MCP `rmx_context`, `--brief`). Regex in a known file, or log triage → grep."
   - The surfaces: CLAUDE.md's ladder, `.refmatrix/PRIMER.md` header, `.refmatrix/CLAUDE.md`, the
     MCP tool description, plan-16 R3 / task 16.3.
   - The PRIMER keeps "plain english" only if R2/R3 support it.
   - Plan-16's `rmx_search` mention is corrected.

## Acceptance criteria {#acceptance}

1. R1's set is committed with its gold answers before any R3 change (the commit order is checked).
2. The R2 table (both routes × hit@1/@5 × the rg baseline) is in the implementation summary.
3. Every R3 change that ships improves hit@5 on R1 on the route it touches, and the losers are
   recorded as negatives.
4. The five surfaces state the same rule, checked by a test that greps each for the rule's anchor
   sentence. The PRIMER makes no claim the R2 table contradicts.

## Files to modify {#files-to-modify}

`eval/production/context_nl/` (set + runner + REPORT.md); `src/refmatrix/context.py` (R3);
`CLAUDE.md`, the PRIMER generator, `.refmatrix/CLAUDE.md` generator (`hooks.py` / install-hooks),
`src/refmatrix/mcp.py` / `verbs.py` descriptions; `workflow/plans/plan-16-invisible-grep-shim.md`.

## Test strategy {#test-strategy}

The ranking work is evaluated, not unit-tested. The surface consistency test is RED today, because
the surfaces disagree.
