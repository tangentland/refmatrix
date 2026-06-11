"""memory_content is logged + replayed, and the writer-rotation swap is
retired by default.

Two coupled fixes for the body-loss-on-rotation class:

(a) `add_memory` writes the body sidecar AND a `memory_content` log event, so
    `apply_log_delta` / `rebuild_index_from_log` reconstruct bodies (previously
    only the entity row was logged — rebuilds produced content-less memories).

(b) The A/B replica swap (`_refresh_replica_now`) is a no-op by default. It
    used to promote a log-replayed inactive slot to writer; any under-logged
    state would vanish on the swap. Snapshot-tier is the read path, so pinning
    the writer to the last-known slot is safe. RMX_REPLICA_ROTATE=1 re-enables.
"""
from __future__ import annotations

from refmatrix.store import Store


def test_memory_content_event_is_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(name="m1", content="the body", mtype="project")
    log = s.log_path.read_text(encoding="utf-8")
    assert '"op": "memory_content"' in log
    assert '"the body"' in log
    s.close()


def test_memory_content_survives_rebuild_from_log(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(
        name="m1", content="durable body text",
        mtype="project", tags=["t1", "t2"], metadata={"k": "v"},
    )
    assert s.get_memory("m1")["content"] == "durable body text"

    res = s.rebuild_index_from_log()
    assert res.get("memory_content", 0) >= 1

    got = s.get_memory("m1")
    assert got is not None
    assert got["content"] == "durable body text"
    assert got["mtype"] == "project"
    assert got["tags"] == ["t1", "t2"]
    assert got["metadata"] == {"k": "v"}
    s.close()


def test_memory_content_latest_write_wins_on_rebuild(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(name="m1", content="first", mtype="project")
    s.add_memory(name="m1", content="second", mtype="project")
    s.rebuild_index_from_log()
    assert s.get_memory("m1")["content"] == "second"
    s.close()


def test_writer_rotation_swap_is_dropped(tmp_path):
    from refmatrix.daemon import Daemon

    s = Store(tmp_path / ".refmatrix")
    s.init()
    d = Daemon(tmp_path / ".refmatrix")
    d.store = s
    d._active_slot = "A"
    res = d._refresh_replica_now()
    # No swap: the writer stays on its slot.
    assert res.get("enabled") is False
    assert "dropped" in (res.get("reason") or "")
    assert d._active_slot == "A"
    s.close()
