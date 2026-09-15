---
name: ch-implement
description: Execute the feature's tasks.md in dependency order, then trigger post-implementation review
argument-hint: [optional task subset]
allowed-tools: [Task, Read, Write, Edit, Grep, Glob, Bash]
model: inherit
enabled: true
---

# /ch-implement — Execute the plan {#root}

Runs the tasks to working code. Last in the SDD chain; hands off to the review gates.

## Steps {#steps}

1. Run `scripts/sdd/check-prerequisites.sh --json --require-tasks --include-tasks`. Parse paths.
2. Load `tasks.md`, `plan.md`, `data-model.md`, `contracts/`, and `workflow/CONSTITUTION.md`.
3. Execute tasks in order, honoring dependencies and phase boundaries:
   - Complete **Setup** then **Foundational** before any user story.
   - Run `[P]`-marked tasks in the same phase concurrently only when they touch disjoint files.
   - Stop at each user-story **checkpoint** and verify that story is independently testable before
     moving on.
   - Mark each task done in `tasks.md` as it lands.
4. Honor the constitution: concrete `src/` only (no stubs/mocks/workarounds), mocks confined to
   tests per `workflow/test_mock_registry.md`, real-auth tests for new protected endpoints,
   contract tests for new UI-facing shapes. Tests run in the project's canonical env — all of them.
5. Keep artifacts current: update `docs/architecture/ARCHITECTURE_INDEX.md`,
   write an implementation summary to
   `workflow/implementation_summaries/<feature>.md`.
6. Report tasks completed vs remaining, tests run, and any deviations from the plan.

## Next {#next}

Post-implementation gates (see `CLAUDE.md` Quality Gates):
- `/ch-review` — four-phase multi-agent review (code, architecture, tests, gaps/docs).
- `@ch-bsd` — runtime-integration audit: prove the code executes in production paths.
Resolve Critical/High before commit.
