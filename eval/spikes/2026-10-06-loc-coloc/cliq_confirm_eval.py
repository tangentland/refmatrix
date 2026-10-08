#!/usr/bin/env python3
"""Throwaway: cliquedb known-item, harness gold FIXED to include anchor-concept
paths (GMD docs are kind=concept anchors now). Weighted sentence proximity +
sentence/paragraph co-location re-rank of content_rank's top-50 entities.
Runs against a COPY of the cliquedb read replica."""
from __future__ import annotations
import collections, math, os, random, re, sys
from pathlib import Path
REPO = Path("/Users/tholley/claude_tools/refmatrix")
sys.path.insert(0, str(REPO / "src")); sys.path.insert(0, str(REPO / "eval" / "cliquedb"))
ROOT = sys.argv[1]
os.environ["REFMATRIX_ROOT"] = ROOT; os.environ["RMX_PARTITION"] = "cliquedb"
import baseline_rederive as H  # noqa: E402
from refmatrix.store import Store  # noqa: E402
from refmatrix.terms import STOPWORDS, content_terms  # noqa: E402

TOK = re.compile(r"[a-z][a-z0-9_']*"); SENT = re.compile(r"(?<=[.!?])\s+|\n+")
POOL, LIMIT, LAM = 50, 20, 0.3
s = Store(ROOT, read_only=True); con = s._connect(); pid = s._partition_id

by_path: dict[str, set] = collections.defaultdict(set)
for eid, path in con.execute("SELECT id, path FROM entities WHERE partition_id=? AND path IS NOT NULL",
                             (pid,)).fetchall():
    by_path[str(path)].add(int(eid))
md = [p for p in by_path if p.endswith(".md") and Path(p).exists()]

def toks_of(txt: str):
    out, si = [], 0
    for pi, para in enumerate(re.split(r"\n\s*\n", txt.lower())):
        for sent in SENT.split(para):
            out.extend((m.group(0), si, pi) for m in TOK.finditer(sent)); si += 1
    return out

df, tfs = collections.Counter(), collections.Counter()
for p in md:
    c = collections.Counter(t[0] for t in toks_of(Path(p).read_text(errors="ignore")))
    for w, n in c.items(): df[w] += 1; tfs[w] += n
N = len(md)
def weight(t): return math.log(N / df[t]) * (tfs[t] / df[t]) if df[t] else 0.0

_ent = {}
def ent_toks(eid):
    if eid not in _ent:
        r = con.execute("SELECT path, tldr FROM entities WHERE id=?", (eid,)).fetchone()
        txt = (r[1] if r and r[1] else "") or ""
        if not txt and r and r[0] and Path(str(r[0])).is_file():
            txt = Path(str(r[0])).read_text(errors="ignore")
        _ent[eid] = toks_of(txt)
    return _ent[eid]

def prox(eid, qw):
    last, best = {}, 0.0
    for w, si, _ in ent_toks(eid):
        if w not in qw: continue
        for o, ps in last.items():
            if o != w: best = max(best, math.sqrt(qw[w] * qw[o]) / (1.0 + si - ps))
        last[w] = si
    return best

def coloc(eid, qw, lvl):
    tot = sum(qw.values()) or 1.0; units = collections.defaultdict(set)
    for t in ent_toks(eid):
        if t[0] in qw: units[t[lvl]].add(t[0])
    return max((sum(qw[w] for w in u) for u in units.values()), default=0.0) / tot

def sign_p(w, l):
    n = w + l
    if not n: return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)

ARMS = ["base", "sent-l0.3", "coloc-sent", "coloc-para", "sent+coloc-para"]
res = {c: {a: [] for a in ARMS} for c in ("lines", "merge")}
rnd = random.Random(20260903); paths = md[:]; rnd.shuffle(paths); asked = 0
for p in paths:
    if asked >= 300: break
    pool = H._body_lines(Path(p))
    if not pool: continue
    draw = random.Random(rnd.random())
    qs = {"lines": H._q_lines(pool, random.Random(draw.random()), None), "merge": H._q_merge(pool)}
    if all(v is None for v in qs.values()): continue
    asked += 1; gold = by_path[p]
    for cons, q in qs.items():
        if q is None: continue
        base = s.content_rank(q.split(), limit=POOL)
        if not base:
            for a in ARMS: res[cons][a].append(0)
            continue
        qw = {w: weight(w) for w in {t.lower() for t in content_terms(q)} - STOPWORDS if weight(w) > 0}
        top = max(sc for _, sc in base) or 1.0
        sc = {e: v / top for e, v in base}
        px = {e: prox(e, qw) for e, _ in base}; pm = max(px.values()) or 1.0
        cs = {e: coloc(e, qw, 1) for e, _ in base}; cp = {e: coloc(e, qw, 2) for e, _ in base}
        fns = {"base": lambda e: sc[e], "sent-l0.3": lambda e: sc[e] + LAM * px[e] / pm,
               "coloc-sent": lambda e: sc[e] + LAM * cs[e], "coloc-para": lambda e: sc[e] + LAM * cp[e],
               "sent+coloc-para": lambda e: sc[e] + LAM * px[e] / pm + LAM * cp[e]}
        order = [e for e, _ in base]
        for a, fn in fns.items():
            lst = sorted(order, key=lambda e: -fn(e))
            res[cons][a].append(next((i + 1 for i, e in enumerate(lst[:LIMIT]) if e in gold), 0))

print(f"md docs on disk={N} queried={asked}")
for cons, arms in res.items():
    print(f"\n== {cons}"); b = arms["base"]
    for a, rs in arms.items():
        n = len(rs); mrr = sum(1 / r for r in rs if r) / n
        at = lambda k: sum(1 for r in rs if 0 < r <= k) / n
        w = sum(1 for x, y in zip(b, rs) if y and (not x or y < x)); l = sum(1 for x, y in zip(b, rs) if x and (not y or y > x))
        print(f"  {a:16s} n={n} MRR={mrr:.4f} hit@1={at(1):.3f} hit@5={at(5):.3f} hit@20={at(20):.3f} +{w}/-{l} p={sign_p(w,l):.4f}")
        print(f"  {'':16s} hist {H._histogram(rs, LIMIT)}")
