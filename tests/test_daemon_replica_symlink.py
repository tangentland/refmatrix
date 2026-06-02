"""Reader-symlink drift invariant for the two-file rotation.

Regression guard for the bug where `read_only.duckdb` pointed at the
slot the daemon was actively writing (lock-held), making every
out-of-process `--via-replica` read fail with a DuckDB lock conflict.

The fix: the reader slot is derived from the slot the store is ACTUALLY
open on (`store.db_path`), never from the on-disk `active` marker, which
can drift if a swap reopens the store but fails to persist the marker.

These build a bare Daemon via `object.__new__` and exercise the pure
slot/symlink helpers — no socket, no model load.
"""
import os
from pathlib import Path

from refmatrix.daemon import Daemon


class _StubStore:
    def __init__(self, db_path):
        self.db_path = db_path


def _daemon(root: Path, *, writer_slot, marker):
    (root / "catalog.A.duckdb").write_text("")
    (root / "catalog.B.duckdb").write_text("")
    (root / "active").write_text(marker)
    d = object.__new__(Daemon)
    d.root = root
    d._log = lambda *a, **k: None
    if writer_slot in ("A", "B"):
        d.store = _StubStore(root / f"catalog.{writer_slot}.duckdb")
    else:  # legacy file — not a rotation slot
        d.store = _StubStore(root / "catalog.duckdb")
    return d


def test_writer_slot_from_store_reads_db_path(tmp_path):
    d = _daemon(tmp_path, writer_slot="A", marker="B")
    assert d._writer_slot_from_store() == "A"


def test_legacy_db_path_has_no_slot(tmp_path):
    d = _daemon(tmp_path, writer_slot="legacy", marker="A")
    assert d._writer_slot_from_store() is None


def test_reader_slot_trusts_store_over_drifted_marker(tmp_path):
    # marker LIES (B) but the store really writes A → reader must be B.
    d = _daemon(tmp_path, writer_slot="A", marker="B")
    assert d._reader_slot() == "B"


def test_reader_slot_falls_back_to_marker_when_legacy(tmp_path):
    # No rotation slot open → trust the marker: writer A → reader B.
    d = _daemon(tmp_path, writer_slot="legacy", marker="A")
    assert d._reader_slot() == "B"


def test_symlink_never_points_at_writer_despite_drift(tmp_path):
    # The exact production failure: writer=A, marker drifted to B.
    d = _daemon(tmp_path, writer_slot="A", marker="B")
    d._refresh_read_only_link()
    target = os.readlink(tmp_path / "read_only.duckdb")
    assert target == "catalog.B.duckdb"          # reader = non-writer
    # And the symlink resolves to a file that is NOT the writer.
    assert Path(target).name != d.store.db_path.name


def test_symlink_atomic_replace_over_existing(tmp_path):
    d = _daemon(tmp_path, writer_slot="B", marker="B")
    # Pre-existing (stale) link pointing at the writer.
    link = tmp_path / "read_only.duckdb"
    os.symlink("catalog.B.duckdb", link)
    d._refresh_read_only_link()
    assert os.readlink(link) == "catalog.A.duckdb"  # now the reader
