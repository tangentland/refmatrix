---
gmd: "0.1"
id: measurement-task-21.5-term-clique-2026-11-13
title: "Task 21.5 term-and-clique overlap as the used comparison (2026-11-13): term and all three clique sources add no signal over the control; two control defects in #why-data-kernel"
tags: [measurement, plan-21, task-21.5, telemetry, used, cliques, terms]
metadata:
  node_type: measurement
  status: provisional
  created: 2026-11-13
---

# Task 21.5: term and clique overlap as the `used` comparison {#root}

Phase 1 of `tc-215` (brief `workflow/agents/tc-215.md` on dev master), run at the user's
direction (2026-11-13: "the used comparison really needs always be on the terms and cliques";
"can we measure 1, 2, and 3 before deciding?"). Persisted by the lead from the agent's text.
Counts only. **Provisional** until ch-bsd reviews it with phases 2-3 and the R12 pilot.

rel: evidence-for -> [[task-21.5-tool-used-signal#r7]]
rel: evidence-for -> [[task-21.5-tool-used-signal#why-data-kernel]]
rel: related-to -> [[measurement-task-21.5-r12-pilot-2026-11-13]]

## Method {#method}

- Windows: refmatrix 2026-10-20..11-14, cliquedb 2026-11-04..11-12; read-only APFS clones
  (deleted); transcripts read in place. Join: proto5 (rev 3 rules, R4 clock, R5 attribution, R7
  per-T control); kernel k = 3, h = 2.
- Item terms T(E): every outgoing `entity_links` concept, folded by `same_as` and case; idf =
  `content_rank`'s df notion (mentions, code partition) with BM25 idf, normalised. Item-term idf
  mass by linkage: mentions 89.9% / 93.8%, part-of 2.8 / 2.4, others small.
- Activity: ring paths → concepts of entities at those paths; transcript tool inputs and reply
  text, resolved by `match_concepts`' rungs.
- Headline: a term counts only if absent from everything before the delivery, including the
  delivering prompt (the confound lbl-215 found). Term credit at idf coverage ≥ 0.10, × kernel,
  max over lags. Clique credit: the activity hits a group containing an item element the exact
  term score left uncovered (both new); weight = mean idf of the group.
- Sources: (1) compiled memory subjects; (2) STM topic composites (`_apply_turn` replay,
  `topic_composites(focus_view(g))` per prompt); (3) store-wide concept communities (spike
  population rule, Jaccard ≥ 0.3, Louvain seed 20261020 — communities, not graph cliques).

## Two control defects {#control-defects}

- **Dead-on-arrival control units:** 1,881 of 5,278 (refmatrix) and 2,630 of 7,179 (cliquedb)
  control units had their key or file delivered earlier in the session; R7's per-T rule can never
  credit them, yet they sit in the denominator. Removed below ("alive control").
- **Like-for-like:** the spec's cliquedb control score 45.7 (0.64%) includes prior-touch credits,
  set against a headline that excludes them. Headline vs headline on alive control: cliquedb
  26.6/5,874 (0.45%) vs 7.1/4,549 (0.16%) = **+0.30 pt, not −0.50**; refmatrix +0.47.
  Stratified kernel O/E for file/name: 2.55 (cliquedb), 3.17 (refmatrix). {#defects-effect}

## Results {#results}

refmatrix (8,390 delivered, 3,397 alive control):

| arm | credited D/C | kernel D | kernel C | lift (pt) | NEW credits (kernel) | precision of NEW (C+I) |
|---|---|---|---|---|---|---|
| file/name (rev 3.1) | 126/24 | 54.5 (0.65%) | 6.1 (0.18%) | +0.47 | — | (R12 pilot) |
| term | 1,643/385 | 288.2 (3.44%) | 76.4 (2.25%) | +1.19 | 1,517 (209.3) | 0/20 [0, 16%] |
| + (1) subjects | 1,891/492 | 499.5 (5.95%) | 159.8 (4.71%) | +1.25 | 1,765 (422.8) | 0/20 [0, 16%] |
| + (2) STM topics | 1,647/386 | 302.1 (3.60%) | 79.2 (2.33%) | +1.27 | 1,521 (223.1) | 0/4 [0, 49%] |
| + (3) store communities | 2,588/510 | 855.5 (10.20%) | 164.8 (4.85%) | +5.35 | 2,462 (783.8) | 0/20 [0, 16%] |

cliquedb (5,874 delivered, 4,549 alive control):

| arm | credited D/C | kernel D | kernel C | lift (pt) | NEW credits (kernel) | precision of NEW (C+I) |
|---|---|---|---|---|---|---|
| file/name | 72/32 | 26.6 (0.45%) | 7.1 (0.16%) | +0.30 | — | (R12 pilot) |
| term | 317/161 | 80.9 (1.38%) | 40.4 (0.89%) | +0.49 | 245 (43.8) | 2/20 = 10% [3, 30%], CAUSED 0 |
| + (1) subjects | = term (0 subject credits) | | | | 0 | n/a |
| + (2) STM topics | 356/163 | 82.1 (1.40%) | 41.0 (0.90%) | +0.50 | 284 (45.3) | 0/20 [0, 16%] |
| + (3) store communities | 1,496/369 | 459.6 (7.82%) | 124.5 (2.74%) | +5.09 | 1,424 (426.7) | 2/20 = 10%, CAUSED 0, both lag 100+ |

## Why the raw lifts are not signal {#not-signal}

1. **Stratified** by item kind × channel × term-count bucket (strata with ≥ 20 control units;
   6,767/8,390 and 5,309/5,874 delivered covered), kernel O/E refmatrix / cliquedb: file/name
   3.17 / 2.55; term 0.83 / 0.73; term hub-excluded 0.84 / 0.74; subjects 0.57 / n/a; topics
   0.61 / 0.66; store communities 0.97 / 0.97. The raw lift is composition: cliquedb has 3,570 of
   7,179 control units with no terms at all (mostly prompt_recall memories), while delivered units
   are term-rich scan_prompt doc anchors.
2. **Placebo** (same item and prior context vs activity from a random prompt of another session),
   real vs placebo kernel share: term 2.93% vs 3.71% (refmatrix), 1.00% vs 1.09% (cliquedb); store
   8.15% vs 9.59%, 6.90% vs 12.62%; difference-in-differences against the control's own placebo
   within ±0.05 pt except store/cliquedb −4.52. Unrelated sessions contain the items' new terms as
   often as the work after the delivery does.
3. **By activity source** (path / tool input / reply): placebo DiD per source within ±0.08 pt.
4. **Threshold sensitivity** (refmatrix): at coverage ≥ 0.5, 1.0% vs 0.9% (p 0.48).

**Labels:** 124 NEW pairs from units with no file/name credit: refmatrix 0 CAUSED, 0 INFORMED of
64; cliquedb 0 CAUSED, 4 INFORMED of 60; the rest UNRELATED (113) or CONSISTENT (26). Flags:
generic terms, prompt-named, junk group. {#labels}

## Coverage and cost {#coverage-cost}

| source | coverage delivered / alive control: refmatrix | cliquedb | build |
|---|---|---|---|
| (1) subjects | 71.9% / 42.7% | 0.2% / 0.5% (6 subjects, 2 elements each — cannot fire) | 0.2 s |
| (2) STM topics | 50.6% / 19.8% | 55.5% / 16.8% | 7.7 s / corpus |
| (3) store communities | 57.6% / 27.9% | 57.7% / 18.8% | 0.8-1.1 s |

Store communities: refmatrix 1,263 groups (median size 2, max 191), cliquedb 878 (median 2, max
266); the largest groups are grab-bags of id-like tokens. Hub top-10 normalised idf 0.12-0.20;
excluding the 30 / 34 keys with df > 0.10 N changes nothing.

## Verdict (provisional) {#verdict}

- Term overlap: **no** — below the control after stratification, placebo equal or higher, CAUSED 0/40.
- (1) memory subjects: **no** — O/E 0.57, placebo DiD 0; cannot fire in cliquedb.
- (2) STM topics: **no** — adds almost nothing over term; O/E 0.61-0.66; precision 0/24.
- (3) store communities: **no** — the +5 pt raw lift is item composition (O/E 0.97, placebo above real, CAUSED 0/40).
- The file/name join is the only leg with excess over the control after stratification (O/E
  2.55-3.17, concentrated at lag 0). Fix the spec's control comparison (headline vs headline,
  drop dead-on-arrival units) before the cliquedb "inverted" line is read. Terms and cliques are
  supported, if at all, only as a stratification covariate, never as a credit.

## Limits {#limits}

One labelling pass, no second rater; refmatrix topics stratum n = 4; the cliquedb placebo draws
from 3 sessions; the PageRank salience floor not reproduced; D15 not applied to transcript tokens;
one Jaccard threshold. Working files (scripts, label TSVs, local transcript excerpts) stay in the
session scratchpad and are not committed.

## Addendum: main-loop and prompt-term splits {#addendum-main-loop}

Re-run on fresh read-only clones (11:52; refmatrix grew to 8,457 delivered / 3,456 alive
control; cliquedb unchanged) with lbl-215's two confounds controlled: main-loop activity from the
main transcript only (tool inputs, reply text, and a `path_main` source from Read/Edit/Write/
MultiEdit/NotebookEdit, Grep/Glob paths and D15-based Bash paths; `bash_name` dropped); ring paths
(which may include subagent calls) reported apart.

**File/name, main loop vs ring (headline):**

| | credits D/C | kernel D | kernel C | lift (pt) |
|---|---|---|---|---|
| refmatrix, ring (all origins) | 132/24 | 57.6 (0.68%) | 6.1 (0.18%) | +0.50 |
| refmatrix, main loop only | 99/5 | 20.1 (0.24%) | 2.0 (0.06%) | +0.18 |
| cliquedb, ring | 72/32 | 26.6 (0.45%) | 7.1 (0.16%) | +0.30 |
| cliquedb, main loop only | 6/1 | 3.9 (0.07%) | 0.0 | +0.07 |

Only 36 of 132 (refmatrix) and 1 of 72 (cliquedb) ring headline credits are also credited from
main-loop touches; the rest are subagent or unattributed. Refmatrix main-loop credits by lag band
0 / 1-3 / 4-6 / 7+ = 10 / 6 / 7 / 76. The stratified main-loop control expects 0, so O/E is
undefined (observed 19 and 3). {#addendum-file-name}

**Term score on main-loop activity:**

| variant | refmatrix D vs C | strat O/E | placebo DiD | cliquedb D vs C | strat O/E | placebo DiD |
|---|---|---|---|---|---|---|
| incl (prompt terms kept) | 33.80% vs 13.63% | 1.15 | +4.42 | 19.55% vs 8.36% | 1.03 | +0.77 |
| noprompt | 31.92% vs 13.15% | 1.12 | +3.72 | 18.40% vs 7.34% | 1.03 | +0.58 |
| head (no prompt, no earlier session work) | 2.53% vs 1.92% | 0.82 | −0.15 | 0.54% vs 0.46% | 0.63 | −0.00 |

The excess left after removing prompt terms vanishes once terms already in the session's earlier
work are removed: it is continuation of work under way (CONSISTENT), not use. {#addendum-terms}

**Cliques on main-loop activity**, headline O/E refmatrix / cliquedb: subjects 0.56 / n/a; STM
topics 0.60 / 0.32; store communities 0.93 / 0.98. Labels on main-loop pairs: CAUSED 0 in both;
cliquedb 4 INFORMED.

**Net:** no term or clique source adds signal on main-loop activity once prompt terms are
excluded; the file/name signal is mostly non-main-loop. Recommendation addendum (provisional): the
21.5 headline is the main-loop file leg only, subagent and unattributed credits reported beside
it and never counted — which needs `origin` on ring lines (D13) or a transcript-side join.
{#addendum-net}
