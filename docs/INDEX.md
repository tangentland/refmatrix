---
gmd: "0.1"
id: refmatrix/INDEX
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
| [[system_design_review]] | Staff-level system design interview reconstructed for refmatrix (v0.60.x, with the scars). Stale: still describes the retired A/B writer rotation; superseded by [[refmatrix/refmatrix_system_design_interview]] |

## ADRs {#adrs}

rel: catalogs -> [[adr-0000-adr-overview]]
rel: catalogs -> [[0001-intuition-lance-integration]]
rel: catalogs -> [[adr-0002-subject-memory-container]]
rel: catalogs -> [[adr-0003-canonical-partition-layout]]
rel: catalogs -> [[adr-0004-unified-location-space-index]]
rel: catalogs -> [[refmatrix/adr-0005-memory-dir-layout]]
rel: catalogs -> [[refmatrix/adr-0007-instruction-architecture]]

| Doc | Hook |
|-----|------|
| [[adr-0000-adr-overview]] | ADR authoring rules (crosslinking, structure, findability) + the ADR index |
| [[0001-intuition-lance-integration]] | Intuition memory layer absorbed into rmx + Lance vector backend (Proposed) |
| [[adr-0002-subject-memory-container]] | Subject: memory-scoped working/durable container for threads of work (Proposed) |
| [[adr-0003-canonical-partition-layout]] | Canonical partition layout: two per project store, one for global, benchmarks mirror production (Proposed) |
| [[adr-0004-unified-location-space-index]] | One location space for every search mechanism; sentence co-location measured +4–14% MRR (Proposed) |
| [[refmatrix/adr-0005-memory-dir-layout]] | Memory dir by type/lifecycle folders (`savestates/`, `impressions/`); topic = derived subject; `.memory-layout` marker gates new on-disk behaviour (Proposed) |
| [[refmatrix/adr-0007-instruction-architecture]] | Instruction architecture: each rule delivered by its trigger event (deny, path rule, skill, check, agent start) from one generated unit, injected once, with a ledger row; always-on ≤ 10,000 B beside the PRIMER (Accepted) |

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

## Measurements {#measurements}

Reports that answer a question with numbers, each naming its harness and what it does NOT claim.
(Process-side measurement notes live under `workflow/measurements/`; these are the knowledge-side
reports — see `CLAUDE.md#planning-task-docs` for the split.)

| Doc | Hook |
|-----|------|
| [[refmatrix/grep-learning-replay]] | Does funnelling grep through rmx teach the graph anything? Two-arm replay: index share 18.5% -> 31.7% (SUPERSEDED by bug-074; re-measured by task-16.4), and the defect the instrument found first |
| [[refmatrix/grep-canonical-breadth]] | bug-070: how wide should the canonical grep match be? Four arms — the obvious fix (plain equality) destroyed the bridge; the trailing-segment anchor costs nothing |

## External reviews {#external-reviews}

Assessments written from outside the build loop (a separate session reading the repo, its ledgers
and the live fleet), under `docs/external_reviews/`. Each names what it does NOT claim and when its
findings are to be acted on.

rel: catalogs -> [[refmatrix/ch-bsd-assessment-2026-11-23]]
rel: catalogs -> [[refmatrix/refmatrix_system_design_interview]]
rel: catalogs -> [[refmatrix/cat-herder-merge-2026-11-24]]

| Doc | Hook |
|-----|------|
| [[refmatrix/ch-bsd-assessment-2026-11-23]] | ch-bsd across the fleet from its own ledgers: highest-value reviewer, unbounded rounds until the L165 reset (r18 → r3); eight findings (stale `last_run.log`, charter, stop condition, leaderboard, precision, template drift, impressions size, and F8: 13 of 25 post-reset SKETCHYs should have been BULLSHIT, 7 shipped unconfirmed) on HOLD until 0.85.0 |
| [[refmatrix/refmatrix_system_design_interview]] | Full staff-level system design interview as a model answer, verified against the code at 0.84.0 (`338c6dfb`): snapshot read tiers, FIFO writer lock, out-of-process copy (bug-110), scan-prompt PPR stack, memory tiers, hub watchdog, incident table, 10×/100× scaling, rubric, `file:line` code map. Supersedes [[system_design_review]] |
| [[refmatrix/cat-herder-merge-2026-11-24]] | Merge cat-herder into refmatrix? Yes, as project-neutral package data in `src/refmatrix/templates/` (where `rmx init` already ships 9 of its files, all drifted) with a parity gate and `rmx template diff\|upgrade`: cat-herder has stalled (3 commits since Oct), refmatrix is the de facto upstream, consumers have no upgrade path. Ownership (atollogy vs tangentland) is the user's call; HOLD until 0.85.0 + the ch-bsd package |

## Non-GMD reference {#non-gmd}

`pseudo-format.pseudo` — the `.pseudo` type-first spec format reference
(not markdown; indexed by the pseudo ingest pass, not `ingest-gmd`).

## cat-herder template docs {#template}

rel: catalogs -> [[architecture-readme]]
rel: catalogs -> [[architecture-index]]
rel: catalogs -> [[architecture-todo]]
rel: catalogs -> [[ONBOARDING]]

| Doc | Hook |
|-----|------|
| [[architecture-readme]] | Template entry point into the four core docs |
| [[architecture-index]] | Navigation hub: topic docs, ADRs, concepts, explorations |
| [[architecture-todo]] | Gap tracking seeded from the 2026-09-14 ch-bsd audit |
| [[ONBOARDING]] | Agent first-run onboarding (done 2026-09-14) |

`docs/gmd/PRIMER.md` + `docs/gmd/SPEC.md` are the bundled GMD primer/spec (ids `PRIMER`, `SPEC`).
