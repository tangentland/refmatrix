---
gmd: "0.1"
id: agent-brief-red-251b
title: "Brief: red-251b — task 25.1 rev 7 test work (ch-test-engineer): contract updates, fixture fixes, new REDs"
tags: [agent-brief, dispatch]
---

# Brief: red-251b — task 25.1 rev 7 test work {#root}

You own the tests for refmatrix task 25.1 after its GREEN. Apply the lead's revision-7 decisions
on the test side; write NO `src/` code.

rel: depends-on -> [[agent-brief-green-251#hard-rules]]
rel: depends-on -> [[agent-brief-green-251b]]

## Where {#where}

- Clone `/Volumes/littlebig/refmatrix-plan25-1`, branch `task-25.1-recall-hook-byte-budget`, tip
  `d68b71c` (GREEN `16ace00`, docs `273050b`, spec rev 7 `d68b71c`). Work and commit (pathspec)
  only here. Interpreter: the clone's `.venv-eval` (untracked symlink; never stage it).

## Read first {#read-first}

1. Spec `workflow/plans/plan-25-cliquedb-field-report-tasks/task-25.1-recall-hook-byte-budget.md`,
   especially `#rev-round-7` (the decision table you implement on the test side), R2, R3, R5, R7,
   R10 (`#r10-bus`), R11, AC-4 … AC-15.
2. `workflow/implementation_summaries/task-25.1-recall-hook-byte-budget.md`: `#red`, `#green`,
   `#lead-judge-table`, `#green-triage` / `#green-triage-table`, `#green-mutations-table`,
   `#green-flags`, `#mocks`.
3. Full-suite log `workflow/review-output/plan25/25.1-green-full.log` (38 failed).
4. `workflow/TDD_GOVERNANCE.md`, `workflow/test_mock_registry.md`.

## Do {#do}

- **Contract updates (27 tests):** per `#green-triage-table`, change each test to the contract its
  cited spec line now states. Never weaken an assertion beyond what the spec changed; keep each
  test's original intent (name it in the commit body per test file).
- **J1, J2, J6** (`#rev-round-7`): fix the fixture / detector / assertion as decided.
- **J3/J4:** the two AC-6 tests are already RED for the right reason; confirm they still express
  "with `include_subjects`, live subjects are named; stale never" and add an assertion that
  non-subject rows are still reranked (so the fix cannot simply disable rerank).
- **J5:** update AC-13 / generator argv expectations to SessionStart `--k 12`; keep AC-9's
  session-start body test (it should pass once k = 12 lands). Prove it RED at HEAD.
- **F1** `#r10-bus`, **F2** R11's producer count, **F3** AC-4 (i), **F6** leg line only under
  `--verbose`: new RED tests, each proven failing at HEAD for the right reason.
- **F4:** a SessionStart payload with a non-zero trailer, so the two AC-14 mutations (delivered
  event for a trimmed hit; global hit's event in the project file) become decidable.
- **F7:** graduate the routing-file mock row in `workflow/test_mock_registry.md`.

## Verify and deliver {#deliver}

- RED files + every file you touched: report pass/fail; the only failures left must be the new
  REDs (J3/J4, J5, F1, F2, F3, F6) and AC-5 (waits on 26.4), each by E line.
- Mutations on any new guard: one at a time, restore in its own command, clear `__pycache__`.
- Commits by pathspec; a `#red-rev7` section in the implementation summary mapping every change to
  its rev-7 row and its HEAD line. Text report: shas, counts, the RED list for the implementer,
  ambiguities.
