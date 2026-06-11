#!/usr/bin/env python3
"""Pool dense ∪ symbolic candidates per query for TREC-style judging.

For each mined query, run BOTH retrievers read-only against the deployed memory
partition and record their ranked id-lists plus a judged candidate pool (the
union of the two top-Ks, with snippets for the LLM judge). Fusion is derived at
SCORE time from these two lists, so we don't need to re-run it per rrf_k here.

Requires the dense extra (lance + sentence-transformers) and the deployed
refmatrix code — run under the deploy venv:

    PYTHONPATH=/Users/tholley/claude_tools/refmatrix/src \
      /Users/tholley/refmatrix/.venv/bin/python pool_candidates.py \
      --root /Users/tholley/github/atollogy/bdep/viascope \
      --partition memory-viascope --k 10 \
      --queries queries.jsonl --out candidates.jsonl

Output (one JSON object per line):
    {"qid","text",
     "dense":[[mid,distance],...],        # ascending distance = best-first
     "symbolic":[[mid,bm25],...],         # descending score = best-first
     "pool":[{"mid","name","snippet"},...]}  # union, for the judge
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _snippet(store, mid: int, limit: int = 240) -> str:
    try:
        m = store.get_memory(mid)
        if m and m.get("content"):
            return " ".join(m["content"].split())[:limit]
    except Exception:
        pass
    e = store.get_entity_by_id(mid)
    return (e.name if e else f"id={mid}")[:limit]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--partition", default="memory-viascope")
    ap.add_argument("--k", type=int, default=10, help="top-k per retriever into the pool")
    ap.add_argument("--queries", default="queries.jsonl")
    ap.add_argument("--out", default="candidates.jsonl")
    args = ap.parse_args()

    from refmatrix.store import Store
    from refmatrix.embedder import Embedder
    from refmatrix import recall as R

    root = Path(args.root) / ".refmatrix"
    store = Store(root, partition=args.partition, read_only=True)
    emb = Embedder()

    queries = [json.loads(l) for l in Path(args.queries).read_text().splitlines() if l.strip()]
    out_lines: list[str] = []
    for q in queries:
        text = q["text"]
        # dense: [(mid, distance)] ascending; symbolic: content_rank [(mid, score)] descending
        try:
            dense = R.dense_recall(store, emb, text, k=max(args.k, 60), kinds=["memory"])
        except Exception as e:
            dense = []
            print(f"  [{q['qid']}] dense failed: {e}")
        terms = R._content_terms(text)
        symbolic = store.content_rank(terms, kinds=["memory"], limit=max(args.k, 60)) if terms else []

        pool_ids: list[int] = []
        for mid, _ in dense[: args.k]:
            if mid not in pool_ids:
                pool_ids.append(mid)
        for mid, _ in symbolic[: args.k]:
            if mid not in pool_ids:
                pool_ids.append(mid)
        pool = [{"mid": mid, "name": (store.get_entity_by_id(mid).name
                                      if store.get_entity_by_id(mid) else str(mid)),
                 "snippet": _snippet(store, mid)} for mid in pool_ids]

        out_lines.append(json.dumps({
            "qid": q["qid"], "text": text,
            "dense": [[int(mid), float(d)] for mid, d in dense],
            "symbolic": [[int(mid), float(s)] for mid, s in symbolic],
            "pool": pool,
        }, ensure_ascii=False))
        print(f"  {q['qid']}: dense={len(dense)} symbolic={len(symbolic)} pool={len(pool)}")

    Path(args.out).write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"pooled {len(out_lines)} queries -> {args.out}")


if __name__ == "__main__":
    main()
