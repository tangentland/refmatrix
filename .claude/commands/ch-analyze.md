---
name: ch-analyze
description: Non-destructive cross-artifact consistency check across spec, ADRs, plan, tasks, and constitution
argument-hint: [optional focus]
allowed-tools: [Read, Grep, Glob, Bash]
model: inherit
enabled: true
---

# /ch-analyze — Pre-implement consistency gate {#root}

A read-only cross-check run **after tasks, before implement**. Complements the *post*-implement
`/ch-review` + `@ch-bsd`. Seventh in the SDD chain. Writes nothing — reports only.

## Steps {#steps}

1. Run `scripts/sdd/check-prerequisites.sh --json --require-tasks --include-tasks`. Parse the paths.
2. Load `spec.md`, the feature's ADRs, `plan.md` (+ `data-model.md`, `contracts/`), `tasks.md`, and
   `workflow/CONSTITUTION.md`.
3. Check consistency and coverage:
   - **Spec → tasks coverage:** every FR/SC and user story has ≥1 task; no orphan tasks with no
     spec basis.
   - **ADR conformance:** the plan cites the feature's ADRs and doesn't contradict their decisions;
     no architectural decision was made in the plan that lacks an ADR.
   - **Constitution compliance:** no principle is violated without a logged, justified deviation.
   - **Plan → tasks fidelity:** every plan component appears in tasks with correct dependency order;
     `[P]` markers don't collide on shared files; each user story reaches an independent checkpoint.
   - **Terminology drift:** entity/field/endpoint names are consistent across artifacts.
4. Emit a findings report grouped by severity (Critical / High / Medium / Low), each with the
   artifact + location and a concrete fix. Do NOT edit files.

## Next {#next}

Resolve Critical/High (loop back to the owning command), then handoff → `/ch-implement`.
