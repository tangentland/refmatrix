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

## Rendering: an expand/collapse tree, active cluster open {#tree-render}

The user, 2026-10-14: "should the stm context be like a expanded/collapsed filesystem display
where the current cluster is expanded and the others collapsed into one line summaries?"

Yes. Today's composite renders its top-3 topic clusters at roughly equal depth (members plus
`rel:` lines each), which spends the budget evenly across threads the prompt is not about. The
tree form spends it where the phase says:

```
▾ topic: plan-23 drain / bind  (active · 42 events · L380–L472)
    members: plan-23-bounded-write-harness, task-23.1, bind(batch), bug-105, …
    rel: …  (the current depth rules: lift-ranked co-occurs, sparse-first LTM)
▸ topic: Time Machine exclusions  (18 events · L455–L470 · id c7f2)
▸ topic: decision walk d1a–d9j    (96 events · L120–L410 · id 3a91)
```

- **Expanded:** exactly the cluster the phase selects (warm: the overlapping cluster; return: the
  restored one; cold: none expanded, every line collapsed, which is the breadth view).
- **Collapsed:** one line each (label, event count, line range, stable cluster id), a few tokens
  apiece. The line is the HANDLE the topic cache re-expands on a return (#topic-cache), and it is
  byte-stable across turns, so versioned injection sends it as "unchanged" (#versioned-injection).
- **Labels need 19.0 first:** a collapsed line is only its label, so a junk label (`re.searc`)
  makes the whole line useless; this is the strongest case yet for the STM hygiene prerequisite.

A correction to the premise: the measured near-zero overlap (median carried 0.000) is plan-10's,
between CONSECUTIVE scan-prompt content hits ([[injection-overlap]]), not between STM clusters.
Cross-cluster overlap of STM members has not been measured; 19.6 measures it (how often a
prompt's terms hit 0, 1 or ≥ 2 clusters) before choosing single-expand vs. expand-top-2.
{#tree-render-body}

## Versioned injection: supersede by convention, never re-send unchanged {#versioned-injection}

The user, 2026-10-14: "is there a way to flag incoming context to be a replacements for entries in
the session kv cache?" No. A hook can only APPEND (UserPromptSubmit / SessionStart stdout,
`additionalContext`); the prompt cache is keyed on the exact prefix and the transcript is
append-only, so nothing a hook emits can retract or replace an earlier block. Only compaction,
`/clear`, and the harness's own context management remove context. A stale block already in the
prefix is cheap to re-read (cached); what it costs is window space and attention. So the levers
are: tell the model which copy is current, and stop paying for copies that did not change.
{#vi-premise}

Design (owned by 19.6, d5b):
1. **Every injected block is versioned.** A stable `id` plus `rev` in its header, and one line:
   "supersedes earlier revs of `<id>`". The STM composite already carries `id: stm-topic-composite`
   and `turn: N`; recall packs, the topic-cache restore and the scan-prompt bundle get the same.
   The model treats the newest rev as authoritative, as `rel: supersedes` already works in GMD.
   {#vi-versioned}
2. **Unchanged means one line.** When a block's content hash equals the last emitted rev for this
   session, emit `<id> rev N unchanged` instead of the body. A topic-cache RETURN emits
   `re-activate <cluster-id> (rev N)` when that rev is still in the window, and the body only when
   it may have been compacted away. {#vi-unchanged}
3. **Compaction keeps only the newest rev.** Whether a PreCompact hook can steer the compaction
   summary is UNVERIFIED; check it before relying on it. Without it, the newest rev after a
   compaction is re-sent in full once (the session's last-emitted state resets at compaction).
   {#vi-compaction}

4. **Text patches, keyframe + delta.** The user, 2026-10-14: "can we pass patches to kv entries?"
   Not to the KV cache itself: each cached key/value depends on every token before it, so changing
   one position means recomputing everything after it, and no API exposes the cache. What CAN be
   sent is a textual patch against a named rev: `<id> rev 22 = rev 21 + {add: …, drop: …}`. The
   model applies it by reading. Rules, video-codec style: a delta is only against a rev known to
   be in the window; a full KEYFRAME every K revs and after any compaction; a delta larger than
   ~half the block is sent as a keyframe instead. The measurement in #vi-evidence adds the delta
   size distribution, and the read-back check ("did the agent use the patched state correctly")
   decides whether deltas are trusted or only "unchanged" lines are used. {#vi-delta}

Where the evidence stands: plan-10's 10.1 measured consecutive scan-prompt CONTENT HITS and found
median carried 0.000 against a pre-registered 0.40 ([[injection-overlap]]), so dedup of
scan-prompt's ranked entries does not pay. That measurement did not cover the STABLE blocks —
the STM composite, recall packs, topic restores — which are near-identical across turns by design.
19.6 measures those first, with the go/no-go-ranges rule
([[feedback_go_no_go_ranges_not_predrop]]): the share of emitted bytes that are byte-identical to
the previous rev of the same id, over a frozen set of real sessions. The event schema (d4a) gets
`block_id`, `rev`, `unchanged: bool` so the saving is a count, not a story. {#vi-evidence}

rel: related-to -> [[plan-10-injection-dedup]]

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
