---
gmd: "0.1"
id: task-7.1-summary
title: "Task 7.1 summary: LongMemEval fetch, session explode, GMD reshape, labels"
tags: [implementation-summary, plan-7]
metadata:
  node_type: summary
  task: task-7.1-plan-7-longmemeval
  created: 2026-09-15
---

# Task 7.1 summary {#root}

rel: realizes -> [[task-7.1-plan-7-longmemeval]]
rel: part-of -> [[plan-7-longmemeval]]

## What shipped {#shipped}

`eval/production/longmemeval/paths.py` and `prepare.py`. `paths.py` is the MemAware off-tree data
contract verbatim: `LONGMEMEVAL_DATA` override, `/Volumes/littlebig/longmemeval` default, `./data`
fallback, `STORE_ROOT` directly under `DATA` so the partition derives as `longmemeval` rather than
repeating MemAware's `memory-store` naming bug.

`prepare.py` fetches the split from HuggingFace (`huggingface_hub`, not `datasets` — `eval/` is on
`sys.path` during eval runs and `eval/datasets.py` shadows the HF package,
[[reference_eval_datasets_shadow]]), explodes every question's haystack into one GMD file per
session, and emits `qrels.json`, `haystacks.json`, `questions.json`, and a type-stratified subset.

## Measured on the real corpus {#measured}

`python3 prepare.py --split s --per-type 20`, 2026-09-15, 74s wall:

| | |
|---|---|
| questions | 500 |
| haystack session slots | 25,112 |
| sessions written | 19,829 |
| deduped | 5,283 |
| content conflicts | **0** |
| questions with resolvable gold | 500 / 500 |
| unresolved gold ids | 0 |
| abstention questions | 30 |
| corpus on disk | 240 MB |

GMD lint over a random 200-file sample: 0 errors, 0 warnings.

## The spec correction {#correction}

The task spec as first written said abstention questions "have no gold session and must be
excluded from Recall/MRR". That was wrong, and checking beat assuming: all 30 `_abs` questions
carry non-empty `answer_session_ids`, and every one of those ids is present in the question's own
haystack. The gold sessions hold the related-but-insufficient evidence. Retrieval is therefore
well defined for them and they are SCORED; abstaining is a decision the answer model makes, not a
retrieval outcome. They are flagged in `questions.json` so `run.py` reports them as their own
slice. Spec and task 7.3 were corrected before any code was written against the wrong reading.

## Tests {#tests}

13 tests, `tests/test_longmemeval_prepare.py`, all on a synthetic 3-question / 6-session fixture —
the real split is a 278MB off-tree download and a test that needs it is a test that does not run.

- RED: `workflow/review-output/red-task-7.1.log` (collection error, module absent)
- GREEN: `workflow/review-output/green-task-7.1.log` (13 passed)

Mutation check — five mutants, all killed:

| Mutant | Result |
|---|---|
| drop `date:` from frontmatter | 1 failed |
| drop the session-id conflict check | 1 failed |
| drop the GMD frontmatter opener | 2 failed |
| make an unresolvable gold id a silent skip | 1 failed |
| replace stratification with file-order truncation | 1 failed |

Two first-pass mutants survived and were themselves wrong, not the tests: one failed to apply
(shell quoting) and one preserved type balance while claiming to remove it. Both were rewritten
until they exercised the behavior the test names.

## Why prose had to become GMD {#why-gmd}

Not a formatting preference. rmx's general markdown pass extracts only structured signals, and the
MemAware measurement is on record: plain chat transcripts produced 1309 doc entities, **0
`mentions` rows and 3 concepts** — no graph at all, every symbolic surface degraded to the grep
backstop. `ingest_gmd` runs the body term-frequency sweep the symbolic index is built from, so
frontmatter is what makes the corpus retrievable at all.

Turn roles are preserved as `### <role> (turn N)` blocks because three of the six question types
turn on who said a thing; a flattened transcript erases the distinction the benchmark tests.
