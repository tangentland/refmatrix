"""bug-129: the live hub ran with no `~/.refmatrix/hub.pid`.

2026-10-15 01:58: an `rmx hub stop` asked the hub to stop, launchd respawned it
(pid 4191 wrote hub.pid at 01:58:42), and the stopper's poll loop then saw no
answering control socket — the successor had not bound it yet — and unlinked
the pid file unconditionally. The hub ran from then on with `hub_pid()` None.
`Hub.shutdown()` carried the same unconditional unlink. The rule both now keep:
a stopper removes the pid file only while it still names the pid it stopped.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from refmatrix import hub


@pytest.fixture
def short_home(monkeypatch):
    d = tempfile.mkdtemp(prefix="rh", dir="/tmp")
    monkeypatch.setenv("RMX_HOME", d)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _stop_with_successor(monkeypatch, *, successor_pid: int) -> None:
    """Run stop_hub while a successor hub writes its pid between the old
    hub's exit and the successor binding its control socket."""
    calls = {"n": 0}

    def is_running():
        calls["n"] += 1
        if calls["n"] == 1:
            return True  # the old hub answers; stop_hub sends `stop`
        # Old hub gone; launchd's successor has written its pid (once) but
        # not yet bound hub.sock, so nothing answers ping.
        if calls["n"] == 2:
            hub.hub_pid_path().write_text(str(successor_pid))
        return False

    monkeypatch.setattr(hub, "is_running", is_running)
    monkeypatch.setattr(hub, "rpc", lambda op, args=None, timeout=30.0: {"ok": True})
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: None)
    monkeypatch.setattr(hub.os, "kill", lambda pid, sig: None)
    hub.stop_hub(timeout=1.0)


def test_stop_hub_keeps_a_successors_pid_file(short_home, monkeypatch):
    hub.hub_pid_path().write_text("111")
    _stop_with_successor(monkeypatch, successor_pid=222)
    assert hub.hub_pid() == 222, "stop_hub deleted the pid file the successor wrote"


def test_stop_hub_removes_the_stopped_hubs_pid_file(short_home, monkeypatch):
    hub.hub_pid_path().write_text("111")
    monkeypatch.setattr(hub, "is_running", lambda: False)
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: None)
    monkeypatch.setattr(hub.os, "kill", lambda pid, sig: None)
    assert hub.stop_hub(timeout=1.0) is True
    assert not hub.hub_pid_path().exists()


def _bare_hub():
    h = object.__new__(hub.Hub)
    h._stop_models = lambda: None
    h.watchdog = SimpleNamespace(stop=lambda: None)
    return h


def test_shutdown_keeps_another_hubs_pid_file(short_home):
    hub.hub_pid_path().write_text("222")
    hub.Hub.shutdown(_bare_hub())
    assert hub.hub_pid() == 222, "shutdown deleted a pid file naming another hub"


def test_shutdown_removes_its_own_pid_file(short_home):
    hub.hub_pid_path().write_text(str(os.getpid()))
    hub.Hub.shutdown(_bare_hub())
    assert not hub.hub_pid_path().exists()


def test_only_the_helpers_write_or_remove_the_pid_file():
    """One claim and one release own hub.pid; a new stopper that unlinks it
    directly reopens bug-129."""
    import ast
    src = Path(hub.__file__).read_text()
    owners = {"_claim_pid_file", "_release_pid_file"}
    bad = []
    for fn in ast.walk(ast.parse(src)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name in owners:
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"unlink", "write_text", "replace", "rename"}
                    and "hub_pid_path" in ast.unparse(node.func.value)):
                bad.append(f"{fn.name}:{node.lineno}")
    assert bad == [], f"hub.pid touched outside its helpers: {bad}"
