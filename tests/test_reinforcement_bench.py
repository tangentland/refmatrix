"""Phase B5 benchmark regression.

Pins the synthetic bench's headline numbers so future scoring-stack
changes can't quietly regress reinforcement's effect on retrieval
ranking. The bench is documented in `eval/reinforcement_bench.py`;
this file just runs it and asserts the deltas.

Scenario summary:
- 12 (query, correct_doc, distractor_doc) tuples.
- Distractor is inserted FIRST, so the BM25 tie-break (entity_id
  ascending) hands it the win at baseline → MRR@10 = 0.5.
- With reinforcement enabled and memories seeded on `concept_pos`,
  the per-doc rescore lifts the correct doc above the tie → MRR@10 = 1.0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_EVAL = _REPO / "eval"


@pytest.fixture
def bench():
    pytest.importorskip("duckdb")
    pytest.importorskip("Stemmer", reason="rmx_retriever optional stemmer")
    import importlib
    # eval/ uses bare-name sibling imports (`from metrics import ...`), so it
    # must be on sys.path to import the bench. But eval/datasets.py SHADOWS the
    # HuggingFace `datasets` package — leaving eval/ on sys.path permanently
    # (as a module-level insert did) breaks sentence_transformers in every
    # later test (embedder/recall/dense) with
    # `ImportError: cannot import name 'Dataset' from 'datasets'`. Scope the
    # path hack to the import and restore it — same pattern as the js/ts
    # extractor fixtures.
    sys.path.insert(0, str(_EVAL))
    try:
        mod = importlib.import_module("reinforcement_bench")
    finally:
        try:
            sys.path.remove(str(_EVAL))
        except ValueError:
            pass
    return mod


def test_baseline_alpha_zero_loses_on_id_tiebreak(bench):
    metrics, _ = bench.run_once(alpha=0.0)
    # BM25 ties, lower entity_id wins, distractor was inserted first.
    assert metrics["MRR@10"] == pytest.approx(0.5)
    assert metrics["Recall@1"] == pytest.approx(0.0)


def test_reinforcement_rescues_every_query(bench):
    metrics, _ = bench.run_once(alpha=0.3)
    assert metrics["MRR@10"] == pytest.approx(1.0)
    assert metrics["Recall@1"] == pytest.approx(1.0)
    assert metrics["nDCG@10"] == pytest.approx(1.0)


def test_alpha_zero_never_regresses_baseline(bench):
    """The ADR forbids regressing the symbolic-only baseline. Two
    runs at alpha=0 with identical inputs must produce identical
    rankings."""
    a, _ = bench.run_once(alpha=0.0)
    b, _ = bench.run_once(alpha=0.0)
    for k in a:
        assert a[k] == pytest.approx(b[k])
