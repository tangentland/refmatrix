"""Store.merge_partition + the `partition_merge` daemon op.

Built for the memory-<project> -> <project> consolidation that closes
the cross-partition wikilink resolution gap. Reparents non-colliding
entities, remaps child rows for collisions, prefers the longer
memory_content body, and drops the SRC partition row on success.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


def _store(tmp_path, monkeypatch, backend="sqlite"):
    monkeypatch.setenv("RMX_BACKEND", backend)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


# ---- happy path ----------------------------------------------------------


def test_merge_reparents_non_colliding_entities(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    # Seed SRC with two memories that have no DST equivalents.
    with s.with_partition("src"):
        s.add_memory("alpha", "first body", mtype="curated")
        s.add_memory("beta", "second body", mtype="curated")
    # Seed DST partition existence with one unrelated row.
    with s.with_partition("dst"):
        s.add_memory("gamma", "third body", mtype="curated")
    result = s.merge_partition("src", "dst")
    assert result["entities_reparented"] == 2
    assert result["entities_merged"] == 0
    # All three rows now live in DST.
    with s.with_partition("dst"):
        assert s.get_memory("alpha") is not None
        assert s.get_memory("beta") is not None
        assert s.get_memory("gamma") is not None
    # SRC partition row was dropped.
    con = s._connect()
    assert con.execute(
        "SELECT 1 FROM partitions WHERE name='src'"
    ).fetchone() is None


def test_merge_collision_prefers_longer_memory_content(tmp_path, monkeypatch):
    """When SRC and DST both have a memory with the same name + kind,
    the longer content wins. Linkages remap to the surviving DST
    entity_id."""
    s = _store(tmp_path, monkeypatch)
    with s.with_partition("dst"):
        s.add_memory("note", "short", mtype="curated")
    with s.with_partition("src"):
        s.add_memory(
            "note", "this is a much longer body that should win",
            mtype="curated",
        )
    s.merge_partition("src", "dst")
    with s.with_partition("dst"):
        m = s.get_memory("note")
    assert m is not None
    assert m["content"] == "this is a much longer body that should win"


def test_merge_collision_keeps_longer_dst_body(tmp_path, monkeypatch):
    """Reverse of the previous: DST already has the longer body. SRC's
    shorter body must NOT overwrite it."""
    s = _store(tmp_path, monkeypatch)
    with s.with_partition("dst"):
        s.add_memory(
            "note", "the DST body is long enough to win the merge",
            mtype="curated",
        )
    with s.with_partition("src"):
        s.add_memory("note", "short", mtype="curated")
    s.merge_partition("src", "dst")
    with s.with_partition("dst"):
        m = s.get_memory("note")
    assert m["content"] == (
        "the DST body is long enough to win the merge"
    )


def test_merge_collision_remaps_entity_links_to_dst_id(tmp_path, monkeypatch):
    """A SRC memory linked to a SRC concept must survive merge with
    its link intact pointing at the corresponding DST ids."""
    s = _store(tmp_path, monkeypatch)
    with s.with_partition("dst"):
        dst_mem = s.add_memory("note", "dst body", mtype="curated")
        dst_concept = s.add_concept("parser")
    with s.with_partition("src"):
        src_mem = s.add_memory("note", "src body short", mtype="curated")
        src_concept = s.add_concept("parser")
        s.link("mentions", src_concept, src_mem)
    s.merge_partition("src", "dst")
    # The merged DST mem id should carry a mentions edge to the DST
    # concept id.
    con = s._connect()
    row = con.execute(
        "SELECT 1 FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "WHERE lt.name='mentions' AND el.entity_id=? AND el.concept_id=?",
        (dst_mem, dst_concept),
    ).fetchone()
    assert row is not None


def test_merge_dry_run_preserves_partitions(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    with s.with_partition("src"):
        s.add_memory("alpha", "x", mtype="curated")
    with s.with_partition("dst"):
        s.add_memory("gamma", "y", mtype="curated")
    out = s.merge_partition("src", "dst", dry_run=True)
    assert out["dry_run"] is True
    assert out["entities_reparented"] == 1
    # SRC still exists.
    con = s._connect()
    assert con.execute(
        "SELECT 1 FROM partitions WHERE name='src'"
    ).fetchone() is not None


def test_merge_unknown_partition_raises(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        s.merge_partition("does-not-exist", "also-not-here")


def test_merge_same_partition_is_noop(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    with s.with_partition("alpha"):
        s.add_memory("a", "x", mtype="curated")
    out = s.merge_partition("alpha", "alpha")
    assert out["entities_reparented"] == 0
    assert out.get("note") == "src == dst"


# ---- op registration ------------------------------------------------------


def test_daemon_partition_merge_op_registered():
    """`rmx partition merge` routes through the daemon when one is up.
    Single-row partition merge is fast enough that bg_pool routing is
    fine; we just need OPS dispatch to know the op."""
    from refmatrix.daemon import OPS
    assert "partition_merge" in OPS
