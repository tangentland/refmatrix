"""plan-4 task 4.4 — a supervised start adopts an unsupervised live daemon
instead of exiting 1 forever (orderly: 11,251 launchd spawns in 1.3 days)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from refmatrix import daemon as dm
from refmatrix.store import Store


def test_supervised_start_adopts_an_unsupervised_daemon():
    base = Path(tempfile.mkdtemp(prefix="rmxa-"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    try:
        d = dm.Daemon(root)
        logs = []
        d._log = lambda m: logs.append(m)
        adopted = d._adopt_unsupervised(dm.socket_path(root))
        assert adopted is True
        assert not dm.ping(root, timeout=0.5, retries=0)
        assert any("adopted unsupervised daemon" in m for m in logs)
    finally:
        dm.stop_daemon(root)
        shutil.rmtree(base, ignore_errors=True)


def test_adopt_is_a_noop_without_a_live_daemon():
    base = Path(tempfile.mkdtemp(prefix="rmxa-"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    d = dm.Daemon(root)
    assert d._adopt_unsupervised(dm.socket_path(root)) is False
    shutil.rmtree(base, ignore_errors=True)
