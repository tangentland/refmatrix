"""Task 23.0 AC-3, amendment round 10 (#rev-amend-r10, d9bx): R4's two child extensions.

CPython imports ONE `sitecustomize`, so two other plans' test needs live in the sandbox's:
(a) `$RMX_SANDBOX_CONNECT_LOG` -- one `<path>\\t<pid>` line per AF_UNIX `socket.connect`,
written BEFORE the deny check, so a refused dial is logged too (19.0 AC-6f); (b)
`$RMX_SANDBOX_PRELOAD` -- an absolute `.py` run with `runpy.run_path` AFTER the refusal is
installed (21.3 AC-5); (c) the exits are asserted BY NAME (`rmx_sandbox.CHILD_EXIT`,
`rmx_sandbox.PRELOAD_EXIT`). Exactly one test pins their literal values, because a by-name
assertion cannot see a value change and 19.0 / 21.3 write "exits 86" in their control legs.

Started from ch-implementer's candidate (scratchpad `probe_ext.py`, 9 legs, verified at
7ba1dd4 by probe: RED 8 failed / 1 passed at 26f80f2's `rmx_sandbox.py`, mutations MX1-MX9
killed). Committed by ch-test-engineer, 2026-10-15. Changes: listener dirs live under the
sandbox root and are removed in a `finally` (the candidate left `/tmp/sx*` behind), and a
SystemExit preload leg.

Every test calls `_require_sandbox()` before a child dials anything: at a HEAD without the
sandbox it fails there and no child reaches a live path. Mutation runs of this file go through
the d9bo #3 decoy-home gate (the "real" hub socket is then a listening decoy).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import rmx_sandbox  # on sys.path via tests/conftest.py (tests/sandbox_site)

DIAL = ("import socket, sys\n"
        "s = socket.socket(socket.AF_UNIX)\n"
        "s.settimeout(2.0)\n"
        "s.connect(sys.argv[1])\n"
        "print('CONNECTED')\n")


def _require_sandbox() -> Path:
    root = os.environ.get("RMX_SANDBOX_ROOT")
    assert root and Path(root).is_dir(), "no sandbox; refusing to spawn a child at a live path"
    return Path(root)


def _real_hub_sock() -> str:
    """The protected home's hub socket (`RMX_SANDBOX_REAL_HOME`: the live home in a normal
    run, the decoy home under the d9bo #3 mutation gate)."""
    return os.path.join(os.environ["RMX_SANDBOX_REAL_HOME"], ".refmatrix", "hub.sock")


def _child(args, cwd=None, **extra):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=60,
                          cwd=cwd, env={**os.environ, **extra})


@pytest.fixture
def short_dir():
    """A short dir for a unix-socket listener (`sun_path` ~104 bytes; pytest's `tmp_path` is
    too long on macOS). Under the sandbox root, and removed even when the test fails."""
    d = tempfile.mkdtemp(dir=str(_require_sandbox()), prefix="sx")
    try:
        yield d
    finally:
        shutil.rmtree(d)


# ---- (a) the connect log ----------------------------------------------------------------


def test_connect_log_writes_one_line_for_an_allowed_socket(tmp_path, short_dir):
    path = os.path.join(short_dir, "ok.sock")
    srv = socket.socket(socket.AF_UNIX)
    try:
        srv.bind(path)
        srv.listen(4)
        log = tmp_path / "connect.log"
        r = _child(["-c", DIAL, path], RMX_SANDBOX_CONNECT_LOG=str(log))
    finally:
        srv.close()
    assert r.returncode == 0 and "CONNECTED" in r.stdout, r.stderr[-2000:]
    lines = log.read_text().splitlines()
    assert len(lines) == 1, lines
    target, pid = lines[0].split("\t")
    assert target == path and pid.isdigit(), lines


@pytest.mark.sandbox_probe
def test_a_refused_dial_is_logged_and_exits_child_exit(tmp_path):
    _require_sandbox()
    log = tmp_path / "connect.log"
    hub = _real_hub_sock()
    r = _child(["-c", DIAL, hub], RMX_SANDBOX_CONNECT_LOG=str(log))
    assert r.returncode == rmx_sandbox.CHILD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "SandboxViolation" in r.stderr
    assert "CONNECTED" not in r.stdout
    assert [ln.split("\t")[0] for ln in log.read_text().splitlines()] == [hub]


