---
gmd: "0.1"
id: exploration-session-phased-context
title: "Exploration: phase what scan-prompt and per-prompt recall return by the session's STM state"
tags: [exploration, context, scan-prompt, memory, stm, budget, plan-19, plan-21]
metadata:
  node_type: exploration
  status: in-progress
  created: 2026-10-14
---

# Exploration: session-phased context injection {#root}

**Date:** 2026-10-14
**Status:** Idea recorded; not measured. It is folded into the plan-19 and plan-21 spec reviews
(Wave 0) instead of becoming its own plan.
**Motivation:** The user, 2026-10-14: "Does it make sense to do a progression of what is returned
by scan-prompt/context based on the depth of the session. At the beginning it seems like broader
context would be better, while later deeper context makes more sense?"

rel: related-to -> [[exploration-adaptive-memory-budget]]
rel: related-to -> [[exploration-agent-context-usage]]
rel: depends-on -> [[plan-21-agent-context-usage]]
rel: amends -> [[plan-19-adaptive-memory-budget]]
rel: related-to -> [[reference_hook_output_10k_cap]]
rel: related-to -> [[project_helix_log_confounded]]
rel: related-to -> [[feedback_causal_story_before_evidence]]

## Answer in one line {#answer}

Yes, but phase on **what the session already knows** (STM state), not on turn count. Depth is a
proxy that breaks the moment a long session switches topic: turn 40 on a new subject is cold
again.

## What one session showed (2026-10-14, session db80475a) {#observed}

Anecdotal, one session, read off the injected hook output. It motivates the idea; it proves
nothing.

- **Turn 1, "whats next?"** scan-prompt matched the literal word `next`: a template's empty
  `handoff-session#next-steps`, `project_coref_crossdoc_banked#next`, ch-bsd impressions. The one
  useful row was `handoff#next`. A cold start wants a MAP (handoff Next, plan-of-plans sequence,
  open bugs, last bsd verdict), and term-matching a two-word prompt cannot produce one. {#obs-cold}
- **Turn 3, "check r13 first…"** the STM composite already carried real topics (r13, handoff.md).
  That is where narrow, anchor-level context pays: the r13 report anchors, the remedy summary. {#obs-warm}
- **Every turn:** per-prompt memory recall (`hooks.py:313`) led with compiled `subject_*` clusters
  (`subject_timeline`, `subject_kickstart`, `subject_channel`), noise at any depth. That is a
  ranking defect independent of phasing, and plan-19's subject grouping should own it. {#obs-subjects}

## Proposed shape {#shape}

The hook budget is fixed (~10k chars delivered whole, [[reference_hook_output_10k_cap]]); phasing
changes how it is SPENT, not its size.

| phase | detected by | spend the budget on |
|---|---|---|
| **cold** | no STM focus yet, or prompt carries no concrete terms | breadth: handoff Next, active plans, open bugs + bsd findings, subject headers. Pointers over snippets. |
| **warm** | focus topics exist and the prompt overlaps them | depth: graph neighbors of touched files/symbols, `--expand` lines, report anchors. Snippets over pointers. |
| **shift** | prompt terms barely overlap the current topics | breadth again, scoped to the new terms. |

Signals already exist: the STM ring, `stm.topic_composites` (`stm.py:790`), files touched, and the
term overlap between the prompt and the composite's members. No new store state is needed. {#signals}

## What must come first {#prereqs}

- **An instrument.** Nothing records whether injected context is USED. Plan-21.1's recall-event
  schema is that instrument; plan-19 needs the same for memory. Without it, "phased beats fixed"
  is a story, not a measurement ([[feedback_causal_story_before_evidence]]). {#prereq-instrument}
- **Not helix.** The helix readership signal is confounded on the hook path
  ([[project_helix_log_confounded]]); it cannot score this. {#prereq-not-helix}
- **Pre-registered comparison.** Fixed vs phased allocation on the same sessions, scored by
  read-back (did a later tool call or answer cite an injected row), threshold written before the
  run. {#prereq-compare}

## Where it goes {#placement}

- **plan-19:** a task "budget allocation by STM phase" after 19.1/19.2, depending on 21.1. The
  subject-cluster noise ([[#obs-subjects]]) is raised in the same review.
- **plan-21:** 21.1's event schema must record the phase at injection time, so the comparison is
  possible without a second instrument.

## Decisions pending {#decisions}

1. Accept the placement above (task in plan-19, schema field in plan-21), or a separate plan.
2. Whether turn count is kept as a tiebreaker signal at all.
