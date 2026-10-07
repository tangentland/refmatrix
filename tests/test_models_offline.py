"""Model loads make NO network call (user, 2026-10-07: "find all external
calls and remove them").

`SentenceTransformer(name)` and `CrossEncoder(name)` contact huggingface.co on
every load to check for a newer revision, even when the model is already in
`~/.cache/huggingface/hub`. Observed live: the hub's embed and rerank workers
and a pytest run each held an HTTPS connection to huggingface.co's CloudFront
(108.138.246.71/.67, `dig huggingface.co`). Loads are now local-only, and a
model that is not cached fails LOUDLY with the fetch command, never a silent
download.

The socket guard below is the external boundary (registered in
workflow/test_mock_registry.md): it RECORDS every non-unix connect attempt and
refuses it. The model code itself is real.
"""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

HF_HUB = Path.home() / ".cache" / "huggingface" / "hub"


@pytest.fixture
def no_network(monkeypatch):
    attempts: list = []
    real_connect = socket.socket.connect

    def guarded(self, address):
        if self.family == socket.AF_UNIX:
            return real_connect(self, address)
        attempts.append(address)
        raise OSError("network blocked by test_models_offline")

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    return attempts


def _cached(repo: str) -> bool:
    return (HF_HUB / ("models--" + repo.replace("/", "--"))).exists()


@pytest.mark.skipif(not _cached("BAAI/bge-small-en-v1.5"), reason="embed model not cached")
def test_the_embedder_loads_without_a_network_call(no_network):
    from refmatrix.embedder import Embedder

    e = Embedder("BAAI/bge-small-en-v1.5")
    e._load()

    assert e._model is not None
    assert no_network == [], f"the embedder called out: {no_network}"


@pytest.mark.skipif(not _cached("cross-encoder/ms-marco-MiniLM-L-12-v2"),
                    reason="rerank model not cached")
def test_the_reranker_loads_without_a_network_call(no_network):
    from refmatrix.reranker import Reranker

    r = Reranker("cross-encoder/ms-marco-MiniLM-L-12-v2")
    r._load()

    assert r._model is not None
    assert no_network == [], f"the reranker called out: {no_network}"


def test_an_uncached_model_fails_loudly_and_offline(no_network):
    """Never a silent download: the error names the model and the one-time
    fetch command, and no connection was attempted."""
    from refmatrix.embedder import Embedder
    from refmatrix.models_local import ModelNotCached

    with pytest.raises(ModelNotCached) as ei:
        Embedder("rmx-test/definitely-not-a-cached-model")._load()

    msg = str(ei.value)
    assert "rmx-test/definitely-not-a-cached-model" in msg
    assert "hf download" in msg or "huggingface-cli download" in msg
    assert no_network == [], no_network
