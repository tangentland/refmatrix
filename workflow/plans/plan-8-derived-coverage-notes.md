---
gmd: "0.1"
id: plan-8-derived-coverage-notes
title: "Briefs — what the corpus knows solidly, and what it is asked but cannot answer"
tags: [plan, memory, consolidate, surface]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-09-15
---

# Proposed Plan: briefs over the memory graph {#root}

**Date:** 2026-09-15
**Status:** Approved
**Location:** `workflow/plans/plan-8-derived-coverage-notes.md` — permanent home; stage is `metadata.status`.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[project_memory_compile_shipped]]
rel: depends-on -> [[project_verbs_layer_antidrift]]
rel: related-to -> [[project_helix_phase1_shipped]]
rel: related-to -> [[project_refmatrix_mission_charter]]
rel: specifies -> [[task-8.1-plan-8-derived-coverage-notes]]
rel: specifies -> [[task-8.2-plan-8-derived-coverage-notes]]
rel: specifies -> [[task-8.3-plan-8-derived-coverage-notes]]
rel: specifies -> [[task-8.4-plan-8-derived-coverage-notes]]

## Context {#context}

`rmx memory compile` groups the corpus into subjects and says what it *has*. Nothing says what it
*lacks*. Every failure mode this project has hit in the last six months was a coverage failure
that nobody could see from inside the store: 43-83% of entities carrying no terms
([[project_main_path_indexed_nothing]]), 179 docs stranded by an mtime gate
([[project_sync_mtime_gate_strands_docs]]), a helix log so self-suppressed it could not decide
anything ([[project_helix_log_confounded]]). In every case the store answered queries; it just
answered them thinly, and the thinness was invisible until a benchmark or an audit went looking.

A competing memory system ships this idea as a generated summary object detecting "patterns and
knowledge gaps." The idea is right and the substrate here is stronger — rmx has the degree
counts, the linkage types, the `contradicts` verb, the retrieval telemetry, and the subject
clusters already. What is missing is a surface that reads them together and writes down the
answer.

**This is a diagnostic surface over existing signal, not a new inference engine.** Everything it
reports must be traceable to a row already in the store or a line already in a log.

## Proposed Approach {#proposed-approach}

