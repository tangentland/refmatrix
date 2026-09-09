"""CSR adjacency cache (0.64.1): per-write-batch caching of the PPR graph.

Equivalence: CSR duck-type must produce identical PPR mass to the dict.
Freshness: same contract as the BM25 caches — dropped at flush_fragments.
"""
from __future__ import annotations

import pytest

from refmatrix.pagerank import (
    CSRAdjacency, build_adjacency, cached_adjacency,
)
from refmatrix.ppr import local_push_ppr
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    c1 = s.add_concept("alpha")
    c2 = s.add_concept("beta")
    d1 = s.upsert_entity(kind="doc", name="a.md", tldr="alpha doc")
    d2 = s.upsert_entity(kind="doc", name="b.md", tldr="beta doc")
    s.link("mentions", c1, d1, weight=2.0)
    s.link("mentions", c2, d1, weight=1.0)
    s.link("mentions", c2, d2, weight=3.0)
    yield s
    s.close()


def test_csr_ppr_mass_equals_dict_ppr_mass(store):
    adj = build_adjacency(store)
    csr = CSRAdjacency.from_dict(adj)
    seeds = {next(iter(adj)): 1.0}
    m_dict = local_push_ppr(adj, seeds, alpha=0.15, eps=1e-5)
    m_csr = local_push_ppr(csr, seeds, alpha=0.15, eps=1e-5)
    assert set(m_dict) == set(m_csr)
    for n in m_dict:
        assert m_dict[n] == pytest.approx(m_csr[n], rel=1e-9)


def test_cached_adjacency_hits_and_invalidates(store):
    a1 = cached_adjacency(store)
    a2 = cached_adjacency(store)
    assert a1 is a2                      # cache hit
    # write batch boundary drops it
    store.flush_fragments()
    a3 = cached_adjacency(store)
    assert a3 is not a1
    # a new edge is visible after the boundary
    c = store.add_concept("gamma")
    d = store.upsert_entity(kind="doc", name="c.md", tldr="gamma doc")
    store.link("mentions", c, d, weight=1.0)
    store.flush_fragments()
    a4 = cached_adjacency(store)
    assert d in a4 or c in a4


def test_cache_key_varies_by_params(store):
    a1 = cached_adjacency(store, link_weight=2.0)
    a2 = cached_adjacency(store, link_weight=3.0)
    assert a1 is not a2
