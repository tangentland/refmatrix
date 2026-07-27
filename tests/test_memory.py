"""Tests for the intuition memory layer (ADR-0001, Phase B).

Covers Store-level CRUD round-trips, sidecar cascade on purge, link
emission to entity_links + bitmap fragments, search, and the DuckDB
CHECK constraint rebuild migration that lets pre-Phase-B catalogs
accept kind='memory' rows.
"""
from __future__ import annotations

import json

import pytest

from refmatrix.store import DEFAULT_LINKAGES, Store, default_partition_name


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
        "INSERT INTO partitions(id, name, kind, created_at) VALUES (1, ?, 'repo', 0)",
        [default_partition_name(root)],
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


def test_memory_partition_default_resolves_to_project_scoped(
    tmp_path, monkeypatch,
):
    """Memory commands default to the project partition when no -p /
    RMX_PARTITION is set. Pre-0.5.0 the default was `memory-<project>`;
    that split made cross-partition wikilinks unresolvable so the
    consolidated default is just `<project>`. Legacy auto-detect
    still routes to `memory-<project>` when that row exists, so a
    pre-merge host stays correct — but the bare default for a fresh
    tree is the project name."""
    from refmatrix import cli as cli_mod
    # Point _root() at tmp_path/.refmatrix so the project name is
    # deterministic (tmp_path basename).
    monkeypatch.setattr(cli_mod, "_root",
                        lambda: tmp_path / ".refmatrix", raising=False)
    # No env var, no override.
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    monkeypatch.setattr(cli_mod, "_partition_override", None, raising=False)
    # Make sure the legacy-detect cache doesn't carry state from a
    # prior test in this module.
    if hasattr(cli_mod._legacy_memory_partition_exists, "_cache"):
        cli_mod._legacy_memory_partition_exists._cache = {}
    # Daemon down + no legacy partition row → project default.
    from refmatrix import daemon as daemon_mod
    monkeypatch.setattr(daemon_mod, "ping", lambda *a, **kw: False)
    monkeypatch.setattr(
        cli_mod, "_reader_store", lambda: None, raising=False,
    )
    monkeypatch.setattr(
        cli_mod, "_store",
        lambda: type("S", (), {
            "_connect": lambda self: type("C", (), {
                "execute": lambda *a, **kw: type("R", (), {
                    "fetchone": lambda self: None
                })(),
            })(),
            "close": lambda self: None,
        })(),
        raising=False,
    )
    cli_mod._apply_memory_partition_default()
    assert cli_mod._partition_override == tmp_path.name
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


def test_ingest_gmd_auto_resume_skips_unchanged(tmp_path, monkeypatch):
    """A second ingest with the same file content must skip both passes.
    Verified by spying on add_memory: it's called on the first run,
    NOT on the second."""
    from refmatrix.ingest_gmd import ingest_gmd_paths

    s = _store(tmp_path, monkeypatch)
    doc = tmp_path / "doc.md"
    doc.write_text(
        '---\ngmd: "0.1"\nid: resume-doc\ntitle: "Resume Doc"\ntags: [smoke]\n'
        'metadata:\n  type: feedback\n---\n\n# Body {#root}\n\nfirst content\n',
        encoding="utf-8",
    )
    with s.with_partition("memory-test"):
        ingest_gmd_paths(s, [doc], as_memory=True)
        # Re-run on unchanged file — should be a no-op for writes.
        call_log: list[str] = []
        orig_add_memory = s.add_memory
        def _tracked_add_memory(*a, **kw):
            call_log.append("add_memory")
            return orig_add_memory(*a, **kw)
        s.add_memory = _tracked_add_memory  # type: ignore[assignment]
        try:
            stats = ingest_gmd_paths(s, [doc], as_memory=True)
        finally:
            s.add_memory = orig_add_memory  # type: ignore[assignment]
    assert call_log == []  # resume must skip add_memory
    assert stats.docs == 1


def test_ingest_gmd_auto_resume_runs_when_content_changed(tmp_path, monkeypatch):
    """A second ingest with different file content must NOT skip — the
    hash mismatch forces full re-processing so the new body lands."""
    from refmatrix.ingest_gmd import ingest_gmd_paths

    s = _store(tmp_path, monkeypatch)
    doc = tmp_path / "doc.md"
    doc.write_text(
        '---\ngmd: "0.1"\nid: changing-doc\ntitle: "Changing"\ntags: []\n'
        'metadata:\n  type: feedback\n---\n\n# T {#root}\n\noriginal\n',
        encoding="utf-8",
    )
    with s.with_partition("memory-test"):
        ingest_gmd_paths(s, [doc], as_memory=True)
        doc.write_text(
            '---\ngmd: "0.1"\nid: changing-doc\ntitle: "Changing"\ntags: []\n'
            'metadata:\n  type: feedback\n---\n\n# T {#root}\n\nupdated\n',
            encoding="utf-8",
        )
        ingest_gmd_paths(s, [doc], as_memory=True)
        m = s.get_memory("changing-doc")
    assert m is not None
    assert "updated" in (m["content"] or "")


