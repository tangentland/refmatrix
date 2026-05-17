"""Phase-1.5: with RMX_READ_VIA_DUCKDB=1, the hot Store read methods route
through DuckCatalogView and return the same shapes/values as the SQLite path.
Locks the wiring so we notice if a read site silently falls back."""
from __future__ import annotations

import pytest

from refmatrix.store import Store


def _seed(s: Store) -> dict:
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
    return {"parser": parser, "tok": tok, "foo": foo, "lex": lex,
            "readme": readme}


def _open(tmp_path, *, duck: bool, monkeypatch) -> Store:
    if duck:
        monkeypatch.setenv("RMX_READ_VIA_DUCKDB", "1")
    else:
        monkeypatch.delenv("RMX_READ_VIA_DUCKDB", raising=False)
    # Pin the backend: this test is about the SQLite→DuckCatalogView read
    # routing toggle, which only makes sense against a SQLite catalog.
    s = Store(tmp_path / ".refmatrix", backend="sqlite")
    s.init()
    return s


def _snapshot(s: Store, ids: dict) -> dict:
    """Pull every metric the hot read methods produce, so we can compare
    SQLite-mode and DuckDB-mode snapshots structurally."""
    e_by_id = s.get_entity_by_id(ids["foo"])
    return {
        "list_linkages": [(lk["name"], lk["directed"]) for lk in s.list_linkages()],
        "linkage_id_defines": s.get_linkage_id("defines"),
        "linkage_id_mentions": s.get_linkage_id("mentions"),
        "get_entity_concept": (
            (lambda e: (e.id, e.kind, e.name, e.protected, e.noise))(
                s.get_entity("concept", "parser")
            )
        ),
        "get_entity_doc_protected": s.get_entity("doc", "README.md").protected,
        "get_entity_by_id_foo": (
            e_by_id.id, e_by_id.kind, e_by_id.name, e_by_id.path,
            e_by_id.tldr, e_by_id.meta, e_by_id.protected, e_by_id.noise,
        ),
        "iter_entities_all": sorted(
            (e.kind, e.name, e.protected) for e in s.iter_entities()
        ),
        "iter_entities_code": sorted(e.name for e in s.iter_entities(kind="code")),
        "name_of_parser": s._name_of(ids["parser"]),
        "missing_entity": s.get_entity("concept", "nonexistent"),
    }


def test_dual_mode_snapshot_matches(tmp_path, monkeypatch):
    """Run the seed + snapshot under both backends; snapshots must match."""
    sqlite_dir = tmp_path / "sqlite"
    duck_dir = tmp_path / "duck"
    sqlite_dir.mkdir(); duck_dir.mkdir()

    s_sql = _open(sqlite_dir, duck=False, monkeypatch=monkeypatch)
    ids_sql = _seed(s_sql)
    snap_sql = _snapshot(s_sql, ids_sql)
    assert s_sql._read_via_duckdb is False
    s_sql.close()

    s_duck = _open(duck_dir, duck=True, monkeypatch=monkeypatch)
    ids_duck = _seed(s_duck)
    snap_duck = _snapshot(s_duck, ids_duck)
    assert s_duck._read_via_duckdb is True
    assert s_duck._duck_view is not None, (
        "expected DuckCatalogView to be lazily constructed by the first read"
    )
    s_duck.close()

    # ids are stable across runs because both stores start fresh from a
    # clean .refmatrix/ and the seed order is identical.
    assert ids_sql == ids_duck
    assert snap_sql == snap_duck


def test_get_linkage_id_raises_under_duck(tmp_path, monkeypatch):
    """KeyError still propagates correctly when the linkage isn't found —
    the read shim must not swallow `None` rows into a stub id."""
    s = _open(tmp_path, duck=True, monkeypatch=monkeypatch)
    try:
        with pytest.raises(KeyError):
            s.get_linkage_id("not_a_real_linkage_type")
    finally:
        s.close()


def test_close_releases_duck_view(tmp_path, monkeypatch):
    s = _open(tmp_path, duck=True, monkeypatch=monkeypatch)
    s.add_concept("c1")  # forces _connect; doesn't trigger read path
    list(s.iter_entities())  # forces read path -> DuckCatalogView constructed
    assert s._duck_view is not None
    s.close()
    assert s._duck_view is None
    assert s._read_conn is None
