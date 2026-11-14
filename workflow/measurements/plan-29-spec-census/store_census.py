import ast, sys, re, collections, json
from pathlib import Path
REPO = Path(sys.argv[1])
for mod in ("store", "daemon"):
    P = REPO/f"src/refmatrix/{mod}.py"; src = P.read_text(); tree = ast.parse(src)
    print(f"== {mod}.py lines {src.count(chr(10))}; top-level statements {len(tree.body)}")
    prev = 0; kinds = collections.Counter(); klines = collections.Counter()
    for n in tree.body:
        k = type(n).__name__; kinds[k] += 1; klines[k] += n.end_lineno - prev; 
        if isinstance(n, ast.ClassDef):
            meths = [m for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            print(f"   class {n.name}: lines {n.end_lineno - n.lineno + 1} (L{n.lineno}-{n.end_lineno}), methods {len(meths)}, private methods {sum(1 for m in meths if m.name.startswith('_') and not m.name.startswith('__'))}")
        prev = n.end_lineno
    print("   kinds:", dict(kinds), "| lines by kind:", dict(klines))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    print("   top-level functions:", len(fns), "private:", sum(1 for f in fns if f.name.startswith("_")), "| _op_* functions:", sum(1 for f in fns if f.name.startswith("_op_")), "lines", sum(f.end_lineno - f.lineno + 1 for f in fns if f.name.startswith("_op_")))
P = REPO/"src/refmatrix/store.py"; src = P.read_text(); tree = ast.parse(src); lines = src.splitlines()
store = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Store")
# section banner comments inside the class: lines like `    # ---- xyz ----` / `    # ==== ... ====`
banners = [(i + 1, l.strip()) for i, l in enumerate(lines[store.lineno - 1: store.end_lineno], start=store.lineno - 1) if re.match(r"\s{4}# ?[-=─]{3,}", l)]
print("Store banner comments:", len(banners))
meths = [m for m in store.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
CONCERN = [
 ("memory",   r"memory|subject|mtype|intuition|forget_memor|recall"),
 ("vectors",  r"vector|lance|embed|dense|ann\b|_ann|rerank"),
 ("fragments",r"fragment|bitmap|roaring|_bm\b|cell|linkage_bits|set_bit|clear_bit|link\b|unlink|_frag"),
 ("slots",    r"slot|snapshot|replica|checkpoint|compact|export|import_|migrate|wal|_open|close|reopen|attach|active|init\b|_connect|catalog|lock|tracked"),
 ("log",      r"facts|log|replay|rebuild|dump"),
 ("partition",r"partition"),
 ("entities", r"entity|entities|concept|linkage|purge|noise|protect|same_as|alias|variant|weight|pagerank|stats|query|saved"),
]
agg = collections.Counter(); cnt = collections.Counter()
for m in meths:
    L = m.end_lineno - m.lineno + 1
    for name, pat in CONCERN:
        if re.search(pat, m.name): agg[name] += L; cnt[name] += 1; break
    else: agg["other"] += L; cnt["other"] += 1
print("Store methods by NAME-regex concern (first match; a rough cut, R0 re-cuts by call graph):")
for k, v in agg.most_common(): print(f"   {k:10s} methods={cnt[k]:4d} lines={v:5d}")
big = sorted(((m.end_lineno - m.lineno + 1, m.name) for m in meths), reverse=True)[:10]
print("largest Store methods:", big)
top = [(n.name, n.end_lineno - n.lineno + 1) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name != "Store"]
print("non-Store top-level defs:", len(top), "lines", sum(l for _, l in top), "| largest:", sorted(top, key=lambda x: -x[1])[:10])
