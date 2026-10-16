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

def _daemon(tmp_path: Path, writer: str = "A"):
    from refmatrix import daemon as dm
    from refmatrix.store import Store
    root = Path(__import__("tempfile").mkdtemp(prefix="rmx", dir="/tmp")) / ".refmatrix"
    root.mkdir()
    a, b = _slots(tmp_path)
    shutil.copyfile(a, root / "catalog.A.duckdb")
    shutil.copyfile(b, root / "catalog.B.duckdb")
    (root / "active").write_text(writer)
    d = dm.Daemon(root, partition="proj")
    d._log = lambda msg: None
    d.store = Store(root, partition="proj")
    assert d.store.db_path.name == f"catalog.{writer}.duckdb"
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
    d._writer_lost = lambda reason: lost.append(reason)

    class _NoOpenStore(dm.Store):
        def init(self):
            raise OSError("simulated: slot cannot be opened")

    monkeypatch.setattr(dm, "Store", _NoOpenStore)
    r = dm._op_replica_merge(d, {"dry_run": True})
    assert r.get("ok") is False, r
    assert "FAILED" in r["error"] and "respawn" in r["error"], r
    assert lost and "slot A" in lost[0], lost


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


# ---- ch-bsd r1 b-1: the writer-lost exit is deterministic -----------------

_WL_CHILD = r'''
import sys, threading, time
from pathlib import Path
from refmatrix import daemon as dm
from refmatrix.store import Store
root = Path(sys.argv[1])
Store(root).init()
d = dm.Daemon(root)
def trig():
    for _ in range(600):
        if dm.ping(root):
            break
        time.sleep(0.05)
    try:
        d._writer_lost("test: simulated reopen failure")
    except TypeError:                      # the r1 shape: (where, exc)
        d._writer_lost("test: simulated reopen failure", RuntimeError("simulated"))
threading.Thread(target=trig, daemon=True).start()
d.serve_forever()
'''


@pytest.mark.parametrize("degrade_s", ["0.2", "8"])
def test_writer_lost_exits_2_from_a_real_serving_daemon(tmp_path, degrade_s):
    """ch-bsd r1 b-1: `_writer_lost` set `_stop` and slept before os._exit(2);
    the serve loop's graceful shutdown ends in os._exit(0) and won whenever it
    finished first (RMX_DEGRADE_EXIT_S=8: exit 0). launchd's KeepAlive
    {SuccessfulExit=0} does not respawn a 0 exit, so the daemon stayed down.
    The real `serve_forever` runs in a child; its exit status must be 2."""
    import os
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="rmx", dir="/tmp")) / ".refmatrix"
    root.mkdir()
    home = Path(tempfile.mkdtemp(prefix="rmxh", dir="/tmp"))
    env = dict(os.environ, HOME=str(home), RMX_HOME=str(home / ".refmatrix"),
               RMX_DEGRADE_EXIT_S=degrade_s, HF_HUB_OFFLINE="1",
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    r = subprocess.run([sys.executable, "-c", _WL_CHILD, str(root)], env=env,
                       capture_output=True, text=True, timeout=120)
    log = (root / "rmxd.log").read_text() if (root / "rmxd.log").exists() else ""
    assert r.returncode == 2, (r.returncode, log[-2000:], r.stderr[-2000:])
    assert "writer-lost" in log, log[-2000:]


# ---- ch-bsd r1 b-2: the swap-failure exit reopens the writer ---------------

@pytest.mark.parametrize("writer", ["A", "B"])
@pytest.mark.parametrize("fail_at", ["replace", "copy2"])
def test_op_swap_failure_leaves_the_writer_reopened_and_locked(tmp_path, monkeypatch, fail_at,
                                                                 writer):
    """The swap installs the merge on A (os.replace), then copies A to B
    (shutil.copy2). Either failing returned `swap: …` with the writer still
    force-closed. Fault injection on the two filesystem calls only."""
    import os
    import shutil as _sh
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path, writer)
    if fail_at == "replace":
        real = os.replace

        def bad_replace(src, dst, *a, **k):
            if str(dst).endswith("catalog.A.duckdb"):
                raise OSError(28, "No space left on device (injected)")
            return real(src, dst, *a, **k)
        monkeypatch.setattr(dm.os, "replace", bad_replace)
    else:
        def bad_copy2(src, dst, *a, **k):
            raise OSError(28, "No space left on device (injected)")
        monkeypatch.setattr(_sh, "copy2", bad_copy2)
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is False, r
        assert "swap" in r["error"], r
        monkeypatch.undo()
        # A holds the merge once os.replace ran (copy2 failed): the writer is
        # A and the partial B is gone for the rotation repair to re-clone.
        # If the replace itself failed nothing moved: the writer is the old one.
        expect = "A" if fail_at == "copy2" else writer
        assert d.store is not None and d.store._conn is not None, "writer left closed"
        assert d.store.db_path.name == f"catalog.{expect}.duckdb"
        assert (root / "active").read_text().strip() == expect
        ok, err = _child_can_open(root / f"catalog.{expect}.duckdb")
        assert not ok and "lock" in err.lower(), err
        if fail_at == "copy2":
            assert (root / "catalog.B.duckdb").exists(), "partial B not re-cloned (m-r2-5)"
        else:
            assert not (root / "catalog.merge.tmp.duckdb").exists()
    finally:
        d.store.close()


