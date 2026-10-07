---
gmd: "0.1"
id: spike-2026-10-07-adjacency-shape
title: "Spike 2026-10-07: the shape of refmatrix's adjacencies across six stores"
tags: [eval, spike, graph, bitmaps, helix]
---

# Spike 2026-10-07: what shape do our adjacencies have? {#root}

Measurement only, never imported by `src/`. `measure.py` reads a COPY of a store's
`catalog.read.duckdb` and measures the term → location incidence layer (`mentions`, concept →
entity). Every term-term relation in ADR-0004 is a projection of that layer. The user asked the
question on 2026-10-07 ("is there any intrinsic shape of our adjacencies that could be
leveraged?") and asked for more than one project. Run on six stores: the code partition of each,
with session partitions excluded. {#lead}

rel: evidence-for -> [[refmatrix/adr-0004-unified-location-space-index]]

## Reproduce {#reproduce}

```bash
cp <project>/.refmatrix/catalog.read.duckdb /tmp/x/<p>.duckdb
env -u PYTHONPATH .venv-eval/bin/python -I eval/spikes/2026-10-07-adjacency-shape/measure.py \
    /tmp/x/<p>.duckdb --partition-id <code partition id> --out results-<p>.json
```

Seed `20261007`; 200 source entities for reach. Raw numbers are in `results-*.json`; run logs are
in `workflow/review-output/spike-shape-*.log`.

## Results {#results}

| store | concepts | entities | edges | df p50 / p99 / max | share df≤1 | tail α (xmin, KS) | top-1% edge share | hapax byte share | reach@1 all→no-hubs | reach@2 all→no-hubs | modularity (communities) | bytes saved: dense ids | bytes saved: path/community order vs random |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| refmatrix | 24,297 | 7,020 | 270,199 | 2 / 183 / 1245 | 0.47 | 1.76 (5, 0.031) | 0.31 | 0.13 | 0.25→0.10 | 0.56→0.54 | 0.22 (350) | 42% | 0.15% |
| cliquedb | 19,456 | 4,619 | 283,410 | 2 / 223 / 1302 | 0.39 | 1.72 (5, 0.036) | 0.27 | 0.11 | 0.39→0.24 | 0.80→0.74 | 0.12 (59) | 29% | 0.19% |
| viascope | 18,904 | 13,533 | 176,936 | 2 / 126 / 845 | 0.40 | 1.88 (6, 0.033) | 0.25 | 0.15 | 0.07→0.02 | 0.72→0.55 | 0.45 (336) | 28% | 0.11% |
| cliquet | 7,740 | 1,986 | 100,795 | 3 / 175 / 754 | 0.30 | 1.75 (4, 0.039) | 0.21 | 0.11 | 0.57→0.37 | 0.92→0.92 | 0.14 (13) | 15% | 0.25% |
| orderly | 3,999 | 482 | 16,153 | 2 / 34 / 85 | 0.46 | 2.18 (4, 0.046) | 0.11 | 0.34 | 0.32→0.24 | 0.87→0.86 | 0.26 (10) | 0% | 0.15% |
| atldb | 3,060 | 544 | 7,708 | 1 / 17 / 54 | 0.58 | 3.08 (8, 0.031) | 0.10 | 0.50 | 0.07→0.04 | 0.26→0.17 | 0.43 (97) | 0% | 0.72% |

**Notes on the columns:**
- reach@k = mean fraction of all entities within k entity-hops (entity → concept → entity is one
  hop). "No-hubs" removes the top 1% of concepts by df.
- Byte savings are total serialized roaring bytes over every concept bitmap after `run_optimize`.
  "Dense ids" means renumbering entity ids 0..N-1 in today's order. The last column compares the
  best of path-locality and community order against a random order.

The top hubs are generic words: `one`, `only`, `every`, `plan`, `file`, `workflow`; viascope's are
`keyword/*` (`channel`, `all`, `when`, `per`). {#results-table}

## What the shape is {#findings}

1. **Heavy-tailed degree, in every store large enough to fit.** The four large stores have tail
   exponents α 1.72–1.88 (KS ≤ 0.039), the top 1% of concepts hold 21–31% of all edges, and 30–47%
   of concepts are hapax (df ≤ 1). The two small stores are less heavy (α 2.2–3.1). The hapax tail
   holds few edges, but 11–50% of the bitmap BYTES, because every tiny bitmap pays container
   overhead. {#f-tail}
2. **Small world, but NOT mainly through hubs.**
   - 56–92% of entities are within two hops in the four large stores.
   - Removing the top 1% hubs cuts ONE-hop reach sharply (refmatrix 0.25→0.10, cliquet 0.57→0.37).
   - It barely moves TWO-hop reach in four of six stores (cliquet 0.92→0.92, orderly 0.87→0.86,
     refmatrix 0.56→0.54, cliquedb 0.80→0.74). Only viascope (0.72→0.55) and atldb (0.26→0.17)
     depend on their hubs.
   - So my earlier explanation ("walks failed because hubs put everything within two hops") is
     only HALF right. Mid-degree concepts alone saturate two hops, and hub exclusion will not rescue
     a global walk.

   {#f-reach}
3. **Communities are weak except in two stores.** Louvain modularity is 0.12–0.26 for four stores
   (weak block structure) and 0.43–0.45 for viascope and atldb (real communities). Community
   structure is a per-store property, not a general one. {#f-communities}
4. **Compression comes from DENSE ids, not ORDER.**
   - Renumbering entity ids densely saves 15–42% of bitmap bytes in the four large stores. Today's
     entity ids are sparse integers in the millions, so each bitmap spans more chunks.
   - Ordering by path locality or by community, versus a random order, saves **< 0.75%** everywhere.
     At entity granularity, a store's entities fit inside one 65,536-id roaring chunk, so array
     containers cost 2 bytes per member whatever the order.
   - "Locality order buys run containers" is therefore NOT supported at entity granularity. It is
     untested at ADR-0004's sentence (`sid`) granularity, where one term can occupy consecutive
     sentences.

   {#f-compression}
