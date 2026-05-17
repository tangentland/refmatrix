# Problem: ADR files are indexed but semantically invisible

## Summary

rmx ingests ADR markdown files as entities (57 ADR entities in catalog) but
extracts zero semantic linkages from them. An ADR that specifies a concrete
class (e.g., ADR-0087 specifies `Zone` with 20+ methods) produces no
`defines:Zone` linkage. The concept `Zone` resolves only to `spatial.pseudo`
— the ADR that designed it is invisible to the discovery ladder.

## Impact

This is a critical gap. The viascope project has 100+ ADRs, ~50 Accepted,
many specifying concrete classes, interfaces, and data structures. The
project's authority hierarchy is:

```
ADR > concept doc > pseudocode > code
```

But rmx's semantic extraction treats ADRs as opaque prose. An agent using
the discovery ladder (`rmx context` → `rmx query` → `tldr` → `grep`) will
find pseudocode definitions and code definitions but will NEVER find the ADR
that specifies the authoritative design.

**Real-world consequence (session 53, 2026-05-13):** ADR-0087 (Spatial Zone
Geometry Standard, Accepted 2026-04-16) specifies a `Zone` base class with
BBOX+POLYGON support, 20+ geometric methods, a 4-class subclass hierarchy,
format conversion, and serialization. It was never implemented across 52
sessions. Five fragmented alternatives were built instead — each agent
pattern-matched against existing code and never found the ADR. When an agent
searched `rmx context Zone`, it got `spatial.pseudo::Region` — not ADR-0087.

## Current behavior

```
$ rmx neighbors "architecture/adr/0087-spatial-zone-geometry-standard.md"
# cardinality=0 — zero linkages
```

The ADR entity exists but has no edges. It participates in no queries. It
cannot be found by concept search. It is dead weight in the index.

## What ADR semantic extraction needs to capture

ADR markdown files have a predictable structure that can be parsed:

1. **Status** — `Status: Accepted|Proposed|Superseded`. Only Accepted ADRs
   should produce strong linkages. Proposed = weaker signal.

2. **Concrete class/interface specs** — ADRs frequently contain pseudocode
   blocks or structured descriptions like:
   ```
   Zone:
     type: BBOX | POLYGON
     area -> float
     centroid -> Point
     contains_point(point) -> bool
     overlaps(other, threshold=0.5) -> bool
   ```
   These should produce `defines:Zone` linkages with the ADR entity as source.

3. **Cross-references** — ADRs reference other ADRs by number (`ADR-0043`,
   `ADR-0066`). These should produce `related_to` linkages between ADR
   entities.

4. **Governs** — The header line `Governs: Zone coordinate representation,
   geometry operations, ...` names the concepts the ADR is authoritative for.
   These should produce `defines` or `mentions` linkages.

5. **Subclass hierarchies** — ADRs specify inheritance:
   ```
   Zone (base)
     +-- AnnotatedZone(Zone)
     +-- ScoredZone(Zone)
     +-- DetectionZone(ScoredZone, AnnotatedZone)
   ```
   These should produce `is_a` linkages.

## Desired behavior

After semantic extraction:

```
$ rmx context Zone
# Returns ADR-0087 as a defining entity, alongside spatial.pseudo and any
# code files that implement it

$ rmx query "defines:Zone"
# Returns ADR-0087, spatial.pseudo, src/viascope/spatial/shapes.py

$ rmx neighbors "architecture/adr/0087-..."
# Returns Zone, AnnotatedZone, ScoredZone, DetectionZone as defined concepts
# Returns ADR-0043, ADR-0066, ADR-0069 as related_to entities
```

An agent running `rmx context Zone` before writing a new spatial class would
see "ADR-0087 specifies this — read it first" and follow the architecture
instead of inventing from scratch.

## Proposed approach

Add an ADR-aware extractor to the ingestion pipeline. When ingesting
`docs/architecture/adr/*.md`:

1. Parse the YAML-style header for Status, Governs, Cross-references.
2. Scan code blocks and indented structure definitions for class/method names.
3. Emit `defines` linkages for each concrete class/interface/enum found.
4. Emit `related_to` linkages for each `ADR-NNNN` cross-reference.
5. Emit `mentions` linkages for concepts named in the Governs line.
6. Weight Accepted ADRs higher than Proposed in ranking.

The extractor should handle both fenced code blocks (```...```) and
indented pseudocode blocks (common in viascope ADRs).

## Priority

CRITICAL. Without this, the discovery ladder structurally cannot enforce the
project's authority hierarchy. Every new session will repeat the ADR-0087
failure pattern — agents will build from code patterns instead of from
architecture because the architecture is invisible to their primary
discovery tool.
