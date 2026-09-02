# Production-pipeline retrieval: the dense half was searching filenames

Every other harness in `eval/` bypasses the code it claims to measure.
`eval/retrievers/rmx_retriever.py` imports `fuse_rrf` and `Store` and builds its
own index straight from the BEIR jsonl, with its own tokenizer and its own
docstring splitter. It calls `refmatrix.ingest` **zero** times. So the 0.982
MRR@10 in `eval/results/REPORT.md` measures the scoring stack, and says nothing
about what production ingest writes.

This harness closes that gap: it writes the corpus to disk and drives `rmx init`
/ `ingest` / `embed` / `context` / `recall` exactly as a user does.

## Setup

CSN python subsample materialized as real `.py` files off the watched tree
(`prepare.py`), then two stores built through the real CLI. The conditions run
the SAME pass and produce the same 4,009 code entities, the same concepts, the
same `mentions` edges — the only difference is whether the docstring is written
as the entity's `tldr`:

    nobody     rmx ingest --semantic, with RMX_INGEST_BODIES=0
    semantic   rmx ingest --semantic

## Result — 2000 docs, 300 queries

| condition / surface | MRR@10 | Recall@1 | Recall@10 | nDCG@10 |
|---|---:|---:|---:|---:|
| nobody / symbolic | 0.9883 | 0.9867 | 0.9900 | 0.9888 |
| semantic / symbolic | 0.9883 | 0.9867 | 0.9900 | 0.9888 |
| **nobody / dense** | **0.6307** | **0.5667** | **0.7600** | **0.6619** |
| **semantic / dense** | **0.9744** | **0.9667** | **0.9833** | **0.9767** |

Dense **MRR@10 +54%**, **Recall@1 +71%**. Symbolic identical to four decimals.

## Why the split is the whole finding

`content_rank` already had the docstring. The keyword pass tokenizes
`ast.get_docstring(node)` into `keyword/<word>` concepts and hangs `mentions`
edges off them, and has for a long time — BM25 never lost anything, which is
why the symbolic column does not move by a single ranked position.

The dense side lost all of it. `embedder._extract_code` concatenates name +
`tldr`, so with no body the vector for a function was the embedding of
`unit_10010.py::get_first` — a filename. **0.6307 is nearest-neighbour search
over identifiers.** The docstring text was parsed on every ingest, mined for
keywords, and discarded before anything semantic could see it.

That is the same defect found in `_extract_concept` (anchored GMD concepts
returning their heading), one layer down and far larger. It silently halved
dense retrieval in every store this pipeline has ever built, and no existing
eval could see it, because no existing eval runs the pipeline.

## What these numbers are not

- **A subsample.** 2,000 docs against CSN's 43,827 — a smaller haystack, so the
  absolute values run high. Compare the conditions to each other; never to
  `eval/results/REPORT.md`.
- **A claim that dense beats symbolic.** It does not (0.9744 vs 0.9883). The
  point is that a dense half which was actively broken is now near parity,
  which is the precondition for fusion or reranking to be worth anything.
- **Generalizable to sparse-docstring code.** CSN units almost all carry a
  docstring. On a codebase where few do, the gain shrinks proportionally.

## Reproduce

```bash
python3 eval/production/prepare.py --out /path/off/the/watched/tree --queries 300
python3 eval/production/run.py --data /path/off/the/watched/tree
```

`prepare.py` refuses to write inside the refmatrix tree: the watcher would
ingest the corpus into the project's own store, which has happened before.
