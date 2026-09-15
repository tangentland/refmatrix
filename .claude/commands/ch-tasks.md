---
name: ch-tasks
description: Break the plan into an actionable, dependency-ordered tasks.md with parallel + checkpoint markers
argument-hint: [optional scope note]
allowed-tools: [Read, Write, Edit, Grep, Glob, Bash]
model: inherit
enabled: true
---

# /ch-tasks — Executable task list {#root}

Decomposes the plan into ordered, independently-verifiable tasks. Sixth in the SDD chain.

## Steps {#steps}

1. Run `scripts/sdd/setup-tasks.sh --json`. Parse `FEATURE_DIR`, `PLAN_FILE`, `TASKS_FILE`.
2. Load `plan.md`, `data-model.md`, `contracts/`, and `spec.md` (for the user-story grouping).
3. Fill `TASKS_FILE` from `workflow/templates/tasks-template.md`, organized **by phase then user
   story**: Setup → Foundational (blocks all stories) → one phase per user story (P1, P2, …) →
   Polish. Each user story ends at a **checkpoint** where it is independently testable.
4. Task line format: `[T###] [P?] [US#] <description with exact file path(s)>`.
   - `[P]` = safe to run in parallel (touches disjoint files, no ordering dep).
   - `[US#]` = the user story it serves; Setup/Foundational/Polish tasks omit the story tag.
   - Within a story, order: (optional tests-first) → models → services → endpoints → integration.
5. Encode dependencies explicitly (a task lists the task IDs it waits on). Keep the file GMD-valid:
   `python3 tools/gmd/lint.py <TASKS_FILE>` — zero errors.
6. Report task count, parallelizable count, and the per-story checkpoints.

## Next {#next}

Handoff → `/ch-analyze` (recommended consistency pre-flight) or `/ch-implement`.
