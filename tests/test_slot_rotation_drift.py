"""Every writer resolves the SAME catalog file — the root of slot-rotation drift.

A rotated store keeps its live catalog in `catalog.A.duckdb` / `catalog.B.duckdb`
with an `active` marker naming the writer. Only the daemon used to resolve that,
patching `db_path` after construction; every other caller kept writing into the
pre-rotation `catalog.duckdb`, where the daemon would never read it again.

That is the documented drift: "rows written outside the log are structurally
invisible to delta-apply", which is why `rmx replica refresh` reports
`applied=0` while the slots diverge. Observed live: `rmx memory forget <name>`
with the daemon stopped reported success, mutated the legacy file, and left the
active slot untouched.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


def _rotate(root, slot="A"):
    """Make `root` look like a rotated store with `slot` active."""
    (root / f"catalog.{slot}.duckdb").touch()
    (root / "active").write_text(slot)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / ".refmatrix"
    s = Store(r, backend="duckdb")
    s.init()
    s.close()
    return r


def test_writer_follows_the_active_marker(root):
    _rotate(root, "A")
    assert Store(root, backend="duckdb").db_path.name == "catalog.A.duckdb"
    _rotate(root, "B")
    assert Store(root, backend="duckdb").db_path.name == "catalog.B.duckdb"


def test_unrotated_store_stays_on_the_legacy_file(root):
    """No marker = a store that never rotated. It must not be moved."""
    assert Store(root, backend="duckdb").db_path.name == "catalog.duckdb"


def test_marker_naming_a_missing_slot_falls_back(root):
    """A half-finished bootstrap must not conjure an empty slot out from under
    the daemon."""
    (root / "active").write_text("A")
    assert Store(root, backend="duckdb").db_path.name == "catalog.duckdb"


def test_garbage_marker_falls_back(root):
    (root / "active").write_text("nonsense")
    assert Store(root, backend="duckdb").db_path.name == "catalog.duckdb"


def test_a_write_with_no_daemon_lands_in_the_active_slot(tmp_path):
    """The end-to-end property. Write through a plain Store on a rotated
    store, then read the slot file back directly: the row must be there."""
    root = tmp_path / ".refmatrix"
    s = Store(root, backend="duckdb"); s.init(); s.close()
    # Promote the initialised catalog into slot A, as bootstrap does.
    (root / "catalog.duckdb").rename(root / "catalog.A.duckdb")
    (root / "active").write_text("A")

    w = Store(root, backend="duckdb")
    w.init()
    assert w.db_path.name == "catalog.A.duckdb"
    eid = w.upsert_entity(kind="doc", name="written-without-a-daemon")
    w.close()

    import duckdb
    con = duckdb.connect(str(root / "catalog.A.duckdb"), read_only=True)
    got = con.execute("SELECT name FROM entities WHERE id=?", (eid,)).fetchone()
    assert got and got[0] == "written-without-a-daemon"
    # And nothing leaked into a resurrected legacy file.
    assert not (root / "catalog.duckdb").exists()


def test_dangling_read_only_symlink_is_not_bound(root):
    """`exists()` follows the link; `is_symlink()` alone accepted a dangling
    one, binding an empty database whose `partitions` table is missing. That
    surfaced as a TypeError from _ensure_partition and dropped the daemon into
    its legacy-catalog fallback."""
    (root / "read_only.duckdb").symlink_to(root / "catalog.read.duckdb")  # no target
    s = Store(root, backend="duckdb", read_only=True)
    assert s.db_path.name != "read_only.duckdb"
