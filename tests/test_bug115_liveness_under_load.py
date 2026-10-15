"""bug-115 / bug-116: liveness must not queue behind work, and abandoned work must not run.

2026-10-15 00:13:18 the hub watchdog SIGTERMed the refmatrix daemon: three missed pings and a
heartbeat older than 60 s. At 00:16:52-00:17:44 it stalled again for 52 s and recovered on its
own. Both pings and the heartbeat ride the 4-worker cli pool: `ping` is in `CLI_OPS`, and the
heartbeat is a no-op submitted to that pool, FIFO behind every queued read. cli.log for the same
hour: `scan-prompt` p50 4.1 s / p95 18.6 s, `memory recall` p50 1.5 s, from up to seven agents'
hooks at once — four slow reads fill the pool, and liveness waits behind the queue.

Two client-side faults feed the queue (bug-116): `daemon.call` RETRIES a socket timeout, re-sending
a request the daemon already queued (so a hook's `--timeout 5` became 15 s and three copies of the
work), and the daemon runs a queued request whose caller has already given up.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import search_hooks


def _daemon(tmp_path) -> dm.Daemon:
    root = tmp_path / ".refmatrix"
    root.mkdir()
    d = dm.Daemon(root)
    d._log = lambda m: None
    return d


def _dispatch_async(d, req: dict, cli_pool, bg_pool):
    """Send `req` through the real `_handle` on its own thread; return (thread, box)."""
    a, b = socket.socketpair()
    a.sendall((json.dumps(req) + "\n").encode())
    box: dict = {}

    def run():
        d._handle(b, cli_pool, bg_pool)
        b.close()
        try:
            a.settimeout(5)
            box["resp"] = json.loads(a.recv(65536).decode().strip() or "null")
        except Exception as e:  # noqa: BLE001 — the test reads box
            box["err"] = e
        a.close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, box


def test_ping_answers_while_every_cli_worker_is_busy(tmp_path):
    """The hub decides wedged-vs-busy by ping. A ping that waits for a cli worker reads a
    BUSY daemon as dead, which is the 00:13:18 restart."""
    d = _daemon(tmp_path)
    cli = ThreadPoolExecutor(max_workers=1)
    bg = ThreadPoolExecutor(max_workers=1)
    gate = threading.Event()
    cli.submit(gate.wait, 10)                 # the one cli worker is occupied
    try:
        t, box = _dispatch_async(d, {"op": "ping", "args": {}}, cli, bg)
        t.join(1.0)
        assert not t.is_alive(), "ping waited behind a busy cli worker"
        assert box.get("resp", {}).get("ok") is True, box
    finally:
        gate.set()
        cli.shutdown(wait=True)
        bg.shutdown(wait=True)


def test_heartbeat_stays_fresh_while_a_deep_queue_is_draining(tmp_path, monkeypatch):
    """A pool that completes work every 0.1 s is alive. At HEAD the heartbeat's no-op joins
    the BACK of the queue, so a queue deeper than the stale window reads as a wedge even
    though work is finishing the whole time."""
    monkeypatch.setenv("RMX_HEARTBEAT_S", "0.05")
    d = _daemon(tmp_path)
    cli = ThreadPoolExecutor(max_workers=1)
    bg = ThreadPoolExecutor(max_workers=1)
    d._cli_pool = cli

    import refmatrix.daemon as dmod
    calls = {"n": 0}

    def slow_read(dd, args):
        calls["n"] += 1
        time.sleep(0.1)
        return {"ok": 1}

    monkeypatch.setitem(dmod.OPS, "bug115_slow_read", slow_read)
    monkeypatch.setattr(dmod, "CLI_OPS", dmod.CLI_OPS | {"bug115_slow_read"})
    threads = [_dispatch_async(d, {"op": "bug115_slow_read", "args": {}}, cli, bg)[0]
               for _ in range(30)]           # ~3 s of queued work on one worker
    time.sleep(0.15)
    d._start_heartbeat()
    try:
        worst = 0.0
        t_end = time.monotonic() + 1.5
        while time.monotonic() < t_end:
            worst = max(worst, dm.heartbeat_age(d.root))
            time.sleep(0.05)
        assert calls["n"] >= 5, "control: the pool must be completing work"
        assert worst < 0.6, f"heartbeat went {worst:.2f}s stale while work was completing"
    finally:
        d._stop_heartbeat()
        for t in threads:
            t.join(10)
        cli.shutdown(wait=True)
        bg.shutdown(wait=True)


def test_a_request_whose_deadline_passed_in_the_queue_never_runs(tmp_path, monkeypatch):
    """bug-116: a hook that gave up after `--timeout 5` left its request queued; the daemon
    then spent a worker on an answer nobody would read."""
    d = _daemon(tmp_path)
    cli = ThreadPoolExecutor(max_workers=1)
    bg = ThreadPoolExecutor(max_workers=1)
    ran = []
    import refmatrix.daemon as dmod
    monkeypatch.setitem(dmod.OPS, "bug116_read", lambda dd, a: ran.append(1) or {"x": 1})
    monkeypatch.setattr(dmod, "CLI_OPS", dmod.CLI_OPS | {"bug116_read"})
    gate = threading.Event()
    cli.submit(gate.wait, 10)
    try:
        t, box = _dispatch_async(d, {"op": "bug116_read", "args": {}, "deadline_s": 0.2},
                                 cli, bg)
        time.sleep(0.5)                       # the caller's deadline has passed
        gate.set()
        t.join(3)
        time.sleep(0.2)
        assert ran == [], "the daemon ran a request after its caller's deadline"
        resp = box.get("resp") or {}
        assert resp.get("ok") is False and "deadline" in resp.get("error", ""), box
    finally:
        gate.set()
        cli.shutdown(wait=True)
        bg.shutdown(wait=True)


def test_a_request_inside_its_deadline_still_runs(tmp_path, monkeypatch):
    """Control for the test above: the deadline only drops LATE work."""
    d = _daemon(tmp_path)
    cli = ThreadPoolExecutor(max_workers=1)
    bg = ThreadPoolExecutor(max_workers=1)
    import refmatrix.daemon as dmod
    monkeypatch.setitem(dmod.OPS, "bug116_read", lambda dd, a: {"x": 1})
    monkeypatch.setattr(dmod, "CLI_OPS", dmod.CLI_OPS | {"bug116_read"})
    try:
        t, box = _dispatch_async(d, {"op": "bug116_read", "args": {}, "deadline_s": 5},
                                 cli, bg)
        t.join(3)
        assert box.get("resp") == {"ok": True, "result": {"x": 1}}, box
    finally:
        cli.shutdown(wait=True)
        bg.shutdown(wait=True)


def test_a_write_past_its_deadline_still_runs(tmp_path, monkeypatch):
    """The safety half of bug-116: a client that timed out on a WRITE has not withdrawn it
    (`focus summarize --promote` says "the daemon may still complete it"). Only reads drop."""
    d = _daemon(tmp_path)
    cli = ThreadPoolExecutor(max_workers=1)
    bg = ThreadPoolExecutor(max_workers=1)
    ran = []
    import refmatrix.daemon as dmod
    monkeypatch.setitem(dmod.OPS, "bug116_write", lambda dd, a: ran.append(1) or {"w": 1})
    gate = threading.Event()
    bg.submit(gate.wait, 10)
    try:
        t, box = _dispatch_async(d, {"op": "bug116_write", "args": {}, "deadline_s": 0.2},
                                 cli, bg)
        time.sleep(0.5)
        gate.set()
        t.join(3)
        assert ran == [1], "a write was dropped at its caller's deadline"
        assert box.get("resp") == {"ok": True, "result": {"w": 1}}, box
    finally:
        gate.set()
        cli.shutdown(wait=True)
        bg.shutdown(wait=True)


def _silent_server(path: Path):
    """Accepts, reads the request, never answers. Counts connections."""
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(path))
    srv.listen(8)
    seen = {"conns": 0, "reqs": []}
    held = []

    def loop():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            seen["conns"] += 1
            try:
                c.settimeout(2)
                seen["reqs"].append(json.loads(c.recv(65536).decode().splitlines()[0]))
            except Exception:  # noqa: BLE001
                pass
            held.append(c)

    threading.Thread(target=loop, daemon=True).start()
    return srv, seen


def test_call_does_not_resend_a_request_the_daemon_already_has(monkeypatch):
    """A socket timeout means the daemon RECEIVED the request and is still working (or
    queued). Re-sending it doubles the work and triples the caller's wait."""
    base = Path(tempfile.mkdtemp(prefix="b115-", dir="/tmp"))
    sock = base / "s.sock"
    monkeypatch.setattr(dm, "socket_path", lambda root: sock)
    srv, seen = _silent_server(sock)
    try:
        t0 = time.monotonic()
        with pytest.raises((socket.timeout, TimeoutError)):
            dm.call(base, "stats", {}, timeout=0.3, retries=2)
        took = time.monotonic() - t0
        assert seen["conns"] == 1, f"request sent {seen['conns']} times"
        assert took < 0.6, f"a 0.3 s timeout took {took:.2f}s"
    finally:
        srv.close()


