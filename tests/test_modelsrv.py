"""Fleet-wide shared model workers.

The point of `modelsrv` is that N daemons share one embedder and one
reranker instead of spawning 2 processes each. These tests cover the parts
that make that safe: the client is surface-compatible with a private
worker, many clients really do land on ONE worker, and an unreachable hub
degrades to a private worker rather than taking dense retrieval down.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import socket
import sys
import textwrap
import threading

import pytest

_HAS_DENSE = importlib.util.find_spec("sentence_transformers") is not None
_OFFLINE = os.environ.get("RMX_EMBED_OFFLINE") == "1"


@pytest.fixture
def sock_path(monkeypatch):
    """A SHORT socket path.

    macOS caps AF_UNIX paths at ~104 bytes and pytest's tmp_path is already
    ~140, so binding under it fails with 'AF_UNIX path too long'. The
    product handles that correctly — it logs and returns False, and daemons
    fall back to private workers — but a test that hits it is testing the
    fallback, not the server. Real deployments bind `~/.refmatrix/models.sock`,
    which is comfortably short.
    """
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="rmxsock", dir="/tmp")
    p = pathlib.Path(d) / "models.sock"
    monkeypatch.setenv("RMX_MODEL_SOCK", str(p))
    yield p
    shutil.rmtree(d, ignore_errors=True)


# --- config surface --------------------------------------------------------


def test_shared_enabled_by_default(monkeypatch):
    from refmatrix.modelsrv import shared_enabled

    monkeypatch.delenv("RMX_SHARED_MODELS", raising=False)
    assert shared_enabled() is True
    monkeypatch.setenv("RMX_SHARED_MODELS", "0")
    assert shared_enabled() is False


def test_shared_available_false_without_a_listener(sock_path):
    from refmatrix.modelsrv import shared_available

    assert shared_available() is False


def test_shared_available_false_on_a_stale_socket_file(sock_path):
    """A killed hub can leave the socket file behind. A path that exists but
    accepts nothing must read as unavailable, or every daemon blocks on it."""
    from refmatrix.modelsrv import shared_available

    sock_path.write_bytes(b"")          # exists, nothing listening
    assert shared_available() is False


# --- server + client over a stub worker ------------------------------------

_STUB = textwrap.dedent("""
    import os, sys
    _OUT = os.fdopen(os.dup(1), "wb"); os.dup2(2, 1); sys.stdout = sys.stderr
    _IN = os.fdopen(os.dup(0), "rb")
    from refmatrix.subproc import recv_frame, send_frame
    n = 0
    while True:
        try:
            req, blob = recv_frame(_IN)
        except EOFError:
            sys.exit(0)
        n += 1
        op = req.get("op")
        if op == "info":
            send_frame(_OUT, {"ok": True, "model": "stub/model", "dim": 4,
                              "pid": os.getpid()})
            continue
        if op == "boom":
            send_frame(_OUT, {"ok": False, "error": "stub refuses"})
            continue
        if op == "blob":
            send_frame(_OUT, {"ok": True, "n": n}, b"\\xaa\\xbb")
            continue
        send_frame(_OUT, {"ok": True, "pid": os.getpid(), "served": n,
                          "echo": req.get("v")})
