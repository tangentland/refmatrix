"""bug-046 (ch-bsd #b-4): src/ must compile on the Python `pyproject` declares.

`requires-python = ">=3.10"`, but the workstation runs 3.14, so syntax newer
than the floor parses here and nobody notices. Two files had drifted:

    src/refmatrix/daemon.py:1325   multi-line quoted literal inside an f-string
    src/refmatrix/cctree.py:575    same quote character reused inside an f-string

Both are PEP 701, which is 3.12+. A 3.10 or 3.11 install would fail at IMPORT —
not at some edge case, but on `import refmatrix.daemon`, i.e. the daemon would
not start at all.

Why this is a subprocess test and not an `ast.parse(feature_version=(3, 10))`
one: `feature_version` does NOT reject PEP 701 — it was measured, and it parsed
the broken file happily. The only honest check is a real interpreter at the
floor, so the test finds one and skips loudly when there is none rather than
passing on a check it did not perform.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "refmatrix"


def _declared_floor() -> tuple:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*"[><=~^]*\s*(\d+)\.(\d+)', text)
    assert m, "pyproject.toml has no parseable requires-python"
    return int(m.group(1)), int(m.group(2))


def _floor_interpreter():
    major, minor = _declared_floor()
    if (major, minor) == sys.version_info[:2]:
        return sys.executable, (major, minor)
    for cand in (f"python{major}.{minor}", f"python{major}{minor}"):
        p = shutil.which(cand)
        if p:
            return p, (major, minor)
    for extra in ("/opt/local/bin", "/opt/homebrew/bin", "/usr/local/bin"):
        p = Path(extra) / f"python{major}.{minor}"
        if p.exists():
            return str(p), (major, minor)
    return None, (major, minor)


def test_every_src_module_compiles_on_the_declared_floor():
    exe, floor = _floor_interpreter()
    if exe is None:
        pytest.skip(
            f"no python{floor[0]}.{floor[1]} on this machine — the declared "
            f"floor cannot be checked here. This skip is the finding: install "
            f"it, or raise requires-python to a version that is checked."
        )
    # `pycache_prefix` sends the floor interpreter's bytecode to a scratch
    # tree instead of `src/refmatrix/__pycache__`. Without it this test writes
    # `*.cpython-310.pyc` into the repo, and bug-037's session guard — which
    # only recompiles for the RUNNING interpreter — then reports a stale pyc
    # under src/, failing `test_the_repo_tree_is_enforced_by_conftest` later in
    # the same suite. A guard that dirties the tree it guards is worse than no
    # guard (found by the full suite, 2026-09-17).
    with tempfile.TemporaryDirectory(prefix="rmxpyc") as cache:
        proc = subprocess.run(
            [exe, "-X", f"pycache_prefix={cache}", "-m", "compileall",
             "-q", str(_SRC)],
            capture_output=True, text=True,
        )
    if proc.returncode != 0:
        files = sorted(set(re.findall(r'File "([^"]+)", line (\d+)', proc.stdout + proc.stderr)))
        detail = "\n  ".join(f"{f}:{ln}" for f, ln in files) or (proc.stdout + proc.stderr)[:2000]
        pytest.fail(
            f"src/ does not compile on Python {floor[0]}.{floor[1]}, which "
            f"pyproject declares as supported:\n  {detail}\n"
            f"Either fix the syntax or raise requires-python — but do not leave "
            f"the declaration claiming a version that cannot import the daemon."
        )
