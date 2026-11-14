"""task-29.4 r2: draft census for the budget-outcome clause (bug-228's shape). Static.
A test function is a hit when it (a) uses a real daemon or runs a hook/CLI child through one of
the real-daemon helpers and (b) asserts a comparison whose one side reads an `outcome` field and
whose other side is a string constant."""
import ast, sys, collections
from pathlib import Path
T = Path(sys.argv[1]) / "tests"
REAL = {"SandboxDaemon", "spawn_daemon_subprocess"}
hits = []; outcome_asserts = 0; fns_with_outcome = 0
for p in sorted(T.glob("test_*.py")):
    tree = ast.parse(p.read_text())
    # fixtures in this file that use a real daemon
    real_fixtures = set()
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and any(isinstance(x, ast.Name) and x.id in REAL or isinstance(x, ast.Attribute) and x.attr in REAL for x in ast.walk(n)):
            real_fixtures.add(n.name)
    for n in ast.walk(tree):
        if not (isinstance(n, ast.FunctionDef) and n.name.startswith("test_")): continue
        names = {x.id for x in ast.walk(n) if isinstance(x, ast.Name)} | {x.attr for x in ast.walk(n) if isinstance(x, ast.Attribute)}
        args = {a.arg for a in n.args.args}
        real = bool(names & REAL) or bool(args & real_fixtures) or bool(names & real_fixtures)
        vals = []
        for a in ast.walk(n):
            if not isinstance(a, ast.Assert): continue
            for c in ast.walk(a.test):
                if isinstance(c, ast.Compare) and len(c.ops) == 1 and isinstance(c.ops[0], (ast.Eq, ast.NotEq, ast.In)):
                    l, r = c.left, c.comparators[0]
                    for x, y in ((l, r), (r, l)):
                        if "outcome" in ast.unparse(x) and isinstance(y, ast.Constant) and isinstance(y.value, str):
                            vals.append(y.value)
        if vals:
            fns_with_outcome += 1; outcome_asserts += len(vals)
            if real: hits.append((p.name, n.name, sorted(set(vals))))
print("test functions that assert an `outcome` against a string:", fns_with_outcome, "(asserts:", outcome_asserts, ")")
print("... of which use a real daemon (SandboxDaemon / spawn_daemon_subprocess, directly or through a fixture in the file):", len(hits))
vc = collections.Counter(v for h in hits for v in h[2]); print("outcome values asserted in those:", dict(vc))
for h in hits: print("   ", h)
