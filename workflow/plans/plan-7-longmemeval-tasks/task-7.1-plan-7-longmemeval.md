---
gmd: "0.1"
id: task-7.1-plan-7-longmemeval
title: "Task 7.1: Fetch, session split, GMD reshape, qrels, haystacks, subsets"
tags: [task, plan-7]
metadata:
  node_type: task
  status: complete
  plan: plan-7-longmemeval
---

# Task 7.1: Fetch, session split, GMD reshape, qrels, haystacks, subsets {#root}

> Plan: [[plan-7-longmemeval]]
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-7-longmemeval]]

## Requirements {#requirements}

- `longmemeval_s` only (Q3). Fetch is explicit and offline-repeatable: the dataset lands under `DATA`, never inside the refmatrix tree — the watcher would ingest it (`feedback_generated_data_off_watched_tree`, and `eval/memaware/paths.py` records the incident).
- `paths.py` mirrors `eval/memaware/paths.py`: `LONGMEMEVAL_DATA` env override, volume default, `./data` fallback, `STORE_ROOT` directly under `DATA` so the partition name derives from the parent basename.
- Each question's `haystack_sessions` explodes to one GMD doc per session id, deduped across questions (sessions are shared between haystacks). Frontmatter carries `node_type: memory`, `type: longmemeval/session`, and the session timestamp as `date:` — temporal-reasoning questions are unanswerable without it.
- Emits `qrels.json` (question_id -> [session_id], from `answer_session_ids`), `haystacks.json` (question_id -> [session_id], the per-question candidate set the `restricted` mode needs), and `subsets/stratified-<n>.json` balanced across the six question types.
- Abstention questions (`_abs` suffix) are labelled and SCORED, not excluded. Verified against
  `longmemeval_s` on 2026-09-15: all 30 carry non-empty `answer_session_ids`, and every one of
  those ids is present in the question's own haystack. The gold sessions hold the *related but
  insufficient* evidence, so retrieval is well-defined for them — abstention is a decision the
  answer model makes, not a retrieval failure. They are reported as their own slice, because a
  retriever succeeding there does not mean the system answered correctly.
- Session ids dedupe across haystacks and the dedupe is lossless: 25,112 slots collapse to 19,829
  unique ids with ZERO content conflicts (measured 2026-09-15). `prepare.py` still hashes session
  content per id and fails loudly on a conflict rather than letting one question's haystack
  silently overwrite another's.
- Counts are printed and reconciled: sessions written, sessions deduped, questions with resolvable qrels, abstention questions. A question whose `answer_session_ids` does not resolve is COUNTED and NAMED, never skipped silently.

## Files to Create / Modify {#files}

- create `eval/production/longmemeval/paths.py`
- create `eval/production/longmemeval/prepare.py`
- create `eval/production/longmemeval/README.md`

## Test Strategy (RED first) {#test-strategy}

`tests/test_longmemeval_prepare.py` over a synthetic 3-question / 6-session fixture (no network):
- session split is lossless and deduped — every haystack session id appears exactly once on disk
- emitted GMD parses under `tools/gmd/lint.py` and carries a non-empty `date:`
- `qrels.json` maps each question (abstention included) to its `answer_session_ids`
- `haystacks.json` round-trips every question's full candidate set
- an unresolvable `answer_session_ids` entry is reported in the returned counts, not dropped
- two questions carrying the same session id with DIFFERENT content raise, rather than one silently overwriting the other
- abstention questions appear in `qrels.json` with their gold sessions and are flagged, not dropped
- the subset builder returns a type-balanced sample for a fixture with skewed type order

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-7.1-plan-7-longmemeval.md`.
- Committed on branch `task-7.1-plan-7-longmemeval`; merged `--no-ff` to `master`.
