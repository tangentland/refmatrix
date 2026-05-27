"""LanceVectorStore unit tests.

Skipped when the [dense] extra (pylance / numpy) isn't installed so
core test suites stay green on lean installs.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HAS_LANCE = importlib.util.find_spec("lance") is not None
_HAS_NUMPY = importlib.util.find_spec("numpy") is not None
pytestmark = pytest.mark.skipif(
    not (_HAS_LANCE and _HAS_NUMPY),
    reason="[dense] extra not installed (pylance + numpy required)",
)


@pytest.fixture
def vector_root(tmp_path):
    return tmp_path / ".refmatrix" / "vectors"


def test_upsert_and_search_roundtrip(vector_root):
    import numpy as np
    from refmatrix.vectors import LanceVectorStore

    vs = LanceVectorStore(vector_root, partition="default", dim=8)
    # 5 distinct random unit vectors, deterministic
    rng = np.random.default_rng(42)
    raw = rng.standard_normal((5, 8)).astype("float32")
    vectors = raw / np.linalg.norm(raw, axis=1, keepdims=True)
    ids = [10, 11, 12, 13, 14]
    vs.upsert_vectors(ids, vectors, kind="memory")

    # Query with the first vector — its own id must be top hit.
    hits = vs.ann_search(vectors[0], k=3, kinds=["memory"])
    assert len(hits) >= 1
    assert hits[0][0] == 10
    # Score is a distance proxy; top-1 should be at or near zero.
    assert hits[0][1] <= 0.01


def test_upsert_is_idempotent_on_repeated_ids(vector_root):
    import numpy as np
    from refmatrix.vectors import LanceVectorStore

    vs = LanceVectorStore(vector_root, partition="default", dim=4)
    v1 = np.array([[1.0, 0.0, 0.0, 0.0]], dtype="float32")
    v2 = np.array([[0.0, 1.0, 0.0, 0.0]], dtype="float32")
    vs.upsert_vectors([7], v1, kind="memory")
    vs.upsert_vectors([7], v2, kind="memory")  # overwrite

    hits = vs.ann_search(v2[0], k=1, kinds=["memory"])
    assert hits[0][0] == 7
    # The overwritten vector should match v2, not v1 — score very close
    # to zero for the v2 query.
    assert hits[0][1] <= 0.01


def test_drop_for_removes_vectors(vector_root):
    import numpy as np
    from refmatrix.vectors import LanceVectorStore

    vs = LanceVectorStore(vector_root, partition="default", dim=4)
    raw = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype="float32"
    )
    vs.upsert_vectors([1, 2], raw, kind="memory")

    vs.drop_for([1], kind="memory")
    hits = vs.ann_search(raw[0], k=2, kinds=["memory"])
    ids = {h[0] for h in hits}
    assert 1 not in ids
    assert 2 in ids


def test_search_across_multiple_kinds(vector_root):
    import numpy as np
    from refmatrix.vectors import LanceVectorStore

    vs = LanceVectorStore(vector_root, partition="default", dim=4)
    v_mem = np.array([[1.0, 0.0, 0.0, 0.0]], dtype="float32")
    v_code = np.array([[1.0, 0.0, 0.0, 0.0]], dtype="float32")
    vs.upsert_vectors([100], v_mem, kind="memory")
    vs.upsert_vectors([200], v_code, kind="code")

    hits = vs.ann_search(v_mem[0], k=5, kinds=["memory", "code"])
    ids = {h[0] for h in hits}
    assert {100, 200}.issubset(ids)


def test_search_kind_filter(vector_root):
    import numpy as np
    from refmatrix.vectors import LanceVectorStore

    vs = LanceVectorStore(vector_root, partition="default", dim=4)
    v = np.array([[1.0, 0.0, 0.0, 0.0]], dtype="float32")
    vs.upsert_vectors([1], v, kind="memory")
    vs.upsert_vectors([2], v, kind="code")

    hits_mem = vs.ann_search(v[0], k=5, kinds=["memory"])
    hits_code = vs.ann_search(v[0], k=5, kinds=["code"])
    assert {h[0] for h in hits_mem} == {1}
    assert {h[0] for h in hits_code} == {2}


def test_empty_kind_returns_empty(vector_root):
    import numpy as np
    from refmatrix.vectors import LanceVectorStore

    vs = LanceVectorStore(vector_root, partition="default", dim=4)
    v = np.zeros(4, dtype="float32")
    assert vs.ann_search(v, k=5, kinds=["memory"]) == []


def test_partition_isolation(vector_root):
    import numpy as np
    from refmatrix.vectors import LanceVectorStore

    a = LanceVectorStore(vector_root, partition="A", dim=4)
    b = LanceVectorStore(vector_root, partition="B", dim=4)
    v = np.array([[1.0, 0.0, 0.0, 0.0]], dtype="float32")
    a.upsert_vectors([1], v, kind="memory")
    # B sees nothing in `memory`.
    assert b.ann_search(v[0], k=5, kinds=["memory"]) == []
    # A still sees its row.
    assert a.ann_search(v[0], k=5, kinds=["memory"])[0][0] == 1
