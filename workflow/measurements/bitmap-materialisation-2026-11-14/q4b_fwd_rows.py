"""Q4b: forward pre-split rows {linkage: {entity_id: BitMap(concepts)}} vs entity_links SQL, and
where the transposed BitMap64 range lookup spends its time (per-op cost on the largest fragment)."""
from common import *
import numpy as np
from pyroaring import BitMap, BitMap64
from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK
print("load at start:", load())
s = open_store(); con = s._connect()
links = [lk["name"] for lk in s.list_linkages()]
lid = {ln: s.get_linkage_id(ln) for ln in links}; name_of = {v: k for k, v in lid.items()}
M = np.uint64(_ENTITY_MASK); SH = np.uint64(_CONCEPT_SHIFT)
for ln in links: s._load_fragment(ln)
def build_fwd():
    out = {}
    for ln in links:
        arr = np.frombuffer(s._load_fragment(ln).to_array(), dtype=np.uint64)
        if not len(arr): out[ln] = {}; continue
        e = (arr & M); c = (arr >> SH).astype(np.uint32)
        o = np.argsort(e, kind="stable"); e, c = e[o], c[o]
        u, st_ = np.unique(e, return_index=True); en = np.append(st_[1:], len(e))
        out[ln] = {int(x): BitMap(c[a:b]) for x, a, b in zip(u.tolist(), st_.tolist(), en.tolist())}
    return out
st_b, F = timeit(build_fwd, n=5)
print("forward pre-split build (fragments warm):", fmt(st_b), "rows", sum(len(v) for v in F.values()))
def fwd_rows(e):
    return {(ln, c) for ln, d in F.items() for c in (d.get(e) or ())}
def fwd_sql(e):
    return {(name_of[r[0]], int(r[1])) for r in con.execute(
        "SELECT linkage_id, concept_id FROM entity_links WHERE entity_id=?", (e,)).fetchall() if r[0] in name_of}
ents = [r[0] for r in con.execute("SELECT id FROM entities WHERE partition_id=? AND kind IN ('doc','code','memory') ORDER BY id", (s._partition_id,)).fetchall()][::200]
bad = 0; ts, tr = [], []
for e in ents:
    a = fwd_sql(e); b = fwd_rows(e)
    bad += a != b
    st1, _ = timeit(lambda: fwd_sql(e), n=5); st2, _ = timeit(lambda: fwd_rows(e), n=5)
    ts.append(st1["med"]); tr.append(st2["med"])
print(f"{len(ents)} entities: SQL {fmt(stats(ts))} | forward rows {fmt(stats(tr), 'us', 1e6)}; set mismatches {bad}")
# per-op cost of the BitMap64 range path on the biggest fragment
big = max(links, key=lambda ln: len(s._load_fragment(ln))); frag = s._load_fragment(big)
c = int(np.frombuffer(frag.to_array(), dtype=np.uint64)[len(frag)//2] >> SH)
lo, hi = c << _CONCEPT_SHIFT, (c + 1) << _CONCEPT_SHIFT
def mk(): m = BitMap64(); m.add_range(lo, hi); return m
m = mk()
for label, fn in (("BitMap64 mask build (add_range 2^32)", mk), ("frag & mask", lambda: frag & m),
                  ("frag.range_cardinality", lambda: frag.range_cardinality(lo, hi)),
                  ("load_bitmap(big, c) total", lambda: s.load_bitmap(big, c))):
    st_, _ = timeit(fn, n=20, warm=2); print(f"  {big} ({len(frag)} bits) {label}: {fmt(st_, 'us', 1e6)}")
print("load at end:", load())
