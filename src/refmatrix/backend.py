"""Catalog backend abstraction (phase-2b of the DuckDB migration).

The legacy Store talked directly to a sqlite3 connection. To let the same
Store run on top of a native DuckDB catalog, we factor connection
management + DDL bootstrap into Backend implementations:

- `SQLiteBackend` wraps the original behavior (PRAGMA WAL, foreign_keys,
  busy_timeout, executescript-based DDL) and is the default.
- `DuckDBBackend` opens `catalog.duckdb` and bootstraps the mirror schema
  from refmatrix.duckdb_catalog. Returned connections expose a
  sqlite3-shaped surface (`.execute(sql, params).fetchone()/fetchall()`,
  `.commit()`, `.close()`, dict-or-tuple row access) so the rest of Store
  doesn't have to branch on backend kind.

Selection: DuckDB is the default (since 2026-05-16). SQLite is opt-in only —
`RMX_BACKEND=sqlite` / constructor arg — or autodetected for a legacy store
whose `.refmatrix/catalog.db` already exists.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import weakref
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable, Protocol

import duckdb

from refmatrix.duckdb_catalog import init_catalog as init_duckdb_catalog


# ---- THE file-backed DuckDB opener (bug-112) --------------------------------
#
# DuckDB's Python `connect(path)` goes through a process-wide instance cache:
# while ANY connection to `path` is open in the process, a new connect returns
# THAT database instance — even after `os.replace` put a different file (new
# inode) at the path. Measured on 1.5.2 (bug-112, 2026-10-15,
# workflow/review-output/bug112-measure.log):
#   * a second read-only connect after a replace read the old value; ATTACH
#     READ_ONLY from `:memory:` read the new one;
#   * two write connects, close one, replace, reopen, INSERT + CHECKPOINT: the
#     reopen served the OLD database and the checkpointed row never reached the
#     new file — a silent WRITE loss (ch-bsd 18.1 r1 B-1);
#   * a writer can NOT get the new file while any in-process instance still
#     holds the path ("Unique file handle conflict"); only closing every holder
#     of the old inode frees it.
#
# Every file-backed open in src/ goes through `open_duckdb`, and every file
# ATTACH through `attach_file` (tests/test_bug112_duckdb_reopen.py AST-checks
# both for a second site):
#   * read-only: ONE private `:memory:` instance per (realpath, inode) ATTACHes
#     the file READ_ONLY; each open gets a cursor of it (`USE`d onto the file).
#     A replace changes the inode, so the next open gets a NEW instance on the
#     new file — no staleness — while readers of one file share one buffer pool
#     and thread pool (ch-bsd r1 s-1: one instance per open cost +699 MB RSS and
#     +120 threads for 8 concurrent readers of the 828 MB snapshot). The
#     instance closes with its last cursor.
#   * write: every registered holder (writer or read-only instance) still bound
#     to a REPLACED inode at that path is interrupted, then closed, with a
#     warning on the `refmatrix.backend` logger (the daemon routes it to
#     rmxd.log). Its writes were already going into an unlinked file. The inode
#     is checked before AND after connecting; a replace in between reconnects.
#     A path DuckDB still refuses (an unregistered holder, a 1.5.2 deferred
#     close) raises `StaleDuckDBInstanceError` naming it.

_RO_ALIAS = "rmx_ro"
_HOLDERS_LOCK = threading.Lock()
# realpath -> [(weakref to a raw write connection, (st_dev, st_ino))]
_WRITERS: "dict[str, list]" = {}
# (realpath, (st_dev, st_ino)) -> _ROInstance
_RO_INSTANCES: "dict[tuple, _ROInstance]" = {}
_OPEN_RETRIES = 3
_CONFLICT_WAIT_S = 2.0
_log = logging.getLogger("refmatrix.backend")


class StaleDuckDBInstanceError(duckdb.ConnectionException):
    """A write open of a path DuckDB still binds to a connection this opener
    could not close (a replaced file's holder): connecting would return the
    old database or be refused."""


def _file_id(path: str) -> "tuple[int, int] | None":
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return (st.st_dev, st.st_ino)


def attach_file(con, path: "os.PathLike | str", alias: str, *,
                read_only: bool = True, db_type: "str | None" = None) -> None:
    """THE rendering of `ATTACH '<file>' AS <alias> (...)` — the snapshot
    mirror, the slot merge/audit, the sqlite migration and view all ATTACH
    files; one place quotes the path and names the options."""
    opts = [f"TYPE {db_type}"] if db_type else []
    if read_only:
        opts.append("READ_ONLY")
    quoted = str(path).replace("'", "''")
    tail = f" ({', '.join(opts)})" if opts else ""
    con.execute(f"ATTACH '{quoted}' AS {alias}{tail}")


_DRAIN_S = 1.0
# Cursor calls counted as "a statement in flight" (ch-bsd r2 s-r2-1).
_TRACKED = frozenset({
    "execute", "executemany", "sql", "query", "fetchone", "fetchall", "fetchmany",
    "fetchdf", "fetch_df", "fetchnumpy", "fetch_arrow_table", "arrow", "df", "pl",
    "register", "unregister",
})


class _ROInstance:
    """One private DuckDB instance with one file ATTACHed read-only.

    `closed` stops new cursors and statements; `inflight` counts statements
    running on its cursors. Closing the instance under a running statement
    segfaulted duckdb 1.5.2 (3/3, ch-bsd r2 s-r2-1) and raised INTERNAL
    errors in r1, so `shut` interrupts, waits for `inflight` to drain, and
    only then closes — or leaves the close to the last statement to finish."""

    def __init__(self, key: str, path: str, fid: "tuple[int, int] | None"):
        self.key, self.fid = key, fid
        self.base = duckdb.connect(":memory:")
        try:
            attach_file(self.base, path, _RO_ALIAS, read_only=True)
            self.base.execute(f"USE {_RO_ALIAS}")
        except BaseException:
            self.base.close()
            raise
        self.handles: "weakref.WeakSet[_ROHandle]" = weakref.WeakSet()
        self.refs = 0
        self.closed = False          # no new cursors / statements
        self.base_closed = False
        self.inflight = 0
        self.cv = threading.Condition()

    def handle(self) -> "_ROHandle":
        # called with _HOLDERS_LOCK held, on an instance that is not closed
        cur = self.base.cursor()
        try:
            cur.execute(f"USE {_RO_ALIAS}")       # a cursor does not inherit USE (measured)
        except BaseException:
            cur.close()
            raise
        self.refs += 1
        h = _ROHandle(self, cur)
        self.handles.add(h)
        return h

    def enter(self) -> None:
        with self.cv:
            if self.closed:
                raise duckdb.ConnectionException(
                    f"{self.key}: this read-only connection was closed because the file "
                    "at its path was replaced; reopen it (bug-112)")
            self.inflight += 1

    def leave(self) -> None:
        with self.cv:
            self.inflight -= 1
            if self.inflight == 0:
                self.cv.notify_all()
                if self.closed and not self.base_closed:
                    self._close_base_locked()     # the deferred close of a drained shut

    def _close_base_locked(self) -> None:
        self.base_closed = True
        self.base.close()

    def shut(self, *, interrupt: bool) -> bool:
        """Stop, interrupt, drain, close. Returns True when the instance is
        closed now, False when the close is deferred to the last running
        statement (ch-bsd r3 m-r3-3: the caller logged "closed" either way)."""
        with self.cv:
            self.closed = True
            live = list(self.handles)
        if interrupt:
            for h in live:
                try:
                    h._cur.interrupt()
                except Exception as exc:  # noqa: BLE001 — reported, the close still waits
                    _log.warning("open_duckdb: interrupt of a reader on %s failed: %r",
                                 self.key, exc)
        with self.cv:
            if self.cv.wait_for(lambda: self.inflight == 0, timeout=_DRAIN_S):
                if not self.base_closed:
                    self._close_base_locked()
                return True
            return False


def _drop_handle(inst: _ROInstance, cur, ref) -> None:
    """Finalizer of a read-only handle: close its cursor, forget the handle,
    and close the instance with its last cursor (a closed instance no longer
    holds the file)."""
    h = ref()
    if h is not None:
        inst.handles.discard(h)                   # shut must not touch it (ch-bsd r2 m-r2-2)
    with inst.cv:
        if not inst.base_closed:
            cur.close()
    with _HOLDERS_LOCK:
        inst.refs -= 1
        last = inst.refs <= 0 and not inst.closed
        if last:
            inst.closed = True
            if _RO_INSTANCES.get((inst.key, inst.fid)) is inst:
                del _RO_INSTANCES[(inst.key, inst.fid)]
    if last:
        with inst.cv:
            if inst.inflight == 0 and not inst.base_closed:
                inst._close_base_locked()


class _ROHandle:
    """A read-only connection from `open_duckdb`: a cursor of the shared
    instance. Attribute access forwards to the cursor; statement calls are
    counted in flight; `close()` releases it."""

    __slots__ = ("_inst", "_cur", "_fin", "__weakref__")

    def __init__(self, inst: _ROInstance, cur):
        self._inst, self._cur = inst, cur
        self._fin = weakref.finalize(self, _drop_handle, inst, cur, weakref.ref(self))

    def __getattr__(self, name: str):
        attr = getattr(self._cur, name)
        if name not in _TRACKED or not callable(attr):
            return attr
        inst, cur, handle = self._inst, self._cur, self

        def tracked(*a, **k):
            inst.enter()
            try:
                out = attr(*a, **k)
            finally:
                inst.leave()
            return handle if out is cur else out  # keep chained fetches counted
        return tracked

    def close(self) -> None:
        self._fin()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _open_read_only(p: str, key: str) -> _ROHandle:
    for _ in range(_OPEN_RETRIES):
        fid = _file_id(key)
        with _HOLDERS_LOCK:
            inst = _RO_INSTANCES.get((key, fid))
            if inst is not None and not inst.closed:
                return inst.handle()
        new = _ROInstance(key, p, fid)
        if _file_id(key) != fid:                  # replaced while attaching (m-3)
            new.shut(interrupt=False)
            continue
        with _HOLDERS_LOCK:
            inst = _RO_INSTANCES.get((key, fid))
            if inst is None or inst.closed:
                _RO_INSTANCES[(key, fid)] = new
                return new.handle()
            h = inst.handle()
        new.shut(interrupt=False)                 # lost a race to an equal instance
        return h
    raise StaleDuckDBInstanceError(f"{p}: the file kept being replaced during the open")


def _close_stale_holders(key: str, p: str) -> int:
    """Interrupt and close every registered holder bound to a replaced inode at
    `key`. Returns how many were closed."""
    with _HOLDERS_LOCK:
        now = _file_id(key)
        if now is None:
            return 0
        live = [(r, fid) for r, fid in _WRITERS.get(key, []) if r() is not None]
        stale_w = [(r, fid) for r, fid in live if fid != now]
        _WRITERS[key] = [(r, fid) for r, fid in live if fid == now]
        stale_r = [inst for (k, fid), inst in _RO_INSTANCES.items()
                   if k == key and fid != now and not inst.closed]
        for inst in stale_r:
            del _RO_INSTANCES[(inst.key, inst.fid)]
    closed = 0
    for r, fid in stale_w:
        con = r()
        if con is None:
            continue
        try:
            con.interrupt()
            con.close()
        except Exception as exc:
            raise StaleDuckDBInstanceError(
                f"{p}: a connection to the replaced file (inode {fid[1]}; the path now "
                f"holds inode {now[1]}) could not be closed ({exc!r}) (bug-112)") from exc
        closed += 1
        _log.warning("open_duckdb: closed a writer of replaced file %s (inode %d -> %d) "
                     "before reopening it for write (bug-112)", p, fid[1], now[1])
    for inst in stale_r:
        old_ino = inst.fid[1] if inst.fid else -1
        if inst.shut(interrupt=True):
            _log.warning("open_duckdb: interrupted and closed a reader of replaced file %s "
                         "(inode %d -> %d) before reopening it for write (bug-112)",
                         p, old_ino, now[1])
        else:
            _log.warning("open_duckdb: interrupted a reader of replaced file %s (inode %d -> "
                         "%d); %d statement(s) still running after %.1fs, so its close is "
                         "DEFERRED to the last of them (bug-112)",
                         p, old_ino, now[1], inst.inflight, _DRAIN_S)
        closed += 1
    return closed


def _is_path_conflict(exc: BaseException) -> bool:
    msg = str(exc)
    return ("Unique file handle conflict" in msg
            or "different configuration than existing connections" in msg)


def _open_write(p: str, key: str):
    import time as _time
    for _ in range(_OPEN_RETRIES):
        closed = _close_stale_holders(key, p)
        before = _file_id(key)
        deadline = _time.monotonic() + (_CONFLICT_WAIT_S if closed else 0.0)
        while True:
            try:
                con = duckdb.connect(p)
                break
            except duckdb.Error as exc:
                if not _is_path_conflict(exc):
                    raise
                if _time.monotonic() >= deadline:
                    raise StaleDuckDBInstanceError(
                        f"{p}: another connection in this process still holds this path "
                        f"({closed} stale holder(s) closed first); DuckDB refused the open "
                        f"({exc}) — close every holder before reopening (bug-112)") from exc
                _time.sleep(0.05)
        after = _file_id(key)
        if before is not None and after != before:  # replaced during the connect (m-3)
            con.close()
            continue
        with _HOLDERS_LOCK:
            live = [(r, fid) for r, fid in _WRITERS.get(key, []) if r() is not None]
            if after is not None:
                live.append((weakref.ref(con), after))
            _WRITERS[key] = live
        return con
    raise StaleDuckDBInstanceError(f"{p}: the file kept being replaced during the open")


def open_duckdb(path: "os.PathLike | str", *, read_only: bool = False):
    """Open a DuckDB database file. `:memory:` passes straight through; a
    write open returns the raw `DuckDBPyConnection`, a read-only open a cursor
    handle of the shared private instance. See the block comment above."""
    p = str(path)
    if p == ":memory:":
        return duckdb.connect(":memory:")
    key = os.path.realpath(p)
    if read_only:
        return _open_read_only(p, key)
    return _open_write(p, key)


def release_duckdb(con) -> None:
    """Close a connection from `open_duckdb` and drop it from the registry."""
    if isinstance(con, _ROHandle):
        con.close()
        return
    with _HOLDERS_LOCK:
        for key in list(_WRITERS):
            kept = [(r, fid) for r, fid in _WRITERS[key]
                    if r() is not None and r() is not con]
            if kept:
                _WRITERS[key] = kept
            else:
                del _WRITERS[key]
    con.close()


def select_backend(
    name: str | None = None,
    *,
    root: "os.PathLike | str | None" = None,
) -> "Backend":
    """Resolve which backend to use.

    Resolution order:
        1. Explicit `name` kwarg (constructor arg).
        2. `RMX_BACKEND` env var.
        3. Autodetect from `root` if provided:
              .refmatrix/catalog.duckdb exists -> duckdb
              .refmatrix/catalog.db      exists -> sqlite  (keeps legacy stores working)
        4. Default: duckdb (DuckDB became the default 2026-05-16; SQLite
           stays opt-in via env or constructor for legacy callers).
    """
    explicit = name or os.environ.get("RMX_BACKEND")
    if explicit:
        kind = explicit.lower()
    elif root is not None:
        from pathlib import Path
        r = Path(root)
        if (r / "catalog.duckdb").exists():
            kind = "duckdb"
        elif (r / "catalog.db").exists():
            kind = "sqlite"
        else:
            kind = "duckdb"
    else:
        kind = "duckdb"
    if kind == "sqlite":
        return SQLiteBackend()
    if kind == "duckdb":
        return DuckDBBackend()
    raise ValueError(f"unknown RMX_BACKEND: {kind!r} (expected 'sqlite' or 'duckdb')")


class Backend(ABC):
    kind: str
    db_filename: str

    @abstractmethod
    def connect(self, db_path: Path, read_only: bool = False) -> "ConnLike":
        """Open a connection to the catalog at `db_path`. Must return a
        connection whose `execute()` produces sqlite3-shaped cursors.
        `read_only` is honored by DuckDB; SQLite ignores it (WAL readers
        don't block)."""

    @abstractmethod
    def init_catalog(self, con: "ConnLike") -> None:
        """Bootstrap the schema if it isn't there yet. Idempotent."""


class ConnLike(Protocol):
    """Structural type for catalog connections. sqlite3.Connection and
    DuckDBConnection both satisfy it; nothing instantiates it."""

    def execute(self, *args: Any, **kwargs: Any) -> Any: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...


# ---------- SQLite ---------------------------------------------------------


class SQLiteBackend(Backend):
    kind = "sqlite"
    db_filename = "catalog.db"

    def connect(self, db_path: Path,
                read_only: bool = False) -> sqlite3.Connection:
        con = sqlite3.connect(db_path, check_same_thread=False)
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA busy_timeout = 5000")
        con.row_factory = sqlite3.Row
        # Portability shim: DuckDB has GREATEST/LEAST as scalar functions,
        # SQLite does not. Store SQL uses GREATEST so the same string works
        # under both backends. SQLite's `MAX(a, b)` is also scalar but DuckDB
        # treats MAX as aggregate-only — sticking with GREATEST avoids the
        # collision.
        con.create_function("GREATEST", 2, lambda a, b: a if a >= b else b)
        con.create_function("LEAST", 2, lambda a, b: a if a <= b else b)
        return con

    def init_catalog(self, con: Any) -> None:
        # SQLiteBackend doesn't own the SQLite DDL — store.py still drives it
        # via CATALOG_DDL.executescript() because the legacy migration path
        # (partitions backfill, ALTER TABLE adds, etc.) is interleaved.
        # Calling this is a no-op for parity with DuckDBBackend.
        pass


# ---------- DuckDB --------------------------------------------------------


class _DuckRow:
    """sqlite3.Row-shaped wrapper around a DuckDB result row."""

    __slots__ = ("_cols", "_vals", "_lookup")

    def __init__(self, cols: tuple[str, ...], vals: tuple):
        self._cols = cols
        self._vals = vals
        self._lookup = None

    def keys(self) -> list[str]:
        return list(self._cols)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        if self._lookup is None:
            self._lookup = {c: i for i, c in enumerate(self._cols)}
        return self._vals[self._lookup[key]]

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


class _DuckCursor:
    """sqlite3.Cursor-shaped view over a DuckDB result. Supports the subset
    Store actually uses: fetchone, fetchall, iteration, lastrowid."""

    def __init__(self, result, lastrowid: int | None = None):
        if result is None or result.description is None:
            self._cols: tuple[str, ...] = ()
            self._rows: list[tuple] = []
        else:
            self._cols = tuple(d[0] for d in result.description)
            self._rows = result.fetchall()
        self._idx = 0
        self.lastrowid = lastrowid

    def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        r = self._rows[self._idx]
        self._idx += 1
        return _DuckRow(self._cols, r)

    def fetchall(self):
        out = [_DuckRow(self._cols, r) for r in self._rows[self._idx:]]
        self._idx = len(self._rows)
        return out

    def __iter__(self):
        while self._idx < len(self._rows):
            r = self._rows[self._idx]
            self._idx += 1
            yield _DuckRow(self._cols, r)


class DuckDBConnection:
    """Adapts a `duckdb.DuckDBPyConnection` to the subset of the sqlite3
    Connection surface that refmatrix.store relies on. Specifically:

    - `.execute(sql, params=())` returns a `_DuckCursor`.
    - `.executescript(script)` splits on `;` and runs each statement.
    - `.commit()` is a no-op (DuckDB autocommits in default mode).
    - `.close()` closes the underlying connection.
    - `row_factory` is a writable attribute for sqlite3 parity, ignored.

    Parameter style: SQLite uses `?`; DuckDB also accepts `?` for prepared
    statements, so the SQL strings in store.py port straight across.
    """

    def __init__(self, duck_conn):
        self._duck = duck_conn
        self.row_factory = None  # ignored; sqlite3 parity

    def execute(self, sql: str, params: Iterable[Any] | tuple = ()) -> _DuckCursor:
        result = self._duck.execute(sql, list(params) if params else None)
        return _DuckCursor(result)

    def executemany(
        self, sql: str, seq_of_params: Iterable[Iterable[Any]]
    ) -> _DuckCursor:
        # DuckDB supports executemany natively. Returned cursor isn't very
        # useful (no rowset for INSERT/UPDATE/DELETE) but matches sqlite3.
        result = self._duck.executemany(sql, [list(p) for p in seq_of_params])
        return _DuckCursor(result)

    def executescript(self, script: str) -> None:
        # Split on ';' that aren't inside a string literal. Store's scripts
        # don't contain string literals with embedded semicolons today, so
        # a naive split is sufficient.
        for stmt in script.split(";"):
            if stmt.strip():
                self._duck.execute(stmt)

    def commit(self) -> None:
        # DuckDB autocommits each statement by default. No-op for parity.
        pass

    def close(self) -> None:
        release_duckdb(self._duck)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # Match sqlite3.Connection: context exit commits/rolls back but does
        # NOT close. Store keeps the connection alive across many `with` blocks.
        if exc[0] is None:
            self.commit()


class DuckDBBackend(Backend):
    kind = "duckdb"
    db_filename = "catalog.duckdb"

    def connect(self, db_path: Path, read_only: bool = False) -> DuckDBConnection:
        return DuckDBConnection(open_duckdb(db_path, read_only=read_only))

    def init_catalog(self, con: Any) -> None:
        init_duckdb_catalog(con._duck)
