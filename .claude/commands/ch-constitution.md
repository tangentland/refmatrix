---
name: ch-constitution
description: Create or update the project constitution (governing principles) that the SDD chain enforces
argument-hint: [principle statements, or empty for interactive]
allowed-tools: [Read, Write, Edit, Grep, Glob, Bash]
model: inherit
enabled: true
---

# /ch-constitution — Establish governing principles {#root}

Owns `workflow/CONSTITUTION.md` — the principle set every feature must honor. `/ch-plan`
re-checks it as a gate; `/ch-analyze` verifies compliance. First command in the SDD chain.

## Steps {#steps}

1. Read the current `workflow/CONSTITUTION.md` (it exists as a baseline template).
2. From `$ARGUMENTS` (or interactively if empty), gather the project-specific principles: name +
   description + rationale for each. Ask focused questions only for genuinely missing decisions.
3. Fill the `## Project-specific principles` section — one `### Name {#project-N}` per principle.
   Never weaken the non-negotiables unless the user explicitly directs it.
4. Bump `metadata.version` (semver: MAJOR = principle removed/redefined, MINOR = new principle,
   PATCH = wording) and add an `## Amendments` row.
5. Keep it GMD-valid: `python3 tools/gmd/lint.py workflow/CONSTITUTION.md` — zero errors.
6. Report the version delta and the principles added/changed.

## Next {#next}

Handoff → `/ch-specify` to define the first feature against these principles.
