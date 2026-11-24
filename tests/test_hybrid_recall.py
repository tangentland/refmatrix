"""Hybrid dense ⊕ content_rank RRF fusion for `memory recall` (round 4).

Closes audit-2 #1 deliverable-2: `_op_ann_search` was pure dense, so a
rare-keyword query ("grep backstop protected query concept") ranked the
lexically-exact memory far down — symbolic content_rank nails it, dense
dilutes it. `hybrid_memory_recall` RRF-fuses both. The fusion arithmetic is
tested with fakes (no daemon / embedder model needed); bug-300's section at the
end drives the verb, the CLI and MCP over a real store and a real daemon."""
from __future__ import annotations

import numpy as np
import pytest

from refmatrix.cli import _ann_similarity, _recall_display_score
from refmatrix.recall import _content_terms, hybrid_memory_recall


class FakeEmbedder:
    dim = 4

    def embed_texts(self, texts):
        return np.zeros((len(texts), self.dim), dtype="float32")


class FakeStore:
    def __init__(self, content, dense):
        self._content = content       # [(id, bm25_score)] best-first
        self._dense = dense           # [(id, l2_distance)] best-first
        self.content_calls = []

    def content_rank(self, terms, *, kinds=None, limit=50):
        self.content_calls.append((tuple(terms), tuple(kinds or ()), limit))
        return self._content[:limit]

    def ann_search(self, v, k, *, dim, kinds=None, candidate_ids=None):
        return self._dense[:k]


# ---- tokenizer -----------------------------------------------------------

def test_content_terms_tokenizes_dedupes_drops_short():
    assert _content_terms("grep backstop protected QUERY query") == [
        "grep", "backstop", "protected", "QUERY",
    ]
    assert _content_terms("  a  of x ") == ["of"]   # 1-char dropped, 'of' kept
    assert _content_terms("") == []


# ---- fusion --------------------------------------------------------------

def test_fusion_rescues_the_symbolic_winner_dense_buried():
    # The real shape: dense ranks the true memory (99) LAST; symbolic #1.
    dense = [(1, 0.10), (2, 0.20), (3, 0.30), (4, 0.40), (99, 0.95)]
    content = [(99, 8.0), (1, 0.5)]
    store = FakeStore(content, dense)
    fused = hybrid_memory_recall(store, FakeEmbedder(), "grep backstop", k=3)
    ids = [eid for eid, _ in fused]
    assert 99 in ids[:3]                              # fusion lifted it
    assert 99 not in [eid for eid, _ in dense[:3]]    # pure dense top-3 missed it


def test_fusion_scopes_content_rank_to_memory_kind():
    store = FakeStore([(1, 1.0)], [(1, 0.1)])
    hybrid_memory_recall(store, FakeEmbedder(), "hello world", k=5)
    terms, kinds, _limit = store.content_calls[0]
    assert kinds == ("memory",)
    assert "hello" in terms and "world" in terms


def test_empty_query_is_dense_only_no_content_rank():
    store = FakeStore([(1, 1.0)], [(7, 0.1), (8, 0.2)])
    fused = hybrid_memory_recall(store, FakeEmbedder(), "   ", k=5)
    assert [eid for eid, _ in fused] == [7, 8]        # dense order preserved
    assert store.content_calls == []                  # no terms → no symbolic side


def test_fused_score_descends_with_rank():
    dense = [(1, 0.1), (2, 0.2), (99, 0.9)]
    content = [(99, 5.0)]
    fused = hybrid_memory_recall(FakeStore(content, dense), FakeEmbedder(), "x y", k=3)
    scores = [s for _, s in fused]
    assert scores == sorted(scores, reverse=True)     # descending


# ---- display score (fused RRF vs dense cosine) ---------------------------

def test_display_score_fused_uses_rrf_value_directly():
    assert _recall_display_score({"id": 1, "score": 0.0321, "fused": True}) == 0.0321


def test_display_score_dense_converts_distance_to_cosine():
    h = {"id": 1, "distance": 0.6947}
    assert abs(_recall_display_score(h) - _ann_similarity(0.6947)) < 1e-9


def test_display_score_dense_higher_for_closer():
    assert _recall_display_score({"distance": 0.3}) > _recall_display_score({"distance": 0.9})


