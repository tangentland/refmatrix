"""bug-253 (task-t0-suite-trust-sweep `#t0-2-bug253`; rulings L121, L122 M5, L123 M3): ONE
definition of "the dev `rmx`", and it is the interpreter running the suite.

WHY. The 29.4 stage-0 serial run in the no-venv clone `/Volumes/littlebig/refmatrix-r0` at
`4c6a0c6` errored in 127 tests on one E line, `AssertionError: dev rmx missing at
<clone>/.venv-eval/bin/rmx`, and failed 2 more for the same cause: the fixtures located the
subprocess `rmx` as `<checkout>/.venv-eval/bin/rmx`, and a littlebig clone has no venv of its
own (ORCHESTRATION runs clones with the dev tree's interpreter and `PYTHONPATH=<clone>/src`).
Eleven files under `tests/` named that path, each its own way; six of them SKIPPED instead of
erroring, which is why 18 pins existed in `tests/conftest.py` at all.

The fix (the bug row's own text): resolve the dev `rmx` from the bin directory of
`sys.executable`, with the checkout's `src` first on `PYTHONPATH` for the child, through ONE
helper the files share -- `tests/devbin.py`:
- `dev_bin() -> Path`: `Path(sys.executable).parent` (NOT resolved: a venv's `bin/python` is a
  symlink to the base interpreter, whose bin holds no `rmx`);
- `dev_rmx() -> Path`: `dev_bin() / "rmx"`;
- `dev_env(env=None) -> dict`: a COPY of `env` (default `os.environ`) whose `PYTHONPATH` has
  this checkout's `src` first and keeps the other absolute entries (the sandbox's
  `tests/sandbox_site` rides there); `os.environ` is not modified.

What is pinned here:
- the helper's three answers, and a real `rmx version -v` child through it reporting code
  from THIS checkout's `src`;
- convergence, statically: no file under `tests/` but the helper builds the
  `.venv-eval/bin` path (two exemptions by name, each with its reason); each of the eleven
  files imports the helper; the six that skipped carry no skip on a missing dev `rmx`;
- the pins follow the tests (R1.2): `tests/conftest.py`'s allowed set is built without the
  checkout venv (`tests/test_t0_skip_gate.py` asserts the hooks-only sets per layout);
- (in `tests/test_grep_learning_replay.py`) the eval harness that file's pinned node drives,
  `eval/production/grep_learning_replay.py`, names the same dev `rmx`, or the replay node cannot
  run in a clone once its skip is gone.
"""
from __future__ import annotations

import ast
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_TESTS = _REPO / "tests"
HELPER = _TESTS / "devbin.py"

# task-t0-suite-trust-sweep `#t0-2-bug253`, re-read at c4b44d0: the eleven files that look up
# the dev `rmx` (five errored in a no-venv clone, six skipped there holding the 18 pins).
ERRORING = ("test_bug240_ingest_file_arg.py", "test_bug240_ingest_file_arg_mcp.py",
            "test_bug241_r2_l112.py", "test_bug241_rule_docs_reingest.py",
            "test_scanorder_r2_l120.py")
SKIPPING = ("test_brief_real_daemon.py", "test_grep_argv_order_e2e.py",
            "test_grep_count_rows_e2e.py", "test_grep_evidence_verified.py",
            "test_grep_learning_replay.py", "test_grep_no_flag_bundle.py")
ELEVEN = ERRORING + SKIPPING

# Files that build a `.venv-eval/bin` path WITHOUT looking up the dev rmx; each is a fixture
# that MAKES a checkout layout, not a lookup.
NOT_A_LOOKUP = {
    "test_t0_skip_gate.py": "AC-1.2's fixture checkouts: it creates `.venv-eval/bin/rmx` in tmp "
                            "layouts to show the allowed set does not depend on them",
    "test_bug253_dev_bin.py": "this file: the patterns it scans for",
}

# A path into a checkout venv's bin dir, in the spellings the eleven used at c4b44d0, read from
# the CODE (comments and docstrings that tell the history are not lookups):
# `X / ".venv-eval" / "bin"`, a parts tuple `(".venv-eval", "bin", …)`, and a string literal
# holding `.venv-eval/bin`.
_VENV, _BIN = ".venv-eval", "bin"


