"""plan-29 task 29.4b (stage 2, with T0.2): R5 -- test roots live under the sandbox root.

WHY. bug-229's leaked daemon served `/private/tmp/r1-hcn81cf7/proj/.refmatrix`, a
`mkdtemp(prefix="r1-", dir="/tmp")` outside the sandbox root, and its root outlived the run.
The store review counted 96 such lines. With every test root under the sandbox
(`rmx_sandbox.short_root(prefix)` -> `<sandbox root>/t/…`), a leaked root goes with the
sandbox, a leaked daemon's pid file is found by one `rglob` under one directory, and two shards
cannot collide on a root by construction (task-29.4 `#r5`, `#r5-why`).

What is pinned here:
- `short_root(prefix)`: a fresh, existing directory under `<sandbox root>/t/`, short enough
  that `<it>/proj/.refmatrix/rmxd.sock` stays far under macOS's 104-byte `sun_path` (62 bytes
  for the untagged root in the spec, plus the prefix).
- The census: every `mkdtemp(` under `tests/` (fixtures included) whose root is `/tmp` or
  `/private/tmp` -- `dir=` that literal, or an absolute `prefix=` under it, which is the same
  root spelled differently (`tests/test_brief_real_daemon.py`'s `prefix="/tmp/bd."`) -- is
  either in `tests/tmp_root_allow.json` or fails. The list is EXACT (the `#r3-census` rule): a
  key with no line number (`file::function::normalised call`), a site not in it fails, and an
  entry whose site is gone fails, so the list only shrinks.
- `tests/fixtures/suite_health/` is exempt BY PATH, in this file, with the reason beside it
  (`#r1-fixtures`); a violation anywhere else under `tests/fixtures/` fails (a must-fail case).
- The 28 files that call `spawn_daemon_subprocess` were moved in this task: the allow list
  holds no site of theirs (`#r5`: "the list starts with the sites left after the 28 files are
  moved").

`tests/tmp_root_allow.json` is `{"entries": [{"key": "<file>::<function>::<call>", "reason":
"…"}, …]}`; a key appears once per site (two identical calls in one function: two entries).

Must-fail cases run the census over synthetic trees, so a census that stopped checking is seen
on input that must fail ([[feedback_clean_corpus_hides_a_dead_gate]]).
"""
from __future__ import annotations

import ast
import json
import os
import warnings
from collections import Counter
from pathlib import Path

import pytest

import rmx_sandbox  # on sys.path via tests/conftest.py (tests/sandbox_site)

_REPO = Path(__file__).resolve().parents[1]
ALLOW = _REPO / "tests" / "tmp_root_allow.json"

# The one exemption, by path (task-29.4 `#r1-fixtures`): the AC-5 fixture cases make their
# store roots with `mkdtemp(dir="/tmp")` ON PURPOSE -- bug-229's out-of-sandbox shape is what
# the reaper must catch -- and they never run as part of the suite.
EXEMPT_DIRS = ("tests/fixtures/suite_health/",)

_TMP_ROOTS = ("/tmp", "/private/tmp")


# ---- the census ------------------------------------------------------------------------------

def _is_mkdtemp(call: ast.Call) -> bool:
    f = call.func
    return (isinstance(f, ast.Attribute) and f.attr == "mkdtemp") or \
        (isinstance(f, ast.Name) and f.id == "mkdtemp")


def _const_str(node) -> "str | None":
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _under_tmp(path: str) -> bool:
    p = path.rstrip("/") or "/"
    return any(p == r or path.startswith(r + "/") for r in _TMP_ROOTS)


def _hits_tmp(call: ast.Call) -> bool:
    kw = {k.arg: k.value for k in call.keywords if k.arg}
    args = list(call.args)          # mkdtemp(suffix, prefix, dir)
    dir_node = kw.get("dir", args[2] if len(args) > 2 else None)
    prefix_node = kw.get("prefix", args[1] if len(args) > 1 else None)
    d = _const_str(dir_node) if dir_node is not None else None
    if d is not None and _under_tmp(d):
        return True
    p = _const_str(prefix_node) if prefix_node is not None else None
    return p is not None and p.startswith("/") and _under_tmp(os.path.dirname(p) or "/")