# ---- bug-300: fusion over a memory's BODY, through the surfaces users call --------
#
# Real store, real GMD ingest (`ingest_gmd_paths(as_memory=True)`, the bridge's path), a real
# sandbox daemon embedding with the real model (RMX_RERANK=0: the ORDER under test is the
# fusion's, not a cross-encoder's). Nothing is faked. The memories are titled by an id (the
# LongMemEval shape that made `--fuse` a no-op on 120 of 120 rankings, T0.6 2026-11-24): their
# own `mentions` are `session` + id tokens and every body word sits on a block node.
#
# s7781_2 holds `daily` + `commute`, but only in its LAST section, after ~800 words about a
# garden: the embedding (bge-small reads 512 tokens) never sees them, so dense ranks it below
# the three memories ABOUT getting to work, none of which uses either word. The symbolic leg is
# the only one that can see s7781_2's commute. Query words are punctuation-free (bug-301).

_FILLER = ("The tomatoes in the raised bed need staking before the storm. Basil seedlings wait "
           "by the greenhouse door while the compost heap steams in the cold air. ") * 30
_B300_QUERY = "daily commute"
_B300_NOTHING = "zyxwvut quuxbar"      # no concept in the store: the symbolic leg must be empty
# Every word a stopword (L199, spec #r1-scope: R3 warns here too when fuse is on). Today
# `content_terms` keeps an all-stopword query's words rather than return nothing, and ingest
# indexes no stopword, so the leg runs and returns []; a GREEN that skips the leg for want of
# terms must say so just the same.
_B300_STOPWORDS = "what is it"
_B300_WARN = "fuse: symbolic leg empty"


def _b300_memory(mid: str, sections, *, preamble: str = "") -> str:
    body = "\n\n".join(f"## {t} {{#{a}}}\n\n{txt}" for t, a, txt in sections)
    return (f'---\ngmd: "0.1"\nid: {mid}\ntitle: "Session {mid}"\ntags: [session]\n'
            f"metadata:\n  node_type: memory\n  type: test/session\n---\n\n"
            f"# Session {mid} {{#root}}\n\n{preamble}\n\n{body}\n")


_B300_MEMORIES = {
    "s7781_2": _b300_memory("s7781_2", [
        ("Garden", "garden", _FILLER),
        ("Travel", "travel", "My daily commute is forty minutes on the train.")]),
    "s7782_1": _b300_memory("s7782_1", [("Work", "work", "Getting to work means a forty minute "
                                         "train ride every weekday morning.")]),
    "s7783_1": _b300_memory("s7783_1", [("Office", "office", "Driving to the office through "
                                         "heavy traffic takes about an hour each way.")]),
    "s7784_1": _b300_memory("s7784_1", [("Job", "job", "The bus to my job leaves at seven and "
                                        "reaches the depot by eight.")]),
    "s7785_1": _b300_memory("s7785_1", [("Kitchen", "kitchen", "The kettle is blue and the "
                                         "toaster burns the bread.")]),
}


@pytest.fixture(scope="module")
def bodied():
    """One real store under `rmx_sandbox.short_root()`, served by a real foreground sandbox
    daemon, memories embedded and snapshotted (the shape of
    tests/test_mcp_memory_recall_routing.py's `routed`)."""
    import os
    from pathlib import Path

    import rmx_sandbox
    from refmatrix import daemon as dm, verbs
    from refmatrix.ingest_gmd import ingest_gmd_paths
    from refmatrix.store import Store
    from tests import task21_1_support as h

    base = Path(rmx_sandbox.short_root("b300r-"))
    home = base / "g" / ".refmatrix"
    root = base / "proj" / ".refmatrix"
    mem = base / "mem"
    mem.mkdir()
    root.parent.mkdir(parents=True)
    for name, text in _B300_MEMORIES.items():
        (mem / f"{name}.md").write_text(text, encoding="utf8")
    st = Store(root)
    try:
        st.init()
        ingest_gmd_paths(st, [mem / f"{n}.md" for n in _B300_MEMORIES], as_memory=True,
                         memory_mtype_default="test/session")
    finally:
        st.close()
    old = os.environ.get("RMX_HOME")
    os.environ["RMX_HOME"] = str(home)
    d = None
    try:
        d = h.SandboxDaemon(root, RMX_HOME=str(home), RMX_RERANK="0")
        d.wait_models_warm()
        part = verbs.memory_partition(root, timeout=30)
        assert dm.call(root, "embed", {"kinds": ["memory"], "partition": part},
                       timeout=900).get("ok")
        assert dm.call(root, "snapshot", {"force": True}, timeout=300).get("ok")
        yield {"root": root, "home": home}
    finally:
        if d is not None:
            d.stop()
        if old is None:
            os.environ.pop("RMX_HOME", None)
        else:
            os.environ["RMX_HOME"] = old
        rmx_sandbox.remove_tree(base)


