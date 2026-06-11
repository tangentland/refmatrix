"""A no-op re-upsert must NOT bump `entities.updated_at`.

Regression guard for the ingest->embed coupling: every re-ingest used to set
`updated_at = excluded.updated_at` unconditionally, so an unchanged entity looked
freshly modified each cycle. `pending_embeddings` keys staleness on
`vectors_updated_at < updated_at`, so the whole store re-staled (the ~2709-vector
re-embed tax) on every no-op ingest. `updated_at` now advances only when an
embedding-/content-relevant field actually changes. Both upsert paths covered.
"""
from __future__ import annotations

import refmatrix.store as store_mod
from refmatrix.store import Store


def _clock(monkeypatch, start: float = 1000.0):
    """Deterministic, monotonic-on-demand clock for store.time.time()."""
    box = {"t": start}
    monkeypatch.setattr(store_mod.time, "time", lambda: box["t"])
    return box


def _updated_at(s: Store, eid: int) -> float:
    return s._connect().execute(
        "SELECT updated_at FROM entities WHERE id=?", (eid,)
    ).fetchone()[0]


def _mark_embedded(s: Store, eid: int, ts: float) -> None:
    con = s._connect()
    con.execute("UPDATE entities SET vectors_updated_at=? WHERE id=?", (ts, eid))
    con.commit()


def test_noop_reupsert_does_not_bump_updated_at(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    s = Store(tmp_path / ".refmatrix")
    s.init()

    eid = s.upsert_entity("code", "pkg/mod.py", path="/abs/pkg/mod.py",
                          tldr="def f(x): summary")
    u1 = _updated_at(s, eid)
    assert u1 == 1000.0

    # Same content re-ingested later in time -> updated_at must NOT move.
    clock["t"] = 2000.0
    eid2 = s.upsert_entity("code", "pkg/mod.py", path="/abs/pkg/mod.py",
                           tldr="def f(x): summary")
    assert eid2 == eid
    assert _updated_at(s, eid) == u1, "no-op re-upsert bumped updated_at"

    # A real tldr change -> updated_at advances to the new now.
    clock["t"] = 3000.0
    s.upsert_entity("code", "pkg/mod.py", path="/abs/pkg/mod.py",
                    tldr="def f(x): NEW summary")
    assert _updated_at(s, eid) == 3000.0
    s.close()


def test_noop_reupsert_keeps_vector_fresh(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    s = Store(tmp_path / ".refmatrix")
    s.init()

    eid = s.upsert_entity("code", "a.py", path="/a.py", tldr="alpha")
    # Simulate the embed pass having vectorized it at the same instant.
    _mark_embedded(s, eid, 1000.0)
    assert [r[0] for r in s.pending_embeddings(kinds=["code"])] == []

    # No-op re-ingest later: the vector must stay fresh (no re-embed tax).
    clock["t"] = 2000.0
    s.upsert_entity("code", "a.py", path="/a.py", tldr="alpha")
    assert s.pending_embeddings(kinds=["code"]) == [], \
        "no-op re-ingest re-staled an unchanged vector"

    # Content change re-stales exactly that entity.
    clock["t"] = 3000.0
    s.upsert_entity("code", "a.py", path="/a.py", tldr="alpha PRIME")
    assert [r[0] for r in s.pending_embeddings(kinds=["code"])] == [eid]
    s.close()


def test_bulk_upsert_noop_does_not_bump_updated_at(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)
    s = Store(tmp_path / ".refmatrix")
    s.init()

    rows = [
        ("code", "one.py", "/one.py", "tldr one", None),
        ("code", "two.py", "/two.py", "tldr two", None),
    ]
    ids = s.bulk_upsert_entity(rows)
    u_before = {i: _updated_at(s, i) for i in ids}
    assert set(u_before.values()) == {1000.0}

    # Identical bulk re-upsert later -> no row bumps.
    clock["t"] = 2000.0
    s.bulk_upsert_entity(rows)
    for i in ids:
        assert _updated_at(s, i) == u_before[i], "bulk no-op bumped updated_at"

    # Change just one row's tldr -> only that row advances.
    clock["t"] = 3000.0
    s.bulk_upsert_entity([
        ("code", "one.py", "/one.py", "tldr one CHANGED", None),
        ("code", "two.py", "/two.py", "tldr two", None),
    ])
    assert _updated_at(s, ids[0]) == 3000.0
    assert _updated_at(s, ids[1]) == u_before[ids[1]]
    s.close()
