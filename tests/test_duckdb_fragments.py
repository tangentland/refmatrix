"""Phase-3: DuckDB stores bitmap fragments as BLOB rows in
`bitmap_fragments` instead of per-partition files. This locks the
persistence path: round-trip, empty-deletion, multi-partition isolation,
and no stray fragment files on disk for pure-DuckDB stores."""
from __future__ import annotations

import pytest

from refmatrix.store import Store


@pytest.fixture
def duck_store(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    yield s
    s.close()


def _blob_rows(s: Store):
    con = s._connect()
    # DuckDB's LENGTH() isn't overloaded for BLOB; OCTET_LENGTH is the right
    # primitive there. Use it so the inspection helper works as documented.
    return con._duck.execute(
        "SELECT partition_id, linkage, OCTET_LENGTH(blob) AS sz "
        "FROM bitmap_fragments ORDER BY partition_id, linkage"
    ).fetchall()


def test_link_writes_to_bitmap_fragments_blob(duck_store):
    parser = duck_store.add_concept("parser")
    foo = duck_store.upsert_entity(kind="code", name="src/foo.py")
    duck_store.link("defines", parser, foo)
    duck_store.flush_fragments()
    rows = _blob_rows(duck_store)
    assert [(r[0], r[1]) for r in rows] == [(1, "defines")]
    assert rows[0][2] > 0


def test_fragment_persists_across_reopen(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend="duckdb"); s.init()
    parser = s.add_concept("parser")
    foo = s.upsert_entity(kind="code", name="src/foo.py")
    s.link("defines", parser, foo)
    s.close()

    s2 = Store(tmp_path / ".refmatrix", backend="duckdb")
    bm = s2.load_bitmap("defines", parser)
    assert foo in bm
    s2.close()


def test_unlink_to_empty_removes_blob_row(duck_store):
    parser = duck_store.add_concept("parser")
    foo = duck_store.upsert_entity(kind="code", name="src/foo.py")
    duck_store.link("defines", parser, foo)
    duck_store.flush_fragments()
    assert len(_blob_rows(duck_store)) == 1

    duck_store.unlink("defines", parser, foo)
    duck_store.flush_fragments()
    assert _blob_rows(duck_store) == []


def test_fragments_are_partition_scoped(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    root = tmp_path / ".refmatrix"
    sa = Store(root, partition="agent-a", backend="duckdb"); sa.init()
    sb = Store(root, partition="agent-b", backend="duckdb"); sb.init()

    ca = sa.add_concept("parser")
    ea = sa.upsert_entity(kind="code", name="src/foo.py")
    sa.link("mentions", ca, ea)

    cb = sb.add_concept("parser")
    eb = sb.upsert_entity(kind="code", name="src/foo.py")
    sb.link("mentions", cb, eb)

    sa.close()
    sb.close()

    # Two rows in bitmap_fragments — one per partition, both keyed
    # `mentions`. Inspect via a fresh connection so we see committed state.
    inspect = Store(root, partition="agent-a", backend="duckdb")
    rows = _blob_rows(inspect)
    assert sorted((r[0], r[1]) for r in rows) == [
        (sa.partition_id, "mentions"),
        (sb.partition_id, "mentions"),
    ]
    inspect.close()


def test_no_fragment_files_created_on_pure_duckdb(tmp_path, monkeypatch):
    """A pure DuckDB store does not write per-partition fragment files —
    the BLOB rows in `bitmap_fragments` are the only persistence."""
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend="duckdb"); s.init()
    parser = s.add_concept("parser")
    foo = s.upsert_entity(kind="code", name="src/foo.py")
    s.link("defines", parser, foo)
    s.close()
    # init() does still mkdir fragments/<partition>/ for layout parity, but
    # no .rb64 files should appear inside it.
    leaked = list((s.root / "fragments").rglob("*.rb64"))
    assert leaked == [], f"unexpected fragment files: {leaked}"


def test_load_bitmap_uses_persisted_blob(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend="duckdb"); s.init()
    parser = s.add_concept("parser")
    a = s.upsert_entity(kind="code", name="a.py")
    b = s.upsert_entity(kind="code", name="b.py")
    s.link("defines", parser, a)
    s.link("defines", parser, b)
    s.close()

    s2 = Store(tmp_path / ".refmatrix", backend="duckdb")
    out = s2.load_bitmap("defines", parser)
    assert set(out) == {a, b}
    s2.close()
