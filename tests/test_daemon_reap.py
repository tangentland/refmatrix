"""`Daemon._reap_predecessor` — smart launchd startup reaps orphan/wedged
predecessor daemons + stale sockets so a fresh launch always wins."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from refmatrix import daemon as dm
from refmatrix.daemon import Daemon


def _mkroot(tmp_path):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    return root


def test_reap_noop_when_no_predecessor(tmp_path):
    root = _mkroot(tmp_path)
    d = Daemon(root)
    assert d._reap_predecessor(dm.socket_path(root)) is True


def test_reap_clears_stale_socket(tmp_path):
    root = _mkroot(tmp_path)
    sock = dm.socket_path(root)
    sock.write_bytes(b"")                       # stale socket file, no listener
    dm.pid_path(root).write_text("999999")       # dead pid
    d = Daemon(root)
    assert d._reap_predecessor(sock) is True
    assert not sock.exists()                     # unlinked


def test_reap_kills_live_predecessor(tmp_path):
    root = _mkroot(tmp_path)
    # A live "daemon" that is NOT serving the socket — the wedged-predecessor
    # case. SIGTERM-able sleeper.
    proc = subprocess.Popen(["sleep", "120"])
    try:
        dm.pid_path(root).write_text(str(proc.pid))
        dm.socket_path(root).write_bytes(b"")    # stale socket, no listener
        d = Daemon(root)
        assert d._reap_predecessor(dm.socket_path(root)) is True
        # predecessor must be dead
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and proc.poll() is None:
            time.sleep(0.05)
        assert proc.poll() is not None           # reaped
        assert not dm.socket_path(root).exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_reap_does_not_kill_self(tmp_path):
    import os
    root = _mkroot(tmp_path)
    dm.pid_path(root).write_text(str(os.getpid()))   # pid file names US
    d = Daemon(root)
    # must return True and obviously not kill the test process
    assert d._reap_predecessor(dm.socket_path(root)) is True


def test_spawn_daemon_subprocess_starts_and_idempotent():
    """spawn_daemon_subprocess launches a real daemon via a fresh CLI process
    (no in-process fork) and is idempotent.

    Uses a SHORT mkdtemp root, not pytest's deep tmp_path: the daemon binds a
    unix socket at <root>/rmxd.sock and macOS caps sun_path at ~104 bytes, which
    pytest's nested basetemp blows past for a long test name."""
    import shutil
    import tempfile
    from refmatrix.store import Store
    base = Path(tempfile.mkdtemp())
    root = base / ".refmatrix"
    Store(root).init()
    try:
        pid = dm.spawn_daemon_subprocess(root, watch_root=[])
        assert pid and pid > 0
        assert dm.ping(root)
        pid2 = dm.spawn_daemon_subprocess(root, watch_root=[])  # already up
        assert pid2 == pid                                       # no new spawn
    finally:
        dm.stop_daemon(root)
        shutil.rmtree(base, ignore_errors=True)
    assert not dm.ping(root)
