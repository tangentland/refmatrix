"""Daemon-level wiring for the out-of-process embedder + rerank stage.

The point of `RMX_EMBED_SUBPROC` is that flipping it changes *where* the
model lives and nothing else: same vectors, same op results, same error
behavior. These tests assert that, plus the lifecycle guarantees the flag
is there to buy — the worker is a real child process, and shutting the
daemon down reaps it.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_HAS_DENSE = (
    importlib.util.find_spec("sentence_transformers") is not None
    and importlib.util.find_spec("lance") is not None
)
_OFFLINE = os.environ.get("RMX_EMBED_OFFLINE") == "1"


def _make_daemon(tmp_path: Path):
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s
    return d


# --- selection logic (no model) --------------------------------------------


def test_flag_off_uses_in_process_embedder(tmp_path, monkeypatch):
    """Default path must be untouched: no worker, no subprocess."""
    from refmatrix.embedder import Embedder

    monkeypatch.setenv("RMX_EMBED_SUBPROC", "0")
    d = _make_daemon(tmp_path)
    try:
        sentinel = Embedder(model_name="fake/model")
        d._embedder_inst = sentinel
        assert d._embedder() is sentinel
        assert d._embed_worker is None
    finally:
        d.store.close()


def test_flag_defaults_to_subprocess(tmp_path, monkeypatch):
    """The default path is now out-of-process."""
    from refmatrix.subproc import subproc_embed_enabled

    monkeypatch.delenv("RMX_EMBED_SUBPROC", raising=False)
    assert subproc_embed_enabled() is True


def test_spawn_failure_falls_back_to_in_process(tmp_path, monkeypatch):
    """Making the subprocess the default must not create a new way for dense
    retrieval to die. A transport failure degrades to the in-process model;
    only a missing [dense] extra propagates, because in-process would fail
    identically."""
    from refmatrix.embedder import Embedder

    monkeypatch.delenv("RMX_EMBED_SUBPROC", raising=False)
    d = _make_daemon(tmp_path)
    logged: list[str] = []
    d._log = logged.append
    try:
        def _boom():
            raise OSError("cannot spawn in this sandbox")

        d._remote_embedder = _boom
        emb = d._embedder()
        assert isinstance(emb, Embedder), "should have fallen back in-process"
        assert any("falling back to in-process" in m for m in logged), \
            "a silent fallback would hide the daemon carrying the model RSS"
        assert d._embed_worker is None
    finally:
        d.store.close()


def test_missing_dense_extra_still_propagates(tmp_path, monkeypatch):
    """ImportError must NOT be swallowed by the fallback -- the op handlers
    turn it into a clean client error, and in-process cannot rescue it."""
    monkeypatch.delenv("RMX_EMBED_SUBPROC", raising=False)
    d = _make_daemon(tmp_path)
    try:
        def _no_extra():
            raise ImportError("sentence-transformers not installed")

        d._remote_embedder = _no_extra
        with pytest.raises(ImportError):
            d._embedder()
    finally:
        d.store.close()


def test_close_workers_is_safe_with_none_spawned(tmp_path):
    d = _make_daemon(tmp_path)
    try:
        d._close_workers()          # must not raise
        assert d._embed_worker is None
        assert d._rerank_worker is None
    finally:
        d.store.close()


def test_evict_idle_workers_noop_when_disabled(tmp_path, monkeypatch):
    """Idle eviction is opt-in — a zero window must not reap a live worker
    on every flush tick."""
    monkeypatch.delenv("RMX_WORKER_IDLE_S", raising=False)

    class _Spy:
        def __init__(self):
            self.calls = 0

        def evict_if_idle(self, idle_s):
            self.calls += 1
            return False

    d = _make_daemon(tmp_path)
    try:
        spy = _Spy()
        d._embed_worker = spy
        d._evict_idle_workers()
        assert spy.calls == 0
        monkeypatch.setenv("RMX_WORKER_IDLE_S", "60")
        d._evict_idle_workers()
        assert spy.calls == 1
    finally:
        d._embed_worker = None
        d.store.close()


# --- rerank wiring (fake model) --------------------------------------------


class _KeywordReranker:
    def score(self, query, docs):
        return [1.0 if "jetsam" in d else 0.0 for d in docs]


@pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_ann_search_rerank_reorders_and_flags_results(tmp_path, monkeypatch):
    from refmatrix.daemon import _op_ann_search, _op_embed

    monkeypatch.setenv("RMX_EMBED_SUBPROC", "0")
    d = _make_daemon(tmp_path)
    try:
        d.store.upsert_entity(
            kind="code", name="sourdough",
            path="/x/a.py", tldr="feed the starter every twelve hours",
        )
        target = d.store.upsert_entity(
            kind="code", name="daemon_death",
            path="/x/b.py", tldr="SIGKILLed by macOS jetsam under pressure",
        )
        assert _op_embed(d, {"kinds": ["code"]})["embedded"] == 2

        d._reranker_inst = _KeywordReranker()
        out = _op_ann_search(
            d, {"query": "sourdough bread", "k": 2, "rerank": True},
        )
        hits = out["hits"]
        assert hits, "rerank must not empty the result set"
        assert hits[0]["reranked"] is True
        assert hits[0]["id"] == target, \
            "the reranker's preferred doc should be rank 1"
    finally:
        d.store.close()


@pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_rerank_off_returns_plain_distances(tmp_path, monkeypatch):
    from refmatrix.daemon import _op_ann_search, _op_embed

    monkeypatch.setenv("RMX_EMBED_SUBPROC", "0")
    monkeypatch.setenv("RMX_RERANK", "0")
    d = _make_daemon(tmp_path)
    try:
        d.store.upsert_entity(
            kind="code", name="a", path="/x/a.py", tldr="roaring bitmaps",
        )
        _op_embed(d, {"kinds": ["code"]})
        hits = _op_ann_search(d, {"query": "bitmaps", "k": 1})["hits"]
        assert "distance" in hits[0]
        assert "reranked" not in hits[0]
    finally:
        d.store.close()


@pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_rerank_failure_falls_back_to_distances(tmp_path, monkeypatch):
    """A broken reranker degrades the ranking, never the result set."""
    from refmatrix.daemon import _op_ann_search, _op_embed

    class _Broken:
        def score(self, query, docs):
            raise RuntimeError("model exploded")

    monkeypatch.setenv("RMX_EMBED_SUBPROC", "0")
    d = _make_daemon(tmp_path)
    try:
        d.store.upsert_entity(
            kind="code", name="a", path="/x/a.py", tldr="roaring bitmaps",
        )
        _op_embed(d, {"kinds": ["code"]})
        d._reranker_inst = _Broken()
        hits = _op_ann_search(
            d, {"query": "bitmaps", "k": 1, "rerank": True})["hits"]
        assert len(hits) == 1
        assert "distance" in hits[0]
    finally:
        d.store.close()


# --- real subprocess embedder ----------------------------------------------


@pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_op_embed_works_through_the_worker(tmp_path, monkeypatch):
    from refmatrix.daemon import _op_embed
    from refmatrix.embedder import RemoteEmbedder

    monkeypatch.setenv("RMX_EMBED_SUBPROC", "1")
    d = _make_daemon(tmp_path)
    try:
        d.store.upsert_entity(
            kind="code", name="parser.tokenize", path="/x/p.py",
            tldr="Split source text into tokens.",
        )
        res = _op_embed(d, {"kinds": ["code"]})
        assert res["embedded"] == 1
        assert res["dim"] == 384
        assert isinstance(d._embedder(), RemoteEmbedder)

        # A real child process, not a thread.
        worker = d._embed_worker
        assert worker is not None and worker.alive()
        pid = worker._proc.pid
        assert pid != os.getpid()

        # Shutdown reaps it — this is the whole point of the flag.
        d._close_workers()
        assert not worker.alive()
        with pytest.raises(OSError):
            os.kill(pid, 0)
    finally:
        d._close_workers()
        d.store.close()


@pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_subproc_and_in_process_agree_on_ann_results(tmp_path, monkeypatch):
    """Flipping the flag must not change retrieval. If it did, every vector
    already written to Lance would be invalidated by the switch."""
    from refmatrix.daemon import _op_ann_search, _op_embed

    rows = [
        ("roaring", "roaring bitmap fragment storage"),
        ("jetsam", "the daemon was SIGKILLed under memory pressure"),
        ("duck", "duckdb catalog rotation slots"),
    ]

    def _run(flag: str):
        monkeypatch.setenv("RMX_EMBED_SUBPROC", flag)
        d = _make_daemon(tmp_path / flag)
        try:
            for name, tldr in rows:
                d.store.upsert_entity(
                    kind="code", name=name, path=f"/x/{name}.py", tldr=tldr,
                )
            _op_embed(d, {"kinds": ["code"]})
            # rerank pinned off: this test is about whether the EMBEDDER flag
            # changes retrieval, and the rerank stage (on by default) replaces
            # dense distances with cross-encoder scores, which would compare
            # the wrong thing.
            hits = _op_ann_search(d, {
                "query": "why did the daemon die", "k": 3, "rerank": False,
            })["hits"]
            return [h["distance"] for h in hits]
        finally:
            d._close_workers()
            d.store.close()

    local = _run("0")
    remote = _run("1")
    assert len(local) == len(remote) == 3
    for a, b in zip(local, remote):
        assert abs(a - b) < 1e-4
