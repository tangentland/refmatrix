"""Out-of-process model worker transport + lifecycle.

The heavy tests (real embed / rerank worker with a real model) are gated
the same way as the rest of the dense suite. Everything else runs against
a stub worker so the protocol, respawn, timeout, and eviction behavior are
covered in milliseconds without a model load.
"""
from __future__ import annotations

import importlib.util
import io
import os
import struct
import sys
import textwrap
import time

import pytest

_HAS_DENSE = importlib.util.find_spec("sentence_transformers") is not None
_OFFLINE = os.environ.get("RMX_EMBED_OFFLINE") == "1"

_skip_no_dense = pytest.mark.skipif(
    not _HAS_DENSE, reason="[dense] extra not installed")
_skip_offline = pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")


# --- frame protocol --------------------------------------------------------


def test_frame_roundtrip_without_blob():
    from refmatrix.subproc import recv_frame, send_frame

    buf = io.BytesIO()
    send_frame(buf, {"op": "info", "n": 3})
    buf.seek(0)
    hdr, blob = recv_frame(buf)
    assert hdr == {"op": "info", "n": 3}
    assert blob == b""


def test_frame_roundtrip_with_blob():
    from refmatrix.subproc import recv_frame, send_frame

    payload = os.urandom(4096)
    buf = io.BytesIO()
    send_frame(buf, {"ok": True, "n": 2}, payload)
    buf.seek(0)
    hdr, blob = recv_frame(buf)
    # `_blob` is a transport detail and must not leak into the header.
    assert hdr == {"ok": True, "n": 2}
    assert blob == payload


def test_frames_are_self_delimiting():
    """Two frames back-to-back must not bleed into each other -- the whole
    reason for the length prefix."""
    from refmatrix.subproc import recv_frame, send_frame

    buf = io.BytesIO()
    send_frame(buf, {"a": 1}, b"xxxx")
    send_frame(buf, {"b": 2})
    buf.seek(0)
    assert recv_frame(buf) == ({"a": 1}, b"xxxx")
    assert recv_frame(buf) == ({"b": 2}, b"")


def test_recv_frame_raises_on_eof():
    from refmatrix.subproc import recv_frame

    with pytest.raises(EOFError):
        recv_frame(io.BytesIO(b""))


def test_recv_frame_raises_on_truncated_frame():
    from refmatrix.subproc import recv_frame

    # Header claims 100 bytes, supplies 4. A short read is a dead peer.
    truncated = struct.pack(">I", 100) + b"{}  "
    with pytest.raises(EOFError):
        recv_frame(io.BytesIO(truncated))


# --- flag ------------------------------------------------------------------


def test_subproc_flag_defaults_on(monkeypatch):
    """Out-of-process is the default; the flag is an opt-OUT escape hatch."""
    from refmatrix.subproc import subproc_embed_enabled

    monkeypatch.delenv("RMX_EMBED_SUBPROC", raising=False)
    assert subproc_embed_enabled() is True
    monkeypatch.setenv("RMX_EMBED_SUBPROC", "0")
    assert subproc_embed_enabled() is False
    monkeypatch.setenv("RMX_EMBED_SUBPROC", "false")
    assert subproc_embed_enabled() is False
    monkeypatch.setenv("RMX_EMBED_SUBPROC", "1")
    assert subproc_embed_enabled() is True


# --- lifecycle against a stub worker ---------------------------------------

_STUB = textwrap.dedent("""
    import os, sys, time
    _OUT = os.fdopen(os.dup(1), "wb"); os.dup2(2, 1); sys.stdout = sys.stderr
    _IN = os.fdopen(os.dup(0), "rb")
    from refmatrix.subproc import recv_frame, send_frame
    while True:
        try:
            req, blob = recv_frame(_IN)
        except EOFError:
            sys.exit(0)
        op = req.get("op")
        if op == "die":
            os._exit(9)
        if op == "hang":
            time.sleep(60)
        if op == "boom":
            send_frame(_OUT, {"ok": False, "error": "stub says no"})
            continue
        if op == "noisy":
            # A library printing to stdout must not corrupt the channel.
            print("stray stdout line")
            sys.stdout.flush()
            send_frame(_OUT, {"ok": True, "echo": req.get("v")})
            continue
        if op == "blob":
            send_frame(_OUT, {"ok": True}, b"\\x01\\x02\\x03\\x04")
            continue
        send_frame(_OUT, {"ok": True, "pid": os.getpid(), "echo": req.get("v")})
""")


@pytest.fixture
def stub_client(tmp_path):
    from refmatrix.subproc import WorkerClient

    script = tmp_path / "stub_worker.py"
    script.write_text(_STUB)
    c = WorkerClient("embed", argv=[sys.executable, str(script)], timeout=10.0)
    yield c
    c.close(timeout=2.0)


def test_call_roundtrip(stub_client):
    hdr, blob = stub_client.call("echo", {"v": 42})
    assert hdr["echo"] == 42
    assert blob == b""


