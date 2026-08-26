"""The hub health signal must exercise a read path and look at the file.

cliquet ran for six days reporting `daemon_up: true, stale_files: 0` while
every memory read raised (1013 logged failures) and its catalog had grown to
41GB for 45 documents. Both signals were true; neither could have caught it.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    yield s
    s.close()


def test_missing_partition_raises_a_diagnosis_not_a_typeerror(store, monkeypatch):
    """`row[0]` on a None gave `TypeError: 'NoneType' object is not
    subscriptable` forty frames from the cause, and the daemon swallowed it
    into a silent fallback. The message has to name the fault."""
    calls = {"n": 0}
    real = store._conn.execute

    def fake(sql, *a, **kw):
        # Starve BOTH partition lookups — the indexed one and the
        # pushdown-defeating retry — as an empty catalog would.
        if "FROM partitions WHERE name" in sql:
            calls["n"] += 1

            class Empty:
                def fetchone(self_inner):
                    return None
            return Empty()
        return real(sql, *a, **kw)

    monkeypatch.setattr(store._conn, "execute", fake)
    with pytest.raises(RuntimeError) as exc:
        store._ensure_partition()
    assert "partition" in str(exc.value)
    assert calls["n"] == 2, "must retry through a pushdown-defeating predicate"


def test_corrupt_statistics_are_named_as_such(store, monkeypatch):
    """When the indexed predicate misses but the expression form finds the row,
    that is a damaged zonemap — the exact live failure on cliquet. Say so."""
    real = store._conn.execute

    def fake(sql, *a, **kw):
        if "FROM partitions WHERE name=?" in sql:
            class Empty:
                def fetchone(self_inner):
                    return None
            return Empty()
        return real(sql, *a, **kw)

    monkeypatch.setattr(store._conn, "execute", fake)
    with pytest.raises(RuntimeError) as exc:
        store._ensure_partition()
    assert "statistics are corrupt" in str(exc.value)


def test_recent_memories_is_a_usable_liveness_probe(store):
    """`_store_health` calls this to prove the memory path works. It must be
    cheap and must not raise on an empty store."""
    assert store.recent_memories(limit=1) == []
