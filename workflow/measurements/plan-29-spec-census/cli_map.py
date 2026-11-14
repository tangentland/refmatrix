"""Proposed command-group -> module map for 29.5, with measured line counts (static)."""
import ast, json, sys, collections
from pathlib import Path
P = Path(sys.argv[1])/"src/refmatrix/cli.py"
src = P.read_text(); tree = ast.parse(src)
ct = json.load(open("clicktree.json")); rows = ct["rows"]
MAP = {
 "memory_cmds":  ["memory", "taxonomy"],
 "session_cmds": ["focus", "session", "task", "save-state", "recall-state", "scan-prompt", "cctree"],
 "grep_cmds":    ["grep"],
 "search_cmds":  ["context", "recall", "locate"],
 "vectors_cmds": ["embed", "search-dense"],
 "catalog_cmds": ["partition", "replica", "derive", "repair-index", "compact", "compact-log", "rebuild", "checkpoint", "dump-log", "migrate-to-duckdb", "merge-verb-aliases"],
 "removal_cmds": ["forget", "untrack", "vacuum", "prune-noise", "noise", "unnoise", "protect", "unprotect", "audit-same-as"],
 "graph_cmds":   ["link", "unlink", "add", "add-concept", "add-entity", "add-linkage-type", "canon", "concept", "coref", "pairs"],
 "ingest_cmds":  ["ingest", "ingest-gmd", "ingest-status", "sync", "reingest", "tldr-warm", "graphify-warm", "init", "import", "export"],
 "daemon_cmds":  ["daemon", "queue", "watch", "log", "cli-log", "telemetry", "fingerprint"],
 "learn_cmds":   ["learn"],
 "hub_cmds":     ["hub", "bus", "schedule", "ui", "projects", "mcp", "curator", "refine"],
 "query_cmds":   ["query", "describe", "neighbors", "top", "co-occur", "stats", "info", "list", "list-entities", "list-linkages", "list-queries", "run", "save-query", "primer", "tools-primer", "pagerank"],
 "admin_cmds":   ["install-hooks", "upgrade", "version"],
}
where = {t: m for m, ts in MAP.items() for t in ts}
tops = {r["path"].split()[0] for r in rows}
missing = sorted(tops - set(where)); extra = sorted(set(where) - tops)
print("top-level names:", len(tops), "| unmapped:", missing, "| mapped but absent:", extra)
fn_mod = {}
for r in rows:
    if r["fn"]: fn_mod.setdefault(r["fn"], where[r["path"].split()[0]])
# spans (leading comments ride with the next stmt)
stmts = []; prev = 0
for n in tree.body:
    stmts.append((n, prev + 1, n.end_lineno)); prev = n.end_lineno
defs = {n.name: (n, s, e) for n, s, e in stmts if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
group_fns = {r["fn"] for r in rows if r["group"]}
def refs(node):
    return {x.id for x in ast.walk(node) if isinstance(x, ast.Name)} | {x.value.id for x in ast.walk(node) if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)}
uses = {name: refs(n) & set(defs) - {name} for name, (n, s, e) in defs.items()}
helpers = [h for h in defs if h not in fn_mod and h != "main"]
# iterate: a helper belongs to a module iff every def that uses it is in that one module; else _core
assign = dict(fn_mod); assign["main"] = "_core"
users = collections.defaultdict(set)
for name, us in uses.items():
    for u in us: users[u].add(name)
changed = True; rounds = 0
for h in helpers: assign[h] = None
while changed and rounds < 50:
    changed = False; rounds += 1
    for h in helpers:
        mods = {assign.get(u) for u in users[h] if u not in group_fns or True}
        mods.discard(None) if all(assign.get(u) is not None for u in users[h]) else None
        if not users[h]: new = "_core"
        elif None in mods: continue
        elif len(mods) == 1: new = next(iter(mods))
        else: new = "_core"
        if assign[h] != new: assign[h] = new; changed = True
for h in helpers:
    if assign[h] is None: assign[h] = "_core"        # mutually recursive leftovers
tot = collections.Counter(); cb = collections.Counter(); hp = collections.Counter(); nh = collections.Counter()
for name, (n, s, e) in defs.items():
    m = assign[name]; tot[m] += e - s + 1
    if name in fn_mod: cb[m] += e - s + 1
    else: hp[m] += e - s + 1; nh[m] += 1
other = sum(e - s + 1 for n, s, e in stmts if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
tot["_core"] += other
print(f"{'module':14s} {'lines':>6s} {'callbacks':>10s} {'helpers':>8s} {'n_helpers':>9s}  top-level names")
for m in ["_core"] + list(MAP):
    print(f"{m:14s} {tot[m]:6d} {cb[m]:10d} {hp[m]:8d} {nh[m]:9d}  {', '.join(MAP.get(m, ['main group, cli_entry, shared helpers, imports, constants']))}")
print("sum", sum(tot.values()), "of", src.count(chr(10)) + (0 if src.endswith(chr(10)) else 1), "| non-def top-level lines (to _core):", other)
core_h = sorted((defs[h][2] - defs[h][1] + 1, h, len({assign[u] for u in users[h]})) for h in helpers if assign[h] == "_core")
print("_core helpers:", len(core_h), "| used by >=2 command modules:", sum(1 for c in core_h if c[2] >= 2), "| with no user inside cli.py:", sum(1 for h in helpers if not users[h]))
print("largest _core helpers:", [(l, h) for l, h, _ in sorted(core_h, reverse=True)[:12]])
print("helpers with no in-file user:", sorted(h for h in helpers if not users[h]))
json.dump(assign, open("cli_assign.json", "w"))
