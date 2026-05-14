"""Run rmx and/or CodeRankEmbed against a BEIR-format dataset.

Example:
    python eval/run.py --dataset eval/datasets/csn_python --model rmx
    python eval/run.py --dataset eval/datasets/csn_python --model coderankembed
    python eval/run.py --dataset eval/datasets/csn_python --model both
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Allow running as `python eval/run.py` from repo root without installing.
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent / "src") not in sys.path:
    sys.path.insert(0, str(_HERE.parent / "src"))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from datasets import load_beir
from metrics import all_metrics


def _run_dir(out_root: Path, model: str, dataset_name: str) -> Path:
    p = out_root / dataset_name / model
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_run(run: dict, path: Path) -> None:
    with path.open("w") as f:
        for qid, scored in run.items():
            ranked = sorted(scored.items(), key=lambda kv: -kv[1])
            for rank, (did, score) in enumerate(ranked, start=1):
                f.write(f"{qid}\t{did}\t{rank}\t{score:.6f}\n")


def _save_metrics(metrics: dict[str, float], path: Path, *, model: str, dataset: str, elapsed: float) -> None:
    payload = {"model": model, "dataset": dataset, "elapsed_sec": elapsed, **metrics}
    path.write_text(json.dumps(payload, indent=2) + "\n")


def run_rmx(dataset_dir: Path, out_dir: Path) -> dict[str, float]:
    from retrievers.rmx_retriever import RmxRetriever

    ds = load_beir(dataset_dir)
    print(f"loaded {ds!r}")

    r = RmxRetriever()
    t0 = time.time()
    print("ingesting corpus into rmx store...")
    r.ingest_corpus(ds.corpus)
    print(f"  ingest done in {time.time()-t0:.1f}s")

    print("retrieving...")
    t1 = time.time()
    run = r.run(ds.queries, top_k=1000)
    elapsed = time.time() - t1
    print(f"  retrieve done in {elapsed:.1f}s")

    metrics = all_metrics(run, ds.qrels)
    _save_run(run, out_dir / "run.tsv")
    _save_metrics(metrics, out_dir / "metrics.json", model="rmx", dataset=ds.name, elapsed=elapsed)
    r.close()
    return metrics


def run_coderankembed(dataset_dir: Path, out_dir: Path, *, device: str, batch_size: int, bf16: bool) -> dict[str, float]:
    from retrievers.coderankembed_retriever import CodeRankEmbedRetriever

    ds = load_beir(dataset_dir)
    print(f"loaded {ds!r}")

    r = CodeRankEmbedRetriever(device=device, batch_size=batch_size, bf16=bf16)
    t0 = time.time()
    print("encoding corpus...")
    r.ingest_corpus(ds.corpus)
    print(f"  encode-corpus done in {time.time()-t0:.1f}s")

    print("encoding queries + ranking...")
    t1 = time.time()
    run = r.run(ds.queries, top_k=1000)
    elapsed = time.time() - t1
    print(f"  done in {elapsed:.1f}s")

    metrics = all_metrics(run, ds.qrels)
    _save_run(run, out_dir / "run.tsv")
    _save_metrics(metrics, out_dir / "metrics.json", model="coderankembed", dataset=ds.name, elapsed=elapsed)
    return metrics


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True,
                   help="Path to BEIR dataset directory (e.g., eval/datasets/csn_python)")
    p.add_argument("--model", choices=["rmx", "coderankembed", "both"], default="rmx")
    p.add_argument("--out", type=Path, default=_HERE / "results")
    p.add_argument("--device", default="cpu", help="CodeRankEmbed device (cpu / cuda / mps)")
    p.add_argument("--batch-size", type=int, default=32, help="CodeRankEmbed batch size")
    p.add_argument("--bf16", action="store_true", help="Use bf16 for CodeRankEmbed (needs CUDA)")
    args = p.parse_args()

    if not args.dataset.exists():
        print(f"dataset dir not found: {args.dataset}", file=sys.stderr)
        print("run eval/fetch_datasets.sh first", file=sys.stderr)
        return 2

    dataset_name = args.dataset.name
    args.out.mkdir(parents=True, exist_ok=True)

    if args.model in ("rmx", "both"):
        out = _run_dir(args.out, "rmx", dataset_name)
        m = run_rmx(args.dataset, out)
        print(f"\n[rmx] {dataset_name}: {m}\n")

    if args.model in ("coderankembed", "both"):
        out = _run_dir(args.out, "coderankembed", dataset_name)
        m = run_coderankembed(
            args.dataset, out,
            device=args.device, batch_size=args.batch_size, bf16=args.bf16,
        )
        print(f"\n[coderankembed] {dataset_name}: {m}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
