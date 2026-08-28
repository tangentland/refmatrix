"""Prompt-concept expansion: canonical variants, prompt-coverage, prompt clique.

Three changes to how `scan-prompt` turns a prompt into concepts:

1. resolution expands through `canonical_name`, which every OTHER read
   surface already did and this one did not;
2. concept SELECTION is weighted by how much a concept's neighborhood
   overlaps the rest of the prompt's (the coverage term `content_rank` uses
   for entities);
3. the prompt's concepts are linked to each other before the PPR walk, so
   mass can travel between them.

Measured together on MemAware Layer-A, concept path isolated:
MRR 0.043 -> 0.065, hit@20 0.200 -> 0.267, Recall@20 0.132 -> 0.206.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# --- clique overlay --------------------------------------------------------


def test_clique_links_every_seed_pair():
    from refmatrix.ppr import overlay_prompt_clique

    adj = {1: {10: 1.0}, 2: {20: 1.0}, 3: {30: 1.0}}
    out = overlay_prompt_clique(adj, [1, 2, 3], weight=0.5)
    for a in (1, 2, 3):
        for b in (1, 2, 3):
            if a != b:
                assert out[a][b] == 0.5, f"{a}->{b} missing"
    # Original neighbors survive.
    assert out[1][10] == 1.0


def test_clique_does_not_mutate_the_caller_adjacency():
    """`build_adjacency` is expensive and callers reuse it; a walk-local
    overlay must not leak into the next query's graph."""
    from refmatrix.ppr import overlay_prompt_clique

    adj = {1: {10: 1.0}, 2: {20: 1.0}}
    out = overlay_prompt_clique(adj, [1, 2], weight=1.0)
    assert 2 not in adj[1], "caller's adjacency was mutated"
    assert 2 in out[1]


def test_clique_is_a_noop_below_two_seeds_or_zero_weight():
    from refmatrix.ppr import overlay_prompt_clique

    adj = {1: {10: 1.0}, 2: {20: 1.0}}
    assert overlay_prompt_clique(adj, [1], weight=1.0) is adj
    assert overlay_prompt_clique(adj, [1, 2], weight=0.0) is adj
    assert overlay_prompt_clique(adj, [], weight=1.0) is adj


def test_clique_skips_seeds_absent_from_the_graph():
    from refmatrix.ppr import overlay_prompt_clique

    adj = {1: {10: 1.0}, 2: {20: 1.0}}
    out = overlay_prompt_clique(adj, [1, 2, 999], weight=1.0)
    assert 999 not in out
    assert 999 not in out[1]


def test_clique_sums_onto_an_existing_edge():
    from refmatrix.ppr import overlay_prompt_clique

    adj = {1: {2: 3.0}, 2: {1: 3.0}}
    out = overlay_prompt_clique(adj, [1, 2], weight=2.0)
    assert out[1][2] == 5.0


# --- seed coverage ---------------------------------------------------------


def test_coverage_is_the_shared_neighbor_fraction():
    from refmatrix.ppr import seed_coverage

    # 1 and 2 both touch entity 10; 3 touches nothing they do.
    adj = {1: {10: 1.0, 11: 1.0}, 2: {10: 1.0}, 3: {30: 1.0}}
    cov = seed_coverage(adj, [1, 2, 3])
    assert cov[1] == pytest.approx(0.5)    # 1 of {10,11} shared
    assert cov[2] == pytest.approx(1.0)    # its only neighbor is shared
    assert cov[3] == pytest.approx(0.0)    # disjoint from the prompt


def test_coverage_of_a_lone_seed_is_zero():
    """A one-concept prompt has no 'rest of the prompt' to overlap."""
    from refmatrix.ppr import seed_coverage

    assert seed_coverage({1: {10: 1.0}}, [1]) == {1: 0.0}


def test_coverage_handles_a_seed_with_no_neighbors():
    from refmatrix.ppr import seed_coverage

    cov = seed_coverage({1: {10: 1.0}, 2: {}}, [1, 2])
    assert cov[2] == 0.0


# --- prompt-aware ranking --------------------------------------------------