def test_prestage_hashes_marks_existing_as_done(tmp_path, monkeypatch):
    """prestage_hashes stamps the current file hash onto matching
    entities so the next ingest treats them as already done."""
    from refmatrix.ingest_gmd import (
        ingest_gmd_paths, prestage_hashes, _existing_hash_for,
        _doc_content_hash,
    )

    s = _store(tmp_path, monkeypatch)
    doc = tmp_path / "p.md"
    doc.write_text(
        '---\ngmd: "0.1"\nid: pre-doc\ntitle: "Pre"\ntags: []\n'
        'metadata:\n  type: feedback\n---\n\n# T {#root}\n\nbody\n',
        encoding="utf-8",
    )
    with s.with_partition("memory-test"):
        ingest_gmd_paths(s, [doc], as_memory=True)
        # Clear the hash so the entity looks pre-resume.
        eid = s.get_memory("pre-doc")["id"]
        s._connect().execute(
            "UPDATE entities SET meta=? WHERE id=?",
            ('{"title":"Pre"}', eid),
        )
        s._connect().commit()
        assert _existing_hash_for(s, "pre-doc", ("memory",)) is None
        report = prestage_hashes(s, [doc])
        assert report["written"] == 1
        assert _existing_hash_for(s, "pre-doc", ("memory",)) == _doc_content_hash(doc)


def test_ingest_gmd_as_memory_honors_with_partition(tmp_path, monkeypatch):
    """Regression: `ingest-gmd --as-memory` must land memory rows in the
    caller's partition (e.g. `memory-<project>`), not the store's bound
    partition. Before the fix, daemon `_op_ingest_gmd` ignored `args['partition']`
    so 105 viascope memories were orphaned in the code-sync partition and
    invisible to `rmx memory list/recall`."""
    from refmatrix.ingest_gmd import ingest_gmd_paths

    s = _store(tmp_path, monkeypatch)
    doc = tmp_path / "doc.md"
    doc.write_text(
        '---\ngmd: "0.1"\nid: hello-doc\ntitle: "Hello Doc"\ntags: [smoke]\n'
        'metadata:\n  type: feedback\n---\n\n# Hello {#root}\n\nbody text\n',
        encoding="utf-8",
    )
    target_partition = "memory-target"
    with s.with_partition(target_partition):
        ingest_gmd_paths(s, [doc], as_memory=True)
    with s.with_partition(target_partition):
        names = [m["name"] for m in s.iter_memories()]
    assert names == ["hello-doc"]
    # Default partition must NOT see the memory — proves the routing.
    assert [m["name"] for m in s.iter_memories()] == []


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


# --- embed self-heal: partition-aware incremental guard --------------------

def test_pending_embeddings_requeues_on_partition_mismatch(tmp_path, monkeypatch):
    import time
    s = _store(tmp_path, monkeypatch)
    eid = s.add_memory("m1", "body", mtype="note")
    con = s._connect()
    # Simulate a row embedded (fresh timestamp) but vectors recorded against a
    # DIFFERENT partition than this store's active one — the mis-partition bug.
    con.execute(
        "UPDATE entities SET vectors_updated_at=?, vectors_partition=? WHERE id=?",
        (time.time() + 100, "some-other-partition", eid))
    con.commit()
    pend = [r[0] for r in s.pending_embeddings(kinds=["memory"])]
    assert eid in pend, "partition mismatch must re-queue (self-heal)"

    # Same partition name → current, NOT re-queued.
    con.execute("UPDATE entities SET vectors_partition=? WHERE id=?",
                (s.partition_name, eid))
    con.commit()
    assert eid not in [r[0] for r in s.pending_embeddings(kinds=["memory"])]

    # Legacy NULL vectors_partition + fresh timestamp → trusted (no mass
    # re-embed on migration).
    con.execute("UPDATE entities SET vectors_partition=NULL WHERE id=?", (eid,))
    con.commit()
    assert eid not in [r[0] for r in s.pending_embeddings(kinds=["memory"])]

