---
gmd: "0.1"
id: plan-6-deferrals-docs-benchmark
title: "No stale deferrals, generated CLI docs, a committed benchmark artifact, registered mocks"
tags: [plan, remediation, bsd]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-09-14
  bsd_findings: "#bs-5, #sk-4, #meh-1, #meh-2"
---

# Proposed Plan: No stale deferrals, generated CLI docs, a committed benchmark artifact, registered mocks {#root}

**Date:** 2026-09-14
**Status:** Accepted
**Location:** `workflow/plans/plan-6-deferrals-docs-benchmark.md` — permanent home; stage is `metadata.status`.

rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: specifies -> [[task-6.1-plan-6-deferrals-docs-benchmark]]
rel: specifies -> [[task-6.2-plan-6-deferrals-docs-benchmark]]
rel: specifies -> [[task-6.3-plan-6-deferrals-docs-benchmark]]
rel: specifies -> [[task-6.4-plan-6-deferrals-docs-benchmark]]
rel: specifies -> [[task-6.5-plan-6-deferrals-docs-benchmark]]

## Context {#context}

BSD #bs-5, #sk-4, #meh-1, #meh-2: six docstrings describe systems that no longer exist or phases nobody scheduled
(`ingest_gmd.py:13`, `store.py:646`, `duckdb_view.py`, `embedder.py:203`, `sync.py:200`, `launchctl.py:322`);
`docs/ARCHITECTURE.md` documents 24 of 80 CLI commands; README's headline `0.961` has no committed artifact; 184
`monkeypatch.setattr` sites are unregistered; `verbs.py:148` swallows a daemon error; one test is perma-red.

## Proposed Approach {#proposed-approach}

1. Delete/rewrite each stale sentence; remove `duckdb_view.py` + its tests (or wire the flag — Q1); drop unused sync params;
   register the Linux-supervisor gap in `workflow/deferral_registry.md` as `fail-closed-seam`.
2. `scripts/gen-cli-tree.py` renders the click tree into `docs/ARCHITECTURE.md` between markers; a test asserts the doc section
   equals the render. README hooks table generated the same way from `hooks._claude_hook_block`.
3. `eval/production/csn_code.py --out <path>` writes `metrics.json`; commit the full-corpus run if it completes in-session, else
   README cites the committed 2000-doc REPORT number and marks 0.961 as historical (commit 57c7778) until regenerated.
4. Fix `test_context_op_honors_partition_under_ambient_drift` (stub daemon gains `_st`); `verbs.py:148` logs; mock registry sweep
   (classify by file; graduate the bridge lambda — done in plan 5).

## Open Questions {#open-questions}

### Q1: Q1 duckdb_view.py: delete or wire? {#q1}
**Status:** RESOLVED

**Decision:** Delete. The store is DuckDB-native; an env-flag facade nobody sets is a second path.
**Rationale:** see Decisions Log.

### Q2: Q2 Full-corpus benchmark in-session? {#q2}
**Status:** RESOLVED

**Decision:** Attempt once with a time box of 60 min on the production harness; otherwise ship the honest citation and a follow-up task.
**Rationale:** see Decisions Log.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Q1 duckdb_view.py: delete or wire? | Delete. The store is DuckDB-native; an env-flag facade nobody sets is a second path. | 2026-09-14 |
| Q2 | Q2 Full-corpus benchmark in-session? | Attempt once with a time box of 60 min on the production harness; otherwise ship the honest citation and a follow-up task. | 2026-09-14 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 6.1 | Stale deferrals removed or registered | — |
| 6.2 | Generated CLI tree + hooks table in docs | — |
| 6.3 | Benchmark artifact | — |
| 6.4 | Loud verbs.py partition detect, perma-red test, mock registry | — |
| 6.5 | The rewriter hook stops baking the generator's tree (bug-008) | — |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation check on every new test;
implementation summary per task under `workflow/implementation_summaries/`; then `@ch-bsd` over the plan's commit range —
remedy and re-review until the verdict is CLEAN; then the plan's `metadata.status` → `completed`.
