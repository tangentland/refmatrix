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
    monkeypatch.setattr(wd, "_restart", lambda r, **kw: (restarts.append(r) or True))
    # The no-process branch kicks on the SECOND consecutive tick: a relaunch
    # in progress reads as "no process" while its pid file still names the
    # SIGTERMed pid, and the hub kicked five of those inside launchd's
    # ThrottleInterval (plan-4 r3 #s-3). This test ticked once and had been
    # red since that change landed (bug-034).
    wd.tick()
    assert restarts == [], "first no-process tick arms the counter, never kicks"
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
    monkeypatch.setattr(wd, "_restart", lambda r, **kw: called.append(r))
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
    monkeypatch.setattr(wd, "_restart", lambda r, **kw: called.append(r))
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


def test_ensure_global_daemon(short_home):
    """Global store gets its OWN daemon; writes route through it (not a direct
    Store open) per the store-calls-via-daemon rule."""
    from refmatrix import daemon as daemon_mod
    assert hub.ensure_global_daemon() is True
    try:
        assert hub.global_store_root().is_dir()
        add = hub.global_call("memory_add", {
            "name": "behave", "content": "be terse", "mtype": "feedback",
            "tags": ["tone"]})
        assert add["ok"] and add["result"]["id"] > 0
    finally:
        daemon_mod.stop_daemon(hub.global_store_root())


def test_global_store_is_the_home_dir(monkeypatch, tmp_path):
    """The hub home (~/.refmatrix) IS the user-level global store — discovered,
    named "global" (not by its parent dir), and always present."""
    home = tmp_path / ".refmatrix"
    home.mkdir()
    monkeypatch.setenv("RMX_HOME", str(home))
    assert discovery.is_global_root(home) is True
    assert discovery.store_name(home) == "global"
    proj = tmp_path / "proj" / ".refmatrix"; proj.mkdir(parents=True)
    assert discovery.is_global_root(proj) is False
    # global is always discovered, alongside any registered project
    discovery.register_root(proj)
    roots = {str(r) for r in discovery.discover_roots()}
    assert str(home.resolve()) in roots   # the global/home store
    assert str(proj.resolve()) in roots


def test_registry_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    r = tmp_path / "p" / ".refmatrix"
    r.mkdir(parents=True)
    discovery.register_root(r)
    assert str(r.resolve()) in discovery.load_registry()
    discovery.unregister_root(r)
    assert str(r.resolve()) not in discovery.load_registry()


# ---- port-orphan reap + start preflight (the 7777-wedge fixes) ----


def test_pid_on_port_parses_lsof(monkeypatch):
    import subprocess
    class R:
        stdout = "12345\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert hub._pid_on_port(7777) == 12345


def test_pid_on_port_none_when_free(monkeypatch):
    import subprocess
    class R:
        stdout = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert hub._pid_on_port(7777) is None


def test_stop_hub_reaps_port_orphan(monkeypatch):
    """A zombie hub whose control socket is dead (is_running False) but whose
    uvicorn still holds the port must be killed by port."""
    monkeypatch.setattr(hub, "is_running", lambda: False)
    monkeypatch.setattr(hub, "hub_pid", lambda: None)
    # Orphan present on first probe, gone after the SIGTERM.
    seen = {"n": 0}
    def fake_pid_on_port(port):
        seen["n"] += 1
        return 99999 if seen["n"] == 1 else None
    monkeypatch.setattr(hub, "_pid_on_port", fake_pid_on_port)
    killed = []
    monkeypatch.setattr(hub.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    assert hub.stop_hub() is True
    assert killed and killed[0][0] == 99999  # SIGTERM'd the orphan


def test_stop_hub_clean_when_nothing_running(monkeypatch):
    monkeypatch.setattr(hub, "is_running", lambda: False)
    monkeypatch.setattr(hub, "hub_pid", lambda: None)
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: None)
    assert hub.stop_hub() is True
