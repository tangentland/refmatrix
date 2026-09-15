---
name: ch-clarify
description: Resolve underspecified areas of the current spec via up to 5 targeted questions, encoded back into spec.md
argument-hint: [optional focus area]
allowed-tools: [Read, Write, Edit, Grep, Glob, Bash]
model: inherit
enabled: true
---

# /ch-clarify — De-risk the spec {#root}

Interrogates the current feature spec for ambiguity **before** architecture and planning. Third in
the SDD chain.

## Steps {#steps}

1. Run `scripts/sdd/check-prerequisites.sh --json --paths-only` to locate `SPEC_FILE` /
   `FEATURE_DIR` for the active feature.
2. Read `spec.md`. Scan for ambiguity across: scope boundaries, data shapes, user-role/permission
   assumptions, error/edge behavior, non-functional targets, and every `[NEEDS CLARIFICATION]`.
3. Ask **at most 5** highly targeted questions, highest-impact first. Prefer concrete options over
   open prompts. Ask one batch; stop early once ambiguity is resolved.
4. Encode each answer back into the relevant spec section and delete the resolved
   `[NEEDS CLARIFICATION]` marker. Do not expand scope — record only what the user decided.
5. Re-lint: `python3 tools/gmd/lint.py <SPEC_FILE>` — zero errors. Report what was clarified.

## Next {#next}

Handoff → `/ch-crucible` — surface the architectural decisions this clarified spec now implies.
