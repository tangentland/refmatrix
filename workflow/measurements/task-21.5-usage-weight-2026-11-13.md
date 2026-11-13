---
gmd: "0.1"
id: measurement-task-21.5-usage-weight-2026-11-13
title: "Usage-amplified term weight (2026-11-13): RSJ s_t is inert at the pre-registered lambdas and unfittable on current evidence; do not build yet"
tags: [measurement, plan-21, task-21.5, term-weight, rsj, reinforcement]
metadata:
  node_type: measurement
  status: provisional
  created: 2026-11-13
---

# Usage-amplified term weight, 2026-11-13 {#root}

Phase 3 of `tc-215` (brief `#amendment-2`), at the user's question: "collect an inverse score of
the inverted widely linked terms — when they are used collect an amplified secondary score that can
be used as an alternate weight mechanism". Persisted by the lead from the agent's text. Counts
only. Pre-registration written 12:03, before any phase-3 result (session scratchpad
`tc/PREREG_phase3.txt`). **Provisional** until ch-bsd.

rel: related-to -> [[measurement-task-21.5-term-clique-2026-11-13]]

## Setup (pre-registered) {#setup}

- Time-ordered split at the 60th percentile of delivered-unit times: refmatrix train 5,052 /
  held-out 3,405 delivered (control 2,128 / 1,328); cliquedb 3,519 / 2,355 (control 2,951 / 1,598).
- "Used" evidence: CAUSED/INFORMED labels (all 325 labelled pairs mapped to units), R12 explicit
  used events, and main-loop file credits not prior-touched; a CONSISTENT/UNRELATED label overrides
  a main-loop credit. Never `bash_name`, ring or subagent credits.
- Overlap: item terms covered by main-loop activity, triggering-prompt terms removed.
- `s_t = log[((u_t+0.5)/(d_t−u_t+0.5)) / ((uc_t+0.5)/(dc_t−uc_t+0.5))]`; zero unless u_t ≥ 3 and
  d_t ≥ 10. `w_t = max(idf_t, λ·s_t)`, λ ∈ {0.1, 0.25, 0.5}.

## Evidence {#evidence}

- refmatrix: 93 used delivered units (train 31, held-out 62): main-loop path 68, R12 18, label +
  path 6, label only 1; 78 of 103 R12 used events did not resolve to a delivered unit. Control used
  units: 3.
- cliquedb: 15 used units (train 7, held-out 8); control used units: 1.
- The RSJ control side rests on 3 / 1 used units, so `s_t` is almost entirely P(used | t) among
  delivered units plus smoothing.

## Counters on train {#counters}

refmatrix: 16,837 terms with d_t > 0, 816 with u_t > 0, 115 meet minimum support (66 with
s_t > 0); s_t quartiles −2.47 / −0.15 / 0.12 / 0.40 / 1.68. 80 of the 115 are df top-decile hubs
(storage, confirmed, cliquedb, partition, phase have the highest s). cliquedb: 2 supported terms,
both negative — unfittable.

## Held-out results {#results}

Terms λ·s_t lifts above idf (refmatrix): λ 0.1 → 0, 0.25 → 0, 0.5 → 3 of 115; post-hoc λ 1 → 26,
2 → 50, 4 → 55. cliquedb: none at any λ.

| weight (refmatrix held-out) | kernel share D vs C | strat O/E | NEW credits vs idf | AUC, held-out used units (n = 62) |
|---|---|---|---|---|
| idf | 42.75% vs 15.88% | 1.00 | — | 0.503 |
| λ 0.1 / 0.25 / 0.5 | = idf | 1.00 | 0 | 0.503 |
| post-hoc λ 1 / 2 / 4 | up to 44.49% vs 16.84% | 1.00 | 4 / 12 / 22, all unlabelled | 0.501 |
| reinforcement (`store.py:5607` form) | 42.69% vs 15.82% | 1.00 | 0 | 0.503 |

The existing reinforcement channel (513 concepts with signal, 313 positive) covers 1,074 of
331,197 held-out item-term slots and none of the 115 supported terms: it and s_t measure disjoint
things. Term overlap does not rank used units above other delivered units (AUC 0.50); reweighting
terms cannot fix a score that carries no use information. cliquedb: every λ and the reinforcement
form equal idf (AUC 0.785 on n = 8). {#results-notes}

## Verdict (provisional) {#verdict}

Not supported now: inert at the pre-registered λ, no held-out discrimination at larger post-hoc λ.
The binding constraint is evidence (93 / 15 trustworthy used units; 3 / 1 in control). If wanted,
collect the counters first — demote-only, never feeding retrieval — until each corpus has several
hundred main-loop used units and the control enough for the RSJ denominator, then refit on the same
split.

## Feedback-loop note {#feedback-loop}

Retrieval using s_t would be rich-get-richer, and it would undo idf's hub damping: 80 of the 115
supported terms are hubs. Guards: cap λ·s_t at the median term's idf (or tiebreak only); a
permanent control arm with s_t always a ratio against it; demote-only decay
([[feedback_decay_never_loses_knowledge]]); count only main-loop file and explicit evidence, never
term overlap, so the score is not reinforced by its own matches.

## Limits {#limits}

First-lag coverage per term on main-loop no-prompt activity (not phase 1's head variant); R12
mapping misses 78 of 103 refmatrix events (first query_id only); AUC on 62 / 8 held-out used units;
no labelled NEW credits.
