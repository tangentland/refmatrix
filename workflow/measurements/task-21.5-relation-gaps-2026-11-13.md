---
gmd: "0.1"
id: measurement-task-21.5-relation-gaps-2026-11-13
title: "Relation gaps for relevance matching (2026-11-13): code-structure 2-hop and GMD-provenance combos beat chance; GMD rel: gap = bare doc-id targets bound to a same-named concept (bug-216)"
tags: [measurement, plan-21, task-21.5, graph, linkages, gmd, relevance]
metadata:
  node_type: measurement
  status: provisional
  created: 2026-11-13
---

# Relation gaps for relevance matching, 2026-11-13 {#root}

Phase 2 of `tc-215` (brief `#amendment-1`), at the user's question "are there missing relations
or relation combos that would increase relevancy matching". Persisted by the lead from the
agent's text. Counts only. **Provisional** until ch-bsd. Everything here measures RELEVANCE (what
the main loop touches next), not USE: labelled positives (refmatrix 7, cliquedb 10) are too few
to rank relations for use.

rel: related-to -> [[measurement-task-21.5-term-clique-2026-11-13]]
rel: related-to -> [[measurement-task-21.5-r12-pilot-2026-11-13]]

## Method {#method}

(A) unlabelled, at scale: project files the main loop touches at lags 0-3 after a delivery,
excluding the item's own file and anything touched earlier in the session; delivered units vs
alive control units (≤ 4,000 per arm, seed 20261113). (B) labelled: does a relation connect the
item to another main-loop file in the credited window, for positive / negative / control pairs.
Hop-2 middle nodes capped at degree ≤ 50 (set before results). Base rate: a random indexed project
file is touched next with probability 1.11% (refmatrix, 1,327 files), 0.18% (cliquedb, 1,587).

## Existing metapaths {#metapaths}

| corpus | metapath | nbr precision D | C | × random | support (credited / covered) |
|---|---|---|---|---|---|
| refmatrix | all ≤ 2-hop neighbours | 0.25% | 0.24% | 0.23× | |
| cliquedb | all ≤ 2-hop neighbours | 0.13% | 0.25% | 0.74× | |
| refmatrix | mentions>.mentions< | 0.25% | 0.28% | 0.2× | |
| refmatrix | lead>.defines< | 3.26% | 0 of 59 | 2.9× | 17/395 |
| refmatrix | mentions>.defines< | 2.38% | 0.77% | 2.1× | 45/868 |
| refmatrix | mentions>.called_by< | 2.07% | 0.46% | 1.9× | 46/716 |
| refmatrix | lead>.called_by< | 2.07% | 0 | 1.9× | 14/312 |
| refmatrix | mentions>.calls< | 1.53% | 0.44% | 1.4× | 34/678 |
| refmatrix | mentions<.derives-from< | 6.33% | 0 of 31 | 5.7× | 5/55 |
| refmatrix | mentions<.implements< | 5.88% | 1.59% | | 5/48 |

