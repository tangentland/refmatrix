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


def run_rmx(dataset_dir: Path, out_dir: Path, *, variant: str = "baseline", workers: int = 1) -> dict[str, float]:
    from retrievers.rmx_retriever import RmxRetriever

    ds = load_beir(dataset_dir)
    print(f"loaded {ds!r}")

    variant_config = {
        "baseline":           {"scorer": "tf_rrf"},
        "bm25":               {"scorer": "bm25"},
        "bm25_stem":          {"scorer": "bm25", "stem": True},
        "bm25_freqstop50":    {"scorer": "bm25", "freq_stop_threshold": 0.50},
        "bm25_freqstop30":    {"scorer": "bm25", "freq_stop_threshold": 0.30},
        "bm25_freqstop10":    {"scorer": "bm25", "freq_stop_threshold": 0.10},
        "bm25_idfpow15":      {"scorer": "bm25", "idf_power": 1.5},
        "bm25_idfpow20":      {"scorer": "bm25", "idf_power": 2.0},
        "bm25_docstring":     {"scorer": "bm25_multi", "linkage_weights": {"docstring": 2.0, "code": 1.0}},
        "bm25_docstring30":   {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}},
        "bm25_docstring_eq":  {"scorer": "bm25_multi", "linkage_weights": {"docstring": 1.0, "code": 1.0}},
        "bm25_docstring30_cov05": {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 0.5},
        "bm25_docstring30_cov10": {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 1.0},
        "bm25_docstring30_cov20": {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 2.0},
        "bm25_docstring30_cov30": {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 3.0},
        "bm25_docstring30_canon":            {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "canon_expand": True},
        "bm25_docstring30_cov20_canon":      {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 2.0, "canon_expand": True},
        "bm25_docstring30_cov30_cm10":       {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 3.0, "comention_alpha": 1.0},
        "bm25_docstring30_cov30_cm20":       {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 3.0, "comention_alpha": 2.0},
        "bm25_docstring30_cm20":             {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "comention_alpha": 2.0},
        "bm25_ast":             {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "defines": 5.0, "params": 2.0, "calls": 2.0, "code": 1.0}},
        "bm25_ast_cov30_cm20":  {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "defines": 5.0, "params": 2.0, "calls": 2.0, "code": 1.0}, "coverage_alpha": 3.0, "comention_alpha": 2.0},
        "bm25_ast_v2_cov30_cm20": {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "defines": 3.0, "params": 1.5, "calls": 1.5, "code": 1.0}, "coverage_alpha": 3.0, "comention_alpha": 2.0},
        # Bigram bonuses on top of current best (docstring30 + cov30 + cm20).
        "bm25_best_bg_ds3":  {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 3.0, "comention_alpha": 2.0, "bigram_source": "docstring", "bigram_weight": 3.0},
        "bm25_best_bg_ds5":  {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 3.0, "comention_alpha": 2.0, "bigram_source": "docstring", "bigram_weight": 5.0},
        "bm25_best_bg_code3": {"scorer": "bm25_multi", "linkage_weights": {"docstring": 3.0, "code": 1.0}, "coverage_alpha": 3.0, "comention_alpha": 2.0, "bigram_source": "code", "bigram_weight": 3.0},
    }
    if variant not in variant_config:
        raise SystemExit(f"unknown rmx variant: {variant}")
    r = RmxRetriever(**variant_config[variant])
    label = "rmx" if variant == "baseline" else f"rmx_{variant}"

    t0 = time.time()
    print(f"ingesting corpus into rmx store (variant={variant})...")
    r.ingest_corpus(ds.corpus)
    print(f"  ingest done in {time.time()-t0:.1f}s")

    print(f"retrieving (workers={workers})...")
    t1 = time.time()
    run = r.run(ds.queries, top_k=1000, workers=workers)
    elapsed = time.time() - t1
    print(f"  retrieve done in {elapsed:.1f}s")

    metrics = all_metrics(run, ds.qrels)
    _save_run(run, out_dir / "run.tsv")
    _save_metrics(metrics, out_dir / "metrics.json", model=label, dataset=ds.name, elapsed=elapsed)
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
    p.add_argument(
        "--variant", default="baseline",
        help="rmx variant: baseline | bm25 | ... (each writes to results/<ds>/rmx_<variant>/)",
    )
    p.add_argument(
        "--workers", type=int, default=1,
        help="Parallel workers for rmx retrieve (fork-pool; bm25/bm25_multi only).",
    )
    args = p.parse_args()

    if not args.dataset.exists():
        print(f"dataset dir not found: {args.dataset}", file=sys.stderr)
        print("run eval/fetch_datasets.sh first", file=sys.stderr)
        return 2

    dataset_name = args.dataset.name
    args.out.mkdir(parents=True, exist_ok=True)

    if args.model in ("rmx", "both"):
        rmx_label = "rmx" if args.variant == "baseline" else f"rmx_{args.variant}"
        out = _run_dir(args.out, rmx_label, dataset_name)
        m = run_rmx(args.dataset, out, variant=args.variant, workers=args.workers)
        print(f"\n[{rmx_label}] {dataset_name}: {m}\n")

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
