"""Store-level Lance wrappers + vectors_updated_at column tests."""
from __future__ import annotations

import importlib.util

import pytest

_HAS_DENSE = (
    importlib.util.find_spec("lance") is not None
    and importlib.util.find_spec("numpy") is not None
)
pytestmark = pytest.mark.skipif(
    not _HAS_DENSE,
    reason="[dense] extra not installed (pylance + numpy required)",
)


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def test_vectors_updated_at_column_present(store):
    """Schema migration adds vectors_updated_at on init for both backends."""
    con = store._connect()
    backend = store._backend.kind
    if backend == "sqlite":
        cols = {r[1] for r in con.execute("PRAGMA table_info(entities)")}
    else:
        cols = {
            r[0]
            for r in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='entities'"
            ).fetchall()
        }
    assert "vectors_updated_at" in cols


def test_upsert_vector_marks_embedded_timestamp(store):
    import numpy as np

    eid = store.upsert_entity(kind="code", name="foo.py", path="/x/foo.py")
    v = np.zeros((1, 4), dtype="float32")
    v[0, 0] = 1.0
    store.upsert_vector([eid], v, kind="code", dim=4)

    row = store._connect().execute(
        "SELECT vectors_updated_at FROM entities WHERE id = ?",
        [eid],
    ).fetchone()
    assert row[0] is not None


def test_pending_embeddings_filters_to_stale(store):
    import numpy as np
    import time

    a = store.upsert_entity(kind="code", name="a.py", path="/x/a.py")
    b = store.upsert_entity(kind="code", name="b.py", path="/x/b.py")
    # Embed only a; b should be pending.
    v = np.zeros((1, 4), dtype="float32")
    v[0, 0] = 1.0
    store.upsert_vector([a], v, kind="code", dim=4)

    pending = store.pending_embeddings(kinds=["code"])
    ids = [p[0] for p in pending]
    assert b in ids
    assert a not in ids

    # Touch a's updated_at to a future value; pending must now include it.
    store._connect().execute(
        "UPDATE entities SET updated_at = ? WHERE id = ?",
        [time.time() + 3600, a],
    )
    store._connect().commit()
    pending = store.pending_embeddings(kinds=["code"])
    ids = [p[0] for p in pending]
    assert a in ids


def test_ann_search_returns_inserted_entity(store):
    import numpy as np

    eid = store.upsert_entity(kind="code", name="x.py", path="/x/x.py")
    v = np.zeros((1, 4), dtype="float32")
    v[0, 0] = 1.0
    store.upsert_vector([eid], v, kind="code", dim=4)
    hits = store.ann_search(v[0], k=3, dim=4, kinds=["code"])
    assert hits[0][0] == eid


def test_drop_vectors_clears_timestamp(store):
    import numpy as np

    eid = store.upsert_entity(kind="code", name="y.py", path="/x/y.py")
    v = np.zeros((1, 4), dtype="float32")
    v[0, 0] = 1.0
    store.upsert_vector([eid], v, kind="code", dim=4)
    store.drop_vectors([eid], kind="code", dim=4)
    row = store._connect().execute(
        "SELECT vectors_updated_at FROM entities WHERE id = ?",
        [eid],
    ).fetchone()
    assert row[0] is None
