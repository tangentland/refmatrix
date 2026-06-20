"""Phase 5: message bus + refinement queue + hub streaming."""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest

from refmatrix import bus as busmod
from refmatrix import discovery, hub


@pytest.fixture
def home(monkeypatch):
    d = tempfile.mkdtemp(prefix="rh", dir="/tmp")
    monkeypatch.setenv("RMX_HOME", d)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ---- Bus unit ----


def test_publish_persists_and_history(home):
    b = busmod.Bus()
    b.publish("proj:x:topic", "hello", sender="a", project="x", mtype="note")
    hist = b.history("proj:x:topic")
    assert len(hist) == 1 and hist[0]["body"] == "hello"
    chans = {c["channel"] for c in b.channels()}
    assert "proj:x:topic" in chans


def test_subscriber_receives_matching(home):
    b = busmod.Bus()
    sub = b.subscribe(["global:"])
    b.publish("global:alerts", "hi", mtype="note")
    b.publish("proj:y:z", "no", mtype="note")  # shouldn't match
    got = sub.q.get(timeout=1)
    assert got["body"] == "hi"
    assert sub.q.empty()


def test_pattern_matching():
    assert busmod._matches("*", "anything")
    assert busmod._matches("global:", "global:x")
    assert busmod._matches("proj:a*", "proj:abc")
    assert not busmod._matches("global:", "proj:x")
    assert busmod._matches("exact", "exact")
    assert not busmod._matches("exact", "exact2")


def test_announce_enqueues_refinement(home):
    b = busmod.Bus()
    b.publish("global:decisions", "use duckdb", mtype="decision")
    b.publish("global:chat", "just chatting", mtype="note")  # not promoted
    q = b.refinement_queue("pending")
    assert len(q) == 1
    assert q[0]["scope"] == "global"
    assert q[0]["suggested"]["mtype"] == "feedback"
    assert "behavior" in q[0]["suggested"]["tags"]


def test_accept_refinement_writes_global_memory(home, monkeypatch):
    b = busmod.Bus()
    msg = b.publish("global:decisions", "always branch first", mtype="decision")
    res = b.accept_refinement(msg["id"])
    assert res["ok"] and res["memory_id"] > 0
    # candidate now accepted
    assert b.refinement_queue("pending") == []
    assert len(b.refinement_queue("accepted")) == 1
    # memory landed in the global store
    from refmatrix.store import Store
    s = Store(hub.global_store_root())
    s.init()
    with s.with_partition(hub.GLOBAL_PARTITION):
        rows = s.search_memories("branch first")
    s.close()
    assert any("branch first" in (r["content"] or "") for r in rows)


def test_reject_refinement(home):
    b = busmod.Bus()
    msg = b.publish("global:decisions", "x", mtype="decision")
    assert b.reject_refinement(msg["id"])["ok"]
    assert b.refinement_queue("pending") == []
    assert len(b.refinement_queue("rejected")) == 1


# ---- hub streaming ----


def test_hub_bus_stream_roundtrip(home, monkeypatch):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    h = hub.Hub(port=0)
    th = threading.Thread(target=h.serve_sock, daemon=True)
    th.start()
    for _ in range(50):
        if hub.hub_sock_path().exists():
            break
        time.sleep(0.05)
    received = []
    stop = threading.Event()

    def reader():
        for m in hub.subscribe_stream(["global:"]):
            received.append(m)
            if stop.is_set():
                break

    rt = threading.Thread(target=reader, daemon=True)
    rt.start()
    time.sleep(0.3)  # let the subscription register
    try:
        r = hub.rpc("bus_pub", {"channel": "global:t", "body": "ping", "type": "note"})
        assert r["ok"]
        for _ in range(40):
            if received:
                break
            time.sleep(0.05)
        assert received and received[0]["body"] == "ping"
    finally:
        stop.set()
        h._stop.set()
        th.join(timeout=3)
