"""Phase 4: global behavior store (daemon-routed) + scope merge."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix import hub
from refmatrix.cli import _merge_scope


@pytest.fixture
def short_home(monkeypatch):
    d = tempfile.mkdtemp(prefix="rh", dir="/tmp")
    monkeypatch.setenv("RMX_HOME", d)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def test_merge_scope_project_only():
    p = [{"name": "a"}, {"name": "b"}]
    g = [{"name": "x"}]
    assert [r["name"] for r in _merge_scope(p, g, 10, "project")] == ["a", "b"]


def test_merge_scope_global_only():
    p = [{"name": "a"}]
    g = [{"name": "x"}, {"name": "y"}]
    assert [r["name"] for r in _merge_scope(p, g, 10, "global")] == ["x", "y"]


def test_merge_scope_both_round_robins():
    p = [{"name": "p1"}, {"name": "p2"}, {"name": "p3"}]
    g = [{"name": "g1"}, {"name": "g2"}]
    out = [r["name"] for r in _merge_scope(p, g, 10, "both")]
    assert out == ["p1", "g1", "p2", "g2", "p3"]  # interleaved, global guaranteed
    assert all(r.get("scope") for r in _merge_scope(p, g, 10, "both"))


def test_merge_scope_both_dedupes():
    p = [{"name": "shared"}, {"name": "p"}]
    g = [{"name": "shared"}, {"name": "g"}]
    out = [r["name"] for r in _merge_scope(p, g, 10, "both")]
    assert out.count("shared") == 1


def test_merge_scope_caps_at_k():
    p = [{"name": f"p{i}"} for i in range(10)]
    g = [{"name": f"g{i}"} for i in range(10)]
    assert len(_merge_scope(p, g, 5, "both")) == 5


def test_global_daemon_roundtrip(short_home):
    """Global add + recall route through the global store's OWN daemon — no
    direct Store opens (the store-calls-via-daemon rule)."""
    import time
    root = hub.global_store_root()
    try:
        assert hub.ensure_global_daemon() is True
        add = hub.global_call("memory_add", {
            "name": "be-terse", "content": "respond tersely",
            "mtype": "feedback", "tags": ["tone"]})
        assert add["ok"] and add["result"]["id"] > 0
        # the daemon's read mirror refreshes shortly after a write — poll
        names = []
        for _ in range(20):
            found = hub.global_call("memory_search", {"query": "tersely", "limit": 5})
            names = [r["name"] for r in found.get("result", {}).get("rows", [])]
            if "be-terse" in names:
                break
            time.sleep(0.2)
        assert "be-terse" in names
    finally:
        from refmatrix import daemon as daemon_mod
        daemon_mod.stop_daemon(root)
