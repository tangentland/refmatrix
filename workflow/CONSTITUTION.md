---
gmd: "0.1"
id: constitution
title: "Project Constitution — governing principles (SDD gate)"
tags: [constitution, governance, sdd]
metadata:
  node_type: constitution
  version: "1.1.0"
  ratified: 2026-07-06
---

# Project Constitution {#root}

The governing principles every feature must honor. `/ch-plan` re-checks this file as a **gate**
before and after design; `/ch-analyze` verifies artifacts comply. Violations must be justified in
the plan's Complexity Tracking table or the design changes. Amend deliberately — bump `version`
and note the change in [[#amendments]].

> This is the baseline template's constitution. Replace/extend the project-specific principles
> below when you bootstrap a real project (`/ch-constitution`). The **non-negotiables** are the
> template's spine and should survive.

## Non-negotiable principles {#non-negotiable}

### I. Concrete production code {#concrete}

All `src/` code is fully concrete — no stubs, mocks, simulated behavior, fake implementations, or
placeholder logic. Every function/class/module does real work or does not exist yet. Mocks live
ONLY in test code, classified in `workflow/test_mock_registry.md`. Internal-subsystem mocks must
graduate when the real subsystem exists.

### II. No workarounds {#no-workarounds}

A missing dependency (table, service, config) is not worked around. Define the gap, propose the
real solution, ask before proceeding. Consult `workflow/development_resources.md` first.

### III. Reason from tenets {#from-tenets}

Every design proposal reasons FROM the architecture's tenets, not around them. Before a new
mechanism, verify an existing architectural primitive doesn't already solve it. No parallel
infrastructure when an existing conceptual alignment covers the concern. Architectural decisions
are captured as ADRs (`/ch-crucible`) between spec-clarify and plan; `plan.md` must cite them.

### IV. Tests are real and complete {#tests-real}

Tests run in the project's canonical environment (Docker where applicable) — ALL of them, never
skipped to dodge a broken environment. New auth-protected endpoints get a real-auth test; new
UI-facing response shapes get a contract test. Test tiers and mock governance per
`workflow/test_mock_registry.md`.

### V. GMD is the documentation substrate {#gmd}

All `docs/` and `workflow/` items are Graph Markdown: frontmatter (`gmd: "0.1"` + `id` + `title` +
`tags`), a `{#anchor}` on every heading, and typed `rel:` edges for citations. Validate with
`python3 tools/gmd/lint.py <path>` — zero errors — before commit.

### VI. Spec-driven flow {#sdd}

Non-trivial features follow the chain: `/ch-constitution → /ch-specify → /ch-clarify → /ch-crucible →
/ch-plan → /ch-tasks → /ch-analyze → /ch-implement`. Spec defines *what/why* (tech-agnostic);
ADRs capture architectural decisions; plan defines *how* and honors this constitution + the ADRs;
implementation is verified post-hoc by `/ch-review` + `@ch-bsd`.

## Project-specific principles {#project}

### VII. One writer, daemon-routed {#project-1}

The daemon is the only process that opens a store's active slot for writing. CLI and MCP writes go
through daemon ops (`_store(write)`); reads use the lock-free snapshot. In-process fallbacks exist
for daemon-down only and must never race a live daemon. Rationale: every catalog corruption and
lock crash in this project's history came from a second writer.

### VIII. Memory paths never fail silently {#project-2}

Between a memory file and the store there is no `2>/dev/null`, `|| true`, bare `except: pass`,
or uncounted skip. Failures are returned, printed, and counted. Rationale: a memory system that
loses entries quietly lies to the next session (2026-09-14: ten days of files never ingested).

### IX. Verbs first {#project-3}

Every capability an agent can invoke is a `@verb` in `verbs.py`; CLI commands and MCP tools are
adapters over verbs. Parity between surfaces is asserted by a test, never assumed. Rationale:
the MCP surface drifted to 30 tools over 10 verbs; behavior lived in only one adapter.

### X. Hooks are generated {#project-4}

The Claude Code hook config this project runs is produced by `rmx install-hooks`; the installed
file equals the generated block (`rmx install-hooks --check`). A hook that only exists in a
settings file is a template bug to be promoted or deleted. Rationale: hand-authored hooks were
invisible to reinstall, unreviewed, and silenced a failure the code was designed to shout.

### XI. Measure the path users run {#project-5}

Benchmarks and evals exercise the production ingest + query path (`eval/production/`); a number
reported in README has a committed artifact under `eval/` that regenerates it. Rationale: a
bespoke harness hid four defects behind a true score.

### XII. Supervisors never SIGKILL a working daemon {#project-6}

Watchdogs distinguish dead from busy (reconnecting to a model worker, mid-ingest, index repair)
and escalate only past a grace window. Rationale: `kickstart -k` mid-write corrupted the entities
index on 2026-09-14.

## Governance {#governance}

- **Gate authority:** `/ch-plan` MUST evaluate every principle here before Phase 0 and re-evaluate
  after Phase 1 design. `/ch-analyze` cross-checks spec/plan/tasks against it.
- **Deviation:** any violation is recorded in the plan's Complexity Tracking with justification,
  or the design is changed to comply. Unjustified violations block `/ch-implement`.
- **Precedence:** the non-negotiables ([[#non-negotiable]]) outrank project-specific principles on
  conflict.

## Amendments {#amendments}

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-07-06 | Initial baseline constitution (template). |
