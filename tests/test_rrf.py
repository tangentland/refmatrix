"""Tests for Reciprocal Rank Fusion."""
from __future__ import annotations

import pytest

from refmatrix.context import build_context
from refmatrix.query import fuse_rrf
from refmatrix.store import Store


def test_fuse_rrf_unanimous_top_wins():
    # Same id at rank 0 in two lists beats a list's #1 with no overlap.
    a = [10, 20, 30]
    b = [10, 40, 50]
    fused = fuse_rrf([a, b])
    assert fused[0][0] == 10


def test_fuse_rrf_scores_sum_known_values():
    fused = fuse_rrf([[1, 2], [2, 1]], k=60)
    # id=1: 1/60 + 1/61, id=2: 1/61 + 1/60 — identical scores, id ascending breaks tie.
    assert fused[0][0] == 1
    assert fused[1][0] == 2
    assert pytest.approx(fused[0][1]) == pytest.approx(fused[1][1])


def test_fuse_rrf_empty_lists_return_empty():
    assert fuse_rrf([]) == []
    assert fuse_rrf([[], []]) == []


def test_fuse_rrf_tie_break_by_id_ascending():
    # Two distinct ids, same rank in different single lists → same score, lower id wins.
    fused = fuse_rrf([[7], [3]])
    assert [eid for eid, _ in fused] == [3, 7]


def test_fuse_rrf_deeper_rank_dampened():
    # k=60 means rank 0 (1/60) vs rank 10 (1/70) — close but ordered.
    fused = fuse_rrf([[100] + list(range(200, 210)), [100]])
    assert fused[0][0] == 100


@pytest.fixture
def fused_store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    parser = s.add_concept("parser")
    # Three docs in 'mentions' (weighted). One file in 'defines' (unweighted).
    doc_a = s.upsert_entity(kind="doc", name="A.md", path="/p/A.md", tldr="a")
    doc_b = s.upsert_entity(kind="doc", name="B.md", path="/p/B.md", tldr="b")
    doc_c = s.upsert_entity(kind="doc", name="C.md", path="/p/C.md", tldr="c")
    code_x = s.upsert_entity(kind="code", name="x.py", path="/p/x.py", tldr="x")
    s.weighted_link("mentions", parser, doc_a, weight=5.0)
    s.weighted_link("mentions", parser, doc_b, weight=3.0)
    s.weighted_link("mentions", parser, doc_c, weight=1.0)
    s.link("defines", parser, code_x)
    yield s
    s.close()


def test_build_context_fuse_preserves_anchor_and_groups(fused_store):
    b = build_context(fused_store, "parser", fuse=True)
    assert b.anchor is not None
    assert "mentions" in b.groups
    assert "defines" in b.groups


def test_build_context_fuse_includes_high_rank_from_late_linkage(fused_store):
    # 'mentions' comes after 'defines' in DEFAULT_LINKAGE_ORDER. Under a tight
    # entity cap without fusion, defines:x.py would consume the slot first.
    # With fusion, the top 'mentions' candidate must still appear in output.
    b = build_context(fused_store, "parser", fuse=True, max_entities=2)
    flat = {e.entity.name for entries in b.groups.values() for e in entries}
    assert "A.md" in flat
