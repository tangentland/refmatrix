---
gmd: "0.1"
id: agent-brief-spec-u1
title: "Brief: spec U1, use observations recorded only (Q83 = a, L250)"
tags: [agent-brief, planning, u1, used-signal, telemetry]
metadata:
  node_type: brief
  created: 2026-11-25
---

# Spec U1: use observations, recorded only {#root}

rel: implements -> [[plan-of-plans#questions]]
rel: depends-on -> [[orchestration#planning]]
rel: depends-on -> [[measurement-task-21.5-usage-weight-2026-11-13]]

**Why.** The weights carry ingest structure only; nothing learns from whether injected context
was used. The 2026-11-13 usage-weight measurement found the binding constraint is evidence (93
trustworthy used units), and the 21.5 R12 pilot found a touch-counter measures proximity, not use
(~90% of credits were touches the agent would have made anyway). 21.5 phase B and any derived
weights stay frozen behind plan-28 (D-Q4). The user (Q83 = a, L250): start accumulating the
record now, with a control arm, read by nothing in retrieval. {#why}

## The record {#record}

One append-only event per item delivered (or held out) by an injection surface: scan-prompt,
prompt recall, and the I1 injected units. The association it captures is

```
(cue → item → outcome), with the counterfactual arm
cue     = the concepts in the prompt / tool context that triggered the retrieval
item    = the entity (stable id + kind + path)
channel = the surface and hook event
arm     = delivered | held-out (retrieved and ranked into the budget, then withheld)
outcome = caused | informed | ignored | already-held, classified at REPORT time from the
          session's later events, with an evidence ref; never by the hook
```

The derived associations it must make possible later (not built here): cue → item
(`useful_for`, delivered and used counts, lift over the held-out arm), item ↔ item co-use, item
→ focus topic. {#record-body}

## Scope {#scope}

- The writer, the held-out arm, the outcome classifier as a read-only report, and the
  retention/size bound. Reuse before inventing: the I1.b2 instruction ledger
  (`task-I1.b2-marker-and-ledger.md`), `recall-events.jsonl`, `query.log`, the STM ring, and
  21.5's join (`task-21.5-tool-used-signal.md` `#r12`, its pilot's corrections). Say which one the
  record extends or sits beside, and why.
- **The held-out rate is a user gate:** propose a default with its cost (items withheld from live
  sessions) and the evidence rate it buys (events per week at the measured delivery volume), as an
  open decision with a recommendation.
- Hook-path rules: no silent failure (`CLAUDE.md` `#no-silent-failures`), bounded time inside the
  hook budget (`hook_budget.py`), no raw prompts stored (hash or concept ids only; the repo is
  public: `feedback_no_raw_prompts_in_public_repo`).
- Non-goals: no ranking change, no weight written, no consumer in retrieval, no BSI.

{#scope-list}

## Shape and rules {#rules}

One page scaled (`workflow/ORCHESTRATION.md` `#one-page-scaled`): goal, acceptance criteria each
with the test through the entry point users call, the files, the risks (the self-audit for this
change), the `src/` mutation table, open decisions with recommendations (no Q ids). File:
`workflow/plans/task-U1-use-observations.md`, `status: approved-pending`.
Work in `/Volumes/littlebig/refmatrix-spec-window` on a branch `spec-u1` from the dev tree's
`master`. Planning only: no `src/`, no tests, never touch the dev tree, never push. Read-only
against every live store; look things up with `scripts/rmx-master` or the read-only MCP tools;
a measurement of delivery volume runs on a read-only copy. `./scripts/lint-gmd.sh` zero errors.
Report the sha, the page size, the criteria and mutation counts and the open decisions. {#rules-body}
