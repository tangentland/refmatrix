---
name: ch-plan
description: Produce the technical implementation plan + design artifacts, honoring the constitution and ADRs
argument-hint: [optional stack/approach notes]
allowed-tools: [Read, Write, Edit, Grep, Glob, Bash]
model: inherit
enabled: true
---

# /ch-plan — Technical plan {#root}

Turns the clarified spec + its ADRs into the *how*. Fifth in the SDD chain. The constitution is a
**gate** here, checked before and after design.

## Steps {#steps}

1. Run `scripts/sdd/setup-plan.sh --json`. Parse `FEATURE_DIR`, `SPEC_FILE`, `PLAN_FILE`,
   `RESEARCH`, `DATA_MODEL`, `CONTRACTS_DIR`, `CONSTITUTION`.
2. Load `spec.md`, `workflow/CONSTITUTION.md`, and the feature's ADRs
   (`docs/architecture/adr/*` whose `rel: derives-from` points at this spec). If `rmx` is present,
   `rmx neighbors <SPEC_FILE>` / `rmx context <Concept>` to pull related decisions.
3. **Constitution Check (gate, pre-design):** evaluate every principle in `CONSTITUTION` against the
   intended approach. Record violations; if any are unavoidable, they go in Complexity Tracking with
   justification — otherwise change the approach.
4. Fill `PLAN_FILE` from `workflow/templates/plan-template.md`: Technical Context (language, deps,
   storage, testing, platform, perf goals, constraints, scale), Project Structure, and the phased
   plan. The plan MUST cite the ADRs by number and conform to their consequences.
5. **Phase 0** → write `research.md` (resolve unknowns, evaluate options).
   **Phase 1** → write `data-model.md`, `contracts/` (API/interface specs), and `quickstart.md`.
6. **Constitution Check (gate, post-design):** re-evaluate after Phase 1. Update Complexity Tracking.
7. GMD-validate all new artifacts: `python3 tools/gmd/lint.py <FEATURE_DIR>` — zero errors. Report
   the artifacts written, ADRs cited, and any constitution deviations logged.

## Next {#next}

Handoff → `/ch-tasks` to break the plan into an executable, dependency-ordered task list.
