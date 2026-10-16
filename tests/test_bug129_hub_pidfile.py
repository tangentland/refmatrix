"""bug-129: the live hub ran with no `~/.refmatrix/hub.pid`.

Measured cause (ch-bsd r1, 2026-10-16): `tests/test_hub.py`'s two `stop_hub`
tests ran without an `RMX_HOME`, so the real `stop_hub()` released the LIVE
pid file; a pytest session ran after hub 4191 started on 2026-10-15. Those
tests now run on `short_home`. The restart race first blamed (`rmx hub stop`
unlinking a successor's file) did not happen — cli.log shows the stop ended
4 s before 4191 existed — and is kept below as defence in depth, with the
second-hub path (a hub that fails its port check must leave the live hub's
file alone) and one owner for every hub.pid write or removal.
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
    hub.stop_hub(timeout=1.0)


def test_stop_hub_keeps_a_successors_pid_file(short_home, monkeypatch):
    hub.hub_pid_path().write_text(str(_dead_pid()))
    _stop_with_successor(monkeypatch, successor_pid=222)
    assert hub.hub_pid() == 222, "stop_hub deleted the pid file the successor wrote"


def _dead_pid() -> int:
    import subprocess
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def test_stop_hub_removes_the_stopped_hubs_pid_file(short_home, monkeypatch):
    dead = _dead_pid()  # the stopped hub has exited; stop_hub waits for that
    hub.hub_pid_path().write_text(str(dead))
    monkeypatch.setattr(hub, "is_running", lambda: False)
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: None)
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


def test_only_the_helpers_reach_the_pid_file():
    """One claim, one release and one reader own hub.pid. Any other reference
    to `hub_pid_path`, `HUB_PID` or the literal "hub.pid" anywhere in
    `src/refmatrix/` — an alias, `os.unlink(...)`, `hub_home() / HUB_PID` —
    is a path around the owner check (ch-bsd r1 s2)."""
    import ast
    # Owners are the four functions IN hub.py; a same-named function in any
    # other module is not exempt (ch-bsd r2 m1-r2).
    owners = {"_claim_pid_file", "_release_pid_file", "hub_pid", "hub_pid_path"}
    pkg = Path(hub.__file__).parent
    bad = []
    for f in sorted(pkg.rglob("*.py")):
        tree = ast.parse(f.read_text())
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        def owner(node):
            while node in parents:
                node = parents[node]
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return node.name
            return None

        for node in ast.walk(tree):
            hit = ((isinstance(node, ast.Name) and node.id in {"hub_pid_path", "HUB_PID"})
                   or (isinstance(node, ast.alias)
                       and node.name in {"hub_pid_path", "HUB_PID"})
                   or (isinstance(node, ast.Attribute)
                       and node.attr in {"hub_pid_path", "HUB_PID"})
                   or (isinstance(node, ast.Constant) and node.value == "hub.pid"))
            if not hit:
                continue
            where = owner(node)
            is_decl = (f.name == "hub.py" and where is None
                       and isinstance(parents.get(node), ast.Assign))
            if (f.name == "hub.py" and where in owners) or is_decl:
                continue
            bad.append(f"{f.relative_to(pkg)}:{node.lineno} ({where})")
    assert bad == [], f"hub.pid reached outside its owners: {bad}"


class _Reached(Exception):
    pass


def test_a_hub_that_loses_the_port_leaves_the_live_hubs_pid_file(short_home, monkeypatch):
    """A second hub (launchd while an unsupervised hub holds :7777, or
    `rmx ui` -> spawn_hub) must check the port before it claims hub.pid or
    starts anything; claiming first overwrote the live hub's pid and its
    shutdown then removed the file (ch-bsd r1 s1)."""
    hub.hub_pid_path().write_text("4191")
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: 4191)
    h = object.__new__(hub.Hub)
    h.port = 7777

    def reached():
        raise _Reached("the losing hub started its model workers")
    h._start_models = reached
    h._stop_models = lambda: None
    h.watchdog = SimpleNamespace(stop=lambda: None)
    hub.Hub.run(h, serve_http=True)
    assert hub.hub_pid() == 4191


def test_a_declined_release_is_logged(short_home, monkeypatch):
    lines = []
    monkeypatch.setattr(hub, "_log", lines.append)
    hub.hub_pid_path().write_text("222")
    assert hub._release_pid_file(111) is False
    assert any("hub.pid" in ln and "222" in ln for ln in lines), lines


def _hub_that_must_not_start():
    h = object.__new__(hub.Hub)
    h.port = 7777

    def reached():
        raise _Reached("this hub started its model workers")
    h._start_models = reached
    h._stop_models = lambda: None
    h.watchdog = SimpleNamespace(stop=lambda: None)
    return h


def test_a_hub_started_inside_the_live_hubs_startup_stands_down(short_home, monkeypatch):
    """The live hub binds the port last, so while it starts the port is free
    and ping fails; a second hub launched then (rmx ui, detached hub start)
    passed the preflight, overwrote hub.pid, and removed it on losing the
    uvicorn bind (ch-bsd r2 s1-r2). The live hub's lifetime lock on
    hub.lock is what stops it."""
    import fcntl
    hub.hub_pid_path().write_text("4191")
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: None)  # port not bound yet
    live = open(hub.hub_home() / "hub.lock", "a")
    try:
        fcntl.flock(live, fcntl.LOCK_EX | fcntl.LOCK_NB)  # the live hub holds it
        hub.Hub.run(_hub_that_must_not_start(), serve_http=True)
    finally:
        live.close()
    assert hub.hub_pid() == 4191


def test_a_headless_install_still_starts_when_the_port_is_held(short_home, monkeypatch):
    """Without the [ui] extra the hub never serves HTTP, so a held port is not
    its business: it supervises headless, as it did before the preflight moved
    (ch-bsd r2 m2-r2 a)."""
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: 4191)
    monkeypatch.setattr(hub, "_http_available", lambda: False)
    with pytest.raises(_Reached):
        hub.Hub.run(_hub_that_must_not_start(), serve_http=True)


def test_stop_hub_reports_an_unreadable_pid_file(short_home, monkeypatch):
    lines = []
    monkeypatch.setattr(hub, "_log", lines.append)
    monkeypatch.setattr(hub, "is_running", lambda: False)
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: None)
    hub.hub_pid_path().write_text("garbage")
    hub.stop_hub(timeout=0.5)
    assert any("hub.pid" in ln for ln in lines), lines


def test_a_forked_child_does_not_keep_the_hub_lock(short_home):
    """The hub forks without exec (`daemon.spawn_daemon` from the UI and the
    bus); O_CLOEXEC does not apply, so the child held a copy of hub.lock and a
    dead hub's lock outlived it, refusing every later hub (ch-bsd r3 b1-r3).
    The child must drop its copy at fork."""
    lock = hub._take_hub_lock()
    assert lock is not None
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        import time as _t
        os.write(w, b"x")  # the at-fork hooks have run by now
        _t.sleep(3)
        os._exit(0)
    os.close(w)
    try:
        assert os.read(r, 1) == b"x"
        assert hub._take_hub_lock() is None, "the child's fork hook released the hub's lock"
        lock.close()  # the hub dies without unlocking: the kernel closes its fd
        again = hub._take_hub_lock()
        assert again is not None, "a forked child still holds the dead hub's lock"
        hub._drop_hub_lock(again)
    finally:
        os.kill(pid, 9)
        os.waitpid(pid, 0)


def test_shutdown_releases_the_hub_lock(short_home):
    h = _bare_hub()
    h._lock = hub._take_hub_lock()
    hub.Hub.shutdown(h)
    again = hub._take_hub_lock()
    assert again is not None
    hub._drop_hub_lock(again)


def test_a_port_refusal_releases_the_hub_lock(short_home, monkeypatch):
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: 4191)
    monkeypatch.setattr(hub, "_http_available", lambda: True)
    hub.Hub.run(_hub_that_must_not_start(), serve_http=True)
    again = hub._take_hub_lock()
    assert again is not None
    hub._drop_hub_lock(again)


def test_stop_hub_waits_for_the_old_hub_to_exit(short_home, monkeypatch):
    """The socket and port go dark before the hub's 4-5 s model shutdown and
    its lock release; `stop_hub` reported stopped first, and a successor that
    is not the same launchd job then stood down (ch-bsd r3 s1-r3)."""
    import subprocess
    import threading
    old = subprocess.Popen(["sleep", "1.5"])
    threading.Thread(target=old.wait, daemon=True).start()  # reap, no zombie
    hub.hub_pid_path().write_text(str(old.pid))
    monkeypatch.setattr(hub, "is_running", lambda: False)
    monkeypatch.setattr(hub, "_pid_on_port", lambda port: None)
    try:
        assert hub.stop_hub(timeout=10.0) is True
        assert old.poll() is not None, "stop_hub returned while the old hub was alive"
    finally:
        old.kill()
