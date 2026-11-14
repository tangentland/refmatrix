"""`_DaemonWriter` vs `Store` surface census for task 29.2 -- the spec's measurement, run at the
commit it names. Read-only AST; imports nothing from refmatrix.

Usage: python3 census_writer_surface.py <src/refmatrix> [--list]

Finds the classes by NAME (`_DaemonWriter`, `Store`) in whichever module defines them, so it
gives the same answer after 29.5 moves them.

EXPLICIT PROXY METHOD: a public method defined on `_DaemonWriter` (a daemon op).
FALL-THROUGH: an attribute used on a WRITER-BOUND expression that `_DaemonWriter` does not
define; at run time `_DaemonWriter.__getattr__` hands it to the lock-free READER store (and
raises AttributeError for an underscored name).
WRITER-BOUND: `_store()` / `_store(write=True)` used directly as `_store().attr`, or a name
assigned from it (or bound by `with _store() as s`) inside the same function. `_store(write=False)`
and `_store(False)` are readers and are not counted. A writer passed to another function is NOT
followed (static limit; mypy over the Protocol is the complete answer, this is the estimate).
`--list` prints every fall-through use as `module:line function: name.attr`.
"""
from __future__ import annotations

import ast
import collections
import pathlib
import sys


def find_class(src: pathlib.Path, name: str) -> tuple[str, ast.ClassDef]:
    for p in sorted(src.rglob("*.py")):
        for n in ast.parse(p.read_text()).body:
            if isinstance(n, ast.ClassDef) and n.name == name:
                return p.relative_to(src).as_posix(), n
    raise SystemExit(f"class {name} not found under {src}")


def methods(c: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {m.name: m for m in c.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}


def sig(f: ast.FunctionDef) -> tuple[list[str], list[str], bool, bool]:
    a = f.args
    return ([p.arg for p in a.posonlyargs + a.args if p.arg != "self"],
            [p.arg for p in a.kwonlyargs], bool(a.vararg), bool(a.kwarg))


def is_writer_call(n: ast.AST) -> bool:
    if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_store"):
        return False
    for k in n.keywords:
        if k.arg == "write" and isinstance(k.value, ast.Constant) and k.value.value is False:
            return False
    if n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value is False:
        return False
    return True


def main(argv: list[str]) -> int:
    src = pathlib.Path(argv[1])
    show = "--list" in argv
    dw_mod, dw_cls = find_class(src, "_DaemonWriter")
    st_mod, st_cls = find_class(src, "Store")
    dw, st = methods(dw_cls), methods(st_cls)
    explicit = [m for m in dw if not m.startswith("_")]
    uses: list[tuple[str, int, str, str, str]] = []
    writer_calls = 0
    for p in sorted(src.rglob("*.py")):
        rel = p.relative_to(src).as_posix()
        tree = ast.parse(p.read_text())
        writer_calls += sum(1 for n in ast.walk(tree) if is_writer_call(n))
        seen: set[tuple[int, int]] = set()
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names: set[str] = set()
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign) and is_writer_call(n.value):
                    names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
                if isinstance(n, ast.With):
                    for it in n.items:
                        if is_writer_call(it.context_expr) and isinstance(it.optional_vars, ast.Name):
                            names.add(it.optional_vars.id)
            for n in ast.walk(fn):
                if not isinstance(n, ast.Attribute) or (n.lineno, n.col_offset) in seen:
                    continue
                if is_writer_call(n.value):
                    seen.add((n.lineno, n.col_offset))
                    uses.append((rel, n.lineno, fn.name, "_store()", n.attr))
                elif isinstance(n.value, ast.Name) and n.value.id in names:
                    seen.add((n.lineno, n.col_offset))
                    uses.append((rel, n.lineno, fn.name, n.value.id, n.attr))
    ex = set(explicit)
    routed = [u for u in uses if u[4] in ex]
    fall = [u for u in uses if u[4] not in ex]
    if show:
        for rel, line, fn, nm, attr in sorted(fall):
            print(f"{rel}:{line} {fn}: {nm}.{attr}")
        return 0
    print(f"_DaemonWriter defined in {dw_mod}; Store defined in {st_mod}")
    print(f"_store(...) writer call expressions in src: {writer_calls}")
    print(f"_DaemonWriter explicit public methods: {len(explicit)}; has __getattr__: {'__getattr__' in dw}")
    print(f"Store public methods: {len([m for m in st if not m.startswith('_')])}")
    missing = [m for m in explicit if m not in st]
    print(f"explicit proxy methods with no Store method of that name: {len(missing)}: {missing}")
    mism = [(m, sig(dw[m]), sig(st[m])) for m in explicit if m in st and sig(dw[m]) != sig(st[m])]
    print(f"same-name methods whose parameter lists differ: {len(mism)}")
    for m, a, b in mism:
        print(f"  {m}: proxy pos={a[0]} kwonly={a[1]} | store pos={b[0]} kwonly={b[1]}")
    print(f"attribute uses on a writer-bound expression: {len(uses)} "
          f"({len({u[4] for u in uses})} distinct attributes)")
    print(f"  routed by an explicit proxy method: {len(routed)} uses, "
          f"{len({u[4] for u in routed})} attributes")
    print(f"  FALL-THROUGH to the reader via __getattr__: {len(fall)} uses, "
          f"{len({u[4] for u in fall})} attributes")
    cnt = collections.Counter(u[4] for u in fall)
    for attr, c in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0])):
        where = "Store method" if attr in st else ("underscored: AttributeError under a daemon"
                                                   if attr.startswith("_") else "Store attribute")
        if attr.startswith("_") and attr in st:
            where = "Store private method: AttributeError under a daemon"
        print(f"    {attr:30}{c:3}  {where}")
    unused = sorted(ex - {u[4] for u in uses})
    print(f"explicit proxy methods this scan never sees used on a writer-bound expression: {unused}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
