---
gmd: "0.1"
id: plan-7-longmemeval
title: "LongMemEval wired into eval/production/ as an outside-comparable memory-retrieval number"
tags: [plan, eval, memory, benchmark]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-09-15
---

# Proposed Plan: LongMemEval as a production-path memory benchmark {#root}

**Date:** 2026-09-15
**Status:** Approved
**Location:** `workflow/plans/plan-7-longmemeval.md` — permanent home; stage is `metadata.status`.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[project_memaware_benchmark]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_main_path_must_exercise_core_mechanisms]]
rel: related-to -> [[project_csn_production_harness]]
rel: specifies -> [[task-7.1-plan-7-longmemeval]]
rel: specifies -> [[task-7.2-plan-7-longmemeval]]
rel: specifies -> [[task-7.3-plan-7-longmemeval]]
rel: specifies -> [[task-7.4-plan-7-longmemeval]]

## Context {#context}

rmx has two production-path numbers: CSN code retrieval (MRR@10 0.961, `eval/production/`) and
MemAware proactive surfacing (Layer A only, near-floor). Neither is a number an outsider can
place. **LongMemEval** (Wu et al. 2024) is the long-term-memory benchmark every competing memory
system reports on. Two landmarks: `mcp-memory-service` publishes 80.4% Recall@5 / 89.1% MRR with
per-type gaps at multi-session 70.7% and temporal-reasoning 72.0%; `agentmemory` (28.5k stars)
publishes **95.2% Recall@5 on LongMemEval-S**, from BM25 + vector + graph fused by RRF at k=60 —
architecturally the same three signals rmx fuses, which makes it the sharper comparison.