def test_stray_stdout_does_not_corrupt_channel(stub_client):
    """The worker repoints fd 1 at stderr precisely so this holds."""
    hdr, _ = stub_client.call("noisy", {"v": "a"})
    assert hdr["echo"] == "a"
    hdr, _ = stub_client.call("echo", {"v": "b"})
    assert hdr["echo"] == "b"


def test_blob_response(stub_client):
    hdr, blob = stub_client.call("blob")
    assert blob == b"\x01\x02\x03\x04"


def test_error_frame_raises_worker_error(stub_client):
    from refmatrix.subproc import WorkerError

    with pytest.raises(WorkerError, match="stub says no"):
        stub_client.call("boom")
    # An error frame is not a death: the worker keeps serving.
    assert stub_client.call("echo", {"v": 1})[0]["echo"] == 1


def test_worker_death_is_retried_on_a_fresh_process(stub_client):
    first = stub_client.call("echo", {"v": 0})[0]["pid"]
    with pytest.raises((EOFError, BrokenPipeError, OSError)):
        # `die` exits without answering; the retry hits a worker that is
        # spawned but also gets no answer, so the second attempt raises.
        stub_client.call("die")
    # The client is usable again -- new process, new pid.
    second = stub_client.call("echo", {"v": 1})[0]["pid"]
    assert second != first


def test_timeout_kills_the_worker(stub_client):
    stub_client.timeout = 1.0
    t0 = time.time()
    with pytest.raises(TimeoutError):
        stub_client.call("hang")
    assert time.time() - t0 < 20, "timeout did not bound the wait"
    assert not stub_client.alive()
    # And it recovers.
    assert stub_client.call("echo", {"v": 7})[0]["echo"] == 7


def test_close_on_eof_exits_worker(stub_client):
    stub_client.call("echo", {"v": 1})
    proc = stub_client._proc
    assert proc is not None and proc.poll() is None
    stub_client.close(timeout=5.0)
    assert proc.poll() == 0, "worker should exit cleanly on stdin EOF"


def test_evict_if_idle_respects_the_window(stub_client):
    stub_client.call("echo", {"v": 1})
    assert stub_client.evict_if_idle(3600) is False   # too recent
    assert stub_client.alive()
    assert stub_client.evict_if_idle(0.0) is True     # past the window
    assert not stub_client.alive()
    assert stub_client.evict_if_idle(0.0) is False    # already gone


def test_worker_env_blocks_recursion(monkeypatch, stub_client):
    monkeypatch.setenv("RMX_EMBED_SUBPROC", "1")
    env = stub_client._worker_env()
    assert env["RMX_EMBED_SUBPROC"] == "0", "a worker must never spawn a worker"
    assert env["TOKENIZERS_PARALLELISM"] == "false"


# --- venv containment ------------------------------------------------------


def test_python_executable_is_this_interpreter():
    """Workers must run the SAME interpreter as the daemon, or they get a
    python without the [dense] extra and fail as a missing dependency."""
    from refmatrix.subproc import python_executable

    assert python_executable() == sys.executable


def test_worker_env_drops_pyvenv_launcher(monkeypatch, stub_client):
    """macOS framework python sets __PYVENV_LAUNCHER__; a child that
    inherits it can resolve back to the framework interpreter instead of
    the venv one we asked for."""
    monkeypatch.setenv("__PYVENV_LAUNCHER__", "/usr/bin/python3")
    assert "__PYVENV_LAUNCHER__" not in stub_client._worker_env()


def test_worker_env_drops_pythonhome(monkeypatch, stub_client):
    """PYTHONHOME overrides the prefix derived from the interpreter path
    and would point the child at a different stdlib."""
    monkeypatch.setenv("PYTHONHOME", "/somewhere/else")
    assert "PYTHONHOME" not in stub_client._worker_env()


def test_worker_env_pins_the_venv(stub_client):
    from refmatrix.subproc import in_venv

    env = stub_client._worker_env()
    if in_venv():
        assert env["VIRTUAL_ENV"] == sys.prefix
        assert env["PATH"].split(os.pathsep)[0] == os.path.join(sys.prefix, "bin")
    # refmatrix must be importable by the child regardless.
    assert "PYTHONPATH" in env


def test_worker_runs_in_the_parent_environment(tmp_path):
    """End-to-end: a real spawned worker reports the parent's sys.prefix.
    This is the assertion that would catch a venv escape."""
    from refmatrix.subproc import WorkerClient

    probe = tmp_path / "probe_worker.py"
    probe.write_text(textwrap.dedent("""
        import os, sys
        _OUT = os.fdopen(os.dup(1), "wb"); os.dup2(2, 1); sys.stdout = sys.stderr
        _IN = os.fdopen(os.dup(0), "rb")
        from refmatrix.subproc import recv_frame, send_frame
        while True:
            try:
                req, _ = recv_frame(_IN)
            except EOFError:
                sys.exit(0)
            send_frame(_OUT, {"ok": True, "prefix": sys.prefix,
                              "python": sys.executable})
    """))
    c = WorkerClient("embed", argv=[sys.executable, str(probe)], timeout=30.0)
    try:
        hdr, _ = c.call("info")
        assert hdr["prefix"] == sys.prefix
        assert hdr["python"] == sys.executable
    finally:
        c.close(timeout=2.0)


