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
    """Tokenize an NL query into content-search terms for `content_rank`:
    whitespace split, drop sub-2-char tokens, dedupe (case-insensitive).
    Mirrors `context._ref_terms`; kept local so recall.py doesn't import a
    context-private helper. Per-term variant/canonical expansion happens
    inside `Store.content_rank`."""
    out: list[str] = []
    seen: set[str] = set()
    for tok in re.split(r"\s+", (query or "").strip()):
        tok = tok.strip()
        if len(tok) < 2 or tok.lower() in seen:
            continue
        seen.add(tok.lower())
        out.append(tok)
    return out


def hybrid_memory_recall(
    store: Store,
    embedder,
    query: str,
    *,
    k: int = 20,
    kinds: Sequence[str] | None = None,
    rrf_k: int = 60,
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
    )


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
