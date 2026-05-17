# rmx Doc-Authoring Primer (for Agents)

You are an agent authoring documentation in a project that uses rmx
to index code, concepts, and architecture. The primary failure mode
this primer prevents: writing docs that are *file-system visible*
but *semantically invisible* — they exist on disk but no concept
search will surface them.

Before authoring any technical doc, decide which of these forms
rmx already understands. Match your doc to the form; the indexer
does the rest.

## Why this matters — the discovery ladder

Other agents (and you, in future sessions) find authoritative
design via:

```
rmx context <Concept>  →  rmx query <linkage>:<concept>  →  rmx grep <term>  →  rg/grep
```

The ladder favors *structured* sources over *free prose*. A doc
that doesn't fit a structured form sits below grep, only findable
by full-text search of its file content. If the project's authority
hierarchy is `ADR > concept doc > pseudocode > code`, an unstructured
markdown file effectively ranks *below code* — opposite of intent.

Authoring a doc in the right shape promotes it up the ladder.

`rmx grep PATTERN` is the bottom rung of the structured side: it
walks `linkage_evidence` for concepts whose name matches PATTERN and
emits `path:line` per hit. If the index has nothing, it falls through
to `rg` and folds any rg hits back into a `query/PATTERN` concept so
the second call lands in the index. Reach for it instead of `rg` when
you can — the index already knows where every named concept is referenced.

## Decision tree — which form do I write?

Answer the first matching question:

| Question | Form | Location |
|---|---|---|
| "Is this a binding architecture decision?" | **ADR** | `docs/architecture/adr/NNNN-title.md` |
| "Am I authoring a graph of typed nodes I want walkable with first-class verbs?" | **GMD (Graph Markdown)** | Anywhere; `.gmd` or `.md` with `gmd:` frontmatter |
| "Am I defining one or more named concepts canonically?" | **Concept doc** | `docs/.../concepts/<concept>.md` |
| "Am I specifying types, interfaces, or contracts for implementation?" | **`.pseudo` file** | Anywhere; conventional `pseudo/` |
| "Am I exploring, proposing, or recording context that isn't a decision yet?" | **Design doc** | `docs/design/<topic>.md` |
| "Am I declaring intent for code that should exist (a plan, spec, or issue)?" | **Plan / spec / issue doc** | `PLAN-*.md`, `ISSUE-*.md`, `SPEC-*.md`, `ROADMAP-*.md`, or anything under `plans/`, `specs/`, `issues/`, `roadmap/` |
| "Is this transient (a session note, a retro)?" | Plain markdown | `docs/sessions/` (indexed via universal extractors only) |
| "Do I want cross-modal edges (design↔code rationale, semantic similarity, community clusters) that no other ingest pass produces?" | **External graph cache** (see Form 7) | Run `graphify .` then `rmx graphify-warm .` |

If multiple forms could fit, prefer the form *higher* in the table —
it ranks higher on the discovery ladder.

## Form 1 — ADR (Architecture Decision Record)

Full reference: `docs/adr-format.md`. The contract in brief:

**File path:** must match `<some-dir>/adr/NNNN-kebab-title.md` where
`NNNN` is zero-padded.

**Required header** (before first `## ` section):

```markdown
# ADR-0087: Spatial Zone Geometry Standard

Status: Accepted
Governs: Zone, BBOX, POLYGON, geometry operations
Cross-references: ADR-0043, ADR-0066

## Context
...
```

**What rmx extracts:**

| Header field | Linkage emitted | Notes |
|---|---|---|
| `Status` | (weight only) | `Accepted=1.0`, `Proposed=0.3`, `Superseded=0` (silent) |
| `Governs: A, B` | `mentions:A→ADR`, `mentions:B→ADR` | only CamelCase tokens; prose is ignored |
| `ADR-NNNN` anywhere | `related_to` between ADRs | mediated by `adr/NNNN` namespaced concept |
| Fenced class spec | `defines:ClassName→child entity` | see below |
| Subclass tree | `is_a:Parent→Child entity` | see below |

