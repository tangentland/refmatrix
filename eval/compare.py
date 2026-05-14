"""Render a markdown comparison from results/<dataset>/<model>/metrics.json files.

    python eval/compare.py --out eval/results/REPORT.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def collect(root: Path) -> dict[str, dict[str, dict]]:
    """Return: {dataset: {model: metrics_dict}}."""
    out: dict[str, dict[str, dict]] = {}
    for ds_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        ds_name = ds_dir.name
        for model_dir in sorted(p for p in ds_dir.iterdir() if p.is_dir()):
            m_path = model_dir / "metrics.json"
            if not m_path.exists():
                continue
            out.setdefault(ds_name, {})[model_dir.name] = json.loads(m_path.read_text())
    return out


def render(results: dict[str, dict[str, dict]]) -> str:
    lines = ["# rmx vs CodeRankEmbed", ""]
    metric_keys = ["MRR@10", "MRR@1000", "Recall@1", "Recall@10", "Recall@100", "nDCG@10"]
    for ds, models in results.items():
        lines.append(f"## {ds}")
        lines.append("")
        lines.append("| model | " + " | ".join(metric_keys) + " | elapsed (s) |")
        lines.append("|" + "|".join(["---"] * (len(metric_keys) + 2)) + "|")
        for model_name in sorted(models):
            row = models[model_name]
            cells = [f"{row.get(k, 0):.4f}" for k in metric_keys]
            elapsed = f"{row.get('elapsed_sec', 0):.1f}"
            lines.append(f"| {model_name} | " + " | ".join(cells) + f" | {elapsed} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, default=Path(__file__).resolve().parent / "results")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    if not args.results.exists():
        print(f"no results dir at {args.results}")
        return 1

    results = collect(args.results)
    md = render(results)
    if args.out:
        args.out.write_text(md + "\n")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
