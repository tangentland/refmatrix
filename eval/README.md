# rmx vs CodeRankEmbed eval

Side-by-side retrieval eval on **CSN python** (CodeSearchNet, Python split,
BEIR layout) — the same dataset and split CoRNStack's `eval_csn.py` uses.

## Why

rmx is symbolic — no embeddings, no NL semantics. CodeRankEmbed is a dense
encoder fine-tuned for NL→code retrieval. Running them on the same set lets
us measure the floor of what the symbolic graph alone can do and quantify
the gap a dense retriever closes.

The rmx adapter is a deliberately simple BM25-style baseline:
- Each corpus doc → entity. Each token in the doc → concept.
- `mentions`-link from concept to doc with weight = term frequency.
- For a query: tokenize, look up each token's `top_weighted` doc list,
  fuse them with `fuse_rrf` (k=60).

That's what the symbolic graph can do *without* embeddings. The gap to
CodeRankEmbed is the headroom available to a hybrid (dense + graph) setup.

## Layout

```
eval/
  datasets.py                 # BEIR loader
  metrics.py                  # MRR@k, Recall@k, nDCG@k
  retrievers/
    rmx_retriever.py          # symbolic baseline using fuse_rrf
    coderankembed_retriever.py# sentence-transformers cornstack/CodeRankEmbed
  fetch_datasets.sh           # download + convert CSN to BEIR
  run.py                      # CLI: --model rmx|coderankembed|both
  compare.py                  # render results to markdown
  requirements.txt            # eval-only deps (torch, sentence-transformers)
  datasets/                   # downloaded data (gitignored)
  results/                    # run.tsv + metrics.json per (dataset, model)
```

## Setup

```bash
# 1. Fetch CSN python (BEIR-format)
./eval/fetch_datasets.sh

# 2. Eval-only venv (separate from rmx core)
python -m venv .venv-eval
. .venv-eval/bin/activate
pip install -e .
pip install -r eval/requirements.txt
```

## Run

```bash
# rmx baseline (fast, CPU)
python eval/run.py --dataset eval/datasets/csn_python --model rmx

# CodeRankEmbed (CPU works but slow; CUDA / MPS recommended)
python eval/run.py --dataset eval/datasets/csn_python \
    --model coderankembed --device mps --batch-size 64

# Both, then render the comparison
python eval/run.py --dataset eval/datasets/csn_python --model both --device mps
python eval/compare.py --out eval/results/REPORT.md
```

## Output

Each `(dataset, model)` writes:
- `results/<dataset>/<model>/run.tsv` — TREC-style `qid\tdid\trank\tscore`
- `results/<dataset>/<model>/metrics.json` — MRR/Recall/nDCG + elapsed

`compare.py` collates into one markdown table.

## Metric reference

- **MRR@1000** — primary metric in CoRNStack's CSN eval; reciprocal rank of
  the first relevant doc within top-1000.
- **MRR@10**, **Recall@{1,10,100}**, **nDCG@10** — standard BEIR set.

## Honest expectation

rmx will lose on CSN. CSN queries are natural-language docstrings that
share little lexical overlap with the code they describe. The rmx baseline
relies on token overlap — useful for code-to-code (`mentions:parser`) but
weak for NL-to-code. The number isn't the point; the gap is.

Hybrid next: encode corpus + queries with CodeRankEmbed, also rank
symbolically with rmx, fuse both rankings via `fuse_rrf`. That's the
cheapest test of whether the graph adds anything on top of dense retrieval.
