---
gmd: "0.1"
id: task-26.0-adr-memory-dir-layout
title: "Task 26.0: ADR-0005 — the curated memory dir is laid out by type and lifecycle; topic is a derived subject"
tags: [task, plan-26, adr, memory-dir, layout]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
---

# Task 26.0: ADR-0005 memory-dir layout {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: nothing. Author: `@ch-architect` (dispatched by `/ch-crucible`).

rel: part-of -> [[plan-26-memory-organisation]]
rel: depends-on -> [[refmatrix/adr-0002-subject-memory-container]]
rel: related-to -> [[refmatrix/adr-0003-canonical-partition-layout]]

## Requirements {#requirements}

1. Write `docs/adr/0005-memory-dir-layout.md` as GMD, with status Proposed, and lint it clean.
   It must state:
   - the folder table in [[plan-26-memory-organisation#root]] (`feedback/ project/ reference/
     user/ guardrail/ impressions/ savestates/`), and why type folders are singular and
     lifecycle folders plural;
   - that store identity is the frontmatter `id`, and a file's folder is never part of it;
   - that topics are subjects: `part-of` to an ADR-0002 subject, many per memory, never a
     folder;
   - the folder-authority rule from plan Q3 (authoritative for `savestates/`, report-only
     elsewhere);
   - that `memory_layout.py` is the one place the table lives;
   - that legacy flat dirs stay readable forever (fallback, never a hard cut).
2. Add a `rel: catalogs` row in `docs/adr/0000-adr-overview.md` and a row in `docs/INDEX.md`.
3. Add edges: `rel: depends-on -> ADR-0002` and `rel: related-to -> ADR-0003` (partition
   layout). The ADR must not contradict either one.

## Files to Create / Modify {#files}

- Create `docs/adr/0005-memory-dir-layout.md`.
- Modify `docs/adr/0000-adr-overview.md` and `docs/INDEX.md`.

## Test Strategy {#test-strategy}

Documentation only: `./scripts/lint-gmd.sh` shows zero errors. `@ch-alignment` derives the
`memory_layout` pseudocode from the ADR before 26.1 goes RED.
