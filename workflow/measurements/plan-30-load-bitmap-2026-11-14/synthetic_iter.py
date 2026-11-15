import time, statistics, sys
import numpy as np
from pyroaring import BitMap, BitMap64
SH = 32
def t(fn, n=20):
    xs = []
    for _ in range(n):
        a = time.perf_counter(); r = fn(); xs.append(time.perf_counter() - a)
    return statistics.median(xs) * 1e6, r
def it(fr, start, end):
    out = BitMap()
    for v in fr.iter_equal_or_larger(start):
        if v >= end: break
        out.add(v & 0xFFFFFFFF)
    return out
for emax, cmax in ((130_000, 115_000), (3_000_000, 3_000_000), (30_000_000, 30_000_000)):
    rng = np.random.default_rng(7)
    sizes = np.minimum(rng.zipf(1.6, 114_000), 5000); scale = 834_000 / sizes.sum()
    cs = np.sort(rng.choice(cmax, size=114_000, replace=False)).astype(np.uint64)
    vals = []
    for c, n in zip(cs, sizes):
        n = max(1, int(n * scale))
        e = rng.choice(emax, size=min(n, emax), replace=False).astype(np.uint64)
        vals.append((c << np.uint64(SH)) | e)
    arr = np.unique(np.concatenate(vals))
    fr = BitMap64.deserialize(BitMap64(arr.tolist()).serialize())
    stats = fr.get_statistics()
    hi = arr >> np.uint64(SH); cids, st0, cnt = np.unique(hi, return_index=True, return_counts=True)
    big = [i for i in range(len(cids)) if 250 <= cnt[i] <= 400]
    print(f"emax={emax} cmax={cmax} bits={len(fr)} containers={stats.get('n_containers')}")
    for i in (big[0], big[len(big)//2], big[-1]):
        c = int(cids[i]); s, e = c << SH, (c + 1) << SH
        ref = BitMap((arr[st0[i]:st0[i]+cnt[i]] & np.uint64(0xFFFFFFFF)).astype(np.uint32))
        us, r = t(lambda: it(fr, s, e))
        us0, _ = t(lambda: next(iter(fr.iter_equal_or_larger(s)), None))
        us4, a = t(lambda: fr.next_set_bit(s))
        print(f"   pos={st0[i]:7d} |row|={cnt[i]:4d} iter {us:8.1f} us ok={r==ref}; seek+first only {us0:8.1f} us; next_set_bit {us4:6.2f} us")
