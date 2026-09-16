---
gmd: "0.1"
id: rerank-window-ab-0916
title: "A/B: what the reranker actually sees — head truncation vs a query-anchored window"
tags: [measurement, rerank, retrieval-quality, bug-032, longmemeval]
metadata:
  node_type: measurement
  created: 2026-09-16
---

# A/B: head truncation vs a query-anchored window {#root}

rel: evidence-for -> [[task-12.3-rerank-doc-window]]
rel: part-of -> [[plan-12-open-bug-remediation]]
rel: reinforces -> [[feedback_causal_story_before_evidence]]

## What was measured, and what was NOT {#scope}

**Measured:** the mechanism. For all **896 answer-bearing turns** of
`longmemeval_oracle`, on the session documents exactly as `prepare.py` renders them for ingest:
does the answer-bearing turn survive the cut the reranker applies? A turn counts as covered when
its first 200 characters appear in the slice handed to the model. Both arms, same documents, same
questions, same budget.

**NOT measured:** end-to-end MRR/hit@5 on the `scan` surface. That run is ~2 h per arm on a
depth-uncontrolled surface whose reranker, under the load that matters, usually does not answer at
all (see [[rerank-cost-budget-0916]]). **No ranking claim is made here** — only a coverage claim,
which is the thing head truncation was hiding.

## The always-on surfaces, precisely {#always-on}

There are TWO always-on UserPromptSubmit hooks and they do not share a budget:

- `memory recall --stdin-json` caps at `RERANK_DOC_CHARS`=700 in `collect_rerank_docs`, which is
  below `WINDOW_MIN_CHARS`=1024, so its rerank input is **byte-identical** to before.
- `scan-prompt` reaches the reranker through `content_only_bundle` → `_rerank_bodied` →
  `rerank_entity_hits` → `collect_rerank_docs` with **no `doc_chars`**, so `RemoteReranker.score`
  windows at `MAX_DOC_CHARS`=2048 — above the floor. **`scan-prompt`'s rerank input IS changed**,
  and the RANKING effect there is unmeasured; this document measures coverage only (ch-bsd plan-12
  #s-3, correcting an earlier "the always-on hook path is unchanged").

## Reproducing it {#harness}

`eval/production/rerank_window_ab.py --oracle <path to longmemeval_oracle>`. The dataset stays out
of the repo; the harness does not, because these numbers chose `WINDOW_HEAD_FRAC` and
`WINDOW_MIN_CHARS` and have to be re-derivable when the reranker or the corpus moves.

## Result {#result}

Limit 2048 (the `MAX_DOC_CHARS` bound):

| arm | answer in the head (n=547) | answer past it (n=349) | total (n=896) |
|---|---|---|---|
| head truncation (before) | 541 | 0 | **541** (60.4%) |
| query-anchored window only | 383 | 119 | 502 (56.0%) |
| **head + query-anchored tail (shipped)** | 535 | 137 | **672** (75.0%) |

Limit 700 (the per-prompt hook's `RERANK_DOC_CHARS`):

| arm | total (n=896) |
|---|---|
| head truncation | 509 |
| split window at 0.5 | 500 |
| **shipped (falls back to the head below 1024)** | **509 — byte-identical** |

Cost: windowing 896 documents took **0.029 s** total (~32 µs/doc) at 2048. The slice length is
unchanged, so the per-pair model cost is unchanged.

## The result that corrected the plan {#correction}

The task spec proposed replacing head truncation with a KWIC window. **Measured alone, that is
worse than what it replaces** — 502 vs 541. 547 of the 896 answers are already inside the first
2048 chars, and moving the window away from the head loses 158 of them to gain 119.

The fix only pays when it KEEPS the head: half the budget on the head, half where the query
occurs. That was not the plan's hypothesis; it is what the numbers said.

Second correction: the split is **budget-sensitive**. At 700 chars two ~350-char halves cut the
answer turn in the middle and the split loses (500 vs 509), so below `WINDOW_MIN_CHARS` (1024) the
shipped code keeps head truncation byte-for-byte. The always-on hook path is therefore
**unchanged**, and bug-032's benefit lands on the 2048-char surfaces.

## Sensitivity worth knowing {#sensitivity}

The 200-char probe is a strict reading of "the model saw the answer"; a cross-encoder can score a
partial overlap. A shorter probe would raise every number and would likely narrow the 700-char gap.
The probe was fixed before the arms were compared and is not re-tuned after the fact.
