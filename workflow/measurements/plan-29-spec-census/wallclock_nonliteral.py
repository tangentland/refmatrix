import ast, re, sys, collections
from pathlib import Path
T = Path(sys.argv[1]) / "tests"
TIME = {"time", "monotonic", "perf_counter"}
NAME = re.compile(r"^(elapsed|took|wall|dt|duration|dur|secs|seconds|spent|waited|latency|lat|wall_s|elapsed_s|took_s)\d*$", re.I)
def tcall(n): return isinstance(n, ast.Call) and ((isinstance(n.func, ast.Attribute) and n.func.attr in TIME) or (isinstance(n.func, ast.Name) and n.func.id in TIME))
def clockdiff(n): return any(isinstance(s, ast.BinOp) and isinstance(s.op, ast.Sub) and tcall(s.left) for s in ast.walk(n))
def num(n): return isinstance(n, ast.Constant) and type(n.value) in (int, float)
lit = []; nonlit = []; lower = []
for p in sorted(T.glob("*.py")):
    src = p.read_text(); tree = ast.parse(src)
    bound = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and clockdiff(n.value):
            for t in n.targets:
                for s in ast.walk(t):
                    if isinstance(s, ast.Name): bound.add(s.id)
    def timey(e):
        names = {s.id for s in ast.walk(e) if isinstance(s, ast.Name)}
        return clockdiff(e) or bool(names & bound) or any(NAME.match(x) for x in names)
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assert): continue
        for c in ast.walk(n.test):
            if not isinstance(c, ast.Compare): continue
            parts = [c.left] + c.comparators
            for i, op in enumerate(c.ops):
                l, r = parts[i], parts[i + 1]
                if isinstance(op, (ast.Lt, ast.LtE)): subj, lim = l, r
                elif isinstance(op, (ast.Gt, ast.GtE)): subj, lim = r, l
                else: continue
                if timey(subj) and not timey(lim):
                    (lit if num(lim) else nonlit).append((p.name, n.lineno, ast.unparse(c)[:90]))
                elif timey(lim) and not timey(subj):
                    lower.append((p.name, n.lineno, ast.unparse(c)[:90]))
lit = sorted(set(lit)); nonlit = sorted(set(nonlit)); lower = sorted(set(lower))
print("upper bound, numeric literal:", len(lit), "in", len({x[0] for x in lit}), "files")
print("upper bound, NON-literal limit (a named constant or expression):", len(nonlit), "in", len({x[0] for x in nonlit}), "files")
for x in nonlit: print("   ", x)
print("LOWER bounds on elapsed (it waited at least N):", len(lower), "in", len({x[0] for x in lower}), "files")
for x in lower[:12]: print("   ", x)
