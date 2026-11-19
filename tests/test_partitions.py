"""Tests for the partition dimension."""
from __future__ import annotations

import pytest

from refmatrix.store import Store, default_partition_name


# --- fresh init ------------------------------------------------------------


def test_fresh_init_creates_default_partition(tmp_path, monkeypatch):
    """A brand-new Store starts with a single project-scoped partition
    (id=1, named after the project dir) and fragments live under
    fragments/<that-name>/. Existing read/write APIs work unchanged because
    the default partition is implicit.

    Pinned to SQLite: the per-partition fragment file layout is
    SQLite-only. DuckDB persists fragments as BLOB rows (see the BLOB
    persistence tests in test_duckdb_fragments.py)."""
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    default = default_partition_name(tmp_path / ".refmatrix")
    assert s.partition_name == default
    assert s.partition_id == 1

    # Default partition row materialized.
    rows = s._connect().execute(
        "SELECT id, name FROM partitions ORDER BY id"
    ).fetchall()
    assert [(r["id"], r["name"]) for r in rows] == [(1, default)]

    # Roundtrip a basic write/read.
    cid = s.add_concept("parser")
    eid = s.upsert_entity(kind="code", name="src/foo.py")
    s.link("mentions", cid, eid)
    s.close()

    # Fragment file landed under the per-partition subdir.
    assert (s.root / "fragments" / default / "mentions.rb64").exists()


# --- legacy migration ------------------------------------------------------


# --- two-partition isolation ----------------------------------------------


def test_two_partitions_stay_isolated(tmp_path, monkeypatch):
    """Two Stores rooted at the same .refmatrix/ but bound to different
    partitions can hold entities with the same (kind, name) and never see
    each other's data through the partition-scoped APIs.

    Pinned to SQLite: the final fragments/<partition>/ on-disk assertion
    is SQLite-layout-specific. DuckDB stores both partitions as BLOB rows
    in `bitmap_fragments`, which the DuckDB-specific tests cover."""
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
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


def test_rename_partition_moves_rows_and_dirs(tmp_path, monkeypatch):
    """rename_partition updates the catalog row, keeps entity data resolvable
    (entities key off partition id, not name), and moves the fragment dir."""
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    root = tmp_path / ".refmatrix"
    s = Store(root, partition="old-name")
    s.init()
    cid = s.add_concept("parser")
    e = s.upsert_entity(kind="code", name="x.py")
    s.link("mentions", cid, e)
    s.close()
    assert (root / "fragments" / "old-name").exists()

    s2 = Store(root, partition="old-name")
    s2.rename_partition("old-name", "new-name")
    s2.close()

    s3 = Store(root, partition="new-name")
    names = [r["name"] for r in s3._connect().execute(
        "SELECT name FROM partitions"
    )]
    assert "new-name" in names and "old-name" not in names
    assert s3.get_entity("concept", "parser") is not None
    assert (root / "fragments" / "new-name").exists()
    assert not (root / "fragments" / "old-name").exists()
    s3.close()


