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

## Open questions {#open}

- Typed expansion: which relation types, at which depth (1–3), under which lift/budget gates,
  earn their cost — a per-type evaluation grid, never a global walk. {#q-expansion}
- Cycle re-seeding (one conjunctive extra pass) is untested.
- Edit alignment's similarity threshold and compaction cadence.
- Graduation thresholds (cycle identity Jaccard; how many sessions; what counts as "used").
- ~~intropretor's unported modules: port / adapt / skip~~ — resolved 2026-10-06, see
  [[#intropretor]]. Left open from it: what "used" means for graduation. {#q-intropretor}
