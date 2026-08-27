"""Cross-encoder rerank stage.

The model half is exercised through a fake reranker: what matters here is
that the shortlist is split correctly, that the store half and the model
half stay separable (so the daemon can drop `_store_lock` between them),
and that every failure degrades to retrieval order instead of raising.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

_HAS_DENSE = importlib.util.find_spec("sentence_transformers") is not None
_OFFLINE = os.environ.get("RMX_EMBED_OFFLINE") == "1"


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


class _FakeReranker:
    """Scores by position of a keyword, so expected order is obvious."""

    def __init__(self, keyword="jetsam", fail=False):
        self.keyword = keyword
        self.fail = fail
        self.seen: list[tuple[str, list[str]]] = []

    def score(self, query, docs):
        if self.fail:
            raise RuntimeError("model exploded")
        self.seen.append((query, list(docs)))
        return [1.0 if self.keyword in d else 0.0 for d in docs]


def _make_daemon(tmp_path):
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s
    return d


def _mk_code(store, name, tldr):
    return store.upsert_entity(
        kind="code", name=name, path=f"/x/{name}.py", tldr=tldr,
    )


# --- flag ------------------------------------------------------------------


def test_rerank_enabled_by_default(monkeypatch):
    """On by default -- affordable because it runs in its own worker."""
    from refmatrix.reranker import rerank_enabled

    monkeypatch.delenv("RMX_RERANK", raising=False)
    assert rerank_enabled() is True
    monkeypatch.setenv("RMX_RERANK", "0")
    assert rerank_enabled() is False
    monkeypatch.setenv("RMX_RERANK", "false")
    assert rerank_enabled() is False
    monkeypatch.setenv("RMX_RERANK", "1")
    assert rerank_enabled() is True


# --- store half ------------------------------------------------------------


def test_collect_splits_texted_from_untexted(store):
    from refmatrix.reranker import collect_rerank_docs

    a = _mk_code(store, "alpha", "daemon jetsam under memory pressure")
    b = _mk_code(store, "beta", "roaring bitmap fragments")
    missing = 999999            # no entity row -> no kind -> no text

    scored, untexted, tail = collect_rerank_docs(
        store, [(a, 0.9), (missing, 0.8), (b, 0.7)], k=10,
    )
    assert [e for e, _t in scored] == [a, b]
    assert [e for e, _s in untexted] == [missing]
    assert tail == []


def test_collect_respects_the_pool_boundary(store):
    from refmatrix.reranker import collect_rerank_docs

    eids = [_mk_code(store, f"e{i}", f"tldr {i}") for i in range(10)]
    hits = [(e, 1.0 - i / 100) for i, e in enumerate(eids)]

    scored, untexted, tail = collect_rerank_docs(store, hits, k=2, pool=4)
    assert len(scored) + len(untexted) == 4
    assert [e for e, _ in tail] == eids[4:]


def test_collect_pool_is_capped(store, monkeypatch):
    """A huge -k must not turn the rerank stage into a full-partition scan."""
    import refmatrix.reranker as rr

    monkeypatch.setattr(rr, "MAX_POOL", 3)
    eids = [_mk_code(store, f"e{i}", f"tldr {i}") for i in range(8)]
    hits = [(e, 1.0) for e in eids]
    scored, untexted, tail = rr.collect_rerank_docs(store, hits, k=8)
    assert len(scored) + len(untexted) == 3
    assert len(tail) == 5


def test_collect_uses_one_query_for_kinds(store):
    """Regression guard: kind lookup must be a single IN query, not N."""
    from refmatrix.reranker import collect_rerank_docs

    eids = [_mk_code(store, f"e{i}", f"tldr {i}") for i in range(5)]
    calls = {"n": 0}
    real_connect = store._connect

    def counting_connect():
        calls["n"] += 1
        return real_connect()

    store._connect = counting_connect
    try:
        collect_rerank_docs(store, [(e, 1.0) for e in eids], k=5)
    finally:
        store._connect = real_connect
    # One for the kind lookup + one per extractor row; the kind lookup
    # itself must not scale with N, so this stays well under 2N.
    assert calls["n"] <= len(eids) + 2


# --- model half ------------------------------------------------------------


def test_apply_rerank_reorders_by_model_score():
    from refmatrix.reranker import apply_rerank

    scored = [(1, "roaring bitmaps"), (2, "daemon jetsam kill"), (3, "duckdb")]
    out = apply_rerank(_FakeReranker(), "q", scored, [], [], k=3)
    assert out[0][0] == 2, "the keyword doc should be promoted to rank 1"
    assert [e for e, _ in out] == [2, 1, 3] or out[0][0] == 2


def test_apply_rerank_keeps_untexted_behind_scored():
    from refmatrix.reranker import apply_rerank

    out = apply_rerank(
        _FakeReranker(), "q",
        [(1, "roaring bitmaps")], [(2, 0.5)], [(3, 0.1)], k=5,
    )
    assert [e for e, _ in out] == [1, 2, 3]


def test_apply_rerank_output_is_monotonically_descending():
    """The contract is 'descending by score'. Position alone is not enough:
    `rmx memory recall` re-sorts by score, so any row whose score contradicts
    its position gets reshuffled. Untexted/tail rows carry RETRIEVAL scores on
    a different scale from cross-encoder logits, which is how a body-less row
    (0.44) once outranked a real reranked hit (-0.52)."""
    from refmatrix.reranker import apply_rerank

    # The reranked row scores 0.0 (no keyword); the untexted row carries a
    # retrieval score of 0.9 -- higher on its own scale, and meaningless here.
    out = apply_rerank(
        _FakeReranker(), "q",
        [(1, "roaring bitmaps")], [(2, 0.9)], [(3, 0.95)], k=5,
    )
    assert [e for e, _ in out] == [1, 2, 3]
    scores = [sc for _e, sc in out]
    assert scores == sorted(scores, reverse=True), scores
    # And re-sorting by score -- what the CLI does -- must be a no-op.
    resorted = [e for e, _ in sorted(out, key=lambda p: -p[1])]
    assert resorted == [1, 2, 3]


def test_apply_rerank_demotes_below_the_reranked_floor():
    from refmatrix.reranker import apply_rerank

    out = apply_rerank(
        _FakeReranker(), "q",
        [(1, "jetsam"), (2, "unrelated")], [(3, 99.0)], [], k=5,
    )
    reranked_floor = min(sc for eid, sc in out if eid in (1, 2))
    demoted = [sc for eid, sc in out if eid == 3][0]
    assert demoted < reranked_floor


def test_apply_rerank_with_nothing_scored_preserves_order():
    from refmatrix.reranker import apply_rerank

    out = apply_rerank(_FakeReranker(), "q", [], [(2, 0.5)], [(3, 0.1)], k=5)
    assert [e for e, _ in out] == [2, 3]


def test_apply_rerank_truncates_to_k():
    from refmatrix.reranker import apply_rerank

    scored = [(i, f"doc {i}") for i in range(10)]
    assert len(apply_rerank(_FakeReranker(), "q", scored, [], [], k=3)) == 3


# --- wrapper ---------------------------------------------------------------


def test_rerank_entity_hits_end_to_end(store):
    from refmatrix.reranker import rerank_entity_hits

    a = _mk_code(store, "alpha", "roaring bitmap fragments")
    b = _mk_code(store, "beta", "daemon jetsam under memory pressure")
    # Retrieval put the wrong one first; the reranker should fix it.
    out = rerank_entity_hits(
        store, _FakeReranker(), "why did the daemon die",
        [(a, 0.9), (b, 0.1)], k=2,
    )
    assert out[0][0] == b


def test_rerank_entity_hits_noop_on_empty_query(store):
    from refmatrix.reranker import rerank_entity_hits

    a = _mk_code(store, "alpha", "x")
    hits = [(a, 0.9)]
    assert rerank_entity_hits(store, _FakeReranker(), "", hits, k=5) == hits


def test_rerank_entity_hits_noop_when_nothing_has_text(store):
    from refmatrix.reranker import rerank_entity_hits

    hits = [(999998, 0.9), (999999, 0.1)]
    assert rerank_entity_hits(store, _FakeReranker(), "q", hits, k=5) == hits


# --- non-finite guard ------------------------------------------------------


def test_checked_rejects_nan():
    """NaN sorts unpredictably rather than to the bottom, so a NaN score set
    must raise instead of silently scrambling the ranking. Measured live:
    cross-encoder/ms-marco-MiniLM-L-6-v2 does exactly this under
    transformers 5.8.1."""
    from refmatrix.reranker import _checked

    with pytest.raises(RuntimeError, match="non-finite"):
        _checked([0.5, float("nan")], "some/model")


def test_checked_rejects_inf():
    from refmatrix.reranker import _checked

    with pytest.raises(RuntimeError, match="non-finite"):
        _checked([float("-inf")], "some/model")


def test_checked_passes_finite_scores():
    from refmatrix.reranker import _checked

    assert _checked([1, -2.5, 0], "m") == [1.0, -2.5, 0.0]


def test_nan_scores_degrade_to_retrieval_order(tmp_path):
    """End of the chain: a NaN-producing model must leave the caller with
    the retrieval ordering, not an exception and not a scrambled list."""
    from refmatrix.daemon import _apply_rerank_safe

    class _NanReranker:
        def score(self, query, docs):
            from refmatrix.reranker import _checked
            return _checked([float("nan")] * len(docs), "bad/model")

    d = _make_daemon(tmp_path)
    try:
        d._reranker_inst = _NanReranker()
        assert _apply_rerank_safe(d, "q", ([(1, "doc")], [], []), 5) is None
    finally:
        d.store.close()


# --- daemon integration ----------------------------------------------------


def test_maybe_rerank_arg_beats_env(tmp_path, monkeypatch):
    d = _make_daemon(tmp_path)
    try:
        monkeypatch.setenv("RMX_RERANK", "0")
        assert d._maybe_rerank({}) is False
        assert d._maybe_rerank({"rerank": True}) is True
        monkeypatch.setenv("RMX_RERANK", "1")
        assert d._maybe_rerank({}) is True
        assert d._maybe_rerank({"rerank": False}) is False
    finally:
        d.store.close()


def test_apply_rerank_safe_degrades_when_model_fails(tmp_path):
    from refmatrix.daemon import _apply_rerank_safe

    d = _make_daemon(tmp_path)
    try:
        d._reranker_inst = _FakeReranker(fail=True)
        out = _apply_rerank_safe(d, "q", ([(1, "doc")], [], []), 5)
        assert out is None, "a failing model must fall back to retrieval order"
    finally:
        d.store.close()


def test_apply_rerank_safe_degrades_without_dense_extra(tmp_path):
    from refmatrix.daemon import _apply_rerank_safe

    d = _make_daemon(tmp_path)
    try:
        def _boom():
            raise ImportError("sentence-transformers not installed")
        d._reranker = _boom
        assert _apply_rerank_safe(d, "q", ([(1, "doc")], [], []), 5) is None
    finally:
        d.store.close()


def test_apply_rerank_safe_returns_none_with_no_scored_docs(tmp_path):
    from refmatrix.daemon import _apply_rerank_safe

    d = _make_daemon(tmp_path)
    try:
        called = {"n": 0}

        def _never():
            called["n"] += 1
            raise AssertionError("should not build a reranker")

        d._reranker = _never
        logged: list[str] = []
        d._log = logged.append
        assert _apply_rerank_safe(d, "q", ([], [(1, 0.5)], []), 5) is None
        assert called["n"] == 0, "no texted docs must not cost a model load"
        # A silent skip here is indistinguishable from rerank being disabled,
        # which is exactly the confusion this line exists to prevent.
        assert any("rerank skipped" in m for m in logged), logged
    finally:
        d.store.close()


# --- real model ------------------------------------------------------------


@pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_real_reranker_prefers_the_relevant_doc():
    from refmatrix.reranker import Reranker

    rr = Reranker()
    docs = [
        "Sourdough starter needs feeding every twelve hours.",
        "The daemon was SIGKILLed by macOS jetsam under memory pressure.",
    ]
    scores = rr.score("why did the daemon get killed", docs)
    assert scores[1] > scores[0]


@pytest.mark.skipif(not _HAS_DENSE, reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_real_rerank_worker_matches_in_process_scores():
    from refmatrix.reranker import Reranker, RemoteReranker
    from refmatrix.subproc import WorkerClient

    docs = ["roaring bitmap fragments", "the daemon died to jetsam"]
    local = Reranker().score("daemon death", docs)

    c = WorkerClient("rerank", timeout=300.0)
    try:
        remote = RemoteReranker(c).score("daemon death", docs)
    finally:
        c.close()

    assert len(remote) == len(local)
    for r, l in zip(remote, local):
        assert abs(r - l) < 1e-4
