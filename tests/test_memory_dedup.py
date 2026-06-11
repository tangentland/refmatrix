"""`Store.fold_concept_dups` / `rmx memory dedup`.

Pre-0.7.6 GMD ingest minted a `kind=concept` node twinning each doc-level
memory (the `__root__` collision), splitting a subject's edges across two
nodes. The fold migrates the concept's edges onto the same-named memory and
purges the concept.
"""
from __future__ import annotations

from refmatrix.store import Store


def _kinds(s, name):
    return {
        r[0] for r in s._connect().execute(
            "SELECT kind FROM entities WHERE name=?", (name,)
        )
    }


def _has_edge(s, linkage, concept_id, entity_id):
    return s._connect().execute(
        "SELECT 1 FROM entity_links el JOIN linkage_types lt "
        "ON lt.id = el.linkage_id "
        "WHERE lt.name=? AND el.concept_id=? AND el.entity_id=?",
        (linkage, concept_id, entity_id),
    ).fetchone() is not None


def test_fold_migrates_edges_and_drops_concept(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    with s.with_partition("p"):
        mid = s.add_memory(name="dup_slug", content="body")
        cid = s.upsert_entity(kind="concept", name="dup_slug")
        other = s.upsert_entity(kind="code", name="x.py")
        refs = s.add_concept("refers")
        # inbound: refs --mentions--> dup_slug(concept)  (entity_id=cid)
        s.link("mentions", refs, cid)
        # outbound: dup_slug(concept) --mentions--> other (concept_id=cid)
        s.link("mentions", cid, other)
        assert _kinds(s, "dup_slug") == {"concept", "memory"}

        res = s.fold_concept_dups()
        assert res["folded"] == 1
        assert res["edges_migrated"] == 2

        # concept twin gone; only the memory remains.
        assert _kinds(s, "dup_slug") == {"memory"}
        # edges re-pointed onto the memory.
        assert _has_edge(s, "mentions", refs, mid)      # inbound now -> memory
        assert _has_edge(s, "mentions", mid, other)     # outbound now from memory
        # nothing still references the dead concept id.
        assert not _has_edge(s, "mentions", refs, cid)
        assert not _has_edge(s, "mentions", cid, other)
    s.close()


def test_fold_dry_run_counts_without_mutating(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    with s.with_partition("p"):
        s.add_memory(name="dup_slug", content="body")
        s.upsert_entity(kind="concept", name="dup_slug")
        res = s.fold_concept_dups(dry_run=True)
        assert res["folded"] == 1
        assert res["dry_run"] is True
        # concept still present — dry run mutated nothing.
        assert _kinds(s, "dup_slug") == {"concept", "memory"}
    s.close()


def test_fold_noop_when_no_dups(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    with s.with_partition("p"):
        s.add_memory(name="lonely", content="body")
        s.add_concept("unrelated")
        res = s.fold_concept_dups()
        assert res["folded"] == 0
        assert res["edges_migrated"] == 0
    s.close()
