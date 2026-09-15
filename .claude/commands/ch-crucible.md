---
name: ch-crucible
description: Extract architectural decisions from the clarified spec and record them as ADRs before planning
argument-hint: [optional decision focus]
allowed-tools: [Task, Read, Write, Edit, Grep, Glob, Bash]
model: inherit
enabled: true
---

# /ch-crucible — Architectural clarity gate {#root}

Sits **between clarify and plan**. Asks: *what architectural clarity can we add to this spec?*
Decisions are captured as ADRs that `/ch-plan` must then honor and cite. This is the SDD chain's
architecture gate — the *how-shaped* decisions, extracted before the technical plan commits to them.

## Steps {#steps}

1. Run `scripts/sdd/check-prerequisites.sh --json --paths-only`; read `spec.md` and
   `workflow/CONSTITUTION.md`.
2. Dispatch **`ch-architect`** (pre-implementation mode) via Task with the spec + constitution.
   Prompt it to identify the architectural decisions this spec forces but does not yet resolve:
   - System boundaries, key abstractions, and where new concepts attach to existing primitives.
   - Data ownership, invariants, and cross-cutting concerns (consistency, concurrency, failure).
   - Any place the spec could be realized two+ ways where the choice has downstream cost.
   - Per Constitution III ([[#root]] reason-from-tenets): does an existing primitive already solve
     this? Prefer reuse; flag proposed parallel infrastructure.
3. For each material decision, draft an ADR into `docs/architecture/adr/NNNN-<kebab-title>.md` from
   `workflow/templates/adr-template.md` (zero-padded next number). One decision per ADR. Set
   `metadata.status: Proposed`, list `governs:` concepts, and add
   `rel: derives-from -> [[<NNN-slug>-spec]]` pointing at the feature spec's GMD id.
4. If no ADR-worthy decision exists, say so explicitly and record why (the spec is architecturally
   inert) — do not manufacture ADRs.
5. Validate every new ADR: `python3 tools/gmd/lint.py docs/architecture/adr/<file>` — zero errors.
   If `rmx` is available: `rmx ingest .` so the ADRs index for `/ch-plan`.
6. Report the ADRs created (numbers + titles + status) and the decisions deliberately deferred.

## Next {#next}

Handoff → `/ch-plan`. The plan MUST cite these ADRs and comply with their consequences.
