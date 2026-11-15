"""Cross-module private (`_name`) uses and test patch targets, for the 29.5 spec. Static."""
import ast, sys, re, json, collections
from pathlib import Path
REPO = Path(sys.argv[1]); S = REPO/"src/refmatrix"; T = REPO/"tests"
mods = {p.stem for p in S.glob("*.py")}
def scan(path, own):
    src = path.read_text(); tree = ast.parse(src)
    alias = {}                       # local name -> refmatrix module
    imp = []                         # (target module, name, line) for from-imports of names
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            base = None
            if n.module == "refmatrix" or (n.level and not n.module and path.parent == S):
                for a in n.names:
                    if a.name in mods: alias[a.asname or a.name] = a.name
                continue
            if n.module and n.module.startswith("refmatrix."): base = n.module.split(".")[1]
            elif n.level and n.module and path.parent == S: base = n.module.split(".")[0]
            if base in mods:
                for a in n.names: imp.append((base, a.name, n.lineno))
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("refmatrix.") and a.name.split(".")[1] in mods:
                    alias[a.asname or a.name] = a.name.split(".")[1]
    attr = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias:
            attr.append((alias[n.value.id], n.attr, n.lineno))
        # refmatrix.X._name dotted
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute) and isinstance(n.value.value, ast.Name) and n.value.value.id == "refmatrix" and n.value.attr in mods:
            attr.append((n.value.attr, n.attr, n.lineno))
    patches = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("setattr", "delattr", "object", "patch"):
            a = n.args
            if len(a) >= 2 and isinstance(a[0], ast.Name) and a[0].id in alias and isinstance(a[1], ast.Constant) and isinstance(a[1].value, str):
                patches.append((alias[a[0].id], a[1].value, n.lineno))
            elif a and isinstance(a[0], ast.Constant) and isinstance(a[0].value, str):
                m = re.match(r"refmatrix\.(\w+)\.(\w+)$", a[0].value)
                if m and m.group(1) in mods: patches.append((m.group(1), m.group(2), n.lineno))
    return [(t, nm, ln) for t, nm, ln in imp + attr if t != own], [(t, nm, ln) for t, nm, ln in patches if t != own]
def report(label, files, own_of):
    uses = []; patches = []
    for p in files:
        u, pt = scan(p, own_of(p)); uses += [(p.name, *x) for x in u]; patches += [(p.name, *x) for x in pt]
    priv = [u for u in uses if u[2].startswith("_") and not u[2].startswith("__")]
    by = collections.Counter(u[1] for u in priv); distinct = collections.defaultdict(set)
    for u in priv: distinct[u[1]].add(u[2])
    print(f"\n== {label}: private cross-module uses: {len(priv)} sites, {sum(len(v) for v in distinct.values())} distinct (module, name) pairs, in {len({u[0] for u in priv})} files")
    for m, c in by.most_common(12): print(f"   -> {m:14s} sites={c:4d} distinct names={len(distinct[m])}")
    if patches:
        pb = collections.Counter(p[1] for p in patches); pd = collections.defaultdict(set)
        for p in patches: pd[p[1]].add(p[2])
        print(f"   patch sites (setattr/patch on a refmatrix module attr): {len(patches)} sites in {len({p[0] for p in patches})} files")
        for m, c in pb.most_common(8): print(f"   -> patch {m:12s} sites={c:4d} distinct names={len(pd[m])} (private: {sum(1 for x in pd[m] if x.startswith('_'))})  top: {collections.Counter(p[2] for p in patches if p[1]==m).most_common(6)}")
    return priv, patches, distinct
sp, _, sd = report("src -> src", sorted(S.glob("*.py")), lambda p: p.stem)
print("   src files importing private names FROM cli:", sorted({(u[0], u[2]) for u in sp if u[1] == "cli"}))
print("   src private names taken FROM store:", sorted(sd["store"]))
tp, tpat, td = report("tests -> src", sorted(T.glob("*.py")), lambda p: None)
json.dump(dict(src=sp, tests=tp, patches=tpat), open("private.json", "w"))
