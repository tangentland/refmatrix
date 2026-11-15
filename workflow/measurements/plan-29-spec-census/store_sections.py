"""Store methods per section banner in store.py, with line counts. Static."""
import ast, re, sys
from pathlib import Path
P = Path(sys.argv[1]) / "src/refmatrix/store.py"; src = P.read_text(); lines = src.splitlines()
tree = ast.parse(src); store = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Store")
banners = [(i + 1, re.sub(r"[-=─#]+", "", l).strip()) for i, l in enumerate(lines) if store.lineno <= i + 1 <= store.end_lineno and re.match(r"\s{4}# ?[-=─]{3,}", l)]
banners = [(store.lineno, "(class header, __init__)")] + banners + [(store.end_lineno + 1, None)]
meths = [m for m in store.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
for (start, name), (end, _) in zip(banners, banners[1:]):
    ms = [m for m in meths if start <= m.lineno < end]
    print(f"\n## {name}: L{start}-{end - 1} ({end - start} lines, {len(ms)} methods)")
    print("   " + ", ".join(f"{m.name}:{m.end_lineno - m.lineno + 1}" for m in ms))
