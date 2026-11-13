---
gmd: "0.1"
id: task-21.7-behavioural-use
title: "Task 21.7: behavioural use without naming — did a delivered item shape what the agent did, judged from the transcript against a control"
tags: [task, plan-21, telemetry, used, judge, memory, feedback]
metadata:
  node_type: task
  status: drafting
  plan: plan-21-agent-context-usage
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 21.7: behavioural use without naming {#root}

> Plan: [[plan-21-agent-context-usage]]
> Status: Drafting. The user asked for the task row on 2026-11-13 (Q6 in [[open-questions]]); the
> spec is not written yet.
> Depends on: 21.5 (the delivered-event join, the control, the labelling rubric), 19.6 (its
> transcript scorer is the sibling instrument).

rel: part-of -> [[plan-21-agent-context-usage]]
rel: depends-on -> [[task-21.5-tool-used-signal]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache]]
rel: derives-from -> [[measurement-task-21.5-r12-pilot-2026-11-13]]

## Why {#why}

21.5's mechanical legs credit a delivery only when a later tool call touches or names the item.
The 2026-11-13 measurements showed they cannot see the use that matters most for memories: a
feedback memory's rule followed, a mistake it warned about avoided, a recorded decision reused —
use that names nothing. Term and clique overlap do not recover it either (topical, no excess over
the control after stratification).

## Scope to specify {#scope}

- A sampled LLM judge reads the transcript window after a delivery, with the arm (delivered or
  control) and every injected block removed, and answers whether the agent's actions or reply are
  consistent with the item's content in a way the rest of the context does not explain.
- The same-session never-delivered control is judged identically; the result is delivered minus
  control, never a raw rate.
- A second rater on a share of the sample; pre-registered bands before any run.
- Item kinds first: feedback and guardrail memories, then decisions.
- Raw transcripts stay local; committed results are counts and labels.
