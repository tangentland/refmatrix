import os, sys, tempfile, itertools
from pathlib import Path
from refmatrix import memory_layout as ml
d = Path(tempfile.mkdtemp(dir=sys.argv[1]))
def mk(name, upd, mtime):
    p = d / name
    p.write_text(f'---\ngmd: "0.1"\nid: {name[:-3]}\ntitle: t\nmetadata:\n  type: session/recall-state\n  updated: {upd}\n---\n# t {{#root}}\n')
    os.utime(p, (mtime, mtime)); return p
A = mk("savestate_a.md", "2026-11-09T12:00:00-08:00", 1000)
C = mk("savestate_c.md", "2026-11-09T10:00:00-08:00", 3000)
B = mk("savestate_b.md", "2026-11-09", 2000)
res = set()
for perm in itertools.permutations([A, B, C]):
    res.add(ml.sort_savestates(list(perm))[0].name)
print("newest across input orders:", sorted(res))
print("iter_savestates:", [p.name for p in ml.iter_savestates(d)])
