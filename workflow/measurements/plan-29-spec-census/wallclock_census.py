"""Union census: an `assert` with a numeric-literal UPPER bound on (a) a clock difference,
(b) a name bound from a clock difference in the same file, or (c) an elapsed-like NAME."""
import ast, re, sys, collections
from pathlib import Path
T = Path(sys.argv[1]) / "tests"
TIME = {"time", "monotonic", "perf_counter"}
NAME = re.compile(r"^(elapsed|took|wall|dt|duration|dur|secs|seconds|spent|waited|latency|lat|ms|wall_s|elapsed_s|took_s)\d*$", re.I)
def tcall(n): return isinstance(n, ast.Call) and ((isinstance(n.func, ast.Attribute) and n.func.attr in TIME) or (isinstance(n.func, ast.Name) and n.func.id in TIME))
def clockdiff(n): return any(isinstance(s, ast.BinOp) and isinstance(s.op, ast.Sub) and (tcall(s.left)) for s in ast.walk(n))
def num(n): return isinstance(n, ast.Constant) and type(n.value) in (int, float)
rows = []; kinds = collections.Counter()
for p in sorted(T.glob("*.py")):
    tree = ast.parse(p.read_text())
    bound = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and clockdiff(n.value):
            for t in n.targets:
                for s in ast.walk(t):
                    if isinstance(s, ast.Name): bound.add(s.id)
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assert): continue
        for c in ast.walk(n.test):
            if not isinstance(c, ast.Compare): continue
            parts = [c.left] + c.comparators
            for i, op in enumerate(c.ops):
                l, r = parts[i], parts[i + 1]
                if isinstance(op, (ast.Lt, ast.LtE)) and num(r): subj, lim = l, r.value
                elif isinstance(op, (ast.Gt, ast.GtE)) and num(l): subj, lim = r, l.value
                else: continue
                names = {s.id for s in ast.walk(subj) if isinstance(s, ast.Name)}
                if clockdiff(subj): k = "clockdiff"
                elif names & bound: k = "bound-name"
                elif any(NAME.match(x) for x in names): k = "elapsed-name"
                else: continue
                rows.append((p.name, n.lineno, lim, k)); kinds[k] += 1
rows = sorted(set(rows))
files = collections.Counter(r[0] for r in rows)
print(f"{len(rows)} wall-clock upper-bound asserts in {len(files)} files; by kind {dict(kinds)}")
lims = collections.Counter("<=1s" if r[2] <= 1 else "1-5s" if r[2] <= 5 else "5-20s" if r[2] <= 20 else ">20s" for r in rows)
print("by bound:", dict(lims))
for f, c in sorted(files.items()):
    print(f"{c:3d} {f}: " + ", ".join(f"L{r[1]}<{r[2]}" for r in rows if r[0] == f))
