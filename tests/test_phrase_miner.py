"""The `phrase/*` miner: skip-pair identity and its concept-table shape.

Phrases are default-OFF (see `phrases_enabled` for the MemAware numbers that
settled it), but the miner stays in the tree and these pin the two properties
that made it the best-measured variant, plus the store rule that keeps its
keys out of the identifier machinery.
"""

from __future__ import annotations

from refmatrix.ingest import text_phrases
from refmatrix.store import _concept_variants


def test_pairs_are_order_invariant():
    """`load model` and `model ... load` are the same key.

    Alphabetizing was worth ~7% more recurring keys on the measured corpora,
    for free -- word order is not part of what a co-occurrence means.
    """
    a = text_phrases("model wraps loader")
    b = text_phrases("loader wraps model")
    assert set(a) == set(b)
    assert all("_" in k for k in a)
    assert all(k == "_".join(sorted(k.split("_"))) for k in a)


def test_contiguity_is_not_required():
    """The point of skip-pairs: a paraphrase that shares no trigram in any
    order still shares its pairs. Contiguity was the expensive constraint --
    dropping it cut the hapax rate 87.1% -> 82.8% on docstrings."""
    a = text_phrases("loads the sentence transformer model")
    b = text_phrases("the model, which is a sentence transformer")
    assert "sentence_transformer" in a
    assert "sentence_transformer" in b


def test_window_bounds_the_pairing():
    """Words further apart than the window never pair, so the signal stays
    local. Widening to 6 measured WORSE than 4 (more keys, same hapax)."""
    got = text_phrases("alpha beta gamma delta epsilon", stop=frozenset())
    assert "alpha_beta" in got
    assert "alpha_delta" in got          # gap 3, inside window=4
    assert "alpha_epsilon" not in got    # gap 4, outside


def test_stopwords_and_punctuation_break_the_run():
    """A stopword ENDS a run rather than being skipped over: skipping would
    pair words that were never near each other in meaning. Measured, stripping
    stopwords instead RAISED the hapax rate (88.9% -> 90.7%)."""
    got = text_phrases("store the handle. returns nothing",
                       stop=frozenset({"the"}))
    assert "handle_store" not in got     # `the` broke it
    assert "handle_returns" not in got   # `.` broke it


def test_phrase_keys_skip_identifier_variant_expansion():
    """`phrase/a_b` is a generated pair identity, not an identifier anyone
    types. Expanding it wrote `phrase/a b` + `phrase/a-b` alias rows carrying
    no `mentions` -- pure bloat in the concept table and in the df statistics
    the noise pruner reads."""
    canon, variants = _concept_variants("phrase/load_model")
    assert canon == "phrase/load_model"
    assert variants == []
    # A real multi-word concept still expands.
    canon, variants = _concept_variants("load_model")
    assert canon == "load_model"
    assert set(variants) == {"load model", "load-model"}
