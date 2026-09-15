---
name: ch-specify
description: Create a feature specification (the what/why, tech-agnostic) from a natural-language description
argument-hint: <feature description>
allowed-tools: [Read, Write, Edit, Grep, Glob, Bash]
model: inherit
enabled: true
---

# /ch-specify — Feature specification {#root}

Turns a plain-language feature request into a structured, tech-agnostic spec. Second in the SDD
chain: `constitution → **specify** → clarify → adr → plan → tasks → analyze → implement`.

## Steps {#steps}

1. Run: `scripts/sdd/create-new-feature.sh --json "$ARGUMENTS"`. Parse `BRANCH_NAME`,
   `FEATURE_DIR`, `SPEC_FILE`, `FEATURE_NUM` from its JSON. This creates
   `workflow/specs/NNN-<slug>/spec.md` (seeded from `workflow/templates/spec-template.md`) and a
   feature branch.
   - Then set the rmx STM subject to this feature so working memory partitions per feature and
     promoted digests / `/save-state` handoffs file under it: call the `refmatrix` MCP tool
     `rmx_change_subject` with the `<NNN-slug>` label (idempotent). Prefer the MCP tool over
     `Bash rmx focus change-subject`.
2. Fill `SPEC_FILE` from the user's intent:
   - Prioritized user stories (P1/P2/P3), each **independently testable** with Given/When/Then
     acceptance scenarios.
   - Functional Requirements (`FR-###`), Key Entities, measurable Success Criteria (`SC-###`).
   - Edge cases and Assumptions.
   - Keep it the *what/why* — **no** tech stack, no APIs, no schema. Those come at `/ch-plan`.
3. Mark genuine unknowns with `[NEEDS CLARIFICATION: question]` — at most 3. Don't invent detail.
4. Set the GMD frontmatter `id` to `<NNN-slug>-spec` and `title` accordingly; add anchors on every
   heading. Validate: `python3 tools/gmd/lint.py <SPEC_FILE>` — zero errors.
5. Report the feature dir, story count, and any `[NEEDS CLARIFICATION]` markers.

## Next {#next}

Handoff → `/ch-clarify` (recommended if any `[NEEDS CLARIFICATION]` remain), else `/ch-crucible`.
