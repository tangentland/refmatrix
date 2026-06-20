"""Phase 3: hub watchdog + control-socket RPC + global store + discovery."""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest

from refmatrix import discovery, hub


@pytest.fixture
def short_home(monkeypatch):
    """A short RMX_HOME under /tmp — AF_UNIX socket paths cap at ~104 chars,
    and pytest's tmp_path is too deep for `<home>/hub.sock` to bind."""
    d = tempfile.mkdtemp(prefix="rh", dir="/tmp")
    monkeypatch.setenv("RMX_HOME", d)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def test_watchdog_restarts_down_daemon_when_auto(monkeypatch, tmp_path):
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    monkeypatch.setattr(discovery, "discover_roots", lambda: [root])
    monkeypatch.setattr(hub.daemon_mod, "ping", lambda r, timeout=0.5: False)
    restarts = []
    wd = hub.Watchdog()
    monkeypatch.setattr(wd, "_restart", lambda r: (restarts.append(r) or True))
    wd.tick()
    assert restarts == [root]
    h = wd.health()[str(root.resolve())]
    assert h["restart_count"] == 1
    assert h["history"][-1]["up"] is False and h["history"][-1]["restarted"]


def test_watchdog_manual_policy_observes_only(monkeypatch, tmp_path):
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    monkeypatch.setattr(discovery, "discover_roots", lambda: [root])
    monkeypatch.setattr(hub.daemon_mod, "ping", lambda r, timeout=0.5: False)
    wd = hub.Watchdog()
    wd.set_policy(root, "manual")
    called = []
    monkeypatch.setattr(wd, "_restart", lambda r: called.append(r))
    wd.tick()
    assert called == []  # manual = no restart
    assert wd.health()[str(root.resolve())]["restart_count"] == 0


def test_watchdog_up_daemon_no_restart(monkeypatch, tmp_path):
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    monkeypatch.setattr(discovery, "discover_roots", lambda: [root])
    monkeypatch.setattr(hub.daemon_mod, "ping", lambda r, timeout=0.5: True)
    wd = hub.Watchdog()
    called = []
    monkeypatch.setattr(wd, "_restart", lambda r: called.append(r))
    wd.tick()
    assert called == []
    assert wd.health()[str(root.resolve())]["history"][-1]["up"] is True


def test_control_socket_rpc_roundtrip(monkeypatch, short_home):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    h = hub.Hub(port=0)
    th = threading.Thread(target=h.serve_sock, daemon=True)
    th.start()
    # wait for sock
    for _ in range(50):
        if hub.hub_sock_path().exists():
            break
        time.sleep(0.05)
    try:
        assert hub.rpc("ping")["ok"] is True
        info = hub.rpc("hub_info")
        assert info["ok"] and info["result"]["home"] == str(short_home)
        # projects with empty discovery
        proj = hub.rpc("projects")
        assert proj["ok"] and proj["result"]["projects"] == []
        # unknown op
        bad = hub.rpc("nope")
        assert bad["ok"] is False
    finally:
        h._stop.set()
        th.join(timeout=3)


def test_set_watchdog_via_rpc(monkeypatch, short_home):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    h = hub.Hub(port=0)
    th = threading.Thread(target=h.serve_sock, daemon=True)
    th.start()
    for _ in range(50):
        if hub.hub_sock_path().exists():
            break
        time.sleep(0.05)
    try:
        r = hub.rpc("set_watchdog", {"root": "/x/.refmatrix", "policy": "manual"})
        assert r["ok"] and r["result"]["policy"] == "manual"
        assert h.watchdog.get_policy(Path("/x/.refmatrix")) == "manual"
    finally:
        h._stop.set()
        th.join(timeout=3)


def test_ensure_global_store(monkeypatch, tmp_path):
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    s = hub.ensure_global_store()
    try:
        assert hub.global_store_root().is_dir()
        eid = s.add_memory(name="behave", content="be terse", mtype="feedback",
                           tags=["tone"])
        assert eid > 0
        assert s.get_memory("behave")["content"] == "be terse"
    finally:
        s.close()


def test_registry_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    r = tmp_path / "p" / ".refmatrix"
    r.mkdir(parents=True)
    discovery.register_root(r)
    assert str(r.resolve()) in discovery.load_registry()
    discovery.unregister_root(r)
    assert str(r.resolve()) not in discovery.load_registry()
