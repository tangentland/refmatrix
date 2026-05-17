"""One-shot SQLite → native DuckDB catalog migration. Reads
`.refmatrix/catalog.db`, creates `.refmatrix/catalog.duckdb` with the
mirrored schema, copies every catalog row, and optionally packs the
on-disk `fragments/<partition>/*.rb64` files into the `bitmap_fragments`
BLOB table. Row counts verified at the end.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from refmatrix.duckdb_catalog import (
    SEQUENCES,
    TABLE_LOAD_ORDER,
    init_catalog,
)


SQLITE_ALIAS = "src"


def migrate_catalog(
    sqlite_path: Path | str,
    duckdb_path: Path | str,
    *,
    overwrite: bool = False,
    fragments_dir: Path | str | None = None,
) -> dict[str, int]:
    """Copy every catalog table from `sqlite_path` into a freshly-created
    DuckDB native catalog at `duckdb_path`. Returns a {table: row_count} map.
    The `bitmap_fragments` row count reports the number of (partition,
    linkage) BLOB rows packed in from disk; 0 when `fragments_dir` is None
    or doesn't exist.

    Raises FileExistsError if the destination already exists and `overwrite`
    is False — the migration is destructive on the destination side, never on
    the source. Source SQLite file is opened READ_ONLY.

    Pass `fragments_dir` to also pack the per-partition .rb64 fragment files
    into the `bitmap_fragments` BLOB table. Typically that's `<root>/fragments`.
    The source fragment files are not deleted — keep them as backup until
    you've verified the migrated DuckDB store reads correctly.
    """
    sqlite_path = Path(sqlite_path)
    duckdb_path = Path(duckdb_path)
    fragments_dir = Path(fragments_dir) if fragments_dir else None

    if not sqlite_path.exists():
        raise FileNotFoundError(f"source SQLite catalog not found: {sqlite_path}")
    if duckdb_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"destination DuckDB catalog already exists: {duckdb_path} "
                "(pass overwrite=True to replace)"
            )
        duckdb_path.unlink()

    con = duckdb.connect(str(duckdb_path))
    try:
        con.execute("INSTALL sqlite_scanner")
        con.execute("LOAD sqlite_scanner")
        con.execute(
            f"ATTACH '{sqlite_path}' AS {SQLITE_ALIAS} (TYPE SQLITE, READ_ONLY)"
        )
        # Compute sequence starts BEFORE creating tables — DuckDB can't ALTER
        # a sequence once a table column DEFAULTs to it, so we have to set
        # the START value at create time. Each sequence opens at one past the
        # max id observed in the source table.
        sequence_starts: dict[str, int] = {}
        for table, col, seq in SEQUENCES:
            present = con.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_catalog = ? AND table_name = ?",
                [SQLITE_ALIAS, table],
            ).fetchone()
            if not present:
                sequence_starts[seq] = 1
                continue
            row = con.execute(
                f"SELECT COALESCE(MAX({col}), 0) FROM {SQLITE_ALIAS}.main.{table}"
            ).fetchone()
            sequence_starts[seq] = (row[0] or 0) + 1

        init_catalog(con, sequence_starts=sequence_starts)

        counts: dict[str, int] = {}
        for table in TABLE_LOAD_ORDER:
            # Source might predate a schema addition (e.g. very old catalog
            # missing `tracked_files`). Skip absent tables — init_catalog has
            # already created the empty destination table.
            present = con.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_catalog = ? AND table_name = ?",
                [SQLITE_ALIAS, table],
            ).fetchone()
            if not present:
                counts[table] = 0
                continue

            # Use destination column order so any source column reorderings
            # (e.g. ALTER TABLE migrations) don't shift values into the wrong
            # column. SELECTing by name forces correct alignment.
            dst_cols = _ordered_columns(con, table)
            col_list = ", ".join(dst_cols)
            con.execute(
                f"INSERT INTO {table} ({col_list}) "
                f"SELECT {col_list} FROM {SQLITE_ALIAS}.main.{table}"
            )
            counts[table] = con.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

        # Parity check: row counts must match the source for tables that
        # exist on both sides.
        for table, n in counts.items():
            src_present = con.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_catalog = ? AND table_name = ?",
                [SQLITE_ALIAS, table],
            ).fetchone()
            if not src_present:
                continue
            src_count = con.execute(
                f"SELECT COUNT(*) FROM {SQLITE_ALIAS}.main.{table}"
            ).fetchone()[0]
            if src_count != n:
                raise RuntimeError(
                    f"row count mismatch on {table}: src={src_count} dst={n}"
                )

        # Pack per-partition fragment files into bitmap_fragments BLOB rows.
        # Naming: fragments/<partition_name>/<linkage>.rb64
        bitmap_count = 0
        if fragments_dir and fragments_dir.is_dir():
            # Resolve partition_name -> partition_id once.
            pid_by_name = {
                r[0]: r[1]
                for r in con.execute("SELECT name, id FROM partitions").fetchall()
            }
            for partition_subdir in sorted(fragments_dir.iterdir()):
                if not partition_subdir.is_dir():
                    continue
                pid = pid_by_name.get(partition_subdir.name)
                if pid is None:
                    # Partition referenced in fragments/ has no matching
                    # partitions row — skip rather than invent one.
                    continue
                for frag_path in sorted(partition_subdir.glob("*.rb64")):
                    blob = frag_path.read_bytes()
                    if not blob:
                        continue
                    linkage = frag_path.stem
                    con.execute(
                        "INSERT INTO bitmap_fragments(partition_id, linkage, blob) "
                        "VALUES (?, ?, ?) "
                        "ON CONFLICT(partition_id, linkage) DO UPDATE "
                        "SET blob = excluded.blob",
                        [pid, linkage, blob],
                    )
                    bitmap_count += 1
        counts["bitmap_fragments"] = bitmap_count

        con.execute(f"DETACH {SQLITE_ALIAS}")
        return counts
    finally:
        con.close()


def _ordered_columns(con, table: str) -> list[str]:
    """Return the destination table's columns in declaration order."""
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? AND table_catalog = current_database() "
        "ORDER BY ordinal_position",
        [table],
    ).fetchall()
    return [r[0] for r in rows]
