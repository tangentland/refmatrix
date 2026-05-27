"""Phase B5 reinforcement-scoring benchmark.

Synthesizes a small labeled corpus (16 docs, 12 queries) where each
query has one correct doc and one near-distractor that overlaps on
surface tokens but resolves to a different concept. Runs the
bm25_docstring30_cov30_cm20 stack twice:

  baseline:  alpha=0   (ADR-safe ship default)
  reinforced: alpha=α  with seeded memories that `reinforces` the
                       correct concept and `contradicts` the
                       distractor concept

Prints MRR@10 / Recall@1 for both runs. Used to tune `RMX_REINFORCE_*`
defaults; the same scenarios run as a pytest regression
(`tests/test_reinforcement_bench.py`).

Run standalone:

    .venv-eval/bin/python eval/reinforcement_bench.py
    .venv-eval/bin/python eval/reinforcement_bench.py --alpha 0.3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src"))

from retrievers.rmx_retriever import RmxRetriever, BM25Params  # noqa: E402
from metrics import all_metrics  # noqa: E402


# 12 (query, correct_doc, distractor_doc, concept_pair) scenarios. Each
# row says: "for query Q, doc_correct is the truth and doc_distractor
# overlaps on tokens but means something different." Memories link
# concept_pos -> reinforces (boosts correct) and concept_neg -> contradicts
# (dampens distractor).
SCENARIOS = [
    # query, doc_correct, doc_distractor, concept_pos, concept_neg
    # Concepts are full alphabetic words — the rmx tokenizer splits on
    # camelCase and drops single-digit tails, so "md5" / "sha1" wouldn't
    # survive as discriminating tokens.
    ("parse input payload",
     "doc_a01", "doc_b01", "parse", "dump"),
    ("encode value text",
     "doc_a02", "doc_b02", "encode", "decode"),
    ("hash bytes digest",
     "doc_a03", "doc_b03", "hash", "compare"),
    ("retry request backoff",
     "doc_a04", "doc_b04", "retry", "abort"),
    ("connect cache server",
     "doc_a05", "doc_b05", "connect", "publish"),
    ("compress two iterables",
     "doc_a06", "doc_b06", "compress", "expand"),
    ("flatten nested items",
     "doc_a07", "doc_b07", "flatten", "chunk"),
    ("split text tokens",
     "doc_a08", "doc_b08", "split", "concat"),
    ("load file rows",
     "doc_a09", "doc_b09", "load", "save"),
    ("validate address format",
     "doc_a10", "doc_b10", "validate", "render"),
    ("sort ascending",
     "doc_a11", "doc_b11", "sort", "shuffle"),
    ("filter items predicate",
     "doc_a12", "doc_b12", "filter", "groupby"),
]


def _doc(name: str, docstring: str, body: str) -> dict:
    return {
        "title": docstring,
        "text": (
            f"def {name}(arg):\n"
            f"    \"\"\"{docstring}\"\"\"\n"
            f"    {body}\n"
            f"    return arg\n"
        ),
        "metadata": {"lang": "python"},
    }


def build_corpus() -> tuple[dict, dict, dict]:
    """Build an adversarial corpus where the distractor doc wins on
    raw BM25 by stuffing the positive concept token multiple times.

    Both docs use generic function names so `defines` doesn't shortcut
    the discrimination. The single-token query matches `pos` in both
    docs; the distractor has 4x the term frequency so BM25 picks it.
    Per-concept signals (`reinforces` boost on `pos`, `contradicts`
    dampen on `neg`) lift the correct doc and pull the distractor
    down through `per_doc_rescore`.
    """
    corpus: dict[str, dict] = {}
    queries: dict[str, str] = {}
    qrels: dict[str, dict[str, int]] = {}

    # The rmx eval tokenizer is a *bag of unique tokens* per doc (see
    # `expand_token` — dedups via a per-call seen set), so TF stuffing
    # has no effect. We make the docs tie on BM25 and put the
    # distractor FIRST in insertion order so the entity-id tie-break
    # (ascending) hands the distractor the win at baseline. The bench
    # then measures whether reinforcement flips the tie.
    for i, (_q, correct, distractor, pos, neg) in enumerate(SCENARIOS):
        # Insert distractor first → lower entity_id → wins the tie.
        corpus[distractor] = _doc(
            f"helper_{i}",
            f"helper {pos} {neg}",
            f"value = arg",
        )
        corpus[correct] = _doc(
            f"func_{i}",
            f"helper {pos}",
            f"value = arg",
        )
        qid = f"q{i}"
        queries[qid] = pos
        qrels[qid] = {correct: 1}
    return corpus, queries, qrels


def seed_memories(r: RmxRetriever, *, n_each: int = 3) -> None:
    """For each scenario, write `n_each` reinforcing memories on
    concept_pos and `n_each` contradicting memories on concept_neg.
    Multiple memories accumulate signal toward the cap so the
    rescore factor approaches its alpha-bounded limit instead of
    sitting near zero (one weight=1 memory leaves signal=1 ≪ cap=5
    and tanh(1/5) ≈ 0.2 only)."""
    s = r.store
    for i, (_q, _cor, _dist, pos, neg) in enumerate(SCENARIOS):
        pos_cid = s.resolve_concept_ids(pos, strict=False)
        neg_cid = s.resolve_concept_ids(neg, strict=False)
        for k in range(n_each):
            if pos_cid:
                m = s.add_memory(
                    f"obs-pos-{i}-{k}", f"users want {pos}",
                    mtype="observation",
                )
                s.link("reinforces", pos_cid[0], m, weight=1.0)
            if neg_cid:
                m = s.add_memory(
                    f"obs-neg-{i}-{k}", f"users avoid {neg}",
                    mtype="observation",
                )
                s.link("contradicts", neg_cid[0], m, weight=1.0)
    r.clear_reinforcement_cache()


def run_once(*, alpha: float, verbose: bool = False) -> tuple[dict, dict]:
    corpus, queries, qrels = build_corpus()
    r = RmxRetriever(
        scorer="bm25",
        bm25=BM25Params(k1=1.5, b=0.0),
        reinforce_alpha=alpha,
    )
    r.ingest_corpus(corpus)
    if alpha > 0:
        seed_memories(r)
    run = r.run(queries, top_k=20)
    metrics = all_metrics(run, qrels)
    if verbose:
        for qid in queries:
            ranked = sorted(run[qid].items(), key=lambda kv: -kv[1])[:3]
            target = list(qrels[qid])[0]
            mark = "OK " if ranked and ranked[0][0] == target else "BAD"
            print(f"  {mark} {qid:>4s}  {queries[qid]!r:<42s} → {ranked}")
    r.close()
    return metrics, run


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alpha", type=float, default=0.3,
                   help="Reinforcement rescore strength (default 0.3).")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Print per-query top-3 hits with OK/BAD markers.")
    args = p.parse_args()

    print("=== baseline (alpha=0) ===")
    base, _ = run_once(alpha=0.0, verbose=args.verbose)
    for k, v in base.items():
        print(f"  {k:<14s} {v:.4f}")

    print(f"\n=== reinforced (alpha={args.alpha}) ===")
    rein, _ = run_once(alpha=args.alpha, verbose=args.verbose)
    for k, v in rein.items():
        delta = rein[k] - base[k]
        print(f"  {k:<14s} {v:.4f}  ({delta:+.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
