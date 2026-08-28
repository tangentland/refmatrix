"""Hybrid retrieval entry point.

Combines refmatrix's symbolic retrieval (BM25 + linkage coverage +
identifier expansion) with Lance dense ANN. Three modes:

- dense-only      : `dense_recall(...)` — pure ANN, no symbolic.
- symbolic-only   : existing query/context paths; nothing here.
- hybrid          : `hybrid_recall(...)` — RRF fusion of a caller-
                    supplied symbolic ranking with the dense ANN
                    output. Optional bitmap pre-filter narrows the
                    ANN candidate pool BEFORE the distance search,
                    which is the cheap precision lever (microsecond
                    AND on roaring bitmaps + sub-100ms ANN).

The dense path is best-effort: if the [dense] extra isn't installed
or no vectors have been indexed yet, callers should fall back to the
symbolic ranking. `dense_available()` is the cheap probe.

Phase A7 surface; Phase B's `rmx memory recall` is the CLI consumer.
"""
from __future__ import annotations

import re
from typing import Sequence

from refmatrix.query import fuse_rrf
from refmatrix.store import Store


def dense_available() -> bool:
    """Cheap probe — does this environment have the [dense] extra
    available? Lets callers degrade quietly to symbolic-only when
    pylance / sentence-transformers isn't installed."""
    try:
        import importlib.util as _u
        return all(
            _u.find_spec(name) is not None
            for name in ("lance", "numpy", "sentence_transformers")
        )
    except Exception:
        return False


def dense_recall(
    store: Store,
    embedder,
    query: str,
    *,
    k: int = 20,
    kinds: Sequence[str] | None = None,
    candidate_ids: Sequence[int] | None = None,
) -> list[tuple[int, float]]:
    """Pure dense ANN. `embedder` must already be loaded. Returns
    `[(entity_id, distance)]` ascending by L2."""
    if not query:
        return []
    v = embedder.embed_texts([query])[0]
    return store.ann_search(
        v, k=k, dim=embedder.dim, kinds=kinds,
        candidate_ids=candidate_ids,
    )


def hybrid_recall(
    store: Store,
    embedder,
    query: str,
    *,
    k: int = 20,
    kinds: Sequence[str] | None = None,
    symbolic_hits: Sequence[int] | None = None,
    candidate_ids: Sequence[int] | None = None,
    rrf_k: int = 60,
) -> list[tuple[int, float]]:
    """RRF-fused hybrid retrieval.

    Inputs:
        symbolic_hits: caller-ranked entity ids (best-first) from
            the existing scoring stack. None = symbolic side
            contributes nothing.
        candidate_ids: bitmap-derived id set used as a PRE-FILTER
            on the ANN scan. None = no pre-filter. Empty list =
            ANN returns nothing (the symbolic side may still
            contribute).

    Output: `[(entity_id, fused_score)]` descending by fused RRF
    score. RRF inputs are rank-based, so distance magnitudes from
    Lance don't need calibrating against symbolic scores.
    """
    lists: list[list[int]] = []
    if symbolic_hits:
        lists.append(list(symbolic_hits))

    dense_hits = dense_recall(
        store, embedder, query,
        k=max(k, rrf_k),  # widen the ANN pool a bit so fusion has
                          # room to upvote cross-list winners.
        kinds=kinds,
        candidate_ids=candidate_ids,
    )
    if dense_hits:
        lists.append([eid for eid, _d in dense_hits])

    if not lists:
        return []
    fused = fuse_rrf(lists, k=rrf_k)
    return fused[:k]


def _content_terms(query: str) -> list[str]:
    """Tokenize an NL query into content-search terms for `content_rank`.

    Was a local copy that claimed to mirror `context._ref_terms` but dropped
    no stopwords, so `memory recall --fuse` sent `why`/`did`/`the`/`by` into
    BM25 as query terms. Now the same tokenizer every read surface uses."""
    from refmatrix.terms import content_terms
    return content_terms(query)


def hybrid_memory_recall(
    store: Store,
    embedder,
    query: str,
    *,
    k: int = 20,
    kinds: Sequence[str] | None = None,
    rrf_k: int = 60,
    candidate_ids: Sequence[int] | None = None,
) -> list[tuple[int, float]]:
    """Dense ⊕ symbolic RRF fusion for `rmx memory recall`.

    Runs `store.content_rank` (BM25 over the mentions forward index — rewards
    rare, exact query terms) AND the dense ANN, then RRF-fuses via
    `hybrid_recall`. Closes the gap where pure dense missed a lexically-exact
    memory because a 384-dim vector dilutes rare terms into topical space
    (e.g. "grep backstop protected query concept" — symbolic nailed it, dense
    didn't). `content_rank` is partition-scoped, so the CALLER must already
    have `store` bound to the target memory partition.

    Returns `[(entity_id, fused_score)]` descending by RRF score."""
    terms = _content_terms(query)
    # Cull the dense search space with the symbolic side's own answer. See
    # `concept_prefilter` for why this returns None rather than [] when it
    # cannot help.
    symbolic_hits: list[int] = []
    if terms:
        symbolic_hits = [
            eid for eid, _score in store.content_rank(
                terms,
                kinds=list(kinds) if kinds else ["memory"],
                limit=max(k, rrf_k),
            )
        ]
    return hybrid_recall(
        store, embedder, query,
        k=k, kinds=kinds, symbolic_hits=symbolic_hits, rrf_k=rrf_k,
        candidate_ids=candidate_ids,
    )


