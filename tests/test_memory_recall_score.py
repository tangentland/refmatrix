"""Focused tests for `memory recall` score honesty (audit-2 #1).

Bug: the daemon ANN op returns raw L2 *distance* (ascending = best), which
`memory recall` rendered under a column literally headed "score" — so the
numbers ASCENDED while rank DESCENDED (rank1=0.6947 < rank3=0.6989). Column
and order disagreed = user-visible-broken.

Fix: `_ann_similarity` converts the L2 distance over L2-normalized vectors to
cosine similarity (higher = better), so the displayed `score` decreases
monotonically with rank. These tests pin the conversion + the monotonicity
invariant without needing a daemon or embedder."""
from __future__ import annotations

import math

import numpy as np

from refmatrix.cli import _ann_similarity


def test_known_values():
    """Anchor points of cos = 1 − d²/2 for unit vectors."""
    assert _ann_similarity(0.0) == 1.0                 # identical → sim 1
    assert math.isclose(_ann_similarity(math.sqrt(2)), 0.0, abs_tol=1e-9)  # orthogonal
    assert math.isclose(_ann_similarity(2.0), -1.0, abs_tol=1e-9)          # opposite


def test_monotonic_decreasing_so_column_agrees_with_rank():
    """Ascending distance (the order ANN returns best-first) must map to
    STRICTLY descending similarity — the property that makes the score column
    agree with the row order."""
    distances = [0.6947, 0.6968, 0.6989, 0.7309, 0.7353]   # the live repro
    sims = [_ann_similarity(d) for d in distances]
    assert sims == sorted(sims, reverse=True)              # descending
    assert all(a > b for a, b in zip(sims, sims[1:]))      # strictly


def test_matches_true_cosine_for_unit_vectors():
    """The converted score IS the real cosine similarity, so labeling it
    `score` is honest (not an arbitrary monotone transform)."""
    rng = np.random.default_rng(0)
    for _ in range(50):
        a = rng.standard_normal(384).astype("float32")
        b = rng.standard_normal(384).astype("float32")
        a /= np.linalg.norm(a)
        b /= np.linalg.norm(b)
        l2 = float(np.linalg.norm(a - b))
        cos = float(np.dot(a, b))
        assert math.isclose(_ann_similarity(l2), cos, abs_tol=1e-5)


def test_better_hit_scores_higher_than_worse_hit():
    """A closer (smaller-distance) hit always outscores a farther one."""
    near = _ann_similarity(0.30)
    far = _ann_similarity(0.95)
    assert near > far
