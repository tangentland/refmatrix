"""Phase-2c: bulk_link batches many link inserts into one Arrow batch. Covers semantics + a
small benchmark gate. (Both-backend until S1, 2026-11-19; DuckDB is the one backend.)"""
from __future__ import annotations

import time

import pytest

from refmatrix.query import QueryEngine
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def test_bulk_link_inserts_and_returns_new_count(store):
    parser = store.add_concept("parser")
    a = store.upsert_entity(kind="code", name="a.py")
    b = store.upsert_entity(kind="code", name="b.py")
    c = store.upsert_entity(kind="code", name="c.py")
    added = store.bulk_link([
        ("defines", parser, a, None),
        ("defines", parser, b, 0.5),
        ("defines", parser, c, None),
    ])
    assert added == 3
    qe = QueryEngine(store)
    assert set(qe.run("defines:parser")) == {a, b, c}


def test_bulk_link_skips_existing_pairs(store):
    parser = store.add_concept("parser")
    a = store.upsert_entity(kind="code", name="a.py")
    b = store.upsert_entity(kind="code", name="b.py")
    store.link("defines", parser, a)
    added = store.bulk_link([
        ("defines", parser, a, None),  # already linked
        ("defines", parser, b, None),  # new
    ])
    assert added == 1


def test_bulk_link_empty_is_noop(store):
    assert store.bulk_link([]) == 0


def test_bulk_link_handles_multiple_linkages(store):
    parser = store.add_concept("parser")
    tok = store.add_concept("tokenizer")
    a = store.upsert_entity(kind="code", name="a.py")
    b = store.upsert_entity(kind="code", name="b.py")
    added = store.bulk_link([
        ("defines", parser, a, None),
        ("mentions", parser, b, None),
        ("defines", tok, a, None),
    ])
    assert added == 3
    qe = QueryEngine(store)
    assert set(qe.run("defines:parser")) == {a}
    assert set(qe.run("mentions:parser")) == {b}
    assert set(qe.run("defines:tokenizer")) == {a}


def test_bulk_link_preserves_weights_on_duckdb_only(store):
    """The Arrow path stores the weight on the initial insert."""
    parser = store.add_concept("parser")
    a = store.upsert_entity(kind="code", name="a.py")
    store.bulk_link([("defines", parser, a, 0.42)])
    assert store.get_weight("defines", parser, a) == 0.42


def test_bulk_link_beats_per_row_link_on_throughput(tmp_path, monkeypatch):
    """Gate: bulk_link must be at least 2× faster than the equivalent per-row
    `link()` loop on a moderately-sized batch (the Arrow path is the win)."""
    N = 2000

    def _build(name: str):
        s = Store(tmp_path / name)
        s.init()
        cid = s.add_concept("hot")
        eids = [s.upsert_entity(kind="code", name=f"f{i}.py") for i in range(N)]
        return s, cid, eids

    # Per-row baseline.
    s1, cid, eids = _build("per_row")
    t0 = time.perf_counter()
    for e in eids:
        s1.link("defines", cid, e)
    per_row = time.perf_counter() - t0
    s1.close()

    # Bulk path.
    s2, cid2, eids2 = _build("bulk")
    items = [("defines", cid2, e, None) for e in eids2]
    t0 = time.perf_counter()
    added = s2.bulk_link(items)
    bulk = time.perf_counter() - t0
    s2.close()

    assert added == N
    # Generous gate: at least 2× speedup. Local runs typically see 5-10×.
    assert bulk * 2 < per_row, (
        f"bulk_link not faster enough: bulk={bulk:.3f}s "
        f"per_row={per_row:.3f}s ratio={per_row / bulk:.1f}×"
    )
