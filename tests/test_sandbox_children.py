"""Task 23.0 R4 and AC-3: a child process a test spawns refuses live paths ITSELF.

bug-088's recorder patched `socket.socket.connect` in the pytest process and could not see a
spawned `rmx` at all. R4: every child inherits the sandbox env plus a `PYTHONPATH` entry for
`tests/sandbox_site/sitecustomize.py`, which installs the same audit hook from
`RMX_SANDBOX_ROOT` and exits the child nonzero with the violation on stderr.

Each test calls `_require_sandbox()` first: at a HEAD without the sandbox it fails there and no
child is ever spawned against a live path.

Mutation (AC-3, pre-registered): drop the `PYTHONPATH` entry -> the children connect (or fail
differently) and these tests fail. That mutation run reaches the live paths by design.
"""
from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _real_home() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def _require_sandbox() -> Path:
    root = os.environ.get("RMX_SANDBOX_ROOT")
    assert root, (
        "R1: RMX_SANDBOX_ROOT is unset -- no sandbox; refusing to spawn a child at a live path")
    assert Path(root).is_dir(), root
    return Path(root)


def test_children_get_the_sandbox_site_on_pythonpath():
    """R4: the inherited PYTHONPATH carries `tests/sandbox_site`, and its sitecustomize exists."""
    _require_sandbox()
    site = _REPO / "tests" / "sandbox_site"
    entries = [Path(p).resolve() for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    assert site.resolve() in entries, f"PYTHONPATH={os.environ.get('PYTHONPATH')!r}"
    assert (site / "sitecustomize.py").is_file()


def test_python_child_connecting_to_the_real_hub_socket_is_refused():
    """AC-3: `<venv>/bin/python -c` connecting to the real `~/.refmatrix/hub.sock` exits
    nonzero with SandboxViolation on stderr -- the refusal happens IN the child."""
    _require_sandbox()
    hub_sock = str(_real_home() / ".refmatrix" / "hub.sock")
    code = (
        "import socket\n"
        "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "s.settimeout(1.0)\n"
        f"s.connect({hub_sock!r})\n"
        "print('CONNECTED')\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode != 0, f"child exited 0: stdout={r.stdout!r}"
    assert "CONNECTED" not in r.stdout
    assert "SandboxViolation" in r.stderr, r.stderr[-2000:]


def test_rmx_child_on_the_repos_live_store_is_refused():
    """AC-3: `rmx` with REFMATRIX_ROOT at the repo's real `.refmatrix/` exits nonzero with
    SandboxViolation on stderr. `daemon status` reads the store's pid/marker files and pings
    its socket -- read-only even when the refusal is mutated away. A clone has no repo store,
    so there the real global home (also in the deny set) stands in for it."""
    _require_sandbox()
    target = _REPO / ".refmatrix"
    if not target.is_dir():
        target = _real_home() / ".refmatrix"
    rmx = shutil.which("rmx")
    assert rmx, "no rmx on PATH"
    env = dict(os.environ)
    env["REFMATRIX_ROOT"] = str(target)
    env["REFMATRIX_NO_TELEMETRY"] = "1"     # no cli.log row even if the refusal is mutated away
    r = subprocess.run([rmx, "daemon", "status"], capture_output=True, text=True, env=env,
                       timeout=120)
    assert r.returncode != 0, f"rmx exited 0 against {target}: {r.stdout[-1000:]!r}"
    assert "SandboxViolation" in r.stderr, r.stderr[-2000:]
