"""Read surfaces must share their mechanisms, not reimplement them.

The project has been bitten by this twice already: `project_rmx_audit_graph_
quality#grammar-drift` recorded "three sibling read surfaces, three input
grammars", and `feedback_reuse_shared_stoplist` recorded the same junk-token
bug at four call sites. These tests pin the shared paths so a fourth copy
cannot quietly appear.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# --- one tokenizer ---------------------------------------------------------


PROSE = "why did the daemon get killed by the OS"


def test_recall_and_context_tokenize_identically():
    """`recall._content_terms` claimed in its docstring to mirror
    `context._ref_terms` and did not: it dropped no stopwords, so
    `memory recall --fuse` sent `why`/`did`/`the`/`by` into BM25."""
    from refmatrix.context import _ref_terms
    from refmatrix.recall import _content_terms

    assert _content_terms(PROSE) == _ref_terms(PROSE)


def test_stopwords_are_dropped_from_recall_terms():
    from refmatrix.recall import _content_terms

    got = [t.lower() for t in _content_terms(PROSE)]
    for junk in ("why", "did", "the", "by"):
        assert junk not in got, f"{junk!r} should not be a BM25 query term"
    assert "daemon" in got and "killed" in got


def test_scan_stoplist_is_the_shared_one():
    """scan re-exports rather than owning a second copy."""
    from refmatrix.scan import _PROMPT_STOPWORDS
    from refmatrix.terms import STOPWORDS

    assert _PROMPT_STOPWORDS is STOPWORDS


def test_single_token_query_survives_the_stoplist():
    """`context "the"` must still search for `the` — a query that is entirely
    function words has nothing else to search on."""
    from refmatrix.terms import content_terms

    assert content_terms("the") == ["the"]
    assert content_terms("why is it") == ["why", "is", "it"]


def test_kind_prefix_stripped_only_for_context():
    from refmatrix.terms import content_terms

    assert content_terms("code:parse_url", strip_kind_prefix=True) == ["parse_url"]
    # A prose query containing a colon is not a kind selector.
    assert "why" not in content_terms("why: the daemon died",
                                      strip_kind_prefix=True)
    # Without the flag the prefix is left alone.
    assert content_terms("code:parse_url") == ["code:parse_url"]


def test_order_and_case_are_preserved():
    """content_rank does its own canonical expansion, so the tokenizer must
    not lowercase or reorder."""
    from refmatrix.terms import content_terms

    assert content_terms("parseURL Store DuckDB") == ["parseURL", "Store", "DuckDB"]


def test_dedupe_is_case_insensitive():
    from refmatrix.terms import content_terms

    assert content_terms("Daemon daemon DAEMON") == ["Daemon"]


# --- one rerank path -------------------------------------------------------


class _KeywordReranker:
    def score(self, query, docs):
        return [1.0 if "jetsam" in d else 0.0 for d in docs]


def _corpus(store):
    store.upsert_entity(kind="doc", name="sourdough.md", path="/x/a.md",
                        tldr="feed the starter every twelve hours")
    return store.upsert_entity(
        kind="doc", name="deaths.md", path="/x/b.md",
        tldr="the daemon was SIGKILLed by macOS jetsam under memory pressure")


def test_content_only_bundle_accepts_a_reranker(store):
    """scan-prompt's content view and `rmx context` share
    `_append_content_hits`, so one wiring must serve both."""
    from refmatrix.context import content_only_bundle

    _corpus(store)
    b = content_only_bundle(store, "memory pressure", grep_backstop=False,
                            reranker=_KeywordReranker())
    assert b is not None


def test_build_context_accepts_a_reranker(store):
    from refmatrix.context import build_context

    _corpus(store)
    b = build_context(store, "memory pressure", grep_backstop=False,
                      reranker=_KeywordReranker())
    assert b is not None


def test_a_broken_reranker_leaves_the_bundle_intact(store):
    """Reranking refines an answer we already have; it must never be the
    reason a surface returns nothing."""
    from refmatrix.context import content_only_bundle

    class _Broken:
        def score(self, query, docs):
            raise RuntimeError("model exploded")

    _corpus(store)
    good = content_only_bundle(store, "memory pressure", grep_backstop=False)
    broken = content_only_bundle(store, "memory pressure", grep_backstop=False,
                                 reranker=_Broken())
    assert len(broken.groups) == len(good.groups)


def test_every_surface_threads_a_reranker():
    """Signature guard. If a surface loses the parameter, it silently stops
    reranking and nothing else fails."""
    import inspect

    from refmatrix.context import build_context, content_only_bundle

    for fn in (build_context, content_only_bundle):
        assert "reranker" in inspect.signature(fn).parameters, fn.__name__


def test_shared_reranker_returns_none_without_a_hub(monkeypatch):
    """CLI surfaces are shared-or-nothing: an always-on hook must not spawn a
    ~450 MB model process to reorder twenty rows."""
    from refmatrix import reranker as rr

    monkeypatch.setenv("RMX_MODEL_SOCK", "/tmp/definitely-not-a-socket-rmx")
    monkeypatch.setenv("RMX_RERANK", "1")
    assert rr.shared_reranker() is None


def test_shared_reranker_respects_the_off_switch(monkeypatch):
    from refmatrix import reranker as rr

    monkeypatch.setenv("RMX_RERANK", "0")
    assert rr.shared_reranker() is None


# --- node bodies -----------------------------------------------------------


def test_anchored_concept_extracts_its_body(store):
    """GMD ingest hangs the body term-index on the anchored `doc#section`
    concept, so on a GMD corpus those nodes are what content_rank returns.
    Representing them by their heading alone starved every semantic consumer:
    BM25 saw the body, dense and rerank saw a label."""
    from refmatrix.embedder import extract_text_for_entity

    eid = store.add_concept("guide#setup")
    store._connect().execute(
        "UPDATE entities SET tldr = ? WHERE id = ?",
        ["Install the daemon and point it at the catalog directory.", eid],
    )
    store._connect().commit()
    text = extract_text_for_entity(store, eid, "concept")
    assert "guide#setup" in text
    assert "catalog directory" in text, "body missing from concept text"


def test_bare_concept_is_unchanged(store):
    """Unanchored concepts have no body; they must not gain one."""
    from refmatrix.embedder import extract_text_for_entity

    eid = store.add_concept("parse_url")
    assert extract_text_for_entity(store, eid, "concept") == "parse_url"


def test_rerank_gate_is_text_length_not_kind(store):
    """The first cut gated on kind and was wrong in both directions: it
    excluded anchored concepts that DO have bodies and would have admitted a
    bodiless doc row."""
    from refmatrix.context import _MIN_RERANK_CHARS, _rerank_bodied

    long_body = "the daemon was SIGKILLed by macOS jetsam " * 5
    assert len(long_body) >= _MIN_RERANK_CHARS
    rich = store.add_concept("doc#rich")
    store._connect().execute(
        "UPDATE entities SET tldr = ? WHERE id = ?", [long_body, rich])
    thin = store.add_concept("doc#thin")
    store._connect().commit()

    seen = {}

    class _Spy:
        def score(self, query, docs):
            seen["docs"] = docs
            return [1.0] * len(docs)

    # Only one bodied row -> nothing to reorder, and the spy is never called.
    out = _rerank_bodied(store, _Spy(), "jetsam", [(rich, 2.0), (thin, 1.0)])
    assert out == [(rich, 2.0), (thin, 1.0)]
    assert "docs" not in seen


# --- pseudo-relevance feedback --------------------------------------------


def test_prf_is_off_by_default(monkeypatch):
    """Measured on MemAware: expanding the query from top-hit bodies scored
    0.211 (5 terms) / 0.208 (10) against 0.217 with it off. The bodies pay off
    as node REPRESENTATION, not as query expansion."""
    from refmatrix.context import _prf_terms

    monkeypatch.delenv("RMX_PRF_TERMS", raising=False)
    assert _prf_terms() == 0
    monkeypatch.setenv("RMX_PRF_TERMS", "5")
    assert _prf_terms() == 5
    monkeypatch.setenv("RMX_PRF_TERMS", "nonsense")
    assert _prf_terms() == 0


def test_prf_mines_terms_the_query_lacks(store):
    from refmatrix.context import _prf_expansion

    eid = store.upsert_entity(
        kind="doc", name="d.md", path="/x/d.md",
        tldr="jetsam SIGKILL reclaimed the resident embedder process")
    got = [t.lower() for t in _prf_expansion(store, [(eid, 1.0)], ["daemon"], 4)]
    # Every term here ties at df=1, so the contract under test is the
    # DETERMINISTIC one: df desc, then first appearance in the body.
    assert got == ["jetsam", "sigkill", "reclaimed", "resident"], got
    assert "daemon" not in got, "query terms must not be re-added"
    assert "the" not in got, "stopwords must not become expansion terms"


def test_prf_expansion_is_stable_across_calls(store):
    """A set-iteration tie-break made this vary run to run, which is how it
    passed once and failed later in the same session."""
    from refmatrix.context import _prf_expansion

    eid = store.upsert_entity(
        kind="doc", name="d.md", path="/x/d.md",
        tldr="jetsam SIGKILL reclaimed the resident embedder process")
    runs = {tuple(_prf_expansion(store, [(eid, 1.0)], ["daemon"], 3))
            for _ in range(8)}
    assert len(runs) == 1, f"non-deterministic expansion: {runs}"
