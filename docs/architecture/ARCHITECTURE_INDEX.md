---
gmd: "0.1"
id: refmatrix/architecture-index
title: "Architecture Index — refmatrix"
tags: [architecture, index, refmatrix]
---

# Architecture Index {#root}

Navigation hub. Follow the wikilinks; do not grep prose. The curated catalog of every GMD doc
under `docs/` is [[INDEX]].

## Entry Points {#entry-points}

- Overview: [[architecture-readme#root]]
- Tracked gaps: [[architecture-todo#root]]

## Topic Docs {#topic-docs}

| Doc | Purpose |
|-----|---------|
| [[SYSTEM]] | What refmatrix is: bitmap matrix, discovery ladder, lifecycle, use cases |
| [[ARCHITECTURE]] | Module layout, dependency graph, catalog schema, daemon/concurrency, CLI tree |
| [[INTEGRATION]] | llm-tldr, git + Claude Code hooks, GMD ingest, watcher, socket protocol |
| [[PERFORMANCE]] | Scoring stack, production CSN harness, MemAware benchmark, negatives |
| [[system_design_review]] | Staff-level system design interview reconstruction |

## Decision Records (`docs/adr/`) {#adr}

| ADR | Title | Status |
|-----|-------|--------|
| [[adr-0000-adr-overview]] | ADR authoring rules + index | — |
| [[0001-intuition-lance-integration]] | Intuition memory layer + Lance vector backend | Proposed |
| [[adr-0002-subject-memory-container]] | Subject: memory-scoped container for threads of work | Proposed |

## Concept Docs (`concepts/`) {#concepts}

None yet under `docs/architecture/concepts/`; concept-level docs live as memories and in
[[agent-doc-primer]].

## Explorations (`explorations/`) {#explorations}

Earlier design research lives in the `docs/PERFORMANCE.md` negatives and in memory files
(`project_retrieval_negatives_*`). Explorations, 2026-10-07:

| exploration | question | status |
|---|---|---|
| [[exploration-concept-similarity-cull-merge]] | which similarity signal may cull or merge concepts (helix) | research complete, awaiting decisions |
| [[exploration-agent-context-usage]] | how the agent uses `rmx context` once grep is passive (plan-16) | research complete, awaiting decisions |
| [[exploration-adaptive-memory-budget]] | adaptive memory selection under the context load limits | research complete, awaiting decisions |
| [[exploration-storage-concurrency-redesign]] | storage options A-E: DuckDB concurrency, Vortex, BSI (2026-10-08) | measured in part, awaiting decisions |
| [[exploration-session-phased-context]] | phase scan-prompt/recall breadth vs depth by STM state (2026-10-14) | idea recorded, folded into plan-19/21 reviews |

## Tech Stack (`tech-stack/`) {#tech-stack}

See `workflow/TECH_STACK_DECISIONS.md`.

rel: part-of -> [[architecture-readme]]
rel: related-to -> [[INDEX]]
