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
    # setenv-then-delenv so monkeypatch records an undo even when the variable
    # was absent: `load_local` sets it, and a bare `delenv(raising=False)` on an
    # absent variable restores nothing, so it leaked into the rest of the
    # session (ch-bsd r6 #m-3).
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.setenv(var, "sentinel")
        monkeypatch.delenv(var)
    # `enforce_offline` also flips the already-imported hub constant; restore it.
    import sys
    constants = sys.modules.get("huggingface_hub.constants")
    if constants is not None:
        monkeypatch.setattr(constants, "HF_HUB_OFFLINE", False)
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

    from sentence_transformers import CrossEncoder
    assert isinstance(r._model, CrossEncoder), type(r._model)
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


# ---- ch-bsd r6 #m-3: each offline mechanism holds ALONE ---------------------
#
# Importing huggingface_hub first freezes HF_HUB_OFFLINE into its constants, so
# the env var set at load time does nothing; `local_files_only` must hold the
# main path on its own. With the constant forced False after import, any
# connect attempt here means a mechanism is missing.

@pytest.mark.skipif(not _cached("BAAI/bge-small-en-v1.5"), reason="embed model not cached")
def test_a_load_after_the_hub_was_imported_still_makes_no_call(no_network):
    import huggingface_hub  # noqa: F401  -- imported FIRST, on purpose
    from refmatrix.embedder import Embedder

    Embedder("BAAI/bge-small-en-v1.5")._load()

    assert no_network == [], f"the embedder called out: {no_network}"


def test_a_load_leaves_the_hub_in_offline_mode_even_if_imported_first(no_network):
    """Remote model code (CodeRankEmbed's `cached_file`) never sees
    `local_files_only`, so the hub's own offline constant must be on."""
    import huggingface_hub.constants as constants
    from refmatrix.models_local import enforce_offline

    assert constants.HF_HUB_OFFLINE is False
    enforce_offline()
    assert constants.HF_HUB_OFFLINE is True


def test_an_explicit_operator_opt_out_is_kept(no_network, monkeypatch):
    import huggingface_hub.constants as constants
    from refmatrix.models_local import enforce_offline

    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    enforce_offline()
    assert constants.HF_HUB_OFFLINE is False


# ---- ch-bsd r6 #b-2: the eval CodeRankEmbed retriever is offline too --------

@pytest.mark.skipif(not _cached("cornstack/CodeRankEmbed"), reason="CodeRankEmbed not cached")
def test_the_coderankembed_retriever_makes_no_call(no_network):
    import huggingface_hub  # noqa: F401  -- the r6 repro imported it first
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    try:
        from eval.retrievers.coderankembed_retriever import CodeRankEmbedRetriever
        CodeRankEmbedRetriever(device="cpu")
    finally:
        sys.path.remove(str(root))

    assert no_network == [], f"CodeRankEmbed called out: {no_network}"


# ---- ch-bsd r6 #s-2: a PARTIAL cache is a loud failure, never a substitute ---
#
# Probed in r6: bge-small without its tokenizer files loaded and encoded at
# cosine 0.553 to the real model; without modules.json it loaded with mean
# pooling and no Normalize (cosine 0.952), silently; without 1_Pooling it
# raised TypeError. Each must be ModelNotCached, naming the missing file.

def _partial_copy(tmp_path, repo: str, drop: list[str]) -> Path:
    import shutil
    snap = next((HF_HUB / ("models--" + repo.replace("/", "--")) / "snapshots").iterdir())
    dst = tmp_path / "model"
    shutil.copytree(snap, dst, symlinks=False)
    for name in drop:
        target = dst / name
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    return dst


@pytest.mark.skipif(not _cached("BAAI/bge-small-en-v1.5"), reason="embed model not cached")
@pytest.mark.parametrize("drop,named", [
    (["tokenizer.json", "vocab.txt", "tokenizer_config.json"], "tokenizer"),
    (["modules.json"], "modules.json"),
    (["1_Pooling"], "1_Pooling"),
])
def test_a_partial_embed_cache_fails_loudly(no_network, tmp_path, drop, named):
    from refmatrix.models_local import ModelNotCached, load_local

    path = _partial_copy(tmp_path, "BAAI/bge-small-en-v1.5", drop)
    with pytest.raises(ModelNotCached) as ei:
        load_local("embed", str(path), "cpu")
    assert named in str(ei.value), str(ei.value)


@pytest.mark.skipif(not _cached("cross-encoder/ms-marco-MiniLM-L-12-v2"),
                    reason="rerank model not cached")
def test_a_partial_rerank_cache_fails_loudly(no_network, tmp_path):
    from refmatrix.models_local import ModelNotCached, load_local

    path = _partial_copy(tmp_path, "cross-encoder/ms-marco-MiniLM-L-12-v2",
                         ["tokenizer.json", "vocab.txt", "tokenizer_config.json"])
    with pytest.raises(ModelNotCached) as ei:
        load_local("rerank", str(path), "cpu")
    assert "tokenizer" in str(ei.value), str(ei.value)


@pytest.mark.skipif(not _cached("BAAI/bge-small-en-v1.5"), reason="embed model not cached")
def test_a_complete_local_copy_still_loads(no_network, tmp_path):
    from refmatrix.models_local import load_local

    path = _partial_copy(tmp_path, "BAAI/bge-small-en-v1.5", [])
    assert load_local("embed", str(path), "cpu") is not None
    assert no_network == []


@pytest.mark.skipif(not _cached("BAAI/bge-small-en-v1.5"), reason="embed model not cached")
def test_local_files_only_alone_holds_when_the_operator_opted_out(no_network, monkeypatch):
    """`HF_HUB_OFFLINE=0` is kept (an explicit operator value), so the hub is
    ONLINE and `local_files_only=True` is the only thing between a cached
    load and a revision check."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    from refmatrix.models_local import load_local

    load_local("embed", "BAAI/bge-small-en-v1.5", "cpu")

    assert no_network == [], f"called out with the hub online: {no_network}"


@pytest.mark.skipif(not _cached("BAAI/bge-small-en-v1.5"), reason="embed model not cached")
def test_a_config_the_check_passes_but_the_library_rejects_is_model_not_cached(
        no_network, tmp_path):
    """The file check sees `1_Pooling/config.json` present; the library cannot
    build a Pooling from `{}` and raises TypeError. That is still a broken
    cache, so it is ModelNotCached, not a stack trace from a daemon worker."""
    from refmatrix.models_local import ModelNotCached, load_local

    path = _partial_copy(tmp_path, "BAAI/bge-small-en-v1.5", [])
    (path / "1_Pooling" / "config.json").write_text("{}")
    with pytest.raises(ModelNotCached) as ei:
        load_local("embed", str(path), "cpu")
    assert "TypeError" in str(ei.value), str(ei.value)