# ---- ch-bsd r1 b-3: a stale source slot lacks the newest column ------------

def _drop_newest_column(path: Path) -> None:
    """Make a slot as old as the 2026-06-20 global B: no `vectors_partition`.
    DuckDB refuses DROP COLUMN while indexes depend on the table, so the
    indexes are dropped and recreated around it."""
    con = duckdb.connect(str(path))
    idx = con.execute("SELECT index_name, sql FROM duckdb_indexes() "
                      "WHERE table_name = 'entities' AND sql IS NOT NULL").fetchall()
    for name, _ in idx:
        con.execute(f'DROP INDEX "{name}"')
    con.execute("ALTER TABLE entities DROP COLUMN vectors_partition")
    for _, sql in idx:
        con.execute(sql)
    con.close()


@pytest.mark.parametrize("stale", ["a", "b"])
@pytest.mark.parametrize("dry_run", [True, False])
def test_merge_slots_merges_a_slot_older_than_the_schema(tmp_path, stale, dry_run):
    """The global store's live shape: writer A current, B from 2026-06-20
    without `entities.vectors_partition`. `SET vectors_partition =
    be.vectors_partition` failed 'Table "be" does not have a column named
    "vectors_partition"'. A column the winning source lacks is set NULL."""
    from refmatrix.replica_merge import merge_slots
    a, b = _slots(tmp_path)
    _drop_newest_column(a if stale == "a" else b)
    out = tmp_path / "merged.duckdb"
    report = merge_slots(a, b, out, dry_run=dry_run)
    assert report["merged_counts"]["entities"] == 3
    if not dry_run:
        con = duckdb.connect(str(out), read_only=True)
        try:
            vp = dict(con.execute("SELECT name, vectors_partition FROM entities").fetchall())
        finally:
            con.close()
        # the newer B row wins; a stale side contributes NULL, never a crash
        assert vp["shared.md"] == (None if stale == "b" else "pb")


def test_memory_content_set_list_is_target_and_source_columns(tmp_path):
    from refmatrix.replica_merge import merge_slots
    a, b = _slots(tmp_path)
    for path, upd in ((a, 5.0), (b, 9.0)):
        con = duckdb.connect(str(path))
        con.execute("INSERT INTO memory_content(entity_id, content, mtype, created_at, updated_at) "
                    "VALUES (100, ?, 'observation', 1.0, ?)", [f"c{upd}", upd])
        con.close()
    con = duckdb.connect(str(b))
    con.execute("ALTER TABLE memory_content DROP COLUMN tags")
    con.close()
    out = tmp_path / "merged.duckdb"
    merge_slots(a, b, out)
    con = duckdb.connect(str(out), read_only=True)
    try:
        assert con.execute("SELECT content FROM memory_content WHERE entity_id=100").fetchone()[0] == "c9.0"
    finally:
        con.close()


# ---- ch-bsd r1 s-3 / bug-128: linkage_types collide by name ----------------

