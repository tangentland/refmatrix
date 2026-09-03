"""`RMX_TF_NORM` — tf transforms for content_rank, default `raw`.

The default is load-bearing: `raw` must be the identity, because content_rank
carries ~75% of the scan surface and every store reads it.
"""

from __future__ import annotations

import math

import pytest

from refmatrix.store import Store


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_linkage_type("mentions")
    cids = {t: s.add_concept(t) for t in ("alpha", "beta")}
    for name, terms in (("d1", {"alpha": 3.0, "beta": 1.0}),
                        ("d2", {"beta": 1.0}),
                        ("d3", {"alpha": 1.0})):
        eid = s.upsert_entity(kind="doc", name=name)
        for t, w in terms.items():
            s.link("mentions", cids[t], eid, weight=w)
    yield s
    s.close()


def test_raw_is_the_identity(store, monkeypatch):
    monkeypatch.delenv("RMX_TF_NORM", raising=False)
    fn, label = store._tf_transform()
    assert label == "raw"
    for tf in (0.0, 1.0, 2.0, 7.0, 171.0):
        assert fn(tf, {}) == tf


def test_log_compresses_and_is_corpus_blind(store, monkeypatch):
    """The control arm: same log shape, no corpus calibration. Its whole job
    is to make a surprisal win attributable — measured, the two were
    indistinguishable, so the calibration contributed nothing."""
    monkeypatch.setenv("RMX_TF_NORM", "log")
    fn, label = store._tf_transform()
    assert label == "log"
    assert fn(1.0, {}) == 1.0
    assert fn(2.0, {}) == pytest.approx(2.0)
    assert fn(8.0, {}) == pytest.approx(4.0)
    # identical whatever the corpus tail says
    assert fn(8.0, {8.0: 0.5}) == fn(8.0, {8.0: 0.001})


def test_surprisal_is_calibrated_by_the_corpus_tail(store, monkeypatch):
    """Same tf scores HIGHER in a corpus where that tf is rarer."""
    monkeypatch.setenv("RMX_TF_NORM", "surprisal")
    fn, label = store._tf_transform()
    assert label == "surprisal"
    common = fn(3.0, {3.0: 0.256})     # prose: tf=3 is the top 26%
    rare = fn(3.0, {3.0: 0.035})       # code:  tf=3 is the top 3.5%
    assert rare > common
    assert common == pytest.approx(1.0 + -math.log2(0.256))


def test_surprisal_never_zeroes_the_majority_of_the_index(store, monkeypatch):
    """Raw surprisal is 0 at the most common tf by construction, and tf=1 is
    ~55% of prose edges. The `1 +` is what keeps that half of the index
    scoring at all."""
    monkeypatch.setenv("RMX_TF_NORM", "surprisal")
    fn, _ = store._tf_transform()
    assert fn(1.0, {1.0: 1.0}) == 1.0
    assert fn(5.0, {}) == 1.0          # missing tail entry degrades, not crashes
    assert fn(0.0, {}) == 0.0


def test_tf_tail_is_a_descending_cumulative(store):
    """P(TF>=tf) must be monotone non-increasing in tf and start at 1.0."""
    mlid = store.get_linkage_id("mentions")
    tail = store.mentions_tf_tail(mlid)
    assert isinstance(tail, dict)
    if tail:
        keys = sorted(tail)
        vals = [tail[k] for k in keys]
        assert vals == sorted(vals, reverse=True)
        assert vals[0] == pytest.approx(1.0)
