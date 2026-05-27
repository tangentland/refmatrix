"""Tests for the Phase B5 reinforcement scoring layer.

Covers the unit math (sign, decay, cap), env-var configuration, the
Store passthrough, and the per-concept rescore multiplier used by the
retrieval-side hook in `RmxRetriever._retrieve_bm25_multi`.
"""
from __future__ import annotations

import math
import time

import pytest

from refmatrix import reinforcement as rein
from refmatrix.store import Store


def _store(tmp_path, monkeypatch, backend="sqlite"):
    monkeypatch.setenv("RMX_BACKEND", backend)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def _seed(s: Store, name: str, concept: str, linkage: str, weight: float,
          *, age_days: float = 0.0, now: float | None = None) -> tuple[int, int]:
    """Add a memory, link it to a concept, then back-date the entity's
    created_at so we exercise the decay path. Returns (eid, cid)."""
    if now is None:
        now = time.time()
    eid = s.add_memory(name, f"body for {name}")
    cid = s.add_concept(concept)
    s.link(linkage, cid, eid, weight=weight)
    backdated = now - age_days * 86400.0
    con = s._connect()
    con.execute(
        "UPDATE entities SET created_at=? WHERE id=?", (backdated, eid),
    )
    con.commit()
    return eid, cid


# --- pure math -------------------------------------------------------------


def test_component_signs_by_linkage_regardless_of_weight_sign():
    """Linkage-name decides the sign so a mis-signed weight can't flip
    polarity. `reinforces` = +|w|, `contradicts` = -|w|."""
    assert rein._component("reinforces", 0.5) == pytest.approx(0.5)
    assert rein._component("reinforces", -0.5) == pytest.approx(0.5)
    assert rein._component("contradicts", 0.5) == pytest.approx(-0.5)
    assert rein._component("contradicts", -0.5) == pytest.approx(-0.5)
    assert rein._component("reinforces", None) == pytest.approx(1.0)


def test_decay_halves_every_halflife():
    halflife = 10.0
    dt = halflife * 86400.0
    one = rein._decay(0, halflife)
    half = rein._decay(dt, halflife)
    quarter = rein._decay(2 * dt, halflife)
    assert one == pytest.approx(1.0)
    assert half == pytest.approx(0.5, rel=1e-9)
    assert quarter == pytest.approx(0.25, rel=1e-9)


def test_decay_returns_one_when_halflife_nonpositive():
    """halflife <= 0 means no decay — old contributions count at full."""
    assert rein._decay(1e9, 0) == 1.0
    assert rein._decay(1e9, -5) == 1.0


def test_rescore_factor_zero_alpha_is_noop():
    assert rein.rescore_factor(1.5, alpha=0.0, cap=5.0) == 1.0
    assert rein.rescore_factor(-1.5, alpha=0.0, cap=5.0) == 1.0


def test_rescore_factor_bounded_by_alpha():
    for sig in (-100.0, -0.5, 0.5, 100.0):
        f = rein.rescore_factor(sig, alpha=0.3, cap=5.0)
        # |alpha * tanh(_)| < alpha, so f sits in [1 - alpha, 1 + alpha]
        assert 0.7 - 1e-12 <= f <= 1.3 + 1e-12


def test_rescore_factor_signal_zero_yields_one():
    assert rein.rescore_factor(0.0, alpha=0.5, cap=5.0) == pytest.approx(1.0)


# --- store passthrough -----------------------------------------------------


