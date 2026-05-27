"""Hybrid recall + bitmap prefilter tests."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_HAS_DENSE = (
    importlib.util.find_spec("lance") is not None
    and importlib.util.find_spec("sentence_transformers") is not None
)
_OFFLINE = os.environ.get("RMX_EMBED_OFFLINE") == "1"

pytestmark = [
    pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed"),
    pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1"),
]


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


@pytest.fixture
def seeded(store):
    """A store with three embeddable code entities and one doc."""
    from refmatrix.daemon import _op_embed, Daemon

    a = store.upsert_entity(
        kind="code", name="tokenize.py",
        tldr="Lex source text into a sequence of tokens.",
    )
    b = store.upsert_entity(
        kind="code", name="parser.py",
        tldr="Build an AST from a token stream.",
    )
    c = store.upsert_entity(
        kind="code", name="server.py",
        tldr="HTTP server with route handlers.",
    )
    d_id = store.upsert_entity(
        kind="doc", name="README.md",
        tldr="Repo overview, install, and quick start.",
    )

    d = Daemon(store.root)
    d.store = store
    _op_embed(d, {"kinds": ["code", "doc"]})
    return {"a": a, "b": b, "c": c, "d": d_id}


def test_dense_available_probe():
    from refmatrix.recall import dense_available

    assert dense_available() is True


def test_dense_recall_top1_matches_semantic_intent(store, seeded):
    from refmatrix.embedder import Embedder
    from refmatrix.recall import dense_recall

    e = Embedder()
    hits = dense_recall(
        store, e, "lexer that splits text into tokens", k=3,
    )
    assert hits[0][0] == seeded["a"]


def test_dense_recall_respects_candidate_prefilter(store, seeded):
    from refmatrix.embedder import Embedder
    from refmatrix.recall import dense_recall

    e = Embedder()
    # Restrict to just parser + server; tokenize is excluded so it
    # cannot win even though it would otherwise be top-1.
    hits = dense_recall(
        store, e, "lexer that splits text into tokens", k=3,
        candidate_ids=[seeded["b"], seeded["c"]],
    )
    ids = [h[0] for h in hits]
    assert seeded["a"] not in ids
    assert set(ids).issubset({seeded["b"], seeded["c"]})


def test_dense_recall_empty_candidate_set_returns_empty(store, seeded):
    from refmatrix.embedder import Embedder
    from refmatrix.recall import dense_recall

    e = Embedder()
    hits = dense_recall(store, e, "anything", k=3, candidate_ids=[])
    assert hits == []


def test_hybrid_recall_fuses_symbolic_and_dense(store, seeded):
    from refmatrix.embedder import Embedder
    from refmatrix.recall import hybrid_recall

    e = Embedder()
    # Both sides agree tokenize wins: symbolic ranks it first,
    # dense ranks it first. RRF must surface it at top of fused.
    hits = hybrid_recall(
        store, e, "lexer that splits text into tokens",
        k=4, symbolic_hits=[seeded["a"], seeded["b"], seeded["c"]],
    )
    assert hits[0][0] == seeded["a"]


def test_hybrid_recall_disagreement_is_resolved_by_rrf(store, seeded):
    """When symbolic and dense disagree on the top hit, RRF prefers
    items that appear in BOTH lists over items that appear in only one.
    Symbolic = [b, c, d]; dense puts a at rank 0 but b at rank 1.
    Fused top should be b (in both) over a (dense-only)."""
    from refmatrix.embedder import Embedder
    from refmatrix.recall import hybrid_recall

    e = Embedder()
    hits = hybrid_recall(
        store, e, "lexer that splits text into tokens",
        k=4, symbolic_hits=[seeded["b"], seeded["c"], seeded["d"]],
    )
    # b appears in both top-3 of symbolic and top-3 of dense; a is
    # dense-only. RRF gives b the higher fused score.
    assert hits[0][0] == seeded["b"]
    # a still makes it into the fused list because dense contributed.
    assert seeded["a"] in [h[0] for h in hits]


def test_hybrid_recall_with_empty_symbolic_falls_back_to_dense(store, seeded):
    from refmatrix.embedder import Embedder
    from refmatrix.recall import hybrid_recall

    e = Embedder()
    hits = hybrid_recall(
        store, e, "lexer that splits text into tokens",
        k=3, symbolic_hits=None,
    )
    assert hits and hits[0][0] == seeded["a"]


def test_hybrid_recall_with_no_query_uses_symbolic_only(store, seeded):
    from refmatrix.embedder import Embedder
    from refmatrix.recall import hybrid_recall

    e = Embedder()
    sym = [seeded["b"], seeded["c"]]
    hits = hybrid_recall(store, e, "", k=3, symbolic_hits=sym)
    ids = [h[0] for h in hits]
    # Empty query → dense contributes nothing → result is symbolic
    # ranking exactly.
    assert ids == sym


def test_bitmap_prefilter_unions_concept_bitmaps(store):
    from refmatrix.recall import bitmap_prefilter

    # Two concepts; link a couple of code entities under "mentions".
    parser = store.add_concept("parser_kw")
    lexer = store.add_concept("lexer_kw")
    a = store.upsert_entity(kind="code", name="a.py")
    b = store.upsert_entity(kind="code", name="b.py")
    c = store.upsert_entity(kind="code", name="c.py")
    store.link("mentions", parser, a)
    store.link("mentions", parser, c)
    store.link("mentions", lexer, b)

    out = bitmap_prefilter(store, [parser, lexer], linkage="mentions")
    assert set(out) == {a, b, c}

    out_one = bitmap_prefilter(store, [parser], linkage="mentions")
    assert set(out_one) == {a, c}

    assert bitmap_prefilter(store, [], linkage="mentions") == []
