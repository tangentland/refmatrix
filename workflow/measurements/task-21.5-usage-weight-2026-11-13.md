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

Phase 3 of `tc-215` (brief `#amendment-2`), at the user's question: asked for a usage-amplified secondary weight for widely linked terms. Persisted by the lead from the agent's text. Counts
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

## Addendum: placebo comparison {#addendum-placebo}

Held-out split; each unit scored against its real activity and against activity from a random
prompt of another session (prompt-term exclusion from the real prompt — a milder form of the term-clique placebo bias, mostly cancelled by the ratio of ratios), per arm; difference-in-differences as a
ratio; AUC of real-scored used units against the same units placebo-scored.

| corpus | weight | delivered real/placebo | control real/placebo | DiD ratio | AUC real vs placebo |
|---|---|---|---|---|---|
| refmatrix (62 used) | idf and every pre-registered λ | 1.31 | 1.30 | 1.00 | 0.570 |
| refmatrix | post-hoc λ 1 / 2 / 4 | | | 1.01 | 0.569 / 0.561 / 0.553 |
| refmatrix | reinforcement form | | | 1.00 | 0.570 |
| cliquedb (8 used) | every weight | 1.00 | 0.96 | 1.04 | 0.844 |

s_t separates delivered units from neither the control (stratified O/E identical to idf) nor the
placebo (DiD 1.00, as idf); larger post-hoc λ makes used-vs-placebo separation slightly worse. The
verdict stands. {#addendum-placebo-reading}

## Review corrections (ch-bsd m1, 2026-11-13) {#review-m1}

rel: amends -> [[bsd-215m1-measurements-r1]]

- Placebo rows corrected in place ([[bsd-215m1-measurements-r1#m5]]); at the pre-registered λ a
  DiD of 1.00 equals idf by construction (at most 3 of 115 terms change weight), so it is not
  separate evidence. The reinforcement comparison and the placebo addendum were NOT
  pre-registered.
- The pre-registered primary hub slice, omitted above: refmatrix held-out 58.13% vs 27.16%, O/E
  1.00 for every λ ([[bsd-215m1-measurements-r1#m2]]).
- "Trustworthy" overstates the evidence: 68 of 93 refmatrix used units are main-loop path credits,
  whose labelled precision is 0.35 [0.19, 0.54] ([[bsd-215m1-measurements-r1#s3]]). The binding
  constraint is label validity as well as count; the "do not build" verdict is stronger, not weaker.
- Pre-registration timing verified: PREREG 12:03:57, script 12:04:38, first outputs 12:04:44.
