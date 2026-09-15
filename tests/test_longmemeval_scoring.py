"""LongMemEval Layer A scoring — the two haystack modes and what they cost.

RED first for task 7.3 (plan-7-longmemeval). Pure functions only: no store, no
`rmx` subprocess, no network. Retrieval correctness is the store's problem;
what is tested here is that the NUMBERS mean what the table says they mean.

Three things a benchmark can get wrong while still printing a plausible figure:

  * **Conflating the modes.** `restricted` (filtered to the question's own
    ~50-session haystack) and `union` (the whole 19,829-doc store) differ by an
    order of magnitude in difficulty. Quoting one as the other is the entire
    way a benchmark lies.
  * **Hiding the approximation.** `restricted` is a deep retrieve plus a
    post-hoc filter, because `ann_search(candidate_ids=...)` has no CLI flag
    and reaching past the CLI would make this a bespoke path. The gold session
    can fall outside the deep pool, which caps `restricted` below 1.0 for
    reasons that have nothing to do with rmx. That cap is the recall CEILING
    and it has to be reported beside every restricted number.
  * **A silently defaulted reranker.** `--rerank` flipped ON by default in the
    daemon at 0.42.0. A method that passes no flag measures whatever the
    environment happened to be, and every pre-0.42.0 row becomes incomparable
    without anyone noticing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval" / "production" / "longmemeval"))

import run as lme  # noqa: E402


def _q(qid, qtype, *, abstention=False):
    return {"question_id": qid, "question_type": qtype, "question": f"q {qid}",
            "abstention": abstention}


# ── the two modes ──────────────────────────────────────────────────────────

def test_restricted_drops_candidates_outside_the_questions_haystack():
    ranked = ["other_a", "gold", "other_b", "distractor"]
    out = lme.restrict(ranked, {"gold", "distractor"}, k=10)
    assert out == ["gold", "distractor"]


def test_restricted_preserves_the_retrieved_order():
    ranked = ["z", "gold", "y", "near"]
    assert lme.restrict(ranked, {"near", "gold"}, k=10) == ["gold", "near"]


def test_restricted_cuts_to_k_after_filtering_not_before():
    """Cutting first would throw away haystack members the filter would have
    promoted — the whole point of retrieving deep."""
    ranked = ["x1", "x2", "x3", "gold", "h2"]
    assert lme.restrict(ranked, {"gold", "h2"}, k=1) == ["gold"]
    assert lme.restrict(ranked, {"gold", "h2"}, k=2) == ["gold", "h2"]


def test_the_two_modes_produce_different_scores_on_the_same_retrieval():
    """If a change ever makes these agree, one of them stopped being itself."""
    questions = [_q("q1", "multi-session")]
    qrels = {"q1": ["gold"]}
    haystacks = {"q1": ["gold", "h2"]}
    # gold is 4th overall, but 1st among its own haystack
    deep = {"q1": ["x1", "x2", "x3", "gold", "h2"]}
    # `mrr` is reciprocal rank at max(ks) — the cutoff the table names.
    union = lme.score(deep, questions, qrels, haystacks, ks=[1, 10], mode="union")
    restricted = lme.score(deep, questions, qrels, haystacks, ks=[1, 10],
                           mode="restricted")
    assert union["overall"]["hit@1"] == 0.0
    assert restricted["overall"]["hit@1"] == 1.0
    assert union["overall"]["mrr"] == pytest.approx(0.25)
    assert restricted["overall"]["mrr"] == pytest.approx(1.0)


# ── the ceiling ────────────────────────────────────────────────────────────

def test_recall_ceiling_is_below_one_when_a_gold_falls_outside_the_deep_pool():
    questions = [_q("q1", "multi-session"), _q("q2", "multi-session")]
    qrels = {"q1": ["gold1"], "q2": ["gold2"]}
    deep = {"q1": ["gold1", "x"], "q2": ["x", "y"]}      # gold2 never retrieved
    assert lme.recall_ceiling(deep, questions, qrels) == pytest.approx(0.5)


def test_recall_ceiling_is_one_when_every_gold_is_somewhere_in_the_pool():
    questions = [_q("q1", "multi-session")]
    qrels = {"q1": ["gold"]}
    assert lme.recall_ceiling({"q1": ["a", "b", "gold"]}, questions, qrels) == 1.0


def test_restricted_never_scores_above_its_own_ceiling():
    questions = [_q(f"q{i}", "multi-session") for i in range(4)]
    qrels = {f"q{i}": [f"gold{i}"] for i in range(4)}
    haystacks = {f"q{i}": [f"gold{i}", "h"] for i in range(4)}
    deep = {"q0": ["gold0"], "q1": ["gold1"], "q2": ["x"], "q3": ["y"]}
    ceiling = lme.recall_ceiling(deep, questions, qrels)
    s = lme.score(deep, questions, qrels, haystacks, ks=[20], mode="restricted")
    assert s["overall"]["recall@20"] <= ceiling + 1e-9


def test_the_summary_carries_its_mode_and_depth_so_a_table_cannot_be_mislabelled():
    questions = [_q("q1", "multi-session")]
    s = lme.score({"q1": ["gold"]}, questions, {"q1": ["gold"]},
                  {"q1": ["gold"]}, ks=[1], mode="restricted", depth=200)
    assert s["_meta"]["mode"] == "restricted"
    assert s["_meta"]["depth"] == 200


# ── the slices ─────────────────────────────────────────────────────────────

def test_per_type_slices_partition_the_scored_set_exactly():
    questions = [_q("a", "multi-session"), _q("b", "temporal-reasoning"),
                 _q("c", "multi-session")]
    qrels = {q["question_id"]: ["g"] for q in questions}
    hs = {q["question_id"]: ["g"] for q in questions}
    deep = {q["question_id"]: ["g"] for q in questions}
    s = lme.score(deep, questions, qrels, hs, ks=[1], mode="union")
    per_type = sum(v["n"] for k, v in s.items()
                   if k not in ("overall", "abstention", "_meta"))
    assert per_type == s["overall"]["n"] == 3


def test_abstention_questions_are_scored_and_also_reported_as_their_own_slice():
    """All 30 `_abs` questions carry gold sessions present in their own
    haystack: retrieval is well defined and abstaining is the answer model's
    decision. Dropping them would silently shrink the denominator."""
    questions = [_q("a", "multi-session"), _q("b_abs", "multi-session", abstention=True)]
    qrels = {"a": ["g"], "b_abs": ["g2"]}
    hs = {"a": ["g"], "b_abs": ["g2"]}
    deep = {"a": ["g"], "b_abs": ["g2"]}
    s = lme.score(deep, questions, qrels, hs, ks=[1], mode="union")
    assert s["overall"]["n"] == 2           # scored, not excluded
    assert s["abstention"]["n"] == 1        # and visible on its own


def test_a_question_with_no_gold_is_not_scored_as_a_zero():
    questions = [_q("a", "multi-session"), _q("b", "multi-session")]
    s = lme.score({"a": ["g"], "b": []}, questions, {"a": ["g"]},
                  {"a": ["g"], "b": []}, ks=[1], mode="union")
    assert s["overall"]["n"] == 1
    assert s["overall"]["hit@1"] == 1.0


# ── the reranker flag ──────────────────────────────────────────────────────

@pytest.mark.parametrize("method", sorted(
    m for m in getattr(lme, "METHODS", {}) if m.startswith("recall")))
def test_every_recall_method_states_its_rerank_flag_explicitly(method):
    """0.42.0 flipped the daemon default ON. A method that passes no flag
    measures the environment, not the surface."""
    argv = lme.METHODS[method].argv("a query", k=20)
    assert ("--rerank" in argv) ^ ("--no-rerank" in argv), argv


def test_every_method_requests_json_so_a_parse_failure_cannot_look_like_a_miss():
    for name, m in lme.METHODS.items():
        argv = m.argv("a query", k=20)
        assert "--json" in argv or "--format" in argv, (name, argv)


# ── the metrics themselves ─────────────────────────────────────────────────

def test_metrics_match_hand_computed_values():
    questions = [_q("q1", "multi-session")]
    qrels = {"q1": ["g1", "g2"]}
    hs = {"q1": ["g1", "g2", "a", "b", "c"]}
    deep = {"q1": ["a", "g1", "b", "g2", "c"]}
    s = lme.score(deep, questions, qrels, hs, ks=[1, 2, 5], mode="union")
    o = s["overall"]
    assert o["mrr"] == pytest.approx(0.5)          # first gold at rank 2
    assert o["hit@1"] == 0.0
    assert o["hit@2"] == 1.0
    assert o["recall@2"] == pytest.approx(0.5)     # 1 of 2 golds in top 2
    assert o["recall@5"] == pytest.approx(1.0)