def _relink(path: Path, renames: "dict[str, int]", links: "list[tuple]") -> None:
    """Move named linkage rows to new ids (as two slots that seeded or added
    linkages in a different order do), then add entity_links/evidence."""
    con = duckdb.connect(str(path))
    for name, new_id in renames.items():
        row = con.execute("SELECT id, directed, inverse_of, description FROM linkage_types "
                          "WHERE name = ?", [name]).fetchone()
        if row is None:
            con.execute("INSERT INTO linkage_types(id, name, directed) VALUES (?, ?, 1)",
                        [new_id, name])
        else:
            con.execute("DELETE FROM linkage_types WHERE name = ?", [name])
            con.execute("INSERT INTO linkage_types(id, name, directed, inverse_of, description) "
                        "VALUES (?, ?, ?, ?, ?)", [new_id, name, row[1], row[2], row[3]])
    for eid, lk_name, cid in links:
        lid = con.execute("SELECT id FROM linkage_types WHERE name=?", [lk_name]).fetchone()[0]
        con.execute("INSERT INTO entity_links VALUES (?, ?, ?, 1.0)", [eid, lid, cid])
        con.execute("INSERT INTO linkage_evidence(entity_id, linkage_id, concept_id, file, line) "
                    "VALUES (?, ?, ?, 'f.md', 1)", [eid, lid, cid])
    con.close()


def test_merge_remaps_linkage_ids_that_collide_by_name(tmp_path):
    """bug-128: refmatrix's own snapshot vs its stale slot A failed `Duplicate
    key "name: part-of"` — one linkage name, different ids per slot. The merge
    keys linkage_types by NAME and remaps B's linkage_id in every referencing
    table, so every link keeps the linkage it named."""
    from refmatrix.replica_merge import merge_slots
    a, b = _slots(tmp_path)
    _relink(a, {"alpha-lk": 900, "beta-lk": 901, "part-of": 950}, [(100, "alpha-lk", 101), (101, "part-of", 100)])
    _relink(b, {"beta-lk": 900, "gamma-lk": 901, "part-of": 902},
            [(100, "beta-lk", 102), (102, "gamma-lk", 100), (102, "part-of", 100)])
    out = tmp_path / "merged.duckdb"
    merge_slots(a, b, out)
    con = duckdb.connect(str(out), read_only=True)
    try:
        names = [r[0] for r in con.execute("SELECT name FROM linkage_types").fetchall()]
        assert len(names) == len(set(names))
        links = set(con.execute(
            "SELECT el.entity_id, lt.name, el.concept_id FROM entity_links el "
            "JOIN linkage_types lt ON lt.id = el.linkage_id").fetchall())
        assert {(100, "alpha-lk", 101), (101, "part-of", 100), (100, "beta-lk", 102),
                (102, "gamma-lk", 100), (102, "part-of", 100)} <= links, links
        ev = set(con.execute(
            "SELECT le.entity_id, lt.name, le.concept_id FROM linkage_evidence le "
            "JOIN linkage_types lt ON lt.id = le.linkage_id").fetchall())
        assert (102, "gamma-lk", 100) in ev and (100, "beta-lk", 102) in ev, ev
        orphans = con.execute("SELECT count(*) FROM entity_links el LEFT JOIN linkage_types lt "
                              "ON lt.id = el.linkage_id WHERE lt.id IS NULL").fetchone()[0]
        assert orphans == 0
    finally:
        con.close()


def test_merge_refuses_partitions_that_collide_by_name_with_a_named_diagnosis(tmp_path):
    """The sibling shape (partitions.name is UNIQUE too). Partition ids reach
    every table, so the merge refuses with a diagnosis naming the partition —
    before anything is written — rather than a bare constraint error."""
    from refmatrix.replica_merge import merge_slots
    a, b = _slots(tmp_path)
    con = duckdb.connect(str(b))
    con.execute("INSERT INTO partitions(id, name, kind, created_at) VALUES (77, 'collide', 'repo', 1.0)")
    con.close()
    con = duckdb.connect(str(a))
    con.execute("INSERT INTO partitions(id, name, kind, created_at) VALUES (78, 'collide', 'repo', 1.0)")
    con.close()
    out = tmp_path / "merged.duckdb"
    with pytest.raises(Exception) as ei:
        merge_slots(a, b, out)
    assert type(ei.value).__name__ == "MergeRefused", repr(ei.value)
    assert "collide" in str(ei.value)
    assert not out.exists()


