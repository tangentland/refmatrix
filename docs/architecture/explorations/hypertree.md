---
gmd: "0.1"
id: exploration-hypertree
title: "Exploration: a hypertree for refmatrix, compared with the existing graph"
tags: [exploration, graph, hypertree, containment, facets, bitmaps, storage, helix, render]
metadata:
  node_type: exploration
  status: in-progress
  created: 2026-10-20
  updated: 2026-10-20
---

# Exploration: a hypertree for refmatrix {#root}

**Date:** 2026-10-20
**Status:** In Progress. The research is done; the M1-M7 spike was ordered by the user on 2026-10-20 ("run the m1-7 spike"). The deciding measurements
and their go/no-go bands are written below, before any data.
**Motivation:** Earlier this session the user asked whether refmatrix builds a graph or a tree, and
whether a tree would be better. The answer was "a graph, with trees as views and indexes". The
user then pointed at thiquet's "deconstructed faceted relational hypertree", which is a refmatrix
memory subject (`subject_explore_thiquet_s_deconstructed_facetted_relatio`, id 100845). That
subject has a label and no body. The user asked: "write up a hypertree exploration with a
comparison to the existing. Feel free to read thiquet, cliquedb, and cliquet's docs."

**The goal, restated by the user (2026-10-20):** "the primary motivation for the hypertree
conversation is to insure rmx's internal structures maximize associative power and is not meant as
an endorsement of any particular implementation." So the question is which internal structures let
refmatrix surface the most relevant ASSOCIATIONS (what else bears on this?), not whether to adopt
thiquet's, cliquedb's or cliquet's design. Every option and measurement below is read through that
lens: does it change what can be associated, and how well? {#goal}

rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: derives-from -> [[refmatrix/adr-0004-unified-location-space-index#amend-shape]]
rel: derives-from -> [[spike-2026-10-07-adjacency-shape]]
rel: related-to -> [[exploration-session-phased-context#tree-render]]
rel: related-to -> [[exploration-concept-similarity-cull-merge]]
rel: related-to -> [[exploration-storage-concurrency-redesign]]
rel: related-to -> [[project_storage_redesign_findings]]

The source projects' docs live in other repos, so [[#references]] cites them by their GMD ids as code spans rather than as
`rel:` edges or wikilinks: the repo lint (`./scripts/lint-gmd.sh`) fails any link whose target is
outside the scanned set. {#cross-repo-note}

## Answer in one paragraph {#answer}

None of the three source projects uses the word "hypertree". The phrase combines three ideas:

1. thiquet's **deconstructed property hypergraph**. The hypergraph is the conceptual model, realized
   as typed relational tables, one per relation type.
2. cliquedb's **faceted-property-hypergraph**. Facets are declared, indexed properties.
3. thiquet's **placement** store. It holds containment trees with the path in the key, so one
   entity can sit at many places.

For refmatrix, the candidate is therefore **a graph plus N containment trees and per-value facet
sets over one id space**.

The measured shape of refmatrix's adjacencies has three properties:

- weak communities in four of six stores;
- small-world reach that does not go through hubs;
- compression that comes from dense ids, not from order.

All three say the authoritative model stays the graph. **The recommendation is Option B: build the
hypertree as an INDEX layer over the graph.** It would hold containment placements and facets, it
is mostly ADR-0004's already-proposed containment and facet halves, and it would be built as a
strangler beside the existing tables. Before B is built, two read-only measurements decide whether
B is worth its cost: tree-coherence of concepts (M1) and containment-query demand (M2). Option C,
the hypertree as the primary model, is eliminated on present evidence. Its own lineage reversed
itself: cliquedb withdrew the bitmap kernel after benchmarking it, and cliquet forked away from it.
{#answer-body}

## Background {#background}

### What refmatrix is today {#bg-refmatrix}

refmatrix stores a **bipartite incidence** between entities and concepts, typed by linkage. It is
a hypergraph in all but name: each `(linkage, concept)` bitmap is a hyperedge over entities.

- `entities(id, partition_id, kind, path, name, tldr, meta, …)`, with
  `kind ∈ {doc, code, concept, memory}` (`src/refmatrix/store.py:259-275`). Concepts are entities
  too (`store.py:283-287`).
- **Bitmaps:** one roaring `BitMap64` per `(partition, linkage)`, packed `(concept_id << 32) |
  entity_id` (`docs/ARCHITECTURE.md:116-117`). A concept's member set is a range mask of that
  bitmap. Presence only, no weight and no time ([[refmatrix/adr-0004-unified-location-space-index#context-lead]]).
- **`entity_links(entity, linkage, concept, weight)`** is the generic edge table, a "maintained
  shadow" of the bitmaps (`store.py:326-341`). **`linkage_evidence`** adds `(file, line,
  span_end, detail)` per link (`store.py:392-410`). That makes it a reified, n-ary statement in
  all but name.
- **Typed entity→entity edges** use the same mechanism, with the target as a concept-entity:
  `calls`, `imports`, `is_a`, `specifies`, `same_as`, memory verbs (`store.py:460-488`), plus every
  author-declared GMD `rel:` verb. The verb set is OPEN: the GMD ingester auto-creates linkage
  types (`docs/ARCHITECTURE.md:170-172`).
- **Partitions** are one level of tree above everything (`store.py:249-257`).

**Trees already inside it.** None of these is indexed as a tree, so ancestor and subtree queries
are walks or `path LIKE` scans:

- the filesystem path (`entities.path`);
- GMD heading containment as `part-of` edges (`src/refmatrix/ingest_gmd.py:1164-1169`);
- code containment as `has-part` (`src/refmatrix/ingest.py:976-982`);
- the task stack;
- `supersedes` chains;
- the memory-compile subjects.

{#bg-refmatrix-body}

### The measured shape (spike 2026-10-07, six stores) {#bg-shape}

The figures are from [[spike-2026-10-07-adjacency-shape#results-table]] and
[[refmatrix/adr-0004-unified-location-space-index#amend-shape]]. Caveat: the spike's "cliquedb" and
"cliquet" rows are refmatrix's OWN catalogs built over those repos' files. They measure nothing
about the cliquedb or cliquet engines.

| property | measured | source |
|---|---|---|
| heavy-tailed degree | α 1.72–1.88 in the four large stores; top 1% of concepts hold 21–31% of edges; 30–47% hapax | spike `README.md:53-57` |
| small world, not via hubs | 2-hop reach 56–92%; dropping the top-1% hubs barely moves it in 4 of 6 stores (cliquet 0.92→0.92) | spike `README.md:58-68` |
| weak communities | Louvain modularity 0.12–0.26 in four stores; 0.43–0.45 in viascope and atldb | spike `README.md:69-71` |
| dense ids, not order | dense renumbering saves 15–42% of bitmap bytes; path or community order vs random saves < 0.75%; untested at `sid` granularity | spike `README.md:72-80` |

{#bg-shape-table}

### ADR-0004 already proposes trees as views {#bg-adr0004}

ADR-0004 (Proposed) already chooses trees as views and indexes, not as the model:

- **Two-tier ids.** A stable external id `entity(32) | sid(32)` is separate from a per-ingest
  Dewey **local ref** `section | paragraph | sentence`. "Containment, range masks … and decoration
  go through it" ([[refmatrix/adr-0004-unified-location-space-index#two-tier-ids]], ADR lines 61-70).
- **Containment is a relation family.** It covers structural, sequential, emergent and statistical
  containment. "The location→location pair is a materialized view of the Dewey ranges, never
  authoritative" ([[refmatrix/adr-0004-unified-location-space-index#containment]]).
- **Directory and extension facets.** `dir ⊃ doc ⊃ section ⊃ sentence` is a path-prefix level,
  and kind and extension are "a **facet bitmap** per value"
  ([[refmatrix/adr-0004-unified-location-space-index#amend-facets]]).
- **Tree render.** The 2026-10-14 idea renders STM as an expand/collapse tree, with the active
  cluster open and the rest one line each ([[exploration-session-phased-context#tree-render]],
  task 19.6).

{#bg-adr0004-body}

### thiquet: a deconstructed property hypergraph over parts and BOMs {#bg-thiquet}

thiquet is a "Prototype backbone for a unified vehicle part-number hierarchy" (`thiquet/README.md:3-5`)
on PostgreSQL 18 + FastAPI. Its name for the structure is the **deconstructed property hypergraph**.
The words "hypertree" and "faceted relational hypertree" do not occur in its docs.

- **The decision** (`docs/architecture/adr/adr-0009-deconstructed-property-hypergraph.md:30-36`):
  "The property hypergraph is the **conceptual** model; the **realization** is **decomposed into
  typed relational sibling tables** — one table per edge-type, each an associative table with FK'd
  participants + typed attribute columns (a reified hyperedge). The hypergraph is a **query view**
  … **never** a stored generic structure." Each new structure must answer four questions: "what
  are its nodes? what is the hyperedge (its participants)? what attributes does it carry? which
  typed table realizes it?" That decomposition is what "deconstructed" means.
- **Rejected:** a "Generic `edge(src, dst, props jsonb)` table — … same loss, plus a pivot on
  every read" (adr-0009:53-54). A graph DB and a triple store are rejected too.
- **Nodes and hyperedges** (`docs/concepts/deconstructed-property-hypergraph.md:25-33`):
  - The nodes are "abstract positions, canonicals, units, orgs, vehicle-classes".
  - "every fitment, override, BOM edge, and attribute is a *reified, n-ary, attributed
    relationship* — a **statement**". A fitment relates "(part × vehicle × config × position ×
    qty)".
  - "Multiple representations — several labeled edge-relations over one vertex set (OEM vs
    aftermarket vs service decompositions)". The named analogue is "Wikidata's statement … EAV
    done right".
- **The tree half: `placement`** (`adr-0023-primary-structural-store-inverted-index.md:33-52`,
  Accepted, "Implementation: pending"):
  - The shape is `placement(representation, version, path ltree, entity_id, PRIMARY KEY
    (representation, version, path))` with GiST on `path`, for "subtree / ancestor / where-used".
  - "`path` in the PK → many placements per entity". This is how one part sits in many
    assemblies.
  - "the **bitmap** … is *derived from it*".
  - "Hard invariant: *no qualifiers in `placement`* — structure only".
  - "Re-parent cost is moot because representations are **immutable per version**".
  - `pseudocode/13-entity-substrate-planned.md:49-51` later realizes it as "CliqueDB's ltree axis
    … NOT a thiquet `placement` table".
- **Facets** come in two senses. One is typed sibling columns on `part_bom_edges` (`service_level`,
  `config_predicate`, `qty`, …; `docs/thiquet_product_architecture.md:1236`). The other is
  engine-indexed columns, "roaring/BSI/ltree/GIN facets" (`adr-0029-adopt-cliquedb-engine.md:49`).
- **Variants live on edges, not in tree forks:** "An edge applies when `unit.config_attrs @>
  edge.config_predicate` … never fork the whole tree" (`pseudocode/04-versioned-bom.md:37-40`).
- **Selections** are "intensional" cliques. "A selection STORES A PREDICATE, NEVER members"
  (`pseudocode/14-first-class-selection.md:10,40`). The `selection` row is deferred.
- **Query model:**
  - BOM tree = "`related(root,'has_part',depth)` closure (cycle-safe, no CTE)".
  - fitment = "`find` over the `fits` relation (BSI serial range + GIN config-predicate DSL)"
    (`pseudocode/12-cliquedb-adoption.md:118-126`).
- **Tree vs star:** "the current normalized hybrid wins decisively". A star is "a *downstream
  mart*", and "It is a layering decision: graph/OLTP for truth and transactions, star/OLAP for
  counting" (`docs/hybrid_tree_vs_star.md:17-20`).
- **Measured:** nothing on latency. The benchmarks are targets only: "Where-used query: 1M+
  canonical_parts, p99 < 50ms; Subtree walk: 500-level deep BOM, p99 < 20ms"
  (`docs/ROADMAP.md:478-481`). The recorded results are correctness counts (pgTAP, pytest).
- **Unclear:** how a bare `(parent, child)` `has_part` edge is qualified by `bom_version` is "a
  tracked parity item, not a settled mechanism" (`pseudocode/04-versioned-bom.md:69-71`). The
  whitepaper's "eventually consistent (CQRS)" read model contradicts ADR-0029's in-transaction
  maintenance. The stored data is ordinary associative and adjacency tables; the hypergraph
  exists in the docs and the query layer.

{#bg-thiquet-body}

### cliquedb: a faceted-property-hypergraph engine that withdrew its bitmaps {#bg-cliquedb}

- **The pitch** (`cliquedb/README.md:3-11`): "A database engine for
  **faceted-property-hypergraphs** … set algebra over always-consistent projective bitmaps. …
  everything is a *clique* — a named set materialized as a bitmap over one shared, dense entity
  address space … Query = `AND`/`OR`/`ANDNOT`/`XOR` over cliques".
- **Lineage:** it was "distilled from the very convergence of thiquet and refmatrix"
  (thiquet `adr-0029:45-47`). The bitmap-clique kernel is refmatrix's own model, carried into
  Postgres.
- **Address:** a pair of signed 64-bit words. "word-1 is the object-TYPE subnet … word-2 is an
  instance/part under it … `word_2 == 0 ⟺ the TYPE-entity itself`". Typing is prefix
  containment on word 1 (`pseudocode/00-address.md:16-20`). Containment is in the address.
- **Relations:**
  - Edges are reified, and standard verbs carry an engine-enforced algebra.
  - Mereology is "directed, trans, acyclic … May project to an `ltree` axis where a single tree
    fits" (`docs/cliquedb-standard-relations.md:72`).
  - Closure is computed at read time, with a hop cap.
- **Facets** are declared, indexed property columns with a predicate strategy (roaring member,
  BSI range, ltree, GIN). For example, `set_property_facet('part','taxonomy','ltree', …)`
  (`docs/COMMAND_PRIMER.md:636`).
- **Hierarchical subtree store** (`pseudocode/19-hierarchical-subtree-storage.md:10-13`;
  ADR-0044):
  - "Each distinct sub-assembly **branch** is stored **ONCE** as an abstract structural
    **definition** … each occurrence is a **lightweight instantiation ref**".
  - It is a derived, rebuildable cache, and it is opt-in per relation.
  - Reuse rule: "A reused sub-assembly is ONE minted addr referenced N times"
    (`pc19:1128-1129`).
  - Prohibited: inferring shared subtrees from a flat BOM, which is "frequent-subgraph mining"
    (`pc19:1134-1136`).
  - The O(1) bitmap-reachability claim is "⛔ WITHDRAWN" (`pc19:957-962`).
  - The savings are "MODELED … not measured" (ADR-0044:37).
- **Measured (2026-07-14, the old roaring engine; `reports/perf-benchmark-2026-07-14.md:79-107`):**
  - "the benchmark REFUTES the latency/storage thesis and CONFIRMS only the deployability +
    expressiveness thesis".
  - Set algebra loses to a plain recursive CTE by "16× (small) → 22× (med) → 27.7× (large)".
  - k-hop at 1M nodes is "47.2 ms p50 / 1406 ms p95, vs recursive-CTE 1.12 ms / 20 ms and Neo4j
    ~6.5 ms".
  - Storage is 13.61 GB vs 1.14 GB = 11.9×.
  - Writes stay flat at 1.2× from 1 to 16 writers.
- **Then the bitmap layer was withdrawn.** ADR-0058 (Accepted): "Membership becomes append-only
  signed dot rows … the chunked engine, the BSI slice substrate, the SFC pos axis and the roaring
  dependency are DELETED". The read engine became recursive CTEs over `proj_adj`/`proj_mem`
  (pseudocode/18).
- **Why the benchmark does not transfer:**
  - The benchmark measured a **PL/pgSQL interpreter** looping over `pg_roaringbitmap`, not
    roaring itself.
  - refmatrix's bitmaps run in CRoaring through pyroaring, where each op is one big C call.
  - [[project_storage_redesign_findings#bsi]] records the rule: "keep the loop in C/C++ and keep
    each bitmap op big".
  - It is a caution about interpreted per-element set algebra, not evidence against
    refmatrix's bitmaps.
- **Status:** "TODD CALLED A HARD FORK. ACTIVE WORK IS IN **`cliquet`**" (`workflow/STATUS.md:9`).
  The README and design doc are stale against the ADR layer.

{#bg-cliquedb-body}

### cliquet: a topic store, nothing built {#bg-cliquet}

- **Origin:** a hard fork of cliquedb, founded 2026-08-04 (`cliquet/CHARTER.md:12`). cliquedb
  "INFORMS, NEVER OVERRIDES" (`CHARTER.md:21`).
- **Status:** "⛔ **NOTHING IS BUILT.**" (`docs/architecture/adr/adr-physical-layout.md:25`).
  `src/`, `sql/` and `bench/` hold only `.gitkeep`, and there are no measurements.
- **Model:** a TMDM topic store (ISO 13250-2) written in SQL inside PostgreSQL. In todd's words,
  "the difference between a facetted-hyper-graph and a topic map is the topic map has 20+ years
  of thought" (`adr-scope.md:192`).
  - Relations are n-ary.
  - Arity is a mutable constraint on the type.
  - "No table is created per type — the schema is FIXED against type growth"
    (`adr-physical-layout.md:1247`).
- **Hierarchy** is containment in the address: "cliquet COMPARES TYPE VIA CONTAINMENT"
  (`adr-comparison-resolution.md:618`). Multiple supertypes are "a lattice over a tree"
  (`:803`), and subsumption is a read-path gather.
- **"No bitmaps. No bitmap-value-key-proxies."** (`CHARTER.md:295`).
- "Hypertree" does not occur in cliquet.

{#bg-cliquet-body}

### The older Atollogy "hypertree" schema {#bg-atl-hypertree}

The only artifact in the bdep tree that is named "hypertree" is `atl_hypertree/hypertree_schema.json`
(2021, outside the three requested repos). It is a JSON Schema for "a nestable container structure
for complex objects" (`hypertree_schema.json:45`):

- an `org` whose `structure` holds child `org`s plus `resources`, `roles`, `groups`, `users`,
  `locations` (lines 63-106);
- path-addressed resources `:domain::path` with prefix (`.`) and wildcard (`*`) search forms,
  plus `@` references across the tree (lines 18-41, 111-130).

That is the same idea in miniature: a containment tree, a path address with prefix queries, and
cross-tree references. Whether it is what the user means by "hypertree" is open question Q1.
{#bg-atl-body}

## A precise definition of the candidate {#definition}

There are two meanings, and they should not be confused.

**(1) The graph-theory hypertree.** A hypergraph H = (V, E) is a *hypertree* (a subtree hypergraph)
when some tree T on V exists such that every hyperedge e ∈ E induces a **connected subtree** of T.
Equivalently, H's dual is α-acyclic. For refmatrix, take V = entities (or locations), E = each
`(linkage, concept)` member set, and T = the containment tree. refmatrix is a hypertree in this
sense exactly when concepts are tree-local, meaning each concept's occurrences sit in one
contiguous region of the containment tree. That is a testable property (M1 below). It is also the
opposite of what refmatrix is for: cross-cutting recall finds the concept in places the tree does
not group. {#def-graph-theory}

**(2) The composite: a deconstructed, faceted, relational hypertree.** This is what the source
projects build, and it is the candidate considered here. Over one id space it has four parts:

| # | part | source | refmatrix mapping |
|---|---|---|---|
| P1 | **Placements:** rows `(representation, version, path) → node`, with the path in the key, so one node can have many placements; subtree and ancestor are path-prefix queries | thiquet `placement` (adr-0023); cliquedb ltree axis | `node` = entity id now, or ADR-0004 `sid` later; `path` = ADR-0004's Dewey local ref extended upward (`partition ▸ dir ▸ file ▸ section/class ▸ para/def ▸ sentence/block`); `representation` ∈ {fs, gmd-heading, code-ast, subject, session}; `version` = a manifest id |
| P2 | **Facets:** one member set per (facet, value) | cliquedb facets; ADR-0004 #amend-facets | roaring bitmap per value: `kind`, extension, partition, `protected`, `noise`, mtype, age tier, session tier |
| P3 | **Reified typed hyperedges:** n-ary statements, decomposed by type | thiquet adr-0009 | already present: the bitmap fragment per `(partition, linkage)` IS the per-type decomposition; `linkage_evidence` is the reified statement with qualifiers `(file, line, span)`; GMD `rel:` attrs are qualifiers |
| P4 | **The graph is a query view over P1–P3** | thiquet adr-0009 "query view … never a stored generic structure" | ranking, admission, walk and render read P1–P3; nothing new is authoritative |

{#def-composite}

**Constraints carried over from the sources.** They are adopted because they are sound, not
because the sources measured them.

- **No qualifiers in placements.** The path is structure only (thiquet adr-0023). Weight, time and
  evidence stay on the statement or in the tiers.
- **A representation is immutable per version.** A re-ingest writes a new version of that file's
  subtree, so there is no re-parent cost. This is ADR-0004 edit alignment plus manifests.
- **Variants and filters are facets or predicates, never a tree fork.** This mirrors thiquet's
  `config_predicate`. A "selection" stores a predicate, never members.
- **The address carries no order that the ids depend on.** The external id stays dense
  ([[#bg-shape]] row 4) and the path is a separate column. This is ADR-0004's two-tier rule, which
  also distinguishes it from cliquedb, where containment lives in the address.

{#def-constraints}

**What the definition leaves out on purpose:**

- cliquedb's shared-subtree definitions. Mining repeated subtrees is exactly what pc19 prohibits,
  and refmatrix has no authored DAG reuse to preserve. Vendored copies are already excluded from
  the corpus.
- A table per relation type. refmatrix's verb set is open: GMD creates verbs on sight. cliquet
  ruled the same way ("FIXED against type growth").

{#def-not}

## Comparison: the existing graph vs the hypertree candidates {#comparison}

B is the hypertree as an index layer over the graph; C is the hypertree as the primary model.

| axis | existing graph (A) | hypertree index (B) | hypertree primary (C) |
|---|---|---|---|
| **representation** | bipartite entity × concept incidence per linkage (bitmaps) + generic `entity_links` shadow + evidence; trees implicit (`path`, `part-of`, `has-part`) | A, plus placement rows per representation and facet bitmaps; the graph stays authoritative | placements + per-type statement tables are the store; incidence is derived or dropped |
| **multi-membership** (one concept in many files) | native: a concept bitmap holds every entity; one entity in many concepts is free | native for concepts (unchanged); a node in many trees = many placements (path in key) | concepts must become hyperedges over placements; multi-membership is a join, not a bit |
| **cross-cutting recall** | the strength: BM25 + dense + concept bitmaps ignore the tree; 2-hop reach 56–92% | unchanged; facets add cheap filters (`kind`, extension, age) as ANDs | weakest: recall scoped by subtree loses exactly the cross-tree hits; it only works if concepts are tree-local (M1), and the shape says they mostly are not |
| **containment / address queries** ("everything in this dir/section", "where is X placed", ancestors) | `path LIKE` scans, iterative `part-of`/`has-part` walks; no ancestor index | path-prefix range = one indexed range per query; ancestors = prefixes of one path; LCA trivial | same as B |
| **render to an agent** | flat neighbor lists with `path:line`; repeated path prefixes cost tokens; legibility depends on rank order | a tree render falls out (shared prefixes printed once, expand/collapse per 19.6); collapsed subtrees are byte-stable handles | same as B, but the cross-cutting neighbors that do not fit the tree need a second render path anyway |
| **incremental ingest / update** | per-file entity + link + bitmap updates through the daemon; per-entity write patterns have hurt before (bug-085) | plus one per-file placement-subtree rewrite (immutable version → append + tombstone); facets update with the entity row; must be batched per file | every read path and derive pass rewritten; per-type tables for an open verb set mean DDL on ingest (cliquet rejected that) |
| **storage / compression** | bitmaps; dense-id renumbering would save 15–42%; order saves < 0.75% at entity granularity | placement rows are small (path + ids); facet bitmaps are few and dense; path ORDER buys nothing at entity grain, so ids stay dense and the path is a column; untested at `sid` grain (M7) | relational edges with per-row metadata; cliquedb's own engine measured 11.9× a plain CTE store, though its relational-only successor is unmeasured |
| **fit to heavy tail** | hubs are stoplist / hub-damping signals; hapax feeds promotion or cull | facets are low-cardinality by design; placements are one per node per representation, so there are no hub rows | a hub concept as a hyperedge over placements is a huge join; tree-local storage gives the tail nothing |
| **fit to small world (not via hubs)** | the expansion ADR-0004 allows: typed, lift-gated, budgeted admission | unchanged; LCA distance in the tree becomes one more proximity band (ADR-0004 #amend-proximity) | the tree gives no shortcut across subtrees; reach comes back only through the graph C demoted |
| **fit to weak communities** | does not depend on communities | a `subject` representation only where modularity is strong (viascope, atldb 0.43–0.45) | a single primary hierarchy would be arbitrary in 4 of 6 stores (modularity 0.12–0.26) |
| **decay / helix versioning** | time in four unjoined places; ADR-0004 adds age tiers + manifests keyed on `(concept, entity)` | placements versioned per representation and listed in the same manifest; "as of" = manifest diff; decay applies to tiers, never to placements (structure does not decay; rule-no-delete) | same mechanisms, but every relation table needs its own version and tombstone story (cliquedb's CAS dot rows show the cost) |
| **busy/absent single-writer daemon** | `_op_*` is the only write surface; CLI reads hit the snapshot | placements and facets are written by the same daemon op as the file's entities, in the same transaction; readers see them in the snapshot; nothing new runs when the daemon is absent (the CLI only reads) | same writer model, but a full storage-core rewrite under it |
| **migration cost** | none | a new derived layer beside the old (strangler, as ADR-0004 #consequences prescribes); a backfill derive pass per store; old readers untouched | rewrite of ingest, `content_rank`, context, scan-prompt, recall, daemon ops, replica rotation, hub; every eval re-baselined |

{#comparison-table}

## Option A: keep the graph, trees as views (status quo direction) {#option-a}

Keep the incidence graph as the model. Trees appear only as renderings and as the indexes already
planned:

- ADR-0004's Dewey local ref (containment and decoration);
- the 19.6 expand/collapse STM render;
- `part-of` and `has-part` edges;
- a subject hierarchy (memory-compile subjects) only in stores with strong communities.

- **For:** no new storage. Every measured win (sentence co-location, hybrid recall) is on the
  graph side. It matches the shape.
- **Against:** containment and address queries remain scans and walks. The agent-facing render
  still repeats path prefixes. "Where else is this placed" has no direct answer.
- **Needs measured:** nothing to keep A. M2 says how much A leaves on the table.

{#option-a-body}

## Option B: the hypertree as an index layer over the graph {#option-b}

Add P1 (placements) and P2 (facets) as a derived layer, P4 as the read discipline, and keep P3 as
it is. The graph stays authoritative: placements are rebuilt from the files and the entities, and
are listed in manifests. In detail:

- **`placement(partition, representation, version, path, node)`**, PK `(partition, representation,
  version, path)`. `path` is a fixed-width, order-preserving encoding of the Dewey components, so
  "subtree" is a key range and "ancestors" are the prefixes. Start with three representations:
  - `fs`: dir ▸ file;
  - `gmd`: heading tree, replacing the `part-of` walk;
  - `code`: module ▸ class ▸ def, replacing the `has-part` walk.

  `subject` is admitted per store only if M5 passes.
- **Facet bitmaps** per value for `kind`, extension, partition, `protected`, `noise`, memory
  `mtype`, and later age and session tiers. This is ADR-0004 #amend-facets as written.
- **Readers that change** (each opt-in, each measured):
  - `rmx context --under <path>` / `rmx query "under:<path> AND …"` as a facet-like AND;
  - LCA distance as a proximity band in ranking (ADR-0004 #amend-proximity);
  - the tree render for context bundles and STM (19.6).

- **For:**
  - containment queries become index ranges;
  - the render gets a real tree;
  - multi-membership across representations is explicit;
  - it lands most of ADR-0004's containment and facet halves without waiting for the location
    space, because it works at entity granularity first and `sid` later.
- **Against:**
  - it is one more derived structure to keep consistent: the bug-039 lesson is that derived
    graphs decay behind green health, so it needs a derive stamp and a `derive_history` count
    from day one;
  - it adds write cost per file;
  - its value depends on whether agents and users actually ask containment questions (M2).
- **Needs measured:** M1 (does LCA proximity carry signal), M2 (demand), M4 (render tokens), M6
  (write cost), and M7 at `sid` grain if B moves to locations.

{#option-b-body}

## Option C: the hypertree as the primary model {#option-c}

Replace the incidence graph with placements plus per-type reified statement tables, thiquet
adr-0009 style. Concept membership becomes a hyperedge over placements, and bitmaps become a
derived projection or disappear, as in cliquedb ADR-0058 and cliquet's charter.

- **For:**
  - one structural truth;
  - n-ary statements with qualifiers become first-class (`linkage_evidence` promoted);
  - containment and versioning are native.
- **Against:**
  - it subordinates the cross-cutting incidence that every measured refmatrix win rides on;
  - it fits an open verb set badly;
  - it rewrites the storage core;
  - the projects it comes from did not validate it either. thiquet's latency benchmarks are
    targets only. cliquedb's measured engine refuted its own latency and storage thesis and was
    then rebuilt on recursive CTEs. cliquet is unbuilt.
- **Needs measured before it could even be considered:** M1 at ≥ the C band AND M3 recall parity
  on every held-out set.

{#option-c-body}

## Findings {#findings}

What the measured shape says about each option:

1. **Weak communities (0.12–0.26 in 4 of 6 stores) rule out any single primary hierarchy over
   concepts.** A tree must be a containment tree the files already have (fs, headings, AST), not
   one inferred from co-occurrence. Inferred hierarchies (subjects) are per-store and gated on
   modularity. This hurts C and leaves A and B intact. {#f-communities}
2. **Small world through mid-degree concepts means recall cannot be scoped by subtree.** Two hops
   reach 56–92% of entities without hubs, so the relevant neighbors of a query sit all over the
   tree. A tree-first retrieval (C) would have to fall back to the graph for most hits. B uses the
   tree only as a filter and as a proximity band, so it loses nothing. {#f-small-world}
3. **Dense ids, not order, drive compression.** A hypertree's usual storage argument, that tree
   order clusters ids into runs, is unsupported at entity granularity (< 0.75%). Keep the external
   id dense and put the path in a column, ADR-0004's two-tier rule. The only place order might pay
   is `sid` granularity (M7). {#f-compression}
4. **Heavy tail: hubs belong to facets and stoplists, not to trees.** A tree gives the hapax tail
   no evidence, while promotion and cull do. Placements are one row per node per representation,
   so the tail costs nothing extra there. {#f-tail}
5. **refmatrix is already "deconstructed" by relation type at the bitmap level.** One fragment per
   `(partition, linkage)` is thiquet's per-type decomposition, and `linkage_evidence` is its
   reified statement. The parts it lacks are P1 (placements) and P2 (facets). That is B, and ADR-0004
   already proposes both. {#f-already-deconstructed}
6. **The lineage is a warning about C, not about bitmaps.** cliquedb took refmatrix's bitmap-clique
   model into Postgres, benchmarked a PL/pgSQL interpretation of it, measured 16–28× slower set
   algebra and 11.9× storage, then withdrew bitmaps. cliquet banned them. Those numbers measure an
   interpreter over `pg_roaringbitmap`. refmatrix's CRoaring calls are a different cost regime
   ([[project_storage_redesign_findings#bsi]]). What does transfer is the shape of thiquet's
   conclusion: "graph/OLTP for truth …, star/OLAP for counting". Here that reads as the graph for
   truth and the tree for addressing and rendering. {#f-lineage}
7. **The math hypertree property is directly testable and probably false.** If concepts were
   subtree-local, path order would also cluster bitmaps. The spike's < 0.75% does not settle it,
   because at entity grain the container type hides order. M1 settles it. {#f-testable}

{#findings-body}

### Deciding measurements, with bands written before any data {#measurements}

The run is read-only, on catalog copies, like the 2026-10-07 spike, over the same six stores. Each
band names an action. No band was tuned on data, because no data exists yet.

| id | measurement | how | bands → action |
|---|---|---|---|
| M1 | **tree-coherence of concepts**: edge-weighted share of concepts (df ≥ 2) whose members lie in ONE subtree at directory depth ≥ 2 of the `fs` tree; also mean connected components per concept in the tree | `mentions` × `entities.path`; report per store | **≥ 60%** → hypertree-shaped: C may be reconsidered (still needs M3); B's LCA band is likely strong. **25–60%** → B: LCA distance is worth a proximity band; test it in ranking. **< 25%** → not tree-local: no LCA band; B only for containment queries and render, if M2 passes |
| M2 | **containment-query demand**: share of real queries that are containment-shaped (path prefix, "in/under X", `--hit-lines` on one file, grep `-r` scoped to a subdir) | `.refmatrix/query.log` + `cli.log`, last 30 days, all stores | **< 10%** → B not worth a table; serve containment from `entities.path` ranges (A). **10–30%** → B with `fs` + `gmd` only. **> 30%** → B with all three representations |
| M3 | **recall parity of a tree-scoped retrieval** (C's precondition) | retrieve within the top LCA subtree + graph fallback, vs production `content_rank`, on cliquedb `lines`/`merge` and MemAware test-720 | **any held-out MRR loss > 0.005** → C stays eliminated. **within ±0.005** → C is no worse, but has no reason to exist; still eliminated on migration cost. **gain ≥ 0.02 on held-out** → reopen C as an amendment to ADR-0004 |
| M4 | **render token cost**: tokens per distinct covered entity, tree render vs today's flat bundle, same budget, same members | the context bundles of 200 logged prompts | **≥ 25% fewer** → tree render becomes the default for context and STM. **10–25%** → opt-in flag. **< 10%** → keep flat; render-only work stops |
| M5 | **subject representation per store** | Louvain modularity (already measured) + subject-label quality (19.0 hygiene) | **≥ 0.40** → admit a `subject` representation in that store. **0.30–0.40** → label quality first. **< 0.30** → no subject tree |
| M6 | **write cost of placements**: p95 added time per file re-ingest through the daemon, batched per file | throwaway store under a short `mkdtemp()` root, never the live store | **< 5%** of today's per-file sync → inline. **5–20%** → batch at the snapshot tick. **> 20%** → no-go for inline maintenance; derive offline only |
| M7 | **order at `sid` grain** (ADR-0004's open item) | Dewey-ordered vs random `sid` numbering, per-term bitmaps after `run_optimize` | **≥ 10%** bytes saved → number sids in Dewey order. **2–10%** → order at compaction only. **< 2%** → order is irrelevant; paths stay columns everywhere |

{#measurements-table}

## Spike results (2026-10-20) {#spike-results}

The M1-M7 run is reported in [[spike-2026-10-20-hypertree]], with per-store tables, method,
snapshot times and scripts under `eval/spike_hypertree/`. The bands above are unchanged.

rel: evidence-for -> [[spike-2026-10-20-hypertree]]

| M | result (six stores unless noted) | band → action |
|---|---|---|
| M1 | edge-weighted local@2 1.5–12.7%; 50–69% of top-10 associates outside the depth-2 subtree | < 25% → no LCA band |
| M2 | refmatrix 61%, atldb 98% containment-shaped, but subtree-shaped only 8.2% / 4.1%; 4 stores insufficient data | > 30% → B; the demand is within-file (`gmd`/`code`), not `fs` |
| M3 | tree-scoped MRR −0.026 to −0.342 (cliquedb), −0.0075 MemAware test-720 held-out | loss > 0.005 → C stays eliminated |
| M4 | 3.4% on 200 real prompts (relative paths alone 3.9%); concept-anchor variant 17–31% | < 10% → keep flat |
| M5 | modularity 0.12–0.26 in 4 stores, atldb 0.33 (was 0.43), viascope 0.45 with generic labels | no subject tree, except viascope in principle |
| M6 | p95 placement ÷ p95 re-sync 0.2–1.3% (all 6 stores); per-file p95 7.6–39% | < 5% → inline, fused into the entity transaction |
| M7 | Dewey vs random sid bytes 0.1–6.9% | 2–10% (3 stores) compaction only; < 2% (3 stores) irrelevant |

{#spike-results-table}

**Implied option: B, scoped.** The graph stays authoritative. `gmd` section and `code` def
placements are written inline for within-file address queries. There is no LCA band, no tree
render default, no `fs` table, no subject tree and no Dewey-ordered ids. C stays eliminated. For
associative power: the cross-cutting graph surfaces the associations, and the tree carries signal
only inside a file. {#spike-results-implication}

## Transition Summary {#transition-summary}

**Status:** NOT STARTED

**Date:** 2026-10-20
**Proposed Plan:** none yet. The next step is a read-only spike (M1, M2, M4, M5) under
`eval/spikes/`, and a plan only if B survives it.

### What Survived Analysis {#what-survived-analysis}

- **Option B**, the hypertree as an index: placements per representation (`fs`, `gmd`, `code`;
  `subject` only where M5 passes) plus facet bitmaps, with the graph authoritative. It is mostly
  ADR-0004's containment and facet halves, and it can ship at entity granularity before the
  location space.
- **Option A** as the fallback, if M2 shows little containment demand: tree render (19.6) and the
  `entities.path` ranges are enough.
- Constraints adopted from thiquet: no qualifiers in placements; representations immutable per
  version; variants as predicates or facets, never tree forks.

### What Was Eliminated {#what-was-eliminated}

- **Option C** (the hypertree as the primary model). The reasons:
  - weak communities and small-world reach make subtree-scoped recall lossy;
  - the open verb set does not fit per-type tables;
  - it would rewrite the storage core;
  - its own lineage reversed. cliquedb measured its bitmap kernel and withdrew it, and cliquet
    forked to an unbuilt topic store.

  It reopens only on M1 ≥ 60% AND an M3 held-out gain.
- **Tree-ordered ids for compression** at entity granularity (the spike: < 0.75%).
- **Shared-subtree definitions** (cliquedb pc19). There is no authored reuse to preserve, and
  mining it is prohibited even there.

### Key Constraints Discovered {#key-constraints-discovered}

- The external id stays dense and the path stays a column (the two-tier rule). Containment in the
  address, as in cliquedb's paired words, would trade away the measured 15–42% dense-id saving.
- Any derived tree layer needs a derive stamp and `derive_history` counts from day one (bug-039).
- Placement writes go through the daemon's `_op_*` surface, batched per file (the bug-085
  pattern).
- Structure does not decay. Age tiers apply to statements, and placements change only by
  re-ingest or the audited removal path (ADR-0004 #rule-no-delete).

### Open Questions Requiring User Decisions {#open-questions-requiring-user-decisions}

- **Q1:** Which "hypertree" did you mean? The candidates are:
  - (a) the composite here: placements + facets + typed statements;
  - (b) the graph-theory property, where every concept is subtree-local (M1 tests it);
  - (c) the 2021 `atl_hypertree` nestable-container schema;
  - (d) something in thiquet not written down (its docs never use the word).
- **Q2:** Run the read-only spike (M1, M2, M4, M5 over the six stores) now, before any plan?
- **Q3:** For B, which representations come first? The proposal is `fs`, `gmd` and `code`, with
  `subject` gated per store.
- **Q4:** Should B ship at entity granularity now, or wait to key on ADR-0004 `sid`s? The proposal
  is entity now, `sid` when the location space lands.
- **Q5:** Should `linkage_evidence` + GMD `rel:` attrs become thiquet-style reified statements
  with qualifiers (P3 made explicit), or stay as they are? It is out of B's scope, but it is the
  part of thiquet that refmatrix only half has.
- **Q6:** Does this belong in ADR-0004 as an amendment (placements as its containment realization),
  or in a separate ADR?

### What Is NOT Moving Forward {#what-is-not-moving-forward}

- Per-type relational tables, TMDM topic-map modelling, cliquedb's paired-word address and its
  CAS dot-row membership: interesting, and well argued in their repos, but out of scope for a
  single-writer, open-vocabulary, bitmap-native index.
- A star or OLAP mart (thiquet's analytics layer). refmatrix's counting needs are served by
  `derive_history` and telemetry.

## References {#references}

- [[refmatrix/adr-0004-unified-location-space-index]]: two-tier ids, containment family,
  facets, the shape evidence, helix rules.
- [[spike-2026-10-07-adjacency-shape]]: `eval/spikes/2026-10-07-adjacency-shape/README.md`.
- [[exploration-session-phased-context#tree-render]]: the expand/collapse render (task 19.6).
- [[exploration-storage-concurrency-redesign]], [[project_storage_redesign_findings]]: BSI, the
  PL/pgSQL-loop caution.
- refmatrix source: `src/refmatrix/store.py:249-488`, `docs/ARCHITECTURE.md:107-117,170-186`,
  `src/refmatrix/ingest_gmd.py:1164-1169`, `src/refmatrix/ingest.py:976-982`.
- thiquet (`~/github/atollogy/bdep/thiquet`):
  - `thiquet/adr-0009-deconstructed-property-hypergraph`
  - `thiquet/deconstructed-property-hypergraph`
  - `thiquet/adr-0023-primary-structural-store-inverted-index`
  - `thiquet/hybrid_tree_vs_star`
  - `pseudocode/04,12,13,14`
  - `docs/ROADMAP.md`
- cliquedb (`~/github/atollogy/bdep/cliquedb`):
  - `cliquedb/cliquedb-design`
  - `cliquedb/adr-0044-hierarchical-subtree-instantiation-storage`
  - `cliquedb/adr-0058-the-bitmap-layer-is-withdrawn`
  - `perf-benchmark-2026-07-14`
  - `pseudocode/00,18,19`
  - `workflow/STATUS.md`
- cliquet (`~/github/atollogy/bdep/cliquet`):
  - `cliquet/adr-scope`
  - `cliquet/adr-comparison-resolution`
  - `CHARTER.md`
  - `adr-physical-layout.md`
- `~/github/atollogy/bdep/atl_hypertree/hypertree_schema.json` (2021).
