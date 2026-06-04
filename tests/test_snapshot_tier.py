"""Snapshot-tier: unidirectional read-snapshot replacing A/B rotation.

Locks in the daemon-side contract:
  * `_snapshot_catalog()` produces `catalog.read.duckdb` from the writer's
    current catalog (file-copy after CHECKPOINT), atomic via tmp + rename.
  * The `read_only.duckdb` symlink swings to point at the snapshot file
    rather than a slot file once the snapshot exists.
  * Debounce coalesces burst calls; `force=True` bypasses it.
  * `_request_snapshot()` is the lock-safe handoff write-op handlers use;
    it only sets a flag + Event, never touches DuckDB itself.
  * SQLite backend skips silently — SQLite WAL already gives readers
    lock-free concurrency.
  * `_op_snapshot` is registered in OPS and CLI_OPS.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from refmatrix.daemon import Daemon
from refmatrix.store import Store


def _bare_daemon(root: Path, store: Store) -> Daemon:
    """Build a Daemon shell wired up with just enough state for the
    snapshot helpers — no socket, no thread pool. Mirrors the harness
    in test_daemon_replica_symlink.py."""
    d = object.__new__(Daemon)
    d.root = root
    d._log = lambda *a, **k: None
    d.store = store
    d._store_lock = threading.Lock()
    d._snapshot_lock = threading.Lock()
    d._last_snapshot_ts = 0.0
    d._snapshot_dirty = False
    d._snapshot_event = threading.Event()
    d._snapshot_stop = threading.Event()
    return d


def _duck_store(root: Path) -> Store:
    """Initialize a DuckDB-backed Store the daemon can CHECKPOINT + copy."""
    s = Store(root, backend="duckdb")
    s._connect()
    return s


# ---- _snapshot_catalog -----------------------------------------------------


def test_snapshot_catalog_writes_read_file_and_swings_symlink(tmp_path):
    s = _duck_store(tmp_path)
    try:
        d = _bare_daemon(tmp_path, s)
        result = d._snapshot_catalog(force=True)
        snap = tmp_path / "catalog.read.duckdb"
        link = tmp_path / "read_only.duckdb"
        assert snap.exists(), result
        assert link.is_symlink()
        assert os.readlink(link) == "catalog.read.duckdb"
        assert result["snapshot_path"] == str(snap)
        assert result["size"] > 0
    finally:
        s.close()


def test_snapshot_catalog_is_atomic_via_tmp(tmp_path):
    """The tmp file used for the atomic rename must not survive past a
    successful snapshot — leaving it on disk would mean the rename never
    fired and readers could pick up a half-written file."""
    s = _duck_store(tmp_path)
    try:
        d = _bare_daemon(tmp_path, s)
        d._snapshot_catalog(force=True)
        tmp_file = tmp_path / "catalog.read.duckdb.tmp"
        assert not tmp_file.exists()
    finally:
        s.close()


def test_snapshot_catalog_debounced_by_default(tmp_path, monkeypatch):
    """Two rapid calls without `force` produce one snapshot. The second
    short-circuits with `skipped=debounced` so burst writes don't pay
    N file-copies."""
    monkeypatch.setenv("RMX_SNAPSHOT_DEBOUNCE_MS", "10000")
    s = _duck_store(tmp_path)
    try:
        d = _bare_daemon(tmp_path, s)
        first = d._snapshot_catalog()
        second = d._snapshot_catalog()
        assert "snapshot_path" in first, first
        assert second.get("skipped") == "debounced", second
    finally:
        s.close()


def test_snapshot_catalog_force_bypasses_debounce(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_SNAPSHOT_DEBOUNCE_MS", "10000")
    s = _duck_store(tmp_path)
    try:
        d = _bare_daemon(tmp_path, s)
        d._snapshot_catalog(force=True)
        second = d._snapshot_catalog(force=True)
        assert "snapshot_path" in second, second
    finally:
        s.close()


def test_snapshot_catalog_skips_sqlite_backend(tmp_path):
    """SQLite already has many-readers-one-writer concurrency via WAL.
    Snapshot-tier is a no-op there — return a skip marker instead of
    burning a copy."""
    s = Store(tmp_path, backend="sqlite")
    s._connect()
    try:
        d = _bare_daemon(tmp_path, s)
        out = d._snapshot_catalog(force=True)
        assert out.get("skipped") == "non-duckdb", out
        assert not (tmp_path / "catalog.read.duckdb").exists()
    finally:
        s.close()


# ---- _request_snapshot -----------------------------------------------------


def test_request_snapshot_sets_dirty_and_signals_event(tmp_path):
    """Lock-safe handoff used by write-op handlers. Must not touch the
    catalog; just flip a flag and wake the tick thread."""
    s = _duck_store(tmp_path)
    try:
        d = _bare_daemon(tmp_path, s)
        d._snapshot_event.clear()
        d._snapshot_dirty = False
        d._request_snapshot()
        assert d._snapshot_dirty
        assert d._snapshot_event.is_set()
    finally:
        s.close()


# ---- _refresh_read_only_link prefers snapshot ------------------------------


def test_refresh_read_only_link_prefers_snapshot_when_present(tmp_path):
    """Once the snapshot file exists, `_refresh_read_only_link()` (the
    function rotation calls on every swap) must target it rather than a
    slot file. Otherwise rotation would clobber the snapshot policy by
    repointing readers at a slot the writer can later attach to."""
    s = _duck_store(tmp_path)
    try:
        d = _bare_daemon(tmp_path, s)
        # Seed rotation files so the fallback target exists.
        (tmp_path / "catalog.A.duckdb").write_text("")
        (tmp_path / "catalog.B.duckdb").write_text("")
        (tmp_path / "active").write_text("A")
        d._active_slot = "A"
        # No snapshot yet → falls back to rotation reader slot.
        d._refresh_read_only_link()
        assert os.readlink(tmp_path / "read_only.duckdb") == "catalog.B.duckdb"
        # Materialize snapshot, refresh again — now points at the snapshot.
        d._snapshot_catalog(force=True)
        d._refresh_read_only_link()
        assert (
            os.readlink(tmp_path / "read_only.duckdb")
            == "catalog.read.duckdb"
        )
    finally:
        s.close()


# ---- OPS registration ------------------------------------------------------


def test_op_snapshot_registered_in_ops_and_cli_ops():
    """`rmx` callers route `snapshot` through the daemon socket; both
    OPS (the dispatcher) and CLI_OPS (the latency-sensitive cli pool)
    must list it."""
    from refmatrix.daemon import OPS, CLI_OPS
    assert "snapshot" in OPS
    assert "snapshot" in CLI_OPS


# ---- reader-during-write ---------------------------------------------------


def test_reader_during_write_lands_on_snapshot(tmp_path):
    """A Store(read_only=True) opened after a snapshot was taken lands
    on `catalog.read.duckdb` (via the daemon-maintained symlink), not
    the primary writer file. That's the whole point of snapshot-tier —
    the writer never has to surrender its file lock to give readers a
    consistent view."""
    s = _duck_store(tmp_path)
    try:
        d = _bare_daemon(tmp_path, s)
        d._snapshot_catalog(force=True)
        reader = Store(tmp_path, read_only=True)
        try:
            assert reader.db_path == tmp_path / "read_only.duckdb"
        finally:
            reader.close()
    finally:
        s.close()


# ---- snapshot tick ---------------------------------------------------------


def test_snapshot_tick_coalesces_burst_writes(tmp_path, monkeypatch):
    """When the tick is running, N `_request_snapshot()` calls in a
    tight loop produce ONE snapshot — the second-and-later requests fire
    during the debounce sleep and ride out the same tick. Concrete test:
    after a burst, the last-snapshot timestamp moves forward exactly
    once and the snapshot file exists."""
    monkeypatch.setenv("RMX_SNAPSHOT_DEBOUNCE_MS", "50")
    s = _duck_store(tmp_path)
    try:
        d = _bare_daemon(tmp_path, s)
        d._start_snapshot_tick()
        try:
            for _ in range(20):
                d._request_snapshot()
            # Allow the debounce window plus a small slack.
            time.sleep(0.3)
        finally:
            d._snapshot_stop.set()
            d._snapshot_event.set()
            if d._snapshot_thread is not None:
                d._snapshot_thread.join(timeout=2.0)
        assert (tmp_path / "catalog.read.duckdb").exists()
        # Dirty flag drained after the snapshot ran.
        assert d._snapshot_dirty is False
    finally:
        s.close()
