"""Broad-except census for task 29.3(c) -- the spec's measurement, run at the commit it names.

Usage: python3 census_broad_except.py <src/refmatrix> [--list CLASS]

A handler is BROAD when it catches `Exception` or `BaseException` (alone or in a tuple) or is a
bare `except:`. Each broad handler gets exactly one class, first match wins:

  reraise    the handler body (nested defs/lambdas excluded) contains a `raise` statement.
  surfaced   the body does one of:
               - references the bound exception name (`except Exception as e:` ... `e` used);
               - an augmented assignment to a FAILURE counter: the target's text matches COUNTER
                 (`errors += 1`, `stats["skipped"] += 1`; a plain `n += 1` is not one -- found
                 at ingest.py:1409, where `n` counts docs registered, not failures);
               - calls a function whose final name is in SURFACE_CALLS (loggers, stderr writers,
                 degraded-mode recorders), or `print(..., file=...)`, or `click.echo(..., err=True)`.
  justified  none of the above, and the `except` line carries `noqa: BLE001` followed by a dash
             and a reason of at least three words.
  silent     none of the above. Reported in two parts: `silent(commented)` has a `#` comment on
             the except line, the line before it, or the handler's first body line (a reason a
             reader can see, but not in the gate's form); `silent(bare)` has none.

The 29.3(c) census test applies the SAME rule; both `silent` parts are what it fails on. A bare
`# noqa: BLE001` with no reason is `silent` here (it names no reason).
"""
from __future__ import annotations

import ast
import collections
import pathlib
import re
import sys

SURFACE_CALLS = {
    "_log", "log", "warn", "_warn", "warning", "error", "exception", "critical", "info", "debug",
    "_note_degraded", "record_pointer_error", "_say", "_alert", "secho",
}
COUNTER = re.compile(r"err|fail|skip|drop|miss|unread|bad|degrad|lost|refus", re.I)
JUSTIFY = re.compile(r"noqa:\s*BLE001\s*[—–-]+\s*(\S+\s+){2,}\S+")
MEMORY_PATH_MODULES = {
    "ingest_gmd.py", "handoff.py", "recall.py", "promote.py", "memory_index.py",
    "memory_layout.py", "stm.py", "embedder.py", "consolidate.py", "brief.py",
}


def broad(h: ast.ExceptHandler) -> bool:
    t = h.type
    if t is None:
        return True
    elts = list(t.elts) if isinstance(t, ast.Tuple) else [t]
    for n in elts:
        name = n.id if isinstance(n, ast.Name) else (n.attr if isinstance(n, ast.Attribute) else "")
        if name in ("Exception", "BaseException"):
            return True
    return False


def body_nodes(h: ast.ExceptHandler):
    stack = list(h.body)
    while stack:
        n = stack.pop()
        yield n
        for c in ast.iter_child_nodes(n):
            if not isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                stack.append(c)


def call_name(c: ast.Call) -> str:
    f = c.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def classify(h: ast.ExceptHandler, lines: list[str]) -> str:
    nodes = list(body_nodes(h))
    if any(isinstance(n, ast.Raise) for n in nodes):
        return "reraise"
    if h.name and any(isinstance(n, ast.Name) and n.id == h.name for n in nodes):
        return "surfaced"
    for n in nodes:
        if isinstance(n, ast.AugAssign) and COUNTER.search(ast.unparse(n.target)):
            return "surfaced"
        if isinstance(n, ast.Call):
            nm = call_name(n)
            kw = {k.arg: k.value for k in n.keywords}
            if nm in SURFACE_CALLS:
                return "surfaced"
            if nm == "print" and "file" in kw:
                return "surfaced"
            if (isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                    and n.func.value.id in ("console", "err_console") and nm == "print"):
                return "surfaced"
            if (nm == "write" and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "stderr"):
                return "surfaced"
            if nm == "echo" and isinstance(kw.get("err"), ast.Constant) and kw["err"].value:
                return "surfaced"
    if JUSTIFY.search(lines[h.lineno - 1]):
        return "justified"
    prev = lines[h.lineno - 2] if h.lineno >= 2 else ""
    upto_first_stmt = lines[h.lineno - 1:h.body[0].lineno] if h.body else [lines[h.lineno - 1]]
    if prev.strip().startswith("#") or any("#" in ln for ln in upto_first_stmt):
        return "silent(commented)"
    return "silent(bare)"


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1])
    want = argv[3] if len(argv) > 3 and argv[2] == "--list" else None
    per = collections.defaultdict(collections.Counter)
    tot = collections.Counter()
    for p in sorted(root.rglob("*.py")):
        lines = p.read_text().splitlines()
        rel = p.relative_to(root).as_posix()
        for h in ast.walk(ast.parse("\n".join(lines))):
            if isinstance(h, ast.ExceptHandler) and broad(h):
                c = classify(h, lines)
                per[rel][c] += 1
                tot[c] += 1
                if c == want:
                    print(f"{rel}:{h.lineno}: {lines[h.lineno - 1].strip()}")
    if want:
        return 0
    print(f"total broad handlers: {sum(tot.values())}  " + "  ".join(
        f"{k}={tot[k]}" for k in ("reraise", "surfaced", "justified", "silent(commented)", "silent(bare)")))
    mem = collections.Counter()
    for m, c in per.items():
        if pathlib.PurePosixPath(m).name in MEMORY_PATH_MODULES:
            mem.update(c)
    print("memory-path modules: " + "  ".join(
        f"{k}={mem[k]}" for k in ("reraise", "surfaced", "justified", "silent(commented)", "silent(bare)")))
    print(f"{'module':26}{'reraise':>8}{'surfaced':>9}{'justified':>10}{'commented':>10}"
          f"{'bare':>6}{'total':>6}")
    for m, c in sorted(per.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"{m:26}{c['reraise']:8}{c['surfaced']:9}{c['justified']:10}"
              f"{c['silent(commented)']:10}{c['silent(bare)']:6}{sum(c.values()):6}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
