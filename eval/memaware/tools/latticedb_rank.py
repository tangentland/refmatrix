#!/usr/bin/env python3
"""Rank the corpus with LatticeDB's BM25 index — a fourth Layer-A condition.

LatticeDB (github.com/jeffhajewski/latticedb) is an embedded single-file graph
engine that puts BM25 full-text, HNSW vectors and graph traversal behind one
transaction path. refmatrix currently spreads those across DuckDB + Lance +
roaring bitmaps + a hand-rolled facts.log, and most of its operational scars
live on those seams — so the question worth answering is whether the
consolidated engine actually retrieves better on the same corpus, rather than
whether its README's benchmark table is flattering.

**Scope: BM25 only.** That is the like-for-like comparison against the
`bm25` condition (upstream's own JS implementation) and against the lexical
half of `rmx context`. The vector path is deliberately NOT exercised here:
LatticeDB ships `hash_embed`, which is a hashing trick and not a semantic
embedding, so a vector run against rmx's bge-small numbers would measure the
embedder and report it as the index. The honest version of that experiment is
to load the SAME bge-small vectors into both and compare recall and latency;
see README for why it is a separate piece of work.

Timings are recorded because speed is what the project claims. Build time and
per-query latency land in the sidecar JSON next to the rankings.

    python3 tools/latticedb_rank.py --questions <subset.json> --k 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from paths import CORPUS, DATA, SUBSETS, UPSTREAM   # noqa: E402

DB_DIR = DATA / "latticedb"


def build(db_path: Path, *, rebuild: bool) -> tuple[dict[int, str], float]:
    """One node per session, FTS-indexed on the full transcript.

    Returns (node_id -> session_id, seconds). Session granularity matches every
    other condition; see prepare.py for why day-level chunking is a different
    (and much worse) experiment.
    """
    from latticedb import Database

    sidecar = db_path.with_suffix(".nodes.json")
    if db_path.exists() and not rebuild:
        if sidecar.exists():
            print(f"  ~ reusing {db_path}")
            return {int(k): v for k, v in
                    json.loads(sidecar.read_text()).items()}, 0.0
        print(f"  ! {db_path} exists but {sidecar.name} is missing — rebuilding")
        rebuild = True
    if db_path.exists():
        db_path.unlink()
        sidecar.unlink(missing_ok=True)

    docs = sorted(CORPUS.rglob("*.md"))
    if not docs:
        sys.exit("  ! corpus missing — run prepare.py first")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    node_to_sid: dict[int, str] = {}
    t0 = time.time()
    with Database(str(db_path), create=True) as db:
        with db.write() as txn:
            for p in docs:
                sid = p.stem
                text = p.read_text(encoding="utf8")
                node = txn.create_node(labels=["Session"],
                                       properties={"session_id": sid})
                txn.fts_index(node.id, text)
                node_to_sid[node.id] = sid
            txn.commit()
    dt = time.time() - t0
    sidecar.write_text(json.dumps({str(k): v for k, v in node_to_sid.items()},
                                  indent=1), encoding="utf8")
    print(f"  + indexed {len(node_to_sid)} sessions in {dt:.1f}s "
          f"({db_path.stat().st_size / 1e6:.0f} MB)")
    return node_to_sid, dt


def _terms(question: str) -> list[str]:
    """Content words only, via refmatrix's shared stoplist.

    LatticeDB's `@@` / fts_search is **conjunctive by design** — "The search
    query is a space-separated list of terms. All terms must match (implicit
    AND)" (book/src/cypher/full-text-search.md). Handing it a 20-word natural
    language question therefore matches nothing at all: passing the raw
    question returned a mean of 0.12 documents across 90 questions.

    That is not a defect, it is a contract, and honouring it is what a real
    integration would do. Using the SAME stoplist our own conditions use keeps
    the comparison about the engine rather than about who wrote a better
    tokenizer.
    """
    from refmatrix.scan import _PROMPT_STOPWORDS
    out, seen = [], set()
    for tok in re.split(r"[^A-Za-z0-9_]+", question):
        t = tok.strip().lower()
        if len(t) < 2 or t in seen or t in _PROMPT_STOPWORDS:
            continue
        seen.add(t)
        out.append(t)
    return out


def rank(db_path: Path, node_to_sid: dict[int, str], questions: list[dict],
         k: int) -> tuple[dict[str, list[str]], list[float]]:
    from latticedb import Database

    out: dict[str, list[str]] = {}
    latencies: list[float] = []
    with Database(str(db_path), read_only=True) as db:

        def search(query: str):
            try:
                return db.fts_search(query, limit=k)
            except Exception as exc:
                # Loud per question: an engine that rejects a query SHAPE is a
                # finding, not something to average into a zero.
                print(f"  ! fts_search({query[:40]!r}): {exc}", file=sys.stderr)
                return []

        for q in questions:
            terms = _terms(q["question"])
            t0 = time.perf_counter()
            # Back off from the full conjunction until something matches, then
            # top up from single-term results. Deliberately generous: without
            # this, AND over a whole question is empty and the condition would
            # score zero for a reason that says nothing about retrieval.
            hits, probe = [], list(terms)
            while probe and not hits:
                hits = search(" ".join(probe))
                probe = probe[:-1]
            seen = {h.node_id for h in hits}
            for t in terms:
                if len(hits) >= k:
                    break
                for h in search(t):
                    if h.node_id not in seen:
                        seen.add(h.node_id)
                        hits.append(h)
                        if len(hits) >= k:
                            break
            latencies.append((time.perf_counter() - t0) * 1000)
            out[q["question_id"]] = [
                node_to_sid[h.node_id] for h in hits[:k]
                if h.node_id in node_to_sid
            ]
    return out, latencies


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", type=Path,
                    default=SUBSETS / "stratified-30.json")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--name", default="latticedb",
                    help="condition name (results/rank-<name>.json)")
    args = ap.parse_args()

    db_path = DB_DIR / "memaware.db"
    node_to_sid, build_s = build(db_path, rebuild=args.rebuild)
    questions = json.loads(args.questions.read_text(encoding="utf8"))
    rankings, latencies = rank(db_path, node_to_sid, questions, args.k)

    results = DATA / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / f"rank-{args.name}.json").write_text(
        json.dumps(rankings, indent=1), encoding="utf8")

    latencies.sort()
    stats = {
        "engine": "latticedb",
        "mode": "fts/bm25",
        "sessions": len(node_to_sid),
        "index_seconds": round(build_s, 2),
        "db_bytes": db_path.stat().st_size,
        "queries": len(latencies),
        "query_ms_median": round(latencies[len(latencies) // 2], 3) if latencies else None,
        "query_ms_p95": round(latencies[int(len(latencies) * 0.95)], 3) if latencies else None,
    }
    (results / f"timing-{args.name}.json").write_text(
        json.dumps(stats, indent=1), encoding="utf8")
    print(f"  + {len(rankings)} rankings -> results/rank-{args.name}.json")
    print(f"  + {json.dumps(stats)}")


if __name__ == "__main__":
    main()
