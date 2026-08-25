"""`bulk_link(update_weight=True)` must be indistinguishable from a sequence of
`link()` calls.

The GMD body term-frequency sweep could not use bulk_link while it was
first-wins: one concept routinely reaches the same node twice — as a title
token (weight 2.0) and again as a body term (weight tf) — and DO NOTHING would
freeze the first weight, corrupting every BM25 score derived from it. That is
why the pass wrote ~1 row per unique term per document and took ~2.3s/doc on
prose. These tests pin the equivalence the batched path now relies on.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


@pytest.fixture(params=["sqlite", "duckdb"])
def store(tmp_path, request, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend=request.param)
    s.init()
    yield s
    s.close()


def _weight(s: Store, linkage: str, cid: int, eid: int):
    lid = s.get_linkage_id(linkage)
    row = s._connect().execute(
        "SELECT weight FROM entity_links "
        "WHERE entity_id = ? AND linkage_id = ? AND concept_id = ?",
        (eid, lid, cid),
    ).fetchone()
    return None if row is None else row[0]


def _setup(s: Store):
    s.add_linkage_type("mentions")
    eid = s.upsert_entity(kind="doc", name="doc-a")
    cid = s.add_concept("alpha")
    return cid, eid


def test_update_weight_overwrites_existing(store):
    cid, eid = _setup(store)
    store.link("mentions", cid, eid, weight=2.0)
    store.bulk_link([("mentions", cid, eid, 7.0)], update_weight=True)
    assert _weight(store, "mentions", cid, eid) == 7.0


def test_default_mode_still_first_wins(store):
    cid, eid = _setup(store)
    store.link("mentions", cid, eid, weight=2.0)
    store.bulk_link([("mentions", cid, eid, 7.0)])
    assert _weight(store, "mentions", cid, eid) == 2.0


def test_null_weight_preserves_stored_value(store):
    """link() leaves a stored weight alone when the incoming one is NULL, so
    the batched path must too — the wikilink `mentions` pass in ingest_gmd
    passes no weight and must not erase a term frequency."""
    cid, eid = _setup(store)
    store.link("mentions", cid, eid, weight=5.0)
    store.bulk_link([("mentions", cid, eid, None)], update_weight=True)
    assert _weight(store, "mentions", cid, eid) == 5.0


def test_duplicate_keys_in_one_batch_keep_the_last(store):
    """DuckDB refuses to update the same row twice in one ON CONFLICT DO
    UPDATE, so duplicates are collapsed in Python. Last-wins is what the
    equivalent link() sequence produces — title token first, body tf second."""
    cid, eid = _setup(store)
    store.bulk_link(
        [("mentions", cid, eid, 2.0), ("mentions", cid, eid, 9.0)],
        update_weight=True,
    )
    assert _weight(store, "mentions", cid, eid) == 9.0


def test_matches_per_row_link_sequence(store, tmp_path):
    """End-to-end equivalence on the exact shape the GMD sweep emits."""
    store.add_linkage_type("mentions")
    eid = store.upsert_entity(kind="doc", name="doc-seq")
    terms = {"alpha": 2.0, "beta": 3.0, "gamma": 1.0}
    cids = {t: store.add_concept(t) for t in terms}

    # per-row reference: title weight first, then the body tf
    for t in terms:
        store.link("mentions", cids[t], eid, weight=2.0)
    for t, tf in terms.items():
        store.link("mentions", cids[t], eid, weight=tf)
    reference = {t: _weight(store, "mentions", cids[t], eid) for t in terms}

    eid2 = store.upsert_entity(kind="doc", name="doc-batch")
    batch = [("mentions", cids[t], eid2, 2.0) for t in terms]
    batch += [("mentions", cids[t], eid2, tf) for t, tf in terms.items()]
    store.bulk_link(batch, update_weight=True)
    batched = {t: _weight(store, "mentions", cids[t], eid2) for t in terms}

    assert batched == reference
    assert batched == terms
