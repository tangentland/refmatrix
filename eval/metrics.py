"""Retrieval metrics. Matches CodeRankEmbed/BEIR conventions.

A `run` is the standard BEIR/TREC shape:
    run[qid] = {doc_id: score, ...}    score higher = better

`qrels` maps qid -> {doc_id: relevance>0}. We treat any positive score as
relevant (binary), which is what CSN and most CoIR tasks use.
"""
from __future__ import annotations

import math


def _ranked(run_for_q: dict[str, float], k: int) -> list[str]:
    return [d for d, _ in sorted(run_for_q.items(), key=lambda kv: -kv[1])[:k]]


def mrr_at_k(run: dict[str, dict[str, float]], qrels: dict[str, dict[str, int]], k: int = 1000) -> float:
    total = 0.0
    n = 0
    for qid, scored in run.items():
        rels = {d for d, r in qrels.get(qid, {}).items() if r > 0}
        if not rels:
            continue
        n += 1
        for rank, did in enumerate(_ranked(scored, k), start=1):
            if did in rels:
                total += 1.0 / rank
                break
    return total / n if n else 0.0


def recall_at_k(run: dict[str, dict[str, float]], qrels: dict[str, dict[str, int]], k: int) -> float:
    total = 0.0
    n = 0
    for qid, scored in run.items():
        rels = {d for d, r in qrels.get(qid, {}).items() if r > 0}
        if not rels:
            continue
        n += 1
        hits = sum(1 for d in _ranked(scored, k) if d in rels)
        total += hits / len(rels)
    return total / n if n else 0.0


def ndcg_at_k(run: dict[str, dict[str, float]], qrels: dict[str, dict[str, int]], k: int) -> float:
    total = 0.0
    n = 0
    for qid, scored in run.items():
        rel_map = {d: r for d, r in qrels.get(qid, {}).items() if r > 0}
        if not rel_map:
            continue
        n += 1
        dcg = 0.0
        for rank, did in enumerate(_ranked(scored, k), start=1):
            rel = rel_map.get(did, 0)
            if rel > 0:
                dcg += (2 ** rel - 1) / math.log2(rank + 1)
        ideal_rels = sorted(rel_map.values(), reverse=True)[:k]
        idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal_rels))
        if idcg > 0:
            total += dcg / idcg
    return total / n if n else 0.0


def all_metrics(run: dict[str, dict[str, float]], qrels: dict[str, dict[str, int]]) -> dict[str, float]:
    return {
        "MRR@1000": mrr_at_k(run, qrels, 1000),
        "MRR@10": mrr_at_k(run, qrels, 10),
        "Recall@1": recall_at_k(run, qrels, 1),
        "Recall@10": recall_at_k(run, qrels, 10),
        "Recall@100": recall_at_k(run, qrels, 100),
        "Recall@200": recall_at_k(run, qrels, 200),
        "Recall@500": recall_at_k(run, qrels, 500),
        "Recall@1000": recall_at_k(run, qrels, 1000),
        "nDCG@10": ndcg_at_k(run, qrels, 10),
    }
