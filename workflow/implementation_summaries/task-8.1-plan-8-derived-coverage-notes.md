---
gmd: "0.1"
id: task-8.1-summary
title: "Task 8.1 summary: brief detectors and the evidence contract"
tags: [implementation-summary, plan-8]
metadata:
  node_type: summary
  task: task-8.1-plan-8-derived-coverage-notes
  created: 2026-09-15
---

# Task 8.1 summary {#root}

rel: realizes -> [[task-8.1-plan-8-derived-coverage-notes]]
rel: part-of -> [[plan-8-derived-coverage-notes]]
rel: derives-from -> [[project_memory_compile_shipped]]
rel: reinforces -> [[feedback_reuse_shared_stoplist]]
rel: reinforces -> [[feedback_no_silent_failures]]

## What shipped {#shipped}

`src/refmatrix/brief.py` — four deterministic detectors, a `Brief` dataclass whose constructor
enforces the evidence contract, and `compile_briefs` as the run.

| Class | Fires when |
|---|---|
| `corroborated` | a compile subject has >= N members spanning >= M **distinct days** |
| `singleton` | a memory appears in the compile plan's `unclustered` list |
| `contradicted` | a `contradicts` pair exists and neither side was superseded |
| `orphan-concept` | `mentions` degree >= threshold, `defines` + `lead` degree zero |

## Three design calls worth keeping {#calls}

**Distinct DAYS, not members.** Size alone is not corroboration: four memories written in one
sitting are one observation recorded four times — the writer's mood, not the corpus's agreement.

**`singleton` reads `unclustered`, not clusters of size one.** `compile_memories` enforces
`min_size` and a lone memory never becomes a cluster at all, so "clusters of size 1" would have
been permanently empty — a detector that can never fire, which is worse than no detector because
it reads as evidence of a clean corpus.

**A resolved contradiction is history.** The `supersedes` edge IS the resolution; re-reporting it
would train a reader to skim past the class.

## The contract {#contract}

`Brief.__post_init__` raises on an empty evidence list. A detector that cannot point at a row
cannot emit, which is the single rule keeping this a diagnostic rather than a generator of
plausible sentences. There is no LLM call in the module and no summarization step.

Exclusions are imported from `consolidate` **by identity**, and a test asserts the `is`
relationship rather than equality — so a future copy-paste fails rather than drifting. The same
junk-token bug appeared at four call sites in this codebase because each grew its own copy of the
list.

`compile_briefs` skips the two plan-derived classes when no compile plan is passed and reports
that in `classes_not_run`, rather than silently triggering a cluster pass that costs vectors and
minutes. The cheap classes are never gated behind the expensive one.

## Tests {#tests}

18 tests, `tests/test_brief_detectors.py`, one fixture store per class.

- RED: `workflow/review-output/red-task-8.1.log`
- GREEN: `workflow/review-output/green-task-8.1.log`

Seven mutants, all killed: empty evidence allowed; corroborated ignoring date spread; superseded
contradictions still firing; orphan ignoring `defines`/`lead`; an unresolvable singleton going
uncounted; operational rows admitted; the exclusion list copy-pasted instead of imported.
