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
doc_toks: dict[str, list[tuple[str, int, int]]] = {}
df = collections.Counter()
tf_sum = collections.Counter()
for sid, p in files.items():
    txt = p.read_text(encoding="utf-8", errors="ignore").lower()
    toks = []
    si = 0
    for pi, para in enumerate(re.split(r"\n\s*\n", txt)):
        for sent in SENT.split(para):
            toks.extend((m.group(0), si, pi) for m in TOK.finditer(sent))
            si += 1
    doc_toks[sid] = toks
    c = collections.Counter(t[0] for t in toks)
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
    for i, (w, si, _pi) in enumerate(toks):
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




def coloc(sid: str, qw: dict[str, float], level: int) -> float:
    """Best weighted coverage of the query inside ONE unit (1=sentence, 2=paragraph):
    max over units of sum w(t) for distinct query terms present / sum w(all)."""
    tot = sum(qw.values()) or 1.0
    units: dict[int, set] = collections.defaultdict(set)
    for t in doc_toks.get(sid) or []:
        if t[0] in qw:
            units[t[level]].add(t[0])
    return max((sum(qw[w] for w in u) for u in units.values()), default=0.0) / tot


def sentsum(eid, qw):
    """Full-weight same-sentence evidence: for every sentence holding >=2 distinct
    query terms, add the FULL weight of every query term in it (no decay, no
    best-pair max). Summed over sentences."""
    units = collections.defaultdict(set)
    for t in doc_toks.get(eid) or []:
        if t[0] in qw: units[t[1]].add(t[0])
    return sum(sum(qw[w] for w in u) for u in units.values() if len(u) >= 2)

import itertools, pickle
W = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
WP = [0.0, 0.5, 1.0, 1.5, 2.0]
def eval_grid(recs):
    """recs: list of (cands, gold) with cands = [(id, base, cs, cp)]."""
    out = {}
    for ws, wp in itertools.product(W, WP):
        ranks = []
        for cands, gold in recs:
            lst = sorted(cands, key=lambda c: -(c[1] + ws * c[2] + wp * c[3]))
            ranks.append(next((i + 1 for i, c in enumerate(lst[:20]) if c[0] in gold), 0))
        out[(ws, wp)] = ranks
    return out
def summarize(tag, grid):
    base = grid[(0.0, 0.0)]
    n = len(base)
    def mrr(r): return sum(1 / x for x in r if x) / n
    print(f"\n== {tag} (n={n})  MRR grid: rows=sentence weight, cols=paragraph weight")
    print("   s\\p " + "".join(f"{p:>8}" for p in WP))
    for s in W:
        print(f"  {s:>5} " + "".join(f"{mrr(grid[(s, p)]):8.4f}" for p in WP))
    best = sorted(grid, key=lambda k: -mrr(grid[k]))[:5]
    for k in best:
        r = grid[k]
        w = sum(1 for x, y in zip(base, r) if y and (not x or y < x)); l = sum(1 for x, y in zip(base, r) if x and (not y or y > x))
        print(f"   top {k}: MRR={mrr(r):.4f} hit@1={sum(1 for x in r if x == 1)/n:.3f} +{w}/-{l}")
    return {k: mrr(v) for k, v in grid.items()}

def routed(tag, recs):
    """Ratio router: base top1/top2 > theta -> weights (0,0), else w."""
    def rk(cands, gold, ws, wp):
        lst = sorted(cands, key=lambda c: -(c[1] + ws * c[2] + wp * c[3]))
        return next((i + 1 for i, c in enumerate(lst[:20]) if c[0] in gold), 0)
    def ratio(cands):
        v = sorted((c[1] for c in cands), reverse=True)
        return v[0] / v[1] if len(v) > 1 and v[1] > 0 else 99.0
    base = [rk(c, g, 0, 0) for c, g in recs]; n = len(base)
    def line(name, r):
        m = sum(1 / x for x in r if x) / n
        w = sum(1 for x, y in zip(base, r) if y and (not x or y < x)); l = sum(1 for x, y in zip(base, r) if x and (not y or y > x))
        print(f"   {name:24s} MRR={m:.4f} hit@1={sum(1 for x in r if x == 1)/n:.3f} +{w}/-{l}")
    print(f"\n-- {tag}: static vs routed")
    line("base", base)
    for w in ((1.0, 0.5), (1.5, 0.0), (2.0, 0.0), (3.0, 0.0), (2.0, 1.0)):
        line(f"static {w}", [rk(c, g, *w) for c, g in recs])
        for th in (1.1, 1.25, 1.5):
            line(f"  route th{th} {w}", [rk(c, g, 0, 0) if ratio(c) > th else rk(c, g, *w) for c, g in recs])

def sign_p(w: int, l: int) -> float:
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


qrels = json.loads((DATA / "qrels.json").read_text())
used = set()
for f in ("stratified-30.json", "holdout-90.json"):
    used |= {q["question_id"] for q in json.loads((DATA / "subsets" / f).read_text())}
allq = json.loads((DATA / "upstream" / "data" / "questions.json").read_text())
qs = [q for q in allq if qrels.get(q["question_id"])]
RECS = {"tune180": [], "test720": []}
ARMS = ["base", "coloc-sent-l1.0", "s.6+p.4 coloc", "prox.6+para.4"]
ranks = {a: [] for a in ARMS}
for q in qs:
    rel = {Path(p).stem for p in qrels[q["question_id"]]}
    terms = content_terms(q["question"])
    hits = s.content_rank(terms, limit=POOL * 4)
    order, seen, score = [], set(), {}
    for eid, sc in hits:
        sid = ent_sid.get(int(eid))
        if sid and sid not in seen:
            seen.add(sid); order.append(sid); score[sid] = sc
        if len(order) >= POOL:
            break
    qw = {w: weight(w) for w in {t.lower() for t in terms if t.lower() not in STOPWORDS} if weight(w) > 0}
    top = max(score.values()) if score else 1.0
    px = {sid: prox(sid, qw, "sent", 0) for sid in order}
    pm = max(px.values(), default=0) or 1.0
    cs = {sid: coloc(sid, qw, 1) for sid in order}
    cp = {sid: coloc(sid, qw, 2) for sid in order}
    ss = {sid: sentsum(sid, qw) for sid in order}
    sm = max(ss.values(), default=0) or 1.0
    RECS["tune180" if q["question_id"] in used else "test720"].append(
        ([(sid, score[sid] / top, cs[sid], cp[sid]) for sid in order], rel))

G = {}
for k in ("tune180", "test720"):
    G[k] = summarize(f"MemAware {k}", eval_grid(RECS[k]))
    routed(f"MemAware {k}", RECS[k])
pickle.dump(RECS, open("/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/a9e25baf-9b1e-4058-9b95-67ab63c114b2/scratchpad/recs_mem.pkl", "wb"))
pickle.dump(G, open("/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/a9e25baf-9b1e-4058-9b95-67ab63c114b2/scratchpad/grid_mem.pkl", "wb"))
