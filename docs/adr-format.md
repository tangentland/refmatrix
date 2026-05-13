# ADR Format Reference

Architecture Decision Records (ADRs) are markdown files that record
*why* a system is shaped the way it is. rmx treats ADRs as
first-class authority: an ADR specifying a class outranks pseudocode
and code that implements it. The discovery ladder is:

```
ADR > concept doc > pseudocode > code
```

For that ordering to hold, ADRs must be semantically indexed — not
just registered as opaque files. This document describes the
structure rmx's ADR extractor parses, and what linkages each part
emits.

## Detection

A markdown file is treated as an ADR when both:

1. Its filename matches `NNNN-*.md` (four-digit zero-padded number).
2. Its path contains a directory segment named `adr` (case-insensitive).

Typical layout:

```
docs/
  architecture/
    adr/
      0001-channel-as-universal-primitive.md
      0087-spatial-zone-geometry-standard.md
      ...
```

Non-ADR markdown files (READMEs, design docs outside `adr/`) are
indexed as `doc` entities but get no ADR-specific extraction.

## Required header

The top of every ADR is a YAML-ish key/value block, ending at the
first `## ` section heading. Fields rmx reads:

| Field             | Required | Effect                                                       |
|-------------------|----------|--------------------------------------------------------------|
| `Status`          | yes      | Controls linkage weight. See *Status weighting* below.       |
| `Governs`         | no       | Comma-separated concepts the ADR is authoritative for.       |
| `Cross-references`| no       | ADR-NNNN ids this ADR depends on or relates to.              |

Other header fields (`Date`, `Authors`, `Tags`, etc.) are preserved in
the entity but produce no linkages.

Example header:

```markdown
# ADR-0087: Spatial Zone Geometry Standard

Status: Accepted
Date: 2026-04-16
Governs: Zone coordinate representation, geometry operations, BBOX, POLYGON
Cross-references: ADR-0043, ADR-0066

## Context
...
```

## Status weighting

`Status` controls linkage weight. Accepted ADRs win ranking ties
against weaker sources; Proposed ADRs are weaker signals; Superseded
ADRs are silent.

| Status        | Weight | Linkages emitted? |
|---------------|--------|-------------------|
| `Accepted`    | 1.0    | yes               |
| `Proposed`    | 0.3    | yes               |
| `Draft`       | 0.2    | yes               |
| `Superseded`  | 0.0    | **no**            |
| `Deprecated`  | 0.0    | **no**            |
| `Rejected`    | 0.0    | **no**            |
| (any other)   | 0.3    | yes               |

Promoting an ADR to `Accepted` and re-running `rmx ingest` raises its
weight; retiring an ADR to `Superseded` zeroes its influence on the next
ingest.

## What the extractor emits

### 1. ADR entity per file

Every detected ADR becomes a `doc` entity:

- `name` = repo-relative path (`docs/architecture/adr/0087-...md`)
- `meta.adr_number` = `"0087"`

This is the entity that `rmx context Zone` will surface alongside
pseudo/code definitions.

### 2. `mentions` from `Governs` tokens

The `Governs:` line is scanned for CamelCase tokens (≥3 chars, not
builtin types). Each becomes a concept linked to the ADR entity with
`mentions`, weight = status weight.

```
Governs: Zone coordinate representation, BBOX operations
```

Emits: `mentions:Zone → ADR-0087`, `mentions:BBOX → ADR-0087`.

Lowercase prose ("coordinate representation", "operations") is
ignored — it produces noise, not signal.

### 3. `related_to` between ADRs

Every `ADR-NNNN` reference anywhere in the body resolves to the
target ADR entity (if also indexed). Each reference creates an
`adr/NNNN` namespaced concept and links both ADR entities via
`related_to`.

This lets you ask:

```
rmx neighbors "docs/architecture/adr/0087-...md"
```

…and see related ADRs as edges. The `adr/NNNN` concept hub also
means cross-references survive re-ingest order — the linkage is
mediated by a stable concept, not a direct entity-to-entity edge.

### 4. `defines` + `is_a` for class specs

ADRs frequently contain pseudocode-style class specs, in fenced code
blocks **or** in indented blocks under a section heading:

````markdown
## Decision

```
Zone:
  type: BBOX | POLYGON
  area -> float
  centroid -> Point
  contains_point(point) -> bool
  overlaps(other, threshold=0.5) -> bool
```
````

The extractor recognizes a class block by a PascalCase identifier at
column 0 followed by an indented body. For each class found:

- Creates a child entity named `<rel-path>::<ClassName>` (kind: `doc`).
- `defines:<ClassName>` → child entity (weight = status weight).
- `mentions:<MethodName>` → child entity for each method line.
- `mentions:<TypeRef>` → child entity for each CamelCase type
  reference in field annotations, params, return types.

#### Subclass syntax — inline

```
Zone:
  ...
AnnotatedZone(Zone):
  annotation: string
ScoredZone(Zone):
  score: float
```

Emits: `is_a:Zone → AnnotatedZone entity`, `is_a:Zone → ScoredZone entity`.

#### Subclass syntax — tree

```
Zone (base)
  +-- AnnotatedZone(Zone)
  +-- ScoredZone(Zone)
  +-- DetectionZone(ScoredZone, AnnotatedZone)
```

Each `+-- Child(Parent[, Parent2...])` line emits:
- `defines:Child → Child entity`
- `is_a:Parent → Child entity` for every parent listed

### 5. Evidence trail

Every emitted linkage records a `linkage_evidence` row with the
ADR's file path, line number, and a human-readable detail
(`ADR-0087 class Zone`, `Governs: Zone`, `references ADR-0043`).

`rmx explain <entity_id>` and `rmx neighbors --evidence` surface
these so you can trace any linkage back to the exact line that
produced it.

## What is NOT extracted

Out of scope for the extractor (parsed as prose only):

- Free-text `## Context`, `## Decision`, `## Consequences` sections —
  the prose is searchable as full text but produces no linkages.
- Pseudocode at column 0 outside a class block (loose functions).
- Decision tables, ASCII diagrams, sequence diagrams.
- External links (URLs to other docs, Confluence pages).

If you need a concept-level reference from prose, name it in the
`Governs:` line.

## Authoring checklist

Before committing an ADR that should be discoverable through rmx:

- [ ] Filename matches `NNNN-kebab-title.md`, in an `adr/` directory.
- [ ] `Status:` set (defaults to `Proposed` weight if missing).
- [ ] `Governs:` lists every concept the ADR is authoritative for, as
      CamelCase identifiers.
- [ ] Concrete classes / interfaces specified in fenced code blocks
      with `Name:` at column 0 and indented methods/fields.
- [ ] Subclass hierarchies use `Child(Parent)` or `+-- Child(Parent)`
      tree notation, not English ("AnnotatedZone extends Zone").
- [ ] Related ADRs referenced inline as `ADR-NNNN` (not "ADR 87").

After commit, re-ingest to refresh the index:

```bash
rmx ingest .
```

Then verify:

```bash
rmx context <ConceptName>     # ADR should appear in results
rmx neighbors <adr-path>      # non-zero edge count
```

## Worked example

See `docs/templates/adr-template.md` for a minimal copy-paste
starter that exercises every linkage type.
