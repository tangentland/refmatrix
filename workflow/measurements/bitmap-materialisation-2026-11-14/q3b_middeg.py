"""Q3: pre-split rows {linkage: {concept_id: BitMap}} built once from the fragments; neighbors
depth 1/2 today vs prototype (same algorithm, row lookup + BitMap.union per hop). Q6: topn.
Every prototype result is asserted IDENTICAL to today's."""
import time, gc, tracemalloc, statistics, random
from common import *
import numpy as np
from pyroaring import BitMap, BitMap64
from refmatrix.query import QueryEngine
from refmatrix.store import DENOTES_TERM_LINKAGES, _CONCEPT_SHIFT, _ENTITY_MASK

print("load at start:", load())
s = open_store()
links = [lk["name"] for lk in s.list_linkages()]

def build_rows(st):
    rows = {}
    for ln in links:
        frag = st._load_fragment(ln)
        if len(frag) == 0: rows[ln] = {}; continue
        arr = np.frombuffer(frag.to_array(), dtype=np.uint64)
        hi = (arr >> np.uint64(_CONCEPT_SHIFT)); lo = (arr & np.uint64(_ENTITY_MASK)).astype(np.uint32)
        cids, starts = np.unique(hi, return_index=True)
        ends = np.append(starts[1:], len(arr))
        rows[ln] = {int(c): BitMap(lo[a:b]) for c, a, b in zip(cids.tolist(), starts.tolist(), ends.tolist())}
    return rows

# build: from a fresh Store (includes fragment deserialize) and with fragments warm
def fresh_build():
    return build_rows(open_store())
st_b_fresh, rows = timeit(fresh_build, n=5)
for ln in links: s._load_fragment(ln)
st_b_warm, _ = timeit(lambda: build_rows(s), n=5)
nrows = sum(len(v) for v in rows.values()); nbits = sum(len(b) for v in rows.values() for b in v.values())
fragbits = sum(len(s._load_fragment(ln)) for ln in links)
assert nbits == fragbits
ser_rows = sum(len(b.serialize()) for v in rows.values() for b in v.values())
ser_frag = sum(len(s._load_fragment(ln).serialize()) for ln in links)
gc.collect(); tracemalloc.start(); r2 = build_rows(s); cur, peak = tracemalloc.get_traced_memory(); tracemalloc.stop(); del r2
print(f"pre-split build fresh Store: {fmt(st_b_fresh)}; fragments warm: {fmt(st_b_warm)}")
print(f"rows {nrows} across {len(links)} linkages, bits {nbits} (== fragment bits); "
      f"serialized rows {ser_rows} B vs fragments {ser_frag} B; traced Python alloc {cur/1e6:.1f} MB (peak {peak/1e6:.1f})")

# --- seeds: in-degree across all linkages, by concept, from the rows; partition concepts only
deg = {}
for ln, v in rows.items():
    for c, b in v.items(): deg[c] = deg.get(c, 0) + len(b)
con = s._connect()
pc = {r[0]: r[1] for r in con.execute("SELECT id, name FROM entities WHERE partition_id=? AND kind='concept' AND noise=0", (s._partition_id,)).fetchall()}
cand = sorted((d, c) for c, d in deg.items() if c in pc)
# Keep only names that resolve uniquely in strict mode (so the seed is the concept we picked).
qs = QueryEngine(s, strict=True)
def ok(c):
    return s.resolve_concept_ids(pc[c], strict=True) == [c]
n = len(cand); picks = []
random.seed(7)
for lo_q, hi_q, k in ((0.80, 0.90, 5), (0.90, 0.97, 5), (0.97, 0.995, 5)):
    pool = cand[int(lo_q * n):max(int(hi_q * n), int(lo_q * n) + 1)]
    random.shuffle(pool); got = 0
    for d, c in pool:
        if ok(c): picks.append((d, c)); got += 1
        if got == k: break
picks.sort()
print("seed in-degree spectrum:", [d for d, _ in picks])
print("degree quantiles of partition concepts: p50", cand[n // 2][0], "p90", cand[int(n * .9)][0], "p99", cand[int(n * .99)][0], "max", cand[-1][0])

def neighbors_proto(qe, rows, concept_name, depth=1):
    st = qe.s
    cids = st.resolve_concept_ids(concept_name, strict=qe.strict)
    if not cids: return BitMap()
    link_names = list(rows)
    typed = [ln for ln in link_names if ln not in DENOTES_TERM_LINKAGES]
    noise = qe._noise_ids(); noise_bm = BitMap(noise) if noise else BitMap()
    def eqv(bm):
        out = BitMap()
        for vs in st.denotes_equivalents(list(bm)).values(): out |= BitMap(vs)
        return out
    seed = BitMap(cids); eq_only = eqv(seed) - seed - noise_bm
    frontier = seed | eq_only; seen = BitMap(frontier)
    E = BitMap()
    for _ in range(depth):
        parts = []
        for cid in frontier:
            for ln in (typed if cid in eq_only else link_names):
                r = rows[ln].get(cid)
                if r is not None: parts.append(r)
        nf = BitMap.union(*parts) if parts else BitMap()
        nf -= seen; nf -= noise_bm
        new_eq = eqv(nf) - seen - noise_bm - nf
        eq_only = new_eq; nf |= new_eq
        if len(nf) == 0: break
        seen |= nf; frontier = nf
    seen -= seed
    return seen

res = []
for depth in (1, 2):
    for d, c in picks:
        name = pc[c]
        # today: fresh QueryEngine per call, as graphread.neighbors_payload does; warm Store
        st_t, a = timeit(lambda: QueryEngine(s, strict=True).neighbors(name, depth=depth), n=5)
        st_p, b = timeit(lambda: neighbors_proto(QueryEngine(s, strict=True), rows, name, depth=depth), n=5)
        assert a == b, (name, depth, len(a), len(b))
        res.append((depth, d, len(a), st_t["med"], st_t["p90"], st_p["med"], st_p["p90"]))
        print(f"depth {depth} indeg {d:6d} |result| {len(a):6d}  today {st_t['med']*1e3:9.2f}/{st_t['p90']*1e3:9.2f} ms   proto {st_p['med']*1e3:8.2f}/{st_p['p90']*1e3:8.2f} ms  (med/p90) IDENTICAL", flush=True)
    print("load:", load())
import json
json.dump(res, open(S / "q3b_neighbors.json", "w"))

print("load at end:", load())
