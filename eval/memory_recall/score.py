#!/usr/bin/env python3
"""LLM-judge the pooled candidates, then score dense / symbolic / fused.

Two phases:
  1. JUDGE — for each (query, candidate) in candidates.jsonl, ask a cheap model
     (claude-haiku-4-5) whether the memory is relevant to the query. Graded
     0 (no) / 1 (related) / 2 (directly answers). Results cached to qrels.tsv
     (`qid<TAB>mid<TAB>rel`) so re-runs never re-pay. `--no-judge` skips this
     phase and scores against the existing qrels.tsv.
  2. SCORE — build a BEIR-style `run` per retriever (dense=-distance,
     symbolic=content_rank, fused=fuse_rrf at rrf_k ∈ {10,30,60,100}), then
     compute MRR@10 / Recall@1,5,10 / nDCG@10 against the judged qrels, reusing
     eval/metrics.py. Writes REPORT.md.

Run (judge needs `pip install anthropic` + ANTHROPIC_API_KEY; scoring needs
only refmatrix for fuse_rrf):

    /Users/tholley/refmatrix/.venv/bin/python score.py \
        --candidates candidates.jsonl --qrels qrels.tsv --out REPORT.md

The viascope set is the go/no-go: fused must beat max(dense, symbolic) on
MRR@10 at some rrf_k to justify flipping `memory recall --fuse` on by default.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

JUDGE_MODEL = "claude-haiku-4-5"   # cheapest tier ($1/$5 per MTok); ample for a yes/no
RRF_KS = [10, 30, 60, 100]

_JUDGE_SYS = (
    "You grade whether a stored project MEMORY is relevant to a developer's "
    "QUERY (a prompt they typed while working). Relevance = would surfacing "
    "this memory help answer or act on the query. Grade strictly:\n"
    "  2 = directly relevant (the memory is about this exact topic)\n"
    "  1 = related / partially useful\n"
    "  0 = not relevant\n"
    "Return only the JSON object."
)
_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"relevance": {"type": "integer", "enum": [0, 1, 2]}},
    "required": ["relevance"],
    "additionalProperties": False,
}


def _load_qrels(path: Path) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            qid, mid, rel = line.split("\t")
            qrels.setdefault(qid, {})[mid] = int(rel)
    return qrels


def _judge(rows: list[dict], qrels: dict[str, dict[str, int]], qrels_path: Path) -> None:
    """Fill qrels for any (qid, mid) not already judged. Appends to qrels.tsv
    incrementally so a crash/interrupt keeps prior labels."""
    import anthropic
    client = anthropic.Anthropic()
    with qrels_path.open("a", encoding="utf-8") as out:
        for r in rows:
            qid, text = r["qid"], r["text"]
            for cand in r["pool"]:
                mid = str(cand["mid"])
                if mid in qrels.get(qid, {}):
                    continue
                msg = (f"QUERY: {text}\n\nMEMORY ({cand['name']}):\n{cand['snippet']}\n\n"
                       "Grade relevance (0/1/2).")
                try:
                    resp = client.messages.create(
                        model=JUDGE_MODEL, max_tokens=64,
                        system=_JUDGE_SYS,
                        messages=[{"role": "user", "content": msg}],
                        output_config={"format": {"type": "json_schema",
                                                  "schema": _JUDGE_SCHEMA}},
                    )
                    txt = next(b.text for b in resp.content if b.type == "text")
                    rel = int(json.loads(txt)["relevance"])
                except Exception as e:
                    print(f"  judge error {qid}/{mid}: {e}")
                    continue
                qrels.setdefault(qid, {})[mid] = rel
                out.write(f"{qid}\t{mid}\t{rel}\n")
                out.flush()
            print(f"  judged {qid}: {len(qrels.get(qid, {}))} labels")


def _runs(rows: list[dict]) -> dict[str, dict[str, dict[str, float]]]:
    from refmatrix.query import fuse_rrf
    dense: dict[str, dict[str, float]] = {}
    symbolic: dict[str, dict[str, float]] = {}
    fused: dict[int, dict[str, dict[str, float]]] = {k: {} for k in RRF_KS}
    for r in rows:
        qid = r["qid"]
        d_ids = [int(mid) for mid, _ in r["dense"]]
        s_ids = [int(mid) for mid, _ in r["symbolic"]]
        dense[qid] = {str(mid): -float(dist) for mid, dist in r["dense"]}
        symbolic[qid] = {str(mid): float(sc) for mid, sc in r["symbolic"]}
        for k in RRF_KS:
            fused[k][qid] = {str(mid): sc for mid, sc in fuse_rrf([d_ids, s_ids], k=k)}
    out = {"dense": dense, "symbolic": symbolic}
    for k in RRF_KS:
        out[f"fused@{k}"] = fused[k]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default="candidates.jsonl")
    ap.add_argument("--qrels", default="qrels.tsv")
    ap.add_argument("--out", default="REPORT.md")
    ap.add_argument("--no-judge", action="store_true",
                    help="Skip the LLM judge; score against the existing qrels.tsv.")
    args = ap.parse_args()

    # Reuse eval/metrics.py — scope the sys.path insert so it can't shadow other imports.
    _eval_dir = str(Path(__file__).resolve().parent.parent)
    sys.path.insert(0, _eval_dir)
    try:
        from metrics import mrr_at_k, recall_at_k, ndcg_at_k
    finally:
        sys.path.remove(_eval_dir)

    rows = [json.loads(l) for l in Path(args.candidates).read_text().splitlines() if l.strip()]
    qrels_path = Path(args.qrels)
    qrels = _load_qrels(qrels_path)
    if not args.no_judge:
        _judge(rows, qrels, qrels_path)
    qrels = _load_qrels(qrels_path)

    judged = {qid for qid, d in qrels.items() if any(v > 0 for v in d.values())}
    runs = _runs(rows)

    def metrics(run):
        run = {q: s for q, s in run.items() if q in judged}
        return {
            "MRR@10": mrr_at_k(run, qrels, 10),
            "Recall@1": recall_at_k(run, qrels, 1),
            "Recall@5": recall_at_k(run, qrels, 5),
            "Recall@10": recall_at_k(run, qrels, 10),
            "nDCG@10": ndcg_at_k(run, qrels, 10),
        }

    results = {name: metrics(run) for name, run in runs.items()}
    cols = ["MRR@10", "Recall@1", "Recall@5", "Recall@10", "nDCG@10"]
    base = max(results["dense"]["MRR@10"], results["symbolic"]["MRR@10"])
    best_fused = max((results[f"fused@{k}"]["MRR@10"], k) for k in RRF_KS)

    lines = [
        "# Memory-recall fusion eval (viascope, real queries)",
        "",
        f"- Queries judged (≥1 relevant): **{len(judged)}** / {len(rows)} pooled",
        f"- Judge: `{JUDGE_MODEL}`, graded 0/1/2; relevance = r>0",
        f"- Go/no-go: fused must beat max(dense, symbolic) MRR@10 = **{base:.4f}**",
        "",
        "| method | " + " | ".join(cols) + " |",
        "|" + "---|" * (len(cols) + 1),
    ]
    for name in ["dense", "symbolic"] + [f"fused@{k}" for k in RRF_KS]:
        r = results[name]
        lines.append(f"| {name} | " + " | ".join(f"{r[c]:.4f}" for c in cols) + " |")
    verdict = ("FLIP default-on" if best_fused[0] > base + 1e-9 else "KEEP default-off")
    lines += [
        "",
        f"**Best fused:** rrf_k={best_fused[1]} at MRR@10={best_fused[0]:.4f} "
        f"(vs {base:.4f} best single). **Verdict: {verdict}.**",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
