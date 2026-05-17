"""Read-only DuckDB facade over the SQLite catalog (`.refmatrix/catalog.db`).

Phase 1 of the DuckDB+Lance migration. The SQLite catalog stays the system of
record for writes; this module opens a DuckDB connection that mounts the same
file via the `sqlite_scanner` extension so SELECTs can be served by DuckDB.
Used to validate parity, then to actually serve the read side once the env
flag `RMX_READ_VIA_DUCKDB` is set.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import duckdb


SCHEMA_ALIAS = "cat"


class _DuckRow:
    """Mimics enough of sqlite3.Row for the call sites we care about: integer
    indexing, string-column indexing, `.keys()`, and `dict(row)` conversion."""

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

    def __repr__(self) -> str:
        return f"_DuckRow({dict(zip(self._cols, self._vals))!r})"


class _ReadCursor:
    """Cursor-shaped wrapper around a DuckDB result so callers can use the
    sqlite3 idioms (`.fetchone()`, `.fetchall()`, iteration)."""

    def __init__(self, result):
        self._cols = tuple(d[0] for d in result.description) if result.description else ()
        self._rows = result.fetchall()
        self._idx = 0

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


class ReadConnection:
    """Drop-in `con.execute(sql, params)` shim over a DuckDB connection. Only
    SELECTs are routed here; writes still go through the SQLite connection."""

    def __init__(self, duck_conn):
        self._duck = duck_conn

    def execute(self, sql: str, params: Iterable[Any] | tuple = ()) -> _ReadCursor:
        result = self._duck.execute(sql, list(params) if params else None)
        return _ReadCursor(result)


class DuckCatalogView:
    def __init__(self, db_path: Path | str, alias: str = SCHEMA_ALIAS):
        self.db_path = Path(db_path)
        self.alias = alias
        self.con = duckdb.connect(database=":memory:")
        self.con.execute("INSTALL sqlite_scanner")
        self.con.execute("LOAD sqlite_scanner")
        self.con.execute(
            f"ATTACH '{self.db_path}' AS {self.alias} (TYPE SQLITE, READ_ONLY)"
        )
        self.con.execute(f"USE {self.alias}")

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "DuckCatalogView":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def fetchall(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> list[tuple]:
        cur = self.con.execute(sql, list(params) if params else None)
        return cur.fetchall()

    def fetchone(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> tuple | None:
        cur = self.con.execute(sql, list(params) if params else None)
        return cur.fetchone()

    def tables(self) -> list[str]:
        rows = self.fetchall(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog = ? ORDER BY table_name",
            (self.alias,),
        )
        return [r[0] for r in rows]

    def read_connection(self) -> ReadConnection:
        return ReadConnection(self.con)
