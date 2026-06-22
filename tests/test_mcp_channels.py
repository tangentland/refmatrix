"""claude/channel capability: capability advertisement + the hub-bus → native
push-notification bridge. The hub stream itself is covered by the bus suite;
here we monkeypatch it to exercise the mapping + loop in isolation."""
from __future__ import annotations

import refmatrix.mcp as mcp
from refmatrix import hub as hub_mod


def test_initialize_advertises_channel_capability():
    resp = mcp.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    caps = resp["result"]["capabilities"]
    assert caps["tools"] == {}
    assert caps["experimental"]["claude/channel"] == {}


def test_notification_maps_body_and_meta():
    msg = {"channel": "proj:cliquedb:bugs", "from": "cliquedb-claude",
           "type": "announce", "id": "abc123", "ts": "2026-06-22T01:30:18",
           "body": "two tools threw KeyError", "project": None}
    n = mcp._channel_notification(msg)
    assert n["method"] == "notifications/claude/channel"
    assert n["params"]["content"] == "two tools threw KeyError"
    meta = n["params"]["meta"]
    assert meta["channel"] == "proj:cliquedb:bugs"
    assert meta["from"] == "cliquedb-claude"
    assert meta["id"] == "abc123"
    assert "project" not in meta  # None values dropped


def test_notification_json_encodes_dict_body():
    n = mcp._channel_notification({"channel": "global:queues", "body": {"k": 1}})
    assert n["params"]["content"] == '{"k": 1}'


def test_default_patterns_include_global():
    pats = mcp._channel_patterns()
    assert "global:*" in pats
    assert any(p.startswith("proj:") and p.endswith(":*") for p in pats)


def test_channel_loop_emits_each_bus_message(monkeypatch):
    sent: list[dict] = []

    def fake_emit(obj):
        sent.append(obj)
        mcp._CHANNEL_STOP.set()  # stop after the first message

    def fake_stream(patterns, history=0):
        assert patterns == ["proj:cliquedb:*"]
        yield {"channel": "proj:cliquedb:x", "from": "bob",
               "type": "announce", "id": "i1", "ts": "t", "body": "hi"}

    monkeypatch.setattr(mcp, "_emit", fake_emit)
    monkeypatch.setattr(mcp, "_channel_patterns", lambda: ["proj:cliquedb:*"])
    monkeypatch.setattr(hub_mod, "is_running", lambda: True)
    monkeypatch.setattr(hub_mod, "subscribe_stream", fake_stream)

    mcp._CHANNEL_STOP.clear()
    try:
        mcp._channel_loop()
    finally:
        mcp._CHANNEL_STOP.clear()

    assert len(sent) == 1
    assert sent[0]["params"]["content"] == "hi"
    assert sent[0]["params"]["meta"]["channel"] == "proj:cliquedb:x"


def test_channel_bridge_starts_once(monkeypatch):
    starts = []
    monkeypatch.setattr(mcp.threading, "Thread",
                        lambda *a, **k: _FakeThread(starts))
    mcp._CHANNEL_THREAD = None
    mcp._ensure_channel_bridge()
    mcp._ensure_channel_bridge()  # idempotent — already alive
    assert len(starts) == 1


class _FakeThread:
    def __init__(self, log):
        self._log = log

    def start(self):
        self._log.append(1)

    def is_alive(self):
        return True
