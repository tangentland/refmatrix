#!/usr/bin/env python3
"""Known-item retrieval over a REAL curated store, to test the structural
signals MemAware cannot exercise.

MemAware is synthetic prose with no curation in it: 0 `rel:` edges, nothing
protected, 99.6% of nodes at heading level 1. Five of the eight discarded
signals are therefore invisible to it — not disproven, untestable. cliquedb is
the opposite: 34.8k typed edges, four populated heading levels, real tags.

It has no qrels, and `query.log` records real prompts but never which document
was right. So labels come from construction instead: sample a passage OUT of a
document, use it as the query, and that document is the answer.

Two sampling rules keep the task from grading the signals under test:
  * passages are drawn from NON-LEAD lines, so the `lead` boost gets no help
  * passages are drawn from the BODY, never the heading, so `titles` gets none

Scored on the rank of the best entity sharing the source file's path — a file
becomes a doc entity AND one concept per anchor, and any of them is a correct
retrieval of that document.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
LEAD_SKIP = 6          # lines to skip so the `lead` signal is never sampled
QUERY_WORDS = 10


def _passages(path: Path, rnd: random.Random) -> "str | None":
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None
    body = [l for l in raw
            if l.strip()
            and not l.startswith(("#", "rel:", "---", "```", "|", ">"))
            and not l.strip().startswith(("-", "*", "="))]
    if len(body) <= LEAD_SKIP:
        return None
    pool = body[LEAD_SKIP:]
    rnd.shuffle(pool)
    for line in pool[:20]:
        words = _WORD.findall(line)
        if len(words) >= 5:
            return " ".join(words[:QUERY_WORDS])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Volumes/littlebig/cq/.refmatrix")
    ap.add_argument("--partition", default="cliquedb")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260903)
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()

    os.environ["REFMATRIX_ROOT"] = a.root
    os.environ["RMX_PARTITION"] = a.partition
    from refmatrix.store import Store

    s = Store(a.root)
    con = s._connect()
    rows = con.execute(
        "SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL "
        "AND kind IN ('doc','memory')", (s._partition_id,)).fetchall()
    by_path: dict[str, set] = {}
    for r in rows:
        by_path.setdefault(str(r[1]), set()).add(int(r[0]))
    # every entity sharing the path counts as a hit, anchors included
    for r in con.execute(
        "SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL",
        (s._partition_id,)).fetchall():
        p = str(r[1])
        if p in by_path:
            by_path[p].add(int(r[0]))

    rnd = random.Random(a.seed)
    paths = [p for p in by_path if Path(p).exists()]
    rnd.shuffle(paths)

    ranks: list[int] = []
    asked = 0
    for p in paths:
        if asked >= a.n:
            break
        q = _passages(Path(p), rnd)
        if not q:
            continue
        asked += 1
        hits = s.content_rank(q.split(), limit=a.limit)
        gold = by_path[p]
        rank = next((i + 1 for i, (eid, _sc) in enumerate(hits) if eid in gold), 0)
        ranks.append(rank)

    def at(k: int) -> float:
        return sum(1 for r in ranks if 0 < r <= k) / max(len(ranks), 1)

    mrr = sum(1.0 / r for r in ranks if r > 0) / max(len(ranks), 1)
    print(f"  n={len(ranks)}  MRR={mrr:.4f}  hit@1={at(1):.4f} "
          f"hit@5={at(5):.4f}  hit@10={at(10):.4f}  hit@20={at(20):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
