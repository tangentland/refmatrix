#!/usr/bin/env python3
"""Cross-doc coref reach A/B on an isolated corpus.

Two measurements, both content_rank with RMX_BOOST_COREF off vs on:

  reach  — for each doc B that cross-doc resolution bound to an antecedent X
           (a `refers-to` edge + a conf=0.2 coref resolution), query = X and
           gold = B. B does NOT organically mention X (that is why the pronoun
           needed resolving), so boost-off cannot reach it; boost-on surfaces
           it through the coref postings. This is the reach the whole layer
           exists to buy -- a query for a named entity reaching a document
           that only refers to it by pronoun.

  guard  — standard known-item (query sampled from a doc's own body, gold =
           that doc) over ALL docs. Confirms the coref postings do not damage
           ordinary retrieval by injecting distractors.
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
LEAD_SKIP = 6
QW = 10


def _body_q(content: str, rnd) -> "str | None":
    lines = [l for l in content.splitlines()
             if l.strip() and not l.startswith(("#", "rel:", "---", "```", "|", ">"))
             and not l.strip().startswith(("-", "*", "="))]
    if len(lines) <= LEAD_SKIP:
        return None
    pool = lines[LEAD_SKIP:]
    rnd.shuffle(pool)
    for line in pool[:20]:
        w = _WORD.findall(line)
        if len(w) >= 5:
            return " ".join(w[:QW])
    return None


def _hit(hits, gold, k):
    return next((i + 1 for i, (e, _s) in enumerate(hits) if e == gold), 0) <= k \
        and next((i + 1 for i, (e, _s) in enumerate(hits) if e == gold), 0) > 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--partition", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260905)
    a = ap.parse_args()
    os.environ["REFMATRIX_ROOT"] = a.root
    os.environ["RMX_PARTITION"] = a.partition
    from refmatrix.store import Store
    s = Store(a.root, read_only=True)
    con = s._connect()

    # cross-doc linked docs: refers-to source entities + their antecedent term
    try:
        rlid = s.get_linkage_id("refers-to")
    except Exception:
        print("no refers-to linkage — cross-doc link never ran")
        return 1
    linked = [int(r[0]) for r in con.execute(
        "SELECT DISTINCT entity_id FROM entity_links WHERE linkage_id=?",
        (rlid,)).fetchall()]
    # antecedent term per linked doc = the coref concept linked to it
    clid = s.get_linkage_id("coref")
    ante_of: dict[int, str] = {}
    for eid in linked:
        row = con.execute(
            "SELECT e.name FROM entity_links el JOIN entities e "
            "ON e.id = el.concept_id WHERE el.linkage_id=? AND el.entity_id=? "
            "LIMIT 1", (clid, eid)).fetchone()
        if row:
            ante_of[eid] = str(row[0])
    print(f"cross-doc linked docs: {len(linked)}  with antecedent term: {len(ante_of)}")

    def reach(boost: str) -> "tuple[int,int]":
        os.environ["RMX_BOOST_COREF"] = boost
        hit = 0
        for eid, term in ante_of.items():
            hits = s.content_rank(term.split(), limit=a.limit)
            if any(e == eid for e, _ in hits):
                hit += 1
        return hit, len(ante_of)

    off_h, n = reach("0")
    on_h, _ = reach("1.0")
    print(f"REACH  gold-in-top{a.limit}:  boost=0 {off_h}/{n}"
          f"   boost=1 {on_h}/{n}   (+{on_h-off_h})")

    # guard: standard known-item over all docs
    rows = con.execute(
        "SELECT mc.entity_id, mc.content FROM memory_content mc "
        "JOIN entities e ON e.id=mc.entity_id WHERE e.partition_id=?",
        (s._partition_id,)).fetchall()
    rnd = random.Random(a.seed)
    samples = []
    for eid, content in rows:
        q = _body_q(content or "", rnd)
        if q:
            samples.append((q, int(eid)))
    rnd.shuffle(samples)
    samples = samples[:300]

    def guard(boost: str):
        os.environ["RMX_BOOST_COREF"] = boost
        ranks = []
        for q, gold in samples:
            hits = s.content_rank(q.split(), limit=a.limit)
            ranks.append(next((i + 1 for i, (e, _s) in enumerate(hits) if e == gold), 0))
        mrr = sum(1.0 / r for r in ranks if r > 0) / max(len(ranks), 1)
        h20 = sum(1 for r in ranks if 0 < r <= a.limit) / max(len(ranks), 1)
        return mrr, h20

    o_mrr, o_h = guard("0")
    n_mrr, n_h = guard("1.0")
    print(f"GUARD  n={len(samples)}  MRR {o_mrr:.4f}->{n_mrr:.4f}  "
          f"hit@{a.limit} {o_h:.4f}->{n_h:.4f}")
    os.environ.pop("RMX_BOOST_COREF", None)
    s.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
