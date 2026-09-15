---
gmd: "0.1"
id: specs-readme
title: "workflow/specs — per-feature SDD artifact chain"
tags: [sdd, workflow, index]
metadata:
  node_type: readme
---

# workflow/specs {#root}

Home of the **per-feature spec-driven-development (SDD) artifact chain**. Each feature gets a
numbered directory holding its spec → plan → tasks lineage. This is the *feature* layer; the
`workflow/` root holds the *meta/governance* layer (plan-of-plans, governance, registries).

## Layout {#layout}

```
workflow/specs/NNN-<slug>/
├── spec.md          # /ch-specify  — what/why, tech-agnostic (P1/P2/P3 stories, FR/SC)
├── plan.md          # /ch-plan     — how; honors constitution + cites the feature's ADRs
├── research.md      # /ch-plan Phase 0
├── data-model.md    # /ch-plan Phase 1
├── contracts/       # /ch-plan Phase 1 — API/interface specs
└── tasks.md         # /ch-tasks    — [T###] [P] [US#] tasks, checkpoint markers
```

Architectural decisions surfaced from a spec are ADRs in `docs/architecture/adr/` (authored by
`/ch-crucible`, between clarify and plan), not files under `specs/` — they are cross-feature and
long-lived. The feature's `plan.md` cites them.

## The chain {#chain}

`/ch-constitution → /ch-specify → /ch-clarify → /ch-crucible → /ch-plan → /ch-tasks → /ch-analyze →
/ch-implement`. Directories are created by `scripts/sdd/create-new-feature.sh` (numbered
`NNN-<slug>`, on a matching feature branch). See `workflow/CONSTITUTION.md` for the governing
gate and the command files in `.claude/commands/ch-*.md` for each step.

## Relationship to the meta layer {#meta}

| This layer (`workflow/specs/`) | Meta layer (`workflow/` root) |
|--------------------------------|-------------------------------|
| One feature's spec→plan→tasks artifacts | `plan-of-plans.md` — index + sequenced execution across features |
| Numbered per feature (`NNN-slug`) | `plans/` holds all plans; stage = `metadata.status` (`drafting` → `approved` → `in-progress` → `completed`) |
| Produced by the `/ch-*` SDD chain | Governance: `PLAN_GOVERNANCE.md`, `TDD_GOVERNANCE.md`, registries |

All artifacts here are GMD (frontmatter + anchors); validate with `python3 tools/gmd/lint.py`.
