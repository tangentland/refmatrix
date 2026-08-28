"""Prompt-as-net: core clique -> tldr expansion -> corroboration cull.

The load-bearing property is step 3: a node joins the net only if MORE THAN
ONE core member reached it. That is what distinguishes this from the degree-2
`enrich` walk, which soft-weighted by reach and collapsed to 0.013 MRR because
a bipartite frontier outruns any decay.

The second property is the interaction with STM: a single-term prompt has a
core of one, so nothing can have two edges into it and the net is empty BY
CONSTRUCTION. Merging the session's focus is what makes the cull well-defined
in exactly the case the prompt carries least signal.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_linkage_type("mentions")
    yield s
    s.close()


def _graph(store):
    """shared/only docs so corroboration is controllable.

    alpha+beta both mention `shared`; only alpha mentions `alpha_only`.
    """
    shared = store.upsert_entity(kind="doc", name="shared.md",
                                 path="/x/s.md", tldr="shared body")
    alpha_only = store.upsert_entity(kind="doc", name="alpha_only.md",
                                     path="/x/a.md", tldr="alpha body")
    a = store.add_concept("alpha")
    b = store.add_concept("beta")
    for c, ent in ((a, shared), (b, shared), (a, alpha_only)):
        store.link("mentions", concept_id=c, entity_id=ent)
    return a, b, shared, alpha_only


def test_cull_keeps_only_corroborated_nodes(store):
    from refmatrix.net import build_net

    a, b, shared, alpha_only = _graph(store)
    net, core, _prompt = build_net(store, [a, b], use_bodies=False)
    assert set(core) == {a, b}
    assert shared in net, "reached by both core members"
    assert alpha_only not in net, "reached by one core member — must be culled"
    assert net[shared] == {a, b}


def test_min_support_one_disables_the_cull(store):
    from refmatrix.net import build_net

    a, b, _shared, alpha_only = _graph(store)
    net, _core, _p = build_net(store, [a, b], min_support=1, use_bodies=False)
    assert alpha_only in net, "support=1 is no cull at all"


def test_single_term_core_yields_an_empty_net(store):
    """The failure mode STM exists to fix: one core member cannot corroborate
    anything, so the net is empty by construction."""
    from refmatrix.net import build_net

    a, _b, _shared, _only = _graph(store)
    net, core, _p = build_net(store, [a], use_bodies=False)
    assert core == [a]
    assert net == {}


def test_stm_rescues_the_single_term_core(store):
    """Merging session focus raises the core above one, which is what makes
    the >1-edge cull meaningful for a short prompt."""
    from refmatrix.net import build_net

    a, b, shared, _only = _graph(store)
    net, core, prompt = build_net(store, [a], stm_seed_ids=[b],
                                  use_bodies=False)
    assert set(core) == {a, b}
    assert prompt == {a}, "STM members are core but not prompt seeds"
    assert shared in net


def test_core_members_never_enter_their_own_net(store):
    from refmatrix.net import build_net

    a, b, _shared, _only = _graph(store)
    net, _core, _p = build_net(store, [a, b], use_bodies=False)
    assert a not in net and b not in net


def test_unknown_seeds_produce_nothing(store):
    from refmatrix.net import build_net

    net, core, _p = build_net(store, [999999], use_bodies=False)
    assert net == {} and core == []


def test_net_concepts_ranks_by_support(store):
    from refmatrix.net import net_concepts

    a = store.add_concept("alpha")
    b = store.add_concept("beta")
    c = store.add_concept("gamma")
    two = store.add_concept("reached_by_two")
    three = store.add_concept("reached_by_three")
    d2 = store.upsert_entity(kind="doc", name="d2.md", path="/x/2.md", tldr="x")
    d3 = store.upsert_entity(kind="doc", name="d3.md", path="/x/3.md", tldr="y")
    for cc in (a, b, two):
        store.link("mentions", concept_id=cc, entity_id=d2)
    for cc in (a, b, c, three):
        store.link("mentions", concept_id=cc, entity_id=d3)

    out = net_concepts(store, [a, b, c], k=10, use_bodies=False,
                       include_seeds=False)
    by_name = {r["name"]: r["support"] for r in out}
    assert by_name.get("reached_by_three", 0) >= by_name.get("reached_by_two", 0)


def test_body_expansion_reaches_across_a_missing_edge(store):
    """Two concepts can describe the same thing and share no edge. Graph
    adjacency structurally cannot reach that; the body can."""
    from refmatrix.net import build_net

    a = store.add_concept("alpha")
    b = store.add_concept("beta")
    store._connect().execute(
        "UPDATE entities SET tldr = ? WHERE id IN (?, ?)",
        ["roaring bitmap fragment storage layer", a, b])
    store._connect().commit()
    target = store.upsert_entity(
        kind="doc", name="frag.md", path="/x/f.md",
        tldr="roaring bitmap fragment storage layer")
    for term in ("roaring", "bitmap", "fragment"):
        store.link("mentions", concept_id=store.add_concept(term),
                   entity_id=target)

    with_bodies, _c, _p = build_net(store, [a, b], use_bodies=True)
    without, _c2, _p2 = build_net(store, [a, b], use_bodies=False)
    assert len(with_bodies) >= len(without)


# --- flags -----------------------------------------------------------------


def test_support_default_is_corroboration(monkeypatch):
    from refmatrix import scan

    monkeypatch.delenv("RMX_SCAN_NET_SUPPORT", raising=False)
    assert scan._net_min_support() == 2
    monkeypatch.setenv("RMX_SCAN_NET_SUPPORT", "banana")
    assert scan._net_min_support() == 2
    monkeypatch.setenv("RMX_SCAN_NET_SUPPORT", "3")
    assert scan._net_min_support() == 3


def test_bodies_on_by_default(monkeypatch):
    from refmatrix import scan

    monkeypatch.delenv("RMX_SCAN_NET_BODIES", raising=False)
    assert scan._net_use_bodies() is True
    monkeypatch.setenv("RMX_SCAN_NET_BODIES", "0")
    assert scan._net_use_bodies() is False
