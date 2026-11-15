"""Census of numeric env-knob reads that bypass `envknob` (task 29.3 slice h, bug-188) -- the
spec's measurement, run at the commit it names. Read-only AST.

Usage: python3 census_env_knobs.py <src/refmatrix> [--list]

BARE READ: a call `float(X)` or `int(X)` whose first argument's source text contains
`os.environ` or `getenv(` (so `float(os.environ.get("K", "5"))`, `int(os.environ["K"])`,
`float(os.getenv("K") or 5)`), in any module except `envknob.py`.
`--list` prints each as `module:line: <call>`.
"""
from __future__ import annotations

import ast
import collections
import pathlib
import sys


def main(argv: list[str]) -> int:
    src = pathlib.Path(argv[1])
    show = "--list" in argv
    per: collections.Counter = collections.Counter()
    kinds: collections.Counter = collections.Counter()
    for p in sorted(src.rglob("*.py")):
        if p.name == "envknob.py":
            continue
        rel = p.relative_to(src).as_posix()
        for n in ast.walk(ast.parse(p.read_text())):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in ("float", "int") and n.args):
                s = ast.unparse(n.args[0])
                if "os.environ" in s or "getenv(" in s:
                    per[rel] += 1
                    kinds[n.func.id] += 1
                    if show:
                        print(f"{rel}:{n.lineno}: {ast.unparse(n)[:100]}")
    if show:
        return 0
    print(f"bare numeric env reads outside envknob: {sum(per.values())} in {len(per)} modules "
          f"(float {kinds['float']}, int {kinds['int']})")
    for m, c in sorted(per.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {m:22}{c:4}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
