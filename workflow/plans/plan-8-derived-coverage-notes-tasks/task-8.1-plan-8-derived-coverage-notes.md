---
gmd: "0.1"
id: task-8.1-plan-8-derived-coverage-notes
title: "Task 8.1: Brief detectors, note schema, evidence contract"
tags: [task, plan-8]
metadata:
  node_type: task
  status: complete
  plan: plan-8-derived-coverage-notes
---

# Task 8.1: Brief detectors, note schema, evidence contract {#root}

> Plan: [[plan-8-derived-coverage-notes]]
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-8-derived-coverage-notes]]

## Requirements {#requirements}

- New module `src/refmatrix/brief.py`, sibling of `consolidate.py`. Fully concrete — no stub branches, no phase markers (the CLAUDE.md no-mocks rule).
- A **brief** is a derived `kind=memory` row, mtype namespace `brief/<class>`, carrying: class, subject/concept label, a one-line finding, and `evidence` — a list of entity ids that a reader can resolve. **A brief with empty evidence is a bug, not a brief**: the constructor refuses it.
- Detectors in this task (Q2 — the cheap four, all reading signal that already exists):
  - `brief/corroborated` — a `memory compile` subject with >= N members spanning >= M distinct dates
  - `brief/singleton` — a compile subject whose cluster has exactly one member
  - `brief/contradicted` — two memories joined by a `contradicts` edge with neither superseded
  - `brief/orphan-concept` — a concept with `mentions` degree >= threshold and `defines` + `lead` degree zero
- Deterministic. No LLM call, no generated prose. Thresholds are parameters with stated defaults, not magic numbers buried in the body.
- Operational content is excluded the same way `consolidate.py` excludes it (`DEFAULT_EXCLUDE_MTYPES`, `_OPERATIONAL_RE`) — session and digest rows are artifacts, not knowledge, and they would dominate every class. Reuse those constants; do not re-declare them ([[feedback_reuse_shared_stoplist]] — the same junk-token bug appeared at four call sites for exactly this reason).
- Every skipped row is COUNTED and returned in the result ([[feedback_no_silent_failures]]).

## Files to Create / Modify {#files}

- create `src/refmatrix/brief.py`
- modify `src/refmatrix/consolidate.py` only if a constant needs exporting (no logic change)

## Test Strategy (RED first) {#test-strategy}

`tests/test_brief_detectors.py`, one fixture store per class:
- `corroborated` fires on a 4-member/3-date subject and NOT on a 4-member/1-date subject
- `singleton` fires on a 1-member cluster and not on a 2-member one
- `contradicted` fires on an unresolved `contradicts` pair and NOT when one side is superseded
- `orphan-concept` fires on high-mentions/zero-defines and not when a `defines` row exists
- constructing a brief with empty evidence RAISES
- every evidence id returned by every detector resolves to a real row in the fixture store
- session/digest rows never appear in any class
- skipped rows are counted and the count is non-zero on a fixture containing one unembedded row

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-8.1-plan-8-derived-coverage-notes.md`.
- Committed on branch `task-8.1-plan-8-derived-coverage-notes`; merged `--no-ff` to `master`.