**Class spec pattern** (use fenced code blocks):

````markdown
```
Zone:
  type: BBOX | POLYGON
  area -> float
  centroid -> Point
  contains_point(point) -> bool
  overlaps(other, threshold=0.5) -> bool
```
````

**Subclass tree pattern:**

```
Zone (base)
  +-- AnnotatedZone(Zone)
  +-- ScoredZone(Zone)
  +-- DetectionZone(ScoredZone, AnnotatedZone)
```

**Authoring rules:**

1. Set `Status: Accepted` only when the decision is binding. Use
   `Proposed` while in review; rmx weights it lower so it doesn't
   outrank Accepted ADRs in concept search.
2. List every authoritative concept in `Governs:` using CamelCase.
   "Zone geometry operations" → write `Governs: Zone, BBOX, POLYGON`
   not `Governs: Zone geometry operations`.
3. Reference related ADRs as literal `ADR-NNNN`, not "ADR 87" or
   "the spatial ADR". The regex is `\bADR-\d{4}\b`.
4. Put class specs in fenced code blocks. Indented blocks under a
   heading also work but are easier to break.
5. Use `Child(Parent)` form for inheritance, not English prose.
6. To retire an ADR: set `Status: Superseded`. rmx zeros all its
   linkages on the next ingest — no need to delete the file.

**Template:** `docs/templates/adr-template.md` (when created).

## Form 2 — Concept doc

A concept doc canonically *defines* one or more named concepts.
Filename and structure carry the meaning.

**File path:** prefer `docs/architecture/concepts/<concept>.md`
(case-sensitive `concepts/` directory). Filename = primary concept
in kebab-case (`spatial-zone.md` defines `SpatialZone`).

**Structure rmx will extract** (parser implementation pending — see
*Indexing status* below):

```markdown
# Spatial — Entities, Hierarchy, Containment

Brief one-paragraph definition of the primary concept.

## Some narrative section (H2 — prose, not indexed)

### World

Definition of World. Each H3 with a single CamelCase title is a
sub-concept and becomes `defines:World → this-doc::World`.

### Zone

A Zone **subclasses** Area, adding reactive behavior. The word
"subclasses" between two CamelCase tokens is a recognized
inheritance signal: `is_a:Area → this-doc::Zone`.

### Place

A Place subclasses Zone, adding domain activity context.
```

**Authoring rules:**

1. One canonical concept per H3. Don't pack multiple definitions
   under one H3.
2. H3 titles: single CamelCase word for the primary concept.
   Subtitles or commas in the H3 hurt extraction.
   - Good: `### Zone`
   - Tolerable: `### Zone (reactive area)` — first CamelCase token wins
   - Bad: `### Zones, Places, and Stations` — multiple concepts in one H3
3. To declare inheritance, use the literal word `subclasses` or
   `extends` followed by a CamelCase parent name anywhere in the H3
   body. The child is the H3 concept. Both of these work:
   - `Zone subclasses Area, adding reactive behavior.`
   - `A zone subclasses Area, adding reactive behavior.` (lowercase
     subject — child is taken from the H3 title)
   Avoid synonyms ("is a kind of", "specializes") — the parser only
   recognizes the literal `subclasses` and `extends` verbs.
4. H1 = the doc's top-level concept. Filename should match. If they
   differ, filename wins for indexing.
5. Cross-reference other concept docs by their concept name, not by
   relative path. rmx joins on the concept, not the path.

**Self-check after writing:**

```bash
rmx ingest .
rmx context <YourConcept>     # should return your doc
rmx neighbors <docs/.../yourdoc.md>   # non-zero
```

## Form 3 — Design doc

A design doc records context, exploration, or proposals that aren't
binding decisions. Less structured than ADRs, less canonical than
concept docs, but still indexable if you follow conventions.

