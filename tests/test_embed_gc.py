"""Tests for `rmx embed --gc` and Store.gc_vectors.

GC removes lance vectors whose entity_id no longer exists in the catalog
for the (partition, kind) pair — the orphan class produced when
`memory forget` drops a catalog row without touching the dense layer."""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("lance")

from refmatrix.store import Store


def _seed_store(tmp_path):
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    return s


def _add_memory_with_vector(s: Store, name: str, dim: int = 8) -> int:
    eid = s.add_memory(name=name, content=f"body of {name}", mtype="curated")
    vec = np.random.rand(1, dim).astype("float32")
    s.upsert_vector([eid], vec, kind="memory", dim=dim)
    return eid


def test_gc_no_orphans_returns_zero(tmp_path):
    s = _seed_store(tmp_path)
    _add_memory_with_vector(s, "m1")
    _add_memory_with_vector(s, "m2")
    result = s.gc_vectors(dim=8)
    assert "memory" in result
    assert result["memory"]["orphans"] == 0
    assert result["memory"]["kept"] == 2


def test_gc_drops_orphan_after_forget(tmp_path):
    s = _seed_store(tmp_path)
    e1 = _add_memory_with_vector(s, "keep")
    e2 = _add_memory_with_vector(s, "drop")
    # Forget the second memory — drops catalog row, vector stays.
    s.forget_memory(e2)
    pre = s.gc_vectors(dim=8, dry_run=True)
    assert pre["memory"]["orphans"] == 1
    assert pre["memory"]["kept"] == 1
    assert pre["memory"]["dry_run"] is True
    # Live run: actually drop.
    post = s.gc_vectors(dim=8)
    assert post["memory"]["orphans"] == 1
    assert post["memory"]["kept"] == 1
    # Second run finds nothing.
    again = s.gc_vectors(dim=8)
    assert again["memory"]["orphans"] == 0
    assert again["memory"]["kept"] == 1


def test_gc_no_lance_datasets_returns_empty(tmp_path):
    s = _seed_store(tmp_path)
    # No upserts → no lance dirs.
    result = s.gc_vectors(dim=8)
    assert result == {}


def test_gc_scoped_to_kind_filter(tmp_path):
    """`--kinds memory` skips other kinds even if they have orphans."""
    s = _seed_store(tmp_path)
    e_mem = _add_memory_with_vector(s, "m1")
    # Forget memory → orphan vector in memory.lance
    s.forget_memory(e_mem)
    result = s.gc_vectors(kinds=["memory"], dim=8)
    assert result["memory"]["orphans"] == 1
    # Other kinds not present, so map only carries 'memory'.
    assert set(result.keys()) == {"memory"}


def test_gc_partition_scoped(tmp_path):
    """A vector in partition A must not be GC'd by a partition-B run, even
    when partition-B has no matching catalog row for that id."""
    s = _seed_store(tmp_path)
    # Seed partition A
    with s.with_partition("partA"):
        _add_memory_with_vector(s, "a1")
    # Switch to partition B, run GC -- should leave partA vectors alone.
    with s.with_partition("partB"):
        result = s.gc_vectors(dim=8)
    # partB has no lance datasets, so result is empty.
    assert result == {}
    # Round-trip back to partA and confirm vector still there.
    with s.with_partition("partA"):
        result_a = s.gc_vectors(dim=8)
    assert result_a["memory"]["kept"] == 1
    assert result_a["memory"]["orphans"] == 0
