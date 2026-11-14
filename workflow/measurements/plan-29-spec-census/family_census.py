import ast, sys, json, collections, re
from pathlib import Path
REPO = Path(sys.argv[1]); S = REPO/"src"/"refmatrix"; T = REPO/"tests"
mods = {p.stem: p for p in S.glob("*.py")}
def imports(path, toplevel_only=False):
    tree = ast.parse(path.read_text()); out = set()
    nodes = tree.body if toplevel_only else ast.walk(tree)
    for n in (ast.walk(tree) if not toplevel_only else tree.body):
        if isinstance(n, ast.ImportFrom):
            if n.level and path.parent == S:      # relative import inside the package
                if n.module: out.add(n.module.split(".")[0])
                else: out |= {a.name for a in n.names}
            elif n.module == "refmatrix": out |= {a.name for a in n.names}
            elif n.module and n.module.startswith("refmatrix."): out.add(n.module.split(".")[1])
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("refmatrix."): out.add(a.name.split(".")[1])
    return {m for m in out if m in mods}
g = {m: imports(p) - {m} for m, p in mods.items()}          # m imports g[m] (lazy imports included)
rev = collections.defaultdict(set)
for m, ds in g.items():
    for d in ds: rev[d].add(m)
def rclosure(m):
    seen = {m}; todo = [m]
    while todo:
        for r in rev[todo.pop()]:
            if r not in seen: seen.add(r); todo.append(r)
    return seen
helpers = {p.stem: p for p in T.glob("*.py") if not p.name.startswith("test_")}
timp = {}
for p in sorted(T.glob("test_*.py")):
    im = imports(p)
    # through tests/ helpers
    src = p.read_text()
    for h, hp in helpers.items():
        if re.search(r"\btests(\.|\s+import\s+.*\b)%s\b" % h, src) or re.search(r"from tests import [^\n]*\b%s\b" % h, src):
            im |= imports(hp)
    timp[p.name] = im
subproc_cli = [n for n in timp if re.search(r"sys\.executable|[\"']rmx[\"']|\.venv-eval|-m[\"'],\s*[\"']refmatrix|generated_cmd|run_hook", (T/n).read_text())]
noimp = [n for n in timp if not timp[n]]
print("src modules:", len(mods), "| test files:", len(timp), "| test files importing no refmatrix module (direct or via a tests/ helper):", len(noimp))
print("test files that run the CLI/hooks in a child process (no import edge to what the child loads):", len(subproc_cli))
print(f"{'module':16s} {'lines':>6s} {'direct':>7s} {'depth1':>7s} {'closure':>8s}  rev-importers(src)")
rows = []
for m in sorted(mods):
    direct = {t for t, im in timp.items() if m in im}
    d1 = {t for t, im in timp.items() if im & (rev[m] | {m})}
    cl = rclosure(m); full = {t for t, im in timp.items() if im & cl}
    rows.append((m, mods[m].read_text().count("\n"), len(direct), len(d1), len(full), len(rev[m])))
for r in sorted(rows, key=lambda r: -r[2])[:22]:
    print(f"{r[0]:16s} {r[1]:6d} {r[2]:7d} {r[3]:7d} {r[4]:8d}  {r[5]}")
import statistics
print("median direct family:", statistics.median(r[2] for r in rows), "| median closure family:", statistics.median(r[4] for r in rows), "| modules with 0 direct test importers:", sorted(r[0] for r in rows if r[2] == 0))
print("modules whose closure family is >= 300 of 357 files:", sum(1 for r in rows if r[4] >= 300), "of", len(rows))
for m in ("handoff", "query", "stm", "hooks", "sync", "search_hooks", "vectors", "memory_index"):
    r = next(x for x in rows if x[0] == m); print(" ", m, "direct", r[2], "depth1", r[3], "closure", r[4])
json.dump({"graph": {k: sorted(v) for k, v in g.items()}, "tests": {k: sorted(v) for k, v in timp.items()}}, open("family.json", "w"))