def test_reinforcement_score_returns_zero_for_unlinked_concept(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    cid = s.add_concept("orphan")
    assert s.reinforcement_score(cid) == 0.0


def test_reinforces_adds_contradicts_subtracts(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    _, cid = _seed(s, "supports", "topic", "reinforces", 1.0, age_days=0)
    eid2 = s.add_memory("denies", "denies body")
    s.link("contradicts", cid, eid2, weight=0.4)
    # No decay (age=0 for both), no cap hit. Signal ≈ 1.0 - 0.4 = 0.6.
    sig = s.reinforcement_score(cid, halflife_days=30.0, cap=5.0)
    assert sig == pytest.approx(0.6, abs=1e-3)


def test_signal_decays_with_age(tmp_path, monkeypatch):
    """A 30-day-old memory at 30-day half-life contributes ~0.5×, not 1×."""
    s = _store(tmp_path, monkeypatch)
    _, cid = _seed(s, "old", "topic", "reinforces", 1.0, age_days=30.0)
    sig = s.reinforcement_score(cid, halflife_days=30.0, cap=5.0)
    assert sig == pytest.approx(0.5, abs=1e-2)


def test_signal_caps_at_plus_minus_cap(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    cid = s.add_concept("hot")
    for i in range(100):
        eid = s.add_memory(f"m{i}", "x")
        s.link("reinforces", cid, eid, weight=1.0)
    sig = s.reinforcement_score(cid, halflife_days=30.0, cap=2.0)
    assert sig == 2.0  # clamped


def test_batched_form_returns_zero_for_missing_concepts(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    _, cid = _seed(s, "m", "linked", "reinforces", 0.7, age_days=0)
    other = s.add_concept("unlinked")
    scores = s.reinforcement_scores([cid, other], halflife_days=30.0, cap=5.0)
    assert scores[cid] == pytest.approx(0.7, abs=1e-3)
    assert scores[other] == 0.0


# --- env-var config --------------------------------------------------------


def test_env_overrides_kick_in(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    _, cid = _seed(s, "old", "topic", "reinforces", 1.0, age_days=30.0)
    # Env halflife = 1 day. After 30 days the decay should be ~2^-30 ≈ 1e-9.
    monkeypatch.setenv("RMX_REINFORCE_HALFLIFE_DAYS", "1")
    monkeypatch.setenv("RMX_REINFORCE_CAP", "5")
    sig = s.reinforcement_score(cid)
    assert sig == pytest.approx(math.pow(2.0, -30.0), abs=1e-6)


def test_alpha_env_changes_rescore_factor(monkeypatch):
    monkeypatch.setenv("RMX_REINFORCE_ALPHA", "0.5")
    monkeypatch.setenv("RMX_REINFORCE_CAP", "5")
    factor = rein.rescore_factor(5.0)  # tanh(1) ≈ 0.7616
    assert factor == pytest.approx(1.0 + 0.5 * math.tanh(1.0), rel=1e-9)


def test_env_garbage_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("RMX_REINFORCE_HALFLIFE_DAYS", "not-a-number")
    assert rein.get_halflife_days() == rein.DEFAULT_HALFLIFE_DAYS


# --- components / explain --------------------------------------------------


def test_components_ordered_by_abs_contribution(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    _, cid = _seed(s, "weak", "topic", "reinforces", 0.1, age_days=0)
    eid2 = s.add_memory("strong", "x")
    s.link("contradicts", cid, eid2, weight=0.9)
    rows = s.reinforcement_components(cid, halflife_days=30.0)
    assert [r["entity_name"] for r in rows] == ["strong", "weak"]
    assert rows[0]["contribution"] == pytest.approx(-0.9, abs=1e-3)
    assert rows[1]["contribution"] == pytest.approx(0.1, abs=1e-3)


# --- integration with apply_to_concept_scores ------------------------------


def test_apply_to_concept_scores_passthrough_when_alpha_zero(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    _, cid = _seed(s, "m", "topic", "reinforces", 1.0, age_days=0)
    contributions = {cid: {100: 2.0, 200: 1.5}}
    monkeypatch.setenv("RMX_REINFORCE_ALPHA", "0")
    out = rein.apply_to_concept_scores(contributions, s)
    assert out == {100: 2.0, 200: 1.5}


def test_apply_to_concept_scores_boosts_reinforced(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    _, cid_hot = _seed(s, "hot-m", "hot", "reinforces", 2.0, age_days=0)
    _, cid_cold = _seed(s, "cold-m", "cold", "contradicts", 2.0, age_days=0)
    contributions = {
        cid_hot:  {1: 1.0, 2: 1.0},
        cid_cold: {1: 1.0, 3: 1.0},
    }
    out = rein.apply_to_concept_scores(
        contributions, s, alpha=0.5, cap=5.0,
    )
    # eid=2 only gets hot's boosted contribution; eid=3 only gets cold's
    # dampened contribution. Boost > 1, dampen < 1.
    assert out[2] > 1.0
    assert out[3] < 1.0
    # Boost > dampen at the same base contribution.
    assert out[2] > out[3]
