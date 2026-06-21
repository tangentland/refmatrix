---
gmd: "0.1"
id: adr-0000-adr-overview
title: "ADR-0000: Architecture Decision Records — rules + index"
tags: [adr, meta]
---

# ADR-0000: Architecture Decision Records {#root}

> Status: Living Document · Last Updated: 2026-06-20

Architecture Decision Records for refmatrix. This page is the authoring rules and
the index. The prose rules are loose by design — what is **required** is three
things: **crosslinking**, **structure**, and **findability**. GMD is the one
mechanism that delivers all three at once, so **every ADR is a GMD doc**. That keeps
ADRs graph-indexable by rmx (`ADR > concept doc > pseudocode > code` in the discovery
ladder; see [[adr-format]] for the extractor's header view).

rel: catalogs -> [[adr-0002-subject-memory-container]]
rel: related-to -> [[adr-format]]

## The three requirements {#requirements}

- **Crosslinking {#crosslinking}.** Every ADR wires into the graph with `rel:` edges —
  to the ADRs/concepts/memories it depends on, refines, supersedes, or amends.
  Supersession and amendment are typed edges (`rel: supersedes -> [[adr-NNNN-...]]`,
  `rel: amends -> [[...]]`), never bare prose, so lineage is walkable. An ADR with no
  edges is a red flag, not a finished ADR.
- **Structure {#structure}.** A `{#anchor}` on every heading makes each
  section an addressable node (cite `[[adr-NNNN#decision]]`, not "see the ADR"). Use a
  consistent skeleton — `Context` → `Decision` → `Consequences` (+ `Alternatives`,
  `Open questions`, `Implementation` as needed) — so readers and agents land on the
  part they need.
- **Findability {#findability}.** Stable address + discoverability: file
  `docs/adr/NNNN-slug.md` (4-digit), frontmatter `id` = `adr-NNNN-slug`, wikilink
  `[[adr-NNNN-slug]]`, listed in the [#index] below. rmx ingests the GMD so the ADR
  surfaces via `context` / `recall` / `neighbors` — found by query, not just by path.

## Mechanics {#mechanics}

- **GMD {#gmd-required}.** `gmd: "0.1"` frontmatter with `id` + `title` +
  `tags: [adr, ...]`. Validate: `python3 ~/claude_tools/gmd/lint.py <path>` → zero
  errors. (This is how the three requirements above are enforced, not a fourth rule.)
- **Header line {#header}.** Under the H1: `**Status:** X · **Date:** Y ·
  **Implementation:** Z`.
- **Status lifecycle (loose) {#status}.** `Proposed → Accepted → Superseded | Amended`.

## Index {#index}

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-intuition-lance-integration.md) | Intuition memory layer + Lance vector backend | Proposed (pre-GMD, grandfathered) |
| [[adr-0002-subject-memory-container]] | Subject: memory-scoped working/durable container | Proposed |

> ADR-0001 predates the GMD-required rule (it uses the extractor's key/value header
> from [[adr-format]]). Grandfathered; convert to GMD on next substantive edit.
