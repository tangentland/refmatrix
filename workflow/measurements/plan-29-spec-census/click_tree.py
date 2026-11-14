"""Introspect the REAL click tree (import only; no command runs, no store opened)."""
import ast, sys, json, collections, inspect, hashlib
from pathlib import Path
import click
import refmatrix.cli as cli
P = Path(cli.__file__)
assert Path(sys.argv[1]).resolve() in P.resolve().parents, f"refmatrix.cli imported from {P}; set PYTHONPATH=<checkout>/src"
src = P.read_text(); tree = ast.parse(src)
span = {}; prev = 0
for n in tree.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): span[n.name] = (prev + 1, n.end_lineno)
    prev = n.end_lineno
def unwrap(f):
    while hasattr(f, "__wrapped__"): f = f.__wrapped__
    return f
rows = []
def walk(grp, path):
    for name, c in sorted(grp.commands.items()):
        cb = unwrap(c.callback) if c.callback else None
        fn = cb.__name__ if cb else None
        mod = cb.__module__ if cb else None
        s, e = span.get(fn, (0, -1)) if mod == "refmatrix.cli" else (0, -1)
        rows.append(dict(path=" ".join(path + [name]), group=isinstance(c, click.Group), hidden=bool(c.hidden), fn=fn, mod=mod, lines=e - s + 1, params=len(c.params)))
        if isinstance(c, click.Group): walk(c, path + [name])
walk(cli.main, [])
vis = [r for r in rows if not r["hidden"]]
print("commands+groups in the tree:", len(rows), "| visible:", len(vis), "| hidden aliases:", len(rows) - len(vis), "| groups:", sum(r["group"] for r in rows), "| params:", sum(r["params"] for r in rows))
print("callbacks defined outside refmatrix.cli:", collections.Counter(r["mod"] for r in rows if r["mod"] != "refmatrix.cli"))
# hidden aliases share a callback with a visible command: count distinct callbacks
fns = {}
for r in rows:
    if r["mod"] == "refmatrix.cli": fns.setdefault(r["fn"], r)
top = collections.defaultdict(lambda: dict(n=0, hidden=0, lines=0, fns=set()))
for r in rows:
    parts = r["path"].split()
    key = parts[0] if (len(parts) > 1 or r["group"]) else "(top-level)"
    t = top[key]; t["n"] += 1; t["hidden"] += r["hidden"]
    if r["fn"] and r["fn"] not in t["fns"] and r["mod"] == "refmatrix.cli":
        t["fns"].add(r["fn"]); t["lines"] += r["lines"]
print("\ntop-level name: entries (hidden) / callback lines")
for k, t in sorted(top.items(), key=lambda kv: -kv[1]["lines"]):
    print(f"  {k:18s} {t['n']:3d} ({t['hidden']:2d})  {t['lines']:5d}")
tl = [r for r in rows if len(r["path"].split()) == 1 and not r["group"] and not r["hidden"]]
print("\nvisible top-level commands:", len(tl))
print("  " + ", ".join(f"{r['path']}:{r['lines']}" for r in sorted(tl, key=lambda r: -r["lines"])))
htl = [r for r in rows if len(r["path"].split()) == 1 and r["hidden"]]
print("hidden top-level aliases:", len(htl), ", ".join(r["path"] for r in htl))
cmd_fns = set(fns)
helpers = {n: se for n, se in span.items() if n not in cmd_fns}
print("\ncallback defs:", len(cmd_fns), "lines", sum(span[f][1] - span[f][0] + 1 for f in cmd_fns), "| non-callback top-level defs/classes:", len(helpers), "lines", sum(e - s + 1 for s, e in helpers.values()))
json.dump(dict(rows=rows, span=span), open("clicktree.json", "w"))
# a tree fingerprint of the kind the spec asks 29.5 to pin
def sig(c, path):
    d = dict(path=path, type=type(c).__name__, help=c.help, short_help=c.short_help, epilog=c.epilog, hidden=c.hidden, deprecated=bool(c.deprecated),
             context_settings=repr(sorted((c.context_settings or {}).items())),
             params=[dict(name=p.name, opts=p.opts, secondary=p.secondary_opts, kind=type(p).__name__, type=repr(p.type), required=p.required, default=repr(p.default) if not callable(p.default) else "<callable>", nargs=p.nargs, multiple=getattr(p, "multiple", None), is_flag=getattr(p, "is_flag", None), help=getattr(p, "help", None), envvar=p.envvar, hidden=getattr(p, "hidden", None)) for p in c.params])
    out = [d]
    if isinstance(c, click.Group):
        for n, s in sorted(c.commands.items()): out += sig(s, path + [n])
    return out
blob = json.dumps(sig(cli.main, ["rmx"]), sort_keys=True, indent=0, default=repr)
print("tree dump bytes:", len(blob), "sha256:", hashlib.sha256(blob.encode()).hexdigest()[:16])
