---
gmd: "0.1"
id: plan-5-memory-bridge-complete
title: "The memory bridge ingests every file, counts what it skips, survives overlap, and is tested for real"
tags: [plan, remediation, bsd]
metadata:
  node_type: plan
  status: approved
  created: 2026-09-14
  bsd_findings: "#bs-1, #sk-1, #sk-2, #meh-2, #meh-3"
---

# Proposed Plan: The memory bridge ingests every file, counts what it skips, survives overlap, and is tested for real {#root}

**Date:** 2026-09-14
**Status:** Accepted
**Location:** `workflow/plans/plan-5-memory-bridge-complete.md` — permanent home; stage is `metadata.status`.

rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: specifies -> [[task-5.1-plan-5-memory-bridge-complete]]
rel: specifies -> [[task-5.2-plan-5-memory-bridge-complete]]
rel: specifies -> [[task-5.3-plan-5-memory-bridge-complete]]

## Context {#context}

BSD #bs-1, #sk-1, #sk-2, #meh-2, #meh-3: the 0.66.1 bridge (`ingest-gmd --as-memory`) skips the 21 non-GMD files in the
memory dir with no counter; `memory sync-disk` is a second bridge nothing runs (README still teaches it); two overlapping bridge
runs hit the single-active-ingest guard and print FAILED; the bridge tests monkeypatch the bridge; the widen branch is
untested; `handoff.finalize_save_state` swallows subject-filing errors.

## Proposed Approach {#proposed-approach}

1. `ingest_gmd_paths(..., lenient=True)` for `--as-memory`: a file without `gmd:` still becomes a memory (doc_id = stem, mtype
   from `metadata.type` else default); `IngestStats.skipped_non_gmd` + `skipped_unparseable` counted and printed.
2. `memory sync-disk` becomes a thin alias of the bridge (same code path, deprecation note); README/ARCHITECTURE updated.
3. `_sync_memory_dir`: on `ingest already active`, poll `ingest_gmd_status` for the running job; if its targets cover the memdir,
   wait (bounded, `RMX_BRIDGE_WAIT_S`=120) and return its report; else retry once after it finishes.
4. Real-path tests on a tmp store; `finalize_save_state` returns `filed_subject_error` instead of `pass`.

## Open Questions {#open-questions}

### Q1: Q1 Lenient parse or route non-GMD through sync-disk? {#q1}
**Status:** RESOLVED

**Decision:** Lenient parse: one bridge, one identity rule (frontmatter `id` else stem), one report.
**Rationale:** see Decisions Log.

### Q2: Q2 Keep `memory sync-disk`? {#q2}
**Status:** RESOLVED

**Decision:** Keep the name as an alias for one release with a deprecation line; delete in 0.68.
**Rationale:** see Decisions Log.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Q1 Lenient parse or route non-GMD through sync-disk? | Lenient parse: one bridge, one identity rule (frontmatter `id` else stem), one report. | 2026-09-14 |
| Q2 | Q2 Keep `memory sync-disk`? | Keep the name as an alias for one release with a deprecation line; delete in 0.68. | 2026-09-14 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 5.1 | Lenient bridge + skipped counters + sync-disk alias | — |
| 5.2 | Bridge overlap: wait for the active job | 5.1 |
| 5.3 | Real tests replace mocks; widen + subject-filing loudness | 5.1 |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation check on every new test;
implementation summary per task under `workflow/implementation_summaries/`; then `@ch-bsd` over the plan's commit range —
remedy and re-review until the verdict is CLEAN; then the plan's `metadata.status` → `completed`.
