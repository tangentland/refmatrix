"""Corpus-modal salience and the candidate tokenizer — both default-OFF.

These pin the DEFAULTS, because the measurement said the shipped configuration
wins (eval/memaware/REPORT.md). The load-bearing property is the first test:
whatever the blend does in prose mode, the default path must remain exactly the
expression that shipped, so no code store can move.
"""

from __future__ import annotations

import math

from refmatrix import scan


def _original(central: float, df: int, token: str, name: str) -> float:
    """The pre-modal salience expression, written out independently."""
    idf = 1.0 / math.log2(df + 2) if df > 0 else 0.3
    ns_bonus = 0.5 if "/" in name else 0.0
    return central + 1.5 * idf + scan._token_shape_score(token) + ns_bonus


def test_default_salience_is_exactly_the_original_expression():
    """code_frac=1.0 must reduce the blend to the original formula.

    `w_central = 0.3 + 0.7*cf` and the specificity blend both collapse at
    cf=1.0. If this drifts, every code store's scan-prompt ranking moves.
    """
    for df in (1, 16, 22, 91, 472, 850, 5000):
        for token, name in (("sneakers", "sneakers"), ("parse_url", "parse_url"),
                            ("foo", "keyword/foo")):
            blended = scan._salience_from_parts(
                central=1.234, df=df, token=token, name=name,
                code_frac=1.0, n_docs=2940)
            assert abs(blended - _original(1.234, df, token, name)) < 1e-12


def test_prose_mode_ranks_the_rare_term_above_the_common_one():
    """The inversion this was built to fix: on prose, `central` (0..2.5) swamps
    `1.5*idf` (~0.45), so salience RISES with df. Measured on eval/memaware,
    `sneakers` df=22 scored 1.43 while `there` df=864 scored 2.65."""
    rare = scan._salience_from_parts(central=1.10, df=22, token="sneakers",
                                     name="sneakers", code_frac=0.0, n_docs=2940)
    common = scan._salience_from_parts(central=2.50, df=864, token="there",
                                       name="there", code_frac=0.0, n_docs=2940)
    assert rare > common
    # ...and the default (code) mode reproduces the inversion, on purpose.
    rare_c = scan._salience_from_parts(central=1.10, df=22, token="sneakers",
                                       name="sneakers", code_frac=1.0, n_docs=2940)
    common_c = scan._salience_from_parts(central=2.50, df=864, token="there",
                                         name="there", code_frac=1.0, n_docs=2940)
    assert common_c > rare_c


def test_trailing_punctuation_is_kept_by_default(monkeypatch):
    """Stripping it is correct by inspection and NEGATIVE by measurement
    (concept-path MRR 0.069 -> 0.052), so the default keeps it."""
    monkeypatch.delenv("RMX_SCAN_STRIP_PUNCT", raising=False)
    assert "first." in scan.extract_candidates("move the items first.")
    monkeypatch.setenv("RMX_SCAN_STRIP_PUNCT", "1")
    got = scan.extract_candidates("move the items first.")
    assert "first" in got and "first." not in got


def test_strip_preserves_dotted_paths(monkeypatch):
    """Interior dots are structure, trailing ones are grammar."""
    monkeypatch.setenv("RMX_SCAN_STRIP_PUNCT", "1")
    assert "os.path" in scan.extract_candidates("we import os.path.")


def test_shape0_floor_fades_with_corpus_mode():
    """In prose every token is shape-0, so a gate that treats shape-0 as
    second-class has nothing left to discriminate."""
    assert scan._shape0_floor(1.0) == scan.SHAPE0_SALIENCE_FLOOR
    assert scan._shape0_floor(0.0) == 0.0
