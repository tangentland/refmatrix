---
gmd: "0.1"
id: impl-task-6.1-plan-6-deferrals-docs-benchmark
title: "Task 6.1: stale deferrals removed, and the memory path stopped whispering"
tags: [implementation-summary, plan-6, deferrals, memory, no-silent-failures]
metadata:
  node_type: implementation-summary
  status: complete
  plan: plan-6-deferrals-docs-benchmark
  task: task-6.1-plan-6-deferrals-docs-benchmark
  created: 2026-09-16
---

# Task 6.1: stale deferrals removed, and the memory path stopped whispering {#root}

rel: implements -> [[task-6.1-plan-6-deferrals-docs-benchmark]]
rel: part-of -> [[plan-6-deferrals-docs-benchmark]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: related-to -> [[project_factslog_audit_verdict]]
rel: related-to -> [[project_gmd_bulk_link_perf]]

## What this task looked like, and what it actually was {#framing}

On paper: delete four stale comments. In practice three of the four phrases were load-bearing, and
one of them was covering a live defect on a memory path. The phrase was the symptom; the audit
was the task. {#framing-lead}

## The defect the comment was hiding {#defect}

`embedder._extract_memory` carried a comment reading "Phase A stub" above **two bare
`except Exception: pass` branches**. The function is on the production path — `extract_batch`
(the daemon's `_op_embed`), `context.py:553`, `reranker.py:418` — so:

- a memory entity whose `memory_content` sidecar row is missing fell through to the entity NAME
  and embedded the slug as if it were the body;
- a coref `apply` that raised was swallowed, and the row embedded un-substituted.

Neither raised, neither logged, neither was counted. The embed run reported `embedded=N` and looked
healthy, while N vectors described the wrong text — a plausible-looking neighbor for the wrong
query. That is exactly the failure `CLAUDE.md#no-silent-failures` names, sitting behind a comment
about a phase that ended months ago. {#defect-body}

## What shipped {#shipped}

- **`embedder.py`** — `_note_degraded(reason, entity_id, detail)` counts and logs every degraded
  extraction; `degraded_report()` / `reset_degraded()` expose the counters. The two bare excepts
  are now narrow, named, and counted (`memory_content_unreadable`, `memory_content_missing`,
  `coref_apply_failed`). **The fallback TEXT is deliberately unchanged** — this task made the
  degradation audible, it did not change what gets embedded. Module docstring corrected: the
  memory extractor exists, it is not a future phase. {#shipped-embedder}
- **`daemon.py`** — `_op_embed` resets before `extract_batch` and returns `degraded` on both
  exit paths. Embed runs daemon-side in the common case, so a counter that lived only in the CLI
  process would have read zero forever. {#shipped-daemon}
- **`cli.py`** — `_degraded_embed_line` renders the summary, accumulated across batches and
  printed after `done embedded=…`. A counter nobody prints is still silence. {#shipped-cli}
- **`sync.py`** — `yield_lock` / `yield_every` removed from FOUR signatures (`sync_files`,
  `sync_since`, `flush_queue`, `_sync_paths`). Verified dead before removal: no caller anywhere
  passes them. The daemon passes those names to `ingest_path` / `ingest_gmd_paths`, which really
  do use them — which is precisely why the dead copies were dangerous. They implied the sync loop
  yields the store lock mid-transaction. It does not, and must not. {#shipped-sync}
- **`ingest_gmd.py`** — "Full BM25 over node body text is deferred to v1" was not stale, it was
  **false**: body term frequencies land as weighted `mentions` edges (0.35.0/0.36.1) and
  `content_rank` scores over them. {#shipped-gmd}
- **`store.py`** — `_log_event`'s "Phase 2 will gate the catalog writes off" replaced with what
  the 2026-09 audit actually found: no edge-time history to recover, three write paths that never
  logged. facts.log is an observability surface, not a journal-in-waiting. {#shipped-store}
- **`workflow/deferral_registry.md`** — launchctl/Linux registered as a `fail-closed-seam`;
  bug-008's row updated to GRADUATED LIVE after checking the live hook. {#shipped-registry}

## The spec was wrong about one file {#correction}

Task 6.1 said to delete `src/refmatrix/duckdb_view.py` and `tests/test_duckdb_read_routing.py`.
**Neither was done, and neither should be.** `store.py:1762` imports `DuckCatalogView` at runtime;
`store.py:867` and `:1754` document `ReadConnection` as part of the cursor surface;
`tests/test_duckdb_read_routing.py` does not exist, while `tests/test_duckdb_parity.py` imports the
module and passes. The module looked orphaned when the plan was written and was not re-checked.
Following the spec literally would have broken the read path. Recorded in the task spec so the
next reader does not retry it. {#correction-body}

## Verification {#verification}

| gate | result |
|---|---|
| RED | `workflow/review-output/pytest-task-6.1-RED.log` — **9 failed, 1 passed** |
| GREEN | `workflow/review-output/pytest-task-6.1-GREEN2.log` — **14 passed** |
| Affected files | `workflow/review-output/pytest-task-6.1-affected.log` — **87 passed** (embedder, sync, dense ops, recall, subproc embed, duckdb parity) |
| GMD lint | 0 errors, 14 warnings (the established baseline) |

The `_op_embed` tests were checked against reality rather than trusted for being green: a direct
probe on a throwaway `mkdtemp` store wrote a real 384-dim Lance dataset, printed
`embed: degraded extraction entity=1 reason=memory_content_missing`, and returned
`{'embedded': 1, …, 'degraded': {'memory_content_missing': 1}}`. The suspicious 0.76 s runtime was
chased down rather than accepted — `sentence_transformers` is never imported in the test process
because the model lives in the shared out-of-process worker (0.42.0). Fast for a real reason, not
fast because it skipped. {#verification-probe}

## The guard {#guard}

`tests/test_deferrals_clean.py` bans the five phrases by grep, and a meta-test asserts the banned
list still has at least four entries — a guard whose list can be quietly emptied passes forever.
{#guard-body}
