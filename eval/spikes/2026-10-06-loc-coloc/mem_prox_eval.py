#!/usr/bin/env python3
"""Throwaway spike: WEIGHTED proximity re-rank on MemAware Layer-A.

Base = production `content_rank` over a COPY of the MemAware replica, collapsed
to session ids (pool 50). Re-rank each candidate session by

    prox = max over pairs (a,b) of distinct query terms of
           sqrt(w(a)·w(b)) · f(d(a,b))          w(t) = idf(t) · burstiness(t)

with d the minimum distance between occurrences (tokens or sentences), read
from the session's corpus file. Score = base_norm + λ·prox_norm.
Tune on stratified-30, confirm on holdout-90 (disjoint).
"""
from __future__ import annotations

import collections
import json
import math
import os
import re
import sys
from pathlib import Path

REPO = Path("/Users/tholley/claude_tools/refmatrix")
sys.path.insert(0, str(REPO / "src"))
ROOT = sys.argv[1]
DATA = Path("/Volumes/littlebig/memaware")
os.environ["REFMATRIX_ROOT"] = ROOT
os.environ["RMX_PARTITION"] = "memaware"

from refmatrix.store import Store  # noqa: E402
from refmatrix.terms import content_terms, STOPWORDS  # noqa: E402

POOL = 50
TOK = re.compile(r"[a-z][a-z0-9_']*")
SENT = re.compile(r"(?<=[.!?])\s+|\n+")

s = Store(ROOT, read_only=True)
con = s._connect()
pid = s._partition_id
ent_sid: dict[int, str] = {}
for eid, name, path in con.execute(
        "SELECT id, name, path FROM entities WHERE partition_id=?", (pid,)).fetchall():
    v = str(path) if path else str(name)
    sid = Path(v).stem if ("/" in v or v.endswith(".md")) else v
    ent_sid[int(eid)] = sid.split("#", 1)[0]

# Corpus statistics straight from the files: df, burstiness (mean tf where present).
files = {p.stem: p for p in (DATA / "corpus").rglob("*.md")}
doc_toks: dict[str, list[tuple[str, int]]] = {}
df = collections.Counter()
tf_sum = collections.Counter()
for sid, p in files.items():
    txt = p.read_text(encoding="utf-8", errors="ignore").lower()
    toks = []
    for si, sent in enumerate(SENT.split(txt)):
        toks.extend((m.group(0), si) for m in TOK.finditer(sent))
    doc_toks[sid] = toks
    c = collections.Counter(w for w, _ in toks)
    for w, n in c.items():
        df[w] += 1
        tf_sum[w] += n
N = len(files)


def weight(t: str) -> float:
    if not df[t]:
        return 0.0
    return math.log(N / df[t]) * (tf_sum[t] / df[t])


def prox(sid: str, qw: dict[str, float], mode: str, sigma: float) -> float:
    toks = doc_toks.get(sid) or []
    last: dict[str, tuple[int, int]] = {}
    best = 0.0
    for i, (w, si) in enumerate(toks):
        if w not in qw:
            continue
        for o, (pi, ps) in last.items():
            if o == w:
                continue
            d = (i - pi) if mode == "tok" else (si - ps)
            f = math.exp(-d / sigma) if mode == "tok" else 1.0 / (1.0 + d)
            best = max(best, math.sqrt(qw[w] * qw[o]) * f)
        last[w] = (i, si)
    return best


qrels = json.loads((DATA / "qrels.json").read_text())
ARMS = [("base", None, 0, 0)]
for lam in (0.3, 1.0):
    ARMS += [(f"tok10-l{lam}", "tok", 10.0, lam), (f"tok3-l{lam}", "tok", 3.0, lam),
             (f"sent-l{lam}", "sent", 0, lam)]


def run(subset: str) -> None:
    qs = json.loads((DATA / "subsets" / subset).read_text())
    ranks = {a[0]: [] for a in ARMS}
    for q in qs:
        rel = {Path(p).stem for p in qrels.get(q["question_id"], [])}
        terms = content_terms(q["question"])
        hits = s.content_rank(terms, limit=POOL * 4)
        order, seen, score = [], set(), {}
        for eid, sc in hits:
            sid = ent_sid.get(int(eid))
            if sid and sid not in seen:
                seen.add(sid)
                order.append(sid)
                score[sid] = sc
            if len(order) >= POOL:
                break
        qwords = {w.lower() for w in terms if w.lower() not in STOPWORDS}
        qw = {w: weight(w) for w in qwords if weight(w) > 0}
        top = max(score.values()) if score else 1.0
        for name, mode, sigma, lam in ARMS:
            if mode is None:
                lst = order
            else:
                px = {sid: prox(sid, qw, mode, sigma) for sid in order}
                pmax = max(px.values()) or 1.0
                lst = sorted(order, key=lambda sid: -(score[sid] / top + lam * px[sid] / pmax))
            ranks[name].append(next((i + 1 for i, sid in enumerate(lst[:20]) if sid in rel), 0))
    print(f"\n== {subset} (n={len(qs)})")
    base = ranks["base"]
    for name, rs in ranks.items():
        n = len(rs)
        mrr = sum(1 / r for r in rs if r) / n
        at = lambda k: sum(1 for r in rs if 0 < r <= k) / n  # noqa: E731
        won = sum(1 for x, y in zip(base, rs) if y and (not x or y < x))
        lost = sum(1 for x, y in zip(base, rs) if x and (not y or y > x))
        print(f"  {name:11s} MRR@20={mrr:.4f} hit@1={at(1):.3f} hit@5={at(5):.3f} "
              f"hit@10={at(10):.3f} hit@20={at(20):.3f}  vs base +{won}/-{lost}")


print(f"sessions={N} entities={len(ent_sid)}")
run("stratified-30.json")
run("holdout-90.json")
