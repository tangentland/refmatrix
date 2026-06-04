"""replica_merge: drift-recovery merge of rotation slots A and B.

Covers:
  - audit_slots row-count diffs + entity collision shapes
  - merge_slots resolves (partition, kind, name) collisions by picking the
    newer entities.updated_at and remapping references
  - memory_content newer-wins on shared entity_id; loser-side mc redirects
    to canonical id without losing newer content
  - merged catalog has no UNIQUE(partition_id, kind, name) violations
  - all standard tables get populated; FKs (modeled as joins) resolve
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("duckdb") is None,
    reason="duckdb not installed",
)


def _make_slot(path: Path) -> None:
    """Build a fresh DuckDB catalog at `path` via init_catalog."""
    import duckdb
    from refmatrix.duckdb_catalog import init_catalog
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    init_catalog(con)
    con.close()


def _seed_baseline(path: Path) -> None:
    """Two partitions, two linkage_types, one entity per partition, plus
    a memory entity + sidecar. Identical baseline in both A and B."""
    import duckdb
    con = duckdb.connect(str(path))
    con.execute(
        "INSERT INTO partitions(id, name, kind, created_at) "
        "VALUES (1, 'local', 'repo', 1000.0)"
    )
    con.execute(
        "INSERT INTO partitions(id, name, kind, created_at) "
        "VALUES (2, 'memory-x', 'repo', 1001.0)"
    )
    con.execute(
        "INSERT INTO linkage_types(id, name, directed) "
        "VALUES (1, 'mentions', 1)"
    )
    con.execute(
        "INSERT INTO linkage_types(id, name, directed) "
        "VALUES (2, 'defines', 1)"
    )
    # Entity 100: doc, partition 1, baseline content
    con.execute(
        "INSERT INTO entities(id, partition_id, kind, name, created_at, "
        "                     updated_at, protected, noise) "
        "VALUES (100, 1, 'doc', 'README.md', 1000.0, 1000.0, 0, 0)"
    )
    # Entity 200: memory, partition 2, baseline content
    con.execute(
        "INSERT INTO entities(id, partition_id, kind, name, created_at, "
        "                     updated_at, protected, noise) "
        "VALUES (200, 2, 'memory', 'feedback_foo', 1000.0, 1000.0, 0, 0)"
    )
    con.execute(
        "INSERT INTO memory_content(entity_id, content, mtype, created_at, "
        "                           updated_at) "
        "VALUES (200, 'baseline-content', 'observation', 1000.0, 1000.0)"
    )
    con.close()


def _make_a(tmp_path: Path) -> Path:
    """A-side: drift adds entity 300 ('a_only'), updates 200's content
    to a newer version, adds an entity_links row."""
    import duckdb
    p = tmp_path / "a.duckdb"
    _make_slot(p)
    _seed_baseline(p)
    con = duckdb.connect(str(p))
    # A-only memory
    con.execute(
        "INSERT INTO entities(id, partition_id, kind, name, created_at, "
        "                     updated_at, protected, noise) "
        "VALUES (300, 2, 'memory', 'feedback_a_only', 2000.0, 2000.0, 0, 0)"
    )
    con.execute(
        "INSERT INTO memory_content(entity_id, content, mtype, created_at, "
        "                           updated_at) "
        "VALUES (300, 'a-only-content', 'observation', 2000.0, 2000.0)"
    )
    # A-newer content for entity 200
    con.execute(
        "UPDATE memory_content SET content='a-newer', updated_at=3000.0 "
        "WHERE entity_id=200"
    )
    con.execute("UPDATE entities SET updated_at=3000.0 WHERE id=200")
    # (p,k,n) collision case: same name as a B row but different id.
    # In A, id=400 is concept 'shared_name' on partition 1.
    con.execute(
        "INSERT INTO entities(id, partition_id, kind, name, created_at, "
        "                     updated_at, protected, noise) "
        "VALUES (400, 1, 'concept', 'shared_name', 2500.0, 2500.0, 0, 0)"
    )
    con.execute("INSERT INTO concepts(id, description) VALUES (400, 'A-side desc')")
    # entity_links referencing the A-side concept id
    con.execute(
        "INSERT INTO entity_links(entity_id, linkage_id, concept_id, weight) "
        "VALUES (100, 1, 400, 0.5)"
    )
    con.close()
    return p


def _make_b(tmp_path: Path) -> Path:
    """B-side: drift adds entity 500 ('b_only'), older content on 200, and
    its own id 401 for 'shared_name' concept on partition 1 — but with
    NEWER updated_at than A's 400 row, so the (p,k,n) collision resolves
    to B.id=401."""
    import duckdb
    p = tmp_path / "b.duckdb"
    _make_slot(p)
    _seed_baseline(p)
    con = duckdb.connect(str(p))
    # B-only memory
    con.execute(
        "INSERT INTO entities(id, partition_id, kind, name, created_at, "
        "                     updated_at, protected, noise) "
        "VALUES (500, 2, 'memory', 'feedback_b_only', 2100.0, 2100.0, 0, 0)"
    )
    con.execute(
        "INSERT INTO memory_content(entity_id, content, mtype, created_at, "
        "                           updated_at) "
        "VALUES (500, 'b-only-content', 'observation', 2100.0, 2100.0)"
    )
    # B-older content for entity 200 (loses to A on mc.updated_at)
    con.execute(
        "UPDATE memory_content SET content='b-older', updated_at=1500.0 "
        "WHERE entity_id=200"
    )
    # B-side concept for same (p,k,n) but id 401 and NEWER updated_at
    con.execute(
        "INSERT INTO entities(id, partition_id, kind, name, created_at, "
        "                     updated_at, protected, noise) "
        "VALUES (401, 1, 'concept', 'shared_name', 2500.0, 9999.0, 0, 0)"
    )
    con.execute("INSERT INTO concepts(id, description) VALUES (401, 'B-side desc')")
    con.execute(
        "INSERT INTO entity_links(entity_id, linkage_id, concept_id, weight) "
        "VALUES (100, 2, 401, 0.7)"
    )
    con.close()
    return p


def test_audit_reports_drift(tmp_path):
    from refmatrix.replica_merge import audit_slots
    a = _make_a(tmp_path)
    b = _make_b(tmp_path)
    report = audit_slots(a, b)
    assert report["drift_detected"] is True
    # A has 100,200,300,400 = 4 entities. B has 100,200,500,401 = 4.
    assert report["a_counts"]["entities"] == 4
    assert report["b_counts"]["entities"] == 4
    # (p,k,n) collision: 'shared_name' concept on partition 1, A.id=400 vs B.id=401
    assert report["entities"]["pkn_collisions_different_ids"] == 1
    # 300 only in A, 500 only in B, 400 only in A, 401 only in B
    assert report["entities"]["a_only_ids"] == 2
    assert report["entities"]["b_only_ids"] == 2


def test_merge_resolves_pkn_collision_to_newer_side(tmp_path):
    import duckdb
    from refmatrix.replica_merge import merge_slots
    a = _make_a(tmp_path)
    b = _make_b(tmp_path)
    out = tmp_path / "merged.duckdb"
    report = merge_slots(a, b, out)
    assert report["dry_run"] is False
    # The collision: A.id=400 (updated_at=2500) vs B.id=401 (updated_at=9999).
    # B wins. remap_a should have {400: 401}.
    assert report["remap"]["a_loser_count"] == 1
    assert report["remap"]["b_loser_count"] == 0

    con = duckdb.connect(str(out), read_only=True)
    # Loser id 400 is gone, winner 401 remains.
    rows = con.execute(
        "SELECT id, partition_id, kind, name FROM entities ORDER BY id"
    ).fetchall()
    ids = [r[0] for r in rows]
    assert 400 not in ids, rows
    assert 401 in ids, rows
    # No (partition, kind, name) duplicate.
    dups = con.execute(
        "SELECT COUNT(*) FROM ("
        " SELECT partition_id, kind, name, COUNT(*) c FROM entities "
        " GROUP BY 1,2,3 HAVING c>1)"
    ).fetchone()[0]
    assert dups == 0
    # entity_links rows from A that pointed at concept_id=400 should
    # have been remapped to 401.
    rows = con.execute(
        "SELECT entity_id, linkage_id, concept_id FROM entity_links "
        "ORDER BY 1,2,3"
    ).fetchall()
    concept_ids = sorted(r[2] for r in rows)
    assert 400 not in concept_ids, rows
    assert 401 in concept_ids, rows
    con.close()


def test_merge_memory_content_newer_wins(tmp_path):
    import duckdb
    from refmatrix.replica_merge import merge_slots
    a = _make_a(tmp_path)
    b = _make_b(tmp_path)
    out = tmp_path / "merged.duckdb"
    merge_slots(a, b, out)
    con = duckdb.connect(str(out), read_only=True)
    # A had newer mc.updated_at (3000) for entity 200 with content 'a-newer';
    # B had older 1500 with 'b-older'. Merged should keep A's content.
    row = con.execute(
        "SELECT content, updated_at FROM memory_content WHERE entity_id=200"
    ).fetchone()
    assert row == ("a-newer", 3000.0), row
    # 300 (A-only) and 500 (B-only) memory rows both survive with content.
    mc_ids = sorted(r[0] for r in con.execute(
        "SELECT entity_id FROM memory_content ORDER BY entity_id"
    ).fetchall())
    assert mc_ids == [200, 300, 500], mc_ids
    # B-only entity 500 also has its entity row present.
    assert con.execute(
        "SELECT name FROM entities WHERE id=500"
    ).fetchone() == ("feedback_b_only",)
    con.close()


def test_merge_preserves_lookup_tables_and_no_fk_orphans(tmp_path):
    import duckdb
    from refmatrix.replica_merge import merge_slots
    a = _make_a(tmp_path)
    b = _make_b(tmp_path)
    out = tmp_path / "merged.duckdb"
    merge_slots(a, b, out)
    con = duckdb.connect(str(out), read_only=True)
    # partitions + linkage_types unchanged (both slots agree).
    assert con.execute("SELECT COUNT(*) FROM partitions").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM linkage_types").fetchone()[0] == 2
    # No memory_content row references a missing entity.
    orphans = con.execute(
        "SELECT COUNT(*) FROM memory_content mc "
        "LEFT JOIN entities e ON e.id = mc.entity_id "
        "WHERE e.id IS NULL"
    ).fetchone()[0]
    assert orphans == 0
    # No entity_links row references a missing entity or linkage_type.
    orphans = con.execute(
        "SELECT COUNT(*) FROM entity_links el "
        "LEFT JOIN entities e ON e.id = el.entity_id "
        "WHERE e.id IS NULL"
    ).fetchone()[0]
    assert orphans == 0
    orphans = con.execute(
        "SELECT COUNT(*) FROM entity_links el "
        "LEFT JOIN entities c ON c.id = el.concept_id "
        "WHERE c.id IS NULL"
    ).fetchone()[0]
    assert orphans == 0
    orphans = con.execute(
        "SELECT COUNT(*) FROM entity_links el "
        "LEFT JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE lt.id IS NULL"
    ).fetchone()[0]
    assert orphans == 0
    con.close()


def test_dry_run_reports_without_writing_target(tmp_path):
    from refmatrix.replica_merge import merge_slots
    a = _make_a(tmp_path)
    b = _make_b(tmp_path)
    out = tmp_path / "merged.duckdb"
    assert not out.exists()
    report = merge_slots(a, b, out, dry_run=True)
    assert report["dry_run"] is True
    assert report["target_size_bytes"] is None
    assert not out.exists()
    # Counts still computed.
    assert report["merged_counts"]["entities"] >= 4
