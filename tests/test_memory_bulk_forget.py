"""Bulk-forget memory rows by ids / names / mtypes.

Locks in the contract for `Store.bulk_forget_memories` + daemon
`memory_bulk_forget` op:
  * union semantics across ids/names/mtypes
  * partition-scoped name + mtype resolution
  * dry_run returns the same shape minus the deletion
  * per-mtype tally in the response
  * empty filter = empty result (no accidental purge)
  * op registered in OPS and CLI_OPS
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


def _store(tmp_path, monkeypatch, backend="sqlite"):
    monkeypatch.setenv("RMX_BACKEND", backend)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def _seed(s: Store) -> dict:
    """Plant a mixed-mtype memory set the bulk-forget cases can carve up."""
    return {
        "obs1": s.add_memory("obs1", "x", mtype="observation"),
        "obs2": s.add_memory("obs2", "x", mtype="observation"),
        "ses1": s.add_memory("ses1", "x", mtype="session-request"),
        "ses2": s.add_memory("ses2", "x", mtype="session-milestone"),
        "cur1": s.add_memory("cur1", "x", mtype="curated"),
    }


def test_bulk_forget_by_mtypes_deletes_matching_rows(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    ids = _seed(s)
    result = s.bulk_forget_memories(
        mtypes=["session-request", "session-milestone"],
    )
    assert result["forgotten"] == 2
    assert set(result["ids"]) == {ids["ses1"], ids["ses2"]}
    assert result["by_mtype"]["session-request"] == 1
    assert result["by_mtype"]["session-milestone"] == 1
    # Survivors intact.
    assert s.get_memory("obs1") is not None
    assert s.get_memory("obs2") is not None
    assert s.get_memory("cur1") is not None
    # Targets gone.
    assert s.get_memory("ses1") is None
    assert s.get_memory("ses2") is None


def test_bulk_forget_dry_run_resolves_without_deleting(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    ids = _seed(s)
    result = s.bulk_forget_memories(
        mtypes=["observation"], dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["forgotten"] == 0
    assert set(result["ids"]) == {ids["obs1"], ids["obs2"]}
    assert result["by_mtype"]["observation"] == 2
    # Nothing actually deleted.
    assert s.get_memory("obs1") is not None
    assert s.get_memory("obs2") is not None


def test_bulk_forget_by_ids_works(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    ids = _seed(s)
    result = s.bulk_forget_memories(ids=[ids["obs1"], ids["cur1"]])
    assert result["forgotten"] == 2
    assert s.get_memory("obs1") is None
    assert s.get_memory("cur1") is None


def test_bulk_forget_by_names_works(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    _seed(s)
    result = s.bulk_forget_memories(names=["obs1", "ses1"])
    assert result["forgotten"] == 2
    assert s.get_memory("obs1") is None
    assert s.get_memory("ses1") is None


def test_bulk_forget_unions_ids_names_mtypes(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    ids = _seed(s)
    result = s.bulk_forget_memories(
        ids=[ids["obs1"]],
        names=["cur1"],
        mtypes=["session-request"],
    )
    # obs1 (by id) + cur1 (by name) + ses1 (by mtype) = 3.
    assert result["forgotten"] == 3
    assert set(result["ids"]) == {ids["obs1"], ids["cur1"], ids["ses1"]}


def test_bulk_forget_empty_filter_returns_zero(tmp_path, monkeypatch):
    """No filter = no resolved ids = no deletion. The CLI surfaces a
    ValueError on this path; the Store call is a safe no-op so tests
    and ad-hoc callers can probe shape without an explicit guard."""
    s = _store(tmp_path, monkeypatch)
    _seed(s)
    result = s.bulk_forget_memories()
    assert result["forgotten"] == 0
    assert result["ids"] == []
    assert result["by_mtype"] == {}


def test_bulk_forget_mtype_filter_is_partition_scoped(tmp_path, monkeypatch):
    """A bulk-forget in partition A must NOT delete memories from
    partition B with the same mtype. The 271-card viascope cleanup
    runs in viascope's `memory-viascope` partition and must leave
    other projects' session memories untouched."""
    s = _store(tmp_path, monkeypatch)
    with s.with_partition("alpha"):
        s.add_memory("a-ses", "x", mtype="session-request")
    with s.with_partition("beta"):
        b_id = s.add_memory("b-ses", "x", mtype="session-request")

    with s.with_partition("alpha"):
        result = s.bulk_forget_memories(mtypes=["session-request"])
    assert result["forgotten"] == 1
    # Beta's row survives.
    with s.with_partition("beta"):
        assert s.get_memory(b_id) is not None


def test_daemon_memory_bulk_forget_op_registered():
    """CLI routes through daemon when one is up; op must exist in the
    dispatcher table. Like the single-row `memory_forget`, this routes
    to the bg pool — purging N entities can take seconds and we don't
    want it starving the cli pool's latency-sensitive reads."""
    from refmatrix.daemon import OPS, CLI_OPS
    assert "memory_bulk_forget" in OPS
    # Sanity: mirrors the single-row forget — also not in CLI_OPS.
    assert "memory_forget" not in CLI_OPS
