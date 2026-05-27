"""Phase B5: signed reinforcement scoring.

Per-concept signal:

    signal(c) = Σ_{m -reinforces->  c} +|w(m,c)| · decay(t − t_m)
              + Σ_{m -contradicts-> c} -|w(m,c)| · decay(t − t_m)

clamped to ±CAP. Memories accumulate confidence on a concept through
`reinforces` linkages and erode it through `contradicts`. Both linkages
carry a signed `weight` column on `entity_links`; the convention is that
`reinforces` weights are positive, `contradicts` weights are negative,
but we take `abs(w)` and apply the sign from the linkage name so callers
can't accidentally flip the polarity by mis-signing a weight.

Decay is exponential with half-life HALFLIFE_DAYS, anchored on the source
entity's `entities.created_at` (REAL epoch). Old memories fade gracefully
rather than dropping off a cliff; missing `created_at` (defensive: should
be NOT NULL but the column has been added by migration on legacy rows)
contributes at full weight.

Env-configurable so tuning doesn't require code changes:

    RMX_REINFORCE_HALFLIFE_DAYS   default: 30.0
    RMX_REINFORCE_CAP             default: 5.0
    RMX_REINFORCE_ALPHA           default: 0.0  (opt-in; the rescore
                                                  multiplier is
                                                  `1 + alpha · tanh(signal/cap)`)

`alpha=0` is intentional: ADR-0001 forbids regressing the symbolic-only
baseline. B5 ships the wiring; alpha tuning waits on the synthesized
benchmark (see `eval/reinforcement_bench.py`).
"""
from __future__ import annotations

import math
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from refmatrix.store import Store


DEFAULT_HALFLIFE_DAYS = 30.0
DEFAULT_CAP = 5.0
DEFAULT_ALPHA = 0.0

REINFORCE_LINKAGES = ("reinforces", "contradicts")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_halflife_days() -> float:
    return _env_float("RMX_REINFORCE_HALFLIFE_DAYS", DEFAULT_HALFLIFE_DAYS)


def get_cap() -> float:
    return _env_float("RMX_REINFORCE_CAP", DEFAULT_CAP)


def get_alpha() -> float:
    return _env_float("RMX_REINFORCE_ALPHA", DEFAULT_ALPHA)


def _decay(delta_seconds: float, halflife_days: float) -> float:
    if halflife_days <= 0 or delta_seconds <= 0:
        return 1.0
    halflife_seconds = halflife_days * 86400.0
    return math.exp(-delta_seconds * math.log(2.0) / halflife_seconds)


def _component(linkage: str, weight: float | None) -> float:
    """Signed raw contribution from one (linkage, weight) row, before decay.

    `reinforces` is always positive, `contradicts` is always negative,
    regardless of how the caller signed the weight. Missing weight = 1.0.
    """
    base = 1.0 if weight is None else abs(float(weight))
    return base if linkage == "reinforces" else -base


def reinforcement_score(
    store: "Store",
    concept_id: int,
    *,
    now: float | None = None,
    halflife_days: float | None = None,
    cap: float | None = None,
) -> float:
    """Signed reinforcement signal for one concept. See module docstring."""
    return reinforcement_scores(
        store, [concept_id],
        now=now, halflife_days=halflife_days, cap=cap,
    ).get(concept_id, 0.0)


def reinforcement_scores(
    store: "Store",
    concept_ids: list[int],
    *,
    now: float | None = None,
    halflife_days: float | None = None,
    cap: float | None = None,
) -> dict[int, float]:
    """Batched form. One SELECT covers all concept_ids; rows are grouped
    and decayed in Python. Returns {cid: signal} for every concept passed
    in, including those with no reinforcement rows (value 0.0)."""
    if not concept_ids:
        return {}
    if now is None:
        now = time.time()
    if halflife_days is None:
        halflife_days = get_halflife_days()
    if cap is None:
        cap = get_cap()

    out: dict[int, float] = {cid: 0.0 for cid in concept_ids}

    placeholders = ",".join("?" * len(concept_ids))
    sql = (
        "SELECT el.concept_id, lt.name AS linkage, el.weight, e.created_at "
        "FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "JOIN entities e ON e.id = el.entity_id "
        f"WHERE el.concept_id IN ({placeholders}) "
        "  AND lt.name IN ('reinforces','contradicts')"
    )
    for row in store._read().execute(sql, list(concept_ids)).fetchall():
        cid = row["concept_id"]
        linkage = row["linkage"]
        weight = row["weight"]
        created_at = row["created_at"] if row["created_at"] is not None else now
        raw = _component(linkage, weight)
        decay = _decay(now - float(created_at), halflife_days)
        out[cid] += raw * decay

    if cap > 0:
        for cid, v in list(out.items()):
            if v > cap:
                out[cid] = cap
            elif v < -cap:
                out[cid] = -cap
    return out