def _div_chain(node) -> list:
    """The operands of an `a / b / c` chain, left to right."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _div_chain(node.left) + [node.right]
    return [node]


def _consecutive(nodes) -> bool:
    vals = [n.value if isinstance(n, ast.Constant) else None for n in nodes]
    return any(a == _VENV and b == _BIN for a, b in zip(vals, vals[1:]))


def venv_bin_lookups(src: str) -> list:
    """Line numbers where `src` builds a path into a checkout's `.venv-eval/bin`."""
    import warnings
    with warnings.catch_warnings():
        # another file's invalid escape in a plain string is not this scan's finding
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(src)
    docstrings = {id(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    hits = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) and _consecutive(_div_chain(n)):
            hits.add(n.lineno)
        elif isinstance(n, (ast.Tuple, ast.List)) and _consecutive(n.elts):
            hits.add(n.lineno)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and \
                id(n) not in docstrings and f"{_VENV}/{_BIN}" in n.value:
            hits.add(n.lineno)
    return sorted(hits)


def _helper():
    assert HELPER.is_file(), (
        f"no {HELPER.relative_to(_REPO)}: the dev rmx is still looked up by each file on its "
        "own (bug-253; task-t0-suite-trust-sweep #t0-2-bug253)")
    sys.path.insert(0, str(_TESTS)) if str(_TESTS) not in sys.path else None
    return importlib.import_module("devbin")


# ---- the helper ------------------------------------------------------------------------------

def test_the_dev_rmx_is_the_bin_dir_of_the_interpreter_running_the_suite():
    """The interpreter running the suite IS the dev interpreter (in the main tree that is
    `.venv-eval/bin/python`; in a clone it is the same file, found through `sys.executable`,
    never through the clone's own `.venv-eval`)."""
    db = _helper()
    want = Path(sys.executable).parent
    assert Path(db.dev_bin()) == want, (db.dev_bin(), want)
    assert Path(db.dev_rmx()) == want / "rmx", (db.dev_rmx(), want / "rmx")
    assert os.access(db.dev_rmx(), os.X_OK), f"{db.dev_rmx()} is not an executable rmx"
    assert ".venv-eval" not in HELPER.read_text().replace("`.venv-eval`", ""), (
        "the helper must not name a checkout's .venv-eval; it reads sys.executable")


def test_dev_env_puts_this_checkouts_src_first_and_keeps_absolute_entries():
    db = _helper()
    site = str(_TESTS / "sandbox_site")
    base = {"PYTHONPATH": os.pathsep.join([site, "/opt/elsewhere"]), "X": "1"}
    before = dict(os.environ)
    env = db.dev_env(base)
    assert env is not base and base["PYTHONPATH"] == os.pathsep.join([site, "/opt/elsewhere"])
    pp = env["PYTHONPATH"].split(os.pathsep)
    assert pp[0] == str(_REPO / "src"), pp
    assert site in pp and "/opt/elsewhere" in pp, pp
    assert env["X"] == "1"
    assert dict(os.environ) == before, "dev_env modified os.environ"
    assert db.dev_env()["PYTHONPATH"].split(os.pathsep)[0] == str(_REPO / "src")


def test_a_child_run_through_the_helper_runs_this_checkouts_code():
    """The point of the pair: `dev_rmx()` under `dev_env()` imports THIS checkout's
    `refmatrix` (in a clone, not the editable install's tree)."""
    db = _helper()
    # A wide COLUMNS: `rmx version -v` prints through rich, which wraps a long `code:` path onto
    # the next line under the default 80 columns (found on the mini lane's long checkout path,
    # bsd-t02 confirm-lite, 2026-11-15), and the line read below then holds no path.
    r = subprocess.run([str(db.dev_rmx()), "version", "-v"],
                       env=dict(db.dev_env(), COLUMNS="1000"),
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    code = next((ln for ln in r.stdout.splitlines() if ln.startswith("code:")), "")
    assert str(_REPO / "src" / "refmatrix") in code, (
        f"the dev rmx child ran code from elsewhere: {code!r}\n{r.stdout[-1500:]}")


# ---- convergence ------------------------------------------------------------------------------

def test_no_test_file_but_the_helper_looks_up_a_checkout_venv_bin():
    """One definition left, not two ([[feedback_converge_repeated_shapes]])."""
    found = []
    for f in sorted(_TESTS.rglob("*.py")):
        if "__pycache__" in f.parts or f == HELPER or f.name in NOT_A_LOOKUP:
            continue
        lines = f.read_text().splitlines()
        for n in venv_bin_lookups(f.read_text()):
            found.append(f"{f.relative_to(_REPO)}:{n}: {lines[n - 1].strip()}")
    assert not found, ("files that still build `<checkout>/.venv-eval/bin` themselves; they "
                       "use tests/devbin.py (bug-253):\n  " + "\n  ".join(found))


@pytest.mark.parametrize("src,hit", [
    ('RMX = REPO / ".venv-eval" / "bin" / "rmx"\n', True),
    ('B = Path(__file__).parents[1] / ".venv-eval" / "bin"\n', True),
    ('assert p.parts[-3:] == (".venv-eval", "bin", "rmx")\n', True),
    ('x = "/repo/.venv-eval/bin/python"\n', True),
    ('(root / ".venv-eval").symlink_to(prefix)\n', False),
    ('"""a docstring naming <checkout>/.venv-eval/bin/rmx"""\n', False),
    ('# a comment: .venv-eval/bin/rmx\nx = 1\n', False),
], ids=["div-chain", "div-chain-dir", "parts-tuple", "string", "symlink-fixture", "docstring",
        "comment"])
def test_the_lookup_scan_sees_each_spelling(src, hit):
    """Must-fail and must-pass cases for the scan itself, so a scan that stopped seeing a
    spelling is caught on input it must flag ([[feedback_clean_corpus_hides_a_dead_gate]])."""
    assert bool(venv_bin_lookups(src)) is hit, (src, venv_bin_lookups(src))


def _imports_devbin(src: str) -> bool:
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import) and any(
                a.name in ("devbin", "tests.devbin") for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module in ("devbin", "tests.devbin"):
            return True
    return False


# A test file that reaches the helper THROUGH the harness it drives (ch-bsd r1 MEH-3, ruling
# L169): `test_grep_learning_replay.py` imports `eval/production/grep_learning_replay.py`, which
# loads tests/devbin.py by path (ruling L142 (1)); it has no lookup of its own to convert.
VIA_HARNESS = {"test_grep_learning_replay.py":
               ("grep_learning_replay", _REPO / "eval" / "production" / "grep_learning_replay.py")}


def _imports_module(src: str, module: str) -> bool:
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import) and any(a.name == module for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == module:
            return True
    return False


def _ends_in_devbin(node, assigns: dict, depth: int = 0) -> bool:
    """`node` is a path expression whose last component is "devbin.py": a string ending in it,
    an `a / … / "devbin.py"` chain, or a name assigned one of those in the same scope."""
    if depth > 3:
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value == "devbin.py" or node.value.endswith("/devbin.py")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _ends_in_devbin(node.right, assigns, depth + 1)
    if isinstance(node, ast.Name) and node.id in assigns:
        return all(_ends_in_devbin(v, assigns, depth + 1) for v in assigns[node.id])
    return False


def _loads_devbin_by_path(src: str) -> bool:
    """The source loads tests/devbin.py by path: a `spec_from_file_location(name, path)` call
    whose OWN path argument ends in "devbin.py" (a literal, a `/` chain, or a name assigned one
    in the same scope). Naming devbin.py elsewhere while loading another file is not enough
    (red-t02's loads-another-file case, ruling L169 MEH-3)."""
    tree = ast.parse(src)
    scopes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for scope in scopes:
        assigns: dict = {}
        body = list(ast.walk(scope)) if scope is not tree else list(tree.body)
        for n in body:
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        assigns.setdefault(t.id, []).append(n.value)
        for n in ast.walk(scope):
            if not isinstance(n, ast.Call):
                continue
            if getattr(n.func, "attr", getattr(n.func, "id", "")) != "spec_from_file_location":
                continue
            arg = n.args[1] if len(n.args) > 1 else next(
                (k.value for k in n.keywords if k.arg == "location"), None)
            if arg is not None and _ends_in_devbin(arg, assigns):
                return True
    return False


def _uses_devbin(name: str, src: str) -> bool:
    if _imports_devbin(src):
        return True
    via = VIA_HARNESS.get(name)
    return via is not None and _imports_module(src, via[0]) and \
        _loads_devbin_by_path(via[1].read_text())


@pytest.mark.parametrize("name", ELEVEN)
def test_each_of_the_eleven_uses_the_helper(name):
    src = (_TESTS / name).read_text()
    assert _uses_devbin(name, src), (
        f"tests/{name} does not import tests/devbin.py; it looked up the dev rmx itself "
        "(bug-253, #t0-2-bug253)")


def _skip_reasons(src: str) -> list:
    """Every `reason=` string literal of a `skipif`/`skip` call, and every `pytest.skip("…")`
    message, in a source."""
    out = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if name not in ("skipif", "skip"):
            continue
        for kw in node.keywords:
            if kw.arg in ("reason", "msg") and isinstance(kw.value, ast.Constant):
                out.append(str(kw.value.value))
        if name == "skip" and node.args and isinstance(node.args[0], ast.Constant):
            out.append(str(node.args[0].value))
    return out


@pytest.mark.parametrize("name", SKIPPING)
def test_the_six_no_longer_skip_on_a_missing_dev_rmx(name):
    """`#t0-2-bug253`: a pinned file that uses the helper no longer skips for a missing
    checkout venv, so its `skipif` goes with its pin (R1.2: the pins follow the tests).
    `test_the_tool_itself_is_the_one_that_scrambles` keeps a skip for a missing `rg` only."""
    bad = [r for r in _skip_reasons((_TESTS / name).read_text())
           if re.search(r"\brmx\b|venv", r)]
    assert not bad, f"tests/{name} still skips on the dev rmx: {bad!r}"


def test_the_conftest_pins_no_venv_skip_and_tests_no_checkout_venv():
    """`#t0-2-bug253`: `_CLONE_ONLY_SKIPS` holds one entry, the hooks test, under R1.1's hooks
    condition; R1.1's venv condition guards nothing and is deleted."""
    src = (_TESTS / "conftest.py").read_text()
    assert "_VENV_RMX_PINS" not in src, "tests/conftest.py still carries the 18 venv pins"
    body = src.split("def allowed_skips", 1)[-1].split("\nALLOWED_SKIPS", 1)[0]
    assert ".venv-eval" not in body, (
        "allowed_skips still tests the checkout's .venv-eval:\n" + body)


# ---- the by-path branch must be able to fail (ch-bsd r1 MEH-3; lead, 2026-11-15) -------------

_HARNESS_SRC = {
    # loads tests/devbin.py by path: the one shape the branch accepts
    "loads-devbin": ('import importlib.util\nfrom pathlib import Path\n'
                     '_spec = importlib.util.spec_from_file_location(\n'
                     '    "devbin", Path(__file__).parents[2] / "tests" / "devbin.py")\n'
                     '_db = importlib.util.module_from_spec(_spec)\n'
                     '_spec.loader.exec_module(_db)\nRMX = _db.dev_rmx()\n'),
    # still builds the checkout venv path itself (the shape bug-253 removed)
    "own-lookup": ('from pathlib import Path\n'
                   'RMX = Path(__file__).parents[2] / ".venv-eval" / "bin" / "rmx"\n'),
    # loads SOME file by path and names devbin.py only in a string: no load of devbin
    "loads-another-file": ('import importlib.util\nfrom pathlib import Path\n'
                           'NOTE = "the dev rmx used to come from devbin.py"\n'
                           '_spec = importlib.util.spec_from_file_location(\n'
                           '    "other", Path(__file__).parent / "other.py")\n'
                           'RMX = Path("/usr/local/bin/rmx")\n'),
    # names devbin.py, loads nothing
    "names-only": ('DOC = "see tests/devbin.py"\n'
                   'RMX = "/usr/local/bin/rmx"\n'),
    # the string IS exactly "devbin.py" and the harness loads ANOTHER file by path: "names
    # devbin.py" and "calls spec_from_file_location" each hold, but not of the same call
    "loads-another-file-names-devbin-exactly": (
        'import importlib.util\nfrom pathlib import Path\n'
        'LEGACY = "devbin.py"\n'
        '_spec = importlib.util.spec_from_file_location(\n'
        '    "other", Path(__file__).parent / "other.py")\n'
        'RMX = Path("/usr/local/bin/rmx")\n'),
}


@pytest.mark.parametrize("harness,imports_it,ok", [
    ("loads-devbin", True, True),
    ("loads-devbin", False, False),
    ("own-lookup", True, False),
    ("loads-another-file", True, False),
    ("names-only", True, False),
    ("loads-another-file-names-devbin-exactly", True, False),
], ids=["loads-devbin", "harness-not-imported", "own-lookup", "loads-another-file",
        "names-only", "loads-another-file-names-devbin-exactly"])
def test_the_by_path_branch_accepts_only_a_harness_that_loads_devbin(tmp_path, monkeypatch,
                                                                    harness, imports_it, ok):
    """green-t02's fold (6bf0082, ch-bsd T0.2 r1 MEH-3) lets a test file pass the census when
    the harness it imports loads tests/devbin.py by path (`VIA_HARNESS`). A planted file whose
    harness does NOT load devbin by path must still fail; only the loading harness, actually
    imported, passes ([[feedback_clean_corpus_hides_a_dead_gate]]). The census's own data
    (`VIA_HARNESS`) is pointed at the planted harness; the census logic is not replaced."""
    mod = sys.modules[__name__]
    harness_file = tmp_path / "planted_harness.py"
    harness_file.write_text(_HARNESS_SRC[harness])
    monkeypatch.setitem(mod.VIA_HARNESS, "test_planted.py", ("planted_harness", harness_file))
    src = ("import planted_harness as h\n\n" if imports_it else "import os\n\n") + \
        "def test_x():\n    assert h.RMX\n"
    got = mod._uses_devbin("test_planted.py", src)
    assert got is ok, (
        f"harness {harness!r} (imported: {imports_it}) -> _uses_devbin {got}, expected {ok}: "
        + ("the by-path branch accepted a harness that does not load tests/devbin.py"
           if got else "the by-path branch refused a harness that loads tests/devbin.py"))
