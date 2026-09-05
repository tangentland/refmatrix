"""Structural-signal boosts and document priors — all default OFF.

Eight signals were being discarded or mis-expressed; these pin that each one
is (a) inert at its default and (b) actually capable of moving a score when
enabled. The second half matters more than it sounds: `reinforcement_scores`
returns 0.0 for ids it does not recognise, so an arm wired to the wrong id
space produces no error and no effect — a silent no-op that would read as
"measured, no gain" in an eval.
"""

from __future__ import annotations

import pytest

from refmatrix.store import Store, _doc_prior_weights, _term_boost_linkages


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    for lk in ("mentions", "titles", "lead"):
        s.add_linkage_type(lk)
    cids = {t: s.add_concept(t) for t in ("alpha", "beta")}
    # Two docs with IDENTICAL term frequencies, so BM25 alone cannot separate
    # them. Only the structural edges below differ.
    d1 = s.upsert_entity(kind="doc", name="d1", meta={"level": 1})
    d2 = s.upsert_entity(kind="doc", name="d2", meta={"level": 4},
                         protected=True)
    for eid in (d1, d2):
        s.link("mentions", cids["alpha"], eid, weight=3.0)
        s.link("mentions", cids["beta"], eid, weight=1.0)
    # d1 carries the structure.
    s.link("titles", cids["alpha"], d1, weight=1.0)
    s.link("lead", cids["alpha"], d1, weight=1.0)
    yield s, {"d1": d1, "d2": d2}
    s.close()


def _rank(s, terms=("alpha",)):
    return dict(s.content_rank(list(terms), limit=10))


def test_defaults_are_all_off(monkeypatch):
    for v in ("RMX_BOOST_TITLES", "RMX_BOOST_LEAD", "RMX_BOOST_REINFORCE",
              "RMX_PRIOR_DEPTH", "RMX_PRIOR_PROTECTED", "RMX_PRIOR_REL"):
        monkeypatch.delenv(v, raising=False)
    b = _term_boost_linkages()
    assert b["titles"] == 0.0
    # `lead` ships ON — the one structural signal that measured, and
    # replicated on held-out questions. Retuned 0.5 -> 0.25 on the clean
    # post-0.49.1 stores (see _term_boost_linkages for the three-view data).
    assert b["lead"] == 0.25
    assert all(v == 0.0 for v in _doc_prior_weights().values())


def test_two_docs_are_tied_without_structure(store, monkeypatch):
    """The fixture's isolation check. Every structural boost must be off for
    this to hold — `lead` ships ON, so it has to be disabled explicitly."""
    monkeypatch.delenv("RMX_BOOST_TITLES", raising=False)
    monkeypatch.setenv("RMX_BOOST_LEAD", "0")
    s, ids = store
    r = _rank(s)
    assert r[ids["d1"]] == pytest.approx(r[ids["d2"]]), (
        "identical tf must tie, or the fixture cannot isolate structure")


def test_title_boost_breaks_the_tie(store, monkeypatch):
    monkeypatch.setenv("RMX_BOOST_LEAD", "0")   # isolate from the shipped default
    """A boost expressed as a LINKAGE, added outside BM25's saturation and
    outside doclen — unlike the `tf=2.0` it replaces, which was swallowed by
    `tf/(tf+k1*...)` and inflated the document length of its own document."""
    s, ids = store
    monkeypatch.setenv("RMX_BOOST_TITLES", "1.0")
    r = _rank(s)
    assert r[ids["d1"]] > r[ids["d2"]]


def test_lead_boost_breaks_the_tie(store, monkeypatch):
    s, ids = store
    monkeypatch.setenv("RMX_BOOST_LEAD", "1.0")
    r = _rank(s)
    assert r[ids["d1"]] > r[ids["d2"]]


def test_depth_prior_prefers_the_shallower_heading(store, monkeypatch):
    monkeypatch.setenv("RMX_BOOST_LEAD", "0")   # isolate from the shipped default
    """`level` has been recorded in entity meta all along and never ranked;
    d1 is H1, d2 is H4."""
    s, ids = store
    monkeypatch.setenv("RMX_PRIOR_DEPTH", "1.0")
    r = _rank(s)
    assert r[ids["d1"]] > r[ids["d2"]]


def test_protected_prior_prefers_the_pinned_entity(store, monkeypatch):
    monkeypatch.setenv("RMX_BOOST_LEAD", "0")   # isolate from the shipped default
    """d2 is the protected one, so this must move the ranking the OTHER way
    from every other signal here — proof it is the flag doing the work and not
    the fixture leaning one direction."""
    s, ids = store
    monkeypatch.setenv("RMX_PRIOR_PROTECTED", "1.0")
    r = _rank(s)
    assert r[ids["d2"]] > r[ids["d1"]]


def test_missing_linkage_is_a_silent_noop_not_a_crash(tmp_path, monkeypatch):
    """A store ingested before `titles` existed must ignore the boost rather
    than fail — the flag is meant to be safe to set globally."""
    monkeypatch.setenv("RMX_BOOST_TITLES", "2.0")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_linkage_type("mentions")
    cid = s.add_concept("alpha")
    eid = s.upsert_entity(kind="doc", name="d1")
    s.link("mentions", cid, eid, weight=2.0)
    assert dict(s.content_rank(["alpha"], limit=5))
    s.close()


def test_mentions_are_counted_once_in_the_adjacency(tmp_path, monkeypatch):
    """A mention edge must contribute ONCE to the centrality graph.

    `build_adjacency` reads mentions twice — flat from the bitmap fragment,
    then again from `entity_links`, which mirrors those bitmaps — so the old
    `both` default scored every mention at `1 + link_weight*tf`. With 99.3% of
    edges being mentions that made PageRank largely a term-frequency measure,
    and PageRank is the prior under `scan._salience`.
    """
    monkeypatch.delenv("RMX_ADJ_MENTIONS", raising=False)
    from refmatrix import pagerank as pg
    assert pg._adj_mentions_mode() == "flat"

    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_linkage_type("mentions")
    cid = s.add_concept("alpha")
    eid = s.upsert_entity(kind="doc", name="d1")
    s.link("mentions", cid, eid, weight=17.0)

    adj = pg.build_adjacency(s)
    assert adj.get(cid, {}).get(eid) == 1.0, "flat: one unweighted count"

    monkeypatch.setenv("RMX_ADJ_MENTIONS", "both")
    adj2 = pg.build_adjacency(s)
    assert adj2.get(cid, {}).get(eid) == pytest.approx(1.0 + 2.0 * 17.0), (
        "the old default double-counted; kept reachable for comparison")
    s.close()
