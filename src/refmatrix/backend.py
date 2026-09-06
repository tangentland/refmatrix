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
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable

import duckdb

from refmatrix.duckdb_catalog import init_catalog as init_duckdb_catalog


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
    def connect(self, db_path: Path) -> "ConnLike":
        """Open a connection to the catalog at `db_path`. Must return a
        connection whose `execute()` produces sqlite3-shaped cursors."""

    @abstractmethod
    def init_catalog(self, con: "ConnLike") -> None:
        """Bootstrap the schema if it isn't there yet. Idempotent."""


class ConnLike:
    """Marker / structural type. Implementations expose:
        execute(sql, params=()) -> CursorLike
        executescript(sql) -> None  (sqlite parity; DuckDB uses execute)
        commit() -> None
        close() -> None
    """


# ---------- SQLite ---------------------------------------------------------


class SQLiteBackend(Backend):
    kind = "sqlite"
    db_filename = "catalog.db"

    def connect(self, db_path: Path) -> sqlite3.Connection:
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

    def init_catalog(self, con: sqlite3.Connection) -> None:
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
        self._duck.close()

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
        return DuckDBConnection(duckdb.connect(str(db_path), read_only=read_only))

    def init_catalog(self, con: DuckDBConnection) -> None:
        init_duckdb_catalog(con._duck)
