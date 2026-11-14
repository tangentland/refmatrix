"""Public-API annotation census for task 29.2 -- the spec's measurement, run at the commit it names.

Usage: python3 census_public_annotations.py <module.py> [<module.py> ...] [--list]

PUBLIC: a module-level function whose name does not start with `_`, or a method of a module-level
class whose name does not start with `_`, the method's own name not starting with `_` (dunder
methods of a public class count as public: `__init__` is the constructor's signature).
FULLY ANNOTATED: a return annotation and an annotation on every parameter except `self`/`cls`.
`--list` prints each public def that is not fully annotated.
"""
from __future__ import annotations

import ast
import pathlib
import sys


def full(f: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    a = f.args
    params = a.posonlyargs + a.args + a.kwonlyargs
    params += [p for p in (a.vararg, a.kwarg) if p is not None]
    params = [p for p in params if p.arg not in ("self", "cls")]
    return f.returns is not None and all(p.annotation is not None for p in params)


def defs(tree: ast.Module):
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n, None
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield m, n.name


def is_public(name: str, cls: str | None) -> bool:
    if cls is None:
        return not name.startswith("_")
    if cls.startswith("_"):
        return False
    if name.startswith("__") and name.endswith("__"):
        return True
    return not name.startswith("_")


def main(argv: list[str]) -> int:
    paths = [a for a in argv[1:] if a != "--list"]
    show = "--list" in argv
    tp = tf = 0
    for p in paths:
        tree = ast.parse(pathlib.Path(p).read_text())
        pub = fully = 0
        for f, cls in defs(tree):
            if is_public(f.name, cls):
                pub += 1
                ok = full(f)
                fully += ok
                if show and not ok:
                    q = f"{cls}.{f.name}" if cls else f.name
                    print(f"  {pathlib.Path(p).name}:{f.lineno} {q}")
        tp += pub
        tf += fully
        print(f"{pathlib.Path(p).name}: public={pub} fully_annotated={fully} missing={pub - fully}")
    print(f"TOTAL: public={tp} fully_annotated={tf} missing={tp - tf}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
