import os, sys
import pyroaring, pyarrow as pa, vortex as vx, vortex.registry as reg, duckdb
D = sys.argv[1]
class RoaringIds(vx.PyArray):
    id = "refmatrix.roaring"
    def __new__(cls, bm):
        self = super().__new__(cls, cls, len(bm), vx.uint(32, nullable=False))
        self.bm = bm
        return self
    def __len__(self): return len(self.bm)
    @property
    def dtype(self): return vx.uint(32, nullable=False)
    @classmethod
    def decode(cls, parts, ctx, dtype, len):
        return cls(pyroaring.BitMap.deserialize(bytes(parts.buffers()[0])))
def step(name, fn):
    try: out = fn(); print(f"OK   {name}: {type(out).__name__}{(chr(32)+str(out)[:120]) if isinstance(out,(int,tuple,str)) else chr(32)}"); return out
    except Exception as e: print(f"FAIL {name}: {type(e).__name__}: {str(e)[:240]}")
reg.register(RoaringIds)
a = step("construct", lambda: RoaringIds(pyroaring.BitMap(range(0, 80_000, 7))))
if a is not None:
    step("len", lambda: len(a))
    step("compress", lambda: vx.compress(a))
    p = os.path.join(D, "roaring.vortex")
    step("write", lambda: vx.io.write(a, p))
    if os.path.exists(p):
        step("python read", lambda: vx.open(p).scan().read_all())
        con = duckdb.connect(); con.execute("INSTALL vortex; LOAD vortex;")
        step("duckdb read", lambda: con.execute(f"SELECT count(*) FROM read_vortex('{p}')").fetchone())
