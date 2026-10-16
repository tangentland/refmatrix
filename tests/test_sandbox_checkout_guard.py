"""Task 23.0 R9 and AC-6: the checkout guard stops a mis-pointed run before the sandbox.

CHARACTERIZATION, not TDD: the guard shipped in bug-109's 54e13c6 (d9w), so this test passes
at HEAD. It is proven by AC-6's pre-registered mutation instead of a RED run: compare against
`_REPO` without `/src` in `_assert_tested_code_is_this_checkout` -> the decoy session collects,
and this test fails.

The inner session is a copy of this checkout's test support (conftest + every non-test file
under tests/, + tools/pyc_guard.py) under a pytester tmp tree whose `src/` is a symlink to the
real `src/`, plus a decoy `refmatrix` package at the tmp root. pytester's subprocess puts its
cwd first on PYTHONPATH, so the decoy is what `import refmatrix` finds.
"""
from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path

pytest_plugins = ["pytester"]

_REPO = Path(__file__).resolve().parents[1]


def _copy_support(dst: Path) -> None:
    tests = dst / "tests"
    tests.mkdir()
    for p in (_REPO / "tests").iterdir():
        if p.name == "__pycache__" or (p.is_file() and p.name.startswith("test_")):
            continue
        if p.is_dir():
            shutil.copytree(p, tests / p.name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(p, tests / p.name)
    (dst / "tools").mkdir()
    shutil.copy2(_REPO / "tools" / "pyc_guard.py", dst / "tools" / "pyc_guard.py")
    (dst / "src").symlink_to(_REPO / "src")


def test_decoy_refmatrix_fails_with_usage_error_before_collection(pytester, monkeypatch):
    """AC-6: an inner session that imports `refmatrix` from a decoy tree fails with
    `pytest.UsageError` naming both paths, before any test is collected -- and (R9: the
    guard is the conftest's FIRST statement after `_REPO`) before the sandbox is made."""
    root = pytester.path
    _copy_support(root)
    decoy = root / "refmatrix"
    decoy.mkdir()
    (decoy / "__init__.py").write_text("__version__ = 'decoy'\n")
    (root / "tests" / "test_decoy_inner.py").write_text("def test_never_collected():\n"
                                                         "    assert True\n")
    tag = secrets.token_hex(3)
    monkeypatch.setenv("RMX_SANDBOX_TAG", tag)

    result = pytester.runpytest_subprocess("tests", "-p", "no:cacheprovider", timeout=300)
    err = result.stderr.str() + result.stdout.str()
    assert result.ret == 4, f"expected a usage error (4), got {result.ret}:\n{err[-3000:]}"
    assert "UsageError" in err or "ERROR:" in err, err[-3000:]
    assert str(decoy.resolve()) in err, f"decoy path not named:\n{err[-3000:]}"
    assert str(root.resolve() / "src") in err, f"checkout path not named:\n{err[-3000:]}"
    assert "test_never_collected" not in err and "collected" not in err, err[-3000:]
    leaked = sorted(Path("/tmp").glob(f"rmx-{tag}-*"))
    assert not leaked, f"a mis-pointed run reached the sandbox: {leaked}"
