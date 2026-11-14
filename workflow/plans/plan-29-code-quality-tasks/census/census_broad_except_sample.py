"""Print K random handlers per class for a hand check of the classifier (task 29.3c).
Uses the SAME classifier as census_broad_except.py (imported from the sibling file).

Usage: python3 census_broad_except_sample.py <src/refmatrix> <seed> <k>
The spec's precision check: seed 29 k 8 (every class), then seed 7 k 22 (the silent(bare) class).
"""
import ast, sys, pathlib, random, importlib.util
spec = importlib.util.spec_from_file_location("c", pathlib.Path(__file__).with_name("census_broad_except.py")); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
root = pathlib.Path(sys.argv[1]); random.seed(int(sys.argv[2])); k = int(sys.argv[3])
by = {}
for p in sorted(root.rglob("*.py")):
    lines = p.read_text().splitlines()
    for h in ast.walk(ast.parse("\n".join(lines))):
        if isinstance(h, ast.ExceptHandler) and c.broad(h):
            by.setdefault(c.classify(h, lines), []).append((p.relative_to(root).as_posix(), h, lines))
for cls in sorted(by):
    print(f"##### {cls} ({len(by[cls])})")
    for rel, h, lines in random.sample(by[cls], min(k, len(by[cls]))):
        end = min(h.end_lineno, h.lineno + 5)
        print(f"--- {rel}:{h.lineno}")
        print("\n".join(lines[h.lineno - 2:end]))
