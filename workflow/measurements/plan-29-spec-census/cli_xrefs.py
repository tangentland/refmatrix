"""task-29.5 r2 census: (1) what the body of each engine-called cli function reads; (2) references
between proposed command modules, with local-scope analysis; (3) `global` statements by AST;
(4) real `-m refmatrix.cli` spawn sites (string constants inside a list/tuple or a call). Static."""
import ast, json, sys, collections
from pathlib import Path
R = Path(sys.argv[1]); P = R / "src/refmatrix/cli.py"; src = P.read_text(); tree = ast.parse(src)
assign = json.load(open(sys.argv[2])); patched = set(sys.argv[3].split(","))
defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
modlevel = set(defs)
for n in tree.body:
    if isinstance(n, (ast.Assign, ast.AnnAssign)):
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
            for s in ast.walk(t):
                if isinstance(s, ast.Name): modlevel.add(s.id)

def bound_names(fn):
    """names bound inside fn (params, assignments, for/with/except targets, imports, nested defs, comprehensions)"""
    b = set()
    a = fn.args if hasattr(fn, "args") else None
    if a:
        for x in a.posonlyargs + a.args + a.kwonlyargs: b.add(x.arg)
        if a.vararg: b.add(a.vararg.arg)
        if a.kwarg: b.add(a.kwarg.arg)
    glob = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Global): glob |= set(n.names)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)): b.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names: b.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not fn: b.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name: b.add(n.name)
        elif isinstance(n, ast.arg): b.add(n.arg)
    return b - glob
def free_loads(fn):
    b = bound_names(fn)
    return {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in b}

print("== (1) engine-called cli functions: module-level cli names each body reads, and which are test-patched")
for f in ("_subject_upsert", "_subject_link", "_sync_memory_dir", "_root_from_projects_slug"):
    fl = sorted(free_loads(defs[f]) & modlevel)
    print(f"   {f} (-> {assign.get(f)}): reads {fl}\n      patched among them: {sorted(set(fl) & patched)}")
    # one level down: do the helpers it calls read patched names?
    deep = set()
    for h in fl:
        if h in defs and isinstance(defs[h], ast.FunctionDef): deep |= free_loads(defs[h]) & patched
    print(f"      patched names read one call down: {sorted(deep)}")

print("\n== (2) references between proposed command modules (free names only; locals excluded)")
edges = collections.Counter(); sites = []; shadow = 0
for name, node in defs.items():
    m = assign.get(name)
    if m in (None, "_core"): continue
    fl = free_loads(node) if not isinstance(node, ast.ClassDef) else set()
    allnames = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    shadow += len({x for x in (allnames - fl) if x in defs})
    for x in fl:
        tm = assign.get(x)
        if x in defs and tm not in (None, "_core", m):
            edges[(m, tm)] += 1; sites.append((name, m, x, tm))
print("   defs in command modules that load a NAME equal to a cli def but bound locally (must NOT be rewritten):", shadow)
print("   cross-command-module references:", len(sites), "from", len({s[0] for s in sites}), "defs")
for (a, b), c in sorted(edges.items(), key=lambda kv: -kv[1]): print(f"      {a} -> {b}: {c}")
for s in sorted(sites)[:40]: print("      ", s)
back = [(n, assign[n], x) for n, node in defs.items() if assign.get(n) == "_core" and not isinstance(node, ast.ClassDef) for x in free_loads(node) if x in defs and assign.get(x) not in (None, "_core")]
print("   core defs that reference a def the map moves OUT of the core:", len(back), sorted(back)[:20])

print("\n== (3) `global` statements in cli.py, by AST")
for n in ast.walk(tree):
    if isinstance(n, ast.Global): print("   line", n.lineno, n.names)

print("\n== (4) `-m refmatrix.cli` spawn sites in src (string constants in code, not comments/docstrings)")
for p in sorted((R / "src/refmatrix").rglob("*.py")):
    t = ast.parse(p.read_text())
    doc = {id(n.body[0].value) for n in ast.walk(t) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
    for n in ast.walk(t):
        if isinstance(n, ast.Constant) and n.value == "refmatrix.cli" and id(n) not in doc:
            print("   ", p.relative_to(R), n.lineno)
