"""bug-112: an in-process DuckDB opener got the OLD database after the file at
its path was replaced.

Measured on DuckDB 1.5.2 (workflow/review-output/bug112-measure.log): while
ANY connection to path P is open in the process, `duckdb.connect(P)` returns
that connection's database instance, even after `os.replace` put a new file
(new inode) at P. `ATTACH 'P' (READ_ONLY)` from `:memory:` is not cached; a
connect after the last holder closes sees the new file.

The fix routes every file-backed DuckDB open through ONE function,
`backend.open_duckdb`: a read-only open ATTACHes from a private `:memory:`
instance (never shares a cached instance, so it always reads the file now at
the path), and a write open first closes every registered connection still
bound to a replaced inode at that path (the only way to free the path —
measured), so the reopen gets the new file and its writes reach disk. An AST
check refuses a second `duckdb.connect(<file>)` site.
"""
from __future__ import annotations

import ast
import os
import shutil
from pathlib import Path

import duckdb
import pytest

from refmatrix import backend as backend_mod
from refmatrix.backend import DuckDBBackend

SRC = Path(backend_mod.__file__).resolve().parent


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("RMX_HOME", str(home / ".refmatrix"))


def _make(path: Path, v: int) -> None:
    c = duckdb.connect(str(path))
    c.execute("CREATE TABLE t(v INTEGER)")
    c.execute("INSERT INTO t VALUES (?)", [v])
    c.close()


def _replace(path: Path, v: int) -> None:
    tmp = path.with_name(path.name + ".tmp")
    _make(tmp, v)
    os.replace(tmp, path)


# ---- the backend opener ---------------------------------------------------

def test_readonly_reopen_sees_the_replaced_file_while_the_old_is_held(tmp_path):
    p = tmp_path / "catalog.read.duckdb"
    _make(p, 1)
    old = DuckDBBackend().connect(p, read_only=True)
    assert old.execute("SELECT v FROM t").fetchone()[0] == 1
    _replace(p, 2)
    new = DuckDBBackend().connect(p, read_only=True)
    try:
        assert new.execute("SELECT v FROM t").fetchone()[0] == 2
        # the old holder keeps its own (old) snapshot — no one is yanked
        assert old.execute("SELECT v FROM t").fetchone()[0] == 1
    finally:
        new.close()
        old.close()


