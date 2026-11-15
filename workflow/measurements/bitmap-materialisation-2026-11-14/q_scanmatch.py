"""How many load_bitmap calls the per-prompt match_concepts path makes and what they cost; and a
decoded-array (np.searchsorted) row extraction checked IDENTICAL over every row + per-prompt output."""
import json, time
from common import *
import numpy as np
from pyroaring import BitMap
from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK
from refmatrix.scan import extract_candidates, match_concepts
print("load at start:", load())
s = open_store()
links = [lk["name"] for lk in s.list_linkages()]
M = np.uint64(_ENTITY_MASK)
t0 = time.perf_counter()
arrs = {ln: np.frombuffer(s._load_fragment(ln).to_array(), dtype=np.uint64) for ln in links}
t_dec = time.perf_counter() - t0
print(f"decode all {len(links)} fragments to sorted uint64 arrays: {t_dec*1e3:.1f} ms, {sum(a.nbytes for a in arrs.values())/1e6:.1f} MB")
def lb_ss(linkage, cid):
    a = arrs.get(linkage)
    if a is None or not len(a): return BitMap()
    lo = np.searchsorted(a, np.uint64(cid << _CONCEPT_SHIFT)); hi = np.searchsorted(a, np.uint64((cid + 1) << _CONCEPT_SHIFT))
    return BitMap((a[lo:hi] & M).astype(np.uint32))
# identity over every row of every linkage
bad = rows = 0
for ln, a in arrs.items():
    if not len(a): continue
    hi_ = a >> np.uint64(_CONCEPT_SHIFT); cids, st0 = np.unique(hi_, return_index=True); en = np.append(st0[1:], len(a))
    for c, x, y in zip(cids.tolist(), st0.tolist(), en.tolist()):
        rows += 1; bad += lb_ss(ln, c) != BitMap((a[x:y] & M).astype(np.uint32))
import random; random.seed(5)
samp = [(ln, int(v >> np.uint64(_CONCEPT_SHIFT))) for ln, a in arrs.items() if len(a) for v in random.sample(list(a), min(10, len(a)))] + [("mentions", 10**9)]
bad2 = sum(s.load_bitmap(ln, c) != lb_ss(ln, c) for ln, c in samp)
print(f"identity: {rows} rows mismatches {bad}; {len(samp)} sampled vs load_bitmap mismatches {bad2}")
c = int(arrs["mentions"][len(arrs["mentions"]) // 2] >> np.uint64(_CONCEPT_SHIFT))
st1, _ = timeit(lambda: s.load_bitmap("mentions", c), n=20, warm=2); st2, _ = timeit(lambda: lb_ss("mentions", c), n=20, warm=2)
print(f"mentions row: load_bitmap {fmt(st1,'us',1e6)} | searchsorted {fmt(st2,'us',1e6)}")

bodies = []
for line in open("/Users/tholley/claude_tools/refmatrix/.refmatrix/query.log", errors="replace"):
    try: r = json.loads(line)
    except Exception: continue
    if r.get("kind") == "scan" and r.get("source") == "scan-prompt" and r.get("ts", "") >= "2026-11-13":
        bodies.append(r.get("body") or "")
bodies = bodies[-40:]
orig = s.load_bitmap; calls = [0]
def counting(ln, cid):
    calls[0] += 1; return orig(ln, cid)
per_calls, t_today, t_new, same = [], [], [], 0
for b in bodies:
    cands = extract_candidates(b)
    s.load_bitmap = counting; calls[0] = 0
    t = time.perf_counter(); m1 = match_concepts(s, cands); t_today.append(time.perf_counter() - t); per_calls.append(calls[0])
    s.load_bitmap = lb_ss
    t = time.perf_counter(); m2 = match_concepts(s, cands); t_new.append(time.perf_counter() - t)
    s.load_bitmap = orig
    assert m1 == m2, (m1, m2); same += 1
print(f"{len(bodies)} recent prompts: load_bitmap calls per match_concepts {stats(per_calls)}")
print(f"match_concepts today {fmt(stats(t_today))} | with searchsorted rows {fmt(stats(t_new))}; identical outputs {same}/{len(bodies)}")
print("load at end:", load())
