"""The budget-outcome census (task 29.4 R3 `#r3-budget-census`; T0.3 + 29.4c, 2026-11-15).

Why: R3's rule has two halves. "No upper bound on elapsed time" is the wall-clock census's.
"Does not assert an outcome that a real-time budget decides unless the test controls which side
of the budget the run falls on" is bug-228's shape, and no `<` appears in it:
`test_ac2b_live_daemon_recall_writes_one_ok_recall_row` asserted `outcome == "ok"` against the
generated hook's real 5 s budget on a live sandbox daemon, and at load 3 the embedder's cold load
spent the budget (`skipped_budget`, latency 5,018 ms; T0.3 base sweep, ruling L157).

A test function is a HIT when it (a) uses a real daemon (`REAL_DAEMON_HELPERS`, directly, through
a helper function of its file, or through a fixture, conftest fixtures included) and (b) asserts a
comparison of an outcome field (`OUTCOME_FIELDS`) with a string. A hit passes only when, in the
same function, it builds the command it runs with `tests.timing.with_budget(command, seconds)`,
`seconds` a literal or `HANG_GUARD_S` imported from `tests.timing` (ruling L141: `with_budget` and
reasoned entries only; the knob forms are not read), or (L159) it calls a harness readiness
signal directly before it runs the hook. Otherwise it fails, or holds a
`budget-outcome` entry with a non-empty `reason` in `tests/wallclock_allow.json`.

What this census cannot see is an outcome asserted through another shape (an exit code, a row
count). That remainder is enforced by review (29.4 `#r3-budget-census`).

The two tables below are the one-line extension points (a new real-daemon helper, a new outcome
field). 29.4 places them in `tests/tiering.py` beside the signal table; that file is stage 4's
(29.4a) and does not exist on this branch, so they live here until it does.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

REAL_DAEMON_HELPERS = frozenset({"SandboxDaemon", "spawn_daemon_subprocess"})
# The harness readiness signals (29.4 #r3-bug228's readiness branch, L157 (1)): a test that
# waits on one before the hook runs has taken the pre-op leg (boot, model warm-up), which held
# >= 90% of bug-228's overrun, off the budget. A third control form beside `with_budget`,
# ruled by L159 (2026-11-15) as a deviation from 29.4 #r3-budget-census's two forms. Matched
# only as a call that certainly runs before the hook, on the daemon itself
# (`_waits_ready_before_the_run`; ch-bsd t03 r1 S3, L177).
READINESS_CALLS = frozenset({"wait_models_warm"})
OUTCOME_FIELDS = frozenset({"outcome"})
RUN_CALLS = frozenset({"run_hook", "run_cmd"})
TIMING_MODULE = "tests.timing"
BUDGET_HELPER = "with_budget"
HANG_GUARD = "HANG_GUARD_S"
EXEMPT_DIRS = ("fixtures/suite_health/",)


@dataclass
class BudgetCensusResult:
    hits: list
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _refs(n: ast.AST) -> set:
    out: set = set()
    for s in ast.walk(n):
        if isinstance(s, ast.Name):
            out.add(s.id)
        elif isinstance(s, ast.Attribute):
            out.add(s.attr)
    return out


def _name_ids(n: ast.AST) -> set:
    return {s.id for s in ast.walk(n) if isinstance(s, ast.Name)}


def _reaches_real(fn: ast.AST, real: set) -> bool:
    """A real-daemon helper by name or attribute (`h.SandboxDaemon`), or a real fixture/helper of
    the file by bare name or as a requested argument (an attribute `x.daemon` is not the local
    `daemon` fixture)."""
    return bool(_refs(fn) & REAL_DAEMON_HELPERS or (_name_ids(fn) | _args(fn)) & real)


def _args(fn: ast.AST) -> set:
    a = fn.args
    return {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}


def _top_functions(tree: ast.Module):
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n.name, n
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{n.name}.{m.name}", m


def real_daemon_names(tree: ast.Module, extra: frozenset = frozenset()) -> set:
    """Every non-test function of the file (fixtures and helpers) that reaches a real daemon,
    directly or through another such function or fixture, to a fixed point. `extra` carries
    conftest fixtures the file can request."""
    real = set(extra)
    funcs = [(name, fn) for name, fn in _top_functions(tree) if not name.startswith("test_")]
    changed = True
    while changed:
        changed = False
        for name, fn in funcs:
            if name in real:
                continue
            if _reaches_real(fn, real):
                real.add(name)
                changed = True
    return real


def _is_outcome(n: ast.AST) -> bool:
    for s in ast.walk(n):
        if (isinstance(s, ast.Subscript) and isinstance(s.slice, ast.Constant)
                and s.slice.value in OUTCOME_FIELDS):
            return True
        if isinstance(s, ast.Attribute) and s.attr in OUTCOME_FIELDS:
            return True
        if isinstance(s, ast.Name) and s.id in OUTCOME_FIELDS:
            return True
    return False


def _is_str(n: ast.AST) -> bool:
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return True
    return (isinstance(n, (ast.Tuple, ast.List, ast.Set)) and bool(n.elts)
            and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in n.elts))


def _asserts_outcome(fn: ast.AST) -> bool:
    for a in ast.walk(fn):
        if not isinstance(a, ast.Assert):
            continue
        for c in ast.walk(a.test):
            if not isinstance(c, ast.Compare):
                continue
            parts = [c.left] + list(c.comparators)
            for i, op in enumerate(c.ops):
                if not isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                    continue
                left, right = parts[i], parts[i + 1]
                if (_is_outcome(left) and _is_str(right)) or (_is_outcome(right) and _is_str(left)):
                    return True
    return False


def _timing_imports(tree: ast.Module) -> tuple:
    """(names bound to tests.timing.with_budget, names bound to tests.timing.HANG_GUARD_S,
    aliases of the tests.timing module)."""
    helper, guard, module = set(), set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 0:
            if n.module == TIMING_MODULE:
                for a in n.names:
                    if a.name == BUDGET_HELPER:
                        helper.add(a.asname or a.name)
                    elif a.name == HANG_GUARD:
                        guard.add(a.asname or a.name)
            elif n.module == "tests":
                for a in n.names:
                    if a.name == "timing":
                        module.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name == TIMING_MODULE and a.asname:
                    module.add(a.asname)
    return helper, guard, module


def _controls_budget(fn: ast.AST, tree: ast.Module) -> bool:
    helper, guard, module = _timing_imports(tree)

    def is_helper(f: ast.AST) -> bool:
        if isinstance(f, ast.Name):
            return f.id in helper
        return (isinstance(f, ast.Attribute) and f.attr == BUDGET_HELPER
                and isinstance(f.value, ast.Name) and f.value.id in module)

    def readable(v: ast.AST) -> bool:
        if (isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                and not isinstance(v.value, bool)):
            return True
        if isinstance(v, ast.Name):
            return v.id in guard
        return (isinstance(v, ast.Attribute) and v.attr == HANG_GUARD
                and isinstance(v.value, ast.Name) and v.value.id in module)

    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and is_helper(n.func):
            seconds = n.args[1] if len(n.args) >= 2 else next(
                (k.value for k in n.keywords if k.arg == "seconds"), None)
            if seconds is not None and readable(seconds):
                return True
    return _waits_ready_before_the_run(fn)


def _call_name(c: ast.Call):
    f = c.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)


def _is_daemon_ctor(e: ast.AST) -> bool:
    return isinstance(e, ast.Call) and _call_name(e) in REAL_DAEMON_HELPERS


def _straight_line(stmts: list, daemons: set):
    """The function's statements that CERTAINLY run, in order: its top-level statements and,
    recursively, `with` bodies. `if`, `try`, loops, nested `def`s and lambdas are not entered,
    because a call there may not run (ch-bsd t03 r1 S3, ruling L177). Yields `(node, exprs)`,
    `exprs` being what that step evaluates itself (a `with` header's context expressions, or a
    whole simple statement). Names bound to a real daemon (`with SandboxDaemon(...) as d`,
    `d = SandboxDaemon(...)`) are added to `daemons` as they are bound."""
    for st in stmts:
        if isinstance(st, (ast.With, ast.AsyncWith)):
            yield st, [item.context_expr for item in st.items]
            for item in st.items:
                if (isinstance(item.optional_vars, ast.Name)
                        and _is_daemon_ctor(item.context_expr)):
                    daemons.add(item.optional_vars.id)
            yield from _straight_line(st.body, daemons)
        else:
            if (isinstance(st, ast.Assign) and _is_daemon_ctor(st.value)
                    and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)):
                daemons.add(st.targets[0].id)
            yield st, [st]


def _waits_ready_before_the_run(fn: ast.AST) -> bool:
    """L159's form, read so that only a readiness call that CERTAINLY runs first counts (ch-bsd
    t03 r1 S3, ruling L177, 2026-11-15): an expression statement `d.wait_models_warm(...)` on the
    function's straight-line path, its receiver `d` a name bound to a real daemon, before the
    first step that runs the hook or CLI child (`RUN_CALLS`). Not counted: a call after the run,
    one in a helper (`_ready(d)`), a lambda or nested `def`, one under `if` / `try` / a loop, or
    one on another receiver (a fixture argument the census cannot tie to the daemon)."""
    daemons: set = set()
    ready = False
    for node, exprs in _straight_line(fn.body, daemons):
        runs = any(isinstance(c, ast.Call) and _call_name(c) in RUN_CALLS
                   for e in exprs for c in ast.walk(e))
        if runs:
            return ready
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr in READINESS_CALLS
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id in daemons):
            ready = True
    return False


def _hits(source: str, relpath: str, extra: frozenset = frozenset()) -> list:
    tree = ast.parse(source, filename=relpath)
    real = real_daemon_names(tree, extra)
    out = []
    for name, fn in _top_functions(tree):
        if not name.split(".")[-1].startswith("test_"):
            continue
        if not _reaches_real(fn, real):
            continue
        if not _asserts_outcome(fn):
            continue
        out.append((f"{relpath}::{name}", _controls_budget(fn, tree)))
    return out


def violations(source: str, relpath: str, extra_fixtures: frozenset = frozenset()) -> list:
    """The `relpath::function` key of every hit that does not control its budget."""
    return [key for key, controlled in _hits(source, relpath, extra_fixtures) if not controlled]


def _exempt(relpath: str) -> bool:
    return any(relpath.startswith(d) for d in EXEMPT_DIRS)


def _conftest_fixtures(tests_root: Path, errors: list) -> dict:
    """dir relpath ('' for the root) -> real-daemon fixtures its conftest.py defines."""
    out: dict = {}
    for p in sorted(tests_root.rglob("conftest.py")):
        rel_dir = p.parent.relative_to(tests_root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        try:
            out[rel_dir] = real_daemon_names(ast.parse(p.read_text(encoding="utf-8")))
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{p.relative_to(tests_root)}: unreadable: {type(exc).__name__}: {exc}")
    return out


def run_census(tests_root, *, allow_path) -> BudgetCensusResult:
    tests_root = Path(tests_root)
    errors: list = []
    conf = _conftest_fixtures(tests_root, errors)
    hits: list = []
    found: list = []
    for p in sorted(tests_root.rglob("*.py")):
        rel = p.relative_to(tests_root).as_posix()
        if "__pycache__" in p.parts or _exempt(rel):
            continue
        parents = [""] + ["/".join(p.parent.relative_to(tests_root).parts[:i + 1])
                          for i in range(len(p.parent.relative_to(tests_root).parts))]
        extra = frozenset().union(*(conf.get(d, set()) for d in parents))
        try:
            file_hits = _hits(p.read_text(encoding="utf-8"), rel, extra)
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{rel}: cannot be read as a syntax tree: {type(exc).__name__}: {exc}")
            continue
        hits += file_hits
        found += [k for k, controlled in file_hits if not controlled]

    entries = json.loads(Path(allow_path).read_text(encoding="utf-8")).get("entries") or []
    allowed: set = set()
    for e in entries:
        if e.get("kind") != "budget-outcome":
            continue
        key = e.get("key", "")
        if not str(e.get("reason", "")).strip():
            errors.append(f"budget-outcome entry {key!r} has no reason")
            continue
        if key not in found:
            errors.append(f"stale budget-outcome entry {key!r}: no such uncontrolled hit in the "
                          f"tree; delete the entry")
            continue
        allowed.add(key)
    for key in found:
        if key not in allowed:
            errors.append(
                f"{key}: asserts an outcome a real-time budget decides against a real daemon, "
                f"and does not control the budget. Build the command with "
                f"tests.timing.with_budget(command, HANG_GUARD_S or a literal), or hold a "
                f"budget-outcome entry with its reason (29.4 #r3-budget-census)")
    return BudgetCensusResult(hits=hits, errors=errors)
