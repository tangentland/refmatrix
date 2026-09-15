---
gmd: "0.1"
id: architecture-readme
title: "refmatrix — Architecture Overview (template entry point)"
tags: [architecture, overview, refmatrix]
---

# refmatrix — Architecture Overview {#root}

refmatrix is a roaring-bitmap reference matrix over documents, code, and concepts, served by a
per-store daemon and a user-level hub, with GMD-backed agent memory. This file is the cat-herder
entry point; the substance lives in the four core docs catalogued in [[INDEX]].

## System Shape {#system-shape}

- What it is, the discovery ladder, lifecycle, use cases → [[SYSTEM]]
- Module layout, storage layers, daemon/concurrency, CLI tree → [[ARCHITECTURE]]
- Everything touching the outside (tldr, git + Claude hooks, GMD ingest, watcher, sockets) → [[INTEGRATION]]
- Where the speed comes from, honest benchmarks, measured negatives → [[PERFORMANCE]]

## Design Tenets {#design-tenets}

The primitives every design reasons FROM are listed in `.claude/PROJECT_PROFILE.md` §primitives;
the governing principles are `workflow/CONSTITUTION.md` (VII–XII are refmatrix-specific).

## Navigation {#navigation}

- Index of architecture docs: [[architecture-index#root]]
- Decision records: `docs/adr/` (index [[adr-0000-adr-overview]])
- Tracked gaps: [[architecture-todo#root]]

rel: catalogs -> [[architecture-index]]
rel: depends-on -> [[architecture-todo]]
rel: related-to -> [[SYSTEM]]
rel: related-to -> [[ARCHITECTURE]]
