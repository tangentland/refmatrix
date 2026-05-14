"""Recompute metrics from a saved run.tsv against a BEIR dataset.

Useful when the original eval saved a deep run (top-1000) but the live
all_metrics() doesn't include every Recall@K we want. Avoids re-running
the retriever.

    python eval/recompute_metrics.py \
        --run eval/results/csn_python/rmx/run.tsv \
        --dataset eval/datasets/csn_python \
        --ks 1 10 100 200 500 1000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from datasets import load_beir
from metrics import mrr_at_k, ndcg_at_k, recall_at_k


def load_run_tsv(path: Path) -> dict[str, dict[str, float]]:
    run: dict[str, dict[str, float]] = {}
    with path.open() as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            qid, did, _rank, score = parts[0], parts[1], parts[2], parts[3]
            run.setdefault(qid, {})[did] = float(score)
    return run


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument(
        "--ks", type=int, nargs="+",
        default=[1, 10, 100, 200, 500, 1000],
        help="Recall@K values to compute.",
    )
    p.add_argument(
        "--write", action="store_true",
        help="Overwrite the metrics.json next to run.tsv.",
    )
    args = p.parse_args()

    print(f"loading run from {args.run}...")
    t0 = time.time()
    run = load_run_tsv(args.run)
    print(f"  {len(run)} queries in {time.time()-t0:.1f}s")

    print(f"loading dataset from {args.dataset}...")
    ds = load_beir(args.dataset)
    print(f"  {ds!r}")

    metrics: dict[str, float] = {
        "MRR@1000": mrr_at_k(run, ds.qrels, 1000),
        "MRR@10": mrr_at_k(run, ds.qrels, 10),
        "nDCG@10": ndcg_at_k(run, ds.qrels, 10),
    }
    for k in args.ks:
        metrics[f"Recall@{k}"] = recall_at_k(run, ds.qrels, k)

    print()
    for name, val in metrics.items():
        print(f"  {name:14s} {val:.4f}")

    if args.write:
        out = args.run.with_name("metrics.json")
        existing = {}
        if out.exists():
            existing = json.loads(out.read_text())
        existing.update(metrics)
        out.write_text(json.dumps(existing, indent=2) + "\n")
        print(f"\nwrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