def reinforcement_components(
    store: "Store",
    concept_id: int,
    *,
    now: float | None = None,
    halflife_days: float | None = None,
) -> list[dict]:
    """Per-row breakdown for `rmx memory score --explain`. Returns
    each contributing memory with its decayed contribution, ordered by
    descending |contribution| (largest movers first)."""
    if now is None:
        now = time.time()
    if halflife_days is None:
        halflife_days = get_halflife_days()

    sql = (
        "SELECT el.entity_id, e.name AS entity_name, e.kind AS entity_kind, "
        "       lt.name AS linkage, el.weight, e.created_at "
        "FROM entity_links el "
        "JOIN linkage_types lt ON lt.id = el.linkage_id "
        "JOIN entities e ON e.id = el.entity_id "
        "WHERE el.concept_id = ? AND lt.name IN ('reinforces','contradicts') "
        "ORDER BY e.created_at DESC"
    )
    rows = store._read().execute(sql, (concept_id,)).fetchall()
    out: list[dict] = []
    for r in rows:
        weight = r["weight"]
        created_at = r["created_at"] if r["created_at"] is not None else now
        raw = _component(r["linkage"], weight)
        decay = _decay(now - float(created_at), halflife_days)
        out.append({
            "entity_id": r["entity_id"],
            "entity_name": r["entity_name"],
            "entity_kind": r["entity_kind"],
            "linkage": r["linkage"],
            "weight": weight,
            "created_at": created_at,
            "age_days": (now - float(created_at)) / 86400.0,
            "decay": decay,
            "contribution": raw * decay,
        })
    out.sort(key=lambda d: -abs(d["contribution"]))
    return out


def rescore_factor(signal: float, *, alpha: float | None = None,
                   cap: float | None = None) -> float:
    """Multiplier applied to a per-concept contribution in a retrieval
    score. `1 + alpha · tanh(signal/cap)` keeps the multiplier in
    `[1-alpha, 1+alpha]`; at alpha=0 every multiplier is exactly 1.0
    (the ship-default no-op).
    """
    if alpha is None:
        alpha = get_alpha()
    if cap is None:
        cap = get_cap()
    if alpha == 0.0:
        return 1.0
    if cap <= 0:
        return 1.0 + alpha * math.tanh(signal)
    return 1.0 + alpha * math.tanh(signal / cap)


def per_doc_rescore(
    scores: dict[int, float],
    doc_concepts: dict[int, set[int] | list[int]],
    signals: dict[int, float],
    *,
    alpha: float | None = None,
    cap: float | None = None,
) -> dict[int, float]:
    """Per-document rescore: each doc's score is multiplied by
    `1 + alpha · tanh(Σ_{c in doc} signal(c) / cap)`. Docs whose
    concept membership is dominated by reinforced concepts get
    boosted; docs leaning on contradicted concepts get dampened.

    The per-concept signal is a confidence prior — it lives independent
    of which concepts the query happened to mention — so the right
    place to apply it is the doc, not the query unit.

    No-op when alpha resolves to 0.0.
    """
    if alpha is None:
        alpha = get_alpha()
    if alpha == 0.0:
        return dict(scores)
    out: dict[int, float] = {}
    for eid, score in scores.items():
        per_doc = 0.0
        for cid in doc_concepts.get(eid, ()):
            per_doc += signals.get(cid, 0.0)
        out[eid] = score * rescore_factor(per_doc, alpha=alpha, cap=cap)
    return out


def apply_to_concept_scores(
    contributions: dict[int, dict[int, float]],
    store: "Store",
    *,
    alpha: float | None = None,
    cap: float | None = None,
    halflife_days: float | None = None,
) -> dict[int, float]:
    """Fold per-(concept, entity) contributions into per-entity scores
    with reinforcement rescoring.

    `contributions[concept_id][entity_id] = raw_score_from_concept` —
    the caller breaks the per-concept share out so reinforcement can
    rescale individual concepts independently. Returns
    `{entity_id: rescaled_total}`.

    No-op (sum without rescaling) when alpha resolves to 0.
    """
    if alpha is None:
        alpha = get_alpha()
    if not contributions:
        return {}
    if alpha == 0.0:
        out: dict[int, float] = {}
        for per_entity in contributions.values():
            for eid, score in per_entity.items():
                out[eid] = out.get(eid, 0.0) + score
        return out

    signals = reinforcement_scores(
        store, list(contributions.keys()),
        halflife_days=halflife_days, cap=cap,
    )
    out2: dict[int, float] = {}
    for cid, per_entity in contributions.items():
        factor = rescore_factor(signals.get(cid, 0.0), alpha=alpha, cap=cap)
        for eid, score in per_entity.items():
            out2[eid] = out2.get(eid, 0.0) + score * factor
    return out2
