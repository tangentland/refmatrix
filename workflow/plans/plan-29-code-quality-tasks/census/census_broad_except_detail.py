"""Detail tables for the broad-except census (task 29.3c): handler types, existing
`noqa: BLE001` use, what makes a handler `surfaced`, and the body shape of the silent ones.
Uses the SAME classifier as census_broad_except.py (imported from the sibling file).

Usage: python3 census_broad_except_detail.py <src/refmatrix>
"""
import ast, sys, pathlib, collections, importlib.util, re
spec = importlib.util.spec_from_file_location("c", pathlib.Path(__file__).with_name("census_broad_except.py")); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
root = pathlib.Path(sys.argv[1])
kinds = collections.Counter(); noqa = collections.Counter(); why = collections.Counter(); nameuse = collections.Counter()
bodyshape = collections.Counter(); carried = []
for p in sorted(root.rglob("*.py")):
    lines = p.read_text().splitlines(); rel = p.relative_to(root).as_posix()
    for h in ast.walk(ast.parse("\n".join(lines))):
        if not (isinstance(h, ast.ExceptHandler) and c.broad(h)): continue
        t = h.type
        kinds["bare" if t is None else ("tuple" if isinstance(t, ast.Tuple) else ast.unparse(t))] += 1
        cls = c.classify(h, lines)
        ln = lines[h.lineno - 1]
        if "noqa: BLE001" in ln:
            noqa[(cls, "reasoned" if c.JUSTIFY.search(ln) else "bare-noqa")] += 1
        nodes = list(c.body_nodes(h))
        if cls == "surfaced":
            byname = bool(h.name and any(isinstance(n, ast.Name) and n.id == h.name for n in nodes))
            bycall = False; bycount = False
            for n in nodes:
                if isinstance(n, ast.AugAssign) and c.COUNTER.search(ast.unparse(n.target)): bycount = True
                if isinstance(n, ast.Call):
                    nm = c.call_name(n); kw = {k.arg: k.value for k in n.keywords}
                    if nm in c.SURFACE_CALLS or (nm == "print" and "file" in kw) or (nm == "echo" and "err" in kw): bycall = True
            key = "+".join(k for k, v in (("name", byname), ("call", bycall), ("counter", bycount)) if v) or "other(console/stderr.write)"
            why[key] += 1
            if byname and not bycall and not bycount:
                # how is the name used?  inside any Call's args / f-string / return / subscript-assign / plain assign
                uses = set()
                for n in nodes:
                    if isinstance(n, ast.Call) and any(isinstance(m, ast.Name) and m.id == h.name for a in list(n.args) + [k.value for k in n.keywords] for m in ast.walk(a)):
                        uses.add("call-arg:" + c.call_name(n))
                    if isinstance(n, ast.Return) and n.value is not None and any(isinstance(m, ast.Name) and m.id == h.name for m in ast.walk(n.value)):
                        uses.add("return")
                    if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None and any(isinstance(m, ast.Name) and m.id == h.name for m in ast.walk(n.value)):
                        uses.add("assign")
                u = "return" if "return" in uses else ("call" if any(x.startswith("call-arg") for x in uses) else ("assign-only" if uses == {"assign"} else "other"))
                nameuse[u] += 1
                if u in ("assign-only", "other", "call"):
                    carried.append(f"{rel}:{h.lineno} [{u}] {sorted(uses)}")
        if cls.startswith("silent"):
            b = h.body
            if len(b) == 1 and isinstance(b[0], ast.Pass): s = "pass"
            elif len(b) == 1 and isinstance(b[0], ast.Continue): s = "continue"
            elif len(b) == 1 and isinstance(b[0], ast.Return): s = "return <default>"
            elif all(isinstance(x, ast.Assign) for x in b): s = "assign default(s)"
            else: s = "other"
            bodyshape[(cls, s)] += 1
print("handler type:", dict(kinds))
print("noqa BLE001 on the except line, by class:", {f"{k[0]}/{k[1]}": v for k, v in sorted(noqa.items())})
print("surfaced by:", dict(why))
print("surfaced by name-reference alone, use of the name:", dict(nameuse))
print("silent body shape:", {f"{k[0]}/{k[1]}": v for k, v in sorted(bodyshape.items())})
print("name-only surfaced, not a return:")
for x in carried: print("  ", x)
