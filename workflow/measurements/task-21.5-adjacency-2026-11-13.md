---
gmd: "0.1"
id: measurement-task-21.5-adjacency-2026-11-13
title: "21.5 graph-neighbour leg (2026-11-13): code-structure adjacency does not separate from the control; the GMD legs' lift is doc-anchor co-citation — keep adjacency out of the used signal"
tags: [measurement, plan-21, task-21.5, graph, adjacency, used]
metadata:
  node_type: measurement
  status: provisional
  created: 2026-11-13
---

# 21.5 graph-neighbour leg, 2026-11-13 {#root}

Run by `adj-215` (brief `workflow/agents/adj-215.md`) at the user's direction (invert the weight of
widely linked concepts). Persisted by the lead; counts only; read-only APFS clones, deleted.
**Provisional** (no ch-bsd round yet).

rel: related-to -> [[measurement-task-21.5-relation-gaps-2026-11-13]]
rel: related-to -> [[measurement-task-21.5-term-clique-2026-11-13]]

## Method {#method}

proto5 join (D15 bases, R4 prompt clock, R5 attribution, R7 per-T control); the direct leg
reproduces the spec (refmatrix 258 credited / 125 headline; cliquedb 215 / 72). A touched project
file X matches a delivered unit when X's entities and the unit's entity share a concept over the
leg's linkages (same_as folded); weight = max idf of the shared concepts (`Store.concept_df`'s
notion, `w = idf / ln N`); unit credit = max over touches of w × kernel (k = 3, h = 2). Legs:
**code** (defines, calls, called_by), **gmd** (implements, part-of, lead), **mentions**. Headline
excludes prior touches; O/E stratified by kind × channel (≥ 20 control units). {#method-body}

## Results (headline) {#results}

| corpus | leg | delivered | control | O/E (all lags / lag ≤ 3) |
|---|---|---|---|---|
| refmatrix | direct | 125 = 1.50% | 24 = 0.46% | — |
| refmatrix | code | 45 = 0.54% | 7 = 0.13% | 1.51 / **0.63** |
| refmatrix | gmd | 227 = 2.72% | 33 = 0.63% | 1.68 / 2.63 |
| refmatrix | mentions | 311 = 3.73% | 118 = 2.25% | 1.46 / 1.62 |
| cliquedb | direct | 72 = 1.23% | 32 = 0.45% | — |
| cliquedb | code | 2 | 16 | 0.30 |
| cliquedb | gmd | 22 = 0.37% | 5 = 0.07% | 3.31 / 5.73 |
| cliquedb | mentions | 58 = 0.99% | 51 = 0.71% | 2.25 |

94-99% of raw adjacency matches are prior touches (scan_prompt delivers neighbours of files already
in work), so including them measures retrieval context, not use. In refmatrix the strong leg's
headline lift sits almost entirely in the doc-anchor × scan_prompt stratum (160/4,018 vs 11/856);
the code leg lifts only in the lag 7+ tail. {#results-notes}

## Verdict (provisional) {#verdict}

- Code-structure adjacency does not separate from the control (refmatrix below control at lag ≤ 3;
  cliquedb inverted). Do not add it.
- The GMD legs' lift is doc-anchor co-citation: bug-216 binds most bare doc-id `rel:` edges to a
  path-less concept reached by every co-citing doc, `lead` behaves like `mentions` (~202k edges), and
  R7's control (trimmed, lower-ranked items) understates the base rate. Read as "the agent opened a
  sibling doc in the same cluster", not use.
- Keep adjacency out of 21.5's used signal; at most an exploratory doc-anchor GMD column in R12's
  labelled sample after bug-216 is fixed and re-measured.

## Limits {#limits}

Units cluster by session and prompt (p-values overstated); 1,150-1,400 units per corpus carry ids
missing from the snapshot; global-scope deliveries unresolved (catalog not copied); only 351 / 430
touched paths are catalogued; small cliquedb samples. Scripts stay in the session scratchpad (`adj/`).
