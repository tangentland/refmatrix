"""Lift-scored association: expand a prompt's concepts by what SHARES their
documents, weighted by how surprising the sharing is.

Why this exists next to `ppr.py`, which already reaches the same neighborhood:
a PPR walk from a seed concept goes concept -> documents -> concepts, so the
co-occurrence neighborhood is already in its frontier. What it has no notion of
is *specificity*. Mass accumulates on whatever is central, so a concept that
co-occurs with the seed because it co-occurs with EVERYTHING scores well. Under
a hard `max_concepts` cap, those slots are the whole product — five bundles get
emitted and nothing else is reachable — so which five you pick is the ranking
that matters.

This scores a candidate by lift instead:

    lift(c) = P(c | prompt documents) / P(c)
            = (co(c) / |A|) / (df(c) / N)

`co` is how many of the prompt's documents mention `c`, `df` is how many
documents mention it at all, `N` is the partition's document count. A hub with
a huge `df` needs a proportionally huge overlap to score; a rare concept
concentrated in exactly the prompt's documents scores high on a handful of
hits. That is the correction PPR mass does not make.

The reachability caveat is worth stating plainly, because the phrase layer died
on exactly this point (see `ingest.phrases_enabled`): association does not
enlarge the candidate POOL relative to PPR — both reach the same 2-hop set. It
re-selects within the truncated top-k. So it can only move a metric through
which concepts win the cap, and a k large enough to hold everything would
erase the difference.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from refmatrix.store import Store


# A candidate must share at least this many documents with the prompt. At 1 a
# single accidental overlap can win on lift alone, because a df=1 concept that
# happens to sit in one of the prompt's documents scores N/|A| — the maximum
# the formula can produce, off one coincidence.
DEFAULT_MIN_CO = 2

# Hub cull: a concept mentioned by more than this FRACTION of the partition
# carries no locating information even if its lift survives. Cheap guard on
# the same failure `promote.py` documents for raw co-occurrence weight.
DEFAULT_MAX_DF_RATIO = 0.25


def _min_co() -> int:
    try:
        return max(1, int(os.environ.get("RMX_ASSOC_MIN_CO", "") or DEFAULT_MIN_CO))
    except ValueError:
        return DEFAULT_MIN_CO


def _max_df_ratio() -> float:
    try:
        v = float(os.environ.get("RMX_ASSOC_MAX_DF", "") or DEFAULT_MAX_DF_RATIO)
    except ValueError:
        return DEFAULT_MAX_DF_RATIO
    return v if 0.0 < v <= 1.0 else DEFAULT_MAX_DF_RATIO


# Cap on the prompt's document set before the group-by. A prompt whose concepts
# span most of the corpus produces an anchor that is not "the prompt's
# documents" in any useful sense, and the IN-list grows with it. Capped runs
# are REPORTED (`truncated` in the result meta), never silently trimmed.
DEFAULT_MAX_ANCHOR = 4000


# Minimum number of prompt concepts a document must carry to join the anchor.
# The union of every seed's documents is NOT "the prompt's documents": on prose
# `match_concepts` hands back function words, and their union is most of the
# corpus. When the anchor is the corpus, co(c)/|A| == df(c)/N for every
# candidate, lift collapses to 1.0 across the board, and whatever tie-breaks
# ranks the COMMONEST words -- the exact bias this module exists to remove.
# Requiring 2 makes the anchor "documents this prompt is jointly about", which
# is the same corrective `ppr.seed_coverage` applies to seeds.
DEFAULT_MIN_COVERAGE = 2


def anchor_documents(
    store: "Store", seed_ids: list[int], mentions_lid: int,
    *, max_anchor: int = DEFAULT_MAX_ANCHOR,
    min_coverage: int = DEFAULT_MIN_COVERAGE,
) -> tuple[list[int], bool]:
    """Documents carrying at least `min_coverage` of the prompt's concepts.

    Falls back to the plain union when nothing clears the bar (a one-concept
    prompt, or seeds that never share a document), so the caller still gets an
    anchor rather than an empty result.
    """
    from pyroaring import BitMap
    cover: dict[int, int] = {}
    acc = BitMap()
    for sid in seed_ids:
        try:
            bm = store.load_bitmap("mentions", sid)
        except Exception:
            continue
        acc |= bm
        for eid in bm:
            cover[eid] = cover.get(eid, 0) + 1
    ids = [eid for eid, c in cover.items() if c >= min_coverage]
    if not ids:
        ids = list(acc)
    ids.sort(key=lambda e: (-cover.get(e, 0), e))
    if len(ids) > max_anchor:
        return ids[:max_anchor], True
    return ids, False


def rank_assoc_for_prompt(
    store: "Store",
    seed_ids: list[int],
    *,
    k: int = 10,
    include_seeds: bool = True,
    kinds: "tuple[str, ...] | None" = ("concept",),
    min_co: "int | None" = None,
    max_df_ratio: "float | None" = None,
    max_anchor: int = DEFAULT_MAX_ANCHOR,
) -> list[dict]:
    """Seeds plus their highest-lift co-occurring concepts.

    Returns `{id, name, kind, score, seed}` dicts, best-first — the same shape
    `ppr.rank_related_for_prompt` returns, so the scan-prompt rank modes stay
    interchangeable. Seeds sort first when `include_seeds`, because the prompt
    naming a concept outranks an inference about it.
    """
    if not seed_ids:
        return []
    min_co_v = _min_co() if min_co is None else min_co
    max_df_v = _max_df_ratio() if max_df_ratio is None else max_df_ratio

    con = store._connect()
    try:
        mlid = store.get_linkage_id("mentions")
    except Exception:
        return []

    anchor, truncated = anchor_documents(
        store, seed_ids, mlid, max_anchor=max_anchor)
    if not anchor:
        return []

    df = store.concept_df(mlid)
    n_docs = store._mentions_bm25_stats(mlid)[0]
    if n_docs <= 0:
        return []

    in_list = ",".join("?" * len(anchor))
    try:
        rows = con.execute(
            f"SELECT concept_id, COUNT(*) FROM entity_links "
            f"WHERE linkage_id=? AND entity_id IN ({in_list}) "
            f"GROUP BY concept_id",
            [mlid, *anchor],
        ).fetchall()
    except Exception:
        return []

    seed_set = set(seed_ids)
    a_len = float(len(anchor))
    df_cap = max_df_v * n_docs
    scored: list[tuple[float, int]] = []
    for r in rows:
        cid = int(r[0])
        if cid in seed_set:
            continue
        co = int(r[1] or 0)
        if co < min_co_v:
            continue
        d = df.get(cid, 0)
        if d <= 0 or d > df_cap:
            continue
        lift = (co / a_len) / (d / float(n_docs))
        if lift <= 1.0:
            continue
        # Support is a GATE (`min_co`), never a multiplier. Multiplying lift by
        # a support term re-elects the hubs: when the anchor is loose every
        # lift sits near 1.0 and the multiplier alone decides, which ranks the
        # commonest words first. Measured that exact failure before the
        # coverage anchor went in.
        scored.append((lift, co, cid))
    # Lift SATURATES: any concept whose documents lie entirely inside the
    # anchor scores N/|A| no matter how rare it is, so the rare tail arrives as
    # one big tie. Support breaks that tie -- but only as a secondary key.
    # Promoting it to a multiplier is what re-elected the hubs earlier.
    scored.sort(key=lambda it: (-it[0], -it[1], it[2]))

    rows_out: list[tuple[float, int, int, bool]] = [
        (lift, co, cid, False) for lift, co, cid in scored]
    if include_seeds:
        rows_out.extend(
            (sc, 0, sid, True)
            for sid, sc in _seed_scores(store, seed_ids, df, n_docs).items()
        )
    rows_out.sort(key=lambda it: (-it[0], -it[1], it[2]))

    out: list[dict] = []
    for score, _co, cid, is_seed in rows_out:
        if len(out) >= k:
            break
        e = store.get_entity_by_id(cid)
        if e is None or (kinds and e.kind not in kinds):
            continue
        if not is_seed and getattr(e, "noise", False):
            continue
        out.append({"id": e.id, "name": e.name, "kind": e.kind,
                    "score": float(score), "seed": is_seed})
    if truncated and out:
        out[0] = dict(out[0], anchor_truncated=True)
    return out[:k] if k > 0 else out


def _seed_scores(
    store: "Store", seed_ids: list[int], df: "dict[int, int]", n_docs: int,
) -> "dict[int, float]":
    """Score each seed by how well it coheres with the REST of the prompt.

    A seed cannot be scored against the full anchor -- its own documents are
    inside it, so the answer is always 1.0 by construction. Scored against the
    OTHER seeds' documents instead, the same lift question becomes meaningful
    and discriminating: on a prose corpus `match_concepts` hands back every
    common word as a concept (`first`, `know`, `still` alongside `bed` and
    `sneakers`), and the junk seeds are exactly the ones that co-occur with the
    rest of the prompt no better than chance.

    Without this, seeds sorted ahead of every association at their salience
    order and consumed the whole `max_concepts` cap -- the selection this
    module exists to change never got a slot.
    """
    from pyroaring import BitMap
    docs: dict[int, "BitMap"] = {}
    for sid in seed_ids:
        try:
            docs[sid] = store.load_bitmap("mentions", sid)
        except Exception:
            continue
    out: dict[int, float] = {}
    for sid, own in docs.items():
        others = BitMap()
        for oid, bm in docs.items():
            if oid != sid:
                others |= bm
        if len(others) == 0 or len(own) == 0:
            out[sid] = 0.0
            continue
        d = df.get(sid, len(own)) or len(own)
        co = len(own & others)
        if co <= 0:
            out[sid] = 0.0
            continue
        out[sid] = (co / float(len(others))) / (d / float(n_docs))
    return out
