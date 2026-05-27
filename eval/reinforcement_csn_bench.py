"""Phase B5 reinforcement on csn_python.

Question: does the reinforcement signal lift retrieval on a real
corpus (not the tie-break-only synthetic in eval/reinforcement_bench.py)?

Procedure:
  1. Load csn_python BEIR dataset (queries + corpus + qrels).
  2. Ingest into RmxRetriever with the canonical
     bm25_docstring30_cov30_cm20 stack at alpha=0 (baseline). Record
     per-query rank of the correct doc.
  3. Seed `reinforces` memories: for every query whose correct doc
     ranks worse than 1 in the baseline, pick the top-TF token in
     the correct doc that's also in the query, write a memory
     reinforcing that concept. Optional --contradict-distractor also
     seeds a `contradicts` memory on the top discriminating token
     of the doc that DID win at rank 1.
  4. Re-run the same retriever with reinforce_alpha=ALPHA. Diff MRR.

Usage:
    python eval/reinforcement_csn_bench.py \\
        --dataset eval/datasets/csn_python \\
        --sample 500 --alpha 0.3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src"))

from retrievers.rmx_retriever import RmxRetriever, BM25Params, expand_token  # noqa: E402
from metrics import all_metrics, mrr_at_k, recall_at_k  # noqa: E402


def _load_beir(root: Path, sample: int | None):
    corpus = {}
    queries = {}
    qrels: dict[str, dict[str, int]] = {}
    with (root / "corpus.jsonl").open() as f:
        for line in f:
            d = json.loads(line)
            corpus[d["_id"]] = {
                "title": d.get("title", ""),
                "text": d.get("text", ""),
                "metadata": d.get("metadata") or {},
            }
    with (root / "queries.jsonl").open() as f:
        for line in f:
            d = json.loads(line)
            queries[d["_id"]] = d["text"]
    with (root / "qrels" / "test.tsv").open() as f:
        next(f)  # header
        for line in f:
            qid, did, score = line.strip().split("\t")
            if int(score) > 0:
                qrels.setdefault(qid, {})[did] = int(score)
    if sample is not None and sample < len(queries):
        sampled_qids = list(queries)[:sample]
        queries = {q: queries[q] for q in sampled_qids}
        qrels = {q: qrels[q] for q in sampled_qids if q in qrels}
    return corpus, queries, qrels


def _correct_doc_tokens(text: str) -> list[str]:
    return expand_token(text)


def _seed_reinforcement(
    r: RmxRetriever, queries: dict, qrels: dict, corpus: dict,
    baseline_run: dict, alpha_weight: float, contradict: bool,
) -> int:
    """For each query where the correct doc didn't win at rank 1, seed
    a reinforces memory on the strongest overlap token. Returns total
    memories seeded."""
    s = r.store
    seeded = 0
    for qid, q_text in queries.items():
        rels = qrels.get(qid) or {}
        if not rels:
            continue
        correct_did = next(iter(rels))
        ranked = sorted(baseline_run.get(qid, {}).items(), key=lambda kv: -kv[1])
        if not ranked:
            continue
        top1_did = ranked[0][0]
        if top1_did == correct_did:
            # Baseline already wins; nothing to reinforce.
            continue
        # Pick the strongest token that appears in BOTH the query and the
        # correct doc — that's the concept the memory layer would have
        # observed about this topic.
        q_tokens = set(_correct_doc_tokens(q_text))
        c_doc = corpus.get(correct_did) or {}
        c_text = (c_doc.get("title") or "") + " " + (c_doc.get("text") or "")
        c_tokens = _correct_doc_tokens(c_text)
        c_tf: dict[str, int] = {}
        for t in c_tokens:
            c_tf[t] = c_tf.get(t, 0) + 1
        overlap = [(t, c_tf[t]) for t in q_tokens if t in c_tf]
        overlap.sort(key=lambda kv: -kv[1])
        if not overlap:
            continue
        pos_tok = overlap[0][0]
        m = s.add_memory(
            f"bench-pos-{qid}", f"users mean {pos_tok}",
            mtype="observation",
        )
        cid = s._concept.get(pos_tok)
        if cid is None:
            cid = s.add_concept(pos_tok)
            s._concept[pos_tok] = cid
        s.link("reinforces", cid, m, weight=alpha_weight)
        seeded += 1
        # Optional contradicts on the distractor's strongest unique token.
        if contradict:
            d_doc = corpus.get(top1_did) or {}
            d_text = (d_doc.get("title") or "") + " " + (d_doc.get("text") or "")
            d_tokens = _correct_doc_tokens(d_text)
            d_only = [t for t in d_tokens if t in q_tokens and t != pos_tok]
            if d_only:
                neg_tok = d_only[0]
                m_neg = s.add_memory(
                    f"bench-neg-{qid}", f"users avoid {neg_tok}",
                    mtype="observation",
                )
                neg_cid = s._concept.get(neg_tok)
                if neg_cid is None:
                    neg_cid = s.add_concept(neg_tok)
                    s._concept[neg_tok] = neg_cid
                s.link("contradicts", neg_cid, m_neg, weight=alpha_weight)
                seeded += 1
    r.clear_reinforcement_cache()
    return seeded


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--sample", type=int, default=500,
                   help="Number of queries to evaluate (default 500). "
                        "Pass 0 for full set (~14k).")
    p.add_argument("--alpha", type=float, default=0.3,
                   help="Reinforcement strength (default 0.3). 0 = baseline.")
    p.add_argument("--seed-weight", type=float, default=1.0,
                   help="Weight per seeded memory (default 1.0).")
    p.add_argument("--contradict-distractor", action="store_true",
                   help="Also seed a contradicts memory on the distractor's "
                        "strongest unique token.")
    args = p.parse_args()

    print(f"loading dataset {args.dataset} (sample={args.sample or 'all'})")
    corpus, queries, qrels = _load_beir(
        args.dataset, args.sample if args.sample > 0 else None,
    )
    print(f"  corpus={len(corpus)} queries={len(queries)} qrels={len(qrels)}")

    print("=== baseline (alpha=0) ===")
    r = RmxRetriever(
        scorer="bm25_multi",
        linkage_weights={"docstring": 3.0, "code": 1.0},
        coverage_alpha=3.0,
        comention_alpha=2.0,
        reinforce_alpha=0.0,
    )
    t0 = time.time()
    r.ingest_corpus(corpus)
    print(f"  ingest {time.time()-t0:.1f}s")
    t1 = time.time()
    baseline_run = r.run(queries, top_k=20)
    print(f"  retrieve {time.time()-t1:.1f}s")
    baseline_metrics = all_metrics(baseline_run, qrels)
    for k, v in baseline_metrics.items():
        print(f"  {k:<14s} {v:.4f}")

    # Seed reinforcement, re-run on the SAME store.
    r.reinforce_alpha = args.alpha
    seeded = _seed_reinforcement(
        r, queries, qrels, corpus, baseline_run,
        args.seed_weight, args.contradict_distractor,
    )
    print(f"\nseeded {seeded} memories for failing queries; "
          f"re-running with alpha={args.alpha}")

    t2 = time.time()
    reinforced_run = r.run(queries, top_k=20)
    print(f"  retrieve {time.time()-t2:.1f}s")
    reinforced_metrics = all_metrics(reinforced_run, qrels)

    print(f"\n=== reinforced (alpha={args.alpha}) ===")
    for k, v in reinforced_metrics.items():
        delta = v - baseline_metrics[k]
        marker = "[+]" if delta > 0 else ("[-]" if delta < 0 else "[=]")
        print(f"  {k:<14s} {v:.4f}  ({delta:+.4f}) {marker}")

    # Per-query rank churn report.
    moved = sum(
        1 for qid in queries
        if list(sorted(baseline_run.get(qid, {}).items(), key=lambda kv: -kv[1]))[:1]
        != list(sorted(reinforced_run.get(qid, {}).items(), key=lambda kv: -kv[1]))[:1]
    )
    print(f"\nrank-1 changed on {moved}/{len(queries)} queries "
          f"({100*moved/max(1,len(queries)):.1f}%)")
    r.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
