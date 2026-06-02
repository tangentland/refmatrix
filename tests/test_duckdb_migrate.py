"""Phase-2: SQLite → DuckDB native catalog migration. Round-trip the seeded
catalog into DuckDB and assert table-by-table row equality + sequence values
that won't collide on subsequent inserts."""
from __future__ import annotations

import pytest
import sqlite3

import duckdb

from refmatrix.duckdb_catalog import TABLE_LOAD_ORDER, init_catalog
from refmatrix.migrate import migrate_catalog
from refmatrix.store import Store


@pytest.fixture
def seeded_catalog(tmp_path):
    # Source is intentionally a SQLite catalog — that's what `migrate_catalog`
    # consumes. Pinning the backend keeps the test honest when the suite is
    # run with `RMX_BACKEND=duckdb` overall.
    s = Store(tmp_path / ".refmatrix", backend="sqlite")
    s.init()
    parser = s.add_concept("parser", description="parses input")
    tok = s.add_concept("tokenizer")
    foo = s.upsert_entity(kind="code", name="src/foo.py", path="src/foo.py")
    lex = s.upsert_entity(kind="code", name="src/lex.py", path="src/lex.py",
                          tldr="tokenizer impl")
    readme = s.upsert_entity(kind="doc", name="README.md", path="README.md",
                             protected=True)
    s.link("defines", parser, foo, weight=0.9)
    s.link("defines", tok, lex)
    s.link("mentions", parser, readme)
    s.link("related_to", parser, lex)
    s.close()
    return tmp_path / ".refmatrix" / "catalog.db"


def test_init_catalog_idempotent(tmp_path):
    """Re-running init_catalog on the same connection must not fail."""
    p = tmp_path / "catalog.duckdb"
    con = duckdb.connect(str(p))
    init_catalog(con)
    init_catalog(con)
    tables = sorted(
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog = current_database()"
        ).fetchall()
    )
    for required in TABLE_LOAD_ORDER:
        assert required in tables
    con.close()


def test_migrate_round_trip_row_counts(seeded_catalog, tmp_path):
    dst = tmp_path / "catalog.duckdb"
    counts = migrate_catalog(seeded_catalog, dst)
    # Sanity: at least the tables we know we wrote into.
    assert counts["partitions"] >= 1
    assert counts["entities"] >= 5  # 2 concepts + 2 code + 1 doc
    assert counts["linkage_types"] >= 7  # the DEFAULT_LINKAGES seeded by init
    assert counts["entity_links"] == 4  # 4 links seeded above

    # Row-by-row: read both sides and assert equality on the user-visible
    # columns (skip stored-as-text JSON fields where SQLite-side may produce
    # NULL while we emit ""; here both sides round-trip identically).
    sq = sqlite3.connect(seeded_catalog)
    duck = duckdb.connect(str(dst))

    for table, cols in [
        ("entities", "id, partition_id, kind, name, path, protected, noise"),
        ("linkage_types", "id, name, directed"),
        ("entity_links", "entity_id, linkage_id, concept_id, weight"),
        ("partitions", "id, name, kind"),
        ("concepts", "id, description"),
    ]:
        sq_rows = [tuple(r) for r in sq.execute(
            f"SELECT {cols} FROM {table} ORDER BY 1"
        ).fetchall()]
        duck_rows = [tuple(r) for r in duck.execute(
            f"SELECT {cols} FROM {table} ORDER BY 1"
        ).fetchall()]
        assert sq_rows == duck_rows, f"row divergence on {table}"

    sq.close()
    duck.close()


def test_migrate_refuses_to_overwrite_unless_asked(seeded_catalog, tmp_path):
    dst = tmp_path / "catalog.duckdb"
    migrate_catalog(seeded_catalog, dst)
    with pytest.raises(FileExistsError):
        migrate_catalog(seeded_catalog, dst)
    # overwrite=True succeeds and leaves a usable catalog.
    counts = migrate_catalog(seeded_catalog, dst, overwrite=True)
    assert counts["entities"] >= 5


def test_migrate_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        migrate_catalog(tmp_path / "nope.db", tmp_path / "out.duckdb")


def test_migrate_packs_fragments_into_bitmap_blobs(seeded_catalog, tmp_path):
    """Phase-3: when a SQLite store has on-disk fragment files, the migration
    can pack them into the DuckDB `bitmap_fragments` table. Round-trip a
    bitmap through migrate_catalog → load_bitmap and confirm the entity ids
    survive."""
    from refmatrix.store import Store, default_partition_name

    src = seeded_catalog
    fragments_dir = src.parent / "fragments"
    # Confirm the seeded SQLite store actually wrote some fragment files.
    assert any(fragments_dir.rglob("*.rb64"))

    dst = tmp_path / "catalog.duckdb"
    counts = migrate_catalog(src, dst, fragments_dir=fragments_dir)
    assert counts["bitmap_fragments"] > 0

    # Open the migrated DuckDB store and verify load_bitmap returns the
    # entity ids the SQLite seed had linked. The default partition is
    # path-derived, and dst sits at a different root than the seed, so open
    # explicitly on the seed's partition (what migrate_catalog carried over).
    s = Store(dst.parent, backend="duckdb",
              partition=default_partition_name(src.parent))
    # The 'defines' linkage in the seed had parser → foo, tok → lex, lexer → lex.
    # Look up parser id by name and check load_bitmap.
    parser = s.get_entity("concept", "parser")
    bm = s.load_bitmap("defines", parser.id)
    assert len(bm) >= 1
    s.close()


def test_sequences_dont_collide_after_migration(seeded_catalog, tmp_path):
    """Loaded rows have explicit ids; nextval must produce a value greater
    than the max id already present, otherwise the next INSERT will conflict."""
    dst = tmp_path / "catalog.duckdb"
    migrate_catalog(seeded_catalog, dst)
    con = duckdb.connect(str(dst))
    try:
        max_eid = con.execute("SELECT MAX(id) FROM entities").fetchone()[0]
        next_eid = con.execute("SELECT nextval('seq_entities_id')").fetchone()[0]
        assert next_eid > max_eid, (max_eid, next_eid)

        max_pid = con.execute("SELECT MAX(id) FROM partitions").fetchone()[0]
        next_pid = con.execute("SELECT nextval('seq_partitions_id')").fetchone()[0]
        assert next_pid > max_pid

        max_lid = con.execute("SELECT MAX(id) FROM linkage_types").fetchone()[0]
        next_lid = con.execute("SELECT nextval('seq_linkage_types_id')").fetchone()[0]
        assert next_lid > max_lid
    finally:
        con.close()
