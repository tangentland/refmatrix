"""Tests for the intuition memory layer (ADR-0001, Phase B).

Covers Store-level CRUD round-trips, sidecar cascade on purge, link
emission to entity_links + bitmap fragments, search, and the DuckDB
CHECK constraint rebuild migration that lets pre-Phase-B catalogs
accept kind='memory' rows.
"""
from __future__ import annotations

import json

import pytest

from refmatrix.store import DEFAULT_LINKAGES, Store


def _store(tmp_path, monkeypatch, backend="sqlite"):
    monkeypatch.setenv("RMX_BACKEND", backend)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


# --- CRUD round-trips ------------------------------------------------------


def test_add_memory_roundtrips_through_get(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory(
        "hello", "this is a test memory body",
        mtype="note", tags=["test", "smoke"],
        metadata={"src": "unit"},
    )
    m = s.get_memory("hello")
    assert m is not None
    assert m["id"] == eid
    assert m["name"] == "hello"
    assert m["mtype"] == "note"
    assert m["tags"] == ["test", "smoke"]
    assert m["metadata"] == {"src": "unit"}
    assert m["content"] == "this is a test memory body"


def test_get_memory_by_id_works(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("by-id", "x")
    by_int = s.get_memory(eid)
    by_str = s.get_memory(str(eid))
    assert by_int is not None and by_int["id"] == eid
    assert by_str is not None and by_str["id"] == eid


def test_get_memory_returns_none_when_kind_mismatch(tmp_path, monkeypatch):
    """An entity of kind='code' with the same name as a memory must not
    masquerade as one. get_memory is kind-gated."""
    s = _store(tmp_path, monkeypatch)
    s.upsert_entity(kind="code", name="conflict")
    assert s.get_memory("conflict") is None


def test_add_memory_idempotent_updates_content(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("the-name", "first body", mtype="observation")
    eid2 = s.add_memory("the-name", "second body", mtype="note", tags=["new"])
    assert eid == eid2
    m = s.get_memory("the-name")
    assert m["content"] == "second body"
    assert m["mtype"] == "note"
    assert m["tags"] == ["new"]


def test_iter_memories_filters_by_mtype(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    s.add_memory("note-a", "a", mtype="note")
    s.add_memory("note-b", "b", mtype="note")
    s.add_memory("obs-a", "c", mtype="observation")
    notes = list(s.iter_memories(mtype="note"))
    obs = list(s.iter_memories(mtype="observation"))
    every = list(s.iter_memories())
    assert {n["name"] for n in notes} == {"note-a", "note-b"}
    assert {n["name"] for n in obs} == {"obs-a"}
    assert len(every) == 3


def test_iter_memories_limit(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    for i in range(5):
        s.add_memory(f"m{i}", f"body {i}")
    assert len(list(s.iter_memories(limit=2))) == 2


# --- search ----------------------------------------------------------------


def test_search_memories_substring_name_and_content(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    s.add_memory("alpha", "the rain in spain")
    s.add_memory("beta", "discussion of caveman mode")
    s.add_memory("gamma", "unrelated")
    hits_alpha = s.search_memories("alpha")
    hits_caveman = s.search_memories("caveman")
    hits_none = s.search_memories("xyzzy_no_match")
    assert {h["name"] for h in hits_alpha} == {"alpha"}
    assert {h["name"] for h in hits_caveman} == {"beta"}
    assert hits_none == []


def test_search_memories_case_insensitive(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    s.add_memory("MixedCase", "MIXED Body content")
    assert {h["name"] for h in s.search_memories("MIXEDCASE")} == {"MixedCase"}
    assert {h["name"] for h in s.search_memories("mixed body")} == {"MixedCase"}


# --- forget / cascade ------------------------------------------------------


def test_forget_memory_drops_entity_and_sidecar(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("forgettable", "body")
    assert s.get_memory("forgettable") is not None
    ok = s.forget_memory("forgettable")
    assert ok is True
    assert s.get_memory("forgettable") is None
    # Sidecar row gone via purge_entity's explicit DELETE.
    con = s._connect()
    mc_count = con.execute(
        "SELECT COUNT(*) FROM memory_content WHERE entity_id=?", (eid,)
    ).fetchone()[0]
    assert mc_count == 0


def test_forget_memory_returns_false_when_missing(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    assert s.forget_memory("never-existed") is False


def test_purge_entity_cascades_to_memory_content(tmp_path, monkeypatch):
    """Direct purge_entity (bypassing forget_memory) must also clear the
    sidecar — purge_entity is the canonical drop path and any caller that
    reaches it should leave memory_content consistent."""
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("cascade-test", "body")
    s.purge_entity(eid)
    con = s._connect()
    mc_count = con.execute(
        "SELECT COUNT(*) FROM memory_content WHERE entity_id=?", (eid,)
    ).fetchone()[0]
    assert mc_count == 0


# --- linkages --------------------------------------------------------------


def test_default_linkages_include_reinforcement_set(tmp_path, monkeypatch):
    """B1: reinforces / contradicts / recalls / informs must be seeded
    on a fresh init (and backfilled into existing stores via the
    INSERT OR IGNORE loop in Store.init)."""
    s = _store(tmp_path, monkeypatch)
    names = {row["name"] for row in s.list_linkages()}
    assert {"reinforces", "contradicts", "recalls", "informs"} <= names


def test_link_memory_to_concept_via_reinforces(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("with-link", "body")
    cid = s.add_concept("cool_idea")
    s.link("reinforces", cid, eid, weight=0.8)
    # The forward index row must exist with the supplied weight.
    con = s._connect()
    row = con.execute(
        "SELECT weight FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE el.entity_id=? AND el.concept_id=? AND lt.name='reinforces'",
        (eid, cid),
    ).fetchone()
    assert row is not None
    assert row["weight"] == pytest.approx(0.8)


# --- DuckDB CHECK rebuild migration ---------------------------------------


def test_duckdb_check_rebuild_accepts_memory_after_open(tmp_path, monkeypatch):
    """Pre-Phase-B catalogs baked `CHECK (kind IN ('doc','code','concept'))`
    into entities at init time. DuckDB 1.5 can't ALTER DROP a CHECK
    constraint, so we rebuild the table on open. After rebuild, a
    memory upsert must succeed and existing rows must still be there
    with the same ids."""
    duckdb = pytest.importorskip("duckdb")
    monkeypatch.setenv("RMX_BACKEND", "duckdb")
    root = tmp_path / ".refmatrix"
    root.mkdir()

    # Forge an old-style catalog: 3-kind CHECK, no memory_content table.
    con = duckdb.connect(str(root / "catalog.duckdb"))
    con.execute("CREATE SEQUENCE seq_entities_id START 1")
    con.execute("CREATE SEQUENCE seq_partitions_id START 1")
    con.execute("CREATE SEQUENCE seq_linkage_types_id START 1")
    con.execute("""
        CREATE TABLE partitions (
            id INTEGER PRIMARY KEY DEFAULT nextval('seq_partitions_id'),
            name TEXT NOT NULL UNIQUE,
            root_path TEXT,
            kind TEXT NOT NULL DEFAULT 'repo'
                CHECK (kind IN ('repo','canon','agent-scratch')),
            created_at DOUBLE NOT NULL,
            meta TEXT
        )
    """)
    con.execute(
        "INSERT INTO partitions(id, name, kind, created_at) VALUES (1, 'local', 'repo', 0)"
    )
    con.execute("""
        CREATE TABLE entities (
            id INTEGER PRIMARY KEY DEFAULT nextval('seq_entities_id'),
            partition_id INTEGER NOT NULL DEFAULT 1,
            kind TEXT NOT NULL CHECK (kind IN ('doc', 'code', 'concept')),
            path TEXT,
            name TEXT NOT NULL,
            tldr TEXT,
            meta TEXT,
            created_at DOUBLE NOT NULL,
            updated_at DOUBLE NOT NULL,
            protected INTEGER NOT NULL DEFAULT 0,
            noise INTEGER NOT NULL DEFAULT 0,
            canonical_name TEXT,
            vectors_updated_at DOUBLE,
            UNIQUE(partition_id, kind, name)
        )
    """)
    con.execute(
        "INSERT INTO entities(id, partition_id, kind, name, created_at, updated_at) "
        "VALUES (100, 1, 'doc', 'pre-existing', 0, 0)"
    )
    con.execute(
        "INSERT INTO entities(id, partition_id, kind, name, created_at, updated_at) "
        "VALUES (101, 1, 'code', 'also-existing', 0, 0)"
    )
    # Confirm the OLD check actually rejects 'memory'.
    with pytest.raises(Exception):
        con.execute(
            "INSERT INTO entities(id, partition_id, kind, name, created_at, updated_at) "
            "VALUES (102, 1, 'memory', 'will-fail', 0, 0)"
        )
    con.close()

    # Open through Store. Migration runs in _migrate_entities_kind_check_if_needed.
    s = Store(root)
    s.init()

    # Pre-existing rows survived with identical ids.
    surviving = {
        r["name"]: r["id"]
        for r in s._connect().execute(
            "SELECT id, name FROM entities ORDER BY id"
        ).fetchall()
    }
    assert surviving["pre-existing"] == 100
    assert surviving["also-existing"] == 101

    # A memory row now lands without raising.
    eid = s.add_memory("post-migration-memory", "body")
    m = s.get_memory("post-migration-memory")
    assert m is not None
    assert m["id"] == eid
    s.close()


def test_memory_partition_default_resolves_to_intuition(tmp_path, monkeypatch):
    """ADR-0001 B4: memory commands default to partition='intuition'
    when no -p / RMX_PARTITION is set, regardless of cwd or any
    `.refmatrix/partition` file alongside. _apply_memory_partition_default
    is the single source of truth — exercise it directly so the
    behavior is asserted at the unit level too."""
    from refmatrix import cli as cli_mod
    # No env var, no override.
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    monkeypatch.setattr(cli_mod, "_partition_override", None, raising=False)
    cli_mod._apply_memory_partition_default()
    assert cli_mod._partition_override == "intuition"
    # Reset and verify explicit override wins.
    monkeypatch.setattr(cli_mod, "_partition_override", "myproject", raising=False)
    cli_mod._apply_memory_partition_default()
    assert cli_mod._partition_override == "myproject"
    # Reset and verify env var wins.
    monkeypatch.setattr(cli_mod, "_partition_override", None, raising=False)
    monkeypatch.setenv("RMX_PARTITION", "from-env")
    cli_mod._apply_memory_partition_default()
    assert cli_mod._partition_override is None  # untouched — env path takes over


def test_recent_memories_orders_newest_first(tmp_path, monkeypatch):
    """Phase C2: `Store.recent_memories` powers `rmx memory recall --recent`.
    Returns by `entities.created_at DESC`."""
    import time as _t
    s = _store(tmp_path, monkeypatch)
    e_old = s.add_memory("old", "x")
    e_new = s.add_memory("new", "y")
    con = s._connect()
    # Backdate `old` so the order is deterministic regardless of insertion
    # latency.
    con.execute(
        "UPDATE entities SET created_at=? WHERE id=?",
        (_t.time() - 3600.0, e_old),
    )
    con.commit()
    rows = s.recent_memories(limit=10)
    assert [r["name"] for r in rows] == ["new", "old"]


def test_recent_memories_since_filter_drops_old(tmp_path, monkeypatch):
    """`since_seconds` argument bounds the window — old rows fall off."""
    import time as _t
    s = _store(tmp_path, monkeypatch)
    e_recent = s.add_memory("recent", "x")
    e_stale = s.add_memory("stale", "y")
    con = s._connect()
    con.execute(
        "UPDATE entities SET created_at=? WHERE id=?",
        (_t.time() - 86400.0 * 8, e_stale),
    )
    con.commit()
    rows = s.recent_memories(since_seconds=86400.0 * 7, limit=10)
    assert {r["name"] for r in rows} == {"recent"}


def test_duckdb_kind_check_migration_idempotent(tmp_path, monkeypatch):
    """Opening a freshly-initialized DuckDB store twice in a row must
    leave the schema in the same state — the migration helper should
    short-circuit when the CHECK already permits 'memory'."""
    pytest.importorskip("duckdb")
    monkeypatch.setenv("RMX_BACKEND", "duckdb")
    root = tmp_path / ".refmatrix"

    s1 = Store(root)
    s1.init()
    s1.add_memory("first", "body")
    s1.close()

    s2 = Store(root)
    s2.init()
    s2.add_memory("second", "body")
    assert {m["name"] for m in s2.iter_memories()} == {"first", "second"}
    s2.close()