**File path:** `docs/design/<topic>.md`.

**Recommended header** (immediately under H1):

```markdown
# Architecture Tenets Catalog

**Created:** 2026-02-22
**Source:** docs/architecture/rewrite-principles.md
**Referenced by:** CLAUDE.md, MEMORY.md
**Companion:** docs/architecture/bedrock.md

Brief paragraph summarizing the doc's purpose.
```

**What rmx will extract** (parser pending):

| Bold-labeled line | Linkage emitted |
|---|---|
| `**Source:** path/to/x.md` | `related_to` between this doc and target file |
| `**Referenced by:** path.md, other.md` | `related_to` to each target |
| `**Companion:** path.md` | `related_to` |
| `**Implements:** ADR-NNNN` | `related_to` via `adr/NNNN` concept |
| `**Supersedes:** path.md` | `related_to` (semantic intent: replacement) |

**Authoring rules:**

1. Put bold-labeled metadata in the first 30 lines of the doc.
   rmx stops scanning for header refs after the first `## ` section.
2. Target paths in metadata are project-relative, not URLs.
3. Comma-separated lists are split.
4. If you reference an ADR, use the literal `ADR-NNNN` form —
   it auto-links to the ADR entity if indexed.
5. Concept references inside design-doc *prose* are not extracted.
   If a design doc is the authoritative definition of a concept,
   promote it to a concept doc (move to `concepts/`).

## Form 4 — `.pseudo` file

Type-first specification of system behavior, data structures, APIs.
Full reference: `docs/pseudo-format.pseudo`. Brief contract:

```pseudo
# Title — One-Line Purpose

TypeName:
    field_name: type
    other_field: list[OtherType]

EnumName:
    VALUE_ONE
    VALUE_TWO

function_name(param: Type) -> ReturnType:
    body_pseudocode
```

**What rmx extracts** (already wired):

- `defines:<TypeName>` and `defines:<function_name>` for every
  top-level declaration.
- `mentions:<OtherType>` for type references in fields, params,
  return types.
- `calls:<other_function>` for function calls inside bodies.
- `imports:<module>` for `from module import ...` lines.

**Authoring rules:**

1. Types are `PascalCase`, functions are `snake_case`, enum values
   are `UPPER_CASE`. The regexes depend on case.
2. Top-level definitions live at column 0. Fields and body are
   indented (any consistent indent — 2 or 4 spaces).
3. Builtin types (`string`, `int`, `bool`, `list`, `dict`, etc.)
   are filtered out — they don't pollute the concept graph.
4. Prefer happy-path bodies. Error handling belongs in
   `contracts.pseudo` or implementation code.

## Form 5 — GMD (Graph Markdown)

A doc-as-graph format. Each `{#id}` heading becomes its own walkable
node; `rel:` lines emit typed linkages between nodes. Use it when the
content is a graph of small pieces that should be retrievable
individually — e.g. an architecture knowledge base, a decision graph
with `supports` / `contradicts` / `supersedes` edges, a checklist
where each step depends-on another.

**File path:** either a `.gmd` extension, or a `.md` file with
`gmd:` in the YAML frontmatter. Sync sniffs the first 512 bytes for
`gmd:` so a .md file lit up via frontmatter is dispatched to the
GMD ingester instead of the generic doc path.

**Minimal example:**

```markdown
---
gmd: "0.1"
id: spatial-zone-thinking
title: "Spatial Zone — Design Reasoning"
imports: [adr/0087]
---

# Zone Geometry — Reasoning Trail {#root}

## Why polygons over rectangles {#polygon-choice}

rel: derives-from -> adr/0087
rel: supports -> [[polygon-implementation]]

Polygons capture occlusion better than BBOXes. See [[bbox-trade]] for
the rejected alternative.

## BBOX trade-off {#bbox-trade}

rel: contradicts -> [[polygon-choice]]
rel: instance-of -> #rejected-alternative

BBOXes pack denser but lose precision at polygon corners.

## Polygon implementation notes {#polygon-implementation}

rel: defined-in -> src/viascope/spatial/shapes.py
rel: depends-on -> adr/0087 {weight=0.8}
```

