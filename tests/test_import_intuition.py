"""Phase C1: rmx memory import-sqlite tests.

Forges a small intuition `.memory.db` (real SQLite, real intuition
schema), runs the importer, asserts row counts and that the
mappings are exact:

- observations  -> entities(kind='memory') + memory_content sidecar
- created_at TEXT iso  -> entities.created_at REAL epoch
- observation_concepts.score -> mentions weight on entity_links
- concept_relations -> typed linkage auto-registered, weight preserved
- concept_aliases / concepts.aliases -> additional concept entities
                                         joined via same_as
- idempotent: re-running leaves counts unchanged

A pre-Phase-B catalog rebuild edge case is already covered by
`tests/test_memory.py::test_duckdb_check_rebuild_accepts_memory_after_open`
so we don't repeat it here.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from refmatrix.import_intuition import import_intuition_db
from refmatrix.store import Store


def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def _forge_intuition_db(path: Path) -> None:
    """Build a minimal intuition .memory.db with the exact schema the
    importer reads. Two observations, three concepts (one with an alias),
    two observation_concept links with distinct scores, and one
    concept_relation with a non-default linkage type."""
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            project TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'observation',
            tags TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE concepts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'unknown',
            description TEXT DEFAULT NULL,
            aliases TEXT NOT NULL DEFAULT '[]',
            parent_id INTEGER DEFAULT NULL,
            properties TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE observation_concepts (
            observation_id INTEGER NOT NULL,
            concept_id INTEGER NOT NULL,
            score REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (observation_id, concept_id)
        );
        CREATE TABLE concept_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_concept_id INTEGER NOT NULL,
            target_concept_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL DEFAULT 'relates-to',
            weight REAL NOT NULL DEFAULT 1.0,
            context TEXT DEFAULT NULL,
            source_origin TEXT NOT NULL DEFAULT 'llm',
            created_at TEXT NOT NULL
        );
        """
    )
    con.execute(
        "INSERT INTO observations(id, content, project, type, tags, "
        "metadata, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (1, "first observation", "vs", "decision",
         json.dumps(["a", "b"]), json.dumps({"src": "manual"}),
         "2026-01-15T12:00:00+00:00", "2026-01-15T12:00:00+00:00"),
    )
    con.execute(
        "INSERT INTO observations(id, content, project, type, tags, "
        "metadata, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (2, "second observation", "vs", "observation",
         json.dumps([]), json.dumps({}),
         "2026-02-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"),
    )
    con.execute(
        "INSERT INTO concepts(id, name, created_at, category, aliases) "
        "VALUES (?,?,?,?,?)",
        (10, "json_parser", "2026-01-01T00:00:00+00:00", "type",
         json.dumps(["JSONParser", "json-parser"])),
    )
    con.execute(
        "INSERT INTO concepts(id, name, created_at, category, aliases) "
        "VALUES (?,?,?,?,?)",
        (11, "token_stream", "2026-01-01T00:00:00+00:00", "type",
         json.dumps([])),
    )
    con.execute(
        "INSERT INTO concepts(id, name, created_at, category, aliases) "
        "VALUES (?,?,?,?,?)",
        (12, "lexer", "2026-01-01T00:00:00+00:00", "type", "[]"),
    )
    # obs 1 mentions concept 10 (high score) + concept 11 (low score)
    con.execute(
        "INSERT INTO observation_concepts VALUES (?,?,?)", (1, 10, 0.9),
    )
    con.execute(
        "INSERT INTO observation_concepts VALUES (?,?,?)", (1, 11, 0.3),
    )
    # obs 2 mentions concept 12
    con.execute(
        "INSERT INTO observation_concepts VALUES (?,?,?)", (2, 12, 0.7),
    )
    # concept relations: token_stream produces_for lexer
    con.execute(
        "INSERT INTO concept_relations(source_concept_id, target_concept_id, "
        "relation_type, weight, created_at) VALUES (?,?,?,?,?)",
        (11, 12, "produces_for", 0.85, "2026-01-01T00:00:00+00:00"),
    )
    con.commit()
    con.close()


# --- basic mapping --------------------------------------------------------


def test_import_creates_memory_per_observation(tmp_path, monkeypatch):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    s = _store(tmp_path, monkeypatch)

    stats = import_intuition_db(s, src)

    assert stats.memories_added == 2
    assert stats.memories_skipped == 0
    names = {m["name"] for m in s.iter_memories()}
    assert f"imp-intuition-1" in names
    assert f"imp-intuition-2" in names


def test_import_preserves_content_type_tags_metadata(tmp_path, monkeypatch):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    s = _store(tmp_path, monkeypatch)
    import_intuition_db(s, src)

    m = s.get_memory("imp-intuition-1")
    assert m["content"] == "first observation"
    assert m["mtype"] == "decision"
    assert m["tags"] == ["a", "b"]
    assert m["metadata"]["src"] == "manual"
    # importer stamps provenance into metadata so we can trace back.
    assert m["metadata"]["intuition_id"] == 1
    assert "intuition_source" in m["metadata"]


def test_import_converts_iso_created_at_to_epoch(tmp_path, monkeypatch):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    s = _store(tmp_path, monkeypatch)
    import_intuition_db(s, src)

    m = s.get_memory("imp-intuition-1")
    expected = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    row = s._connect().execute(
        "SELECT created_at FROM entities WHERE id=?", (m["id"],)
    ).fetchone()
    assert row["created_at"] == pytest.approx(expected, abs=1.0)


