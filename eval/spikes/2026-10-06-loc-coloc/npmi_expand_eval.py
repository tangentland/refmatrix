#!/usr/bin/env python3
"""Throwaway spike: does NPMI-admitted query expansion (k-of-N support) help
cliquedb known-item retrieval, especially the `merge` construction?

Runs against a COPY of the cliquedb read replica (never the live store).
Arms per construction:
  base        content_rank(q)
  rrf-bN      RRF(base, content_rank(top-N NPMI-admitted terms))
  cat-bN      content_rank(q + top-N admitted terms)
"""
from __future__ import annotations

import collections
import math
import os
import random
import sys
from pathlib import Path

REPO = Path("/Users/tholley/claude_tools/refmatrix")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "eval" / "cliquedb"))
ROOT = sys.argv[1]
os.environ["REFMATRIX_ROOT"] = ROOT
os.environ["RMX_PARTITION"] = "cliquedb"

import baseline_rederive as H  # noqa: E402
from pyroaring import BitMap  # noqa: E402
from refmatrix.scan import _PROMPT_STOPWORDS  # noqa: E402
from refmatrix.store import Store  # noqa: E402

LIMIT = 20
BUDGETS = (5, 10)
K_SUPPORT = 2
MIN_CO = 3

s = Store(ROOT, read_only=True)
con = s._connect()
pid = s._partition_id
mlid = s.get_linkage_id("mentions")
post: dict[int, BitMap] = collections.defaultdict(BitMap)
for e, t in con.execute(
        "SELECT l.entity_id, l.concept_id FROM entity_links l JOIN entities u ON u.id=l.entity_id "
        "WHERE l.linkage_id=? AND u.partition_id=?", (mlid, pid)).fetchall():
    post[int(t)].add(int(e))
names = dict(con.execute("SELECT id, name FROM entities WHERE partition_id=? AND kind='concept'",
                         (pid,)).fetchall())
units = BitMap()
for b in post.values():
    units |= b
N = len(units)
df = {t: len(b) for t, b in post.items()}
by_unit: dict[int, list[int]] = collections.defaultdict(list)
for t, b in post.items():
    if 3 <= df[t] <= 0.05 * N:          # hub cull + hapax cull for candidates
        for u in b:
            by_unit[u].append(t)
print(f"units={N} terms={len(post)}", flush=True)


def expand(q: str, budget: int) -> list[str]:
    words = [w for w in q.split() if w.lower() not in _PROMPT_STOPWORDS]
    resolved = s.resolve_concept_ids_many(words)
    seed_sets = []
    for w in words:
        bm = BitMap()
        for cid in resolved.get(w) or []:
            if cid in post:
                bm |= post[cid]
        if bm:
            seed_sets.append((w, bm))
    if len(seed_sets) < K_SUPPORT:
        return []
    cnt = collections.Counter()
    for _, bm in seed_sets:
        for u in bm:
            cnt[u] += 1
    bs = [u for u, v in cnt.items() if v >= K_SUPPORT]
    if not bs:
        return []
    nbs = len(bs)
    co = collections.Counter()
    for u in bs:
        co.update(by_unit[u])
    seed_names = {w.lower() for w, _ in seed_sets}
    scored = []
    for t, c in co.items():
        n = names.get(t)
        if not n or c < MIN_CO or n.lower() in seed_names or n.lower() in _PROMPT_STOPWORDS:
            continue
        if n.startswith(("phrase/",)) or any(ch.isdigit() for ch in n):
            continue
        p = c / N
        if p >= 1.0:
            continue
        npmi = math.log(c * N / (df[t] * nbs)) / (-math.log(p))
        scored.append((npmi, n))
    scored.sort(reverse=True)
    out, seen = [], set()
    for _, n in scored:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
        if len(out) >= budget:
            break
    return out


def rrf(*lists, k=60):
    sc = collections.Counter()
    for lst in lists:
        for i, (eid, _) in enumerate(lst):
            sc[eid] += 1.0 / (k + i + 1)
    return [(e, v) for e, v in sc.most_common()]


rows = con.execute("SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL "
                   "AND kind IN ('doc','memory')", (pid,)).fetchall()
by_path: dict[str, set] = {}
for r in rows:
    by_path.setdefault(str(r[1]), set()).add(int(r[0]))
for r in con.execute("SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL",
                     (pid,)).fetchall():
    if str(r[1]) in by_path:
        by_path[str(r[1])].add(int(r[0]))

rnd = random.Random(20260903)
paths = [p for p in by_path if Path(p).exists()]
rnd.shuffle(paths)
arm_names = ["base"] + [f"rrf-b{b}" for b in BUDGETS] + [f"cat-b{b}" for b in BUDGETS]
res = {c: {a: [] for a in arm_names} for c in ("lines", "merge")}
examples = []
asked = 0
for p in paths:
    if asked >= 300:
        break
    pool = H._body_lines(Path(p))
    if not pool:
        continue
    draw = random.Random(rnd.random())
    qs = {"lines": H._q_lines(pool, random.Random(draw.random()), None), "merge": H._q_merge(pool)}
    if all(v is None for v in qs.values()):
        continue
    asked += 1
    gold = by_path[p]
    for cons, q in qs.items():
        if q is None:
            continue
        base = s.content_rank(q.split(), limit=50)
        lists = {"base": base}
        for b in BUDGETS:
            ex = expand(q, b)
            exh = s.content_rank(ex, limit=50) if ex else []
            lists[f"rrf-b{b}"] = rrf(base, exh) if ex else base
            lists[f"cat-b{b}"] = s.content_rank(q.split() + ex, limit=50) if ex else base
            if cons == "merge" and b == 10 and len(examples) < 6:
                examples.append((q, ex))
        for a, lst in lists.items():
            top = lst[:LIMIT]
            res[cons][a].append(next((i + 1 for i, (e, _) in enumerate(top) if e in gold), 0))

for q, ex in examples:
    print(f"  q: {q}\n     +{ex}")
for cons, arms in res.items():
    print(f"\n== {cons}")
    base = arms["base"]
    for a, ranks in arms.items():
        n = max(len(ranks), 1)
        mrr = sum(1 / r for r in ranks if r) / n
        at = lambda k: sum(1 for r in ranks if 0 < r <= k) / n  # noqa: E731
        won = sum(1 for x, y in zip(base, ranks) if (y and (not x or y < x)))
        lost = sum(1 for x, y in zip(base, ranks) if (x and (not y or y > x)))
        print(f"  {a:9s} n={len(ranks)} MRR={mrr:.4f} hit@1={at(1):.4f} hit@5={at(5):.4f} "
              f"hit@20={at(20):.4f}  vs base +{won}/-{lost}")
        print(f"  {'':9s} hist {H._histogram(ranks, LIMIT)}")