**What rmx extracts:**

| Construct | Linkage emitted |
|---|---|
| `{#node-id}` after a heading | `doc` entity, name `<doc-id>#<node-id>` |
| Heading hierarchy | implicit `part-of` from child to direct parent |
| `rel: <verb> -> <target>` | linkage `<verb>` from current node to target; auto-creates the linkage type if new |
| `rel: <verb> -> [[ref]]` | same, resolving `[[ref]]` to an indexed node id or wikilink target |
| `{weight=0.8}` attribute on a rel line | sets the link weight |
| `alias=[foo, bar]` attribute on heading | each alias → `mentions:<alias>` concept |
| `[[ref]]` outside `rel:` lines | `mentions` linkage to the referenced node |
| Frontmatter `imports: [a, b]` | `imports` linkage on the doc-level entity |
| Title tokens (CamelCase / multi-char identifiers) | `mentions` concepts for retrieval |

**Recommended verbs** (auto-registered; use these before inventing new ones):
`supports`, `contradicts`, `derives-from`, `supersedes`, `depends-on`,
`instance-of`, `part-of`, `mentions`, `defines`, `example-of`,
`parent`, `defined-in`, `evidence-for`, `motivates`, `solves`.

**Authoring rules:**

1. One `{#id}` per heading you want walkable. Skip the marker on
   headings that are only structural.
2. Node ids are kebab-case; lowercase + digits + `._/-`. Don't
   namespace by hand (`zone/origin` is fine, `spatial/zone/origin` is
   also fine — paths inside the doc are free-form).
3. `rel:` must be at the start of a line, no leading spaces, no
   indent — it's parsed line-by-line, not as Markdown.
4. Prefer the recommended verbs. Custom verbs work (auto-registered)
   but reduce cross-doc traversal payoff.
5. `[[ref]]` resolves first as a node id within the current doc, then
   as `<other-doc>#<node>` if `imports:` declares it. Unresolved refs
   become `mentions` concepts so they're at least retrievable.
6. Re-ingest is destructive per file — sync purges the doc's previous
   entities before re-walking it. Cross-doc refs in the same sync
   batch resolve correctly because GMD paths are batched and ingested
   together (see `sync.py`).

**Self-check after writing:**

```bash
rmx ingest-gmd <path-to-doc.gmd>
rmx context <doc-id>#<node-id>     # should return your node + neighbors
rmx neighbors <doc-id>#<node-id>   # walks the typed rels you declared
```

## Form 6 — Plan / spec / issue doc

A markdown doc that **declares intent** for code or design that should
exist but may not exist yet. Plans, specs, issues, and roadmap items
behave identically to concept docs structurally — H1 + H3 headings and
fenced class specs all extract — but the **verb flips from `defines`
to `specifies`**, with inverse `specified_by`.

This closes a critical authority-hierarchy gap: a plan that names a
concept *before* code exists for it now becomes discoverable via
`rmx query "specifies:Foo"`, so an agent doesn't reimplement what was
already designed (the failure mode that motivated this edge type:
ADR-0087 specified `Zone` across 52 sessions; agents never found the
spec and built five fragmented alternatives instead).

**Trigger conditions** (either matches → plan-doc path):

| Trigger        | Matches                                                  |
|----------------|----------------------------------------------------------|
| Filename       | `^(PLAN\|ISSUE\|SPEC\|ROADMAP)([-_].*)?\.md$` (case-insensitive) |
| Path segment   | any of `plans/`, `plan/`, `specs/`, `spec/`, `issues/`, `issue/`, `roadmap/` |

