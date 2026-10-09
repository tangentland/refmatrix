import random, time, os, sys
import pyarrow as pa, pyroaring, vortex as vx, duckdb
random.seed(7)
D = sys.argv[1]; N_ENT = 80_000; N_CON = 2_000
cells = {}
for c in range(N_CON):
    size = min(N_ENT, int(random.paretovariate(1.1) * 8))      # skewed: most cells small, a few huge
    cells[c] = sorted(random.sample(range(N_ENT), size))
rows_c = [c for c, ids in cells.items() for _ in ids]
rows_e = [e for ids in cells.values() for e in ids]
print(f"cells={N_CON} memberships={len(rows_e):,} max_cell={max(map(len,cells.values())):,}")
# pyroaring baseline: one bitmap per cell, portable serialization
rb = {c: pyroaring.BitMap(ids) for c, ids in cells.items()}
rb_bytes = sum(len(b.serialize()) for b in rb.values())
# vortex: long table (concept_id u32, entity_id u32), sorted by concept then entity
tbl = pa.table({"concept_id": pa.array(rows_c, pa.uint32()), "entity_id": pa.array(rows_e, pa.uint32())})
arr = vx.array(tbl)
carr = vx.compress(arr)
print("vortex encodings:", str(carr)[:300].replace("\n", " "))
path = os.path.join(D, "cells.vortex")
t = time.time(); vx.io.write(carr, path); tw = time.time() - t
size = os.path.getsize(path)
back = vx.open(path).scan().read_all().to_arrow_table() if hasattr(vx.open(path), "scan") else None
ok = back is not None and back.equals(tbl)
print(f"vortex file={size:,} B (write {tw:.2f}s) | pyroaring serialized={rb_bytes:,} B | arrow raw={tbl.nbytes:,} B")
print("python round-trip exact:", ok)
con = duckdb.connect()
con.execute("INSTALL vortex; LOAD vortex;")
probe = max(cells, key=lambda c: len(cells[c]))
t = time.time()
got = [r[0] for r in con.execute(f"SELECT entity_id FROM read_vortex('{path}') WHERE concept_id={probe} ORDER BY 1").fetchall()]
td = time.time() - t
print(f"duckdb read_vortex filter concept={probe}: {len(got):,} ids in {td*1000:.1f} ms, matches pyroaring: {got == list(rb[probe])}")
a, b = sorted(cells, key=lambda c: -len(cells[c]))[:2]
t = time.time()
inter = [r[0] for r in con.execute(f"SELECT entity_id FROM read_vortex('{path}') WHERE concept_id={a} INTERSECT SELECT entity_id FROM read_vortex('{path}') WHERE concept_id={b} ORDER BY 1").fetchall()]
tdi = time.time() - t
t = time.time(); pr = rb[a] & rb[b]; tp = time.time() - t
print(f"intersection of two largest cells: duckdb {len(inter):,} ids {tdi*1000:.1f} ms | pyroaring {len(pr):,} ids {tp*1000:.3f} ms | equal: {sorted(pr) == inter}")
w = con.execute(f"COPY (SELECT * FROM read_vortex('{path}')) TO '{D}/cells_duck.vortex' (FORMAT vortex)")
print("duckdb COPY TO vortex:", os.path.getsize(f"{D}/cells_duck.vortex"), "B; re-read equal:",
      con.execute(f"SELECT count(*) FROM (SELECT * FROM read_vortex('{D}/cells_duck.vortex') EXCEPT SELECT * FROM read_vortex('{path}'))").fetchone()[0] == 0)
