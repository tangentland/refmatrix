"""Q4: transposed fragments ((entity << 32) | concept) per linkage: build, size, forward lookup
vs entity_links SQL (sets compared). Q5: filter bitmaps vs today's per-call noise SQL."""
import time, random
from common import *
import numpy as np
from pyroaring import BitMap, BitMap64
from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK

print("load at start:", load())
s = open_store(); con = s._connect(); duck = con._duck
links = [lk["name"] for lk in s.list_linkages()]
lid = {ln: s.get_linkage_id(ln) for ln in links}
for ln in links: s._load_fragment(ln)
M = np.uint64(_ENTITY_MASK); SH = np.uint64(_CONCEPT_SHIFT)

def transpose(frag):
    arr = np.frombuffer(frag.to_array(), dtype=np.uint64)
    t = ((arr & M) << SH) | (arr >> SH)
    t.sort()
    b = BitMap64(t)
    return b
def build_all():
    return {ln: transpose(s._load_fragment(ln)) for ln in links}
st_tb, T = timeit(build_all, n=5)
ser_T = sum(len(b.serialize()) for b in T.values())
ser_F = sum(len(s._load_fragment(ln).serialize()) for ln in links)
assert sum(len(b) for b in T.values()) == sum(len(s._load_fragment(ln)) for ln in links)
st_ser, _ = timeit(lambda: [b.serialize() for b in T.values()], n=5)
blobs = {ln: b.serialize() for ln, b in T.items()}
st_de, _ = timeit(lambda: [BitMap64.deserialize(x) for x in blobs.values()], n=5)
print(f"transposed build (all {len(links)} linkages, fragments warm): {fmt(st_tb)}")
print(f"serialized: transposed {ser_T} B vs original fragments {ser_F} B (ratio {ser_T/ser_F:.2f}); "
      f"serialize {fmt(st_ser)}; deserialize {fmt(st_de)}")

def fwd_T(e):
    out = set(); lo = e << _CONCEPT_SHIFT; hi = (e + 1) << _CONCEPT_SHIFT
    for ln, b in T.items():
        if not len(b): continue
        mask = BitMap64(); mask.add_range(lo, hi)
        sub = b & mask
        if len(sub):
            for c in (np.frombuffer(sub.to_array(), dtype=np.uint64) & M).tolist(): out.add((ln, c))
    return out
def fwd_T_fast(e):  # range_cardinality pre-check avoids building empty intersections
    out = set(); lo = e << _CONCEPT_SHIFT; hi = (e + 1) << _CONCEPT_SHIFT
    for ln, b in T.items():
        if b.range_cardinality(lo, hi) == 0: continue
        mask = BitMap64(); mask.add_range(lo, hi)
        for c in (np.frombuffer((b & mask).to_array(), dtype=np.uint64) & M).tolist(): out.add((ln, c))
    return out
name_of = {v: k for k, v in lid.items()}
def fwd_sql(e):
    return {(name_of[r[0]], int(r[1])) for r in con.execute(
        "SELECT linkage_id, concept_id FROM entity_links WHERE entity_id=?", (e,)).fetchall() if r[0] in name_of}

# sample entities across out-degree: docs, code, memory of the partition
ents = [r[0] for r in con.execute("SELECT id FROM entities WHERE partition_id=? AND kind IN ('doc','code','memory')", (s._partition_id,)).fetchall()]
outdeg = {}
for ln, b in T.items():
    if not len(b): continue
    arr = np.frombuffer(b.to_array(), dtype=np.uint64) >> SH
    u, cnt = np.unique(arr, return_counts=True)
    for x, y in zip(u.tolist(), cnt.tolist()): outdeg[x] = outdeg.get(x, 0) + y
cand = sorted((outdeg.get(e, 0), e) for e in ents if outdeg.get(e, 0) > 0)
n = len(cand)
picks = [cand[int(q * (n - 1))] for q in (0.0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 0.95, 0.99, 1.0)]
print("sample entity out-degrees:", [d for d, _ in picks])
mism = 0; rows_out = []
for d, e in picks:
    a = fwd_sql(e); b = fwd_T(e); c_ = fwd_T_fast(e)
    assert b == c_
    if a != b:
        mism += 1
        print(f"  MISMATCH e={e}: sql-only {len(a-b)} frag-only {len(b-a)}  e.g. sql-only {sorted(a-b)[:3]} frag-only {sorted(b-a)[:3]}")
    st_s, _ = timeit(lambda: fwd_sql(e), n=7); st_t, _ = timeit(lambda: fwd_T_fast(e), n=7)
    rows_out.append((d, len(a), len(b), st_s, st_t))
    print(f"  outdeg {d:5d}: SQL {fmt(st_s)} | transposed {fmt(st_t)}  sets {'IDENTICAL' if a == b else 'DIFFER'}")
print("mismatching entities:", mism, "/", len(picks))
print("load after Q4:", load())

# --- Q5 filter bitmaps --------------------------------------------------------------------
pid = s._partition_id
def bm_of(sql, args):
    d = duck.execute(sql, args).fetchnumpy()
    return BitMap(d["id"].astype(np.uint32))
qs = {
    "noise (concept, partition)": ("SELECT id FROM entities WHERE partition_id=? AND kind='concept' AND noise=1", [pid]),
    "protected (partition)": ("SELECT id FROM entities WHERE partition_id=? AND protected=1", [pid]),
    "partition (all entities)": ("SELECT id FROM entities WHERE partition_id=?", [pid]),
}
for k in ("concept", "code", "doc", "memory"):
    qs[f"kind={k} (partition)"] = ("SELECT id FROM entities WHERE partition_id=? AND kind=?", [pid, k])
tot = 0.0
for label, (q, a) in qs.items():
    st_, bm = timeit(lambda: bm_of(q, a), n=7)
    tot += st_["med"]
    print(f"  build {label}: {fmt(st_)} card {len(bm)} serialized {len(bm.serialize())} B")
print(f"  all filter bitmaps built once: ~{tot*1e3:.1f} ms total (sum of medians)")
st_today, noise = timeit(lambda: s.noise_concept_ids(), n=9)
st_today_bm, _ = timeit(lambda: BitMap(s.noise_concept_ids()), n=9)
print(f"today noise_concept_ids() per QueryEngine: {fmt(st_today)}; + BitMap(noise) as neighbors does: {fmt(st_today_bm)} (|noise|={len(noise)})")
nb = bm_of(*qs["noise (concept, partition)"]); assert set(nb) == noise
# _universe() today (NOT queries)
from refmatrix.query import QueryEngine
st_u, U = timeit(lambda: QueryEngine(s)._universe(), n=5)
assert U == bm_of(*qs["partition (all entities)"])
print(f"today QueryEngine._universe() (python loop over SQL rows): {fmt(st_u)}; identical to the partition bitmap")
print("load at end:", load())
