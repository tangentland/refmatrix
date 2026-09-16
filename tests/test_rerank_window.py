"""bug-032: the cross-encoder only ever read the first 2048 chars.

On `longmemeval_oracle` (896 answer-bearing turns) the median answer offset is
0, p75 3,268, p90 8,117 — and 331/896 = 36.9% sit past 2048, invisible to the
reranker. The BOUND is sound (a cross-encoder truncates at ~512 tokens anyway).
The STRATEGY is not: head truncation assumes a document's head is what the model
needs to rank it, which is true for a curated GMD memory with a title and a lead
and false for a chat transcript that has neither.

These tests cover the window: same bound, same per-pair cost, text taken from
where the query actually occurs.
"""
from __future__ import annotations

import pytest

from refmatrix import reranker as rr


def _doc(answer_at: int, term: str = "sourdough") -> str:
    filler = "the meeting covered logistics and timing. "
    head = (filler * ((answer_at // len(filler)) + 1))[:answer_at]
    return head + f"I finally baked the {term} starter loaf. " + filler * 40


def test_a_hit_past_the_bound_is_inside_the_window():
    text = _doc(6000)
    win = rr.window_doc(text, "how did the sourdough turn out", limit=2048)
    assert "sourdough" in win
    assert "sourdough" not in text[:2048], "the fixture must reproduce the bug"


def test_the_window_never_exceeds_the_bound():
    for size in (3_000, 12_000, 60_000):
        win = rr.window_doc(_doc(size // 2), "sourdough", limit=2048)
        assert len(win) <= 2048, (size, len(win))


def test_a_doc_with_no_query_term_falls_back_to_the_head():
    text = _doc(6000)
    assert rr.window_doc(text, "quarterly revenue forecast", limit=2048) \
        == text[:2048]


def test_a_doc_shorter_than_the_bound_is_returned_whole():
    text = "short note about the sourdough starter"
    assert rr.window_doc(text, "sourdough", limit=2048) == text


def test_no_query_is_head_truncation():
    text = _doc(6000)
    assert rr.window_doc(text, "", limit=2048) == text[:2048]
    assert rr.window_doc(text, None, limit=2048) == text[:2048]


def test_term_order_does_not_move_the_window():
    text = _doc(6000)
    a = rr.window_doc(text, "sourdough starter loaf", limit=1024)
    b = rr.window_doc(text, "loaf starter sourdough", limit=1024)
    assert a == b


def test_the_window_is_off_switchable(monkeypatch):
    """The A/B has to be runnable on a deployed binary without a redeploy."""
    text = _doc(6000)
    monkeypatch.setenv("RMX_RERANK_WINDOW", "0")
    assert rr.window_doc(text, "sourdough", limit=2048) == text[:2048]


# ---- both model paths go through it --------------------------------------

def test_the_in_process_reranker_windows(monkeypatch):
    seen = {}

    class _M:
        def predict(self, pairs, show_progress_bar=False):
            seen["pairs"] = pairs
            return [0.5] * len(pairs)

    r = rr.Reranker()
    r._model = _M()
    monkeypatch.setattr(r, "_load", lambda: None)
    r.score("how did the sourdough turn out", [_doc(6000)])
    assert "sourdough" in seen["pairs"][0][1]


def test_the_remote_reranker_windows():
    sent = {}

    class _C:
        def info(self, *, timeout=None):
            return {}

        def call(self, op, payload=None, *, blob=None, timeout=None):
            sent.update(payload or {})
            return ({"ok": True, "scores": [0.5]}, b"")

    rr.RemoteReranker(_C()).score("how did the sourdough turn out", [_doc(6000)])
    assert "sourdough" in sent["docs"][0]


def test_collect_rerank_docs_windows_at_the_cap(monkeypatch):
    """The cap is applied BEFORE the model sees the doc, so a window applied
    only inside `score` would arrive too late."""
    hits = [(1, 0.9)]
    text = _doc(6000)
    monkeypatch.setattr(rr, "_entity_kinds", lambda store, eids: {1: "memory"})
    monkeypatch.setattr("refmatrix.embedder.extract_text_for_entity",
                        lambda s, eid, kind: text)
    scored, _, _ = rr.collect_rerank_docs(
        object(), hits, k=1, doc_chars=2048,
        query="how did the sourdough turn out")
    assert len(scored[0][1]) <= 2048
    assert "sourdough" in scored[0][1]

    plain, _, _ = rr.collect_rerank_docs(object(), hits, k=1, doc_chars=2048)
    assert plain[0][1] == text[:2048], "no query = today's behaviour, byte-exact"


def test_a_small_budget_keeps_head_truncation(monkeypatch):
    """MEASURED, not chosen: at the per-prompt hook's 700-char cap the split
    window covered 338 of 896 answer-bearing turns against 509 for plain head
    truncation — two ~350-char halves cut the answer in the middle, and every
    split fraction from 0.3 to 0.7 lost there too. Below
    `WINDOW_MIN_CHARS` the behaviour is byte-identical to before."""
    text = _doc(6000)
    assert rr.window_doc(text, "sourdough", limit=700) == text[:700]
    monkeypatch.setenv("RMX_RERANK_WINDOW_MIN", "256")
    import importlib
    importlib.reload(rr)
    try:
        assert rr.window_doc(text, "sourdough", limit=700) != text[:700]
    finally:
        monkeypatch.delenv("RMX_RERANK_WINDOW_MIN")
        importlib.reload(rr)


def test_half_the_budget_stays_on_the_head():
    """Anchoring ALONE measured WORSE than the head it replaced (502 vs 541 of
    896): most answers ARE in the head. The head half is not decoration."""
    text = _doc(6000)
    win = rr.window_doc(text, "how did the sourdough turn out", limit=2048)
    assert win.startswith(text[:1024])
    assert "sourdough" in win