def test_worker_can_import_refmatrix_without_inherited_pythonpath(
    tmp_path, monkeypatch,
):
    """A launchd-spawned daemon may have no PYTHONPATH; the client prepends
    the package parent so `-m refmatrix.embed_worker` still resolves."""
    from refmatrix.subproc import WorkerClient

    monkeypatch.delenv("PYTHONPATH", raising=False)
    probe = tmp_path / "import_probe.py"
    probe.write_text(textwrap.dedent("""
        import os, sys
        _OUT = os.fdopen(os.dup(1), "wb"); os.dup2(2, 1); sys.stdout = sys.stderr
        _IN = os.fdopen(os.dup(0), "rb")
        from refmatrix.subproc import recv_frame, send_frame
        import refmatrix
        while True:
            try:
                recv_frame(_IN)
            except EOFError:
                sys.exit(0)
            send_frame(_OUT, {"ok": True, "file": refmatrix.__file__})
    """))
    c = WorkerClient("embed", argv=[sys.executable, str(probe)], timeout=30.0)
    try:
        import refmatrix
        hdr, _ = c.call("ping")
        assert hdr["file"] == refmatrix.__file__
    finally:
        c.close(timeout=2.0)


# --- RemoteEmbedder proxy over a fake client -------------------------------


class _FakeClient:
    """Stands in for WorkerClient: records calls, returns canned frames."""

    def __init__(self, dim=4, model="fake/model"):
        self.dim = dim
        self.model = model
        self.calls: list[tuple[str, dict]] = []

    def info(self):
        return {"dim": self.dim, "model": self.model}

    def call(self, op, payload=None, **kw):
        import numpy as np
        self.calls.append((op, payload or {}))
        texts = (payload or {}).get("texts") or []
        vecs = np.arange(len(texts) * self.dim, dtype="float32")
        vecs = vecs.reshape(len(texts), self.dim)
        return ({"n": len(texts), "dim": self.dim}, vecs.tobytes())


def test_remote_embedder_surface_matches_embedder():
    """The daemon uses exactly three members. If this drifts, the drop-in
    swap in `_embedder()` silently stops being a drop-in."""
    from refmatrix.embedder import Embedder, RemoteEmbedder

    # `dir()` rather than `hasattr()`: `dim` is a property that loads the
    # model on access, and this test must stay free of a model load.
    local = set(dir(Embedder(model_name="fake/model")))
    remote = set(dir(RemoteEmbedder(_FakeClient())))
    for name in ("dim", "model_name", "embed_texts"):
        assert name in local, f"{name} missing from Embedder"
        assert name in remote, f"{name} missing from RemoteEmbedder"


def test_remote_embedder_decodes_blob_to_matrix():
    from refmatrix.embedder import RemoteEmbedder

    c = _FakeClient(dim=4)
    e = RemoteEmbedder(c)
    assert e.dim == 4
    assert e.model_name == "fake/model"
    out = e.embed_texts(["a", "b", "c"])
    assert out.shape == (3, 4)
    assert out.dtype.name == "float32"
    assert out[1][0] == 4.0


def test_remote_embedder_empty_input_short_circuits():
    from refmatrix.embedder import RemoteEmbedder

    c = _FakeClient(dim=4)
    out = RemoteEmbedder(c).embed_texts([])
    assert out.shape == (0, 4)
    assert not [op for op, _ in c.calls if op == "embed"], \
        "empty batch must not cost a worker round trip"


def test_remote_embedder_truncates_before_the_pipe():
    from refmatrix.embedder import MAX_INPUT_CHARS, RemoteEmbedder

    c = _FakeClient(dim=4)
    RemoteEmbedder(c).embed_texts(["x" * (MAX_INPUT_CHARS * 3)])
    sent = [p for op, p in c.calls if op == "embed"][0]["texts"][0]
    assert len(sent) == MAX_INPUT_CHARS


def test_remote_embedder_result_is_writable():
    """np.frombuffer yields a read-only view; Lance writes into what it
    gets handed, so the proxy must copy."""
    from refmatrix.embedder import RemoteEmbedder

    out = RemoteEmbedder(_FakeClient(dim=4)).embed_texts(["a"])
    out[0][0] = 99.0   # must not raise


# --- real worker (model load) ----------------------------------------------


@_skip_no_dense
@_skip_offline
def test_real_embed_worker_matches_in_process_vectors():
    """The subprocess path must produce the SAME vectors as the in-process
    path -- otherwise flipping RMX_EMBED_SUBPROC invalidates every vector
    already in Lance."""
    import numpy as np
    from refmatrix.embedder import Embedder, RemoteEmbedder
    from refmatrix.subproc import WorkerClient

    texts = ["roaring bitmap reference matrix", "daemon jetsam"]
    local = Embedder().embed_texts(texts)

    c = WorkerClient("embed", timeout=300.0)
    try:
        remote_emb = RemoteEmbedder(c)
        assert remote_emb.dim == local.shape[1]
        remote = remote_emb.embed_texts(texts)
    finally:
        c.close()

    assert remote.shape == local.shape
    assert np.allclose(remote, local, atol=1e-5)
