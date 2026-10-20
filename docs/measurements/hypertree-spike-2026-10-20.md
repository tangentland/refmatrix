---
gmd: "0.1"
id: spike-2026-10-20-hypertree
title: "Spike 2026-10-20: the hypertree M1-M7 measurements — which internal structure surfaces more associations"
tags: [measurement, spike, hypertree, containment, facets, bitmaps, associative-power, helix]
metadata:
  node_type: measurement
  created: 2026-10-20
  harness: eval/spike_hypertree/
  results: eval/spike_hypertree/results/
---

# Spike 2026-10-20: the hypertree measurements M1-M7 {#root}

The user ordered this run on 2026-10-20 ("run the m1-7 spike"). It runs the seven deciding
measurements that [[exploration-hypertree#measurements]] wrote down before any data existed,
over the same six stores as the 2026-10-07 adjacency-shape spike. The user's framing governs the
reading: "the primary motivation for the hypertree conversation is to insure rmx's internal
structures maximize associative power and is not meant as an endorsement of any particular
implementation." So each result below is read twice: once against its pre-registered band, and
once for what it says about which structure surfaces more of "what else bears on this?", and at
what cost. {#lead}

rel: derives-from -> [[exploration-hypertree]]
rel: related-to -> [[spike-2026-10-07-adjacency-shape]]
rel: evidence-for -> [[exploration-hypertree#measurements]]

## Answer {#answer}

Read against the pre-registered bands, the data implies **Option B, scoped**:
- **The graph stays authoritative and cross-cutting.**
- **Containment placements earn their keep only WITHIN files:**
  - `gmd` section and `code` def representations, for "where in this file" address queries;
  - written inline, because they are cheap.
- **Not earned:**
  - an LCA proximity band;
  - a tree render default;
  - an `fs` path-prefix table;
  - a subject tree (except, in principle, viascope, which still lacks labels);
  - Dewey-ordered ids.
- **C stays eliminated.** Every tree-scoped retrieval lost MRR on every set, held-out included.

On associative power, the internal structure that surfaces the most of "what else bears on this?"
is the cross-cutting incidence graph:
- 50–69% of an entity's ten strongest associates sit outside its depth-2 subtree (M1);
- scoping retrieval to a subtree drops real hits (M3);
- community structure WEAKENED as the stores grew (M5).

The tree carries real associative signal only inside a file: same-file pairs are 2–27× random.
That is the containment B-scoped indexes. {#answer-body}

## Band table {#band-table}

| M | refmatrix | cliquedb | viascope | cliquet | orderly | atldb | pre-registered band → action |
|---|---|---|---|---|---|---|---|
| M1 local@2 (edge-w) | 1.6% | 1.5% | 6.3% | 2.3% | 8.2% | 12.7% | all < 25% → no LCA band; B only for containment + render if M2 passes |
| M2 containment share | 61.1% (subtree 8.2%) | n = 2 | n = 4 | n = 0 | n = 1 | 97.6% (subtree 4.1%) | > 30% → B, all three representations (but the demand is within-file, not subtree); 4 stores insufficient data |
| M3 MRR Δ (d2_top1) | — | lines −0.030, merge −0.028 | — | — | — | — | MemAware test-720 −0.0075 (held-out) → loss > 0.005: C stays eliminated |
| M4 tree saving | 3.4% (as defined); 16.7% concept-anchor variant | 18.7%* | 31.0%* | 17.9%* | 21.2%* | 28.6%* | as defined < 10% → keep flat (relative paths save 3.9%); *the variant only |
| M5 modularity | 0.15 | 0.12 | 0.45 | 0.14 | 0.26 | 0.33 | viascope ≥ 0.40 admit (labels generic); atldb 0.30–0.40, labels fail; rest < 0.30 none |
| M6 p95 place ÷ p95 sync | not finished | 0.36% | not finished | 0.33% | 1.30% | 0.81% | < 5% → inline (per-file p95 14–39%: fuse into the entity transaction) |
| M7 Dewey vs random | 2.42% | 2.51% | 6.85% | 0.21% | 0.09% | 1.21% | 3 stores 2–10% → order at compaction only; 3 stores < 2% → irrelevant |

{#band-table-body}

## Method {#method}

- **Stores and partitions.** These are the six stores of [[spike-2026-10-07-adjacency-shape]],
  each with its code partition: refmatrix (4), cliquedb (2), viascope (104), cliquet (1), orderly
  (1) and atldb (2). Session partitions are excluded. As in that spike, every row is refmatrix's
  own catalog built over that repo's files. None of them measures the cliquedb or cliquet engines.
- **Copies, never live stores.** Each store's lock-free snapshot `.refmatrix/catalog.read.duckdb`
  was copied to `/Volumes/littlebig/refmatrix-spike-hypertree/<store>/catalog.duckdb`, along
  with read-only copies of its `query.log` and `cli.log` (for M2 and M4). M6 wrote only to
  further copies under `.../m6/`, with no daemon running. M3's MemAware store was copied from its
  snapshot in the same way. No dev-tree `rmx` ran against a live store, and no live `.refmatrix/`
  was written.
- **Code.** The dev tree was used through `.venv-eval` with `PYTHONPATH=src`, `HF_HUB_OFFLINE=1`
  and `reranker=None`. Nothing contacted a daemon, the hub or `models.sock`.
- **Seed.** Seed `20261020` everywhere, except where a reused harness keeps its own seed for
  comparability: M3 keeps loc-coloc's `20260903` and M5 keeps the 2026-10-07 `measure.py`'s
  `20261007`.
- **No raw query text is committed.** M2 and M4 read prompt and grep bodies in-process and write
  only aggregates and sha256 prefixes.

**Snapshot timestamps** (mtime of each copied `catalog.read.duckdb`):

| store | snapshot mtime | bytes |
|---|---|---|
| refmatrix | 2026-10-20 12:08:55 | 867,708,928 |
| cliquedb | 2026-10-19 23:09:35 | 241,709,056 |
| viascope | 2026-10-19 23:09:45 | 305,672,192 |
| cliquet | 2026-10-19 23:09:39 | 74,723,328 |
| orderly | 2026-10-19 23:09:42 | 22,818,816 |
| atldb | 2026-10-19 23:09:32 | 32,780,288 |
| MemAware (M3) | 2026-09-20 16:24 | (copied from `/Volumes/littlebig/memaware`) |

{#snapshots}

**Scripts and outputs** (`eval/spike_hypertree/`):

| M | script | results |
|---|---|---|
| shared | `common.py` (store list, copy paths, path normalisation) | |
| M1 | `m1_tree_coherence.py <store>` | `results/m1_<store>.json` |
| M2 | `m2_containment_demand.py` | `results/m2_all.json` |
| M3 | `m3_tree_scoped_recall.py` | `results/m3_cliquedb.json`, `results/m3_memaware.json` |
| M4 | `m4_render_tokens.py` | `results/m4_<store>.json` |
| M5 | `m5_subject_representation.py` (runs the 2026-10-07 `measure.py` unchanged) | `results/m5_all.json`, `results/m5_shape_<store>.json` |
| M6 | `m6_placement_write.py <store>` | `results/m6_<store>.json` |
| M7 | `m7_sid_order.py` | `results/m7_<store>.json` |

Run logs are in `workflow/review-output/spike-hypertree-m<N>-*.log`. {#scripts}

## M1: tree-coherence of concepts {#m1}

**Question.** Are concept hyperedges local to the `fs` containment tree? In other words, is
refmatrix a hypertree in the graph-theory sense ([[exploration-hypertree#def-graph-theory]])?

**How it was operationalised.**
- **Members.** Every `mentions` member with a path. Most members are path-bearing GMD section
  nodes (concept-kind), and the 2026-10-07 spike counted them too.
- **Tree nodes.** A member's node is its file. A file node counts as a tree level, so "all
  members in `src/x.py`" has an LCA depth of 2.
- **Memory files.** Files in the project's `~/.claude` memory dir map to a virtual `@memory`
  subtree. Other paths outside the root are excluded and counted.
- **Population.** Concepts with df ≥ 2.
- **Band metric.** The edge-weighted share of concepts whose LCA depth is ≥ 2.
- **Null model.** The same concepts, with the entity → node assignment permuted (3 seeded draws).

| store | members in tree | files | concepts | edges | local@2 edge-weighted | local@2 unweighted | local@1 edge-weighted | null local@2 (edge-w / unw) | depth-2 subtrees per concept (mean / p50) | band |
|---|---|---|---|---|---|---|---|---|---|---|
| refmatrix | 15,298 | 1,403 | 16,665 | 493,856 | 1.6% | 14.6% | 7.2% | 0.2% / 2.1% | 7.1 / 3 | < 25% |
| cliquedb | 11,445 | 1,087 | 15,064 | 511,708 | 1.5% | 16.5% | 2.6% | 0.4% / 5.3% | 7.9 / 3 | < 25% |
| viascope | 36,622 | 2,255 | 11,303 | 168,312 | 6.3% | 29.6% | 7.4% | 0.5% / 3.7% | 3.2 / 2 | < 25% |
| cliquet | 2,362 | 133 | 5,709 | 103,074 | 2.3% | 10.2% | 8.1% | 0.7% / 5.5% | 5.0 / 3 | < 25% |
| orderly | 536 | 52 | 2,188 | 14,506 | 8.2% | 19.7% | 16.7% | 1.1% / 3.5% | 3.3 / 2 | < 25% |
| atldb | 3,142 | 364 | 2,747 | 18,515 | 12.7% | 26.6% | 17.3% | 0.2% / 0.8% | 2.9 / 2 | < 25% |

{#m1-table}

The non-keyword concepts give the same local@2 (0.013–0.120), and so does dropping the top-1%
hubs (0.020–0.138).

**Band.** All six stores are < 25%: concepts are not tree-local, so B gets no LCA proximity band.
B serves only containment queries and render, and only if M2 passes. The result holds even at
depth ≥ 1, the coarsest cut (one top-level directory): at most 17%. C's precondition (≥ 60%) is
far off in every store. {#m1-band}

**Associative power.** The tree is a REAL but MINORITY signal for association.

The table below:
- takes 300 seeded source entities in each store;
- ranks every other entity by idf-weighted shared non-hub concepts;
- reports where each source's top-10 associates sit.

The lift columns give mean idf-weighted Jaccard by tree distance, as lift over random pairs.

| store | top-10 associates outside the source's depth-2 subtree | same, expected at random | top-10 in the same file | lift: same file | lift: same dir | lift: same depth-2, other dir | lift: other depth-2 |
|---|---|---|---|---|---|---|---|
| refmatrix | 67% | 90% | 8% | 5.7× | 2.0× | 2.4× | 0.8× |
| cliquedb | 67% | 80% | 13% | 7.5× | 1.6× | 1.8× | 0.8× |
| viascope | 50% | 85% | 12% | 27.3× | 4.1× | 2.5× | 0.5× |
| cliquet | 69% | 81% | 19% | 1.8× | 1.8× | 1.1× | 0.8× |
| orderly | 57% | 89% | 34% | 3.9× | 1.3× | 1.5× | 0.8× |
| atldb | 64% | 98% | 31% | 9.0× | 2.6× | 13.7× | 0.9× |

{#m1-assoc-table}

Tree proximity predicts association far above chance: same-file pairs are 2–27× random.
Even so, **50–69% of an entity's ten strongest associates live in another depth-2 subtree.**
A structure that groups by the tree puts most of "what else bears on this" somewhere else. The
tree's associative signal is concentrated inside the file (sections and definitions), not in
directories: same-dir and same-subtree lifts are 1.1–4× outside atldb. {#m1-assoc}

## M2: containment-query demand {#m2}

**Universe.** The window is 2026-09-20 to 2026-10-20, read from the copied logs.

What counts as a real corpus query:
- `cli.log` `grep` runs that read files inside the store root, or run `-r` from inside it;
- `context`, `query` and `neighbors` runs;
- `query.log` `scan` (prompt) and `recall` bodies.

What is excluded and counted:
- pipe filters: 25,587 in refmatrix, most of them the test-summary `-qE` checks;
- greps over files outside the root;
- greps over run artifacts (`*.log`, `workflow/review-output/`);
- hook bookkeeping rows.

**Containment-shaped**, as the doc defines it:
- C1: grep scoped to a subdirectory;
- C2: a path prefix, or "in/under X" with a path-like X, in a query argument or a prompt;
- C3: `--hit-lines` on a context call;
- C4: grep on ONE named file, the grep form of "`--hit-lines` on one file".

The band is read on C1–C4 together. It is also split into SUBTREE (C1 + C2, the path-prefix
question the `fs` representation serves) and WITHIN-FILE (C3 + C4, the section/def question the
`gmd` and `code` representations serve).

| store | real queries | containment (doc definition) | of which subtree | of which within-file | facet-shaped | multi-file greps | grep root-wide | band |
|---|---|---|---|---|---|---|---|---|
| refmatrix | 3,524 | 61.1% | 8.2% | 53.0% | 0.7% | 431 | 7 | > 30% |
| cliquedb | 2 | 100.0% | 0.0% | 100.0% | 0.0% | 0 | 0 | insufficient data (n = 2) |
| viascope | 4 | 75.0% | 25.0% | 50.0% | 50.0% | 0 | 1 | insufficient data (n = 4) |
| cliquet | 0 | — | — | — | — | — | — | insufficient data |
| orderly | 1 | 0.0% | 0.0% | 0.0% | 0.0% | 0 | 0 | insufficient data (n = 1) |
| atldb | 170 | 97.6% | 4.1% | 93.5% | 1.8% | 1 | 3 | > 30% |

{#m2-table}

**Band.**
- **refmatrix (61%) and atldb (98%)** are the two stores with enough queries (n ≥ 30). Both are
  > 30%: B with all three representations.
- **The other four stores** logged 0–4 corpus queries in the window. Their M2 is
  **insufficient data**, not a band.

{#m2-band}

**What the split says.** The demand is almost entirely WITHIN-FILE ("where in this file is X").
Subtree demand is 8.2% (refmatrix) and 4.1% (atldb). That is under the doc's 10% line, so a
path-prefix (`fs`) placement table is not earned. `entities.path` ranges (Option A) serve the
subtree case. What is earned is the section/def containment that the `gmd` and `code`
representations would index. Facet-shaped queries (`--include`, `kind:`/`mtype:`) are 0.7%
(refmatrix) and 1.8% (atldb). {#m2-split}

**Caveats.**
- **Built-in Grep tool calls are invisible.** `cli.log` sees only Bash `grep`, which the PreToolUse
  rewrite routes through `rmx grep`. Claude Code's built-in Grep tool calls never reach the log.
  Those are typically root-wide or subdir searches, so this sample is biased toward file-scoped
  greps. The subtree share is therefore a floor, not an estimate.
- **Prompts rarely name containment.** Only 3 of 896 prompts in refmatrix use "in/under <path>".

{#m2-caveats}

**Associative power.** Containment queries are ADDRESS lookups ("where in this file"), not
association lookups ("what else bears on this"). A placement index makes them cheaper. It does
not add associations. The one place the two meet is M1's finding: association is concentrated
within files. A within-file placement (section ▸ def) is also the structure where the tree
carries associative signal. {#m2-assoc}

## M3: recall parity of a tree-scoped retrieval {#m3}

**Harness.** This reuses the 2026-10-06 loc-coloc harness (`cliq_grid3` / `mem_grid2` query
construction, gold labels, a candidate pool of 50, a top-20 cutoff, and seed 20260903).
- **Base.** Production `Store.content_rank`, with no reranker and no co-location.
- **Tree arm.** Base's top 50, re-ranked so that candidates inside subtree S come first (in base
  order) and the rest follow as the graph fallback.

S is chosen three ways:
- `d2_top1`: the top-1 hit's directory, cut to depth 2;
- `d2_plur10`: the plurality depth-2 subtree among the top 10;
- `dir_top1`: the top-1 hit's own directory.

MemAware's tree is its on-disk `corpus/<date>/<session>.md` layout, so there S is one day of
sessions. That is the closest honest containment for a session corpus, and it is labelled as a
variant. On MemAware `dir_top1` equals `d2_top1`, so it is not reported.

| set | n | base MRR | d2_top1 (Δ, won/lost) | d2_plur10 (Δ, won/lost) | dir_top1 (Δ, won/lost) | gold all outside S (d2_top1) |
|---|---|---|---|---|---|---|
| cliquedb `lines` | 300 | 0.890 | 0.861 (−0.030, +4/−25) | 0.548 (−0.342, +9/−122) | 0.862 (−0.029, +3/−26) | 28 |
| cliquedb `merge` | 300 | 0.725 | 0.697 (−0.028, +6/−27) | 0.548 (−0.177) | 0.699 (−0.026, +5/−27) | 49 |
| MemAware test-720 (held-out) | 720 | 0.185 | 0.178 (−0.0075, +13/−99, p = 1.5e-17) | 0.167 (−0.018, +54/−137) | n/a | 598 |
| MemAware tune-180 | 180 | 0.221 | 0.213 (−0.008, +4/−32) | 0.166 (−0.055, +12/−51) | n/a | 145 |

{#m3-table}

cliquedb has no tune/test split. The tree arms fit no parameters, though, so every cliquedb query
is out-of-sample. cliquedb's base MRR (0.890 / 0.725) is below loc-coloc's 0.921 / 0.746 because
this run uses the 2026-10-19 snapshot. MemAware's base reproduces loc-coloc's 0.185 exactly.

**Band.** Every arm loses more than 0.005 MRR on every set, including held-out test-720, and every
sign test is significant. **C stays eliminated.** {#m3-band}

**Associative power.** This is the most direct test of the user's question, and it is
unambiguous:
- Scoping to one subtree never moves hit@1, because the top hit is in S by construction.
- It loses gold at ranks 2–20 that sits OUTSIDE the subtree.
- On MemAware, 86.6% of relevant sessions are outside the top day-subtree, and 372 of 900
  questions have relevant sessions on 2–5 different days.

Relevance is cross-tree by nature. The graph-wide order surfaces more of what bears on a query.
{#m3-assoc}

## M4: render token cost {#m4}

**Bundles.** Production bundles were rebuilt on the copies:
- the scan-prompt content bundle;
- plus the top-5 PPR-ranked concepts through `build_context`, at 600 tokens per concept and 10
  entities;
- with scan-prompt's cross-section dedup, `reranker=None` and `grep_backstop=False`.

**Arms.** Four renders of the same entries:
- flat = production `render_text`;
- flat with root-relative paths (the cheap Option-A fix);
- a tree per linkage group;
- one tree per bundle.

Tokens are counted with production `estimate_tokens` (chars/4). tiktoken is not installed in
`.venv-eval`, so there is no cl100k cross-check.

**As defined: 200 logged prompts, refmatrix only** (196 produced bundles; a seeded sample from 695
deduplicated scan bodies):

| arm | tokens / entity | saving vs flat |
|---|---|---|
| flat (production) | 68.5 | — |
| flat, root-relative paths | 65.9 | 3.9% |
| tree per linkage group | 66.2 | 3.4% (per-prompt median 0.6%) |
| one tree per bundle | 67.5 | 1.4% |

{#m4-defined}

**Labelled variant: concept anchors.** The other five stores have no logged prompts, so this
variant uses up to 200 seeded concept names (mentions df ≥ 2, not `keyword/`) as single
`build_context` anchors, in all six stores:

| store | n | flat → relative → tree-group → tree-one (tokens / entity) | tree-group saving vs flat | vs relative-flat | variant band |
|---|---|---|---|---|---|
| refmatrix | 199 | 63.9 → 56.9 → 53.2 → 54.8 | 16.7% | 6.5% | 10–25% |
| cliquedb | 199 | 61.2 → 53.3 → 49.8 → 51.2 | 18.7% | 6.5% | 10–25% |
| viascope | 200 | 56.6 → 47.7 → 39.0 → 39.8 | 31.0% | 18.2% | ≥ 25% |
| cliquet | 160 | 57.4 → 50.4 → 47.2 → 48.9 | 17.9% | 6.4% | 10–25% |
| orderly | 43 | 47.7 → 38.4 → 37.6 → 39.1 | 21.2% | 2.3% | 10–25% |
| atldb | 200 | 47.8 → 42.1 → 34.2 → 34.4 | 28.6% | 18.9% | ≥ 25% |

{#m4-variant}

**Band.** On the measurement as defined (real prompts, refmatrix), the saving is 3.4%, which is
< 10%: **keep flat; render-only work stops.** The tree also saves LESS than simply printing
root-relative paths (3.9%).

The concept-anchor variant lands at 10–25% (opt-in) in four stores and ≥ 25% in viascope and
atldb. Measured against relative-flat, though, the tree adds only 2–7% in four stores, and 18–19%
in the two deep-directory stores (viascope, atldb). {#m4-band}

**Associative power.** Rendering decides how many associated entities fit in a fixed budget. The
estimates below are tokens/entity ratios, not a re-run of the budget fill:
- **Real prompt bundles:** the tree fits 3.5% more entities and relative paths fit 4.0% more.
  These bundles are dominated by snippets and memory bodies, not location lines.
- **Graph-neighbour bundles:** the tree fits 20–45% more, and relative paths alone fit 12–24%
  more. Only viascope and atldb gain materially beyond relative paths.

So the cheap A fix captures the render gain for what agents actually receive. A tree render buys
associative capacity only for neighbour lists in deep-tree stores. {#m4-assoc}

## M5: subject representation per store {#m5}

**Method.** Two steps:
- **Modularity.** Louvain modularity was RE-MEASURED on today's copies with the 2026-10-07
  `measure.py`, unchanged and with its own seed (20261007). The entity projection is built over
  non-hub concepts with 2 ≤ df ≤ p99.
- **Label quality.** Task 19.0's hygiene rules were applied mechanically to each store's
  memory-compile `subject_*` entities, in both the code and session partitions. Each label falls
  into one class:
  - **unlabeled:** `subject_unlabeled_N`;
  - **junk:** every token is in `scan._PROMPT_STOPWORDS`, ≤ 2 chars, or a stdlib head;
  - **generic:** one content token, e.g. `subject_id`, `subject_bbox`;
  - **descriptive:** ≥ 2 content tokens.

| store | entities | modularity 2026-10-07 | modularity now (communities) | subjects | label classes | subject members | band |
|---|---|---|---|---|---|---|---|
| refmatrix | 10,985 | 0.22 | 0.15 (488) | 71 | descriptive 7, generic 43, junk 5, unlabeled 16 | 225 | < 0.30: no subject tree |
| cliquedb | 10,248 | 0.12 | 0.12 (194) | 6 | descriptive 6 | 5 | < 0.30: no subject tree |
| viascope | 13,559 | 0.45 | 0.45 (337) | 4 | generic 4 | 35 | ≥ 0.40: admit |
| cliquet | 2,357 | 0.14 | 0.14 (22) | 1 | generic 1 | 1 | < 0.30: no subject tree |
| orderly | 486 | 0.26 | 0.26 (9) | 0 | — | 0 | < 0.30: no subject tree |
| atldb | 1,241 | 0.43 | 0.33 (229) | 4 | descriptive 1, generic 2, junk 1 | 19 | 0.30–0.40: label quality first |

{#m5-table}

**Band.**
- **viascope (0.45)** is the only store ≥ 0.40, so it would admit a `subject` representation.
  But its four subjects are all generic single-token labels (`bbox`, `area`, `aid`) covering 35
  members. The partition exists in principle, and the labels to name it do not exist yet.
- **atldb fell from 0.43 to 0.33** as the store grew (544 to 1,241 entities), into the 0.30–0.40
  band. Label quality decides there. Its four labels are generic, junk or descriptive
  (`subject_name`, `subject_id`, `subject_events`, `subject_events_coalesced`), which fails. **No
  subject tree** until 19.0's hygiene and the compile labels improve.
- **refmatrix (0.22 to 0.15), cliquedb, cliquet and orderly** are all < 0.30: no subject tree.
  refmatrix carries 71 subjects, but 64 of them are generic, junk or unlabeled.

{#m5-band}

**Associative power.** The weak-community result from 2026-10-07 got WEAKER as the stores grew.
- **Communities.** refmatrix's modularity fell by a third, and atldb lost its community
  structure. Associations increasingly cut across any partition of the corpus. A subject
  hierarchy would split association neighbourhoods in 5 of 6 stores.
- **Subjects as concepts.** Where subjects exist, they are useful as CONCEPTS: one more hyperedge
  the graph can walk. They are not useful as a tree that scopes anything.
- **Viascope.** A real community partition there could add a "same community" association
  signal, once its labels are fit to show.

{#m5-assoc}

## M6: write cost of placements {#m6}

**Method (deviation, as instructed).** The doc says "through the daemon". This run used a
throwaway copy with NO daemon, and called the production per-file re-sync entry point
in-process: `refmatrix.sync.sync_files(store, [file], root, semantic=False)`, the function the
watcher and `_op_sync_files` call. The daemon's socket, lock and snapshot costs fall on the
ingest side only, so leaving them out makes the placement RATIO conservative (larger).

Each sampled file was set up for a real re-ingest:
- `tracked_files.mtime := -1`, to defeat the mtime gate;
- the GMD content hash dropped, to defeat the resume skip.

For each file:
- **t_ingest** is the production re-sync.
- **t_place** derives the file's placement rows (`fs` dir ▸ file, `gmd` heading tree, `code`
  module ▸ class ▸ def), then deletes the previous version and inserts the new one in ONE
  transaction, as one batched insert.

Two write modes were run, `fused` (same connection, right after ingest) and `separate`, each
quiet and loaded. Load is `os.cpu_count()` busy-loop processes. The other spike scripts were
also running during the quiet arms, so "quiet" is not idle. The table reports the WORSE arm.

| store | files | rows / file (mean) | p95 t_ingest ms | p50 / p95 t_place ms | p95 t_place ÷ p95 t_ingest | per-file ratio p95 | Σ t_place ÷ Σ t_ingest | band |
|---|---|---|---|---|---|---|---|---|
| cliquedb | 100 | 15.2 | 15,408 | 9.4 / 55.9 | 0.36% | 22.1% | 0.48% | < 5%: inline |
| cliquet | 61 | 29.0 | 20,833 | 11.8 / 69.1 | 0.33% | 14.3% | 0.51% | < 5%: inline |
| orderly | 51 | 9.2 | 2,410 | 9.4 / 31.2 | 1.30% | 38.5% | 1.35% | < 5%: inline |
| atldb | 100 | 2.6 | 1,700 | 6.7 / 13.7 | 0.81% | 31.6% | 1.59% | < 5%: inline |
| viascope | — | — | — | — | — | — | — | NOT FINISHED at report time |
| refmatrix | — | — | — | — | — | — | — | NOT FINISHED at report time |

{#m6-table}

**Band.** Placement adds 6–70 ms at p95 against a p95 re-sync of 1.7–21 s: 0.3–1.3%, so the band
is **< 5%: inline** in all four finished stores. When the run was handed back, the viascope and
refmatrix runs were still going under the same script. Their `results/m6_<store>.json` will land
there, and they are NOT reported here. {#m6-band}

**The per-file reading differs.** Taken file by file, the p95 of t_place/t_ingest is 14–39%,
which is > 20% in three stores. The cause is small files that re-sync in ~15–50 ms, where a 5–10
ms write is a large share. The cost is a fixed per-transaction write, not row volume
(2.6–29 rows per file). Inline maintenance is therefore safe in aggregate. For small files,
placement writes should batch into the same transaction as the entity writes (the `fused` mode),
not run as a separate one. {#m6-per-file}

**Associative power.** Keeping containment associations current is cheap: under 2% of the sync
work in aggregate. Cost does not argue against B's placements. Their value is a question for M1
and M2, not M6. {#m6-assoc}

## M7: order at sentence (`sid`) grain {#m7}

**Method.** The stores hold no sentence layer, and ADR-0004's `sid` space does not exist yet. So
the script approximates one from each store's code-partition doc and code files, read read-only
from the live trees:
- **Splitting.** Files are split in Dewey order: file ▸ section (markdown headings, or top-level
  def/class/CREATE) ▸ paragraph ▸ sentence. Sentences use the loc-coloc splitter, so each code
  line is a sentence.
- **Terms.** Terms come from the production keyword tokenizer (`ingest._WORD_RE` minus
  `_DOCSTRING_STOP`) plus bi- and trigrams, kept only if the term is a `mentions` concept of the
  store.
- **Bitmaps.** Per-term 32-bit roaring bitmaps, `run_optimize`, then serialized bytes.
- **Numberings compared:**
  - Dewey order;
  - random order;
  - files in path order with random order inside each file;
  - random file order with document order inside each file.

| store | files | sentences | terms | postings | 64K chunks | Dewey bytes | random bytes | Dewey saving | path-ordered files, random inside | random files, doc order inside | band |
|---|---|---|---|---|---|---|---|---|---|---|---|
| refmatrix | 1,023 | 277,618 | 19,747 | 1,287,213 | 5 | 3,159,544 | 3,237,802 | 2.42% | 2.23% | 1.43% | 2–10% |
| cliquedb | 723 | 252,017 | 14,277 | 1,282,936 | 4 | 2,936,724 | 3,012,372 | 2.51% | 2.46% | 0.97% | 2–10% |
| viascope | 2,021 | 485,224 | 12,308 | 1,335,543 | 8 | 3,124,794 | 3,354,574 | 6.85% | 6.00% | 3.83% | 2–10% |
| cliquet | 77 | 26,148 | 5,279 | 143,696 | 1 | 371,071 | 371,856 | 0.21% | 0.01% | 0.21% | < 2% |
| orderly | 52 | 7,219 | 3,411 | 27,206 | 1 | 108,894 | 108,988 | 0.09% | 0.00% | 0.09% | < 2% |
| atldb | 365 | 129,540 | 4,268 | 296,115 | 2 | 673,703 | 681,924 | 1.21% | 0.75% | 1.21% | < 2% |

{#m7-table}

The Dewey saving by df band (hapax / 2–10 / 11–100 / > 100) is:
- refmatrix 0 / 11.5 / 5.4 / 0.4%;
- cliquedb 0 / 17.0 / 4.1 / 0.9%;
- viascope 0 / 25.2 / 16.5 / 2.4%;
- atldb 0 / 6.4 / 0.7 / 0.8%;
- cliquet and orderly ≤ 0.4% in every band.

Run containers are 0.1–0.5% of containers under Dewey order, and 0 under random. {#m7-split}

**Band.**
- **refmatrix, cliquedb and viascope** fall in 2–10%: order at compaction only.
- **cliquet, orderly and atldb** fall below 2%: order is irrelevant.
- **No store reaches 10%.** Paths stay columns. Dewey order is at most a compaction-time tweak
  for the larger stores.

{#m7-band}

**Associative power.** A term's sentence occurrences do not form contiguous runs, so sentence
order holds almost no local association:
- Nearly all of the saving survives shuffling the sentences inside each file (refmatrix 2.23 of
  2.42 points, viascope 6.00 of 6.85). The gain is a term concentrating in a few files, whose
  sentences share a 65,536-id chunk.
- The entity-level bitmaps already hold that.
- Within-file sentence order adds 0.05–0.85 points.

Association in refmatrix is co-occurrence WITHIN a unit (the sentence co-location win), not
adjacency ALONG an order. {#m7-assoc}

## Associative-power reading {#associative-power}

The user's goal is to maximise associative power: rmx's internal structures should surface as
much as possible of what else bears on a thing. Read that way, the seven results agree:

1. **Association is cross-cutting.** Most strong associates sit in another subtree (M1:
   50–69%), and promoting the subtree loses relevant hits (M3). Community structure is weak and
   weakening (M5). The incidence graph (concept bitmaps, BM25 + dense + co-location) is the
   structure that reaches them. It stays authoritative and unscoped.
2. **Association is local WITHIN a file and a unit, not along an order.** Same-file pairs carry
   2–27× association lift (M1), and sentence co-location already won (loc-coloc). But terms do not
   run contiguously in Dewey order (M7). The associative signal is co-occurrence inside a
   container. Adjacency in an id order adds nothing.
3. **Containment structure is for ADDRESSING.** The demand is within-file address lookup (M2:
   53% and 94% of queries), and it is cheap to maintain inline (M6). A `gmd`/`code` placement
   index makes "where in this file" cheaper. It does not add associations, though, and the doc's
   LCA-proximity band is not earned (M1 < 25%). One open question: whether same-file proximity
   helps as a bounded ranking FEATURE, not as scoping. No measurement here tests that.
4. **Rendering capacity is a path-string problem before it is a tree problem.** For real
   prompts, relative paths fit as many associated entities as a tree does (M4).

{#associative-power-body}

## What this does not settle {#not-settled}

- **M1's pairwise lift has not been tested as a ranking feature.** Same-file and same-section
  proximity carries association lift, but no pre-registered measurement tested it as a ranking
  feature. M3 tested only subtree PROMOTION, which loses. A bounded same-file proximity feature
  added to `content_rank` would be a new measurement, not a reading of these bands.
- **M2 is a two-store result.** Four stores logged too few queries in 30 days, and the built-in
  Grep tool is invisible to `cli.log`.
- **M7 approximates the `sid` layer.** Real ADR-0004 `sid` numbering may differ.
- **M6 ran without a daemon.** It measured an in-process re-ingest on a copy, as instructed, not
  "through the daemon".

{#not-settled-body}
