"""Phase-1 parity: DuckDB sqlite_scanner view returns the same rows as the
SQLite catalog for the read paths the Store exercises today. Locks behavior
before phase 2 swaps reads to DuckDB."""
from __future__ import annotations

import pytest

from refmatrix.duckdb_view import DuckCatalogView
from refmatrix.store import Store


@pytest.fixture
def seeded_store(tmp_path):
    # Parity tests target the SQLite-on-disk catalog explicitly — the
    # DuckCatalogView mounts catalog.db via sqlite_scanner. Pinning the
    # backend keeps the test meaningful when the suite is run with
    # `RMX_BACKEND=duckdb` overall.
    s = Store(tmp_path / ".refmatrix", backend="sqlite")
    s.init()
    parser = s.add_concept("parser", description="parses input")
    tokenizer = s.add_concept("tokenizer")
    lexer = s.add_concept("lexer")
    foo = s.upsert_entity(kind="code", name="src/foo.py", path="src/foo.py")
    lex = s.upsert_entity(kind="code", name="src/lex.py", path="src/lex.py",
                          tldr="tokenizer impl")
    readme = s.upsert_entity(kind="doc", name="README.md", path="README.md",
                             protected=True)
    s.link("defines", parser, foo, weight=0.9)
    s.link("defines", tokenizer, lex)
    s.link("defines", lexer, lex)
    s.link("mentions", parser, readme)
    s.link("related_to", parser, lex)
    # Flush so the view sees committed state.
    s.close()
    yield tmp_path / ".refmatrix" / "catalog.db"


def _both(seeded_store):
    """Return (sqlite_rows_fn, duck_rows_fn) bound to the same db."""
    import sqlite3

    sq = sqlite3.connect(seeded_store)
    sq.row_factory = sqlite3.Row
    duck = DuckCatalogView(seeded_store)

    def sql(q, params=()):
        return [tuple(r) for r in sq.execute(q, params).fetchall()]

    def dk(q, params=()):
        return [tuple(r) for r in duck.fetchall(q, params)]

    return sql, dk, sq, duck


def test_table_inventory_matches(seeded_store):
    sql, dk, sq, duck = _both(seeded_store)
    sqlite_tables = sorted(
        r[0]
        for r in sq.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )
    duck_tables = sorted(duck.tables())
    assert set(sqlite_tables) <= set(duck_tables), (
        f"sqlite has tables duckdb view doesn't: "
        f"{set(sqlite_tables) - set(duck_tables)}"
    )
    duck.close()
    sq.close()


@pytest.mark.parametrize("query", [
    "SELECT id, kind, name, path, protected, noise FROM entities ORDER BY id",
    "SELECT id, name, directed FROM linkage_types ORDER BY id",
    "SELECT entity_id, linkage_id, concept_id, weight FROM entity_links "
    "ORDER BY entity_id, linkage_id, concept_id",
    "SELECT id, name, kind FROM partitions ORDER BY id",
    "SELECT id, description FROM concepts ORDER BY id",
    "SELECT COUNT(*) FROM entities",
    "SELECT COUNT(*) FROM entity_links",
    "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind",
])
def test_select_parity(seeded_store, query):
    sql, dk, sq, duck = _both(seeded_store)
    try:
        assert sql(query) == dk(query), f"divergent: {query}"
    finally:
        duck.close()
        sq.close()


def test_join_parity_entity_links_to_entities(seeded_store):
    """The query path joins entity_links → entities for resolve. Lock parity."""
    sql, dk, sq, duck = _both(seeded_store)
    q = (
        "SELECT el.entity_id, el.concept_id, el.linkage_id, e.name AS e_name, "
        "       c.name AS c_name, lt.name AS lk_name "
        "FROM entity_links el "
        "JOIN entities e ON e.id = el.entity_id "
        "JOIN entities c ON c.id = el.concept_id "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "ORDER BY el.entity_id, el.linkage_id, el.concept_id"
    )
    try:
        assert sql(q) == dk(q)
    finally:
        duck.close()
        sq.close()


def test_parametrized_lookup_parity(seeded_store):
    sql, dk, sq, duck = _both(seeded_store)
    try:
        # SQLite uses '?' params; DuckDB supports the same.
        q = "SELECT id, name FROM entities WHERE kind = ? ORDER BY id"
        assert sql(q, ("code",)) == dk(q, ("code",))
        assert sql(q, ("doc",)) == dk(q, ("doc",))
    finally:
        duck.close()
        sq.close()
