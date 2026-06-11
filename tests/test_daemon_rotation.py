"""Rotation slot bootstrap + asymmetric repair tests.

Regression coverage for the data-loss bug where deleting one of the
two slot files would make `_bootstrap_rotation_if_needed` fall into
the legacy-seed path and clobber the surviving slot with a stale
pre-rotation snapshot.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# DuckDB backend only; SQLite stores don't have rotation slots.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("duckdb") is None,
    reason="duckdb not installed",
)


def _make_daemon(tmp_path: Path):
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    s = Store(root)
    s.init()
    d = Daemon(root)
    d.store = s
    return d


def test_bootstrap_both_slots_present_is_noop(tmp_path):
    d = _make_daemon(tmp_path)
    a = d._replica_file("A")
    b = d._replica_file("B")
    a.touch()
    b.touch()
    (d.root / "active").write_text("A")
    a_before = a.stat().st_size
    b_before = b.stat().st_size
    d._bootstrap_rotation_if_needed()
    assert a.stat().st_size == a_before
    assert b.stat().st_size == b_before


def test_bootstrap_asymmetric_b_only_repairs_from_b(tmp_path):
    """The data-loss regression: only B exists. The old code would have
    copied the legacy catalog.duckdb over B (clobbering it). The repair
    path must clone B -> A instead."""
    import shutil

    d = _make_daemon(tmp_path)
    a = d._replica_file("A")
    b = d._replica_file("B")
    legacy = d.root / "catalog.duckdb"

    # Make a unique B that we want preserved + a stale legacy that
    # would clobber if the old code path ran.
    b.write_bytes(b"FRESH-B-DATA")
    legacy.write_bytes(b"STALE-LEGACY-DATA")
    (d.root / "active").write_text("B")
    assert not a.exists()

    # The store opened catalog.duckdb on init. Repair will close it
    # and re-open against the active slot; for this unit test we just
    # care that B's bytes survive.
    d._bootstrap_rotation_if_needed()

    assert a.exists()
    assert b.read_bytes() == b"FRESH-B-DATA"  # NOT clobbered
    assert a.read_bytes() == b"FRESH-B-DATA"  # cloned from survivor
    active = (d.root / "active").read_text().strip()
    assert active == "B"  # marker preserved


def test_bootstrap_asymmetric_a_only_repairs_from_a(tmp_path):
    d = _make_daemon(tmp_path)
    a = d._replica_file("A")
    b = d._replica_file("B")
    legacy = d.root / "catalog.duckdb"

    a.write_bytes(b"FRESH-A-DATA")
    legacy.write_bytes(b"STALE-LEGACY-DATA")
    # No active marker -- forces default to survivor (A).

    d._bootstrap_rotation_if_needed()

    assert a.read_bytes() == b"FRESH-A-DATA"
    assert b.exists()
    assert b.read_bytes() == b"FRESH-A-DATA"
    active = (d.root / "active").read_text().strip()
    assert active == "A"


def test_bootstrap_no_slots_falls_back_to_legacy(tmp_path):
    """When neither slot exists, the legacy seed path is still
    correct -- it's the only data we have. Behavior preserved."""
    d = _make_daemon(tmp_path)
    legacy = d.root / "catalog.duckdb"
    # The Store's init() created this file on _make_daemon. Just
    # ensure the slots aren't there yet.
    a = d._replica_file("A")
    b = d._replica_file("B")
    if a.exists():
        a.unlink()
    if b.exists():
        b.unlink()
    assert legacy.exists()

    d._bootstrap_rotation_if_needed()

    assert a.exists()
    assert b.exists()
    # Both seeded from the same legacy file: identical bytes.
    assert a.read_bytes() == b.read_bytes()


def test_refresh_replica_now_is_dropped_noop(tmp_path):
    """Writer rotation is dropped: _refresh_replica_now never swaps. It
    returns a no-op sentinel and leaves the active slot untouched (reads come
    from the snapshot tier, the writer stays pinned)."""
    d = _make_daemon(tmp_path)
    d._active_slot = d._read_active_slot()
    before = d._active_slot
    res = d._refresh_replica_now()
    assert res.get("enabled") is False
    assert "dropped" in (res.get("reason") or "")
    assert d._active_slot == before