def test_call_tells_the_daemon_how_long_it_will_wait(monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="b116-", dir="/tmp"))
    sock = base / "s.sock"
    monkeypatch.setattr(dm, "socket_path", lambda root: sock)
    srv, seen = _silent_server(sock)
    try:
        with pytest.raises((socket.timeout, TimeoutError)):
            dm.call(base, "stats", {}, timeout=0.3, retries=0)
        time.sleep(0.1)
        assert seen["reqs"] and seen["reqs"][0].get("deadline_s") == pytest.approx(0.3), seen
    finally:
        srv.close()


def test_grep_tool_teach_hook_stands_down_while_learning_is_off(tmp_path):
    """The user, 2026-10-15: the grep->graph loop is off until plan 16's passive shim
    exists. The rewrite already honours `learn.off`; the Grep-tool teach hook spawned
    `rmx grep` regardless."""
    script = search_hooks.render_scripts(("/bin/false", "/bin/false"))[search_hooks.TEACH_NAME]
    hook = tmp_path / "teach.sh"
    hook.write_text(script)
    hook.chmod(0o755)
    home = tmp_path / "home"
    (home / ".refmatrix").mkdir(parents=True)
    (home / ".refmatrix" / "learn.off").touch()
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    calls = tmp_path / "calls"
    fake = tmp_path / "bin" / "rmx"
    fake.parent.mkdir()
    fake.write_text(f"#!/bin/sh\necho \"$@\" >> {calls}\n")
    fake.chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{fake.parent}:/usr/bin:/bin",
           "RMXGREP_RMX": str(fake)}
    payload = json.dumps({"tool_input": {"pattern": "foo", "path": str(proj)},
                          "cwd": str(proj)})
    r = subprocess.run([str(hook)], input=payload, text=True, env=env,
                       capture_output=True, timeout=10)
    assert r.returncode == 0, r.stderr
    time.sleep(0.5)                            # the spawn is detached
    assert not calls.exists(), f"teach hook ran rmx with learning off: {calls.read_text()}"
    # Control: without the marker the hook does spawn.
    (home / ".refmatrix" / "learn.off").unlink()
    subprocess.run([str(hook)], input=payload, text=True, env=env,
                   capture_output=True, timeout=10)
    time.sleep(0.5)
    assert calls.exists(), "control: the hook must spawn when learning is on"
