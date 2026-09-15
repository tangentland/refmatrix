"""plan-4 task 4.1 — a READ surface never kills the daemon.

2026-09-14: every `rmx grep` miss called `learn_from_grep`, which upserted
entities under a drifted PK index; the fatal fast-exited the daemon, launchd
respawned it, the next grep killed it again (39 runs)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix.store import Store


class _Fatal(Exception):
    pass


@pytest.fixture
def d():
    base = Path(tempfile.mkdtemp(prefix="rmxg-"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    Store(root).init()
    daemon = dm.Daemon(root)
    daemon.store = Store(root); daemon.store.init()
    daemon._request_snapshot = lambda: None
    yield daemon
    daemon.store.close()
    import shutil
    shutil.rmtree(base, ignore_errors=True)


def test_learn_from_grep_degrades_instead_of_fast_exiting(d, monkeypatch):
    def boom(store, pattern, hits, project_root):
        raise _Fatal("FATAL Error: Invalid Input Error: Failed to delete all rows from index. Only deleted 0 out of 1 rows.")
    monkeypatch.setattr(dm, "_learn_grep_hits", boom)
    exited = {"n": 0}
    monkeypatch.setattr(dm.os, "_exit", lambda code: exited.__setitem__("n", exited["n"] + 1))
    res = dm._op_learn_from_grep(d, {"pattern": "x", "hits": [{"file": "a.py", "line": 1}],
                                     "project_root": str(d.root.parent)})
    assert res == {"added": 0, "skipped": "store-invalid"}
    assert exited["n"] == 0, "a read must never take the daemon down"
    marker = d.root / "repair.needed"
    assert marker.exists()
    body = json.loads(marker.read_text())
    assert body["table"] == "entities" and body["op"] == "learn_from_grep"


def test_learn_from_grep_non_fatal_errors_still_raise(d, monkeypatch):
    monkeypatch.setattr(dm, "_learn_grep_hits", lambda *a: (_ for _ in ()).throw(ValueError("bad pattern")))
    with pytest.raises(ValueError):
        dm._op_learn_from_grep(d, {"pattern": "x", "hits": [{"file": "a.py", "line": 1}]})
    assert not (d.root / "repair.needed").exists()
