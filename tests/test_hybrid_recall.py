"""Hybrid dense ⊕ content_rank RRF fusion for `memory recall` (round 4).

Closes audit-2 #1 deliverable-2: `_op_ann_search` was pure dense, so a
rare-keyword query ("grep backstop protected query concept") ranked the
lexically-exact memory far down — symbolic content_rank nails it, dense
dilutes it. `hybrid_memory_recall` RRF-fuses both. Tested with fakes (no
daemon / embedder model needed); the daemon op + CLI are live-verified."""
from __future__ import annotations

import numpy as np

from refmatrix.cli import _ann_similarity, _recall_display_score
from refmatrix.recall import _content_terms, hybrid_memory_recall


class FakeEmbedder:
    dim = 4

    def embed_texts(self, texts):
        return np.zeros((len(texts), self.dim), dtype="float32")


class FakeStore:
    def __init__(self, content, dense):
        self._content = content       # [(id, bm25_score)] best-first
        self._dense = dense           # [(id, l2_distance)] best-first
        self.content_calls = []

    def content_rank(self, terms, *, kinds=None, limit=50):
        self.content_calls.append((tuple(terms), tuple(kinds or ()), limit))
        return self._content[:limit]

    def ann_search(self, v, k, *, dim, kinds=None, candidate_ids=None):
        return self._dense[:k]


# ---- tokenizer -----------------------------------------------------------

def test_content_terms_tokenizes_dedupes_drops_short():
    assert _content_terms("grep backstop protected QUERY query") == [
        "grep", "backstop", "protected", "QUERY",
    ]
    assert _content_terms("  a  of x ") == ["of"]   # 1-char dropped, 'of' kept
    assert _content_terms("") == []


# ---- fusion --------------------------------------------------------------

def test_fusion_rescues_the_symbolic_winner_dense_buried():
    # The real shape: dense ranks the true memory (99) LAST; symbolic #1.
    dense = [(1, 0.10), (2, 0.20), (3, 0.30), (4, 0.40), (99, 0.95)]
    content = [(99, 8.0), (1, 0.5)]
    store = FakeStore(content, dense)
    fused = hybrid_memory_recall(store, FakeEmbedder(), "grep backstop", k=3)
    ids = [eid for eid, _ in fused]
    assert 99 in ids[:3]                              # fusion lifted it
    assert 99 not in [eid for eid, _ in dense[:3]]    # pure dense top-3 missed it


def test_fusion_scopes_content_rank_to_memory_kind():
    store = FakeStore([(1, 1.0)], [(1, 0.1)])
    hybrid_memory_recall(store, FakeEmbedder(), "hello world", k=5)
    terms, kinds, _limit = store.content_calls[0]
    assert kinds == ("memory",)
    assert "hello" in terms and "world" in terms


def test_empty_query_is_dense_only_no_content_rank():
    store = FakeStore([(1, 1.0)], [(7, 0.1), (8, 0.2)])
    fused = hybrid_memory_recall(store, FakeEmbedder(), "   ", k=5)
    assert [eid for eid, _ in fused] == [7, 8]        # dense order preserved
    assert store.content_calls == []                  # no terms → no symbolic side


def test_fused_score_descends_with_rank():
    dense = [(1, 0.1), (2, 0.2), (99, 0.9)]
    content = [(99, 5.0)]
    fused = hybrid_memory_recall(FakeStore(content, dense), FakeEmbedder(), "x y", k=3)
    scores = [s for _, s in fused]
    assert scores == sorted(scores, reverse=True)     # descending


# ---- display score (fused RRF vs dense cosine) ---------------------------

def test_display_score_fused_uses_rrf_value_directly():
    assert _recall_display_score({"id": 1, "score": 0.0321, "fused": True}) == 0.0321


def test_display_score_dense_converts_distance_to_cosine():
    h = {"id": 1, "distance": 0.6947}
    assert abs(_recall_display_score(h) - _ann_similarity(0.6947)) < 1e-9


def test_display_score_dense_higher_for_closer():
    assert _recall_display_score({"distance": 0.3}) > _recall_display_score({"distance": 0.9})