def _child_values(path: Path) -> list:
    """Read the file at `path` from a FRESH process — no instance cache."""
    import subprocess
    import sys
    out = subprocess.run(
        [sys.executable, "-c",
         "import duckdb,sys;c=duckdb.connect(sys.argv[1],read_only=True);"
         "print(sorted(r[0] for r in c.execute('SELECT v FROM t').fetchall()))",
         str(path)],
        capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return ast.literal_eval(out.stdout.strip())


def test_write_after_swap_reaches_the_new_file_on_disk(tmp_path):
    """ch-bsd 18.1 r1 B-1 (plan-18.3's in-daemon reclaim sequence): two
    in-process connects to one path; close one; `os.replace` a new file onto
    the path; reopen; write + CHECKPOINT. At HEAD the reopen served the OLD
    database and the checkpointed row never reached the file on disk."""
    p = tmp_path / "catalog.A.duckdb"
    _make(p, 1)
    c1 = DuckDBBackend().connect(p)
    c2 = DuckDBBackend().connect(p)
    c1.close()
    _replace(p, 2)
    c3 = DuckDBBackend().connect(p)
    try:
        assert c3.execute("SELECT v FROM t").fetchone()[0] == 2
        c3.execute("INSERT INTO t VALUES (99)")
        c3.execute("CHECKPOINT")
    finally:
        c3.close()
    assert _child_values(p) == [2, 99]
    # the holder of the replaced file was closed, loudly, not left writing
    # into an unlinked inode
    with pytest.raises(duckdb.ConnectionException):
        c2.execute("SELECT 1")


def test_write_reopen_beside_a_stale_reader_of_the_old_file(tmp_path):
    """A read-only holder of the old inode makes a writer connect fail
    'Unique file handle conflict' (measured); the write open closes it."""
    p = tmp_path / "catalog.A.duckdb"
    _make(p, 1)
    r = DuckDBBackend().connect(p, read_only=True)
    _replace(p, 2)
    w = DuckDBBackend().connect(p)
    try:
        w.execute("INSERT INTO t VALUES (7)")
        w.execute("CHECKPOINT")
    finally:
        w.close()
    assert _child_values(p) == [2, 7]
    r_closed = False
    try:
        r.execute("SELECT 1")
    except duckdb.ConnectionException:
        r_closed = True
    assert r_closed


def test_write_reopen_of_the_same_inode_shares_as_before(tmp_path):
    p = tmp_path / "catalog.A.duckdb"
    _make(p, 1)
    a = DuckDBBackend().connect(p)
    b = DuckDBBackend().connect(p)
    try:
        a.execute("INSERT INTO t VALUES (5)")
        assert b.execute("SELECT count(*) FROM t").fetchone()[0] == 2
    finally:
        a.close()
        b.close()


# ---- the Store / replica / memory_partition openers -----------------------

def _snapshot(tmp_path: Path, name: str, partitions: "list[str]") -> Path:
    from refmatrix.store import Store
    src = tmp_path / f"src-{name}" / ".refmatrix"
    src.mkdir(parents=True)
    for part in partitions:
        s = Store(src, partition=part, backend="duckdb")
        s._connect()
        s.close()
    return src / "catalog.duckdb"


def _install(snapshot: Path, root: Path) -> None:
    tmp = root / "catalog.read.duckdb.tmp"
    shutil.copyfile(snapshot, tmp)
    os.replace(tmp, root / "catalog.read.duckdb")


def _project_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    (root / "catalog.duckdb").touch()       # select_backend autodetect -> duckdb
    return root


def _names(store) -> "set[str]":
    return {r[0] for r in store._connect().execute("SELECT name FROM partitions").fetchall()}


def test_second_store_reader_sees_a_replaced_snapshot(tmp_path):
    from refmatrix.store import Store
    root = _project_root(tmp_path)
    _install(_snapshot(tmp_path, "one", ["proj"]), root)
    held = Store(root, partition="proj", read_only=True)
    assert "memory-proj" not in _names(held)
    _install(_snapshot(tmp_path, "two", ["proj", "memory-proj"]), root)
    fresh = Store(root, partition="proj", read_only=True)
    try:
        assert "memory-proj" in _names(fresh)
    finally:
        fresh.close()
        held.close()


def test_memory_partition_sees_a_replaced_snapshot_while_another_reader_holds_the_old(tmp_path):
    from refmatrix import search, verbs
    from refmatrix.store import Store
    root = _project_root(tmp_path)
    _install(_snapshot(tmp_path, "one", ["proj"]), root)
    search._REPLICA_CACHE.pop(str(root.resolve()), None)
    try:
        assert verbs.memory_partition(root) == "proj"
        # a second in-process opener of the same snapshot (the bug-110 test
        # shape) holds the OLD file open across the replace
        held = Store(root, partition="proj", read_only=True)
        _names(held)
        _install(_snapshot(tmp_path, "two", ["proj", "memory-proj"]), root)
        assert verbs.memory_partition(root) == "memory-proj"
        held.close()
    finally:
        hit = search._REPLICA_CACHE.pop(str(root.resolve()), None)
        if hit is not None:
            hit[0].close()


# ---- one opener (AST check against bypass) --------------------------------

def _is_memory(arg: ast.AST) -> bool:
    return isinstance(arg, ast.Constant) and arg.value == ":memory:"


def test_every_file_backed_duckdb_connect_goes_through_open_duckdb():
    stray = []
    for py in sorted(SRC.rglob("*.py")):
        tree = ast.parse(py.read_text())
        allowed: set = set()
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name in ("open_duckdb", "_open_write") \
                    and py.name == "backend.py":
                allowed |= {id(n) for n in ast.walk(fn)}
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "connect" and isinstance(n.func.value, ast.Name)
                    and "duckdb" in n.func.value.id):
                continue
            target = n.args[0] if n.args else next(
                (k.value for k in n.keywords if k.arg == "database"), None)
            if target is not None and _is_memory(target):
                continue
            if id(n) in allowed:
                continue
            stray.append(f"{py.relative_to(SRC)}:{n.lineno}")
    assert not stray, f"file-backed duckdb.connect outside backend.open_duckdb: {stray}"


