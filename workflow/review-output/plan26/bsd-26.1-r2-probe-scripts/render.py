"""usage: render.py <memdir> <n_renders> [marker]  -- run with PYTHONPATH=<tree>/src"""
import io, json, sys
from pathlib import Path
from refmatrix import memory_index as mi
md = Path(sys.argv[1]); n = int(sys.argv[2]); marker = len(sys.argv) > 3
if marker:
    (md / ".memory-layout").write_text(json.dumps({"layout": 1}))
print("module", mi.__file__)
for i in range(1, n + 1):
    buf = io.StringIO()
    mi.write(md, out=buf)
    t = (md / "MEMORY.md").read_text()
    lines = t.splitlines()
    linkless = [l for l in lines if l.startswith("- [") and "](" not in l]
    over = [l for l in lines if len(l) > 200]
    print(f"render {i}: {len(lines)} lines {len(t)} chars linkless={len(linkless)} >200={len(over)} check={mi.check(md)}")
    for l in buf.getvalue().splitlines():
        print("   ", l[:300])
