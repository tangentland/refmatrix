"""Tests for the partition dimension."""
from __future__ import annotations

import sqlite3

import pytest

from refmatrix.store import DEFAULT_PARTITION, Store


# --- fresh init ------------------------------------------------------------


def test_fresh_init_creates_default_partition(tmp_path):
    """A brand-new Store starts with a single 'local' partition (id=1) and
    fragments live under fragments/local/. Existing read/write APIs work
    unchanged because the default partition is implicit."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    assert s.partition_name == DEFAULT_PARTITION
    assert s.partition_id == 1

    # Default partition row materialized.
    rows = s._connect().execute(
        "SELECT id, name FROM partitions ORDER BY id"
    ).fetchall()
    assert [(r["id"], r["name"]) for r in rows] == [(1, DEFAULT_PARTITION)]

    # Roundtrip a basic write/read.
    cid = s.add_concept("parser")
    eid = s.upsert_entity(kind="code", name="src/foo.py")
    s.link("mentions", cid, eid)
    s.close()

    # Fragment file landed under the per-partition subdir.
    assert (s.root / "fragments" / DEFAULT_PARTITION / "mentions.rb64").exists()


# --- legacy migration ------------------------------------------------------


def test_legacy_catalog_migrates_into_default_partition(tmp_path):
    """Forge a pre-partition catalog: an entities/tracked_files/saved_queries
    schema without partition_id, plus a loose fragments/<linkage>.rb64. After
    opening the Store, the rebuilt schema should carry partition_id columns
    (all rows backfilled to id=1) and the loose fragment should have moved
    into fragments/local/."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    (root / "fragments").mkdir()

    # Build the *old* schema directly so we exercise the migration. This
    # mirrors the on-disk layout produced by a refmatrix from before the
    # partition split: no partitions table, UNIQUE(kind,name), tracked_files
    # PK on path alone, saved_queries PK on name alone.
    con = sqlite3.connect(root / "catalog.db")
    con.executescript(
        """
        CREATE TABLE entities (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kind        TEXT NOT NULL CHECK (kind IN ('doc','code','concept')),
            path        TEXT,
            name        TEXT NOT NULL,
            tldr        TEXT,
            meta        TEXT,
            created_at  REAL NOT NULL,
            updated_at  REAL NOT NULL,
            UNIQUE(kind, name)
        );
        CREATE TABLE concepts (
            id INTEGER PRIMARY KEY,
            description TEXT,
            FOREIGN KEY (id) REFERENCES entities(id) ON DELETE CASCADE
        );
        CREATE TABLE linkage_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            directed INTEGER NOT NULL DEFAULT 1,
            inverse_of INTEGER,
            description TEXT
        );
        CREATE TABLE saved_queries (
            name TEXT PRIMARY KEY,
            body TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE TABLE tracked_files (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL,
            last_synced REAL NOT NULL
        );
        CREATE TABLE entity_links (
            entity_id INTEGER NOT NULL,
            linkage_id INTEGER NOT NULL,
            concept_id INTEGER NOT NULL,
            weight REAL,
            PRIMARY KEY (entity_id, linkage_id, concept_id)
        );
        CREATE TABLE linkage_evidence (
            entity_id INTEGER NOT NULL,
            linkage_id INTEGER NOT NULL,
            concept_id INTEGER NOT NULL,
            file TEXT, line INTEGER, span_end INTEGER, detail TEXT
        );
        INSERT INTO entities(kind, name, created_at, updated_at)
          VALUES ('concept', 'parser', 1.0, 1.0);
        INSERT INTO entities(kind, name, created_at, updated_at)
          VALUES ('code', 'src/foo.py', 1.0, 1.0);
        INSERT INTO tracked_files(path, mtime, last_synced)
          VALUES ('/repo/src/foo.py', 1.0, 1.0);
        INSERT INTO saved_queries(name, body, created_at)
          VALUES ('q1', 'mentions:parser', 1.0);
        """
    )
    con.commit()
    con.close()

    # Drop a loose fragment to verify the fragment migration moves it into
    # fragments/local/ on first open.
    loose = root / "fragments" / "mentions.rb64"
    loose.write_bytes(b"\x00\x00\x00\x00")  # contents irrelevant; we test the move

    # Open the Store — migration runs in _connect().
    s = Store(root)
    s._connect()

    # partition_id columns now present everywhere.
    assert "partition_id" in {r[1] for r in s._connect().execute(
        "PRAGMA table_info(entities)"
    )}
    assert "partition_id" in {r[1] for r in s._connect().execute(
        "PRAGMA table_info(tracked_files)"
    )}
    assert "partition_id" in {r[1] for r in s._connect().execute(
        "PRAGMA table_info(saved_queries)"
    )}

    # All pre-existing rows backfilled to partition 1.
    assert s._connect().execute(
        "SELECT COUNT(*) FROM entities WHERE partition_id != 1"
    ).fetchone()[0] == 0
    assert s._connect().execute(
        "SELECT COUNT(*) FROM tracked_files WHERE partition_id = 1"
    ).fetchone()[0] == 1
    assert s._connect().execute(
        "SELECT COUNT(*) FROM saved_queries WHERE partition_id = 1"
    ).fetchone()[0] == 1

    # Loose fragment moved to per-partition subdir.
    assert not loose.exists()
    assert (root / "fragments" / DEFAULT_PARTITION / "mentions.rb64").exists()

    # Migration is idempotent — closing and reopening doesn't touch anything.
    s.close()
    Store(root)._connect()