def test_every_file_attach_goes_through_attach_file():
    """ch-bsd plan-23/17 r9: raw `ATTACH '<file>'` strings (the mirror, the
    merge, the audit, the sqlite migration/view) are file opens too. One
    helper, `backend.attach_file`, renders them; a literal elsewhere fails."""
    import re
    pat = re.compile(r"ATTACH\s+['\"{]", re.I)
    stray = []
    for py in sorted(SRC.rglob("*.py")):
        tree = ast.parse(py.read_text())
        allowed: set = set()
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name == "attach_file" \
                    and py.name == "backend.py":
                allowed |= {id(n) for n in ast.walk(fn)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and pat.search(n.value) and id(n) not in allowed:
                stray.append(f"{py.relative_to(SRC)}:{n.lineno}")
    assert not stray, f"file ATTACH outside backend.attach_file: {stray}"


# ---- ch-bsd r1 s-1: one private instance per (path, inode) ----------------

def test_readers_of_one_file_share_one_private_instance(tmp_path):
    """Eight concurrent readers of an 828 MB snapshot cost +699 MB RSS and
    +120 threads with one instance each (ch-bsd r1 s-1). Readers of the same
    (path, inode) now share one private instance: a table one creates in the
    instance's own `memory` catalog is visible to the other."""
    p = tmp_path / "catalog.read.duckdb"
    _make(p, 1)
    r1 = DuckDBBackend().connect(p, read_only=True)
    r2 = DuckDBBackend().connect(p, read_only=True)
    try:
        r1.execute("CREATE TABLE memory.main.same_instance_probe AS SELECT 7 AS x")
        assert r2.execute("SELECT x FROM memory.main.same_instance_probe").fetchone()[0] == 7
        assert r2.execute("SELECT v FROM t").fetchone()[0] == 1
    finally:
        r1.close()
        r2.close()


def test_a_replaced_file_gets_a_new_instance_and_the_last_close_frees_the_path(tmp_path):
    p = tmp_path / "catalog.read.duckdb"
    _make(p, 1)
    old = DuckDBBackend().connect(p, read_only=True)
    _replace(p, 2)
    new = DuckDBBackend().connect(p, read_only=True)
    try:
        assert new.execute("SELECT v FROM t").fetchone()[0] == 2
        assert old.execute("SELECT v FROM t").fetchone()[0] == 1
    finally:
        old.close()
        new.close()
    # every reader closed -> nothing holds the file: a writer opens it
    w = duckdb.connect(str(p))
    w.close()


# ---- ch-bsd r1 s-2: a stale holder mid-statement ---------------------------

def test_stale_reader_mid_statement_is_interrupted_and_the_writer_proceeds(tmp_path):
    """Probe T3: on 1.5.3 close() blocked until a 32 s statement finished; on
    1.5.2 the write open then failed 'Unique file handle conflict'. The stale
    holder is interrupted before it is closed."""
    import threading
    import time
    p = tmp_path / "catalog.A.duckdb"
    _make(p, 1)
    r = DuckDBBackend().connect(p, read_only=True)
    out: dict = {}

    def long_read():
        try:
            out["r"] = r.execute(
                "SELECT count(*) FROM range(50000000000) a, t").fetchone()
        except Exception as e:  # noqa: BLE001 — the type is asserted below
            out["e"] = e

    th = threading.Thread(target=long_read)
    th.start()
    time.sleep(1.0)
    _replace(p, 2)
    t0 = time.monotonic()
    w = DuckDBBackend().connect(p)
    took = time.monotonic() - t0
    try:
        w.execute("INSERT INTO t VALUES (5)")
        w.execute("CHECKPOINT")
    finally:
        w.close()
    th.join(30)
    assert not th.is_alive(), "the stale reader's statement was never interrupted"
    assert took < 10.0, f"write open waited {took:.1f}s on a stale reader's statement"
    assert "e" in out, f"stale reader finished its statement on a replaced file: {out}"
    assert _child_values(p) == [2, 5]


def test_an_unclosable_holder_raises_stale_not_a_driver_conflict(tmp_path):
    """A holder outside the registry (a raw connect, as a test or a library
    would make) still binds the old inode: the write open must say what is
    wrong, not surface the driver's configuration/handle conflict."""
    p = tmp_path / "catalog.A.duckdb"
    _make(p, 1)
    raw = duckdb.connect(str(p), read_only=True)
    _replace(p, 2)
    try:
        with pytest.raises(backend_mod.StaleDuckDBInstanceError) as ei:
            DuckDBBackend().connect(p)
        assert str(p) in str(ei.value)
    finally:
        raw.close()


# ---- ch-bsd r1 m-3: the inode is checked before AND after connecting -------

def test_a_replace_during_connect_is_detected_and_retried(tmp_path, monkeypatch):
    """`duckdb.connect` is wrapped (a collaborator) to `os.replace` a new file
    onto the path right after it connects — the race m-3 names. The opener
    must notice the inode moved and reopen, returning the new file."""
    p = tmp_path / "catalog.A.duckdb"
    _make(p, 1)
    real = duckdb.connect
    fired = []

    def racing_connect(*a, **k):
        con = real(*a, **k)
        if not fired and str(a[0] if a else k.get("database")) == str(p):
            fired.append(1)
            _replace(p, 2)
        return con

    monkeypatch.setattr(backend_mod.duckdb, "connect", racing_connect)
    w = DuckDBBackend().connect(p)
    try:
        assert fired
        assert w.execute("SELECT v FROM t").fetchone()[0] == 2
    finally:
        w.close()


# ---- ch-bsd r1 m-2: the stale-close warning reaches the daemon log ---------

def test_stale_close_warning_reaches_the_daemon_log(tmp_path):
    from refmatrix import daemon as dm
    root = Path(__import__("tempfile").mkdtemp(prefix="rmx", dir="/tmp")) / ".refmatrix"
    root.mkdir()
    d = dm.Daemon(root)
    d.log_fh = (root / "rmxd.log").open("a", encoding="utf-8")
    try:
        getattr(d, "_attach_backend_log", lambda: None)()   # absent at r1 HEAD
        p = tmp_path / "catalog.A.duckdb"
        _make(p, 1)
        held = DuckDBBackend().connect(p)
        _replace(p, 2)
        w = DuckDBBackend().connect(p)
        w.close()
        held  # noqa: B018 — kept referenced so it is a live (stale) holder
        text = (root / "rmxd.log").read_text()
        assert "replaced file" in text and str(p) in text, text
    finally:
        getattr(d, "_detach_backend_log", lambda: None)()
        d.log_fh.close()


def test_a_stale_holder_that_cannot_be_closed_raises_stale(tmp_path):
    """ch-bsd r1 M-j survived: the raise when a stale holder's close fails had
    no test. A DuckDB close cannot be made to fail on demand, so a stand-in
    holder whose interrupt/close raise is registered for the old inode (a
    registry entry, not a patched function); the write open must refuse
    rather than connect beside it."""
    import weakref

    class _Unclosable:
        def interrupt(self):
            raise RuntimeError("cannot interrupt (injected)")

        def close(self):
            raise RuntimeError("cannot close (injected)")

    p = tmp_path / "catalog.A.duckdb"
    _make(p, 1)
    st = os.stat(p)
    holder = _Unclosable()
    key = os.path.realpath(p)
    with backend_mod._HOLDERS_LOCK:
        backend_mod._WRITERS.setdefault(key, []).append(
            (weakref.ref(holder), (st.st_dev, st.st_ino)))
    _replace(p, 2)
    try:
        with pytest.raises(backend_mod.StaleDuckDBInstanceError) as ei:
            DuckDBBackend().connect(p)
        assert "could not be closed" in str(ei.value)
    finally:
        with backend_mod._HOLDERS_LOCK:
            backend_mod._WRITERS.pop(key, None)
