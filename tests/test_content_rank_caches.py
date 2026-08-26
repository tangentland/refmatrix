"""content_rank's read-side caches must be transparent, not just fast.

Profiled on a 1307-document store, a 16-term natural-language ref cost 260 ms
median, of which the postings scan — the part an inverted index actually does —
was 4.9 ms. The rest was work re-derived per query: a `LIKE '%/term'` scan per
term (110.9 ms), a `SUM(weight) GROUP BY` over 96% of the corpus (109.4 ms),
and one `COUNT(DISTINCT)` per term (19.1 ms). These tests pin that removing
that work changes nothing about the answers.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


@pytest.fixture(params=["sqlite", "duckdb"])
def store(tmp_path, request, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend=request.param)
    s.init()
    s.add_linkage_type("mentions")
    docs = {
        "d1": {"alpha": 3.0, "beta": 1.0},
        "d2": {"beta": 5.0},
        "d3": {"alpha": 1.0, "gamma": 2.0},
    }
    cids = {t: s.add_concept(t) for t in ("alpha", "beta", "gamma")}
    # A namespaced concept: reachable by its LEAF (`keyword/alpha` <- "alpha").
    ns = s.add_namespaced_concept("keyword", "alpha", description="kw")
    for name, tfs in docs.items():
        eid = s.upsert_entity(kind="doc", name=name)
        for t, tf in tfs.items():
            s.link("mentions", cids[t], eid, weight=tf)
        if name == "d2":
            s.link("mentions", ns, eid, weight=4.0)
    yield s
    s.close()


def test_namespaced_leaf_index_finds_what_the_like_scan_found(store):
    idx = store._namespaced_leaf_index()
    assert "alpha" in idx, "keyword/alpha must be reachable by its leaf"
    assert store.add_namespaced_concept("keyword", "alpha") in idx["alpha"]


def test_doclen_matches_a_live_sum(store):
    mlid = store.get_linkage_id("mentions")
    cached = store._mentions_doclen(mlid)
    live = {
        int(r[0]): float(r[1] or 0.0)
        for r in store._connect().execute(
            "SELECT el.entity_id, SUM(el.weight) FROM entity_links el "
            "JOIN entities e ON e.id = el.entity_id "
            "WHERE el.linkage_id=? AND e.partition_id=? GROUP BY el.entity_id",
            (mlid, store._partition_id),
        )
    }
    assert cached == live


def test_batched_resolve_matches_the_singular_form(store):
    names = ["alpha", "beta", "gamma", "nosuchterm"]
    batched = store.resolve_concept_ids_many(names)
    for n in names:
        assert batched[n] == store.resolve_concept_ids(n, strict=False), n


def test_flush_fragments_drops_the_caches(store):
    """The caches are only sound because a write boundary clears them. If
    flush_fragments stops doing that, a long-lived daemon Store serves BM25
    denominators from before the last ingest."""
    mlid = store.get_linkage_id("mentions")
    store._mentions_doclen(mlid)
    store._namespaced_leaf_index()
    store._mentions_bm25_stats(mlid)
    assert hasattr(store, "_doclen_cache")
    store.flush_fragments()
    for attr in ("_doclen_cache", "_leafidx_cache", "_bm25_stats_cache"):
        assert not hasattr(store, attr), attr


def test_a_document_ingested_after_the_cache_still_scores(store):
    """A missing doclen entry falls back to avgdl rather than dropping the
    document — the property that makes caching safe between write batches."""
    mlid = store.get_linkage_id("mentions")
    store._mentions_doclen(mlid)          # cache built WITHOUT d4
    cid = store.add_concept("alpha")
    new = store.upsert_entity(kind="doc", name="d4")
    store.link("mentions", cid, new, weight=9.0)
    hits = dict(store.content_rank(["alpha"], kinds=["doc"], limit=10))
    assert new in hits and hits[new] > 0


def test_scores_are_unchanged_by_caching(store):
    """Same query, cold and warm, must produce identical scores."""
    cold = store.content_rank(["alpha", "beta"], kinds=["doc"], limit=10)
    warm = store.content_rank(["alpha", "beta"], kinds=["doc"], limit=10)
    assert cold == warm
    store.flush_fragments()               # drop caches, recompute from scratch
    assert store.content_rank(["alpha", "beta"], kinds=["doc"], limit=10) == cold


def test_ranking_is_deterministic_across_equal_scores(store):
    """Ties must break on entity_id, not on whatever order the query planner
    returned rows in. d1 and d3 both carry `alpha` — a stable order is the
    difference between a reproducible eval and 19-of-90 phantom diffs."""
    cid = store.add_concept("delta")
    ids = [store.upsert_entity(kind="doc", name=f"tie{i}") for i in range(6)]
    for eid in ids:
        store.link("mentions", cid, eid, weight=2.0)
    runs = []
    for _ in range(3):
        store.flush_fragments()           # force a cold recompute each time
        runs.append([e for e, _ in store.content_rank(["delta"], kinds=["doc"],
                                                      limit=10)])
    assert runs[0] == runs[1] == runs[2]
    tied = [e for e in runs[0] if e in ids]
    assert tied == sorted(tied), "equal scores must come back in id order"
