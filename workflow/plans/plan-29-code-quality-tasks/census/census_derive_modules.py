"""The derive-hash modules and what tasks 29.2 / 29.3 would touch in them -- the specs'
measurement, run at the commit it names. Read-only AST; imports nothing from refmatrix.

Usage: python3 census_derive_modules.py <src/refmatrix>

Reads `_DERIVE_CODE_MODULES` (the no-argument union) and `_DERIVE_PASS_MODULES` (pass -> files)
from whichever module assigns them, so the list comes from the tables and not from prose. For
every file named in either table it prints: the passes whose hash it feeds, and its broad-except
classes by census_broad_except.py's rule (silent = commented + bare), because slice 29.3(c) edits
every silent handler.
"""
from __future__ import annotations

import ast
import collections
import importlib.util
import pathlib
import sys


def main(argv: list[str]) -> int:
    src = pathlib.Path(argv[1])
    spec = importlib.util.spec_from_file_location(
        "c", pathlib.Path(__file__).with_name("census_broad_except.py"))
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    union: list[str] = []
    passes: dict[str, list[str]] = {}
    where = ""
    for p in sorted(src.rglob("*.py")):
        for n in ast.parse(p.read_text()).body:
            tgt = None
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                tgt, val = n.targets[0].id, n.value
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
                tgt, val = n.target.id, n.value
            if tgt == "_DERIVE_CODE_MODULES":
                union = [e.value for e in val.elts]
                where = p.relative_to(src).as_posix()
            elif tgt == "_DERIVE_PASS_MODULES":
                for k, v in zip(val.keys, val.values):
                    passes[ast.unparse(k).strip("'\"")] = [e.value for e in v.elts]
    feeds: dict[str, list[str]] = collections.defaultdict(list)
    for name, files in passes.items():
        for f in files:
            feeds[f].append(name)
    files = sorted(set(union) | set(feeds))
    print(f"tables read from {where}: union {union}; {len(passes)} passes; {len(files)} files")
    tot = collections.Counter()
    for f in files:
        p = src / f
        if not p.exists():
            print(f"  {f:20} MISSING ON DISK")
            continue
        lines = p.read_text().splitlines()
        cls = collections.Counter(c.classify(h, lines) for h in ast.walk(ast.parse("\n".join(lines)))
                                  if isinstance(h, ast.ExceptHandler) and c.broad(h))
        silent = cls["silent(commented)"] + cls["silent(bare)"]
        tot["silent"] += silent
        if feeds.get(f):
            tot["silent_pass"] += silent
        print(f"  {f:20} union={'yes' if f in union else 'no ':3} passes={','.join(feeds.get(f, [])) or '-':44} "
              f"broad={sum(cls.values()):3} silent={silent:3}")
    print(f"silent handlers in files that feed a pass hash: {tot['silent_pass']}; "
          f"in all derive files: {tot['silent']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