# ---- ch-bsd r2 m-r2-1: audit reports a partition clash as drift ------------

def test_audit_reports_partition_collisions_as_drift(tmp_path):
    """`audit_slots` is the read-only drift detector; r1 made it raise
    MergeRefused on the worst drift it can meet. It reports the clash."""
    from refmatrix.replica_merge import audit_slots
    a, b = _slots(tmp_path)
    for path, pid in ((a, 78), (b, 77)):
        con = duckdb.connect(str(path))
        con.execute("INSERT INTO partitions(id, name, kind, created_at) VALUES (?, 'collide', 'repo', 1.0)", [pid])
        con.close()
    rep = audit_slots(a, b)
    assert rep["drift_detected"] is True
    assert rep.get("partition_collisions") and "collide" in " ".join(rep["partition_collisions"]), rep


# ---- ch-bsd r2 m-r2-4 R2: inverse_of keeps its NAME through the remap ------

def test_b_only_linkage_inverse_points_at_the_same_name_after_the_merge(tmp_path):
    """The inv.py shape: B's `has-part` (B-only) has inverse_of = B's
    `part-of` = 900, but in A id 900 is `alpha-lk` and `part-of` is 950. The
    merged `has-part` must point at `part-of`, not at whatever holds 900."""
    from refmatrix.replica_merge import merge_slots
    a, b = _slots(tmp_path)
    _relink(a, {"alpha-lk": 900, "part-of": 950}, [(100, "alpha-lk", 101)])
    _relink(b, {"part-of": 900, "has-part": 901}, [(102, "has-part", 100)])
    con = duckdb.connect(str(b))
    con.execute("UPDATE linkage_types SET inverse_of = 900 WHERE name = 'has-part'")
    con.close()
    out = tmp_path / "merged.duckdb"
    merge_slots(a, b, out)
    con = duckdb.connect(str(out), read_only=True)
    try:
        got = con.execute("SELECT y.name FROM linkage_types x JOIN linkage_types y "
                          "ON y.id = x.inverse_of WHERE x.name = 'has-part'").fetchall()
    finally:
        con.close()
    assert got == [("part-of",)], got


# ---- ch-bsd r2 m-r2-5: the partial B is re-cloned right after the reopen ---

def test_copy2_swap_failure_reclones_b_and_keeps_the_writer(tmp_path, monkeypatch):
    import shutil as _sh
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path, "B")
    # a live store always has a facts.log; this one describes neither slot's
    # seeded rows (they were written with direct SQL, as the merge writes)
    d.store.log_path.write_text("")

    def bad_copy2(src, dst, *a, **k):
        raise OSError(28, "No space left on device (injected)")
    monkeypatch.setattr(_sh, "copy2", bad_copy2)
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is False and "swap" in r["error"], r
        monkeypatch.undo()
        assert (root / "catalog.B.duckdb").exists(), "B left missing until a restart"
        con = duckdb.connect(str(root / "catalog.B.duckdb"), read_only=True)
        try:
            n = con.execute("SELECT count(*) FROM entities").fetchone()[0]
        finally:
            con.close()
        assert n >= 3, n                     # the merged catalog, cloned from A
        assert d.store is not None and d.store._conn is not None
        assert d.store.db_path.name == "catalog.A.duckdb"
        ok, err = _child_can_open(root / "catalog.A.duckdb")
        assert not ok and "lock" in err.lower(), err
        # ch-bsd r3 m-r3-1: merge_slots writes the union with direct SQL and
        # logs zero events, so facts.log must be re-snapshotted from the merged
        # catalog (as the success path does) or a rebuild from the log drops
        # the recovered rows. `b-only.md` exists only in slot B's rows.
        log = d.store.log_path
        assert log.exists() and "b-only.md" in log.read_text(), \
            "facts.log still describes a pre-merge slot"
    finally:
        d.store.close()


