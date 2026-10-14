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

## Topic cache: returning from a sidetrack is not cold {#topic-cache}

The user, 2026-10-14: "we should cache the stm topic clusters and switch between them when
sidetracking returns to the topic."

The phase table above treats every low-overlap prompt as **shift** (go broad). That is right for a
NEW topic and wrong for a RETURN: when the session comes back to a topic it already built up, the
deep context it had is still the right context, and rebuilding it from a broad scan wastes the
budget and the turns it took to earn. So **shift** splits in two:

| case | detected by | action |
|---|---|---|
| **return** | prompt terms overlap a CACHED, inactive topic cluster | restore that cluster as the active focus; spend the budget deep, as if warm |
| **new** | overlap with no cached cluster | broad, scoped to the new terms (the old **shift**) |

What already exists (read 2026-10-14, `src/refmatrix/stm.py`):
- `topic_composites` (`stm.py:790`) and `cluster_focus` (`stm.py:752`) compute the clusters each
  turn; nothing keeps them once focus moves on.
- The soft-detour pair (`stm.py:682-742`, `/detour` + `/return`) already snapshots focus and
  re-warms it. It is MANUAL: the agent or user must bookmark before the sidetrack. The topic cache
  is the automatic version of it: every cluster that loses focus is snapshotted, keyed by its
  member set, and a later prompt that matches it re-warms it.

Open design points, for the plan-19 task that owns this:
- **Cache key and match:** member-set overlap (Jaccard) between the prompt's terms (or the new
  turn's cluster) and each cached cluster; a threshold, logged raw like the phase inputs.
- **Bound:** a per-session LRU of N clusters, so the cache cannot grow without limit.
- **Session scope:** keyed by the envelope `session_id`, never `latest_session` (bug-100), or a
  return can restore another session's topic.
- **Measurement:** the event schema records `arm` = fixed / phased / phased+cache, and on a return
  the restored cluster id, so "the cache helped" is a read-back count and not a story.
{#topic-cache-body}

## What must come first {#prereqs}

- **Clean STM clusters (user, 2026-10-14: "lets add fixes to the STM before the phased context
  work").** Phase detection and the topic cache both key on STM clusters, and on this session they
  were led by typos ("aggre"), truncated identifiers from the agent's own heredoc scripts
  (`re.searc`, `s.repla`), a background subagent's tool calls, and hand-back boilerplate. Task
  19.0 fixes that first ([[plan-review-2026-10-14#t5-stm-hygiene]]). {#prereq-stm-hygiene}

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
