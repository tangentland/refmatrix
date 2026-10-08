"""bug-085: a file re-sync purged its symbols' vectors ONE Lance delete each.

py-spy on the wedged daemon (2026-10-07 10:14, pid 1569) put 92% of the busy
thread in `lance.dataset.delete("id = N")`, called from
`watch flush -> sync_files -> purge_path -> purge_entity -> _drop_lance_for_purge`
once per entity of the edited file, under `_store_lock`. Editing store.py (221
entities) held the lock for 6+ minutes; every client queued behind it. The
batched `_drop_lance_for_purge_batch` already existed for `_bulk_purge_ids` but
`purge_path` never used it.

Real Lance, no fakes: each Lance delete commits a new dataset VERSION, so the
version count is the observable number of deletes issued.
"""
from __future__ import annotations

import pytest

import importlib.util

# Skip ONLY when lance is not installed. An installed lance that fails to
# import (e.g. `typing_inspection` missing from the venv) must FAIL here, not
# skip — importorskip read both as "absent" (ch-bsd r8 #s-4).
if importlib.util.find_spec("lance") is None:
    pytest.skip("lance not installed", allow_module_level=True)
import lance  # noqa: E402
import pyarrow as pa  # noqa: E402

from refmatrix.store import Store


def _code_dataset(s: Store, ids: list[int]):
    path = s.root / "vectors" / s._partition_name / "code.lance"
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({
        "id": pa.array(ids, pa.int64()),
        "vector": pa.array([[0.0, 1.0]] * len(ids), pa.list_(pa.float32(), 2)),
    })
    lance.write_dataset(table, str(path))
    return path


def test_purge_path_issues_one_lance_delete_per_kind_not_per_entity(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    src = tmp_path / "big.py"
    src.write_text("x = 1\n")
    ids = [s.upsert_entity("code", f"big.py::f{i}", path=str(src)) for i in range(12)]
    other = s.upsert_entity("code", "other.py::g", path=str(tmp_path / "other.py"))
    path = _code_dataset(s, ids + [other])
    before = lance.dataset(str(path)).version

    removed = s.purge_path(str(src))

    ds = lance.dataset(str(path))
    assert removed == 12
    assert ds.version - before == 1, (
        f"{ds.version - before} Lance commits for one file's purge; "
        "bug-085: one per entity held the store lock for minutes")
    left = sorted(ds.to_table(columns=["id"]).column("id").to_pylist())
    assert left == [other], left


def _dataset(s: Store, kind: str, ids: list[int]):
    path = s.root / "vectors" / s._partition_name / f"{kind}.lance"
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({
        "id": pa.array(ids, pa.int64()),
        "vector": pa.array([[0.0, 1.0]] * len(ids), pa.list_(pa.float32(), 2)),
    })
    lance.write_dataset(table, str(path))
    return path


# The two sibling loops over concepts had the same per-entity Lance delete.

def test_prune_noise_drop_issues_one_lance_delete(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    ents = [s.upsert_entity(kind="code", name=f"f{i}.py") for i in range(20)]
    rare = []
    for i in range(6):
        c = s.add_namespaced_concept("keyword", f"rare{i}")
        s.link("mentions", c, ents[i])
        rare.append(c)
    path = _dataset(s, "concept", rare)
    before = lance.dataset(str(path)).version

    out = s.prune_noise(min_df=2, max_df_ratio=0.25, drop=True)

    ds = lance.dataset(str(path))
    assert out["dropped"] == 6
    assert ds.version - before == 1, ds.version - before
    assert ds.count_rows() == 0


def test_fold_concept_dups_issues_one_lance_delete(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    cids = []
    for i in range(4):
        s.add_memory(name=f"dup{i}", content="body")
        cids.append(s.upsert_entity(kind="concept", name=f"dup{i}"))
    path = _dataset(s, "concept", cids)
    before = lance.dataset(str(path)).version

    res = s.fold_concept_dups()

    ds = lance.dataset(str(path))
    assert res["folded"] == 4
    assert ds.version - before == 1, ds.version - before
    assert ds.count_rows() == 0
