"""bug-113: `rmx replica merge --dry-run` failed on the live fleet and left the
writer closed and unlocked.

Three defects (ch-bsd bug-110 r1 #s-1):
  1. schema lag — the merge target was built by `duckdb_catalog.init_catalog`,
     which lacked `entities.vectors_partition` (the Store ALTERed it in on
     open), so `INSERT INTO entities SELECT ae.*` from a Store-built slot hit
     "table entities has 13 columns but 14 values were supplied";
  2. `_op_replica_merge` never passed `dry_run` to `merge_slots`, so a dry run
     built the whole merge on disk;
  3. on the error, `merge_slots` left its connection (with the slots ATTACHed)
     open, the op's writer reopen failed "Unique file handle conflict", and the
     op returned with the writer closed — another process could then open the
     live slot.

Slots here are built the way production builds them: through `Store`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("RMX_HOME", str(home / ".refmatrix"))


def _cols(con, table: str) -> "list[str]":
    return [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? AND table_catalog = current_database() "
        "AND table_schema = 'main' ORDER BY ordinal_position", [table]).fetchall()]


def _tables(con) -> "list[str]":
    return sorted(r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog = current_database() AND table_schema = 'main'").fetchall())


def _store_catalog(tmp_path: Path, name: str = "s") -> Path:
    from refmatrix.store import Store
    root = tmp_path / name / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root, partition="proj", backend="duckdb")
    s.init()
    s._connect()
    s.close()
    return root / "catalog.duckdb"


# ---- 1. one schema --------------------------------------------------------

def test_init_catalog_builds_exactly_the_store_schema(tmp_path):
    """Every schema-building site (merge target, sqlite->duckdb migration,
    the Store itself) comes out of `duckdb_catalog.init_catalog`; it must
    equal what a Store opens — the lag that broke the merge."""
    from refmatrix.duckdb_catalog import init_catalog
    store_db = _store_catalog(tmp_path)
    s = duckdb.connect(str(store_db), read_only=True)
    m = duckdb.connect(":memory:")
    init_catalog(m)
    try:
        assert _tables(m) == _tables(s)
        for t in _tables(s):
            assert _cols(m, t) == _cols(s, t), t
    finally:
        s.close()
        m.close()


# ---- 2. merge_slots on Store-built slots ----------------------------------

def _seed(path: Path, rows: "list[tuple]") -> None:
    con = duckdb.connect(str(path))
    for eid, name, upd, vp in rows:
        con.execute(
            "INSERT INTO entities(id, partition_id, kind, name, created_at, updated_at, "
            "vectors_updated_at, vectors_partition) VALUES (?, 1, 'doc', ?, 1.0, ?, ?, ?)",
            [eid, name, upd, upd, vp])
    con.close()


def _slots(tmp_path: Path) -> "tuple[Path, Path]":
    base = _store_catalog(tmp_path, "base")
    a, b = tmp_path / "catalog.A.duckdb", tmp_path / "catalog.B.duckdb"
    shutil.copyfile(base, a)
    shutil.copyfile(base, b)
    _seed(a, [(100, "shared.md", 5.0, "pa"), (101, "a-only.md", 5.0, "pa")])
    _seed(b, [(100, "shared.md", 9.0, "pb"), (102, "b-only.md", 5.0, "pb")])
    return a, b


@pytest.mark.parametrize("dry_run", [True, False])
def test_merge_slots_merges_store_built_slots(tmp_path, dry_run):
    from refmatrix.replica_merge import merge_slots
    a, b = _slots(tmp_path)
    out = tmp_path / "merged.duckdb"
    report = merge_slots(a, b, out, dry_run=dry_run)
    assert report["merged_counts"]["entities"] == 3
    assert out.exists() is (not dry_run)
    if not dry_run:
        con = duckdb.connect(str(out), read_only=True)
        try:
            vp = dict(con.execute(
                "SELECT name, vectors_partition FROM entities").fetchall())
        finally:
            con.close()
        # B's newer shared row carries its vectors_partition through the
        # newer-wins UPDATE (the hand-listed SET clause dropped it)
        assert vp == {"shared.md": "pb", "a-only.md": "pa", "b-only.md": "pb"}


# Two failure points: the source probe (a table B lacks) and the build on the
# target (a column B has that the Store schema does not — BY NAME refuses it).
_BREAK_B = {
    "probe": "DROP TABLE saved_queries",
    "build": "ALTER TABLE entities ADD COLUMN not_in_the_store_schema INTEGER",
}


def _break(path: Path, where: str) -> None:
    con = duckdb.connect(str(path))
    con.execute(_BREAK_B[where])
    con.close()


@pytest.mark.parametrize("where", sorted(_BREAK_B))
def test_a_failed_merge_closes_every_connection(tmp_path, where):
    from refmatrix.replica_merge import merge_slots
    a, b = _slots(tmp_path)
    _break(b, where)                               # B cannot be merged
    target = tmp_path / "merged.duckdb"
    with pytest.raises(duckdb.Error) as ei:
        merge_slots(a, b, target)
    assert not target.exists(), "a half-built merge target was left behind"
    # `ei` keeps the traceback (and merge_slots' frame) alive, as the
    # daemon's `except ... as exc` does while it reopens the writer. Nothing
    # may still hold slot A: a leftover ATTACH makes this writer open fail
    # "Unique file handle conflict" (measured, m113.log).
    w = duckdb.connect(str(a))
    w.close()
    assert ei.value is not None


# ---- 3. the daemon op -----------------------------------------------------

def _daemon(tmp_path: Path):
    from refmatrix import daemon as dm
    from refmatrix.store import Store
    root = Path(__import__("tempfile").mkdtemp(prefix="rmx", dir="/tmp")) / ".refmatrix"
    root.mkdir()
    a, b = _slots(tmp_path)
    shutil.copyfile(a, root / "catalog.A.duckdb")
    shutil.copyfile(b, root / "catalog.B.duckdb")
    (root / "active").write_text("A")
    d = dm.Daemon(root, partition="proj")
    d._log = lambda msg: None
    d.store = Store(root, partition="proj")
    assert d.store.db_path.name == "catalog.A.duckdb"
    d.store.init()
    d.store._connect()
    return d, root


def _child_can_open(path: Path) -> "tuple[bool, str]":
    r = subprocess.run(
        [sys.executable, "-c",
         "import duckdb,sys;duckdb.connect(sys.argv[1],read_only=True).execute('SELECT 1')",
         str(path)], capture_output=True, text=True, timeout=60)
    return r.returncode == 0, r.stderr.strip().splitlines()[-1:] and r.stderr.strip().splitlines()[-1] or ""


def _assert_writer_open_and_locked(d, root: Path) -> None:
    assert d.store is not None and d.store._conn is not None, "writer left closed"
    assert d.store.db_path.name == "catalog.A.duckdb"
    assert d.store._connect().execute("SELECT count(*) FROM entities").fetchone()[0] >= 2
    ok, err = _child_can_open(root / "catalog.A.duckdb")
    assert not ok, "another process opened the live writer slot: the lock is gone"
    assert "lock" in err.lower(), err


def test_op_dry_run_succeeds_builds_nothing_and_keeps_the_writer(tmp_path):
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path)
    try:
        r = dm._op_replica_merge(d, {"dry_run": True})
        assert r.get("ok") is True, r
        assert r["dry_run"] is True
        assert r["target_size_bytes"] is None, "dry run built the merge on disk"
        assert not (root / "catalog.merge.tmp.duckdb").exists()
        _assert_writer_open_and_locked(d, root)
    finally:
        d.store.close()


@pytest.mark.parametrize("where", sorted(_BREAK_B))
def test_op_failed_merge_leaves_the_writer_reopened_and_locked(tmp_path, where):
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path)
    _break(root / "catalog.B.duckdb", where)
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is False, r
        assert "merge build" in r["error"], r
        assert not (root / "catalog.merge.tmp.duckdb").exists()
        _assert_writer_open_and_locked(d, root)
    finally:
        d.store.close()


def test_op_whose_writer_cannot_reopen_hands_off_to_writer_lost(tmp_path, monkeypatch):
    """The last line of defence: if the reopen itself fails, the op does not
    return as if all were well with an unlocked slot — it says so and calls
    `_writer_lost` (exit for the supervisor's respawn). The Store the reopen
    builds is replaced by one whose init raises (a collaborator; the op and
    `_reopen_writer_after_merge` run unpatched)."""
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path)
    lost = []
    d._writer_lost = lambda where, exc: lost.append((where, repr(exc)))

    class _NoOpenStore(dm.Store):
        def init(self):
            raise OSError("simulated: slot cannot be opened")

    monkeypatch.setattr(dm, "Store", _NoOpenStore)
    r = dm._op_replica_merge(d, {"dry_run": True})
    assert r.get("ok") is False, r
    assert "FAILED" in r["error"] and "respawn" in r["error"], r
    assert lost and "slot A" in lost[0][0], lost


def test_op_real_merge_installs_on_both_slots_and_keeps_the_writer(tmp_path):
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path)
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is True, r
        assert r["merged_counts"]["entities"] == 3
        _assert_writer_open_and_locked(d, root)
        names = {row[0] for row in d.store._connect().execute(
            "SELECT name FROM entities").fetchall()}
        assert {"shared.md", "a-only.md", "b-only.md"} <= names
    finally:
        d.store.close()