Neither states its haystack scoping, and both are almost certainly per-question. That is exactly
why this plan ships two modes and labels every table with its own (see [[#haystack]]): an
unlabelled Recall@5 is not comparable to anything.

Wiring it gives three things the repo does not have:

1. **External calibration.** A Recall@5 that a reader can compare to a published system.
2. **A prose-memory retrieval number on the path users run** — `rmx ingest-gmd --as-memory` →
   `rmx embed` → `rmx memory recall` / `rmx context` / `rmx scan-prompt`, no adapter class.
3. **Per-type failure structure.** LongMemEval labels every question by type
   (single-session-user / -assistant / -preference, multi-session, temporal-reasoning,
   knowledge-update, plus abstention variants). Multi-session and temporal-reasoning are exactly
   the two the conceptual-memory thesis claims the graph should win, and they are exactly the two
   where the published competitor is weakest.

The MemAware harness (`eval/memaware/`) already solved every structural problem this needs:
off-tree data volume (`paths.py`), session-per-file split, GMD reshape so prose produces a
`mentions` index at all, qrels from `answer_session_ids`, a free Layer A retrieval metric, and a
`METHODS` table of live rmx read surfaces. This plan is that harness retargeted, not a new one.

## Proposed Approach {#proposed-approach}

New directory `eval/production/longmemeval/` (harness code, version-controlled) with its data off
the watched tree per [[feedback_generated_data_off_watched_tree]], reusing the `paths.py` pattern
verbatim.

1. **`paths.py`** — `LONGMEMEVAL_DATA` env override, `/Volumes/littlebig/longmemeval` default,
   `./data` fallback; `STORE_ROOT` directly under `DATA` so the partition name derives correctly
   (the `memory-store` bug `memaware/paths.py` documents).
2. **`prepare.py`** — fetch `xiaowu0162/longmemeval` (`longmemeval_s` default), explode each
   question's `haystack_sessions` into one GMD doc per session under `corpus/<session_id>.md`,
   frontmatter `node_type: memory`, `type: longmemeval/session`, `date:` from the session
   timestamp (temporal-reasoning questions are unanswerable without it). Emit
   `qrels.json` (`question_id -> [session_id]` from `answer_session_ids`),
   `haystacks.json` (`question_id -> [session_id]` — the per-question candidate set),
   and type-stratified subsets.
3. **`ingest.py`** — dedicated store, own partition, no watcher, no launchd:
   `rmx ingest-gmd --as-memory --memory-mtype longmemeval/session` → `rmx embed --kinds memory`
   → `rmx memory compile`. Identical to `eval/memaware/ingest.py`.
4. **`run.py`** — Layer A retrieval scoring. `METHODS` covers `recall`, `recall-fuse`,
   `recall-rr`, `recall-fuse-rr`, `context`, `context-d2`, `scan`, `scan-nocontent`, with
   `--rerank`/`--no-rerank` pinned explicitly (0.42.0 default-on trap already documented in
   `eval/memaware/retrieval_eval.py`). Scores Recall@{1,5,10,20}, MRR, hit@k, broken out per
   question type as well as overall.
5. **`REPORT.md`** — every number with its condition, its corpus size, and an explicit statement
   of which scoring mode produced it (see Q1). No bare figure ships without those three.

### The haystack problem {#haystack}

LongMemEval is **per-question**: each of the 500 questions carries its own haystack (50 sessions
for `_s`, 500 for `_m`), and published Recall@5 is recall within that haystack. rmx indexes one
store. Two scoring modes, both implementable, and they are NOT the same number:

- **restricted** — one union store, retrieved DEEP (`--k <deep>`), then the ranked list is filtered
  to the question's own haystack and cut to k. This approximates per-question retrieval and is the
  mode comparable to published figures.

  It is an approximation, and the reason is worth stating: `ann_search(candidate_ids=...)` exists
  in the Python API (`test_dense_recall_respects_candidate_prefilter`) but **no CLI flag exposes
  it**. Reaching into the API to pass a candidate set would make this harness a bespoke path —
  precisely the sin [[feedback_measure_the_path_users_run]] was written about, where four ingest
  defects hid behind a true-looking 0.982 MRR. So the harness stays on the CLI and pays for it by
  retrieving deep.

  The approximation has a measurable cost and the harness reports it: for every question, whether
  the gold session appeared anywhere in the deep pool. That fraction is the **recall ceiling** —
  `restricted` can never score above it, and a ceiling far below 1.0 means the depth is too
  shallow, not that rmx missed. Every `restricted` table prints its depth and its ceiling beside
  the metrics. Exposing a CLI candidate-set flag is registered as the follow-up that would remove
  the approximation.
- **union** — one union store, no prefilter; the gold session must beat ~25k distractors instead
  of 49. Strictly harder, not comparable to anyone, and the more honest picture of what rmx does
  in production, where there is no oracle haystack.

Ship both, label both, never quote one as the other.

## Open Questions {#open-questions}

### Q1: Which scoring mode is the headline number? {#q1}
**Status:** RESOLVED

**Decision:** Both modes ship every run; `restricted` is the headline, `union` is printed beside it.
**Rationale:** `restricted` is the only mode comparable to a published figure, and external
calibration is the reason this plan exists. `union` is the only mode that describes what rmx does
in production, where no oracle haystack is handed to it. Quoting either alone is a lie of a
different kind, so both carry their mode in every table.

### Q2: Layer B (answer + LLM judge) in scope? {#q2}
**Status:** RESOLVED

**Decision:** Layer A only. Layer B is registered in `workflow/deferral_registry.md`, not built.
**Rationale:** MemAware's Layer B was built and never affordably run — building a second one
before the free metric has said anything repeats that. Layer A also gates Layer B usefully: if
Recall@20 is at the floor there is no QA accuracy for a paid run to find.

Layer A is deterministic and free. Layer B is 500 questions x 2 LLM calls per
condition and produces the QA-accuracy figure most papers quote. MemAware's Layer B was built and
never affordably run.

### Q3: `longmemeval_s` only, or `_m` too? {#q3}
**Status:** RESOLVED

**Decision:** `_s` only; `_m` registered as a deferral.
**Rationale:** `_s` is the variant the published competitor figures use, so it is the one that
buys calibration. `_m`'s ~250k-doc union store is days of ingest and a scale no rmx store has run.

`_s` is ~115k tokens/question (50 sessions); `_m` is 500 sessions/question and
is where the retrieval problem actually gets hard. `_m` union store is ~250k session docs — days
of ingest at current throughput.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Headline scoring mode | Both modes every run; `restricted` headline, `union` beside it, mode named in every table. | 2026-09-15 |
| Q2 | Layer B in scope | Layer A only; Layer B registered as a deferral. | 2026-09-15 |
| Q3 | `_s` only or `_m` too | `_s` only; `_m` registered as a deferral. | 2026-09-15 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 7.1 | `paths.py` + `prepare.py`: fetch, session split, GMD reshape, qrels, haystacks, subsets | — |
| 7.2 | `ingest.py`: dedicated off-tree store on the production ingest path | 7.1 |
| 7.3 | `run.py`: Layer A scoring, both haystack modes, per-type breakdown | 7.1 |
| 7.4 | `REPORT.md` + README citation, committed results artifact | 7.2, 7.3 |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation
check on every new test; implementation summary per task under `workflow/implementation_summaries/`;
then `@ch-bsd` over the plan's commit range — remedy and re-review until CLEAN; then
`metadata.status` → `completed`.

**Benchmark-specific gate:** no number enters `REPORT.md` or `README.md` without the harness
command that produced it, the corpus size, and the scoring mode. The
[[feedback_measure_the_path_users_run]] scar applies in full — the harness calls `rmx`, never an
adapter.