def concept_prefilter(
    store: Store,
    query: str,
    *,
    linkage: str = "mentions",
    kinds: "Sequence[str] | None" = None,
    min_candidates: int = 5,
    max_fraction: float = 0.5,
) -> "list[int] | None":
    """Derive a dense-ANN candidate set from the query's own concepts.

    The pieces have been here since Phase A7 — `bitmap_prefilter` unions the
    concept bitmaps, `ann_search(candidate_ids=...)` restricts the scan, and
    the module docstring calls it "the cheap precision lever". Nothing ever
    derived the concept list automatically: `rmx recall --concept` made the
    caller name them by hand, and `memory recall` never passed one at all. So
    the dense side has always searched the whole partition while the symbolic
    side knew exactly which documents mention the query's terms.

    Returns None (meaning "do not filter") rather than an empty list in every
    case where filtering would be wrong or worthless:

    * no concept resolved — an empty `candidate_ids` makes `ann_search` return
      NOTHING, so a query whose terms are absent from the graph would silently
      lose its dense half. That is the failure mode this guard exists for.
    * fewer than `min_candidates` — too tight to trust; a couple of documents
      is not a candidate pool, it is a guess.
    * more than `max_fraction` of the partition — filtering to most of the
      corpus costs a set union and buys no precision.

    Uses `scan.match_concepts`, so the query is tokenized, stoplisted and
    canonical-expanded by the same code every other surface uses.
    """
    if not query:
        return None
    # Resolve cheaply and by INDEX only. `scan.match_concepts` was the obvious
    # reuse, but it ends its ladder with `name LIKE '%/<cand>'` — a leading
    # wildcard, so a full scan of the concept table per candidate token. That
    # is fine for a once-per-prompt hook and not fine on the recall hot path:
    # wired that way it made the eval daemon stop answering. `resolve_concept_ids`
    # hits `idx_entities_canonical` and covers the case that matters here.
    try:
        from refmatrix.scan import extract_candidates
        from refmatrix.terms import STOPWORDS
        cands = [c for c in extract_candidates(query)
                 if c.lower() not in STOPWORDS]
    except Exception:
        return None
    if not cands:
        return None
    cids: list[int] = []
    seen: set[int] = set()
    for cand in cands:
        try:
            for cid in store.resolve_concept_ids(cand):
                if cid not in seen:
                    seen.add(cid)
                    cids.append(cid)
        except Exception:
            continue
    if not cids:
        return None
    ids = bitmap_prefilter(store, cids, linkage=linkage)
    if len(ids) < min_candidates:
        return None
    # Compare against the population actually being SEARCHED, not against
    # every row in the partition. Counting all entities includes tens of
    # thousands of bare concept nodes that the ANN never ranks, which inflates
    # the denominator so far that the guard can never fire: measured on a
    # 1307-document corpus, a union covering 947 documents (72%) still looked
    # like a tiny fraction of "all entities" and was passed through as a
    # useful cull. A filter that keeps three-quarters of the corpus costs a
    # set union and buys nothing.
    kinds = list(kinds) if kinds else ["code", "doc", "memory"]
    try:
        in_list = ",".join("?" * len(kinds))
        total = store._connect().execute(
            f"SELECT count(*) FROM entities WHERE partition_id = ? "
            f"AND kind IN ({in_list})",
            [store._partition_id, *kinds],
        ).fetchone()[0] or 0
    except Exception:
        total = 0
    if total and len(ids) > total * max_fraction:
        return None
    return ids


def bitmap_prefilter(
    store: Store,
    concepts: Sequence[int],
    linkage: str = "mentions",
) -> list[int]:
    """Build a candidate-id set by OR-ing the bitmaps for each concept
    under `linkage`. Cheap (microseconds of roaring set ops) — the
    typical pre-filter for hybrid_recall when the caller has parsed
    query concepts already.

    Empty `concepts` returns an empty list. Concepts with no
    bitmap contribute nothing.
    """
    if not concepts:
        return []
    from pyroaring import BitMap

    union: BitMap = BitMap()
    for cid in concepts:
        try:
            bm = store.load_bitmap(linkage, cid)
        except Exception:
            continue
        union |= bm
    return list(union)
