---
gmd: "0.1"
id: agent-brief-m5-popularity-prior
title: "Brief: M5, a recency-windowed popularity prior measured against scan-prompt (Q89 = a, L254)"
tags: [agent-brief, measurement, m-lane, retrieval, popularity]
metadata:
  node_type: brief
  created: 2026-11-25
---

# M5: the popularity prior, pre-registered {#root}

rel: implements -> [[plan-of-plans#questions]]
rel: derives-from -> [[exploration-meta-associations]]

**Why.** In M4 one fixed list, the files most often newly touched, beat every recall candidate on
held-out queries, and popularity × mode tied popularity alone (candidate 8). It was a baseline,
not a pre-registered candidate. The user chose to measure it properly (Q89 = a). {#why}

## Questions {#questions}

1. Does a **recency-windowed, per-project popularity prior** (the files newly touched most often
   in the last W days before the query, W pre-registered as a small set, e.g. 3 / 7 / 14) reach
   held-out golds that today's scan-prompt missed, and by how much over a placebo?
2. **Blend, not replace:** does adding the prior's top-k beside scan-prompt's payload (a fixed
   share of the budget, e.g. 2 of 8 items) raise reach@k over scan-prompt alone, and what does it
   cost in payload bytes and in false reach?
3. **Stability:** is the prior's top-k stable enough day to day that it would mostly re-deliver
   what the session already holds (the 2026-11-13 already-held finding: 48%)? Report its overlap
   with the previous day's list and with what the session had already touched.
4. **Who it serves:** split by M4's three activity modes and by item kind; a prior that only
   helps one mode says so.

{#questions-list}

## Method and rules {#rules}

Same as M4 ([[agent-brief-meta-assoc-measure#rules]]): copies only, read-only, nothing raw in the
repo, a time-ordered held-out split (reuse M4's split and joins: `m4_common.py`), bands with an
action each written and committed before any result, a touch is proximity (r12), name a mechanism
only after measuring it. Work in `/Volumes/littlebig/refmatrix-m4` on a new branch
`m5-popularity-prior` from the dev tree's `master`; add a section to
`docs/architecture/explorations/meta-associations.md` (`#m5`) and scripts under
`workflow/measurements/meta-associations-2026-11-25/`. Report the pre-registration sha, the final
sha, one line per question (metric, result with interval, band, action), and what could not be
measured. {#rules-body}