**Minimal example:**

```markdown
# ZoneOverhaul

Replace the legacy region machinery with first-class Zone classes.

## Components

### Zone

The base class with BBOX + POLYGON support.

### AnnotatedZone

A Zone that carries attribute metadata.

A place subclasses Zone.

## Class shape

```
Zone:
  type: BBOX | POLYGON
  area -> float
  contains_point(point) -> bool
```
```

**What rmx extracts:**

| Construct                                  | Linkage emitted                              |
|--------------------------------------------|----------------------------------------------|
| Filename stem (kebab → PascalCase)         | `specifies:<Concept> → doc entity`           |
| H1 first CamelCase token                   | `specifies:<Concept> → doc entity`           |
| H3 PascalCase headings                     | `specifies:<Concept> → child entity` per H3  |
| `Foo subclasses Bar` in H3 prose           | `is_a:Bar → Foo` (cross-spec inheritance)    |
| Fenced class spec (`Name:` + indented body)| `specifies:<Concept>` (weight 0.5)           |

**Authoring rules:**

1. Use one of the trigger names/dirs above. A markdown file outside
   them stays in the concept-doc path (`defines`, not `specifies`).
2. Plan-docs ARE concept docs structurally — same H1+H3+fenced-class
   extraction. Just the verb changes.
3. If the plan is GMD-formatted (with `gmd:` frontmatter), use
   author-declared `rel: specifies -> [[#Concept]]` instead — both
   paths emit the same `specifies` linkage type.
4. A plan that gets implemented should leave the plan-doc in place;
   the `specifies:Foo` edge stays valid and is now joined by
   `defines:Foo` from the code. Queries like
   `defines:Foo AND specifies:Foo` then surface intent + impl together.

**Self-check after writing:**

```bash
rmx query "specifies:<Concept>"      # should return your plan doc
rmx neighbors <plan-doc-path>        # should list the specified concepts
rmx query "specifies:<X> AND NOT defines:<X>"   # finds unimplemented specs
```

## Form 7 — Graphify knowledge graph

Not a doc form you author — a *cache* refmatrix consumes. Graphify is an
external tool that walks any folder of files and produces a community-
detected NetworkX graph at `graphify-out/graph.json`. rmx reads that
graph as a third ingest source (alongside llm-tldr's `metadata.json` and
`call_graph.json`), layered additively on top of whatever the primary
source produced.

**Why it matters:** graphify extracts edges no other rmx pass can —
`rationale_for` (design→code), `semantically_similar_to`,
`conceptually_related_to`, `shares_data_with`, plus community clusters.
On the refmatrix self-eval (20 NL queries, see
`eval/run_graphify_eval.py`), graphify takes coverage from 19/20 →
**20/20**: it catches the one query baseline can't.

**Workflow:**

```bash
graphify .                       # produces graphify-out/graph.json
rmx graphify-warm .              # ingests it
# or in one shot, source=auto layers graphify on top:
rmx tldr-warm . --semantic       # primary ingest
rmx ingest . --source graphify   # additive graphify pass
```

**Verb mapping** (graphify relation → rmx linkage type):

| Graphify relation         | rmx linkage type    | Notes                                |
|---------------------------|---------------------|--------------------------------------|
| `calls`                   | `calls`             |                                      |
| `contains`                | `has-part`          | inverted from graphify's direction   |
| `inherits`                | `is_a`              |                                      |
| `implements`              | `defines`           |                                      |
| `references`              | `mentions`          |                                      |
| `uses`                    | `depends-on`        |                                      |
| `cites`                   | `related_to`        |                                      |
| `method`                  | `has-part`          |                                      |
| `rationale_for`           | `specifies`         | **key alignment** — design→code intent |
| `conceptually_related_to` | `related_to`        |                                      |
| `semantically_similar_to` | `similar_to`        | auto-registered on first encounter   |
| `shares_data_with`        | `shares_data_with`  | auto-registered                      |

