"""`rmx context "<natural language phrase>"` — the three defects a prose corpus
exposed that a code corpus never did.

Measured before these fixes, on 90 questions over 1307 GMD-ingested chat
sessions (eval/memaware): `context` scored 0.007 MRR@20 while `memory recall`
scored 0.180 over the SAME store. It was not a ranking difference — the surface
could not reach the index for this input shape at all.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix.context import _grep_backstop, _ref_terms, build_context
from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store


# ─── _ref_terms: stopwords ────────────────────────────────────────────────

def test_multi_word_ref_drops_function_words():
    terms = [t.lower() for t in _ref_terms(
        "Do you know if my old sneakers are still in that spot?")]
    assert "sneakers" in terms
    for junk in ("do", "you", "if", "my", "are", "in", "that"):
        assert junk not in terms


def test_single_token_ref_is_never_stoplisted():
    """The ref IS the query when there is only one token — `context "the"`
    must still look for `the`, not fall back to an empty term list."""
    assert [t.lower() for t in _ref_terms("the")] == ["the"]


def test_all_stopword_ref_keeps_its_terms():
    """Filtering to nothing would silently turn the query into a no-op."""
    assert _ref_terms("are you the one") != []


def test_identifier_ref_survives_intact():
    assert _ref_terms("fov_wedge_polygon") == ["fov_wedge_polygon"]


# ─── _grep_backstop: word boundaries ──────────────────────────────────────

@pytest.fixture
def tree(tmp_path):
    (tmp_path / "notes.md").write_text(
        "tags: [memaware, session]\nthe user bought sneakers\n", encoding="utf8")
    return tmp_path


def test_substring_match_is_the_default(tree):
    """Identifier refs depend on it: `fov_wedge` must find
    `fov_wedge_polygon`."""
    hits = _grep_backstop(["are"], tree, limit=5)
    assert hits, "substring mode should match 'are' inside 'memaware'"


def test_whole_word_rejects_the_substring(tree):
    """A prose ref carrying a short function word used to crown whichever file
    repeated the commonest fragment — live, `tags: [memaw«are», session]`
    scored 191 and won."""
    assert _grep_backstop(["are"], tree, limit=5, whole_word=True) == []
    assert _grep_backstop(["sneakers"], tree, limit=5, whole_word=True)


# ─── content_rank reaching GMD body text ──────────────────────────────────

# NOTE: the doc id deliberately avoids a `session-` prefix — `_is_session_card`
# treats those as transient activity logs and filters them out of content hits,
# which would mask the behaviour under test here.
GMD_DOC = """---
gmd: "0.1"
id: chat-alpha
title: "Chat alpha"
tags: [testing]
metadata:
  node_type: memory
  type: test/session
---

# Chat alpha {#root}

User: I need to organize my closet and get rid of some old sneakers that are
taking up space on the shoe rack.
"""


@pytest.fixture
def gmd_store(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "chat-alpha.md").write_text(GMD_DOC, encoding="utf8")
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    ingest_gmd_paths(s, [docs / "chat-alpha.md"], as_memory=True,
                     memory_mtype_default="test/session")
    yield s
    s.close()


def test_body_terms_land_on_the_anchored_node_not_the_memory(gmd_store):
    """Pins the graph shape the fix is built around. A GMD doc yields TWO
    entities and the body term-frequency sweep hangs `mentions` on the node,
    so ranking only code/doc/memory searches the half with no body index."""
    node = gmd_store.get_entity("concept", "chat-alpha#root")
    assert node is not None
    hits = gmd_store.content_rank(["sneakers"], kinds=["concept"], limit=10)
    assert node.id in [eid for eid, _ in hits]
    assert gmd_store.content_rank(
        ["sneakers"], kinds=["code", "doc", "memory"], limit=10) == []


def test_multi_word_phrase_reaches_the_index(gmd_store):
    """The regression itself: every term is indexed, so this must produce
    content hits rather than falling through to the grep floor."""
    bundle = build_context(gmd_store, "sneakers closet organize", max_entities=10)
    assert "content" in bundle.groups, f"expected content hits, got {sorted(bundle.groups)}"
    assert bundle.groups["content"]


def test_bare_concepts_are_not_content_hits(gmd_store):
    """Widening the kinds must not turn query terms into results — only
    anchored `doc#section` concepts are somewhere a reader can be sent."""
    bundle = build_context(gmd_store, "sneakers closet organize", max_entities=10)
    for e in bundle.groups.get("content", []):
        if e.entity.kind == "concept":
            assert "#" in e.entity.name
