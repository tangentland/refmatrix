"""Tests for `_store()` / `_active_slot_path()` rotation awareness.

Post-0.3.8 the daemon writes to `catalog.A.duckdb` or `catalog.B.duckdb`
per the `active` marker. The legacy `catalog.duckdb` file is frozen at
bootstrap. CLI's `_store()` must open the active slot (source of truth)
rather than the stale legacy file."""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix.cli import _active_slot_path, _store


def _seed_root_with_marker(tmp_path: Path, slot: str = "A") -> Path:
    """Create a fake refmatrix root with rotation slot files + marker."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    (root / f"catalog.{slot}.duckdb").write_bytes(b"")
    other = "B" if slot == "A" else "A"
    (root / f"catalog.{other}.duckdb").write_bytes(b"")
    (root / "catalog.duckdb").write_bytes(b"")  # legacy
    (root / "active").write_text(slot)
    return root


def test_active_slot_path_resolves_to_marker_slot(tmp_path, monkeypatch):
    root = _seed_root_with_marker(tmp_path, slot="B")
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    assert _active_slot_path() == root / "catalog.B.duckdb"


def test_active_slot_path_none_when_no_marker(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    (root / "catalog.duckdb").write_bytes(b"")
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    assert _active_slot_path() is None


def test_active_slot_path_none_when_marker_invalid(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    (root / "catalog.A.duckdb").write_bytes(b"")
    (root / "active").write_text("garbage")
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    assert _active_slot_path() is None


def test_active_slot_path_none_when_slot_file_missing(tmp_path, monkeypatch):
    """Marker says A but file doesn't exist (mid-rotation, broken state)."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    (root / "active").write_text("A")
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    assert _active_slot_path() is None


def test_store_opens_active_slot_when_marker_present(tmp_path, monkeypatch):
    """_store() should bind to catalog.<active>.duckdb, not the legacy
    catalog.duckdb file."""
    root = _seed_root_with_marker(tmp_path, slot="A")
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    s = _store()
    assert s.db_path == root / "catalog.A.duckdb"
    s.close()


def test_store_falls_back_to_legacy_when_no_marker(tmp_path, monkeypatch):
    """Pre-rotation stores have no `active` marker. _store() must still
    open `catalog.duckdb` for backwards compat."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    (root / "catalog.duckdb").write_bytes(b"")
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    s = _store()
    assert s.db_path == root / "catalog.duckdb"
    s.close()
