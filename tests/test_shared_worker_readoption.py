"""bug-024 / todo G14: a daemon that went private stays private forever.

After the fleet relaunched while the hub was down, every daemon booted with
PRIVATE embed + rerank workers (16 model processes) and kept them after the hub
came back. N torch processes on one CPU oversubscribe its threads — the shared
reranker then scored 10 x 700-char docs in 16-25 s against 0.7 s for one, and
every per-prompt hook rerank timed out.

`_model_client` decided shared-vs-private ONCE, at first use. These tests cover
the re-probe: while a role holds a private worker, the daemon looks at the
shared socket again on its existing background tick and swaps when it answers.

The stand-in for the hub is a real unix socket speaking the real frame
protocol — no torch, no model. `SharedWorkerClient` needs frames, not a hub.
"""
from __future__ import annotations

import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import modelsrv
from refmatrix.subproc import recv_frame, send_frame


class _StubHub:
    """A socket that answers `info` the way the hub's ModelServer does."""

    def __init__(self, path: Path, *, answer: bool = True):
        self.path = path
        self.answer = answer
        self.connections = 0
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(str(path))
        self._srv.listen(8)
        self._srv.settimeout(0.2)
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except (socket.timeout, OSError):
                continue
            self.connections += 1
            threading.Thread(target=self._handle, args=(conn,),
                             daemon=True).start()

    def _handle(self, conn):
        rw = conn.makefile("rwb")
        while not self._stop.is_set():
            try:
                req, _ = recv_frame(rw)
            except (EOFError, OSError):
                return
            if not self.answer:
                return                      # accept, never answer: the mute hub
            send_frame(rw, {"ok": True, "model": "stub", "dim": 384,
                            "version": _version(), "op": req.get("op")})

    def close(self):
        self._stop.set()
        try:
            self._srv.close()
        except OSError:
            pass
        try:
            self.path.unlink()
        except OSError:
            pass


def _version() -> str:
    from refmatrix import __version__
    return __version__


class _FakePrivate:
    """Stand-in for `subproc.WorkerClient` — adoption only needs to recognise
    that it is not shared, and to close it."""

    def __init__(self):
        self.closed = False
        self.pid = 4242

    def close(self, *, timeout: float = 0.0):
        self.closed = True

    def alive(self) -> bool:
        return not self.closed


@pytest.fixture
def daemon_and_sock(tmp_path, monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="rmxg14-"))
    root = base / "p" / ".refmatrix"
    root.parent.mkdir(parents=True)
    sock = base / "models.sock"
    monkeypatch.setenv("RMX_MODEL_SOCK", str(sock))
    d = dm.Daemon(root)
    d._log = lambda m: d.__dict__.setdefault("_logs", []).append(m)
    yield d, sock
    shutil.rmtree(base, ignore_errors=True)


def _logs(d) -> list[str]:
    return d.__dict__.get("_logs", [])


# ---- adoption ------------------------------------------------------------

def test_a_private_daemon_adopts_the_shared_worker_when_it_answers(daemon_and_sock):
    d, sock = daemon_and_sock
    priv = _FakePrivate()
    d._embed_worker = priv
    d._embedder_inst = object()

    assert d._maybe_adopt_shared() == []          # nothing listening yet
    assert d._embed_worker is priv

    hub = _StubHub(sock)
    try:
        adopted = d._maybe_adopt_shared(now=time.time() + 10_000)
        assert adopted == ["embed"]
        assert isinstance(d._embed_worker, modelsrv.SharedWorkerClient)
        assert priv.closed is True
        # the cached proxy must go with it: it wraps the OLD client
        assert d._embedder_inst is None
        assert any("adopted hub-shared worker" in m for m in _logs(d))
    finally:
        hub.close()


def test_a_daemon_already_on_the_shared_worker_does_not_probe(daemon_and_sock):
    d, sock = daemon_and_sock
    hub = _StubHub(sock)
    try:
        d._embed_worker = modelsrv.SharedWorkerClient("embed")
        before = hub.connections
        assert d._maybe_adopt_shared(now=time.time() + 10_000) == []
        assert hub.connections == before
    finally:
        hub.close()


def test_a_role_with_no_worker_at_all_is_left_alone(daemon_and_sock):
    d, sock = daemon_and_sock
    hub = _StubHub(sock)
    try:
        assert d._maybe_adopt_shared(now=time.time() + 10_000) == []
        assert getattr(d, "_embed_worker", None) is None
    finally:
        hub.close()


# ---- probe rate ----------------------------------------------------------

def test_two_ticks_inside_the_window_probe_once(daemon_and_sock, monkeypatch):
    d, sock = daemon_and_sock
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "300")
    d._embed_worker = _FakePrivate()
    probes = []
    monkeypatch.setattr(modelsrv, "shared_available",
                        lambda timeout=0.5: probes.append(1) or False)

    t = time.time()
    d._maybe_adopt_shared(now=t)
    d._maybe_adopt_shared(now=t + 10)
    assert len(probes) == 1
    d._maybe_adopt_shared(now=t + 301)
    assert len(probes) == 2


