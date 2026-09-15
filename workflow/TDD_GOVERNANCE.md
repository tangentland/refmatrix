---
gmd: "0.1"
id: tdd-governance
title: "TDD Governance — RED-first, mutation-gated, slice by slice"
tags: [process, testing, tdd, governance]
metadata:
  node_type: governance
---

# TDD Governance {#root}

rel: depends-on -> [[test_mock_registry]]

How tests are specified, written, and *proven*. The contract that keeps the suite from rotting
into fake, shallow, always-pass tests. **A test counts only when it is proven to catch a real
break.** A fake test is worse than no test — it converts an honest "untested" into a lying
"tested", and the debt compounds. This document makes a shallow test hard to pass off as real.

> Baseline template policy. Projects tune the specifics (mutation tool, coverage bar, slice
> definition) in `.claude/PROJECT_PROFILE.md` / the relevant `.local` overlay; the obligations
> below are the spine.

## Honest split — TDD vs characterization {#split}

- **New work is strict red-green TDD. TEST-FIRST IS THE STANDARD.** For each acceptance
  criterion: write the failing test, run it, *prove it red* against the absent/empty
  implementation, THEN implement to green, then mutation-gate. The recorded red run is the proof
  the test can fail.
- **Pre-existing code is characterized, not TDD** — test-after over known-good code. Label it as
  such; never call it TDD.
- Both pass the **same** mutation + adversarial gate. The label changes; the bar does not.

Plain red-green does not stop a tautology (it goes green too). So the shape is **frozen
acceptance contract (ATDD) + mutation testing**, with red-green TDD as the inner loop.

## The pipeline (every slice, in dependency order) {#pipeline}

One unit of work at a time, fully, before the next:

0. **Alignment refresh** — run `ch-alignment` over the slice's tasks FIRST: ensure the
   ground-truth reference (`pseudocode/` where used, the Accepted ADRs, `workflow/CONSTITUTION.md`)
   is current. Tests and implementation must both match ground truth; stale ground truth means
   tests encode the wrong behavior. Fix drift before anything else.
1. **RED — `ch-test-engineer`** writes the failing tests from the frozen acceptance criteria and
   proves them red against the absent implementation. Records the red run.
2. **GREEN — `ch-implementer`** writes production code to turn those tests green — and authors NO
   tests (separation of duties: no self-tested code).
3. **Mutation + adversarial gate** — mutate the implementation; every surviving mutant is an
   untested behavior. Kill or justify each.
4. **Review** — `/ch-review` + `@ch-bsd` (runtime-integration audit).

**Dispatch order is mandatory: test-engineer (RED) BEFORE implementer (GREEN).** Dispatching the
implementer first violates this contract.

## Non-negotiables {#rules}

- No test is "done" without a recorded RED proving it can fail.
- Mocks only in `tests/`, classified in `test_mock_registry` ([[test_mock_registry#classification]]);
  `src/` stays concrete (constitution I).
- New auth-protected endpoints get a real-auth test; new UI-facing shapes get a contract test.
- All tests run in the project's canonical environment (Docker where applicable) — none skipped.
- A criterion whose stated signature/return type diverges from the live implementation is stale
  ground truth — reconcile before writing the test.
