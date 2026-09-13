---
gmd: "0.1"
id: INDEX
title: "refmatrix docs — curated catalog"
tags: [index, catalog, docs]
---

# refmatrix docs — curated catalog {#root}

One row per GMD doc under `docs/`. Ids are filename stems; every doc is
walkable via `rmx context <id>` / `rmx neighbors <id>#root`.

## Core docs {#core}

rel: catalogs -> [[SYSTEM]]
rel: catalogs -> [[ARCHITECTURE]]
rel: catalogs -> [[INTEGRATION]]
rel: catalogs -> [[PERFORMANCE]]
rel: catalogs -> [[system_design_review]]

| Doc | Hook |
|-----|------|
| [[SYSTEM]] | What refmatrix is: bitmap reference matrix, discovery ladder, lifecycle, use cases |
| [[ARCHITECTURE]] | Module layout, dependency graph, catalog schema, daemon/concurrency, CLI tree |
| [[INTEGRATION]] | Everything touching the outside: llm-tldr, git + Claude Code hooks, GMD ingest, watcher, socket protocol |
| [[PERFORMANCE]] | Where the speed comes from, scoring stack, honest CSN production harness (0.961), MemAware proactive-retrieval benchmark, measured negatives |
| [[system_design_review]] | Staff-level system design interview reconstructed for refmatrix (v0.60.x, with the scars) |

## ADRs {#adrs}

rel: catalogs -> [[adr-0000-adr-overview]]
rel: catalogs -> [[0001-intuition-lance-integration]]
rel: catalogs -> [[adr-0002-subject-memory-container]]

| Doc | Hook |
|-----|------|
| [[adr-0000-adr-overview]] | ADR authoring rules (crosslinking, structure, findability) + the ADR index |
| [[0001-intuition-lance-integration]] | Intuition memory layer absorbed into rmx + Lance vector backend (Proposed) |
| [[adr-0002-subject-memory-container]] | Subject: memory-scoped working/durable container for threads of work (Proposed) |

## Authoring guides {#guides}

rel: catalogs -> [[agent-doc-primer]]
rel: catalogs -> [[adr-format]]
rel: catalogs -> [[gmd-migration-guide]]

| Doc | Hook |
|-----|------|
| [[agent-doc-primer]] | Which doc form to write (ADR / GMD / concept / pseudo / plan / graphify) so rmx can index it |
| [[adr-format]] | The ADR extractor's contract: detection, header fields, status weighting, emitted linkages |
| [[gmd-migration-guide]] | 9-phase playbook for converting existing markdown to full GMD compliance |

## Hook templates {#hooks}

rel: catalogs -> [[intuition-style-hooks]]

| Doc | Hook |
|-----|------|
| [[intuition-style-hooks]] | Copy-pasteable Claude Code settings snippets driving `rmx memory` on session events |

## Doc templates {#templates}

rel: catalogs -> [[adr-template]]
rel: catalogs -> [[concept-doc-template]]
rel: catalogs -> [[design-doc-template]]

| Doc | Hook |
|-----|------|
| [[adr-template]] | Copy-paste ADR starter exercising every linkage type the extractor knows |
| [[concept-doc-template]] | Concept-doc starter: H1 primary concept + H3 sub-concepts + `subclasses` prose |
| [[design-doc-template]] | Design-doc starter: bold-labeled metadata header carrying the indexing signal |

## Non-GMD reference {#non-gmd}

`pseudo-format.pseudo` — the `.pseudo` type-first spec format reference
(not markdown; indexed by the pseudo ingest pass, not `ingest-gmd`).