# --- two-partition isolation ----------------------------------------------


def test_two_partitions_stay_isolated(tmp_path):
    """Two Stores rooted at the same .refmatrix/ but bound to different
    partitions can hold entities with the same (kind, name) and never see
    each other's data through the partition-scoped APIs."""
    root = tmp_path / ".refmatrix"
    Store(root).init()

    sa = Store(root, partition="agent-a")
    sb = Store(root, partition="agent-b")

    # Same kind+name in both partitions — under the legacy UNIQUE(kind,name)
    # this would have collided.
    cid_a = sa.add_concept("parser")
    eid_a = sa.upsert_entity(kind="code", name="src/foo.py")
    sa.link("mentions", cid_a, eid_a)

    cid_b = sb.add_concept("parser")
    eid_b = sb.upsert_entity(kind="code", name="src/foo.py")
    sb.link("mentions", cid_b, eid_b)

    # Distinct global ids.
    assert cid_a != cid_b
    assert eid_a != eid_b

    # get_entity is scoped to the active partition.
    assert sa.get_entity("concept", "parser").id == cid_a
    assert sb.get_entity("concept", "parser").id == cid_b

    # iter_entities sees only the active partition's rows.
    a_names = sorted((e.kind, e.name) for e in sa.iter_entities())
    b_names = sorted((e.kind, e.name) for e in sb.iter_entities())
    assert a_names == [("code", "src/foo.py"), ("concept", "parser")]
    assert b_names == [("code", "src/foo.py"), ("concept", "parser")]

    # Bitmap reads are partition-scoped: each side sees only its own concept's
    # entity. Critically, the global concept_id from partition B is NOT a
    # member of partition A's bitmap, even though both partitions packed bits
    # for "the parser concept" in their own fragment file.
    bm_a = sa.load_bitmap("mentions", cid_a)
    bm_b = sb.load_bitmap("mentions", cid_b)
    assert eid_a in bm_a and eid_b not in bm_a
    assert eid_b in bm_b and eid_a not in bm_b

    # Saved queries are also per-partition.
    sa.save_query("doc-gap", "defines:parser AND NOT mentions:parser")
    assert sa.get_saved_query("doc-gap") is not None
    assert sb.get_saved_query("doc-gap") is None

    # Close both — flush_fragments() persists to per-partition subdirs.
    sa.close()
    sb.close()
    assert (root / "fragments" / "agent-a" / "mentions.rb64").exists()
    assert (root / "fragments" / "agent-b" / "mentions.rb64").exists()


def test_partition_auto_created_on_first_open(tmp_path):
    """Opening a Store with a brand-new partition name auto-registers it; no
    explicit `partition add` step is required for everyday agent use."""
    root = tmp_path / ".refmatrix"
    Store(root).init()

    fresh = Store(root, partition="brand-new")
    fresh._connect()
    rows = [r["name"] for r in fresh._connect().execute(
        "SELECT name FROM partitions ORDER BY id"
    )]
    assert "brand-new" in rows
    fresh.close()
