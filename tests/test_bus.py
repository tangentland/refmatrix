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


def test_accept_refinement_writes_global_memory(home):
    import time
    from refmatrix import daemon as daemon_mod
    b = busmod.Bus()
    msg = b.publish("global:decisions", "always branch first", mtype="decision")
    try:
        res = b.accept_refinement(msg["id"])
        assert res["ok"] and res["memory_id"] > 0
        assert b.refinement_queue("pending") == []
        assert len(b.refinement_queue("accepted")) == 1
        # verify via the global daemon (no direct Store open — would contend
        # with the daemon's catalog lock)
        names = []
        for _ in range(20):
            found = hub.global_call("memory_search", {"query": "branch first", "limit": 5})
            names = [r["name"] for r in found.get("result", {}).get("rows", [])]
            if names:
                break
            time.sleep(0.2)
        assert names  # the promoted memory is retrievable from the global store
    finally:
        daemon_mod.stop_daemon(hub.global_store_root())


def test_reject_refinement(home):
    b = busmod.Bus()
    msg = b.publish("global:decisions", "x", mtype="decision")
    assert b.reject_refinement(msg["id"])["ok"]
    assert b.refinement_queue("pending") == []
    assert len(b.refinement_queue("rejected")) == 1


# ---- read cursor / maintenance ----


def test_read_advances_cursor(home):
    b = busmod.Bus()
    for i in range(3):
        b.publish("proj:x:t", f"m{i}", mtype="note")
    first = b.read("agent1", ["proj:x:"])
    assert [m["body"] for m in first] == ["m0", "m1", "m2"]
    assert b.read("agent1", ["proj:x:"]) == []          # cursor consumed all
    b.publish("proj:x:t", "m3", mtype="note")
    nxt = b.read("agent1", ["proj:x:"])
    assert [m["body"] for m in nxt] == ["m3"]
    # a different agent has its own cursor → sees everything unseen
    assert len(b.read("agent2", ["proj:x:"])) == 4


def test_read_peek_does_not_advance(home):
    b = busmod.Bus()
    b.publish("global:a", "hi", mtype="note")
    assert len(b.read("ag", ["global:"], peek=True)) == 1
    assert len(b.read("ag", ["global:"])) == 1          # still unread after peek


def test_read_n_caps_and_cursor_respects_cap(home):
    b = busmod.Bus()
    for i in range(5):
        b.publish("global:a", f"m{i}", mtype="note")
    got = b.read("ag", ["global:"], n=2)
    assert [m["body"] for m in got] == ["m0", "m1"]      # oldest-first, capped
    # cursor advanced only to the last RETURNED message, not the channel max
    assert [m["body"] for m in b.read("ag", ["global:"])] == ["m2", "m3", "m4"]


def test_mark_read_clears_unread(home):
    b = busmod.Bus()
    for i in range(3):
        b.publish("global:a", f"m{i}", mtype="note")
    b.mark_read("ag", "global:a")
    assert b.read("ag", ["global:"]) == []
    assert b.unread_count("ag").get("global:a", 0) == 0


def test_delete_hides_from_history_and_read(home):
    b = busmod.Bus()
    m = b.publish("global:a", "gone", mtype="note")
    b.publish("global:a", "stay", mtype="note")
    assert b.delete(m["id"])["deleted"] == 1
    bodies = [x["body"] for x in b.history("global:a")]
    assert bodies == ["stay"]
    assert [x["body"] for x in b.read("ag", ["global:"])] == ["stay"]


def test_archive_moves_aside_and_unarchive_restores(home):
    b = busmod.Bus()
    m = b.publish("global:a", "old", mtype="note")
    b.publish("global:a", "new", mtype="note")
    assert b.archive(msg_id=m["id"])["archived"] == 1
    assert [x["body"] for x in b.history("global:a")] == ["new"]
    assert [x["body"] for x in b.history("global:a", status="archived")] == ["old"]
    assert b.unarchive(m["id"])["restored"] == 1
    assert {x["body"] for x in b.history("global:a")} == {"old", "new"}


def test_archive_by_channel_before_ts(home):
    b = busmod.Bus()
    b.publish("global:a", "x", mtype="note")
    # before_ts far in the future archives everything in the channel
    n = b.archive(channel="global:a", before_ts="9999-01-01T00:00:00")["archived"]
    assert n == 1
    assert b.history("global:a") == []


def test_purge_hard_removes_deleted(home):
    b = busmod.Bus()
    m = b.publish("global:a", "x", mtype="note")
    b.delete(m["id"])
    assert b.purge()["purged"] == 1                      # default reaps deleted
    assert b.history("global:a", status="all") == []


def test_stats_reports_totals_and_unread(home):
    b = busmod.Bus()
    a = b.publish("global:a", "1", mtype="note")
    b.publish("global:a", "2", mtype="note")
    b.archive(msg_id=a["id"])
    st = b.stats(agent="ag")
    assert st["totals"].get("active") == 1
    assert st["totals"].get("archived") == 1
    assert st["unread"].get("global:a") == 1             # only the active one


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