@pytest.fixture
def b300(bodied, monkeypatch):
    monkeypatch.setenv("RMX_HOME", str(bodied["home"]))
    monkeypatch.delenv("RMX_RECALL_REPLICA_FIRST", raising=False)
    return bodied


def _cli_recall(fx, query: str, *, fuse: bool):
    import json

    from tests import task21_1_support as h
    args = ["memory", "recall", query, "--json", "-k", "5", "--no-rerank"]
    args.append("--fuse" if fuse else "--no-fuse")
    r = h.run_rmx(args, root=fx["root"], RMX_HOME=str(fx["home"]))
    assert r.returncode == 0, (r.returncode, r.stderr[-2000:])
    return json.loads(r.stdout), r.stderr


def test_fuse_over_a_memory_body_ranks_differently_from_dense(b300):
    """bug-300 AC-2: `rmx memory recall "<body words>" --fuse --json` ranks differently from
    the same call without `--fuse`, and every fused hit says `fused: true`. RED at base: the
    symbolic leg returned [] (a memory's own mentions are its title), so RRF over the dense
    list alone kept dense's order exactly."""
    dense, _ = _cli_recall(b300, _B300_QUERY, fuse=False)
    fused, _ = _cli_recall(b300, _B300_QUERY, fuse=True)
    dense_names = [r["name"] for r in dense]
    fused_names = [r["name"] for r in fused]
    # Fixture sanity, not the claim: the embedding cannot see s7781_2's commute.
    assert dense_names and dense_names[0] != "s7781_2", (
        f"fixture: dense already ranks the body-word memory first: {dense_names}")
    assert fused and all(r.get("fused") is True for r in fused), fused
    assert fused_names != dense_names, (
        f"--fuse ranked exactly like dense: {fused_names} (symbolic leg empty?)")
    assert fused_names[0] == "s7781_2", fused_names


def _recall_warnings(surface: str, fx, query: str, *, fuse: bool) -> "list[str]":
    """The warnings one recall produced, read where that surface puts them: the verb's and
    MCP's `warnings`, the CLI's stderr lines."""
    from refmatrix import verbs

    if surface == "verb":
        res = verbs.memory_recall(fx["root"], query=query, k=5, fuse=fuse, rerank=False)
        assert res.get("memories"), res
        return list(res.get("warnings") or [])
    if surface == "mcp":
        import refmatrix.mcp as mcp
        out = mcp._t_memory_recall({"query": query, "k": 5, "fuse": fuse, "rerank": False,
                                    "scope": "project", "root": str(fx["root"])})
        assert out.get("memories"), out
        return list(out.get("warnings") or [])
    rows, err = _cli_recall(fx, query, fuse=fuse)
    assert rows, err
    return [ln for ln in err.splitlines() if "warning" in ln]


@pytest.mark.parametrize("query", [_B300_NOTHING, _B300_STOPWORDS])
@pytest.mark.parametrize("surface", ["verb", "cli", "mcp"])
def test_an_empty_symbolic_leg_is_said_on_every_surface(b300, surface, query):
    """bug-300 AC-4 (R3): when `--fuse`'s symbolic leg returns nothing -- terms that match no
    concept, or a query of stopwords only -- the answer (still the dense rows) carries a
    `fuse: symbolic leg empty` warning, through the verb, the CLI and MCP, so a no-op fuse is
    never silent. RED at base: no surface says anything."""
    ws = _recall_warnings(surface, b300, query, fuse=True)
    assert any(_B300_WARN in w for w in ws), f"{surface}: no {_B300_WARN!r} in {ws}"


@pytest.mark.parametrize("query,fuse", [(_B300_QUERY, True), (_B300_NOTHING, False)])
def test_no_empty_leg_warning_when_the_leg_ran_or_fuse_is_off(b300, query, fuse):
    """The other side of AC-4: the warning is not a blanket. A fuse whose leg found the body
    word, and a recall without `--fuse`, say nothing about a symbolic leg (GREEN at base; it
    pins that the fix does not warn on every call)."""
    ws = _recall_warnings("verb", b300, query, fuse=fuse)
    assert not any(_B300_WARN in w for w in ws), ws
