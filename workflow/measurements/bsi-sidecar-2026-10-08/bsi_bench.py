import importlib.util, time, random, statistics
import numpy as np
from pyroaring import BitMap
spec = importlib.util.spec_from_file_location("vbsi", "/Users/tholley/github/atollogy/bdep/viascope/src/viascope/storage/bsi.py")
vbsi = importlib.util.module_from_spec(spec); spec.loader.exec_module(vbsi)

def t(fn, n=5):
    xs = []
    for _ in range(n):
        s = time.perf_counter(); r = fn(); xs.append(time.perf_counter() - s)
    return statistics.median(xs), r

class VecBSI:
    """Same layout as viascope _NumericBSI (64 slices of uint64), built with numpy."""
    def __init__(self, ids, vals, bits=64):
        self.bits = []
        for b in range(bits):
            self.bits.append(BitMap(ids[((vals >> np.uint64(b)) & np.uint64(1)).astype(bool)]))
    def gte(self, thr, all_rows):
        greater, equal = BitMap(), all_rows.copy()
        for b in range(len(self.bits) - 1, -1, -1):
            s = self.bits[b]
            if (thr >> b) & 1: equal &= s
            else:
                greater |= (equal & s); equal -= s
        return greater | equal

rng = np.random.default_rng(7)
for N in (80_000, 1_000_000):
    ids = np.arange(N, dtype=np.uint32)
    vals = rng.integers(0, 2**32, N, dtype=np.uint64)       # e.g. timestamps / scaled weights
    all_rows = BitMap(ids)
    # viascope as-is: per-row Python add
    def build_v():
        x = vbsi._NumericBSI()
        for i, v in zip(ids.tolist(), vals.tolist()): x.add_uint(i, v)
        return x
    tb_v, bv = t(build_v, n=1 if N > 100_000 else 3)
    tb_n, bn = t(lambda: VecBSI(ids, vals))
    tb_n32, bn32 = t(lambda: VecBSI(ids, vals, bits=32))
    thr = int(np.median(vals))
    tq_v, rv = t(lambda: bv.gte(thr, all_rows))
    tq_n, rn = t(lambda: bn.gte(thr, all_rows))
    tq_n32, rn32 = t(lambda: bn32.gte(thr, all_rows))
    tq_np, rnp = t(lambda: np.flatnonzero(vals >= thr))
    assert rv == rn == rn32 == BitMap(rnp.astype(np.uint32)), "results differ"
    print(f"N={N:,}: build viascope {tb_v*1000:,.0f} ms | numpy-64 {tb_n*1000:,.1f} ms | numpy-32 {tb_n32*1000:,.1f} ms"
          f"  ||  gte query viascope {tq_v*1000:.2f} ms | numpy-built-64 {tq_n*1000:.2f} ms | 32-slice {tq_n32*1000:.2f} ms | plain numpy scan {tq_np*1000:.2f} ms  ({len(rv):,} rows)")
