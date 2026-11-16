"""The wall-clock census (task 29.4 R3 `#r3-census`, `#r3-kinds`; T0.3 + 29.4c, 2026-11-15).

Why: the suite asserted upper bounds on elapsed time, and under load those bounds decided the
result (bug-231's `stop took < 8.0` failed at 10.05 s and 9.02 s; bug-091 waited one 3 s
`wait`). A grep for `< N.0` found 53 such asserts; the syntax tree found 78 (29.4
`#baseline-wallclock`). This census reads every file under `tests/` as a syntax tree, finds each
UPPER bound on a clock difference, on a name assigned from one, or on an elapsed-like name,
WHATEVER the limit is (a literal, a named constant, an expression), and compares the set with
`tests/wallclock_allow.json`:

- a bound that is not listed fails, naming the file, the test and the four fix classes;
- an entry whose assert no longer exists fails (the list is exact and only shrinks);
- exempt by form: a lower bound, and `< HANG_GUARD_S` where the name is imported from
  `tests/timing.py` (whose value must be >= 60); exempt by path: `tests/fixtures/suite_health/`
  (its bounds ARE the fixture) and nothing else;
- `legacy` entries must name a key that existed at the task's base (the frozen baseline,
  `tests/wallclock_legacy_baseline.json`, guarded by `_BASELINE_SHA256`), so the set only
  shrinks;
- `feature-bound` entries (a deadline that IS the feature) must resolve their `ac` to a spec
  anchor by frontmatter id, quote a wall-clock clause of that AC (one entry per clause), and set
  their `knob` in the test function to a literal at or under `max_s` (<= 2.0), in one of the forms
  `env:NAME`, `const:pkg.mod.NAME`, `arg:param` (ruling L107).

`budget-outcome` entries belong to `tests/budget_outcome_census.py` and are ignored here.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

TIMING_MODULE = "tests.timing"
HANG_GUARD = "HANG_GUARD_S"
HANG_GUARD_MIN_S = 60.0
MAX_S_CEILING = 2.0
EXEMPT_DIRS = ("fixtures/suite_health/",)
CLASSES = {
    "A": "hang guard: wait for the outcome under tests.timing.HANG_GUARD_S and assert it; the "
         "elapsed time goes in the failure message only",
    "B": "budget honoured: assert the mechanism (the timeout that reached the transport, the "
         "attempts, the busy/skipped result); inject the clock where the code reads one",
    "C": "did not block: an ordering check (the call returned while the worker was still held "
         "on an event the test owns); no clock",
    "D": "latency measurement: not a suite test; move it to eval/ with its number, or delete it "
         "with a note of what it measured",
}
_FIX_CLASSES = "; ".join(f"{k}. {v}" for k, v in CLASSES.items())

# The frozen set of bound keys at the task's base (`c4b44d0`, the RED base of T0.3 + 29.4c). A
# `legacy` entry may only name one of these. The hash pins the file: editing the baseline to let
# a new bound in needs an edit here too, which review sees.
BASELINE_FILE = "wallclock_legacy_baseline.json"
_BASELINE_SHA256 = "c8e7403bdc3f03bbac936756bbf5d227fd07395c8023ca3bbfc30451bc9fc639"

_CLOCK_FUNCS = {"time", "monotonic", "perf_counter", "monotonic_ns", "perf_counter_ns",
                "time_ns"}
_ELAPSED_NAME = re.compile(
    r"^(elapsed|took|wall|dt|duration|dur|secs|seconds|spent|waited|latency|lat|ms|wall_s|"
    r"elapsed_s|took_s)\d*$", re.I)
# A wall-clock clause in an AC's own text: a number with a time unit ("within 0.5 s", "2 s").
_CLAUSE_TIME = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|secs|seconds?|min|minutes?)\b")
_ANCHOR = re.compile(r"\{#([A-Za-z0-9_.:-]+)\}")
_HEADING = re.compile(r"^(#{1,6})\s")


@dataclass(frozen=True)
class Bound:
    """One upper-bound assert. `key` carries no line number, so moving code does not churn the
    allow list; a second identical assert in one function gets an ordinal suffix."""
    key: str
    relpath: str
    function: str
    lineno: int
    source: str


@dataclass
class CensusResult:
    bounds: list
    errors: list = field(default_factory=list)
    counts: dict = field(default_factory=lambda: {"legacy": 0, "feature-bound": 0})

    @property
    def ok(self) -> bool:
        return not self.errors

    def report(self) -> str:
        files = len({b.relpath for b in self.bounds})
        lines = [
            f"wall-clock census: {len(self.bounds)} upper bounds in {files} files",
            f"  allow list: legacy {self.counts['legacy']}, "
            f"feature-bound {self.counts['feature-bound']}",
            f"  errors: {len(self.errors)}",
        ]
        lines += [f"  - {e}" for e in self.errors]
        return "\n".join(lines)


# ---- finding bounds ----------------------------------------------------------------------------

def _is_clock_call(n: ast.AST) -> bool:
    if not isinstance(n, ast.Call):
        return False
    f = n.func
    return ((isinstance(f, ast.Attribute) and f.attr in _CLOCK_FUNCS)
            or (isinstance(f, ast.Name) and f.id in _CLOCK_FUNCS))


def _has_clock_diff(n: ast.AST) -> bool:
    return any(isinstance(s, ast.BinOp) and isinstance(s.op, ast.Sub) and _is_clock_call(s.left)
               for s in ast.walk(n))


def _names(n: ast.AST) -> set:
    return {s.id for s in ast.walk(n) if isinstance(s, ast.Name)}


def _clock_bound_names(tree: ast.AST) -> set:
    """Names assigned from a clock difference anywhere in the file (`x = time.monotonic() - t0`)."""
    out: set = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            value = n.value
            if value is None or not _has_clock_diff(value):
                continue
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                out |= _names(t)
    return out


def _hang_guard_imported(tree: ast.Module) -> bool:
    """True when the file takes HANG_GUARD_S from tests/timing.py and never rebinds it: the
    exemption is by import, not by spelling."""
    imported = any(
        isinstance(n, ast.ImportFrom) and n.module == TIMING_MODULE and n.level == 0
        and any(a.name == HANG_GUARD and (a.asname in (None, HANG_GUARD)) for a in n.names)
        for n in ast.walk(tree))
    if not imported:
        return False
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any(HANG_GUARD in _names(t) for t in targets):
                return False
    return True


def _is_hang_guard(limit: ast.AST, exempt: bool) -> bool:
    return exempt and isinstance(limit, ast.Name) and limit.id == HANG_GUARD


def _upper_bound_in(test: ast.AST, clock_names: set, hang_guard_ok: bool) -> bool:
    def timey(e: ast.AST) -> bool:
        names = _names(e)
        return (_has_clock_diff(e) or bool(names & clock_names)
                or any(_ELAPSED_NAME.match(x) for x in names))

    for c in ast.walk(test):
        if not isinstance(c, ast.Compare):
            continue
        parts = [c.left] + list(c.comparators)
        for i, op in enumerate(c.ops):
            left, right = parts[i], parts[i + 1]
            if isinstance(op, (ast.Lt, ast.LtE)):
                subj, limit = left, right
            elif isinstance(op, (ast.Gt, ast.GtE)):
                subj, limit = right, left
            else:
                continue
            if timey(subj) and not timey(limit) and not _is_hang_guard(limit, hang_guard_ok):
                return True
    return False


def _functions(tree: ast.Module):
    """(qualified name, node) for every top-level function and class method; an assert inside a
    nested helper belongs to the outer test function."""
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n.name, n
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{n.name}.{m.name}", m


def _owner_map(tree: ast.Module) -> dict:
    owner: dict = {}
    for name, fn in _functions(tree):
        for s in ast.walk(fn):
            owner.setdefault(id(s), name)
    return owner


def find_bounds(source: str, relpath: str) -> list:
    """Every upper-bound assert in `source`, in line order."""
    tree = ast.parse(source, filename=relpath)
    clock_names = _clock_bound_names(tree)
    hang_ok = _hang_guard_imported(tree)
    owner = _owner_map(tree)
    asserts = sorted((n for n in ast.walk(tree) if isinstance(n, ast.Assert)),
                     key=lambda n: (n.lineno, n.col_offset))
    out: list = []
    seen: dict = {}
    for a in asserts:
        if not _upper_bound_in(a.test, clock_names, hang_ok):
            continue
        fn = owner.get(id(a), "<module>")
        src = ast.unparse(a.test)
        base = f"{relpath}::{fn}::{src}"
        seen[base] = seen.get(base, 0) + 1
        key = base if seen[base] == 1 else f"{base} [{seen[base]}]"
        out.append(Bound(key=key, relpath=relpath, function=fn, lineno=a.lineno, source=src))
    return out


def _exempt(relpath: str) -> bool:
    return any(relpath.startswith(d) for d in EXEMPT_DIRS)


def _iter_sources(tests_root: Path):
    for p in sorted(tests_root.rglob("*.py")):
        rel = p.relative_to(tests_root).as_posix()
        if "__pycache__" in p.parts or _exempt(rel):
            continue
        yield rel, p


def scan(tests_root: Path) -> tuple:
    """(bounds, errors) over the tree. A file that does not parse is an error, never a skip."""
    bounds: list = []
    errors: list = []
    for rel, p in _iter_sources(tests_root):
        try:
            bounds += find_bounds(p.read_text(encoding="utf-8"), rel)
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{rel}: cannot be read as a syntax tree, so its bounds are unknown: "
                          f"{type(exc).__name__}: {exc}")
    return bounds, errors


# ---- the hang guard ----------------------------------------------------------------------------

def _hang_guard_value(tests_root: Path):
    p = tests_root / "timing.py"
    if not p.is_file():
        return None, f"{HANG_GUARD}: {p} does not exist"
    tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    for n in tree.body:
        if (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == HANG_GUARD
                                              for t in n.targets)):
            v = n.value
            if (isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                    and not isinstance(v.value, bool)):
                return float(v.value), None
            return None, f"{HANG_GUARD} in {p} is not a numeric literal: {ast.unparse(v)}"
    return None, f"{HANG_GUARD} is not assigned at module level in {p}"


# ---- specs: resolving `ac` ---------------------------------------------------------------------

def _frontmatter_id(text: str):
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    for line in text[3:end].splitlines():
        m = re.match(r"^id:\s*[\"']?([^\"'\s]+)[\"']?\s*$", line)
        if m:
            return m.group(1)
    return None


def _spec_index(specs_root: Path) -> dict:
    index: dict = {}
    for p in sorted(Path(specs_root).rglob("*.md")):
        text = p.read_text(encoding="utf-8")
        sid = _frontmatter_id(text)
        if sid:
            index.setdefault(sid, (p, text))
    return index


def _anchor_text(text: str, anchor: str):
    """The block an anchor names. A heading's anchor names its section (to the next heading of
    the same or a higher level); any other anchor names the lines back to the previous anchored
    block, a heading, or the frontmatter (GMD closes every block with its anchor)."""
    lines = text.splitlines()
    tag = "{#" + anchor + "}"
    at = next((i for i, ln in enumerate(lines) if tag in ln), None)
    if at is None:
        return None
    h = _HEADING.match(lines[at])
    if h:
        level = len(h.group(1))
        end = len(lines)
        for j in range(at + 1, len(lines)):
            hj = _HEADING.match(lines[j])
            if hj and len(hj.group(1)) <= level:
                end = j
                break
        block = lines[at:end]
    else:
        start = at
        while start > 0:
            prev = lines[start - 1]
            if _ANCHOR.search(prev) or _HEADING.match(prev) or prev.strip() == "---":
                break
            start -= 1
        block = lines[start:at + 1]
    return " ".join(" ".join(block).split())


# ---- knobs -------------------------------------------------------------------------------------

def _literal_number(n: ast.AST):
    """A numeric literal, or a string literal that parses as one (an env value); else None."""
    if isinstance(n, ast.Constant):
        v = n.value
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return None
    return None


def _import_aliases(tree: ast.Module) -> dict:
    """local name -> dotted module path, from `import a.b as c` and `from a import b`."""
    out: dict = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            for a in n.names:
                out[a.asname or a.name] = f"{n.module}.{a.name}"
    return out


def _dotted(n: ast.AST, aliases: dict):
    if isinstance(n, ast.Name):
        return aliases.get(n.id, n.id)
    if isinstance(n, ast.Attribute):
        base = _dotted(n.value, aliases)
        return f"{base}.{n.attr}" if base else None
    return None


def _knob_values(fn: ast.AST, tree: ast.Module, knob: str) -> tuple:
    """(values, problems): every literal the test function sets the knob to, and every setting
    the census cannot read. No setting at all returns ([], [])."""
    kind, _, name = knob.partition(":")
    values: list = []
    problems: list = []

    def take(node: ast.AST, what: str) -> None:
        v = _literal_number(node)
        if v is None:
            problems.append(f"{what} is set to `{ast.unparse(node)}`, which is not a literal "
                            f"the census can read")
        else:
            values.append(v)

    if kind == "env":
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                f = n.func
                if (isinstance(f, ast.Attribute) and f.attr == "setenv" and len(n.args) >= 2
                        and isinstance(n.args[0], ast.Constant) and n.args[0].value == name):
                    take(n.args[1], f"env {name}")
                for kw in n.keywords:
                    if kw.arg == name:
                        take(kw.value, f"env {name}")
            elif isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if isinstance(k, ast.Constant) and k.value == name:
                        take(v, f"env {name}")
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                            and t.slice.value == name):
                        take(n.value, f"env {name}")
    elif kind == "const":
        aliases = _import_aliases(tree)
        mod, _, attr = name.rpartition(".")
        for n in ast.walk(fn):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "setattr"):
                continue
            a = n.args
            if len(a) >= 2 and isinstance(a[0], ast.Constant) and a[0].value == name:
                take(a[1], f"const {name}")
            elif (len(a) >= 3 and isinstance(a[1], ast.Constant) and a[1].value == attr
                  and _dotted(a[0], aliases) == mod):
                take(a[2], f"const {name}")
    elif kind == "arg":
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                for kw in n.keywords:
                    if kw.arg == name:
                        take(kw.value, f"argument {name}= of `{ast.unparse(n.func)}`")
    return values, problems


# ---- the census --------------------------------------------------------------------------------

def _load_baseline(tests_root: Path) -> set:
    p = Path(tests_root) / BASELINE_FILE
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != _BASELINE_SHA256:
        raise ValueError(f"{p}: sha256 {digest} is not the frozen baseline {_BASELINE_SHA256}; "
                         f"the legacy baseline only shrinks through the allow list, never here")
    return set(json.loads(raw)["keys"])


def run_census(tests_root, *, allow_path, specs_root, legacy_baseline=None) -> CensusResult:
    tests_root = Path(tests_root)
    bounds, errors = scan(tests_root)
    result = CensusResult(bounds=bounds, errors=errors)

    guard, problem = _hang_guard_value(tests_root)
    if problem:
        errors.append(problem)
    elif guard < HANG_GUARD_MIN_S:
        errors.append(f"{HANG_GUARD} is {guard:g} s in tests/timing.py; it must be >= "
                      f"{HANG_GUARD_MIN_S:g} s (a hang guard far above any real duration)")

    if legacy_baseline is None:
        legacy_baseline = _load_baseline(tests_root)
    legacy_baseline = set(legacy_baseline)

    entries = json.loads(Path(allow_path).read_text(encoding="utf-8")).get("entries")
    if not isinstance(entries, list):
        errors.append(f"{allow_path}: no `entries` list")
        return result

    by_key = {b.key: b for b in bounds}
    listed: dict = {}
    clause_owners: dict = {}
    specs = None
    trees: dict = {}

    for e in entries:
        kind = e.get("kind")
        key = e.get("key", "")
        if kind == "budget-outcome":
            continue
        if kind not in ("legacy", "feature-bound"):
            errors.append(f"allow entry {key!r}: unknown kind {kind!r} (legacy, feature-bound, "
                          f"budget-outcome)")
            continue
        result.counts[kind] += 1
        if key in listed:
            errors.append(f"allow entry {key!r}: listed twice")
            continue
        listed[key] = e
        b = by_key.get(key)
        if b is None:
            errors.append(f"stale allow entry ({kind}) {key!r}: no such bound in the tree; "
                          f"delete the entry (the list is exact and only shrinks)")
            continue
        if kind == "legacy":
            if e.get("class") not in CLASSES:
                errors.append(f"legacy entry {key!r}: `class` must be one of A/B/C/D, got "
                              f"{e.get('class')!r}")
            if key not in legacy_baseline:
                errors.append(f"new legacy entry {key!r} ({b.relpath}::{b.function}): a legacy "
                              f"entry may only name a bound that existed at the task's base; "
                              f"replace the bound ({_FIX_CLASSES})")
            continue

        # feature-bound
        who = f"feature-bound entry {key!r} ({b.relpath}::{b.function})"
        ac = e.get("ac")
        if not ac or "#" not in str(ac):
            errors.append(f"{who}: no `ac` of the form <spec id>#<anchor>")
        else:
            sid, _, anchor = str(ac).partition("#")
            if specs is None:
                specs = _spec_index(Path(specs_root))
            if sid not in specs:
                errors.append(f"{who}: ac {ac!r}: no spec with frontmatter id {sid!r} under "
                              f"{specs_root}")
            else:
                text = _anchor_text(specs[sid][1], anchor)
                if text is None:
                    errors.append(f"{who}: ac {ac!r}: spec {sid!r} has no anchor {{#{anchor}}}")
                else:
                    clause = " ".join(str(e.get("clause", "")).split())
                    if not clause or clause not in text:
                        errors.append(f"{who}: clause {e.get('clause')!r} is not in the text of "
                                      f"{ac}")
                    else:
                        n_clauses = len(_CLAUSE_TIME.findall(text))
                        owners = clause_owners.setdefault(str(ac), [])
                        owners.append(key)
                        if len(owners) > n_clauses:
                            errors.append(
                                f"{who}: {ac} has {n_clauses} wall-clock clause(s) and "
                                f"{len(owners)} entries ({owners}); one AC, one entry per clause")
        max_s = e.get("max_s")
        if (isinstance(max_s, bool) or not isinstance(max_s, (int, float))
                or not 0 < max_s <= MAX_S_CEILING):
            errors.append(f"{who}: max_s {max_s!r} must be a number in (0, {MAX_S_CEILING:g}]")
            max_s = None
        knob = str(e.get("knob", ""))
        if not re.match(r"^(env:[A-Za-z_][A-Za-z0-9_]*|const:[A-Za-z_][\w.]*\.[A-Za-z_]\w*|"
                        r"arg:[A-Za-z_]\w*)$", knob):
            errors.append(f"{who}: knob {knob!r} is not env:NAME, const:pkg.mod.NAME or "
                          f"arg:param")
            continue
        if b.relpath not in trees:
            trees[b.relpath] = ast.parse((tests_root / b.relpath).read_text(encoding="utf-8"))
        tree = trees[b.relpath]
        fn = dict(_functions(tree)).get(b.function)
        if fn is None:
            errors.append(f"{who}: the bound is not inside a test function")
            continue
        values, problems = _knob_values(fn, tree, knob)
        errors += [f"{who}: {p}" for p in problems]
        if not values and not problems:
            errors.append(f"{who}: the test never sets its knob {knob}; it would wait the "
                          f"production value")
        if max_s is not None:
            over = [v for v in values if v > max_s]
            if over:
                errors.append(f"{who}: knob {knob} is set to {over}, over max_s {max_s:g}")

    for key, b in by_key.items():
        if key not in listed:
            errors.append(
                f"unlisted wall-clock bound in {b.relpath}, test {b.function} (line {b.lineno}): "
                f"`{b.source}`. A test does not assert an upper bound on elapsed time "
                f"(29.4 #r3-rule); replace it by its class: {_FIX_CLASSES}")
    return result
