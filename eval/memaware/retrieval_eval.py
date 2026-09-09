#!/usr/bin/env python3
"""Layer A: does the retriever find the right session? No LLM, no API cost.

MemAware's own harness measures *continuity accuracy* — whether an answer model
visibly used the past context — which takes two LLM calls per question and
conflates two failures: the retriever never surfaced the session, or it did and
the answer model ignored it. Because every question names its
`answer_session_ids` and prepare.py split the corpus one-file-per-session, that
distinction is recoverable for free as a document-level retrieval metric.

Run this first. It is deterministic, costs nothing, and tells you whether a
paid run is even worth launching: if Recall@20 is at the floor, continuity
accuracy has nowhere to come from.

Methods:
  bm25       upstream's own BM25 (via tools/bm25_rank.mjs), re-chunked per session
  recall     `rmx memory recall` — dense ANN over bge-small
  recall-fuse`rmx memory recall --fuse` — dense RRF-fused with content_rank BM25
  context    `rmx context` — symbolic content-rank + graph walk
  scan       `rmx scan-prompt` — the proactive surface the product actually ships
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from paths import DATA, PARTITION, QRELS, RESULTS, STORE_ROOT, SUBSETS, rmx_env

HERE = Path(__file__).resolve().parent
ROOT = STORE_ROOT


# ─── metrics ───────────────────────────────────────────────────────────────

def recall_at_k(ranked: list[str], rel: set[str], k: int) -> float:
    if not rel:
        return 0.0
    return len(set(ranked[:k]) & rel) / len(rel)


def rr_at_k(ranked: list[str], rel: set[str], k: int) -> float:
    for i, doc in enumerate(ranked[:k], 1):
        if doc in rel:
            return 1.0 / i
    return 0.0


def hit_at_k(ranked: list[str], rel: set[str], k: int) -> float:
    return 1.0 if set(ranked[:k]) & rel else 0.0


# ─── rmx adapters ──────────────────────────────────────────────────────────

def _env() -> dict:
    return rmx_env()


def _rmx_json(args: list[str], rmx: str) -> object:
    p = subprocess.run([rmx, *args], env=_env(), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"rmx {' '.join(args)} -> exit {p.returncode}\n{p.stderr[-800:]}")
    out = p.stdout.strip()
    if not out:
        return None
    return json.loads(out)


def _ids(obj, seen=None) -> list[str]:
    """Pull session ids out of whatever shape a read surface returned.

    The read surfaces disagree on envelope (`hits`, `rows`, `neighbors`,
    `memories`) and on whether an id arrives as `name`, `entity`, or a `path`.
    Rather than pin one shape per command — which rots the moment an output
    grows a field — walk the structure in order and keep the first id-looking
    string per record. Order is preserved, which is the whole point: these are
    ranked lists.
    """
    out, seen = [], (seen if seen is not None else set())

    def take(v: str) -> None:
        # Graph nodes arrive anchored (`answer_8ee04a2e#root`) and grep hits
        # arrive as paths; the qrels are bare session ids, which is the file
        # stem and the part of the node name before the anchor.
        sid = Path(v).stem if ("/" in v or v.endswith(".md")) else v
        sid = sid.split("#", 1)[0]
        if sid and sid not in seen:
            seen.add(sid)
            out.append(sid)

    def walk(o) -> None:
        if isinstance(o, dict):
            for key in ("name", "entity", "id", "path", "file"):
                v = o.get(key)
                if isinstance(v, str) and v:
                    take(v)
                    break
            for v in o.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return out


def m_recall(q: str, k: int, rmx: str, fuse: bool = False,
             rerank: bool = False) -> list[str]:
    args = ["memory", "recall", q, "--json", "-k", str(k)]
    if fuse:
        args.append("--fuse")
    # Always explicit. `--rerank` defaults ON in the daemon as of 0.42.0, so a
    # method that passed no flag would silently measure whatever the daemon's
    # env happened to be — and the pre-0.42.0 numbers in REPORT.md were all
    # taken without a reranker. Pinning it here keeps old rows comparable and
    # makes the new rows a controlled A/B against them.
    args.append("--rerank" if rerank else "--no-rerank")
    return _ids(_rmx_json(args, rmx))[:k]


def m_context(q: str, k: int, rmx: str, degree: int = 0) -> list[str]:
    args = ["context", q, "--format", "json"]
    if degree:
        args += ["--degree", str(degree)]
    return _ids(_rmx_json(args, rmx))[:k]


def m_scan(q: str, k: int, rmx: str, content: bool = True,
           rank: str = "ppr") -> list[str]:
    args = ["scan-prompt", q, "--format", "json", "--no-composite",
            "--rank", rank]
    if not content:
        args.append("--no-content")
    return _ids(_rmx_json(args, rmx))[:k]


METHODS = {
    "recall": lambda q, k, r: m_recall(q, k, r),
    "recall-fuse": lambda q, k, r: m_recall(q, k, r, fuse=True),
    # 0.42.0 cross-encoder rerank of the retrieved shortlist. Same retrieval,
    # different ordering — so a gain here is precision the retriever already
    # had and was mis-ranking, and Recall@20 should be ~flat while MRR moves.
    "recall-rr": lambda q, k, r: m_recall(q, k, r, rerank=True),
    "recall-fuse-rr": lambda q, k, r: m_recall(q, k, r, fuse=True, rerank=True),
    "context": m_context,
    # Seeded-PPR expansion (0.63.1): degree-2 walk from the content hits.
    # The candidate-set A/B — CSN was saturated (R@10 0.99), this surface
    # has real misses.
    "context-d2": lambda q, k, r: m_context(q, k, r, degree=2),
    "scan": m_scan,
    # Concept path only. The content bundle is emitted first and carries most
    # of the ids, so it masks any change to concept selection/ranking —
    # isolating it is the only way to see whether the concept path moved.
    "scan-nocontent": lambda q, k, r: m_scan(q, k, r, content=False),
    # Full enrichment: degree-2 walk over canonical-expanded seeds, coalesced
    # by seed-reach. `--no-composite` means no STM here anyway, and MemAware
    # items have no session continuity, so the STM merge contributes nothing
    # to these numbers by construction.
    "scan-enrich": lambda q, k, r: m_scan(q, k, r, rank="enrich"),
    "scan-enrich-nocontent": lambda q, k, r: m_scan(
        q, k, r, content=False, rank="enrich"),
    # Lift-scored association: seeds + the concepts whose overlap with the
    # prompt's documents is most SURPRISING, rather than most massive. Pair
    # with RMX_SCAN_SHAPE0_FLOOR=0 to see it without the shape-0 gate, which
    # is calibrated on code and drops the rare prose content words the anchor
    # needs (`sneakers` df=22 is gated out; `there` df=864 is not).
    "scan-assoc": lambda q, k, r: m_scan(q, k, r, rank="assoc"),
    "scan-assoc-nocontent": lambda q, k, r: m_scan(
        q, k, r, content=False, rank="assoc"),
    # Core clique -> tldr expansion -> keep only nodes >1 core member reached.
    # NOTE: MemAware items have no session continuity, so the STM half of the
    # core is empty here and a single-concept question falls back to PPR. This
    # measures the cull, not the design.
    "scan-net": lambda q, k, r: m_scan(q, k, r, rank="net"),
    "scan-net-nocontent": lambda q, k, r: m_scan(
        q, k, r, content=False, rank="net"),
}


# ─── run ───────────────────────────────────────────────────────────────────

def load_questions(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf8"))


def score(rankings: dict[str, list[str]], questions: list[dict],
          qrels: dict[str, list[str]], ks: list[int]) -> dict:
    by_tier: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        qid = q["question_id"]
        rel = {Path(p).stem for p in qrels.get(qid, [])}
        if not rel:
            continue
        ranked = rankings.get(qid) or []
        row = {"mrr": rr_at_k(ranked, rel, max(ks))}
        for k in ks:
            row[f"recall@{k}"] = recall_at_k(ranked, rel, k)
            row[f"hit@{k}"] = hit_at_k(ranked, rel, k)
        by_tier[q.get("difficulty", "unknown")].append(row)
        by_tier["overall"].append(row)

    summary = {}
    for tier, rows in by_tier.items():
        summary[tier] = {"n": len(rows)}
        if rows:
            for metric in rows[0]:
                summary[tier][metric] = sum(r[metric] for r in rows) / len(rows)
    return summary


def print_table(name: str, summary: dict, ks: list[int]) -> None:
    tiers = [t for t in ("easy", "medium", "hard", "overall") if t in summary]
    cols = ["mrr"] + [f"hit@{k}" for k in ks] + [f"recall@{k}" for k in ks]
    print(f"\n  === {name}\n")
    print("  " + "tier".ljust(9) + "n".rjust(5) + "".join(c.rjust(11) for c in cols))
    print("  " + "-" * (14 + 11 * len(cols)))
    for t in tiers:
        s = summary[t]
        print("  " + t.ljust(9) + str(s["n"]).rjust(5)
              + "".join(f"{s.get(c, 0):.3f}".rjust(11) for c in cols))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", action="append", default=None,
                    help=f"live rmx surfaces {sorted(METHODS)}, or a precomputed "
                         "condition name ('bm25', 'bm25-daily', 'latticedb') "
                         "whose ranker under tools/ has already run. Repeatable.")
    ap.add_argument("--questions", type=Path,
                    default=SUBSETS / "stratified-30.json")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--at", default="1,5,10,20", help="comma-separated cutoffs")
    ap.add_argument("--rmx", default="rmx")
    ap.add_argument("--workers", type=int, default=4,
                    help="parallel rmx calls (reads hit the lock-free replica)")
    ap.add_argument("--probe", metavar="METHOD",
                    help="dump one raw JSON response for METHOD and exit")
    args = ap.parse_args()

    questions = load_questions(args.questions)
    qrels = json.loads(QRELS.read_text(encoding="utf8"))
    ks = [int(x) for x in args.at.split(",")]
    RESULTS.mkdir(parents=True, exist_ok=True)

    if args.probe:
        q = questions[0]["question"]
        cmd = {"recall": ["memory", "recall", q, "--json", "-k", "5"],
               "recall-fuse": ["memory", "recall", q, "--json", "-k", "5", "--fuse"],
               "context": ["context", q, "--format", "json"],
               "scan": ["scan-prompt", q, "--format", "json", "--no-composite"]}[args.probe]
        print(json.dumps(_rmx_json(cmd, args.rmx), indent=1)[:4000])
        return

    methods = args.method or ["bm25", "latticedb", *METHODS]
    for name in methods:
        rank_path = RESULTS / f"rank-{name}.json"
        if name not in METHODS:
            # Precomputed by a tools/ ranker (tools/bm25_rank.mjs,
            # tools/latticedb_rank.py). Anything not in METHODS is expected to
            # have dropped its rankings here already.
            if not rank_path.exists():
                sys.exit(
                    f"  ! {rank_path} missing. Precomputed conditions come from\n"
                    f"    node tools/bm25_rank.mjs --questions {args.questions} --k {args.k}\n"
                    f"    python3 tools/latticedb_rank.py --questions {args.questions} --k {args.k}")
            rankings = json.loads(rank_path.read_text(encoding="utf8"))
        else:
            fn = METHODS[name]
            def one(q, fn=fn):
                try:
                    return q["question_id"], fn(q["question"], args.k, args.rmx)
                except Exception as exc:              # a dead surface is a 0, not a crash
                    print(f"  ! {name} {q['question_id']}: {exc}", file=sys.stderr)
                    return q["question_id"], []
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                rankings = dict(ex.map(one, questions))
            rank_path.write_text(json.dumps(rankings, indent=1), encoding="utf8")

        summary = score(rankings, questions, qrels, ks)
        print_table(name, summary, ks)
        (RESULTS / f"retrieval-{name}.json").write_text(
            json.dumps(summary, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
