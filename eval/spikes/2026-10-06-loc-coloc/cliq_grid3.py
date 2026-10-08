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
FULLBODY = [0]
def ent_toks(eid):
    if eid not in _ent:
        r = con.execute("SELECT path, tldr, meta FROM entities WHERE id=?", (eid,)).fetchone()
        txt = ""
        meta = __import__("json").loads(r[2]) if r and r[2] and r[2].startswith("{") else {}
        if r and r[0] and Path(str(r[0])).is_file():
            lines = Path(str(r[0])).read_text(errors="ignore").splitlines()
            if isinstance(meta.get("line"), int):
                # FULL section body: from the heading to the next heading of ANY level
                # (the anchor's own text; subsections are their own anchors).
                start = meta["line"]
                end = next((i for i in range(start, len(lines))
                            if re.match(r"#{1,6}\s", lines[i])), len(lines))
                txt = "\n".join(lines[start:end])
                FULLBODY[0] += 1
            else:
                txt = "\n".join(lines)
        if not txt:
            txt = (r[1] if r and r[1] else "") or ""
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

def sentsum(eid, qw):
    """Full-weight same-sentence evidence: for every sentence holding >=2 distinct
    query terms, add the FULL weight of every query term in it (no decay, no
    best-pair max). Summed over sentences."""
    units = collections.defaultdict(set)
    for t in ent_toks(eid):
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

def sign_p(w, l):
    n = w + l
    if not n: return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)

ARMS = ["base", "coloc-sent-l1.0", "s.6+p.4 coloc", "prox.6+para.4"]
RECS = {"lines": [], "merge": []}
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
            RECS[cons].append(([], gold))
            continue
        qw = {w: weight(w) for w in {t.lower() for t in content_terms(q)} - STOPWORDS if weight(w) > 0}
        top = max(sc for _, sc in base) or 1.0
        sc = {e: v / top for e, v in base}
        px = {e: prox(e, qw) for e, _ in base}; pm = max(px.values()) or 1.0
        cs = {e: coloc(e, qw, 1) for e, _ in base}; cp = {e: coloc(e, qw, 2) for e, _ in base}
        ss = {e: sentsum(e, qw) for e, _ in base}; sm = max(ss.values()) or 1.0
        RECS[cons].append(([(e, sc[e], cs[e], cp[e]) for e, _ in base], gold))

print(f"queried={asked}")
G = {}
for cons in ("lines", "merge"):
    G[cons] = summarize(f"cliquedb {cons}", eval_grid(RECS[cons]))
    routed(f"cliquedb {cons}", RECS[cons])
pickle.dump(RECS, open("/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/a9e25baf-9b1e-4058-9b95-67ab63c114b2/scratchpad/recs_cliq_full.pkl", "wb"))
pickle.dump(G, open("/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/a9e25baf-9b1e-4058-9b95-67ab63c114b2/scratchpad/grid_cliq.pkl", "wb"))

print("anchor bodies read from file:", FULLBODY[0])
