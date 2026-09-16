---
gmd: "0.1"
id: plan-12-open-bug-remediation
title: "The six open bugs: make the cost knowable, the decay detectable, the bytes trustworthy"
tags: [plan, bugs, model-workers, rerank, store-decay, measurement]
metadata:
  node_type: plan
  status: approved
  created: 2026-09-16
---

# Proposed Plan: close every open row in the bug registry {#root}

**Date:** 2026-09-16
**Status:** Approved
**Location:** `workflow/plans/plan-12-open-bug-remediation.md` — permanent home; stage is `metadata.status`.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[bug_registry]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_green_tests_are_not_a_working_command]]
rel: specifies -> [[task-12.1-shared-worker-readoption]]
rel: specifies -> [[task-12.2-rerank-cost-budget]]
rel: specifies -> [[task-12.3-rerank-doc-window]]
rel: specifies -> [[task-12.4-derive-version-stamp]]
rel: specifies -> [[task-12.5-pyc-invalidation]]
rel: specifies -> [[task-12.6-cli-startup-gap]]

## Context {#context}

Six rows in `workflow/bug_registry.md` read `open` or `recurring` on 2026-09-16: bug-019
(recurring), bug-024, bug-025, bug-032, bug-033, bug-037, bug-039. They are not six unrelated
defects. Four of them are one sentence said four ways: **a cost that nobody measures is a cost
that nobody can budget for.**

- **bug-024 / G14** — a daemon that missed the shared worker at boot never looks again, so the
  fleet silently runs N private models beside the shared pair and every rerank gets 5–20x slower.
  The cost of being private is real and unreported.
- **bug-025 / G13 (with bug-019)** — the always-on hook sends a pool to the shared reranker with
  no idea what that pool costs, times out 7/7 runs, and the abandoned request keeps scoring and
  starves the next caller's probe. The cost of a pool is real and unreported.
- **bug-032** — the cross-encoder scores only the first 2048 chars, so 36.9% of answer-bearing
  turns in LongMemEval are invisible to it. The cost of the truncation STRATEGY is real and, until
  measured, was assumed to be zero.
- **bug-039** — this project's own store was structurally under-derived while every health surface
  read green. The cost of a stale derive is real and has no detector at all.

The remaining two are about trusting the bytes under a measurement: bug-037 (a stale `.pyc` served
a mutated constant through a restored source file) and bug-033 (~8.5 s between `build_context`
at 0.45 s and the daemonless CLI at 9.0 s, unattributed).

## Proposed Approach {#proposed-approach}

### One principle, applied six times {#principle}

**Make the number the caller needs available at the boundary the caller already crosses.** Not a
new probe, not a new surface: the caller is already calling `info`, already opening a store,
already importing a module. Each task adds the missing field to a handshake that happens anyway.

- 12.1 — the daemon already ticks; the tick re-probes the shared socket and adopts it.
- 12.2 — the caller already sends `info`; `info` answers with seconds-per-doc and queue depth, and
  the `rerank` frame carries a deadline the worker honours when it dequeues.
- 12.3 — `collect_rerank_docs` already fetches text; it windows that text around query hits with
  the existing `kwic` windower instead of head-truncating it.
- 12.4 — the store already stamps `tracked_files`; a `derive_stamps` table records WHICH CODE
  derived the graph, and health flags a derive older than the running version.
- 12.5 — the test run already imports `src/`; it refuses to run against timestamp-invalidated
  bytecode.
- 12.6 — nothing is added; the gap is profiled end to end and attributed before anything is built.

### Ordering, and why {#ordering}

12.5 FIRST. It is the cheapest, and every measurement in 12.1–12.4 is taken on a tree whose
bytecode must be trustworthy — bug-037 is precisely the failure where it was not. Then 12.4
(detector, no behaviour change), 12.1 (re-adoption), 12.2 (cost budget, which needs 12.1's shared
worker to be reachable to be measurable), 12.3 (ranking change, measured last), 12.6 (measurement
only, no code).

### What this plan will NOT do {#non-goals}

- **No ranking claim for 12.3 without a measurement.** bug-032's effect may be zero: after the
  ch-bsd r2 attribution correction it can only reach `scan`, and only if the shared worker answered
  at all during the run. The task ships the windower and the A/B; it does not ship a headline.
- **No fix for 12.6 in this plan.** bug-033 is unprofiled. The task produces an attribution and a
  registry row, and a fix gets its own task once the 8.5 s has a name.
- **No new always-on surface.** Every field added here rides an existing handshake.

## Task list {#tasks}

| task | bug | what |
|------|-----|------|
| [[task-12.5-pyc-invalidation]] | bug-037 | the suite refuses timestamp-invalidated bytecode |
| [[task-12.4-derive-version-stamp]] | bug-039 | `derive_stamps` + a stale-derive health signal |
| [[task-12.1-shared-worker-readoption]] | bug-024 | a private daemon re-probes and adopts the shared worker |
| [[task-12.2-rerank-cost-budget]] | bug-025, bug-019 | `info` reports cost; the caller skips and says so; the worker drops an expired frame |
| [[task-12.3-rerank-doc-window]] | bug-032 | KWIC window replaces head truncation |
| [[task-12.6-cli-startup-gap]] | bug-033 | profile and attribute the 8.5 s |

## Acceptance for the plan {#acceptance}

- Every bug row above reaches `fixed` with a remediation that names the mechanism, or stays open
  with a MEASURED reason it cannot close yet (12.6 may legitimately land as an attribution).
- Each task: RED recorded, GREEN recorded, one mutation per new guard, implementation summary.
- `@ch-bsd` over the plan's commit range, remedied to CLEAN.
- No claim of effect anywhere in this plan without a measurement on the path users run.
