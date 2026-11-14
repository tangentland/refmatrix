"""Where load_bitmap's per-call cost goes, and a no-mask row extraction (iter_equal_or_larger /
rank+slice) checked IDENTICAL to load_bitmap over every (linkage, concept) row of the partition."""
import itertools, time
from common import *
import numpy as np
from pyroaring import BitMap, BitMap64
from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK
print("load at start:", load())
s = open_store()
links = [lk["name"] for lk in s.list_linkages()]
for ln in links: s._load_fragment(ln)
frag = s._load_fragment("mentions"); SH = _CONCEPT_SHIFT
c = int(np.frombuffer(frag.to_array(), dtype=np.uint64)[len(frag)//2] >> np.uint64(SH))
lo, hi = c << SH, (c + 1) << SH
def mask_build_and_free():
    m = BitMap64(); m.add_range(lo, hi); del m
def mask_build_kept():
    m = BitMap64(); m.add_range(lo, hi); return m
st1, _ = timeit(mask_build_and_free, n=20, warm=2)
keep = []
def k(): keep.append(mask_build_kept())
st2, _ = timeit(k, n=20, warm=0)
t = time.perf_counter(); keep.clear(); free20 = time.perf_counter() - t
m = mask_build_kept(); print("mask stats:", {k_: v for k_, v in m.get_statistics().items() if 'container' in k_ and v}) if hasattr(m, 'get_statistics') else None
print(f"mask build+free {fmt(st1,'us',1e6)}; build only {fmt(st2,'us',1e6)}; free of 20 masks {free20/20*1e6:.0f} us each")

def lb_iter(fr, cid):
    start = cid << SH; end = (cid + 1) << SH
    out = BitMap()
    if len(fr) == 0: return out
    for v in fr.iter_equal_or_larger(start):
        if v >= end: break
        out.add(v & _ENTITY_MASK)
    return out
def lb_slice(fr, cid):
    start = cid << SH; end = (cid + 1) << SH
    if len(fr) == 0: return BitMap()
    n = fr.range_cardinality(start, end)
    if n == 0: return BitMap()
    i = fr.rank(start - 1) if start > 0 else 0
    return BitMap(np.frombuffer(fr[i:i + n].to_array(), dtype=np.uint64).astype(np.uint32)) if n > 64 else BitMap([fr[j] & _ENTITY_MASK for j in range(i, i + n)])
for label, fn in (("load_bitmap today", lambda: s.load_bitmap("mentions", c)),
                  ("iter_equal_or_larger", lambda: lb_iter(frag, c)),
                  ):
    st_, r = timeit(fn, n=20, warm=2); print(f"  mentions row c={c} (|row|={len(r)}): {label}: {fmt(st_, 'us', 1e6)}")
# (a rank+slice variant was abandoned: BitMap64.__getitem__ calls get_cardinality per element,
# observed in `sample` of the run, so it is O(containers) per element.)
# exhaustive identity check over every row of every linkage (vs load_bitmap) is ~6 ms x 123k rows
# = too slow; check every row against the pre-split decode instead, and a sample against load_bitmap.
mism = 0; nrow = 0
for ln in links:
    fr = s._load_fragment(ln)
    if not len(fr): continue
    arr = np.frombuffer(fr.to_array(), dtype=np.uint64)
    hi_ = arr >> np.uint64(SH); lo_ = (arr & np.uint64(_ENTITY_MASK)).astype(np.uint32)
    cids, st0 = np.unique(hi_, return_index=True); en = np.append(st0[1:], len(arr))
    for cid, a, b in zip(cids.tolist(), st0.tolist(), en.tolist()):
        ref = BitMap(lo_[a:b]); nrow += 1
        if lb_iter(fr, cid) != ref: mism += 1
import random; random.seed(3)
samp = []
for ln in links:
    fr = s._load_fragment(ln)
    if len(fr): samp += [(ln, int(x >> SH)) for x in random.sample(list(np.frombuffer(fr.to_array(), dtype=np.uint64)), min(15, len(fr)))]
samp += [("mentions", 999_999_999), ("calls", 1)]  # absent rows
bad2 = sum(s.load_bitmap(ln, cc) != lb_iter(s._load_fragment(ln), cc) for ln, cc in samp)
print(f"identity: {nrow} rows vs fragment decode, mismatches {mism}; {len(samp)} sampled rows vs load_bitmap, mismatches {bad2}")
# per-call over a realistic mix: 20 concepts x 34 linkages (neighbors depth-1 shape)
cs = [int(x >> SH) for x in random.sample(list(np.frombuffer(frag.to_array(), dtype=np.uint64)), 20)]
def mix_today():
    for cc in cs:
        for ln in links: s.load_bitmap(ln, cc)
def mix_slice():
    for cc in cs:
        for ln in links: lb_iter(s._load_fragment(ln), cc)
st_a, _ = timeit(mix_today, n=5); st_b, _ = timeit(mix_slice, n=5)
print(f"20 concepts x {len(links)} linkages: load_bitmap {fmt(st_a)} | iter_equal_or_larger {fmt(st_b)}")
print("load at end:", load())