def test_backoff_doubles_and_is_capped(daemon_and_sock, monkeypatch):
    d, sock = daemon_and_sock
    monkeypatch.setenv("RMX_SHARED_REPROBE_S", "100")
    monkeypatch.setenv("RMX_SHARED_REPROBE_MAX_S", "400")
    d._embed_worker = _FakePrivate()
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: False)

    t = 1_000_000.0
    waits = []
    for _ in range(6):
        d._maybe_adopt_shared(now=t)
        nxt = d._reprobe_next["embed"]
        waits.append(round(nxt - t))
        t = nxt
    assert waits[:3] == [100, 200, 400]
    assert set(waits[3:]) == {400}, waits


def test_shared_models_off_never_probes(daemon_and_sock, monkeypatch):
    d, sock = daemon_and_sock
    monkeypatch.setenv("RMX_SHARED_MODELS", "0")
    d._embed_worker = _FakePrivate()
    probes = []
    monkeypatch.setattr(modelsrv, "shared_available",
                        lambda timeout=0.5: probes.append(1) or True)
    assert d._maybe_adopt_shared(now=time.time() + 10_000) == []
    assert probes == []


def test_a_mute_socket_leaves_the_private_worker_serving(daemon_and_sock, monkeypatch):
    """A hub mid-restart accepts and never answers. The failure must cost the
    daemon a bounded probe, never its working worker."""
    d, sock = daemon_and_sock
    monkeypatch.setattr(modelsrv, "PROBE_TIMEOUT_S", 0.5)
    hub = _StubHub(sock, answer=False)
    priv = _FakePrivate()
    d._embed_worker = priv
    try:
        assert d._maybe_adopt_shared(now=time.time() + 10_000) == []
        assert d._embed_worker is priv
        assert priv.closed is False
        assert any("shared worker still unusable" in m for m in _logs(d))
    finally:
        hub.close()


# ---- the wiring ----------------------------------------------------------

def test_the_background_tick_calls_the_reprobe(daemon_and_sock, monkeypatch):
    """Not the helper: the daemon's existing tick must actually run it."""
    d, sock = daemon_and_sock
    calls = []
    monkeypatch.setattr(d, "_maybe_adopt_shared", lambda **kw: calls.append(1) or [])
    monkeypatch.setattr(d, "_evict_idle_workers", lambda: None)
    d._start_periodic_flush(interval_s=0.05)
    try:
        deadline = time.time() + 3.0
        while not calls and time.time() < deadline:
            time.sleep(0.05)
        assert calls, "the periodic tick never called _maybe_adopt_shared"
    finally:
        d._flush_stop.set()


def test_health_names_the_worker_kind(daemon_and_sock, monkeypatch):
    """`hub status` can only show a split fleet if the daemon says which
    workers it holds."""
    d, sock = daemon_and_sock
    from refmatrix.store import Store

    s = Store(d.root)
    s.init()
    monkeypatch.setattr(d, "_st", lambda: s, raising=False)
    monkeypatch.setattr(d, "_read_active_slot", lambda: None, raising=False)
    try:
        d._embed_worker = _FakePrivate()
        h = dm._store_health(d)
        assert h["workers"] == {"embed": "private", "rerank": "none"}

        d._rerank_worker = modelsrv.SharedWorkerClient("rerank")
        assert dm._store_health(d)["workers"]["rerank"] == "shared"
    finally:
        s.close()


def test_hub_status_renders_a_split_fleet():
    from refmatrix.cli import render_worker_split

    assert render_worker_split({"embed": "private", "rerank": "shared"}) == \
        "workers: embed=private rerank=shared"
    assert render_worker_split({"embed": "shared", "rerank": "shared"}) == ""
    assert render_worker_split(None) == ""


def test_gather_queues_carries_the_split_from_health(tmp_path, monkeypatch):
    """The relay, not the renderer: a daemon reporting a private worker must
    reach the hub row that `rmx hub queues` reads."""
    from refmatrix import daemon as daemon_mod
    from refmatrix import hub as hub_mod

    root = tmp_path / "p" / ".refmatrix"
    root.mkdir(parents=True)
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [root])
    monkeypatch.setattr("refmatrix.discovery.daemon_status",
                        lambda r: {"up": True, "pid": 1})
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda r: "p")

    def fake_call(r, op, args=None, timeout=0.0, retries=2, **kw):
        if op == "stats":
            return {"ok": True, "result": {"stale_files": [], "health": {
                "workers": {"embed": "private", "rerank": "shared"},
                "derive": {"stale": True, "oldest_version": "0.49.1"},
            }}}
        if op == "ping":
            return {"ok": True, "result": {"pid": 1, "version": _version(),
                                           "code_path": "/x/src/refmatrix/__init__.py",
                                           "dev_tree": False}}
        return {"ok": False}

    monkeypatch.setattr(daemon_mod, "call", fake_call)
    row = hub_mod.Hub._gather_queues(None)[0]
    assert row["private_workers"] == {"embed": "private", "rerank": "shared"}
    assert row["derive_stale"] == "0.49.1"

    # ... and a fully-shared, freshly-derived daemon carries neither key.
    def fake_clean(r, op, args=None, timeout=0.0, retries=2, **kw):
        if op == "stats":
            return {"ok": True, "result": {"stale_files": [], "health": {
                "workers": {"embed": "shared", "rerank": "shared"},
                "derive": {"stale": False},
            }}}
        return fake_call(r, op, args, timeout, retries, **kw)

    monkeypatch.setattr(daemon_mod, "call", fake_clean)
    clean = hub_mod.Hub._gather_queues(None)[0]
    assert "private_workers" not in clean and "derive_stale" not in clean