The bulk of graph reach (co-mention, lead-mention) touches 50-127 files per unit at chance.
cliquedb has almost no calls/defines links; none of its metapaths beat chance. {#metapath-notes}

**Combos beating their singles (refmatrix):** derives-from< + related-to< 54.5% (6/11);
derives-from< + derives-from> 37.5% (6/16, control 0/13); derives-from< + part-of> 22.2% (8/36,
control 0/24); lead>.called_by< + lead>.defines< 3.3% (13/395, control 0/53);
mentions>.called_by< + mentions>.defines< 2.7% (38/1,396, control 0.8%). The GMD-provenance
combos are strongest but rest on 6-8 touches. No cliquedb combo beats its singles. {#combos}

## Candidate missing relations {#candidates}

Files not already reachable by the ≤ 2-hop graph.

| relation | refmatrix D vs C (× random, coverage) | cliquedb D vs C (× random, coverage) | build |
|---|---|---|---|
| memory body / source paths | 3.76% vs 1.97% (3.4×, 7.3%) | 0.72% vs 0.21% (4.1×, 8.2%) | cheap, at ingest |
| same-session co-touch | 2.85% vs 6.07% (2.6×, 5.0%) — control higher | 0.26% vs 0.60% (1.5×, 12.2%) | ring index |
| doc cites a path | 1.58% vs 1.57% (1.4×, 50.5%) | 0.11% vs 0.05% (0.6×, 34.8%) | cheap, at ingest |
| git co-change (2-20 files) | 0.92% vs 1.12% (0.83×, 44.9%) | 0.10% vs 0.06% (0.5×, 14.8%) | git log |
| test ↔ code by name | 0/196 (1.4%) | none | |
| GMD rel: target not linked from the item | 0.33% (0.3×, 45%) | 0.06% | |
| embedding similarity | not measurable (no vectors in the copy; no model loads) | | |

## GMD rel: edges missing from entity_links {#gmd-gap}

> **Correction (2026-11-13, after ch-bsd `bsd-215m1`; supersedes the lead's first note).** The 66.9% / 80.8%
> is real. Edges are stored `rel: X verb -> Y` as `entity_links(entity_id = Y, concept_id = X)`, but this probe
> already walked both directions, so direction is not the cause. The cause: a bare doc-id target binds a
> path-less CONCEPT with the doc's name instead of the doc (`ingest_gmd._resolve_target_eid` tries concept
> first): 67.4% of 5,431 `rel:` evidence rows land path-less, ≥ 1,909 of them on a doc that IS ingested.
> Consequence for this measurement: the 2-hop GMD-provenance combos below (derives-from< + related-to< /
> part-of>) largely measure CO-CITATION of the same id, not item → cited doc; their "strongest precision"
> reading and the "highest leverage, cheap" derive line in [[#shortlist]] are withdrawn until bug-216 is
> fixed and phase 2 re-run. The code-structure metapaths (defines / called_by) are unaffected.
> {#gmd-gap-correction}

refmatrix: 3,376 cross-file `rel:` lines resolve; 2,257 (66.9%) have no `entity_links` edge from
any entity of the source file to the target file (top verbs: contradicts 542, derives-from 434,
depends-on 262, related-to 258, amends 152, evidence-for 124, part-of 123, specifies 107).
cliquedb: 2,213 of 2,740 (80.8%) unlinked (depends-on 676, related-to 583, derives-from 443,
amends 250, implements 102). The strongest combos above ride derives-from / related-to / part-of,
so this is the clearest derivable gap. Logged as bug-216 (suspected) for the bridge check.

## Misses {#misses}

Of next-touched (unit, file) pairs, reached by nothing: refmatrix 97.0% of 58,996 (graph 2.0%),
cliquedb 94.5% of 11,151 (graph 4.7%). Most next touches are ongoing work, not use of the item:
a coverage ceiling, not a miss rate.

## Labelled pairs (refmatrix) {#labelled}

5 POS (CAUSED+INFORMED with a window file), 135 NEG, 20 control: lead>.mentions< 4/5 vs 24/135
vs 2/20 (Fisher one-sided p 0.006); mentions>.lead< 4/5 vs 28/135 (p 0.010); mentions>.mentions<
5/5 vs 57/135 (p 0.016); git co-change 4/5 vs 47/135 (p 0.06); doc cites path 3/5 vs 31/135
(p 0.09). About 30 tests, none survives Bonferroni. cliquedb (10 POS / 109 NEG): nothing above NEG.

## Shortlist (provisional) {#shortlist}

- **Add to relevance scoring:** code-structure 2-hop (mentions> / lead> then defines< / called_by<;
  2-3× chance; refmatrix only); GMD-provenance combos on derives-from with related-to / part-of
  (strongest precision, small support).
- **Derive:** the missing GMD `rel:` edges (67-81% never reach `entity_links`; highest leverage,
  cheap); memory body / source paths (3.4-4.1×, cheap); doc cites path (1.4×, refmatrix only).
- **Not worth it as relevance relations:** git co-change, session co-touch (control higher),
  test ↔ code.

## Limits {#limits}

One hop-2 degree cap; ≤ 4,000 units per arm; outcome = main-loop transcript paths only; git log
read-only; random baseline ignores file popularity; no placebo in this phase.
