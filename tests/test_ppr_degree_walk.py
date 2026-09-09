"""degree>=1 = seeded-PPR reach, not hop count (2026-09-09).

A chain anchor→doc1→bridge→doc2 is invisible at degree=0 (one hop) and
discovered at degree>=1 via the walk group, ranked by PPR mass. Bare
concepts and session cards never surface as walk destinations.
"""
from __future__ import annotations

import pytest

from refmatrix.context import build_context
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _chain(s):
    """anchor_c -- d1 -- bridge_c -- d2, plus an off-chain distractor."""
    anchor_c = s.add_concept("anchor_topic")
    bridge_c = s.add_concept("bridge_topic")
    d1 = s.upsert_entity(kind="doc", name="near.md", tldr="near doc")
    d2 = s.upsert_entity(kind="doc", name="far.md", tldr="far doc")
    s.link("mentions", anchor_c, d1, weight=3.0)
    s.link("mentions", bridge_c, d1, weight=3.0)
    s.link("mentions", bridge_c, d2, weight=3.0)
    # distractor cluster, not connected to the chain
    other_c = s.add_concept("elsewhere")
    d3 = s.upsert_entity(kind="doc", name="unrelated.md", tldr="unrelated")
    s.link("mentions", other_c, d3, weight=3.0)
    return anchor_c, d1, d2, d3


def _names(bundle):
    return {e.entity.name for grp in bundle.groups.values() for e in grp}


def test_degree0_stays_one_hop(store):
    _chain(store)
    b = build_context(store, "anchor_topic", grep_backstop=False)
    names = _names(b)
    assert "near.md" in names
    assert "far.md" not in names


def test_degree_walk_reaches_two_hops(store):
    _chain(store)
    b = build_context(store, "anchor_topic", degree=2, grep_backstop=False)
    walk = [e.entity.name for e in b.groups.get("walk", [])]
    assert "far.md" in walk, b.groups.keys()
    # disconnected cluster gets no mass
    assert "unrelated.md" not in _names(b)


def test_walk_entries_ranked_by_mass_and_no_bare_concepts(store):
    _chain(store)
    b = build_context(store, "anchor_topic", degree=2, grep_backstop=False)
    walk = b.groups.get("walk", [])
    assert walk
    weights = [e.weight or 0.0 for e in walk]
    assert weights == sorted(weights, reverse=True)
    for e in walk:
        assert not (e.entity.kind == "concept" and "#" not in e.entity.name)


def test_walk_excludes_session_cards(store):
    _chain(store)
    card = store.upsert_entity(kind="doc", name="session-abc123",
                               tldr="operational card")
    bridge = store.add_concept("bridge_topic")
    store.link("mentions", bridge, card, weight=5.0)
    b = build_context(store, "anchor_topic", degree=2, grep_backstop=False)
    assert "session-abc123" not in _names(b)


def test_linkage_filter_disables_walk(store):
    _chain(store)
    b = build_context(store, "anchor_topic", degree=2,
                      linkages=["mentions"], grep_backstop=False)
    assert "walk" not in b.groups


def test_walk_caps_one_slot_per_parent_doc(store):
    """A multi-section hub doc must not eat the walk group: one slot per
    parent, highest mass wins (the viascope ui-specification leak)."""
    anchor_c = store.add_concept("anchor_topic")
    d1 = store.upsert_entity(kind="doc", name="near.md", tldr="near doc")
    store.link("mentions", anchor_c, d1, weight=3.0)
    bridge = store.add_concept("bridge_topic")
    store.link("mentions", bridge, d1, weight=3.0)
    # Hub doc with many section anchors, all reachable via the bridge.
    for i in range(6):
        sec = store.upsert_entity(kind="concept", name=f"hubdoc#s{i}",
                                  tldr=f"section {i}")
        store.link("mentions", bridge, sec, weight=2.0)
    far = store.upsert_entity(kind="doc", name="far.md", tldr="far doc")
    store.link("mentions", bridge, far, weight=2.0)
    b = build_context(store, "anchor_topic", degree=2, grep_backstop=False)
    walk = [e.entity.name for e in b.groups.get("walk", [])]
    hub_slots = [n for n in walk if n.startswith("hubdoc#")]
    assert len(hub_slots) <= 1, walk
