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
#     new file (a child process read the file without it) — a silent WRITE
#     loss (ch-bsd 18.1 r1 B-1);
#   * a writer can NOT get the new file while any in-process instance still
#     holds the path: a read-write ATTACH, and a connect beside a read-only
#     ATTACH of the old inode, both fail "Unique file handle conflict". Only
#     closing every holder of the old inode frees the path.
# The bug-110 r1 test saw the read side as a Store reader returning
# `vectors_updated_at = NULL` for rows a fresh subprocess read as stamped.
#
# So every file-backed open in src/ goes through `open_duckdb`
# (tests/test_bug112_duckdb_reopen.py AST-checks for a second site), which
# registers each connection with the inode it opened:
#   * read-only: a private `:memory:` instance ATTACHes the file READ_ONLY and
#     USEs it — never a shared cached instance, so the open reads the file at
#     the path NOW. Unqualified names, PRAGMAs and `current_database()`
#     resolve against the attached file. An older reader keeps its own (old)
#     snapshot until it closes.
#   * write: before connecting, every registered connection still bound to a
#     REPLACED inode at that path is closed, with a warning. Such a connection
#     writes into an unlinked file — its writes are already lost — and it is
#     what would hand this open the old database. Its owner's next call fails
#     loudly ("Connection already closed") instead of losing more writes. If a
#     holder cannot be closed the open raises `StaleDuckDBInstanceError`.

_RO_ALIAS = "rmx_ro"
_HOLDERS_LOCK = threading.Lock()
# realpath -> [(weakref to the raw connection, (st_dev, st_ino) it opened)]
_HOLDERS: "dict[str, list]" = {}


class StaleDuckDBInstanceError(RuntimeError):
    """A write open of a replaced path while a connection to the old file
    could not be closed: DuckDB would return the old database."""


def _file_id(path: str) -> "tuple[int, int] | None":
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return (st.st_dev, st.st_ino)


def _live_holders(key: str) -> list:
    return [(r, fid) for r, fid in _HOLDERS.get(key, []) if r() is not None]


def _register(key: str, con) -> None:
    with _HOLDERS_LOCK:
        live = _live_holders(key)
        fid = _file_id(key)
        if fid is not None:
            live.append((weakref.ref(con), fid))
        _HOLDERS[key] = live


def _close_stale_holders(key: str, p: str) -> int:
    """Close every registered connection bound to a replaced inode at `key`.
    Returns how many were closed; raises StaleDuckDBInstanceError when one
    cannot be."""
    import logging
    with _HOLDERS_LOCK:
        now = _file_id(key)
        live = _live_holders(key)
        if now is None:
            return 0
        stale = [(r, fid) for r, fid in live if fid != now]
        _HOLDERS[key] = [(r, fid) for r, fid in live if fid == now]
    for r, fid in stale:
        con = r()
        if con is None:
            continue
        try:
            con.close()
        except Exception as exc:
            raise StaleDuckDBInstanceError(
                f"{p}: a connection to the replaced file (inode {fid[1]}; the path "
                f"now holds inode {now[1]}) could not be closed ({exc!r}); "
                "duckdb.connect would return the OLD database (bug-112)") from exc
        logging.getLogger(__name__).warning(
            "open_duckdb: closed a connection to replaced file %s (inode %d -> %d) "
            "before reopening it for write (bug-112)", p, fid[1], now[1])
    return len(stale)


def open_duckdb(path: "os.PathLike | str", *, read_only: bool = False):
    """Open a DuckDB database file and return the raw `DuckDBPyConnection`.
    `:memory:` passes straight through. See the block comment above."""
    p = str(path)
    if p == ":memory:":
        return duckdb.connect(":memory:")
    key = os.path.realpath(p)
    if read_only:
        con = duckdb.connect(":memory:")
        try:
            quoted = p.replace("'", "''")
            con.execute(f"ATTACH '{quoted}' AS {_RO_ALIAS} (READ_ONLY)")
            con.execute(f"USE {_RO_ALIAS}")
        except BaseException:
            con.close()
            raise
        _register(key, con)
        return con
    _close_stale_holders(key, p)
    con = duckdb.connect(p)
    _register(key, con)
    return con


def release_duckdb(con) -> None:
    """Close a connection from `open_duckdb` and drop it from the registry."""
    with _HOLDERS_LOCK:
        for key in list(_HOLDERS):
            kept = [(r, fid) for r, fid in _HOLDERS[key]
                    if r() is not None and r() is not con]
            if kept:
                _HOLDERS[key] = kept
            else:
                del _HOLDERS[key]
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
