#!/usr/bin/env python3
"""Post-re-derive cliquedb baseline (0.49.1), with the rank histogram the
2026-09-03 run was missing and query constructions that de-verbatim the probes.

The 09-03 harness sampled passages VERBATIM out of the target document, so 80%
of indexed docs came back at rank 1 and hit@20 pinned at 0.5367 across every
arm — a saturated metric with one document in 300 between rank 21-100. Three
constructions per document break the verbatim identity three different ways:

  lines        one random non-lead body line, first 10 words (the 09-03 rule,
               kept as the comparability anchor)
  lines-nostop the same line with the shared prompt stoplist applied — what
               scan-prompt actually does to a user prompt before ranking
  merge        every OTHER non-lead body line joined, duplicate tokens
               stripped in order, first 10 surviving words — content drawn
               from across the whole document, so no single indexed line
               contains the query

Every arm prints hit@k AND the full rank histogram; a degenerate histogram
means fix the sampling, not run more arms.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
LEAD_SKIP = 6          # never sample what the `lead` signal already boosts
QUERY_WORDS = 10


def _body_lines(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    body = [l for l in raw
            if l.strip()
            and not l.startswith(("#", "rel:", "---", "```", "|", ">"))
            and not l.strip().startswith(("-", "*", "="))]
    return body[LEAD_SKIP:] if len(body) > LEAD_SKIP else []


def _q_lines(pool: list[str], rnd: random.Random, stop: "set[str] | None") -> "str | None":
    pool = pool[:]
    rnd.shuffle(pool)
    for line in pool[:20]:
        words = _WORD.findall(line)
        if stop is not None:
            words = [w for w in words if w.lower() not in stop]
        if len(words) >= 5:
            return " ".join(words[:QUERY_WORDS])
    return None


def _q_merge(pool: list[str]) -> "str | None":
    """Every other line, duplicates stripped in order: a query no single
    indexed line contains. Deterministic per document — no rnd on purpose,
    so the arm differs from `lines` only by construction, not by draw."""
    merged: list[str] = []
    seen: set[str] = set()
    for line in pool[::2]:
        for w in _WORD.findall(line):
            k = w.lower()
            if k in seen:
                continue
            seen.add(k)
            merged.append(w)
    return " ".join(merged[:QUERY_WORDS]) if len(merged) >= 5 else None


def _histogram(ranks: list[int], limit: int) -> str:
    c = Counter()
    for r in ranks:
        if r == 1:
            c["1"] += 1
        elif 2 <= r <= 5:
            c["2-5"] += 1
        elif 6 <= r <= 10:
            c["6-10"] += 1
        elif 11 <= r <= limit:
            c[f"11-{limit}"] += 1
        else:
            c["miss"] += 1
    return "  ".join(f"{b}:{c[b]}" for b in ("1", "2-5", "6-10", f"11-{limit}", "miss"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root",
                    default="/Users/tholley/github/atollogy/bdep/cliquedb/.refmatrix")
    ap.add_argument("--partition", default="cliquedb")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260903)
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()

    os.environ["REFMATRIX_ROOT"] = a.root
    os.environ["RMX_PARTITION"] = a.partition
    from refmatrix.scan import _PROMPT_STOPWORDS
    from refmatrix.store import Store

    s = Store(a.root, read_only=True)
    con = s._connect()
    rows = con.execute(
        "SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL "
        "AND kind IN ('doc','memory')", (s._partition_id,)).fetchall()
    by_path: dict[str, set] = {}
    for r in rows:
        by_path.setdefault(str(r[1]), set()).add(int(r[0]))
    for r in con.execute(
        "SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL",
        (s._partition_id,)).fetchall():
        p = str(r[1])
        if p in by_path:
            by_path[p].add(int(r[0]))

    rnd = random.Random(a.seed)
    paths = [p for p in by_path if Path(p).exists()]
    rnd.shuffle(paths)

    arms = {"lines": [], "lines-nostop": [], "merge": []}
    asked = 0
    for p in paths:
        if asked >= a.n:
            break
        pool = _body_lines(Path(p))
        if not pool:
            continue
        # One rnd draw shared by the two line arms so they differ ONLY by the
        # stoplist, and merge is deterministic — a paired design per document.
        draw = random.Random(rnd.random())
        qs = {
            "lines": _q_lines(pool, random.Random(draw.random()), None),
            "lines-nostop": None,
            "merge": _q_merge(pool),
        }
        if qs["lines"] is not None:
            words = [w for w in qs["lines"].split()
                     if w.lower() not in _PROMPT_STOPWORDS]
            qs["lines-nostop"] = " ".join(words) if len(words) >= 3 else None
        if all(v is None for v in qs.values()):
            continue
        asked += 1
        gold = by_path[p]
        for arm, q in qs.items():
            if q is None:
                continue
            hits = s.content_rank(q.split(), limit=a.limit)
            rank = next((i + 1 for i, (eid, _sc) in enumerate(hits)
                         if eid in gold), 0)
            arms[arm].append(rank)

    for arm, ranks in arms.items():
        n = max(len(ranks), 1)
        mrr = sum(1.0 / r for r in ranks if r > 0) / n

        def at(k: int) -> float:
            return sum(1 for r in ranks if 0 < r <= k) / n

        print(f"{arm:13s} n={len(ranks)}  MRR={mrr:.4f}  hit@1={at(1):.4f}  "
              f"hit@5={at(5):.4f}  hit@10={at(10):.4f}  hit@20={at(20):.4f}")
        print(f"{'':13s} hist  {_histogram(ranks, a.limit)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