**Confidence weighting:** graphify tags each edge `EXTRACTED` (1.0×),
`INFERRED` (0.5×), or `AMBIGUOUS` (0.3×). The multiplier composes with
the edge's own `weight` × `confidence_score`, so INFERRED edges land in
the index but are down-weighted in the scorer.

**Entity naming:** graphify nodes become entities prefixed `graphify::`
(e.g., `graphify::daemon_py`) so they don't collide with tree-walked
entities (`src/refmatrix/daemon.py`). Both surface in `rmx grep`
results; the discovery ladder treats them as different evidence routes
to the same underlying file.

**Self-check after warming:**

```bash
rmx stats                              # entity count should jump by ~graphify's node count
rmx query "specifies:gf/<some-node>"   # walks rationale_for edges
rmx query "calls:gf/<func>"            # graphify-derived call graph
```

## Universal conventions (apply to every doc form)

These work everywhere — ADR, concept doc, design doc, even plain
markdown — and are recommended whenever the situation fits.

### 1. Class specs in fenced code blocks

Any fenced code block at any indent containing a `Name:` line at
column 0 followed by an indented body is parsed as a class spec
(currently in ADRs; extending to all markdown). Use it whenever
you want a concept to be `defined` by your doc.

````markdown
```
Region:
  bounds: BBOX
  refine(point) -> Point
```
````

### 2. ADR cross-references

`ADR-NNNN` anywhere in any doc creates a `related_to` link if the
target ADR is indexed. Use the exact form — not `ADR 87`, not
`ADR.0087`, not `#0087`.

### 3. Subclass tree notation

`+-- Child(Parent)` in any code block or indented region produces
`is_a:Parent → Child`. Works in ADRs today; extending to all docs.

### 4. Use the concept's canonical name

If the project defines a concept named `Zone`, write `Zone`, not
"zone", "zones", `Zone (in spatial)`, or "the zone construct". The
indexer matches case-sensitive exact tokens; variants don't join.

### 5. Don't redefine concepts in prose

If a concept already has a canonical concept-doc or ADR, *reference*
it, don't redefine it inline. Redefinition fragments the graph: two
"Zone"s with conflicting definitions and no `same_as` link.

## Anti-patterns — do not do these

| Anti-pattern | Why it breaks indexing |
|---|---|
| Italic concept names: `*Zone*` instead of `` `Zone` `` | Won't match parser regexes; reads as prose. |
| Plural concept refs: `Zones`, `zones` | Indexer is case- and exact-token sensitive. |
| Concept defs inside long prose paragraphs | No structural anchor for the parser. |
| Mixing concepts in one H3: `### Zone, Place, and Station` | Only first token extracts; others are lost. |
| ADR refs as text: "see ADR 87" or "ADR #0087" | Regex won't match. |
| Inheritance as prose: "Zone is a kind of Area" | Parser only recognizes `subclasses`, `extends`, or `Child(Parent)` form. |
| Filename mismatch: doc `regions.md` defines `Region` | Filename drives concept-doc indexing; rename or use H1 override. |
| Forgetting `Status:` in an ADR | Defaults to weight 0.3 — won't win against Accepted ADRs. |
| Using `Status: Superseded` to "soft delete" | rmx zeros all linkages. The doc is silent. (This is intended — confirm before using.) |
| Mass concept dumps in tables without structure | Tables aren't yet parsed; convert to H3 sections. |

## Self-verification — confirm your doc is indexed

After authoring a doc and running `rmx ingest .`:

```bash
# 1. Is the doc registered as an entity?
rmx list-entities --filter "<your-filename>"

# 2. Does concept search surface it?
rmx context <YourPrimaryConcept>

# 3. Does it have outbound linkages?
rmx neighbors <relative/path/to/your/doc.md>

# 4. Walk the evidence for one linkage:
rmx explain <entity-id>
```

