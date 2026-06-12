"""Verb canonicalization + the one-shot alias merge.

GMD/memory `rel:` edges are kebab-case while seeded defaults + code emitters
historically used snake_case for the SAME relation (`related_to` vs
`related-to`) — a `linkage_types` split-brain. `_canonical_verb` folds the
known twin at every choke point so new writes can't re-split, and
`Store.merge_verb_alias` collapses a pre-existing split (relational forward
index + per-partition bitmap) into the canonical linkage.
"""
from __future__ import annotations

import pytest
from pyroaring import BitMap64

from refmatrix.store import Store, _canonical_verb


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def test_canonical_verb_folds_only_known_twin():
    assert _canonical_verb("related_to") == "related-to"
    assert _canonical_verb("related-to") == "related-to"  # idempotent
    # Distinct snake verbs share no kebab twin and must NOT be remapped.
    for v in ("same_as", "is_a", "called_by", "similar_to",
              "shares_data_with", "specified_by", "mentions"):
        assert _canonical_verb(v) == v


def test_link_via_alias_resolves_to_canonical(store):
    c = store.upsert_entity(kind="concept", name="alpha")
    e = store.upsert_entity(kind="code", name="mod.py", path="/mod.py")
    # Write under the snake alias; it must land on the canonical fragment + id.
    store.link("related_to", c, e)
    store.flush_fragments()
    # Both query forms fold to the same canonical edge.
    assert e in store.load_bitmap("related-to", c)
    assert e in store.load_bitmap("related_to", c)
    assert store.get_linkage_id("related_to") == store.get_linkage_id("related-to")
    # No orphan snake linkage_type was created.
    names = {lk["name"] for lk in store.list_linkages()}
    assert "related-to" in names
    assert "related_to" not in names


def _inject_legacy_split(store, c, e2):
    """Forge a genuine pre-canonicalization split: a `related_to` linkage_type
    with one relational edge + one bitmap bit, all under the raw snake key
    (the normal API can no longer produce this)."""
    con = store._connect()
    con.execute(
        "INSERT INTO linkage_types(name, directed, description) "
        "VALUES ('related_to', 0, 'legacy snake twin')"
    )
    con.commit()
    legacy_id = con.execute(
        "SELECT id FROM linkage_types WHERE name='related_to'"
    ).fetchone()[0]
    con.execute(
        "INSERT INTO entity_links(entity_id, linkage_id, concept_id, weight) "
        "VALUES (?, ?, ?, NULL)",
        (e2, legacy_id, c),
    )
    # Raw bitmap fragment under the snake key (duckdb backend in tests).
    frag = BitMap64()
    frag.add(store._pack(c, e2))
    con._duck.execute(
        "INSERT INTO bitmap_fragments(partition_id, linkage, blob) "
        "VALUES (?, 'related_to', ?)",
        [store._partition_id, frag.serialize()],
    )
    con.commit()
    return legacy_id


def test_merge_verb_alias_collapses_preexisting_split(store):
    c = store.upsert_entity(kind="concept", name="alpha")
    e1 = store.upsert_entity(kind="code", name="m1.py", path="/m1.py")
    e2 = store.upsert_entity(kind="code", name="m2.py", path="/m2.py")
    # Canonical edge (c,e1) under related-to; legacy edge (c,e2) under related_to.
    store.link("related-to", c, e1)
    store.flush_fragments()
    _inject_legacy_split(store, c, e2)

    # Pre-merge: the split hides e2 from the canonical fragment.
    assert e2 not in store.load_bitmap("related-to", c)

    res = store.merge_verb_alias("related_to", "related-to")
    assert res["merged"] is True
    assert res["edges"] == 1
    assert res["fragments"] == 1

    # Post-merge: one linkage, both edges reachable via the canonical fragment.
    names = {lk["name"] for lk in store.list_linkages()}
    assert "related_to" not in names
    bm = store.load_bitmap("related-to", c)
    assert e1 in bm and e2 in bm
    # Relational rows all moved to the canonical id; none stranded.
    canon_id = store.get_linkage_id("related-to")
    con = store._connect()
    assert con.execute(
        "SELECT count(*) FROM entity_links WHERE concept_id=? AND linkage_id=?",
        (c, canon_id),
    ).fetchone()[0] == 2

    # Idempotent: nothing left to merge.
    res2 = store.merge_verb_alias("related_to", "related-to")
    assert res2["merged"] is False


def test_merge_dedups_edge_present_under_both(store):
    """A legacy edge that duplicates an existing canonical edge is dropped, not
    double-inserted (the UNIQUE guard)."""
    c = store.upsert_entity(kind="concept", name="alpha")
    e = store.upsert_entity(kind="code", name="m.py", path="/m.py")
    store.link("related-to", c, e)
    store.flush_fragments()
    # Same (c,e) edge also under the legacy id.
    con = store._connect()
    con.execute(
        "INSERT INTO linkage_types(name, directed, description) "
        "VALUES ('related_to', 0, 'legacy')"
    )
    con.commit()
    legacy_id = con.execute(
        "SELECT id FROM linkage_types WHERE name='related_to'"
    ).fetchone()[0]
    con.execute(
        "INSERT INTO entity_links(entity_id, linkage_id, concept_id, weight) "
        "VALUES (?, ?, ?, NULL)",
        (e, legacy_id, c),
    )
    con.commit()

    store.merge_verb_alias("related_to", "related-to")
    canon_id = store.get_linkage_id("related-to")
    # Exactly one canonical row — no duplicate from the re-point.
    assert con.execute(
        "SELECT count(*) FROM entity_links WHERE concept_id=? AND linkage_id=?",
        (c, canon_id),
    ).fetchone()[0] == 1
