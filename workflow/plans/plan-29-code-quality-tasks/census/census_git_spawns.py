"""Census of git call sites in src/refmatrix for task 29.3(a) -- the spec's measurement, run at
the commit it names. Read-only AST; imports nothing from refmatrix.

Usage: python3 census_git_spawns.py <src/refmatrix>

GIT ARGV:    a list/tuple literal whose first element is the constant "git" (also as the left
             side of `[...] + rest`), or a name assigned such a literal in the same function.
GIT SPAWN:   a call to subprocess run / check_output / check_call / call / Popen (any alias,
             matched on the final name) whose first positional argument is a GIT ARGV.
GIT VIA A SHELL HELPER: any OTHER call that takes a GIT ARGV as a positional argument (for
             example `_ss_sh(["git", ...], repo)`): the helper spawns it, with the helper's
             own failure rule.
WRAPPER:     a function holding a GIT SPAWN that takes the git arguments from its caller
             (`*args` or an `args` parameter); its call sites are counted by name.
Reported per spawn: explicit `timeout=` or not; `check=True` / `check_*` (raises
CalledProcessError) or not; where stderr goes; the handler types of the enclosing `try`.
Not counted: git run by the GENERATED shell hooks (`hooks.py` writes bash, not Python).
"""
from __future__ import annotations

import ast
import collections
import pathlib
import sys

SPAWN = {"run", "check_output", "check_call", "call", "Popen"}


def is_git_lit(n: ast.AST) -> bool:
    if isinstance(n, ast.BinOp):
        return is_git_lit(n.left)
    return (isinstance(n, (ast.List, ast.Tuple)) and bool(n.elts)
            and isinstance(n.elts[0], ast.Constant) and n.elts[0].value == "git")


def call_name(c: ast.Call) -> str:
    f = c.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def main(argv: list[str]) -> int:
    src = pathlib.Path(argv[1])
    spawns, via, wrappers = [], [], {}
    trees = {}
    for p in sorted(src.rglob("*.py")):
        rel = p.relative_to(src).as_posix()
        tree = trees[rel] = ast.parse(p.read_text())
        parent: dict[ast.AST, ast.AST] = {}
        for n in ast.walk(tree):
            for c in ast.iter_child_nodes(n):
                parent[c] = n

        def up(n: ast.AST, kinds: tuple) -> ast.AST | None:
            while n in parent:
                n = parent[n]
                if isinstance(n, kinds):
                    return n
            return None

        for n in ast.walk(tree):
            if not isinstance(n, ast.Call) or not n.args:
                continue
            fn = up(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            a0 = n.args[0]
            git = is_git_lit(a0)
            if not git and isinstance(a0, ast.Name) and isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                git = any(isinstance(m, ast.Assign) and is_git_lit(m.value)
                          and any(isinstance(t, ast.Name) and t.id == a0.id for t in m.targets)
                          for m in ast.walk(fn))
            if not git:
                continue
            nm = call_name(n)
            named = up(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            fname = named.name if named else "<module>"
            if nm in SPAWN:
                kw = {k.arg: k.value for k in n.keywords}
                chk = nm.startswith("check_") or (isinstance(kw.get("check"), ast.Constant)
                                                  and kw["check"].value is True)
                tr = up(n, (ast.Try,))
                caught = ", ".join(ast.unparse(h.type) if h.type else "bare"
                                   for h in tr.handlers) if isinstance(tr, ast.Try) else "none"
                spawns.append((rel, n.lineno, fname, "timeout" if "timeout" in kw else "NO-TIMEOUT",
                               "raises-on-nonzero" if chk else "returns-rc", caught))
                if named is not None:
                    a = named.args
                    if a.vararg or any(p.arg == "args" for p in a.args + a.kwonlyargs):
                        wrappers[fname] = rel
            else:
                via.append((rel, n.lineno, fname, nm))
    per = collections.Counter(s[0] for s in spawns)
    print(f"git spawns: {len(spawns)} in {len(per)} modules "
          f"({'  '.join(f'{m}={c}' for m, c in per.most_common())})")
    print(f"  no timeout: {sum(1 for s in spawns if s[3] == 'NO-TIMEOUT')}   "
          f"raises CalledProcessError on a non-zero exit: {sum(1 for s in spawns if s[4] == 'raises-on-nonzero')}   "
          f"enclosing try catches Exception (any failure reads as empty): "
          f"{sum(1 for s in spawns if s[5] == 'Exception')}")
    for s in spawns:
        print("  %s:%d %s  %s  %s  try-catches=[%s]" % s)
    print(f"git argv handed to a non-subprocess helper: {len(via)}")
    for v in via:
        print("  %s:%d %s -> %s(...)" % v)
    print(f"wrappers (git arguments come from the caller): {len(wrappers)}")
    for w, mod in sorted(wrappers.items()):
        sites = collections.Counter()
        for rel, tree in trees.items():
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and call_name(n) == w:
                    sites[rel] += 1
        print(f"  {mod}:{w}  call sites: {sum(sites.values())} ({dict(sites)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