def test_copy2_swap_failure_whose_reclone_fails_names_the_restart(tmp_path, monkeypatch):
    import shutil as _sh
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path, "A")

    def bad_copy(*a, **k):
        raise OSError(28, "No space left on device (injected)")
    monkeypatch.setattr(_sh, "copy2", bad_copy)
    monkeypatch.setattr(dm, "_copy_out_of_process", bad_copy)
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is False, r
        assert "restart" in r["error"] and "catalog.B" in r["error"], r
        monkeypatch.undo()
        _assert_writer_open_and_locked(d, root)
    finally:
        d.store.close()


def test_audit_via_writer_reports_partition_collisions_as_drift(tmp_path):
    """The daemon's `replica audit` runs on the live writer connection — the
    sibling of `audit_slots`, same report."""
    from refmatrix.replica_merge import audit_via_writer
    a, b = _slots(tmp_path)
    for path, pid in ((a, 78), (b, 77)):
        con = duckdb.connect(str(path))
        con.execute("INSERT INTO partitions(id, name, kind, created_at) VALUES (?, 'collide', 'repo', 1.0)", [pid])
        con.close()
    w = duckdb.connect(str(a))
    try:
        rep = audit_via_writer(w, writer_slot="A", reader_path=b, reader_slot="B")
    finally:
        w.close()
    assert rep["drift_detected"] is True
    assert rep.get("partition_collisions") and "collide" in " ".join(rep["partition_collisions"]), rep


def test_copy2_swap_failure_whose_repair_reopen_fails_names_the_reopen(tmp_path, monkeypatch):
    """ch-bsd r3 m-r3-3: when the reopen INSIDE the B repair raised, the op
    said "re-clone of catalog.B.duckdb failed … restart". The second
    `_reopen_writer` call (the repair's) is made to fail once; the clone ran."""
    import shutil as _sh
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path, "A")
    real = d._reopen_writer
    calls = []

    def flaky_reopen(slot=None):
        calls.append(slot)
        if len(calls) == 2:
            raise OSError("simulated reopen failure inside the B repair")
        return real(slot)

    def bad_copy2(*a, **k):
        raise OSError(28, "No space left on device (injected)")
    monkeypatch.setattr(_sh, "copy2", bad_copy2)
    monkeypatch.setattr(d, "_reopen_writer", flaky_reopen)
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is False, r
        assert "writer reopen on A after re-cloning B failed" in r["error"], r
        assert "re-clone failed" not in r["error"], r
        assert (root / "catalog.B.duckdb").exists()
        monkeypatch.undo()
        _assert_writer_open_and_locked(d, root)
    finally:
        d.store.close()


# ---- ch-bsd r4 m-r4-1: a slot-repair error names its cause -----------------

def _enospc(*a, **k):
    raise OSError(28, "No space left on device (injected)")


def test_startup_slot_repair_failure_logs_the_errno(tmp_path, monkeypatch):
    """The startup asymmetric repair logs `rotation slot repair failed:
    {exc!r}`; with SlotRepairError's message lacking the cause that line said
    only "clone: clone A -> B failed" — no errno. `_copy_out_of_process` (the
    out-of-process copy, a collaborator) fails with ENOSPC."""
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path, "A")
    lines: list = []
    d._log = lines.append
    (root / "catalog.B.duckdb").unlink()
    monkeypatch.setattr(dm, "_copy_out_of_process", _enospc)
    try:
        d._bootstrap_rotation_if_needed()
        failed = [l for l in lines if "rotation slot repair failed" in l]
        assert failed and "No space left on device" in failed[0], lines
        assert d.store is not None and d.store._conn is not None   # writer reopened
    finally:
        d.store.close()


def test_merge_b_repair_failure_log_line_names_the_errno(tmp_path, monkeypatch):
    import shutil as _sh
    from refmatrix import daemon as dm
    d, root = _daemon(tmp_path, "A")
    lines: list = []
    d._log = lines.append
    monkeypatch.setattr(_sh, "copy2", _enospc)
    monkeypatch.setattr(dm, "_copy_out_of_process", _enospc)
    try:
        dm._op_replica_merge(d, {"dry_run": False})
        repair = [l for l in lines if "B repair failed" in l]
        assert repair and "No space left on device" in repair[0], lines
    finally:
        d.store.close()