class _Finder(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel, self.stack, self.keys = rel, [], []

    def _scope(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scope

    def visit_Call(self, node: ast.Call):
        if _is_mkdtemp(node) and _hits_tmp(node):
            fn = ".".join(self.stack) or "<module>"
            self.keys.append(f"{self.rel}::{fn}::{ast.unparse(node)}")
        self.generic_visit(node)


def census_sites(root: Path) -> Counter:
    """`key -> count` for every `/tmp` mkdtemp under `<root>/tests/**/*.py`, outside the exempt
    dirs. Raises on a file that does not parse (a census that skips a file is blind there)."""
    out: Counter = Counter()
    for f in sorted((root / "tests").rglob("*.py")):
        rel = f.relative_to(root).as_posix()
        if "__pycache__" in rel or any(rel.startswith(d) for d in EXEMPT_DIRS):
            continue
        with warnings.catch_warnings():
            # another file's invalid escape in a plain string is not this census's finding
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(f.read_text(), filename=str(f))
        fd = _Finder(rel)
        fd.visit(tree)
        out.update(fd.keys)
    return out


def load_allow(path: Path) -> Counter:
    data = json.loads(path.read_text())
    entries = data["entries"]
    assert isinstance(entries, list), f"{path}: `entries` must be a list"
    for e in entries:
        assert isinstance(e, dict) and e.get("key") and e.get("reason"), (
            f"{path}: every entry needs a `key` and a `reason`: {e!r}")
    return Counter(e["key"] for e in entries)


def census(root: Path, allow: Counter) -> "tuple[list, list]":
    """(new, stale): sites beyond the allow list, and allow entries with no site left."""
    sites = census_sites(root)
    new = sorted((sites - allow).elements())
    stale = sorted((allow - sites).elements())
    return new, stale


# ---- the tree ------------------------------------------------------------------------------

def test_the_tree_holds_no_tmp_root_outside_the_allow_list():
    """`#r5`: a `mkdtemp(` whose root is `/tmp` or `/private/tmp` outside the allow list fails,
    and so does an entry whose site no longer exists."""
    assert ALLOW.is_file(), (
        f"no {ALLOW.relative_to(_REPO)}: the tmp-root census has no list (task-29.4 #r5); "
        f"{sum(census_sites(_REPO).values())} /tmp roots under tests/ are unlisted")
    new, stale = census(_REPO, load_allow(ALLOW))
    assert not new, (f"{len(new)} test root(s) under /tmp outside the sandbox; use "
                     "rmx_sandbox.short_root(prefix) (task-29.4 #r5):\n  " + "\n  ".join(new[:40]))
    assert not stale, ("allow-list entries whose site is gone; delete them (the list only "
                       "shrinks):\n  " + "\n  ".join(stale))


def test_the_spawn_daemon_files_were_moved_onto_short_root():
    """`#r5`: the 28 files that call `spawn_daemon_subprocess` use `short_root` for their
    roots in this task, so the allow list -- the sites LEFT after they moved -- holds none of
    theirs. The set is found by reading the files (28 at f3709d2), not hard-coded."""
    spawners = sorted(
        f.relative_to(_REPO).as_posix() for f in (_REPO / "tests").glob("*.py")
        if "spawn_daemon_subprocess" in f.read_text() and f.name != Path(__file__).name)
    assert len(spawners) >= 28, spawners
    sites = census_sites(_REPO)
    left = sorted(k for k in sites if k.split("::", 1)[0] in spawners)
    assert not left, (f"{len(left)} /tmp root(s) remain in the files that spawn daemons "
                      f"({len({k.split('::', 1)[0] for k in left})} of {len(spawners)} "
                      "files); they move to rmx_sandbox.short_root:\n  " + "\n  ".join(left[:40]))


# ---- short_root ------------------------------------------------------------------------------

def test_short_root_is_fresh_under_the_sandbox_and_short():
    """`#r5`: `short_root(prefix)` returns a fresh, existing directory under
    `<sandbox root>/t/`; two calls differ; the socket path a store under it would use stays
    short (62 bytes for the untagged `/private/tmp/rmx-XXXXXXXX` root, plus the prefix)."""
    short_root = getattr(rmx_sandbox, "short_root", None)
    assert callable(short_root), "rmx_sandbox has no short_root(prefix) (task-29.4 #r5)"
    sb = Path(os.environ["RMX_SANDBOX_ROOT"]).resolve()
    a, b = Path(short_root("r1-")), Path(short_root("r1-"))
    assert a != b and a.is_dir() and b.is_dir(), (a, b)
    for p in (a, b):
        assert p.parent == sb / "t", f"{p} is not directly under {sb / 't'}"
        assert p.name.startswith("r1-"), p
    sock = a / "proj" / ".refmatrix" / "rmxd.sock"
    budget = 62 + len("r1-") + (len(str(sb)) - len("/private/tmp/rmx-XXXXXXXX"))
    assert len(str(sock)) <= budget and len(str(sock)) < 104, (
        f"{sock} is {len(str(sock))} bytes (budget {budget}; macOS sun_path ~104)")


# ---- must-fail cases on synthetic trees ------------------------------------------------------

def _tree(tmp_path: Path, files: dict) -> Path:
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
    return tmp_path


@pytest.mark.parametrize("src", [
    'import tempfile\ndef test_x():\n    tempfile.mkdtemp(prefix="r1-", dir="/tmp")\n',
    'import tempfile\ndef test_x():\n    tempfile.mkdtemp(dir="/private/tmp")\n',
    'import tempfile\ndef test_x():\n    tempfile.mkdtemp(dir="/tmp/")\n',
    'from tempfile import mkdtemp\ndef test_x():\n    mkdtemp(prefix="x")\n'
    'def helper():\n    mkdtemp("", "y", "/tmp")\n',
    'import tempfile\ndef test_x():\n    tempfile.mkdtemp(prefix="/tmp/bd.")\n',
    'import tempfile\nROOT = tempfile.mkdtemp(dir="/tmp")\n',
], ids=["dir-kw", "private-tmp", "trailing-slash", "positional-dir", "absolute-prefix",
        "module-level"])
def test_must_fail_a_tmp_root_outside_the_list(tmp_path, src):
    root = _tree(tmp_path, {"tests/test_synth.py": src})
    new, stale = census(root, Counter())
    assert len(new) == 1 and not stale, (new, stale)


@pytest.mark.parametrize("src", [
    'import tempfile\ndef test_x():\n    tempfile.mkdtemp(prefix="r1-")\n',
    'import os, tempfile\ndef test_x():\n    tempfile.mkdtemp(dir=os.environ["RMX_SANDBOX_ROOT"])\n',
    'import tempfile\ndef test_x():\n    tempfile.mkdtemp(prefix="/tmpfoo")\n',
], ids=["default-dir", "sandbox-root", "not-tmp"])
def test_must_pass_a_root_that_is_not_tmp(tmp_path, src):
    root = _tree(tmp_path, {"tests/test_synth.py": src})
    assert census(root, Counter()) == ([], [])


def test_must_fail_a_stale_entry(tmp_path):
    """The list is exact: an entry whose site is gone fails."""
    root = _tree(tmp_path, {"tests/test_synth.py": "def test_x():\n    pass\n"})
    key = 'tests/test_synth.py::test_x::tempfile.mkdtemp(dir="/tmp")'
    new, stale = census(root, Counter({key: 1}))
    assert stale == [key] and not new


def test_a_listed_site_passes_and_a_second_identical_one_fails(tmp_path):
    """The key has no line number; the count is the multiplicity, so a copy of a listed call
    in the same function is a new site."""
    one = 'import tempfile\ndef test_x():\n    tempfile.mkdtemp(dir="/tmp")\n'
    two = one + '    tempfile.mkdtemp(dir="/tmp")\n'
    key = "tests/test_synth.py::test_x::tempfile.mkdtemp(dir='/tmp')"
    root = _tree(tmp_path, {"tests/test_synth.py": one})
    assert census(root, Counter({key: 1})) == ([], [])
    (root / "tests" / "test_synth.py").write_text(two)
    new, stale = census(root, Counter({key: 1}))
    assert new == [key] and not stale


def test_the_suite_health_fixtures_are_exempt_and_no_other_fixture_dir_is(tmp_path):
    """`#r1-fixtures`: `tests/fixtures/suite_health/` is exempt by path; the same call one
    directory over fails."""
    src = 'import tempfile\ndef f():\n    tempfile.mkdtemp(dir="/tmp")\n'
    root = _tree(tmp_path, {"tests/fixtures/suite_health/case_x.py": src,
                            "tests/fixtures/other/helper.py": src})
    new, _ = census(root, Counter())
    assert new == ["tests/fixtures/other/helper.py::f::tempfile.mkdtemp(dir='/tmp')"], new


def test_a_nested_function_is_keyed_by_its_whole_scope(tmp_path):
    src = ('import tempfile\nclass C:\n    def m(self):\n        def inner():\n'
           '            tempfile.mkdtemp(dir="/tmp")\n')
    root = _tree(tmp_path, {"tests/test_synth.py": src})
    new, _ = census(root, Counter())
    assert new == ["tests/test_synth.py::C.m.inner::tempfile.mkdtemp(dir='/tmp')"], new
