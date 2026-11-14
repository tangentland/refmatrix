"""Census of daemon-liveness gates and daemon RPC bounds in src/refmatrix (task 29.3 d/e spec).

Usage: python3 census_daemon_gates.py <src/refmatrix> [--list ping|call]

PING GATE: a call whose final name is `ping` (`daemon_mod.ping(root)`, `dm.ping(...)`, `ping(...)`)
           that sits inside the test of an `if` / `elif` / `while` / conditional expression, a
           `not`, a boolean operator, or `bool(...)`. Its false branch reads "no daemon".
           Calls to `require_daemon` / `daemon_status` (the typed up/busy/absent classifiers) are
           counted beside it.
RPC CALL:  a call `<x>.call(root, "<op>", ...)` or `call(root, "<op>", ...)` whose second
           positional argument is a string constant (a daemon op name), or `global_call(...)`.
           Reported: explicit `timeout=` or not, explicit `retries=` or not (the default
           `retries=2` makes the worst case 3 x timeout).
"""
from __future__ import annotations
import ast, collections, pathlib, sys


def name_of(c: ast.Call) -> str:
    f = c.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1]); want = argv[3] if len(argv) > 3 and argv[2] == "--list" else None
    ping_gate = collections.Counter(); ping_other = collections.Counter(); typed = collections.Counter()
    rpc = collections.defaultdict(collections.Counter)
    for p in sorted(root.rglob("*.py")):
        tree = ast.parse(p.read_text()); rel = p.relative_to(root).as_posix()
        in_test: set[int] = set()
        for n in ast.walk(tree):
            tests = []
            if isinstance(n, (ast.If, ast.While, ast.IfExp)):
                tests.append(n.test)
            if isinstance(n, ast.BoolOp):
                tests.extend(n.values)
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
                tests.append(n.operand)
            if isinstance(n, ast.Call) and name_of(n) == "bool":
                tests.extend(n.args)
            for t in tests:
                for m in ast.walk(t):
                    if isinstance(m, ast.Call) and name_of(m) == "ping":
                        in_test.add(id(m))
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            nm = name_of(n)
            if nm == "ping":
                if id(n) in in_test:
                    ping_gate[rel] += 1
                    if want == "ping":
                        print(f"{rel}:{n.lineno}: {ast.unparse(n)[:90]}")
                else:
                    ping_other[rel] += 1
            elif nm in ("require_daemon", "daemon_status"):
                typed[rel] += 1
            elif (nm == "call" and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant)
                  and isinstance(n.args[1].value, str)) or nm == "global_call":
                kw = {k.arg for k in n.keywords}
                key = ("timeout" if "timeout" in kw else "NO-timeout") + "/" + (
                    "retries" if "retries" in kw else "DEFAULT-retries")
                rpc[rel][key] += 1
                if want == "call" and "retries" not in kw:
                    print(f"{rel}:{n.lineno}: {ast.unparse(n)[:100]}")
    if want:
        return 0
    print(f"ping gates (ping in a condition): {sum(ping_gate.values())} in {len(ping_gate)} modules; "
          f"other ping calls (assigned / returned): {sum(ping_other.values())}; "
          f"typed classifier calls (require_daemon / daemon_status): {sum(typed.values())}")
    for m in sorted(set(ping_gate) | set(ping_other) | set(typed), key=lambda m: -(ping_gate[m] + ping_other[m])):
        print(f"  {m:22} gate={ping_gate[m]:3} other={ping_other[m]:3} typed={typed[m]:3}")
    tot = collections.Counter()
    for c in rpc.values():
        tot.update(c)
    print(f"daemon RPC calls with a constant op: {sum(tot.values())}  " + "  ".join(f"{k}={v}" for k, v in sorted(tot.items())))
    for m, c in sorted(rpc.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {m:22}" + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