# --- linkage mapping ------------------------------------------------------


def test_observation_concepts_become_mentions_with_score_weight(
    tmp_path, monkeypatch,
):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    s = _store(tmp_path, monkeypatch)
    import_intuition_db(s, src)

    m1 = s.get_memory("imp-intuition-1")
    cid = s.resolve_concept_ids("json_parser", strict=False)[0]
    weight = s.get_weight("mentions", cid, m1["id"])
    assert weight == pytest.approx(0.9, abs=1e-6)


def test_concept_relations_become_typed_linkage(tmp_path, monkeypatch):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    s = _store(tmp_path, monkeypatch)
    stats = import_intuition_db(s, src)

    # produces_for is a non-default linkage; importer should auto-register it.
    assert stats.linkage_types_registered == 1
    names = {lk["name"] for lk in s.list_linkages()}
    assert "produces_for" in names

    src_cid = s.resolve_concept_ids("token_stream", strict=False)[0]
    tgt_cid = s.resolve_concept_ids("lexer", strict=False)[0]
    # Direction: entity_links.entity_id=source, concept_id=target.
    w = s.get_weight("produces_for", tgt_cid, src_cid)
    assert w == pytest.approx(0.85, abs=1e-6)


def test_aliases_create_same_as_links(tmp_path, monkeypatch):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    s = _store(tmp_path, monkeypatch)
    stats = import_intuition_db(s, src)

    # concept 10 has 2 user-supplied aliases. add_concept's own variant
    # expansion may or may not include them depending on canonicalization,
    # so we just assert at least one user alias was linked.
    assert stats.aliases_linked >= 1
    # Resolving by an alias finds the canonical concept too.
    cids_by_alias = s.resolve_concept_ids("JSONParser", strict=False)
    cids_by_canonical = s.resolve_concept_ids("json_parser", strict=False)
    assert set(cids_by_alias) & set(cids_by_canonical)


# --- idempotence ----------------------------------------------------------


def test_reimport_skips_existing_memories(tmp_path, monkeypatch):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    s = _store(tmp_path, monkeypatch)

    first = import_intuition_db(s, src)
    second = import_intuition_db(s, src)
    assert first.memories_added == 2
    assert second.memories_added == 0
    assert second.memories_skipped == 2
    # Total memories in the store unchanged.
    assert len(list(s.iter_memories())) == 2


# --- error handling -------------------------------------------------------


def test_strict_mode_re_raises_first_error(tmp_path, monkeypatch):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    # Corrupt the metadata JSON for one row so json.loads explodes — only
    # observable in strict mode.
    con = sqlite3.connect(src)
    con.execute(
        "UPDATE observations SET tags='not-json{{' WHERE id=1"
    )
    con.commit()
    con.close()
    s = _store(tmp_path, monkeypatch)

    with pytest.raises(Exception):
        import_intuition_db(s, src, strict=True)


def test_archive_source_moves_family_to_intuition_migrated(tmp_path):
    src = tmp_path / ".memory.db"
    src.write_bytes(b"x")
    (tmp_path / ".memory.db-wal").write_bytes(b"x")
    (tmp_path / ".memory.db.concepts.faiss").write_bytes(b"x")
    (tmp_path / ".memory.db.obs.faiss").write_bytes(b"x")
    (tmp_path / ".memory.db.txlog.jsonl").write_bytes(b"x")
    from refmatrix.import_intuition import archive_source

    moved = archive_source(src)
    dest = tmp_path / ".intuition-migrated"
    assert dest.is_dir()
    moved_names = sorted(p.name for p in moved)
    assert ".memory.db" in moved_names
    assert ".memory.db-wal" in moved_names
    assert ".memory.db.concepts.faiss" in moved_names
    assert ".memory.db.obs.faiss" in moved_names
    assert ".memory.db.txlog.jsonl" in moved_names
    # Originals gone.
    assert not src.exists()
    assert not (tmp_path / ".memory.db.concepts.faiss").exists()


def test_archive_source_avoids_overwriting_prior_archive(tmp_path):
    src = tmp_path / ".memory.db"
    src.write_bytes(b"first")
    from refmatrix.import_intuition import archive_source
    archive_source(src)
    # Second time around, recreate the source and archive again.
    src.write_bytes(b"second")
    moved = archive_source(src)
    dest = tmp_path / ".intuition-migrated"
    files = sorted(p.name for p in dest.iterdir())
    # First archived as .memory.db, second collides → .memory.db.1
    assert ".memory.db" in files
    assert ".memory.db.1" in files
    # The most recent move went to the suffixed path.
    assert any(p.name == ".memory.db.1" for p in moved)


def test_nonstrict_mode_records_error_and_continues(tmp_path, monkeypatch):
    src = tmp_path / "intuition.db"
    _forge_intuition_db(src)
    con = sqlite3.connect(src)
    con.execute(
        "UPDATE observations SET tags='not-json{{' WHERE id=1"
    )
    con.commit()
    con.close()
    s = _store(tmp_path, monkeypatch)

    stats = import_intuition_db(s, src, strict=False)
    assert stats.memories_added == 1  # the other obs still landed
    assert any("observation id=1" in e for e in stats.errors)
