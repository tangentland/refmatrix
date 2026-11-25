---
gmd: "0.1"
id: PLAN_GOVERNANCE
title: "Plan Governance"
tags: [governance]
metadata:
  node_type: governance
---

# Plan Governance {#root}

Lifecycle, staleness, and question-forcing rules for plans. Companion to
`workflow/PLANNING_WORKFLOW.md` (the how-to) — this file is the policy.

## Lifecycle Gates {#lifecycle-gates}

All plans live permanently in `workflow/plans/`. A plan never moves between directories — its
stage is recorded ONLY by the `metadata.status` field in its GMD frontmatter:

1. **`drafting`** — design in flux, no task specs yet.
2. **`approved`** — the plan is approved and its next task has an approved one-page spec. No
   production code for a task before that task's spec is approved. The five queue items after the
   one in flight always hold such a spec (L232). The definition is [[plan-of-plans#status-lifecycle]].
3. **`in-progress`** — implementation underway.
4. **`completed`** — all tasks shipped and verified (the file stays in `plans/`).

rel: depends-on -> [[plan-of-plans#status-lifecycle]]

## Staleness {#staleness}

| Age since last update | Action |
|-----------------------|--------|
| 0–14 d | Normal |
| 15–30 d | Verify active work |
| 31–60 d | Re-justify or reclassify |
| 60+ d | Critical — likely abandoned; escalate |

## Question-Forcing {#question-forcing}

A plan that reaches approval with vague deliverables, missing API signatures, or unclear
integration points is **blocked** — present it to the user before implementation. Ambiguity
is a stop condition, not a thing to resolve mid-code.

## Source-of-Truth Order {#source-of-truth-order}

1. `workflow/plan-of-plans.md` — index + sequenced execution order (Status column); what's next
2. `workflow/plans/` — all plans, permanently; each plan's `metadata.status` records its stage
   (`drafting` → `approved` → `in-progress` → `completed`)
3. `workflow/plans/<plan>-tasks/` — task specs for a plan (present once `status: approved`)