""")


@pytest.fixture
def server(tmp_path, sock_path):
    """A ModelServer whose workers are stub processes, not real models."""
    from refmatrix.modelsrv import ModelServer
    from refmatrix.subproc import WorkerClient

    script = tmp_path / "stub_worker.py"
    script.write_text(_STUB)

    srv = ModelServer()
    real = srv._worker

    def stub_worker(role):
        with srv._lock:
            w = srv._clients.get(role)
            if w is None:
                w = WorkerClient(role, argv=[sys.executable, str(script)],
                                 timeout=15.0)
                srv._clients[role] = w
            return w

    srv._worker = stub_worker
    assert srv.start() is True
    yield srv
    srv.stop()


def test_client_roundtrip(server, sock_path):
    from refmatrix.modelsrv import SharedWorkerClient

    c = SharedWorkerClient("embed")
    try:
        hdr, _ = c.call("echo", {"v": 7})
        assert hdr["echo"] == 7
    finally:
        c.close()


def test_client_surface_matches_private_worker():
    """The model proxies accept either; if the surfaces drift, the swap in
    `Daemon._model_client` silently stops being a swap."""
    from refmatrix.modelsrv import SharedWorkerClient
    from refmatrix.subproc import WorkerClient

    shared = set(dir(SharedWorkerClient))
    private = set(dir(WorkerClient))
    for name in ("call", "info", "alive", "close", "evict_if_idle"):
        assert name in shared, f"{name} missing from SharedWorkerClient"
        assert name in private, f"{name} missing from WorkerClient"


def test_many_clients_share_one_worker(server):
    """The whole point: N daemons, one model process."""
    from refmatrix.modelsrv import SharedWorkerClient

    clients = [SharedWorkerClient("embed") for _ in range(5)]
    try:
        pids = {c.call("echo", {"v": i})[0]["pid"] for i, c in enumerate(clients)}
        assert len(pids) == 1, f"expected one worker process, saw {pids}"
    finally:
        for c in clients:
            c.close()


def test_roles_get_separate_workers(server):
    from refmatrix.modelsrv import SharedWorkerClient

    a, b = SharedWorkerClient("embed"), SharedWorkerClient("rerank")
    try:
        assert a.call("echo", {"v": 1})[0]["pid"] != b.call("echo", {"v": 1})[0]["pid"]
    finally:
        a.close(); b.close()


def test_blob_survives_the_socket(server):
    """Vectors travel as raw bytes; the socket hop must not mangle them."""
    from refmatrix.modelsrv import SharedWorkerClient

    c = SharedWorkerClient("embed")
    try:
        _hdr, blob = c.call("blob")
        assert blob == b"\xaa\xbb"
    finally:
        c.close()


def test_concurrent_clients_do_not_interleave_frames(server):
    """Requests serialize per role. If two responses crossed on the wire the
    frames would desync and this would fail or hang."""
    from refmatrix.modelsrv import SharedWorkerClient

    errors: list[BaseException] = []

    def hammer(i: int) -> None:
        c = SharedWorkerClient("embed")
        try:
            for n in range(10):
                hdr, _ = c.call("echo", {"v": f"{i}-{n}"})
                assert hdr["echo"] == f"{i}-{n}"
        except BaseException as exc:
            errors.append(exc)
        finally:
            c.close()

    threads = [threading.Thread(target=hammer, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, errors


def test_worker_error_surfaces_as_worker_error(server):
    from refmatrix.modelsrv import SharedWorkerClient
    from refmatrix.subproc import WorkerError

    c = SharedWorkerClient("embed")
    try:
        with pytest.raises(WorkerError):
            c.call("boom")
        # Still usable: an error frame is not a dropped connection.
        assert c.call("echo", {"v": 1})[0]["echo"] == 1
    finally:
        c.close()


def test_unknown_role_is_rejected():
    from refmatrix.modelsrv import SharedWorkerClient

    with pytest.raises(ValueError):
        SharedWorkerClient("nonsense")


def test_client_reconnects_after_server_restart(server, tmp_path, sock_path):
    from refmatrix.modelsrv import SharedWorkerClient

    c = SharedWorkerClient("embed")
    try:
        assert c.call("echo", {"v": 1})[0]["echo"] == 1
        server.stop()
        assert server.start() is True
        # The old connection is dead; the client must reconnect, not raise.
        assert c.call("echo", {"v": 2})[0]["echo"] == 2
    finally:
        c.close()


def test_server_status_reports_socket_and_workers(server):
    st = server.status()
    assert st["listening"] is True
    assert st["socket"].endswith("models.sock")


def test_stop_unlinks_the_socket(server, sock_path):
    """A leftover socket file makes `shared_available` lie to every daemon."""
    assert sock_path.exists()
    server.stop()
    assert not sock_path.exists()


def test_start_replaces_a_stale_socket_file(tmp_path, sock_path):
    """Unlink-before-bind: a killed hub leaves the file behind, and without
    this the next hub cannot bind and the whole fleet silently goes private."""
    from refmatrix.modelsrv import ModelServer

    sock_path.write_bytes(b"")
    srv = ModelServer()
    try:
        assert srv.start() is True
    finally:
        srv.stop()


# --- daemon integration ----------------------------------------------------


def _make_daemon(tmp_path):
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s
    return d


def test_daemon_uses_the_shared_worker_when_present(tmp_path, server, sock_path):
    from refmatrix.modelsrv import SharedWorkerClient

    d = _make_daemon(tmp_path / "store")
    try:
        c = d._model_client("embed")
        assert isinstance(c, SharedWorkerClient)
    finally:
        d._close_workers()
        d.store.close()


def test_daemon_falls_back_to_private_when_hub_is_absent(tmp_path, sock_path):
    """No hub, no socket -- the daemon must still serve dense retrieval."""
    from refmatrix.subproc import WorkerClient

    d = _make_daemon(tmp_path / "store")
    try:
        c = d._model_client("embed")
        assert isinstance(c, WorkerClient)
    finally:
        d._close_workers()
        d.store.close()


def test_daemon_falls_back_when_shared_disabled(tmp_path, server, monkeypatch):
    from refmatrix.subproc import WorkerClient

    monkeypatch.setenv("RMX_SHARED_MODELS", "0")
    d = _make_daemon(tmp_path / "store")
    try:
        assert isinstance(d._model_client("embed"), WorkerClient)
    finally:
        d._close_workers()
        d.store.close()


def test_daemon_falls_back_when_shared_socket_does_not_answer(
    tmp_path, sock_path,
):
    """A socket that accepts but never replies must not wedge the daemon --
    it should notice on the info() probe and go private."""
    from refmatrix.subproc import WorkerClient

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(4)
    try:
        d = _make_daemon(tmp_path / "store")
        try:
            client = d._model_client("embed")
            assert isinstance(client, WorkerClient), \
                "a mute socket must not be adopted as the model client"
        finally:
            d._close_workers()
            d.store.close()
    finally:
        srv.close()


def test_idle_evict_never_reaps_a_shared_worker(tmp_path, server, monkeypatch):
    """One project going quiet must not drop a model six others are using."""
    monkeypatch.setenv("RMX_WORKER_IDLE_S", "0.001")
    d = _make_daemon(tmp_path / "store")
    try:
        client = d._model_client("embed")
        d._evict_idle_workers()
        assert d._embed_worker is client, "shared client should survive the tick"
    finally:
        d._close_workers()
        d.store.close()


# --- real models -----------------------------------------------------------


@pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_shared_and_private_embedders_agree(tmp_path, sock_path):
    """Sharing must not change a single vector -- otherwise turning the hub
    on or off would invalidate everything already written to Lance."""
    import numpy as np
    from refmatrix.embedder import Embedder, RemoteEmbedder
    from refmatrix.modelsrv import ModelServer, SharedWorkerClient

    texts = ["roaring bitmap reference matrix", "daemon jetsam"]
    local = Embedder().embed_texts(texts)

    srv = ModelServer()
    assert srv.start() is True
    try:
        c = SharedWorkerClient("embed", timeout=300.0)
        try:
            emb = RemoteEmbedder(c)
            assert emb.dim == local.shape[1]
            shared = emb.embed_texts(texts)
        finally:
            c.close()
    finally:
        srv.stop()

    assert np.allclose(shared, local, atol=1e-5)
