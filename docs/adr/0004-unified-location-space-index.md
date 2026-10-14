---
gmd: "0.1"
id: refmatrix/adr-0004-unified-location-space-index
title: "ADR-0004: One location space — hierarchical ids, tiered bitmaps, and the helix on top"
tags: [adr, helix, bitmaps, retrieval, storage, co-location]
---

# ADR-0004: One location space for every search mechanism {#root}

**Status:** Proposed · **Date:** 2026-10-06 · **Implementation:** none yet — evidence spike only
(`eval/spikes/2026-10-06-loc-coloc/`); production work gated on a pre-written plan

rel: amends -> [[project_stm_ltm_helix_design]]
rel: supersedes -> [[project_helix_phase2_storage_fork]]
rel: supersedes -> [[plan-11-helix-phase2-versioned-graph]]
rel: derives-from -> [[spike-2026-10-06-loc-coloc]]
rel: depends-on -> [[project_retrieval_negatives_2026_09]]
rel: related-to -> [[project_concept_path_negatives_0903]]
rel: related-to -> [[project_cliquedb_baseline_post_rederive]]
rel: part-of -> [[adr-0000-adr-overview]]

## Context {#context}

refmatrix answers "what is relevant to this" through three index views over one entity table,
each keyed differently: {#context-lead}

- **Bitmaps** — one roaring `BitMap64` per (partition, linkage), bit `concept<<32 | entity`.
  Presence only; no weight, no time.
- **SQL weights** — `entity_links(entity, linkage, concept, weight)`; `mentions.weight` is the
  term frequency BM25 reads. 772k more rows of `linkage_evidence` carry `(file, line, span)`.
- **Dense** — Lance datasets per (partition, kind) keyed by entity id; the embedded text is
  `name + tldr` for docs, code and anchors.

Time lives in four unjoined places (row timestamps, STM JSON, `helix.log`, `facts.log`); edges
carry none. The concept namespace mixes ~59k body terms, ~29k `phrase/*` pairs, ~4.6k GMD
anchors and title tokens under one df statistic. Helix phase 2 stalled on a storage fork —
mutable edge-time columns vs a versioned store — chosen before anyone asked whether the index
shape itself was right. {#context-time}

The 2026-10-06 spike measured the one thing that shape cannot express — **where inside a
document the query terms occur together** — and it is the largest ranking gain this project has
confirmed on held-out data (see [[#evidence]]).

## Decision {#decision}

### Four primitives {#primitives}

1. **Location space.** Every unit of text (section, paragraph, sentence; for code file ▸ class
   ▸ def ▸ block) has a u64 location id. An entity is a location with a zero suffix. {#p-loc}
2. **Term space.** A term dictionary plus an alias map (a router, as intropretor's `StemNode`),
   separate from entities. Replaces ~36k `same_as` rows and the `phrase/*` concepts. {#p-term}
3. **Tiered bitmap.** One mechanism for weight tiers (tf ≥1, ≥2, ≥4 …), age tiers (day / week /
   month / older) and session tiers. pyroaring has no bit-sliced index; log tiers are the
   BSI-lite this project can build. Stored as per-key blobs (the `pair_index` pattern). {#p-tier}
4. **Snapshot manifest.** A content-hashed list of tier blobs. "The graph as of X", A/B slot
   reconciliation and replica merge all become a manifest diff. This replaces the phase-2
   fork: age tiers give phase-3 recency cheaply, manifests give history. {#p-manifest}

### Two-tier location ids {#two-tier-ids}

Positional ids shift on every edit, which would reset helix history. So:

- **External id** `entity(32) | sid(32)` — allocated once per unit, never reused. Every bitmap,
  tier, vector, typed edge and graduation record keys on it.
- **Local ref** — the Dewey position `section | paragraph | sentence`, rebuilt per ingest in a
  per-document map `sid ↔ dewey (+ line, span)`. Containment, range masks (`lead`, title) and
  decoration (`file:line`) go through it.
- **Edit alignment** at re-ingest: unchanged units keep their sid (hash match), edited-but-similar
  keep it with a version bump, new units take the next sid, removed units are tombstoned in the
  manifest. Optional compaction at a snapshot boundary renumbers sids into document order.

One interning mechanism serves terms, entities and locations (intropretor `concept_id_map`
shape). {#two-tier-ids-interning}

### Layers over the location space {#layers}

| layer | key | status |
|---|---|---|
| L0 incidence | term → sids (tf tiers) | exists as `mentions`, at entity granularity |
| L1 co-location / containment | sentence projection per term; containment from Dewey ranges | **measured win** ([[#evidence]]) |
| L2 term adjacency | term → term, left/right within a window, lift-gated | untested as a layer |
| L3 promoted concepts | term set → concept (subsumption, cycles, Apriori, memory compile) | offline pieces exist |
| L4 typed edges | keyed by SOURCE location (a `calls` edge starts at its call site) | exists entity-keyed |
| L5 time | age tiers per layer + manifests | missing |
| dense | Lance vectors keyed by sid (sentence/paragraph chunks) | exists entity-keyed |

**Containment is a relation family**: structural (doc/loc ⊃ term), sequential (left ⊃ right of
a pair), emergent (a cycle ⊃ its members), statistical (subsumption: `P(A|B) ≥ 0.8`,
`P(B|A) < 0.5`, lift-gated). Each source is a SEPARATE bitmap per direction, written in one
manifest so the two directions cannot disagree. The location→location pair is a materialized
view of the Dewey ranges, never authoritative. {#containment}

### Query pipeline {#pipeline}

1. **Resolve terms** — shared stoplist (`terms.STOPWORDS`), alias map, phrase detection via L2 lift.
2. **Recall** — L0 ∪ dense (∪ typed expansion, per relation type and depth, ONLY where measured).
3. **Rank** — `BM25_norm + 2.0 × sentence_coloc` (measured; [[#evidence]]), where
   `sentence_coloc(d) = max over sentences of Σ w(t) for distinct query terms t present / Σ w(all)`
   and `w(t) = idf(t) × burstiness(t)` (`burstiness = Σtf / df`, mean tf where present).
4. **Admission for subgraph work** — lift/NPMI against the CURRENT accumulated set, support
   `B_S` = locations holding ≥k of S's members (never the union), support as a gate never a
   multiplier, a top-b budget per step. Cycles in the admitted subgraph become transient
   concepts that group results; recurrence + use across sessions graduates them to L3.
5. **Cross-encoder rerank, then decorate** the final k only, from the `sid → line, span` map.
6. **Full path trace** per result (features, terms, edges, sid ranges, cycle id) — always in
   eval, opt-in on the CLI/MCP.

A **confidence cascade** (BM25 top1/top2 ratio above θ skips every later stage) is adopted as a
LATENCY device only: at θ 1.25 it would let ~87% of near-verbatim and ~46% of prose queries skip
co-location, expansion and the cross-encoder. Measured with full bodies, it never improves
accuracy. {#cascade}

## Evidence {#evidence}

Spike: [[spike-2026-10-06-loc-coloc]]. Read-only, on copies of store replicas, re-ranking
production `content_rank`'s top 50. {#evidence-lead}

| set | base MRR | + 2.0 × sentence co-location | won / lost |
|---|---|---|---|
| cliquedb `lines` (n=288, near-verbatim) | 0.921 | **0.959** (hit@1 0.889 → 0.951) | +19 / −1 |
| cliquedb `merge` (n=288, terms spread across the doc) | 0.746 | **0.793** | +42 / −10 |
| MemAware test-720 (never used for tuning) | 0.185 | **0.211** (hit@20 0.403 → 0.438) | +134 / −69 |

- Sentence and paragraph co-location are redundant: once sentence weight is ~2, paragraph adds
  nothing; the split is not identifiable (tuning and test sets disagree on it). **Store the
  sentence projection only.** {#ev-sentence}
- Sentence distance beats token distance on every set → the Dewey sentence suffix is enough; no
  token positions in the id. {#ev-granularity}
- **Rejected:** feeding lift-admitted terms back into BM25 as query expansion (never won a
  query, lost 4–26 of 37 — the PRF shape of [[project_retrieval_negatives_2026_09]]); unbounded
  same-sentence sums (length-biased); top-1 confidence gates and a margin rule as accuracy
  protection. {#ev-negatives}
- **The artifact that inverted a conclusion:** with `tldr` text the same feature LOST 40 of 288
  near-verbatim lookups; reading full section bodies turned it into +19/−1. `tldr` is truncated
  at 500 chars ([[bug_registry]] bug-075). The design keys on full-body locations; any
  implementation that falls back to `tldr` reproduces the loss. {#ev-artifact}

## Consequences {#consequences}

- **Absorbed structures** (on implementation): `bitmap_fragments` → per-term sid bitmaps (the
  entity projection IS today's `mentions`); `entity_links.weight` → weight tiers;
  `linkage_evidence` → the sid map; `pair_index` → L2; `same_as` → alias map; `phrase/*` →
  deleted; `lead`/title tokens → range masks; coref → antecedent term at the pronoun's sid;
  STM focus recency → session tiers; `helix.log`/`facts.log` → manifests + a delta log;
  memory-compile subjects and graduated cycles → one L3 mechanism. `pagerank` stays a scalar.
- **Scope is the storage core.** Ingest, `content_rank`, context, scan-prompt, recall, daemon
  ops, replica rotation and the hub all read today's tables. Build the location index as a NEW
  derived layer beside them (strangler); the old path stays authoritative until evals win.
- **The helix half does not need the location space.** Age tiers and manifests can key on
  today's `(concept, entity)` packing and ship first — it is the on-mission half
  ([[project_refmatrix_mission_charter]]).
- **Cheapest production win first:** sentence co-location as a re-rank stage over
  `content_rank`, computed from full section bodies, before any storage change.

## intropretor audit {#intropretor}

intropretor (`~/github/atollogy/bdep/intropretor/src/intropretor/`) was an earlier "active
semantic graph" whose unported modules overlap this design. It had 193 unit tests but **no eval
harness**, and several modules were never wired into its own pipeline: `DecaySweep`,
`Broadcaster`, `BitmapIndex.recompute_dirty`, `LSDB.freeze` and `VirtualLink.record_hit` have
no callers outside their own modules and tests. Nothing ports on evidence; four ideas are
adopted on fit. {#intropretor-lead}

| verdict | module | how it lands here |
|---|---|---|
| PORT | `temporal/clock.py` | injectable clock + `FakeClock`, so age-tier tests are deterministic |
| ADAPT | `temporal/decay.py` (`max(floor(s*0.9), max(peak//3, 1))` once unreinforced >24h) | **age-tier floor**: tier comes from `now − last_reinforced_at`, but never drops below the tier implied by `peak`. Costs one extra stored scalar per key. 0.9 and 24h were never tuned; they are starting points only. |
| ADAPT | `decay.anchor_exempt_predicate` | protected entities and GMD anchors are exempt from age-tier demotion |
| ADAPT | `graph/stem_node.py` | becomes the alias map ([[#p-term]]), not a traversal node; drop its walk-budget rule (only traversed when ≥3 TTL remain) |
| ADAPT | `graph/conceptual_linkage.py` + `propagation/loop_registry.py` | keep the record shape (count, peak, `last_reinforced_at`, fire at a threshold) as the **graduation ledger**. Its identity (the exact path tuple) is unusable: identity here is member-set Jaccard, and recurrence counts distinct sessions, not hits. |
| ADAPT | `topology/concept_id_map.py` | monotonic, never-reused interning with NUL-prefixed namespaces, so terms, entities and sids share one interner ([[#two-tier-ids-interning]]). It has no Dewey or edit-alignment story. |
| ADAPT (idea) | `topology/lsdb.py` dirty set | a per-write set of dirty keys tells you which tier blobs to rebuild and which manifest entries change. This is the delta log. |
| SKIP | `topology/snapshot.py` | copies every link by value on each freeze (O(edges)), uses a plain counter version, and cannot be diffed or persisted. Content-hashed manifests are strictly better. |
| SKIP | `topology/bitmap_index.py` + `propagation/explorer.py`, `broadcaster.py` | precomputed BFS reach at depths 1–5; the explorer counts any non-empty AND as an "aha", with no lift or support gate, and picks depth from how many terms the payload has, not from relevance. Same shape as the measured-negative degree-2 walk and PPR; lift-gated top-b admission ([[#pipeline]]) replaces it. |
| SKIP | `virtual_link`, `spanning_tree`, `word_node`, `document_node`, `vr_node`, `ctst/` | never used, superseded by the location space and L2, a memory-only optimisation, or (ctst) already measured as null |

"Used", the graduation signal, has no intropretor precedent. `record_access` existed but was
never called, so that open question stays open. {#intropretor-used}

## Amendment 2026-10-07: the relation taxonomy, proximity tiers, and two storage devices {#amend-2026-10-07}

**Source:** the user's notes in `docs/ideas.txt` (untracked), reviewed against this ADR on
2026-10-07. The user said to fold the review in as an amendment. Two ideas from Aster (NTU,
SIGMOD 2025, `github.com/NTU-Siqiang-Group/Aster`, GPL-2.0, so ideas only and never code) are
folded in at the user's direction on the same day. Status stays **Proposed**; this amendment
records the design, not an implementation. {#amend-source}

rel: derives-from -> [[project_apriori_concept_discovery]]
rel: derives-from -> [[project_phrase_layer_closed]]
rel: derives-from -> [[project_sentence_coloc_measured]]
rel: depends-on -> [[project_ppr_degree_walk_shipped]]

### The model: a weighted multilayer multidigraph {#amend-model}

The graph this ADR stores is a **weighted multilayer multidigraph**. Each relation type is a
layer (L0–L5), and each edge carries a **discrete** weight: membership in a weight-tier bitmap
(tf ≥1, ≥2, ≥4 …). Each type may also carry one scalar prior (a per-type weight). The prior is a
small table, not a bitmap, and starts at 1.0 for every type until a per-type evaluation sets it.
Discreteness is the point: "edges of strength ≥ t" is the OR of the tier bitmaps from t up, which
is a query on roaring bitmaps with no sort. {#amend-model-body}

### The taxonomy in ideas.txt, mapped onto the layers {#amend-taxonomy}

| ideas.txt relation | layer / mechanism here | storage |
|---|---|---|
| incident → container (left) / contained (right) | the **sequential** containment source (left ⊃ right of a pair) | one bitmap per direction, one manifest |
| incidence → concurrent / composite (edge) | **L1 co-location**: terms in the same unit (the sentence co-location re-rank is the measured win) | sentence projection per term |
| co-incident → contextual adjacency / association (proximity) | **L2 term adjacency** within a window, lift-gated | `pair_index` per-key blobs, per direction |
| term adjacencies, in-path / out-path | the two direction bitmaps of L2 | as above |
| skip-node | skip-gram pairs (the staged cascade, `project_apriori_concept_discovery`) | L2 with a gap parameter |
| adjacency pairs / triples / quads | pairs = L2; triples and above = **L3 promoted concepts** | pairs stored; higher orders PROMOTED, never materialized |
| doc as subgraph (implicit link for PageRank) | the doc is a location whose Dewey range contains its sections and sentences | `pagerank` stays a scalar |
| term counts | L0 tf tiers | weight-tier bitmaps |
| degree 1 / 2 / 3 | typed expansion depth ([[#q-expansion]]) | none new |
| path tracing, cycle scoring, order by cumulative weight | admission (pipeline step 4), cycles as transient → L3 concepts, full path trace (step 6). Cumulative-weight order is approximated by walking tiers from the top down | none new |
| lift / PMI | the admission gate: **NPMI** with support as a gate | computed, not stored |

{#amend-taxonomy-body}

### Two additions {#amend-additions}

1. **Proximity tiers.** "Contextual adjacency" is a distance dial: same sentence < same paragraph
   < same section < same doc < same directory. This becomes a **tier family**, like weight, age and
   session tiers. A bitmap per distance band answers "co-located within distance ≤ d" as an OR of
   bands, and it unifies L1 (sentence co-location) and L2 (window adjacency) as two settings of one
   dial. {#amend-proximity}
2. **Directory and extension facets.** A directory is one more containment level above the doc: a
   path-prefix level in the location id, so `dir ⊃ doc ⊃ section ⊃ sentence`. The doc's subtype
   (extension, `kind`) is a **facet bitmap** per value. That covers "doc as container (bag) with
   subtype (extension), contained in a directory" without a new relation type. {#amend-facets}

### Two storage devices, from Aster {#amend-aster}

1. **Decaying approximate counters for touch counts.** These are Morris counters or a Count-Min
   sketch, with periodic decay. A touch, recall or edge use increments a few bytes in memory, and a
   snapshot tick flushes them into the **age tiers** and into plan-19's memory-usage scores. The
   point is to stop paying a write per event: bug-085 was the per-event-write failure on the Lance
   side, and grep-learning's `query/*` accretion is the same pattern on the catalog side. The count
   is approximate by design; it feeds tiers and ranks, never a correctness decision. {#amend-counters}

   **Decay never loses knowledge** (user, 2026-10-07: "decay is fine but losing knowledge is bad").
   Every counter obeys these constraints: {#amend-counter-rules}

   1. **Two records per key, only one of which decays.** The *lifetime* record is exact and never
      decays: `first_seen`, `last_seen`, `lifetime_count`. The *recency* score is the decaying one
      (approximate allowed). Decay parameters can then change, and the score can be recomputed,
      without losing anything. {#rule-two-records}
   2. **A floor, never zero.** The decayed score never falls below a floor that grows with the
      lifetime evidence. Knowledge that was used heavily long ago stays findable, ranked below
      current work but present. **The one implementation is task 19.2's decay/floor library**
      (plan review C4, user 2026-10-07): half-life recency over an exact lifetime record, with
      floor `base * (1 + log1p(hits + 2*used))` — never zero, applied at read time over raw counts
      ([[#a14-floor]], amended 2026-10-14). Helix's age tiers and touch counters reuse it rather
      than defining a second formula. The intropretor step decay in the ADAPT row above is prior
      art, not a rule. {#rule-floor}
   3. **Age tiers are terminal, not evicting.** An edge moves day → week → month → older; "older" is
      the last tier, and nothing ages out of the index. {#rule-terminal-tier}
   4. **Decay demotes, never deletes.** A cold counter may change ranking, the inline placement in
      `MEMORY.md` (plan-19's fold) or a merge preference. It may never trigger a forget, cull or
      prune. Removal goes only through the ONE explicit, audited path,
      [[plan-22-audited-removal-and-repair]], which repairs before it removes (dry-run → apply,
      manifest, restore). That includes merges, using plan-20's rule (task 22.4). A folded memory
      stays recallable (plan review C1/C3, user 2026-10-07). Scoped 2026-10-14
      ([[#a14-removal-scope]]): `forget`/`memory bulk-forget` are entry points to that path;
      manifest-backed derived-index cleanup and the listed `untrack`/`prune-noise --drop`
      exceptions are not knowledge removal. {#rule-no-delete}
   5. **A higher floor for asserted knowledge.** Feedback memories, user-asserted or `protected`
      rows, and `rel:`-anchored GMD nodes keep a higher floor; recency may reorder them, never bury
      them. This defines the FLOOR only; `MEMORY.md`'s fold order is a separate tier
      ([[#a14-fold-order]], 2026-10-14). {#rule-asserted-floor}
   6. **Never under-count.** Where a sketch is used, use one whose error is one-sided upward
      (Count-Min with conservative update), so error can only make a key look warmer, never falsely
      cold. Small domains (≈500 memories) use EXACT counters: the sketch exists for edge-scale
      domains only. {#rule-no-undercount}
2. **Choose eager vs lazy merge per key, with a cost model.** Aster's `AdaptPolicy` compares a
   key's write cost with its read cost and picks per key: rewrite the full adjacency (eager), or
   append a merge delta (lazy).
   - Write cost: degree × LSM write amplification ÷ block size.
   - Read cost: cache-miss rate × average degree × lookup/update ratio.

   Here the keys are the per-term tier blobs plus the manifest's delta log. Read-hot keys (often
   queried, rarely written) are kept merged. Write-hot keys (e.g. grep-learned `query/*`: 747 of
   868 protected rows have df ≤ 1) stay as deltas until compaction, which is plan-17's nightly
   tick. The counters from device 1 supply the read/write ratios. {#amend-adapt}

### Gates the evidence imposes on these ideas {#amend-gates}

- **Traversal depth and cumulative-weight ordering are opt-in per relation type, after
  measurement.** A global degree-2 walk measured **5× worse**, and seeded-PPR degree measured flat
  ("mechanism needs typed edges"). Each type × depth earns its place on the evaluation grid
  ([[#q-expansion]]). {#gate-depth}
- **Higher-order n-grams are promoted, not stored.** The phrase layer grew concepts from 42k to
  549k with **zero** hit@20 gain. Triples and quads enter only as L3 promotions that recur and are
  used. {#gate-ngrams}
- **PMI/lift is a gate, never a ranking score.** As a ranker, lift scored MRR 0.007 against
  PPR's 0.069. Use NPMI (bounded) with a support floor. {#gate-pmi}
- **The per-type prior starts flat (1.0)** and moves only on a per-type evaluation, so a
  hand-set weight cannot become an untested ranking change. {#gate-prior}

### Evidence: the shape of the adjacencies, six stores (2026-10-07) {#amend-shape}

rel: derives-from -> [[spike-2026-10-07-adjacency-shape]]

The user asked whether the adjacency network has an intrinsic shape worth leveraging, and asked for
more than one project. The term → location incidence layer (`mentions`) was measured on catalog
copies of refmatrix, cliquedb, viascope, cliquet, orderly and atldb. Full table:
[[spike-2026-10-07-adjacency-shape#results-table]]. {#shape-lead}

| finding | evidence | consequence for this ADR |
|---|---|---|
| **heavy-tailed degree** | tail α 1.72–1.88 in the four large stores (KS ≤ 0.039); top 1% of concepts hold 21–31% of edges; 30–47% of concepts are hapax | Hubs and tail get different handling. Hubs are mostly generic words (`one`, `only`, `every`, `plan`, viascope's `keyword/*`): a **stoplist/hub-damping** signal, not structure. Hapax rows feed **promotion or cull**, never co-occurrence evidence. Aster's per-key merge choice is driven by exactly this degree distribution. |
| **small world, NOT mainly through hubs** | 2-hop reach 56–92% of entities in the large stores; dropping the top 1% hubs barely changes it in 4 of 6 (e.g. cliquet 0.92→0.92); 1-hop reach does drop (refmatrix 0.25→0.10) | Explains the walk negatives better than the hub story: mid-degree concepts alone saturate two hops. **Hub exclusion cannot rescue a global walk.** Typed, lift/NPMI-gated, budgeted admission (pipeline step 4) is the only expansion this graph supports, and [[#gate-depth]] stands. |
| **weak communities except in two stores** | Louvain modularity 0.12–0.26 for four stores, 0.43–0.45 for viascope and atldb | Community blocks are a per-store property. Do not design storage or ranking around them globally. Where strong (viascope), they are candidates for L3 subjects. |
| **compression is about DENSE ids, not ORDER** | dense entity renumbering saves 15–42% of bitmap bytes in the large stores; path-locality or community order vs random saves < 0.75% everywhere | Partition-local **dense** ids are a real storage win. The claim that Dewey/locality ORDER buys run containers is **not supported at entity granularity**: one store's entities fit in one 65,536-id chunk, where array containers cost the same in any order. It remains untested at `sid` granularity, so measure it before relying on it there. |

{#shape-table}

**Corrections to earlier reasoning:**
- (1) "walks failed because hubs put everything within two hops" was half right; see the second
  row.
- (2) "Dewey order → run containers → cheaper bitmaps" is unsupported at entity granularity; see
  the fourth row.

Both claims were stated before this spike and are corrected by it. {#shape-corrections}

### Helix fit {#amend-helix}

Age tiers apply to EVERY layer above. So each relation type, proximity band and facet gets "when"
for free, snapshot manifests give "as of", and the path trace can report that a path existed at an
earlier snapshot. Cycle graduation across sessions is a helix feature as well. The decaying
counters (device 1) are the cheap source of the age and touch signal that phase 1 could not log
without a write per event. {#amend-helix-body}

## Decision log {#decision-log}

- **2026-10-07 (user):** "helix's design supersedes plan 11's". This ADR's helix half governs
  helix phase 2, and plan-11 (the prolly/Merkle versioned edge store) is `superseded`. The half in
  question: snapshot manifests, age tiers on the tiered bitmaps, and the term-space alias map. The
  ADR as a whole stays **Proposed**, because the location-id and query-pipeline halves are not
  decided. Consequence for concept work: merges target the term-space alias map
  ([[exploration-concept-similarity-cull-merge]] d-1), not new `same_as` rows. {#d-2026-10-07}
- **2026-10-07 (user): amendment folded in** ([[#amend-2026-10-07]]). It covers: the `docs/ideas.txt`
  relation taxonomy mapped onto L0–L3; proximity tiers as a tier family; directory/extension facets;
  Aster's decaying approximate counters and per-key eager/lazy merge; and the gates prior
  measurements impose. The ADR stays Proposed. {#d-2026-10-07-amend}

## Amendment 2026-10-14 (APPROVED by the user, 2026-10-14) {#amend-2026-10-14}

Decision d9i of [[plan-review-2026-10-14#t9]]. Drafted from the Wave 0 spec reviews; nothing below
was in force until the user approved it (2026-10-14, "1 - yes"); [[#rule-floor]],
[[#rule-no-delete]] and [[#rule-asserted-floor]] are edited to match.

rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: amends -> [[#rule-floor]]
rel: amends -> [[#rule-no-delete]]

1. **The floor formula is never zero.** [[#rule-floor]]'s `base * log1p(hits + 2*used)` is 0 for a
   memory that has never been recalled, which contradicts "a floor, never zero" and made the
   never-recalled memories fold first (plan-19 review #b-4). The formula becomes
   `base * (1 + log1p(hits + 2*used))`. Task 19.2 stores the raw per-evidence counts and applies
   `base`, the weights and the floor at READ time (`DEFAULT_SCORE_PARAMS`, starting values
   `base` 0.25, `asserted_floor` 1.0, weights 1 and 2, tunable without data loss; d9e).
   {#a14-floor}
2. **The asserted floor and the fold order are two signals.** [[#rule-asserted-floor]]'s
   definition (feedback, user-asserted or `protected`, `rel:`-anchored) stays the FLOOR, the
   protection against loss. `MEMORY.md`'s fold ORDER is a separate, narrower tier (feedback →
   memories linked from curated memories → the rest), because the floor definition covers ~91% of
   memories and cannot order them. Folding loses nothing: every folded memory stays reachable by
   a command its fold line prints (d8b). {#a14-fold-order}
3. **"The ONE removal path" is scoped.** [[#rule-no-delete]] says removal goes only through
   plan-22. Today `rmx forget`, `rmx memory bulk-forget`, `rmx untrack` and `rmx prune-noise
   --drop` also remove rows. Proposed scoping:
   - **Knowledge removal** (an entity, a learned row, a memory, a protection) goes through plan-22's
     audited path: dry run → manifest → `--confirm <hash>` → apply → restore. `forget` and
     `memory bulk-forget` become entry points to it (they build the manifest and require the
     confirm), not a second path.
   - **Derived-index cleanup** is NOT knowledge removal when the thing removed is recomputable
     from a kept source or points at nothing, and it is allowed outside plan-22 only with a
     manifest written before the change: plan-17's orphan-vector reap (the entity is gone from the
     whole catalog; vectors kept in the orphan list, `vectors_restore`), and the bug-105 fragment
     repair (bits of deleted entities, kept in the repair manifest).
   - **`untrack`** (a path the user removed from the corpus) and **`prune-noise --drop`** are
     listed exceptions: each prints what it removes and writes the same manifest form; neither is
     run by a timer or a counter.
   {#a14-removal-scope}
4. **Stale compiled subjects are marked, not removed.** Compile marks a subject `stale`; it stays
   protected and hidden from recall; removal is plan-22's `stale-subject` class (d8a, task 22.1a).
   {#a14-stale-subjects}

{#amend-2026-10-14-body}

## Open questions {#open}

- Typed expansion: which relation types, at which depth (1–3), under which lift/budget gates,
  earn their cost — a per-type evaluation grid, never a global walk. {#q-expansion}
- Cycle re-seeding (one conjunctive extra pass) is untested.
- Edit alignment's similarity threshold and compaction cadence.
- Graduation thresholds (cycle identity Jaccard; how many sessions; what counts as "used").
- ~~intropretor's unported modules: port / adapt / skip~~ — resolved 2026-10-06, see
  [[#intropretor]]. Left open from it: what "used" means for graduation. {#q-intropretor}
