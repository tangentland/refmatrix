#!/usr/bin/env python3
"""Throwaway spike: re-rank content_rank's top-20 by query-term PROXIMITY
(MinDist, Tao & Zhai 2007) read straight from the candidate's text. No new
storage: term positions come from re-tokenizing tldr (section body) or file.

Arms:
  base           content_rank order
  tz-l{λ}        base_norm + λ·log(α + exp(−MinDist_tokens))     (Tao-Zhai form)
  sent-l{λ}      base_norm + λ·1/(1+MinDist_sentences)
  prox-only      sort by MinDist_tokens, base as tie-break
Runs against a COPY of the cliquedb read replica.
"""
from __future__ import annotations

import math
import os
import random
import re
import sys
from pathlib import Path

REPO = Path("/Users/tholley/claude_tools/refmatrix")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "eval" / "cliquedb"))
ROOT = sys.argv[1]
os.environ["REFMATRIX_ROOT"] = ROOT
os.environ["RMX_PARTITION"] = "cliquedb"

import baseline_rederive as H  # noqa: E402
from refmatrix.scan import _PROMPT_STOPWORDS  # noqa: E402
from refmatrix.store import Store  # noqa: E402

LIMIT = 20
ALPHA = 0.3
TOK = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
SENT = re.compile(r"(?<=[.!?])\s+|\n\s*\n|\n(?=\s*[-*#|])")

s = Store(ROOT, read_only=True)
con = s._connect()
pid = s._partition_id
_text: dict[int, list[tuple[str, int]]] = {}
_file: dict[str, str] = {}


def tokens(eid: int) -> list[tuple[str, int]]:
    """[(lower_token, sentence_index)] for an entity's own text."""
    if eid in _text:
        return _text[eid]
    r = con.execute("SELECT path, tldr FROM entities WHERE id=?", (eid,)).fetchone()
    txt = ""
    if r and r[1]:
        txt = r[1]
    elif r and r[0]:
        p = str(r[0])
        if p not in _file:
            try:
                _file[p] = Path(p).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                _file[p] = ""
        txt = _file[p]
    out = []
    for si, sent in enumerate(SENT.split(txt)):
        for m in TOK.finditer(sent):
            out.append((m.group(0).lower(), si))
    _text[eid] = out
    return out


def min_dists(eid: int, qterms: set[str]) -> tuple[float, float]:
    """(token MinDist, sentence MinDist) over occurrences of two DIFFERENT
    query terms. inf when fewer than two distinct terms occur."""
    toks = tokens(eid)
    last_pos: dict[str, int] = {}
    last_sent: dict[str, int] = {}
    best_t = best_s = math.inf
    for i, (w, si) in enumerate(toks):
        if w not in qterms:
            continue
        for other, pos in last_pos.items():
            if other != w:
                best_t = min(best_t, i - pos)
                best_s = min(best_s, si - last_sent[other])
        last_pos[w] = i
        last_sent[w] = si
    return best_t, best_s


rows = con.execute("SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL",
                   (pid,)).fetchall()
by_path: dict[str, set] = {}
for r in con.execute("SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL "
                     "AND kind IN ('doc','memory')", (pid,)).fetchall():
    by_path.setdefault(str(r[1]), set()).add(int(r[0]))
for r in rows:
    if str(r[1]) in by_path:
        by_path[str(r[1])].add(int(r[0]))

LAMBDAS = (0.3, 1.0)
arm_names = (["base"] + [f"tz-l{l}" for l in LAMBDAS] + [f"sent-l{l}" for l in LAMBDAS]
             + ["prox-only"])
res = {c: {a: [] for a in arm_names} for c in ("lines", "merge")}
rnd = random.Random(20260903)
paths = [p for p in by_path if Path(p).exists()]
rnd.shuffle(paths)
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
        base = s.content_rank(q.split(), limit=LIMIT)
        if not base:
            for a in arm_names:
                res[cons][a].append(0)
            continue
        qterms = {w.lower() for w in q.split() if w.lower() not in _PROMPT_STOPWORDS}
        top = max(sc for _, sc in base) or 1.0
        feats = []
        for rank, (eid, sc) in enumerate(base):
            dt, ds = min_dists(eid, qterms)
            feats.append((eid, sc / top, dt, ds, rank))
        lists = {"base": [f[0] for f in feats]}
        for lam in LAMBDAS:
            lists[f"tz-l{lam}"] = [f[0] for f in sorted(
                feats, key=lambda f: -(f[1] + lam * math.log(ALPHA + math.exp(-f[2]))))]
            lists[f"sent-l{lam}"] = [f[0] for f in sorted(
                feats, key=lambda f: -(f[1] + lam * (1.0 / (1.0 + f[3]))))]
        lists["prox-only"] = [f[0] for f in sorted(feats, key=lambda f: (f[2], f[4]))]
        for a, lst in lists.items():
            res[cons][a].append(next((i + 1 for i, e in enumerate(lst) if e in gold), 0))

for cons, arms in res.items():
    print(f"\n== {cons}")
    base = arms["base"]
    for a, ranks in arms.items():
        n = max(len(ranks), 1)
        mrr = sum(1 / r for r in ranks if r) / n
        at = lambda k: sum(1 for r in ranks if 0 < r <= k) / n  # noqa: E731
        won = sum(1 for x, y in zip(base, ranks) if y and (not x or y < x))
        lost = sum(1 for x, y in zip(base, ranks) if x and (not y or y > x))
        print(f"  {a:9s} n={len(ranks)} MRR={mrr:.4f} hit@1={at(1):.4f} hit@5={at(5):.4f} "
              f"hit@20={at(20):.4f}  vs base +{won}/-{lost}")
        print(f"  {'':9s} hist {H._histogram(ranks, LIMIT)}")