def _concept_graph(store):
    """Two concepts sharing a doc, plus an unrelated one."""
    shared = store.upsert_entity(kind="doc", name="shared.md",
                                 path="/x/shared.md", tldr="shared")
    other = store.upsert_entity(kind="doc", name="other.md",
                                path="/x/other.md", tldr="other")
    a = store.add_concept("alpha")
    b = store.add_concept("beta")
    c = store.add_concept("gamma")
    store.add_linkage_type("mentions")
    store.link("mentions", concept_id=a, entity_id=shared)
    store.link("mentions", concept_id=b, entity_id=shared)
    store.link("mentions", concept_id=c, entity_id=other)
    return a, b, c


def test_zero_params_match_plain_rank_related(store):
    """The new ranker must reduce to the old one when both terms are off —
    otherwise every existing measurement silently changes meaning."""
    from refmatrix import ppr

    a, b, _c = _concept_graph(store)
    plain = ppr.rank_related(store, [a, b], k=10)
    same = ppr.rank_related_for_prompt(
        store, [a, b], k=10, clique_weight=0.0, coverage_alpha=0.0)
    assert [r["name"] for r in plain] == [r["name"] for r in same]


def test_coverage_reports_per_seed_overlap(store):
    from refmatrix import ppr

    a, b, c = _concept_graph(store)
    out = ppr.rank_related_for_prompt(
        store, [a, b, c], k=10, coverage_alpha=3.0)
    cov = {r["name"]: r.get("coverage") for r in out if r.get("seed")}
    # alpha/beta share a doc; gamma shares nothing with them.
    assert cov.get("gamma") == 0.0
    assert cov.get("alpha", 0) > 0


def test_empty_seed_set_returns_nothing(store):
    from refmatrix import ppr

    assert ppr.rank_related_for_prompt(store, [], k=5) == []
    assert ppr.rank_related_for_prompt(store, [999999], k=5) == []


# --- canonical-variant expansion in match_concepts -------------------------


def test_match_finds_a_camelcase_concept_from_a_snake_prompt(store, monkeypatch):
    """The bug this fixes: `resolve_concept_ids` folds camel/snake/dash forms
    via canonical_name and store.py documents it as used by
    query/context/neighbors — but scan-prompt resolved by exact name only."""
    from refmatrix import scan

    store.add_concept("parseURL")
    monkeypatch.setenv("RMX_SCAN_VARIANTS", "1")
    got = scan.match_concepts(store, ["parse_url"], drop_unlinked_plain=False)
    assert "parseURL" in got


def test_variant_expansion_can_be_switched_off(store, monkeypatch):
    from refmatrix import scan

    store.add_concept("parseURL")
    monkeypatch.setenv("RMX_SCAN_VARIANTS", "0")
    got = scan.match_concepts(store, ["parse_url"], drop_unlinked_plain=False)
    assert "parseURL" not in got


def test_exact_match_still_wins_without_expansion(store, monkeypatch):
    from refmatrix import scan

    store.add_concept("alpha")
    monkeypatch.setenv("RMX_SCAN_VARIANTS", "0")
    assert "alpha" in scan.match_concepts(
        store, ["alpha"], drop_unlinked_plain=False)


# --- defaults --------------------------------------------------------------


def test_shipped_defaults_enable_all_three(monkeypatch):
    """All three ship ON together. The clique measured WORSE alone
    (concept-path hit@20 0.200 -> 0.178) and only pays off with coverage
    correcting its drift, so a default that enables one without the other
    would ship a known regression."""
    from refmatrix import scan

    for var in ("RMX_SCAN_VARIANTS", "RMX_SCAN_CLIQUE_W",
                "RMX_SCAN_COVERAGE_ALPHA"):
        monkeypatch.delenv(var, raising=False)
    assert scan._variant_expansion() is True
    assert scan._clique_weight() > 0
    assert scan._coverage_alpha() > 0


def test_bad_env_values_fall_back_to_off(monkeypatch):
    """An unparseable weight must degrade to the safe value, not crash the
    always-on hook."""
    from refmatrix import scan

    monkeypatch.setenv("RMX_SCAN_CLIQUE_W", "banana")
    monkeypatch.setenv("RMX_SCAN_COVERAGE_ALPHA", "")
    assert scan._clique_weight() == 0.0
    assert scan._coverage_alpha() == 3.0
