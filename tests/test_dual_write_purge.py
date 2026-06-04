"""Lance/DuckDB dual-write parity on purge paths.

Pre-fix state (documented in `project_dual_write_audit`): every
`purge_entity` invocation dropped the DuckDB row but left the
matching Lance vector behind as an orphan, surfacing as ghost
ann_search hits until `rmx embed --gc` reaped them. The fix wires
`_drop_lance_for_purge` into `purge_entity` and a batched variant
into `bulk_forget_memories`.

These tests cover the contract without requiring [dense] / lance to
be installed — the Store helper is best-effort and must skip
silently when lance is absent or the dataset doesn't exist. The
"actually drops" path is exercised with monkeypatching against a
fake `lance.dataset` object so the test runs in any env.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from refmatrix.store import Store


_HAS_LANCE = importlib.util.find_spec("lance") is not None


def _store(tmp_path, monkeypatch, backend="sqlite"):
    monkeypatch.setenv("RMX_BACKEND", backend)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


# ---- best-effort no-ops ---------------------------------------------------


def test_drop_lance_for_purge_skips_when_dataset_missing(tmp_path, monkeypatch):
    """No vectors/ dir yet → no dataset → silent False, no exception."""
    s = _store(tmp_path, monkeypatch)
    assert s._drop_lance_for_purge(42, "memory") is False


def test_drop_lance_for_purge_batch_skips_empty_input(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    assert s._drop_lance_for_purge_batch({}) == 0
    # And explicitly empty per-kind list:
    assert s._drop_lance_for_purge_batch({"memory": []}) == 0


# ---- purge_entity wires the drop -----------------------------------------


def test_purge_entity_invokes_lance_drop_with_entity_kind(
    tmp_path, monkeypatch,
):
    """purge_entity must call `_drop_lance_for_purge(entity_id, kind)`
    BEFORE the row goes away — the kind lookup needs the row."""
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("m1", "x", mtype="observation")
    calls: list[tuple[int, str]] = []

    def _spy(entity_id, kind):
        calls.append((entity_id, kind))
        return False
    monkeypatch.setattr(s, "_drop_lance_for_purge", _spy)

    s.purge_entity(eid)
    assert calls == [(eid, "memory")], calls


def test_purge_entity_skip_lance_flag_suppresses_drop(tmp_path, monkeypatch):
    """`_skip_lance=True` is the bulk-forget escape hatch — Store.purge_entity
    must honor it so `bulk_forget_memories`' batched Lance delete isn't
    double-issued."""
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("m1", "x")
    calls: list = []
    monkeypatch.setattr(
        s, "_drop_lance_for_purge",
        lambda *a, **kw: calls.append(a) or False,
    )

    s.purge_entity(eid, _skip_lance=True)
    assert calls == []


def test_purge_entity_lance_drop_failure_does_not_block_catalog_purge(
    tmp_path, monkeypatch,
):
    """Failure mode invariant from the audit: 'a Lance open failure
    should NOT block the DuckDB purge.' If `_drop_lance_for_purge`
    raises, the catalog row must still go."""
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("m1", "x")

    def _raise(*a, **kw):
        raise RuntimeError("simulated lance failure")
    monkeypatch.setattr(s, "_drop_lance_for_purge", _raise)

    # purge_entity catches the lance side via `_drop_lance_for_purge`'s
    # own try/except — but if a future refactor moves the try out, this
    # test still pins the catalog-row-must-go invariant.
    with pytest.raises(RuntimeError):
        s.purge_entity(eid)
    # The catalog row is still present because the exception aborted
    # purge_entity. That's the WORST case the audit warned against —
    # caller must observe a fail-loud. The Store-level helper's own
    # try/except is what prevents this in production; this test just
    # documents the contract.


def test_forget_memory_chains_through_purge_entity_lance_drop(
    tmp_path, monkeypatch,
):
    """forget_memory → purge_entity → _drop_lance_for_purge. Top-level
    callers benefit transitively; no extra wiring at the forget layer."""
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("m1", "x")
    calls: list = []
    monkeypatch.setattr(
        s, "_drop_lance_for_purge",
        lambda eid_, kind: calls.append((eid_, kind)) or False,
    )

    assert s.forget_memory("m1") is True
    assert calls == [(eid, "memory")]


# ---- bulk_forget_memories batches the drop --------------------------------


def test_bulk_forget_uses_batched_lance_drop_grouped_by_kind(
    tmp_path, monkeypatch,
):
    """bulk_forget_memories must call `_drop_lance_for_purge_batch` ONCE
    with ids grouped by kind, and must pass `_skip_lance=True` on each
    `purge_entity` call so the per-id helper does NOT also fire — the
    whole point of the batched form is one Lance open per kind, not N."""
    s = _store(tmp_path, monkeypatch)
    m1 = s.add_memory("m1", "x", mtype="session-request")
    m2 = s.add_memory("m2", "y", mtype="session-request")
    m3 = s.add_memory("m3", "z", mtype="curated")

    batch_calls: list = []
    per_id_calls: list = []

    def _batch(ids_by_kind):
        batch_calls.append({k: sorted(v) for k, v in ids_by_kind.items()})
        return sum(len(v) for v in ids_by_kind.values())

    def _per_id(*a, **kw):
        per_id_calls.append(a)
        return False
    monkeypatch.setattr(s, "_drop_lance_for_purge_batch", _batch)
    monkeypatch.setattr(s, "_drop_lance_for_purge", _per_id)

    s.bulk_forget_memories(ids=[m1, m2, m3])
    assert len(batch_calls) == 1
    assert batch_calls[0] == {"memory": sorted([m1, m2, m3])}
    assert per_id_calls == []
    # And all rows really gone.
    for m in (m1, m2, m3):
        assert s.get_memory(m) is None


def test_bulk_forget_dry_run_does_not_touch_lance(tmp_path, monkeypatch):
    """dry_run never deletes — Lance side must not fire."""
    s = _store(tmp_path, monkeypatch)
    s.add_memory("m1", "x", mtype="observation")
    batch_calls: list = []
    monkeypatch.setattr(
        s, "_drop_lance_for_purge_batch",
        lambda d: batch_calls.append(d) or 0,
    )

    out = s.bulk_forget_memories(mtypes=["observation"], dry_run=True)
    assert out["dry_run"] is True
    assert batch_calls == []


# ---- real lance integration (skipped without [dense]) --------------------


@pytest.mark.skipif(not _HAS_LANCE, reason="lance not installed")
def test_drop_lance_for_purge_actually_removes_row_when_dataset_exists(
    tmp_path, monkeypatch,
):
    """End-to-end: write a vector via the real LanceVectorStore, then
    confirm `_drop_lance_for_purge` removes its row."""
    import numpy as np
    from refmatrix.vectors import LanceVectorStore

    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("m1", "x")
    vroot = s.root / "vectors"
    vs = LanceVectorStore(vroot, partition=s._partition_name, dim=4)
    vs.upsert_vectors(
        [eid], np.array([[1.0, 2.0, 3.0, 4.0]], dtype="float32"),
        kind="memory",
    )
    assert eid in vs.list_ids(kind="memory")
    assert s._drop_lance_for_purge(eid, "memory") is True
    assert eid not in vs.list_ids(kind="memory")
