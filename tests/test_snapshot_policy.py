"""Snapshot-tier + CLI policy fix.

Locks in the contract that `Store(read_only=True)` prefers the
daemon-maintained `read_only.duckdb` symlink (the lock-free reader
slot) over the primary catalog file. Also verifies the new daemon ops
that let CLI write commands (`partition add` / `partition rename`)
route through the daemon instead of grabbing the catalog lock from a
second process.

The corresponding bug class: `Could not set lock on catalog.B.duckdb`
when the CLI opens the same DuckDB file the daemon already holds. Fix
strategy: reads go via `_read_store()` (symlink-backed Store(
read_only=True)); writes go via daemon RPC when daemon is up.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from refmatrix.store import Store


def _make_duck_root(tmp_path: Path) -> Path:
    """Initialize a minimal .refmatrix root with a DuckDB catalog so
    Store(read_only=True) has something to open. Uses the same Store
    constructor path the daemon does."""
    s = Store(tmp_path, backend="duckdb")
    s._connect()
    s.close()
    return tmp_path


def test_read_only_store_prefers_read_only_symlink_when_present(tmp_path, monkeypatch):
    """The point of the snapshot-tier policy: with the daemon-maintained
    `read_only.duckdb` symlink present, Store(read_only=True) opens that
    file, not the primary catalog. This is what gives CLI reads a
    lock-free path while the daemon owns the writer."""
    monkeypatch.setenv("RMX_BACKEND", "duckdb")
    root = _make_duck_root(tmp_path)
    # Create a real second catalog file and symlink to it. We just need
    # Store to pick the symlink path — its contents don't have to be a
    # valid DuckDB file for this assertion (we don't _connect() here).
    alt = root / "catalog.alt.duckdb"
    alt.write_text("")
    link = root / "read_only.duckdb"
    os.symlink("catalog.alt.duckdb", link)

    s = Store(root, read_only=True)
    try:
        assert s.db_path == link
    finally:
        s.close()


def test_read_only_store_falls_back_to_primary_when_no_symlink(tmp_path, monkeypatch):
    """Without the symlink (daemon down, fresh install, sqlite backend),
    Store(read_only=True) opens the primary catalog file. The symlink
    optimization is purely additive."""
    monkeypatch.setenv("RMX_BACKEND", "duckdb")
    root = _make_duck_root(tmp_path)
    primary = root / "catalog.duckdb"

    s = Store(root, read_only=True)
    try:
        assert s.db_path == primary
        assert not (root / "read_only.duckdb").exists()
    finally:
        s.close()


def test_read_only_symlink_only_applies_to_duckdb_backend(tmp_path, monkeypatch):
    """SQLite-backed stores skip the symlink lookup entirely — the path
    is DuckDB-specific (DuckDB is what has the exclusive-file-lock
    problem; SQLite WAL doesn't)."""
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    s_setup = Store(tmp_path, backend="sqlite")
    s_setup._connect()
    s_setup.close()
    # Even with a stray symlink present, sqlite Store ignores it.
    (tmp_path / "catalog.alt.duckdb").write_text("")
    os.symlink("catalog.alt.duckdb", tmp_path / "read_only.duckdb")

    s = Store(tmp_path, read_only=True, backend="sqlite")
    try:
        assert s.db_path.name == "catalog.db"
    finally:
        s.close()


def test_daemon_partition_add_op_registered():
    """The CLI policy fix requires `partition_add` to exist on the daemon
    so `rmx partition add` can RPC instead of opening the catalog."""
    from refmatrix.daemon import OPS, CLI_OPS
    assert "partition_add" in OPS
    assert "partition_add" in CLI_OPS


def test_daemon_partition_rename_op_registered():
    """Same as partition_add — `partition rename` must route through the
    daemon when one is up."""
    from refmatrix.daemon import OPS, CLI_OPS
    assert "partition_rename" in OPS
    assert "partition_rename" in CLI_OPS


def test_daemon_partition_list_op_registered():
    """Regression guard for the partition_list daemon-routing fix that
    landed alongside the wider policy."""
    from refmatrix.daemon import OPS, CLI_OPS
    assert "partition_list" in OPS
    assert "partition_list" in CLI_OPS