A derivation pass, a sibling of `consolidate.py`, emitting **briefs** — `kind=memory` rows in the
`brief/<class>` mtype namespace, plus a regenerable GMD index on disk — the same both-directions contract `memory compile` already honors ("the index is
regenerable from the store, and the store is rebuildable from the index").

### Note classes {#classes}

Each class is one detector over signal that already exists. A note carries its evidence ids; a
note with no evidence is a bug, not a note.

| Brief class | Detector | Signal source |
|---|---|---|
| `corroborated` | subject cluster with >= N members drawn from >= M distinct sessions/dates | `memory compile` plan, entity `created` |
| `orphan-concept` | concept with `mentions` degree high and `defines`/`lead` degree zero — talked about, never pinned down | degree counts, the primer's own computation |
| `singleton` | subject whose cluster has exactly one member — a topic the corpus touched once | `memory compile` plan |
| `contradicted` | two memories joined by a `contradicts` edge with neither superseded | GMD rel edges |
| ~~`unanswered`~~ | **NOT SHIPPED** — the confound gate failed; `query.log` records what the agent grepped for, not what the corpus was asked | `query.log` / `cli.log` telemetry |
| `stale` | a subject whose members were all last touched before a cutoff | helix edge-time |

`unanswered` had the most product value and the most measurement risk. The risk won: see Q3 and
`workflow/measurements/brief-unanswered-confound.md`. Four classes ship, not five.

### Surfaces {#surfaces}

Per [[project_verbs_layer_antidrift]]: the capability is a **verb first**, and CLI + MCP are thin
adapters. Nothing implements it twice.

- verb `rmx_memory` gains the `brief` action (parity test covers it, over its FULL parameter set)
- CLI `rmx memory brief` — table / `--gmd` / `--json` rendering only
- daemon `_op_*` for the write half (the derivation writes rows; `_store(write)` control point)
- optional: surfaced in `recall-state` when a brief is fresh and severe

### What this is NOT {#non-goals}

- Not an LLM call. No generated prose, no summarization model. Detectors are deterministic and
  the brief body names its evidence.
- Not a second clustering algorithm — it reads the `memory compile` plan.
- Not on by default in a hook until it has a measured cost ([[feedback_measure_the_path_users_run]],
  and the Stop-promote "0.13 s" that was 55 s live).

## Open Questions {#open-questions}

### Q1: What is this called? {#q1}
**Status:** RESOLVED

**Decision:** **brief**. Command `rmx memory brief`, mtype namespace `brief/<class>`, GMD doc id
`memory-briefs`.
**Rationale:** Explicitly not "cards". The noun had to miss every word this repo has already
spent — `finding` is BSD and review, `gap` is ch-gap-master and the deferral registry, `digest` is
`session/digest`, `subject` is `memory compile`. `brief` collides with none of them and sits in
the same register as `primer`, `composite`, `focus`, and `helix`: a short concrete noun for a
derived artifact.

### Q2: All six brief classes, or land the detectors incrementally? {#q2}
**Status:** RESOLVED

**Decision:** Four cheap detectors in task 8.1 (`corroborated`, `singleton`, `contradicted`,
`orphan-concept`); `unanswered` isolated in task 8.4 behind the Q3 gate; `stale` deferred until
helix phase 2 decides its storage fork ([[project_helix_phase2_storage_fork]]).
**Rationale:** The four read the compile plan and the degree counts — signal that already exists
and is already trusted. `unanswered` reads telemetry with a known confound. `stale` needs
edge-time storage that is not yet decided; building it now would bake in the losing fork.

`corroborated` / `singleton` / `contradicted` read the compile plan and are
cheap. `orphan-concept` needs a degree sweep. `unanswered` needs telemetry parsing and is the one
with a confounding hazard.

### Q3: Is `unanswered` trustworthy given the helix-log precedent? {#q3}
**Status:** RESOLVED (as a gate, not as an answer)

**Decision:** The detector does not ship until a pre-registered confound check passes, written to
`workflow/measurements/brief-unanswered-confound.md` BEFORE its numbers are read. A failed check
is a shipped negative result, not a reason to relax the threshold.
**Rationale:** [[project_helix_log_confounded]] is the exact failure: a log written by a path
that suppresses its own signal, then read as if it measured demand. Before `unanswered` ships it
needs a pre-registered check that the telemetry it reads is not self-suppressing — the same
discipline [[project_helix_phase2_decision_criterion]] applied.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | The noun | **brief** — `rmx memory brief`, mtype `brief/<class>`, doc `memory-briefs`. Not "cards". | 2026-09-15 |
| Q2 | Detector scope | Four cheap detectors in 8.1; `unanswered` isolated in 8.4 behind the Q3 gate; `stale` deferred to helix phase 2. | 2026-09-15 |
| Q3 | `unanswered` confound check | Pre-registered check written before its numbers are read; a failed check ships as a negative result. | 2026-09-15 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 8.1 | Brief detectors, note schema, evidence contract (no surface yet) | — |
| 8.2 | Verb + daemon op + CLI/MCP adapters; parity test | 8.1 |
| 8.3 | GMD index render + regenerate-from-store round trip | 8.1 |
| 8.4 | `unanswered` detector behind the Q3 confound check — **gate FAILED, not built** | 8.1 |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation
check on every new test; implementation summary per task under `workflow/implementation_summaries/`;
then `@ch-bsd` over the plan's commit range — remedy and re-review until CLEAN; then
`metadata.status` → `completed`.

**Plan-specific gate:** every brief class ships with a test that asserts the brief's evidence ids
resolve to real rows, and a mutation check that deleting the detector's call site turns the test
RED ([[impression_bsd_tests_bypass_wiring]]).
