---
gmd: "0.1"
id: agent-brief-m6-retrieval-pressure
title: "Brief: M6, per-session retrieval pressure measured before it shapes 10.2's held line (Q91 = a, L257)"
tags: [agent-brief, measurement, m-lane, retrieval, stm, dedupe]
metadata:
  node_type: brief
  created: 2026-11-25
---

# M6: retrieval pressure {#root}

rel: implements -> [[plan-of-plans#questions]]
rel: derives-from -> [[exploration-meta-associations#m5]]
rel: related-to -> [[task-10.2-plan-10-injection-dedup]]

**Why.** 10.2's names-only dedupe names a held item on one `·held` line but keeps rank and `k`;
nothing accumulates when the same item is retrieved turn after turn, and the STM focus graph is
fed only by what the agent does, never by what retrieval returns. The user asked whether a
deduped item should carry a running session score (Q91 = a: measure it first). {#why}

## The signal {#signal}

Per session and item key: `pressure(t) = Σ over retrievals r before t of decay^(turns since r)`,
with STM's `RMX_STM_DECAY` (0.85) as the default and a small pre-registered set (e.g. 0.7 / 0.85 /
0.95). A retrieval is any row in `recall-events.jsonl` for the item (delivered, and later held or
held-out), on the hook channels. Variants to pre-register: count only, rank-weighted
(`1/rank`), and channel-split. {#signal-body}

## Questions {#questions}

1. **Prediction:** on M4's held-out split, does pressure at turn t predict the agent's next
   first touch of the item (within the next N events) beyond (i) STM's own node score for that
   ref at t, (ii) M5's popularity list, (iii) the item's rank in the current call alone? Report
   AUC deltas with intervals, with each baseline and pressure added to it.
2. **Held-line ordering:** among items that would be held (already delivered earlier in the same
   context), does ordering by pressure put the item touched next earlier than 10.2's default
   order? Report the mean reciprocal position.
3. **Tier upgrade:** for items first delivered as a pointer or excerpt, does crossing a pressure
   band predict a later Read of the item? Pre-register two or three bands; report the precision
   and how many upgrades a session would make (the byte cost).
4. **Self-reinforcement check:** does pressure merely restate the session's topic? Report its
   correlation with STM node score and with the prompt-term overlap; a signal that is ≥ 0.9
   correlated with STM adds nothing.

{#questions-list}

## Method and rules {#rules}

Same as M4 and M5 ([[agent-brief-meta-assoc-measure#rules]]): copies only, read-only, nothing raw
in the repo, M4's time-ordered split and joins (`m4_common.py`), bands with an action each
committed before any result, a touch is proximity (r12), name a mechanism only after measuring it.
STM node scores at t are recomputed from copies of the rings with `stm.py`'s own scorer (import it,
do not re-implement it). Work in `/Volumes/littlebig/refmatrix-m4` on a new branch
`m6-retrieval-pressure` from the dev tree's `master`; add a section `#m6` to
`docs/architecture/explorations/meta-associations.md` and scripts beside M5's. Report the
pre-registration sha, the final sha, one line per question (metric, result with interval, band,
action), and what could not be measured. {#rules-body}