def test_rename_partition_rejects_existing_target(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    root = tmp_path / ".refmatrix"
    for name in ("a", "b"):
        st = Store(root, partition=name)
        st.init()
        st.close()
    s = Store(root, partition="a")
    with pytest.raises(ValueError):
        s.rename_partition("a", "b")
    with pytest.raises(ValueError):
        s.rename_partition("does-not-exist", "c")
    s.close()


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


def test_canon_links_make_concepts_siblings_across_partitions(tmp_path):
    """Two repo partitions each have their own 'parser' concept. After both
    point at the same canon concept via same_as, siblings_via_canon() in one
    repo surfaces the other repo's concept — that's the foundation for
    cross-codebase concept matching."""
    root = tmp_path / ".refmatrix"
    Store(root).init()

    sa = Store(root, partition="repo-a")
    sb = Store(root, partition="repo-b")
    sc = Store(root, partition="repo-c")  # third partition that doesn't link

    parser_a = sa.add_concept("parser")
    parser_b = sb.add_concept("parser")
    parser_c = sc.add_concept("parser")

    # Wire repo-a and repo-b to the same canon concept. repo-c stays untethered.
    canon_a_id = sa.link_canon(parser_a, "canon", "parser")
    canon_b_id = sb.link_canon(parser_b, "canon", "parser")
    # Both link_canon calls resolve to the SAME canon concept (one row in the
    # canon partition's entities table) — that's how the hub works.
    assert canon_a_id == canon_b_id

    # From repo-a's view, the only sibling is repo-b's parser (not repo-c's,
    # which never linked, and not repo-a's own concept).
    siblings_a = sa.siblings_via_canon(parser_a)
    sibling_keys = {(s["partition_name"], s["name"]) for s in siblings_a}
    assert sibling_keys == {("repo-b", "parser")}

    # The same query from repo-b mirrors back to repo-a.
    siblings_b = sb.siblings_via_canon(parser_b)
    assert {(s["partition_name"], s["name"]) for s in siblings_b} == {
        ("repo-a", "parser"),
    }

    # repo-c never linked, so it has no siblings.
    assert sc.siblings_via_canon(parser_c) == []

    # The canon partition itself was auto-created and contains exactly one
    # parser concept (idempotent under re-link).
    sa.link_canon(parser_a, "canon", "parser")
    canon_store = Store(root, partition="canon")
    parsers_in_canon = [
        e for e in canon_store.iter_entities(kind="concept") if e.name == "parser"
    ]
    assert len(parsers_in_canon) == 1
    canon_store.close()

    sa.close()
    sb.close()
    sc.close()


def test_query_engine_universe_is_partition_scoped(tmp_path):
    """A `NOT` query in partition A must not pull in entities that only exist
    in partition B. Before _universe() was scoped, the complement set was
    drawn from the entire entities table — so partition A would see partition
    B's ids as part of its 'everything else' result."""
    from refmatrix.query import QueryEngine

    root = tmp_path / ".refmatrix"
    Store(root).init()

    sa = Store(root, partition="agent-a")
    sb = Store(root, partition="agent-b")

    # Partition A: one concept, one entity, linked.
    cid_a = sa.add_concept("parser")
    eid_a_linked = sa.upsert_entity(kind="code", name="src/lex.py")
    sa.link("mentions", cid_a, eid_a_linked)
    # Plus one *unlinked* entity in A — this is the only id that should
    # appear in `NOT mentions:parser` from A's perspective.
    eid_a_unlinked = sa.upsert_entity(kind="code", name="src/util.py")

    # Partition B: shares the concept name but is otherwise entirely separate.
    cid_b = sb.add_concept("parser")
    eid_b1 = sb.upsert_entity(kind="code", name="src/foo.py")
    eid_b2 = sb.upsert_entity(kind="code", name="src/bar.py")
    sb.link("mentions", cid_b, eid_b1)
    sb.link("mentions", cid_b, eid_b2)

    # Run the complement query in partition A. Expected: just eid_a_unlinked
    # (plus the concept itself, since `NOT` in this engine returns the active
    # partition's universe minus the matched set, and concepts are entities).
    qa = QueryEngine(sa)
    result_a = qa.run("NOT mentions:parser")
    assert eid_a_unlinked in result_a
    # The two B-only entity ids must NOT appear in A's complement.
    assert eid_b1 not in result_a
    assert eid_b2 not in result_a
    # cid_b (B's concept id) likewise must not appear.
    assert cid_b not in result_a

    # And nothing from the A-side mentioned set leaks into B's complement.
    qb = QueryEngine(sb)
    result_b = qb.run("NOT mentions:parser")
    assert eid_a_linked not in result_b
    assert eid_a_unlinked not in result_b
    assert cid_a not in result_b

    sa.close()
    sb.close()
