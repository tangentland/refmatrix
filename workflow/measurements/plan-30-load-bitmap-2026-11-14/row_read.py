"""Read-only probe on a throwaway COPY of a read snapshot (argv[1]). Where load_bitmap's time goes; a stateless
row read with no mask and no len(); identity over every (linkage, concept) row of the partition."""
import os, sys, time, statistics, random, subprocess
from pathlib import Path
ROOT = Path(sys.argv[1])  # a throwaway COPY of a read snapshot under a short temp root
os.environ.pop("REFMATRIX_ROOT", None); os.environ.pop("RMX_PARTITION", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
import numpy as np
from pyroaring import BitMap, BitMap64
from refmatrix.store import Store, _CONCEPT_SHIFT as SH, _ENTITY_MASK
def load(): return subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip().split("load averages:")[-1].strip()
print("load at start:", load())
s = Store(ROOT, partition="refmatrix", read_only=True); s._connect()
assert s._read_only and s.db_path == ROOT / "catalog.read.duckdb", s.db_path
links = [lk["name"] for lk in s.list_linkages()]
for ln in links: s._load_fragment(ln)
frag = s._load_fragment("mentions")
def t(fn, n=20):
    xs = []
    for _ in range(n):
        a = time.perf_counter(); r = fn(); xs.append(time.perf_counter() - a)
    xs.sort(); return statistics.median(xs) * 1e6, xs[int(round(0.9 * (len(xs) - 1)))] * 1e6, r
c = int(np.frombuffer(frag.to_array(), dtype=np.uint64)[len(frag)//2] >> np.uint64(SH))
lo, hi = c << SH, (c + 1) << SH
def mask(): m = BitMap64(); m.add_range(lo, hi); del m
print("len(frag)  med/p90 us:", t(lambda: len(frag))[:2])
print("bool(frag) med/p90 us:", t(lambda: bool(frag))[:2])
print("mask build+free med/p90 us:", t(mask)[:2])
print("load_bitmap today med/p90 us:", t(lambda: s.load_bitmap("mentions", c))[:2])
def row(fr, cid):
    start = cid << SH; end = start + (1 << SH)
    out = BitMap()
    for v in fr.iter_equal_or_larger(start):
        if v >= end: break
        out.add(v & _ENTITY_MASK)
    return out
print("stateless row (no mask, no len) med/p90 us:", t(lambda: row(frag, c))[:2], "|row|", len(row(frag, c)))
# identity over every row of every linkage vs a full decode, and a sample vs load_bitmap
mism = nrow = 0; maxrow = 0; hub = None
for ln in links:
    fr = s._load_fragment(ln)
    arr = np.frombuffer(fr.to_array(), dtype=np.uint64)
    if not len(arr): continue
    h = arr >> np.uint64(SH); l = (arr & np.uint64(_ENTITY_MASK)).astype(np.uint32)
    cids, st0 = np.unique(h, return_index=True); en = np.append(st0[1:], len(arr))
    for cid, a, b in zip(cids.tolist(), st0.tolist(), en.tolist()):
        nrow += 1
        if row(fr, cid) != BitMap(l[a:b]): mism += 1
        if b - a > maxrow: maxrow, hub = b - a, (ln, cid)
random.seed(3); samp = []
for ln in links:
    fr = s._load_fragment(ln); arr = np.frombuffer(fr.to_array(), dtype=np.uint64)
    if len(arr): samp += [(ln, int(x >> np.uint64(SH))) for x in random.sample(list(arr), min(15, len(arr)))]
samp += [("mentions", 999_999_999), ("calls", 1), ("mentions", 0)]
bad = sum(s.load_bitmap(ln, cc) != row(s._load_fragment(ln), cc) for ln, cc in samp)
print(f"identity: {nrow} rows vs fragment decode, mismatches {mism}; {len(samp)} sampled rows vs load_bitmap, mismatches {bad}")
print("largest row:", hub, maxrow, "stateless med/p90 us:", t(lambda: row(s._load_fragment(hub[0]), hub[1]))[:2],
      "today:", t(lambda: s.load_bitmap(*hub), n=5)[:2])
cs = [int(x >> np.uint64(SH)) for x in random.sample(list(np.frombuffer(frag.to_array(), dtype=np.uint64)), 20)]
def mix_today():
    for cc in cs:
        for ln in links: s.load_bitmap(ln, cc)
def mix_new():
    for cc in cs:
        for ln in links: row(s._load_fragment(ln), cc)
a = t(mix_today, n=5); b = t(mix_new, n=5)
print(f"20 concepts x {len(links)} linkages: today med {a[0]/1e3:.1f} ms p90 {a[1]/1e3:.1f} | stateless med {b[0]/1e3:.2f} ms p90 {b[1]/1e3:.2f}")
print("load at end:", load())
