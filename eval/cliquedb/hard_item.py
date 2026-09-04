#!/usr/bin/env python3
"""Known-item retrieval with the EASY part removed.

The first harness sampled a passage verbatim out of the target document, so the
query was literally a substring of the answer: 80% of indexed documents came
back at rank 1, 178 of 181 inside the top 20, and exactly ONE document in 300
sat between rank 21 and 100. hit@20 was therefore pinned at the indexed
fraction and could not move no matter what the ranker did — 0.5367 recurred
across every arm of every sweep because it was a constant, not a result.

Two changes make the task discriminating:

  * targets are restricted to documents that HAVE body terms. A zero-term
    document is not a known-item target, it is an ingest gap, and including
    them measured ingest coverage while looking like a retrieval score.
  * `--drop-rare N` removes the N highest-idf terms from each query. Those are
    the terms that make the verbatim task trivial; without them the query is
    generic vocabulary that many documents share, which is exactly the regime
    where a structural prior has something to contribute.

Always prints the rank histogram. A metric with no mass between the cutoffs
has no headroom, and its stability is not evidence of anything.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
LEAD_SKIP = 6


def _passages(path: Path, rnd: random.Random, k: int) -> list[list[str]]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    body = [l for l in raw
            if l.strip() and not l.startswith(("#", "rel:", "---", "```", "|", ">"))
            and not l.strip().startswith(("-", "*", "="))]
    if len(body) <= LEAD_SKIP:
        return []
    pool = body[LEAD_SKIP:]
    rnd.shuffle(pool)
    out = []
    for line in pool:
        w = _WORD.findall(line)
        if len(w) >= 8:
            out.append(w[:14])
        if len(out) >= k:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Volumes/littlebig/cq/.refmatrix")
    ap.add_argument("--partition", default="cliquedb")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--per-file", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260904)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--drop-rare", type=int, default=3,
                    help="strip the N highest-idf terms from every query")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()

    os.environ["REFMATRIX_ROOT"] = a.root
    os.environ["RMX_PARTITION"] = a.partition
    from refmatrix.store import Store

    s = Store(a.root)
    con = s._connect()
    mlid = s.get_linkage_id("mentions")
    by_path: dict[str, set] = {}
    for r in con.execute(
        "SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL "
        "AND kind IN ('doc','memory')", (s._partition_id,)).fetchall():
        by_path.setdefault(str(r[1]), set()).add(int(r[0]))
    for r in con.execute(
        "SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL",
        (s._partition_id,)).fetchall():
        p = str(r[1])
        if p in by_path:
            by_path[p].add(int(r[0]))

    # df over concept NAMES, to find each query's rarest (highest-idf) terms
    df = {}
    for r in con.execute(
        "SELECT e.name, COUNT(*) FROM entity_links el "
        "JOIN entities e ON e.id = el.concept_id "
        "WHERE el.linkage_id=? GROUP BY e.name", (mlid,)).fetchall():
        df[str(r[0]).lower()] = int(r[1])
    N = max(df.values()) if df else 1

    def indexed(ids) -> bool:
        ph = ",".join("?" * len(ids))
        return con.execute(
            f"SELECT COUNT(*) FROM entity_links WHERE linkage_id=? "
            f"AND entity_id IN ({ph})", (mlid, *ids)).fetchone()[0] > 0

    rnd = random.Random(a.seed)
    paths = [p for p in by_path if Path(p).exists()]
    if a.only:
        paths = [p for p in paths if a.only in p]
    rnd.shuffle(paths)

    ranks, asked, skipped = [], 0, 0
    for p in paths:
        if asked >= a.n:
            break
        if not indexed(sorted(by_path[p])):     # not a valid target
            skipped += 1
            continue
        for words in _passages(Path(p), rnd, a.per_file):
            if asked >= a.n:
                break
            ws = [w.lower() for w in words]
            if a.drop_rare > 0:
                ws.sort(key=lambda w: df.get(w, N))      # rarest first
                ws = ws[a.drop_rare:]                     # strip them
            if len(ws) < 4:
                continue
            asked += 1
            hits = s.content_rank(ws, limit=a.limit)
            ranks.append(next((i + 1 for i, (e, _) in enumerate(hits)
                               if e in by_path[p]), 0))

    def at(k): return sum(1 for r in ranks if 0 < r <= k) / max(len(ranks), 1)
    mrr = sum(1.0 / r for r in ranks if r > 0) / max(len(ranks), 1)
    h = Counter("absent" if r == 0 else "1" if r == 1 else "2-5" if r <= 5
                else "6-10" if r <= 10 else "11-20" for r in ranks)
    print(f"  n={len(ranks)} (skipped {skipped} unindexed targets)  drop_rare={a.drop_rare}")
    print(f"  MRR={mrr:.4f} hit@1={at(1):.4f} hit@5={at(5):.4f} "
          f"hit@10={at(10):.4f} hit@20={at(20):.4f}")
    print("  ranks: " + "  ".join(f"{k}:{h.get(k,0)}"
          for k in ("1", "2-5", "6-10", "11-20", "absent")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