def test_a_connect_log_inside_the_deny_set_exits_child_exit():
    """The log is written with the hook's re-entry guard up (unchecked), so a log path in the
    deny set would be an unrefused write into a live store: refused at install instead."""
    _require_sandbox()
    denied = os.path.join(os.environ["RMX_SANDBOX_REAL_HOME"], ".refmatrix", "connect.log")
    r = _child(["-c", "print('RAN')"], RMX_SANDBOX_CONNECT_LOG=denied)
    assert r.returncode == rmx_sandbox.CHILD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "RAN" not in r.stdout
    assert not os.path.exists(denied)


def test_connect_log_ignores_tcp(tmp_path):
    """Negative control: only AF_UNIX connects are logged (passes without the feature)."""
    _require_sandbox()
    srv = socket.socket(socket.AF_INET)
    try:
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        log = tmp_path / "connect.log"
        code = ("import socket, sys\n"
                "s = socket.socket(socket.AF_INET)\n"
                "s.connect(('127.0.0.1', int(sys.argv[1])))\n"
                "print('CONNECTED')\n")
        r = _child(["-c", code, str(port)], RMX_SANDBOX_CONNECT_LOG=str(log))
    finally:
        srv.close()
    assert r.returncode == 0 and "CONNECTED" in r.stdout, r.stderr[-2000:]
    assert not log.exists() or log.read_text() == "", log.read_text()


# ---- (b) the preload --------------------------------------------------------------------


@pytest.mark.sandbox_probe
def test_preload_runs_after_the_hook_and_cannot_bypass_it(tmp_path):
    _require_sandbox()
    marker = tmp_path / "preloaded"
    pre = tmp_path / "pre.py"
    pre.write_text(f"open({str(marker)!r}, 'w').close()\n")
    r = _child(["-c", DIAL, _real_hub_sock()], RMX_SANDBOX_PRELOAD=str(pre))
    assert marker.exists(), r.stderr[-2000:]
    assert r.returncode == rmx_sandbox.CHILD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "CONNECTED" not in r.stdout


@pytest.mark.sandbox_probe
def test_a_preload_that_dials_a_denied_socket_is_refused(tmp_path):
    """The preload runs AFTER `install_from_env()`: its own dial is refused like the child's."""
    _require_sandbox()
    pre = tmp_path / "pre.py"
    pre.write_text("import socket\n"
                   "s = socket.socket(socket.AF_UNIX)\n"
                   "s.settimeout(2.0)\n"
                   f"s.connect({_real_hub_sock()!r})\n")
    r = _child(["-c", "print('RAN')"], RMX_SANDBOX_PRELOAD=str(pre))
    assert r.returncode == rmx_sandbox.CHILD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "SandboxViolation" in r.stderr and "RAN" not in r.stdout


def test_a_preload_that_raises_exits_preload_exit(tmp_path):
    _require_sandbox()
    pre = tmp_path / "pre.py"
    pre.write_text("raise RuntimeError('preload-boom')\n")
    r = _child(["-c", "print('RAN')"], RMX_SANDBOX_PRELOAD=str(pre))
    assert r.returncode == rmx_sandbox.PRELOAD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "RuntimeError" in r.stderr and "preload-boom" in r.stderr
    assert "RAN" not in r.stdout


def test_a_preload_that_calls_sys_exit_exits_preload_exit(tmp_path):
    """SystemExit included: a preload that exits 0 must not leave the child running half-set."""
    _require_sandbox()
    pre = tmp_path / "pre.py"
    pre.write_text("raise SystemExit(0)\n")
    r = _child(["-c", "print('RAN')"], RMX_SANDBOX_PRELOAD=str(pre))
    assert r.returncode == rmx_sandbox.PRELOAD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "SystemExit" in r.stderr and "RAN" not in r.stdout


def test_a_relative_preload_exits_preload_exit(tmp_path):
    _require_sandbox()
    (tmp_path / "pre.py").write_text("pass\n")
    r = _child(["-c", "print('RAN')"], cwd=str(tmp_path), RMX_SANDBOX_PRELOAD="pre.py")
    assert r.returncode == rmx_sandbox.PRELOAD_EXIT, (r.returncode, r.stderr[-2000:])
    assert "RAN" not in r.stdout


# ---- (c) the one literal pin ------------------------------------------------------------


def test_the_named_exits_are_86_and_87():
    """The ONLY literal assertion of the exit codes in this file: 19.0 AC-6f and 21.3 AC-5 name
    86 in their control legs, so the value is an interface."""
    assert rmx_sandbox.CHILD_EXIT == 86
    assert rmx_sandbox.PRELOAD_EXIT == 87
