import os, sys, tempfile, itertools, random
from pathlib import Path
from refmatrix import memory_layout as ml
base = Path(tempfile.mkdtemp(dir=sys.argv[1]))
d = base
def mk(name, upd, mtime, sub=None):
    dd = d / sub if sub else d; dd.mkdir(exist_ok=True)
    p = dd / name
    fm = f"  updated: {upd}\n" if upd else ""
    p.write_text(f'---\ngmd: "0.1"\nid: {name[:-3]}\ntitle: t\nmetadata:\n  type: session/recall-state\n{fm}---\n# t {{#root}}\n')
    os.utime(p, (mtime, mtime)); return p
A = mk("savestate_a.md", "2026-11-09T12:00:00-08:00", 1762700000)
C = mk("savestate_c.md", "2026-11-09T10:00:00-08:00", 1762710000)
B = mk("savestate_b.md", "2026-11-09", 1762705000)
res = {ml.sort_savestates(list(p))[0].name for p in itertools.permutations([A, B, C])}
print("3-cycle newest across 6 orders:", sorted(res))
# random fuzz: 200 trials x 7 files, mixed tz/naive/date-only/absent/garbage, ties in mtime
random.seed(7); bad = 0
for t in range(200):
    d = Path(tempfile.mkdtemp(dir=base))
    ps = []
    for i in range(7):
        kind = random.choice(["aware", "naive", "date", "none", "garbage", "Z"])
        day = random.choice(["2026-11-08", "2026-11-09"])
        upd = {"aware": f"{day}T{random.randint(0,23):02d}:00:00+05:00", "naive": f"{day}T{random.randint(0,23):02d}:00:00",
               "date": day, "none": "", "garbage": "notadate", "Z": f"{day}T01:00:00Z"}[kind]
        ps.append(mk(f"savestate_{i}.md", upd, 1762700000 + random.choice([0, 0, 100, 200])))
    import contextlib, io
    with contextlib.redirect_stderr(io.StringIO()):
        orders = {tuple(x.name for x in ml.sort_savestates(random.sample(ps, len(ps)))) for _ in range(30)}
    bad += len(orders) != 1
print("fuzz trials with input-order-dependent result:", bad, "/ 200")
# same name in savestates/ and top level, same mtime
d = Path(tempfile.mkdtemp(dir=base))
x1 = mk("savestate_x.md", "2026-11-09", 1762700000); x2 = mk("savestate_x.md", "2026-11-09", 1762700000, sub="savestates")
print("dup-name tie:", {str(ml.sort_savestates(list(p))[0].relative_to(d)) for p in itertools.permutations([x1, x2])})
