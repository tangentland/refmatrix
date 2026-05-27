"""Embedder + per-kind extractor tests.

Embedder tests are gated on:
- [dense] extra installed (sentence-transformers + numpy)
- RMX_EMBED_OFFLINE=0 (model download allowed). Set
  RMX_EMBED_OFFLINE=1 in CI to skip the model-loading tests when no
  network is available.

Extractor tests don't need the model — they only touch the Store.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

_HAS_DENSE = (
    importlib.util.find_spec("sentence_transformers") is not None
    and importlib.util.find_spec("numpy") is not None
)
_OFFLINE = os.environ.get("RMX_EMBED_OFFLINE") == "1"

_skip_no_dense = pytest.mark.skipif(
    not _HAS_DENSE,
    reason="[dense] extra not installed",
)
_skip_offline = pytest.mark.skipif(
    _OFFLINE,
    reason="RMX_EMBED_OFFLINE=1",
)


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# --- extractors (no model required) ----------------------------------------


@_skip_no_dense
def test_extract_code_uses_name_and_tldr(store):
    from refmatrix.embedder import extract_text_for_entity

    eid = store.upsert_entity(
        kind="code", name="parser.tokenize", path="/x/parser.py",
        tldr="Split source text into a sequence of tokens.",
    )
    text = extract_text_for_entity(store, eid, "code")
    assert "parser.tokenize" in text
    assert "tokens" in text


@_skip_no_dense
def test_extract_doc_uses_name_and_tldr(store):
    from refmatrix.embedder import extract_text_for_entity

    eid = store.upsert_entity(
        kind="doc", name="docs/architecture.md", path="/x/a.md",
        tldr="Module map and dataflow.",
    )
    text = extract_text_for_entity(store, eid, "doc")
    assert "architecture" in text
    assert "Module map" in text


@_skip_no_dense
def test_extract_concept_joins_name_and_canonical(store):
    from refmatrix.embedder import extract_text_for_entity

    # `parseURL` canonicalizes to `parse_url` under existing
    # identifier expansion; we don't depend on that here — we just
    # set the row directly.
    eid = store.add_concept("parseURL")
    store._connect().execute(
        "UPDATE entities SET canonical_name = 'parse_url' WHERE id = ?",
        [eid],
    )
    store._connect().commit()
    text = extract_text_for_entity(store, eid, "concept")
    assert "parseURL" in text
    assert "parse_url" in text


@_skip_no_dense
def test_extract_concept_skips_canonical_when_same_as_name(store):
    from refmatrix.embedder import extract_text_for_entity

    eid = store.add_concept("parse_url")
    store._connect().execute(
        "UPDATE entities SET canonical_name = 'parse_url' WHERE id = ?",
        [eid],
    )
    store._connect().commit()
    text = extract_text_for_entity(store, eid, "concept")
    # No duplication: 'parse_url' appears once.
    assert text == "parse_url"


@_skip_no_dense
def test_extract_unknown_kind_returns_empty(store):
    from refmatrix.embedder import extract_text_for_entity

    assert extract_text_for_entity(store, 999999, "bogus") == ""


@_skip_no_dense
def test_extract_batch_filters_empty_text(store):
    from refmatrix.embedder import extract_batch

    a = store.upsert_entity(kind="code", name="a.py", tldr="useful")
    b = store.upsert_entity(kind="code", name="", tldr="")
    rows = [(a, "code", "a.py"), (b, "code", "")]
    out = extract_batch(store, rows)
    ids = [r[0] for r in out]
    assert a in ids
    assert b not in ids


# --- model (network + ~134 MB download on first call) ---------------------


@_skip_no_dense
@_skip_offline
def test_embedder_dim_matches_default():
    from refmatrix.embedder import DEFAULT_DIM, Embedder

    e = Embedder()
    assert e.dim == DEFAULT_DIM


@_skip_no_dense
@_skip_offline
def test_embedder_encodes_text_to_expected_shape():
    from refmatrix.embedder import DEFAULT_DIM, Embedder

    e = Embedder()
    vecs = e.embed_texts(["hello world", "another sentence"])
    assert vecs.shape == (2, DEFAULT_DIM)
    assert vecs.dtype.name == "float32"


@_skip_no_dense
@_skip_offline
def test_embedder_normalizes_output():
    import numpy as np
    from refmatrix.embedder import Embedder

    e = Embedder()
    vecs = e.embed_texts(["text"])
    norm = float(np.linalg.norm(vecs[0]))
    assert abs(norm - 1.0) < 1e-3


@_skip_no_dense
@_skip_offline
def test_embedder_empty_returns_empty():
    from refmatrix.embedder import DEFAULT_DIM, Embedder

    e = Embedder()
    out = e.embed_texts([])
    assert out.shape == (0, DEFAULT_DIM)
