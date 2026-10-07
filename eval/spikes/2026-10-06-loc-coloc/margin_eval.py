"""Offline margin-rule test on saved per-query features (recs_*.pkl).
cands = [(id, base_norm, coloc_sent, coloc_para)] in BASE order (top-1 first)."""
import pickle, math
SP = "/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/a9e25baf-9b1e-4058-9b95-67ab63c114b2/scratchpad/"
sets = {}
c = pickle.load(open(SP + "recs_cliq.pkl", "rb")); sets["cliq lines"] = c["lines"]; sets["cliq merge"] = c["merge"]
m = pickle.load(open(SP + "recs_mem.pkl", "rb")); sets["mem tune180"] = m["tune180"]; sets["mem test720"] = m["test720"]

def ratio(cands):
    v = sorted((x[1] for x in cands), reverse=True)
    return v[0] / v[1] if len(v) > 1 and v[1] > 0 else 99.0

def rank(cands, gold, ws, wp, delta=None, theta=None):
    if not cands:
        return 0
    if theta is not None and ratio(cands) > theta:
        lst = cands
    else:
        lst = sorted(cands, key=lambda x: -(x[1] + ws * x[2] + wp * x[3]))
        if delta is not None and lst[0][0] != cands[0][0]:
            t1 = cands[0]
            if lst[0][2] - t1[2] <= delta:          # challenger not clearly more co-located
                lst = [t1] + [x for x in lst if x[0] != t1[0]]
    return next((i + 1 for i, x in enumerate(lst[:20]) if x[0] in gold), 0)

def sign_p(w, l):
    n = w + l
    return 1.0 if not n else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)

ARMS = [("base", dict(ws=0, wp=0)), ("static (2,0)", dict(ws=2, wp=0)),
        ("route1.5 (2,0)", dict(ws=2, wp=0, theta=1.5))]
for d in (0.0, 0.1, 0.2, 0.3, 0.5):
    ARMS.append((f"margin{d} (2,0)", dict(ws=2, wp=0, delta=d)))
for d in (0.1, 0.2):
    ARMS.append((f"margin{d}+route1.5 (2,0)", dict(ws=2, wp=0, delta=d, theta=1.5)))
ARMS.append(("margin0.2 (1.5,0)", dict(ws=1.5, wp=0, delta=0.2)))
for name, recs in sets.items():
    base = [rank(cd, g, 0, 0) for cd, g in recs]; n = len(base)
    print(f"\n== {name} (n={n})")
    for an, kw in ARMS:
        r = [rank(cd, g, **kw) for cd, g in recs]
        mrr = sum(1 / x for x in r if x) / n
        w = sum(1 for x, y in zip(base, r) if y and (not x or y < x)); l = sum(1 for x, y in zip(base, r) if x and (not y or y > x))
        print(f"  {an:26s} MRR={mrr:.4f} hit@1={sum(1 for x in r if x == 1)/n:.3f} hit@20={sum(1 for x in r if x)/n:.3f} +{w}/-{l} p={sign_p(w,l):.4f}")
