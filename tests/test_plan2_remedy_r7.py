"""bsd-plan2-r7 remedy (round 8 of plan 2).

#b-1  the rerank leg was dead as deployed: `SharedWorkerClient.call(timeout=)`
      set the socket timeout for the 1 s `info` probe and never restored it,
      so the `rerank` call that followed with `timeout=None` ran at 1 s too —
      a warm worker scores 20 docs in ~1 s, so 0 of 12 live hook runs
      reranked. The timeout of a timed call is restored afterwards; proven
      on a real fake models.sock whose second frame is the slow one.
#m-3  `hub.global_call` ran `ensure_global_daemon()` (bare pings + a 30 s
      spawn wait) outside every budget; a budgeted caller (`retries=0`)
      skips it — a hook never spawns a daemon.
"""
from __future__ import annotations

import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

from refmatrix import hub as hub_mod
from refmatrix import modelsrv, reranker
from refmatrix.subproc import recv_frame, send_frame


class _FakeModelSock:
    """A models.sock that answers `info` at once and `rerank` after `delay`
    — the shape of a warm worker scoring a 20-doc pool (~1 s live)."""

    def __init__(self, path: Path, *, delay: float):
        self.delay = delay
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(path)); self.sock.listen(8)
        self._stop = False
        self.ops: list[str] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._stop:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        rw = c.makefile("rwb")
        try:
            while True:
                req, _blob = recv_frame(rw)
                op = req.get("op"); self.ops.append(op)
                if op == "info":
                    send_frame(rw, {"ok": True, "model": "fake", "version": "x"})
                elif op == "rerank":
                    time.sleep(self.delay)
                    send_frame(rw, {"ok": True, "scores": [1.0] * len(req.get("docs") or [])})
                else:
                    send_frame(rw, {"ok": False, "error": f"unknown op {op}"})
        except (EOFError, OSError):
            pass
        finally:
            try:
                c.close()
            except OSError:
                pass

    def close(self):
        self._stop = True
        self.sock.close()


@pytest.fixture
def fake_models(monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="rmxm-", dir="/tmp"))
    path = base / "models.sock"
    monkeypatch.setenv("RMX_MODEL_SOCK", str(path))
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    srv = _FakeModelSock(path, delay=1.5)
    try:
        yield srv
    finally:
        srv.close()


def test_a_timed_probe_does_not_shorten_the_next_call(fake_models):
    c = modelsrv.SharedWorkerClient("rerank", timeout=5.0)
    assert c.info(timeout=1.0)["model"] == "fake"
    t0 = time.monotonic()
    hdr, _ = c.call("rerank", {"query": "q", "docs": ["a", "b"]})   # timeout=None → the client's 5 s
    assert hdr["scores"] == [1.0, 1.0]
    assert time.monotonic() - t0 >= 1.4
    assert c._sock.gettimeout() == 5.0
    c.close()


def test_shared_reranker_scores_after_a_short_probe(fake_models, monkeypatch):
    monkeypatch.setattr(reranker, "rerank_enabled", lambda: True)
    monkeypatch.setattr(reranker, "rerank_available", lambda: True)
    rr = reranker.shared_reranker(timeout=5.0, probe_timeout=1.0)
    assert rr is not None
    scores = rr.score("q", ["doc one", "doc two", "doc three"])
    assert scores == [1.0, 1.0, 1.0]
    assert fake_models.ops == ["info", "rerank"]


def test_budgeted_global_call_never_spawns_the_global_daemon(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(hub_mod, "ensure_global_daemon", lambda: calls.append("ensure") or True)
    monkeypatch.setattr(hub_mod, "global_store_root", lambda: tmp_path)
    from refmatrix import daemon as dm
    monkeypatch.setattr(dm, "call", lambda root, op, args, *, timeout=60.0, retries=2:
                        {"ok": True, "result": {"rows": []}})
    hub_mod.global_call("memory_recent", {"since_seconds": 1, "limit": 1}, timeout=1.0, retries=0)
    assert calls == [], "a budgeted (retries=0) global call must not spawn or wait for a daemon"
    hub_mod.global_call("memory_recent", {"since_seconds": 1, "limit": 1}, timeout=1.0)
    assert calls == ["ensure"]