If `neighbors` returns zero edges and `context` doesn't surface
the doc, the parser found no structure to extract from. Re-read
the relevant Form section above and fix the shape.

## Indexing status

| Form | Status |
|---|---|
| ADR markdown | **Indexed** — header fields, class specs, subclass trees, cross-refs (weight by Status) |
| `.pseudo` files | **Indexed** — types, functions, calls, imports, type refs |
| Concept docs | **Indexed** — filename, H1, H3 sub-concepts, subclass/extends prose, ADR refs |
| Design docs | **Indexed** — bold-labeled metadata refs, ADR refs, fenced class specs (weight 0.5) |
| GMD (`.gmd` / `.md` with `gmd:` frontmatter) | **Indexed** — `{#id}` nodes, `rel:` typed verbs, heading `part-of`, wikilinks, alias mentions, frontmatter `imports:` |
| Plan / spec / issue (`PLAN-*.md`, `ISSUE-*.md`, `SPEC-*.md`, `ROADMAP-*.md`, or under `plans/`, `specs/`, `issues/`, `roadmap/`) | **Indexed** — same H1+H3+fenced-class shape as concept docs, but emits `specifies` (+ inverse `specified_by`) instead of `defines`; agent can query `specifies:X AND NOT defines:X` for unimplemented specs |
| JavaScript / TypeScript (`.js`, `.ts`) | **Indexed** — JSDoc as docstring; function / arrow / class / object-method names; param + callee identifiers via the eval-side `js_extract` (regex-first cut, no tree-sitter) |
| Graphify cache (`graphify-out/graph.json`) | **Indexed** — nodes → `graphify::<id>` entities + `gf/<id>` concepts; edges → linkages with file:line evidence; `rationale_for` → `specifies`, `inherits` → `is_a`, `implements` → `defines`, `semantically_similar_to` → `similar_to`, etc. Confidence-weighted (`EXTRACTED` 1.0, `INFERRED` 0.5, `AMBIGUOUS` 0.3). Layered additively on top of the primary tldr/tree ingest |
| Plain markdown | **Universal extractors apply** — ADR refs and fenced class specs extract from any markdown |

All forms now indexed. Universal extractors (fenced class specs,
ADR-NNNN refs) run on every markdown file regardless of location, so
even a plain prose doc gets some signal if it contains a fenced
`Name:` block or references an ADR.

## Storage backend (operational note for hooks / CI)

The catalog backend defaults to **DuckDB** as of 2026-05-16. Auto-
detection at `Store.__init__`:

- `.refmatrix/catalog.duckdb` present → DuckDB.
- only `.refmatrix/catalog.db` present → SQLite (legacy stores keep working).
- empty directory → DuckDB (fresh stores).

Override explicitly with `RMX_BACKEND=duckdb|sqlite` or
`Store(..., backend=...)`. Use `rmx migrate-to-duckdb` to one-shot
copy a SQLite catalog (catalog tables + on-disk fragment files) into
a native DuckDB catalog alongside the SQLite one. The SQLite file is
not deleted — verify reads against the new catalog before removing.

Ingest performance: hot loops in `_ingest_python_semantics` flush
links via `Store.bulk_link(items)`, which uses an Arrow batch under
DuckDB and `executemany INSERT OR IGNORE` under SQLite. Measured
speedup vs per-row `link()`: 600-1000× on DuckDB at N=5000 links,
80× on SQLite. Doc-authoring rules don't change — this is just why
ingest got fast.

## When in doubt

1. Read the form-specific reference (`adr-format.md`,
   `pseudo-format.pseudo`).
2. Copy from a template (`docs/templates/`).
3. Inspect a known-good example with `rmx explain <entity-id>` to
   see what linkages it produced.
4. If a concept isn't surfacing where you expect, the doc is
   probably wrong — not the indexer. Fix the doc shape.
