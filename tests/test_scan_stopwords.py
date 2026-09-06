"""scan-prompt drops function words (the/does/how) but keeps content words
(user, camera, get) matchable as concepts."""
from __future__ import annotations

from refmatrix.scan import _PROMPT_STOPWORDS, _is_unlinked_plain, match_concepts
from refmatrix.store import Store


def test_function_words_are_stopped():
    for w in ("the", "does", "how", "is", "of", "which", "their", "an"):
        assert w in _PROMPT_STOPWORDS, w


def test_content_words_are_not_stopped():
    # Domain concepts / method-name verbs must stay matchable.
    for w in ("user", "camera", "get", "make", "use", "work", "show", "go",
              "fov", "perspective"):
        assert w not in _PROMPT_STOPWORDS, w


def test_match_concepts_skips_stopwords_keeps_content(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    # Seed junk function-word concepts (as the real graph accidentally does)
    # plus real domain concepts. A real domain concept is MENTIONED in code
    # (degree > 0); seed the link so it survives the unlinked-plain-word gate
    # the way `camera`/`user` do in an actual indexed graph.
    for junk in ("THE", "Does", "How"):
        s.add_concept(junk)
    cam = s.add_concept("camera")
    usr = s.add_concept("user")
    ent = s.upsert_entity(kind="code", name="cam.py")
    s.link("mentions", cam, ent)
    s.link("mentions", usr, ent)
    got = match_concepts(s, ["how", "does", "the", "camera", "user"])
    assert "camera" in got
    assert "user" in got
    assert not ({"THE", "Does", "How"} & set(got))
    s.close()


def test_is_unlinked_plain_predicate():
    # degree-0 plain lowercase word → dropped (accidental prose extraction)
    assert _is_unlinked_plain("selection", 0)
    assert _is_unlinked_plain("meaningful", 0)
    assert _is_unlinked_plain("keep", 0)
    # identifier-shaped tokens the author cited survive even at degree 0
    assert not _is_unlinked_plain("max_tokens", 0)
    assert not _is_unlinked_plain("scan-prompt", 0)
    assert not _is_unlinked_plain("KeyError", 0)
    assert not _is_unlinked_plain("adr-0036", 0)
    # any linked concept survives, plain word or not
    assert not _is_unlinked_plain("selection", 3)


def test_match_concepts_gate_drops_unlinked_plain_keeps_shaped(tmp_path):
    """Unlinked plain word dropped; unlinked *shaped* symbol and linked plain
    concept both kept — the fix cliquedb-claude requested for scan-prompt."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_concept("selection")          # degree-0 plain prose word → junk
    s.add_concept("max_tokens")         # degree-0 but shaped → real symbol
    linked = s.add_concept("authentication")
    ent = s.upsert_entity(kind="code", name="auth.py")
    s.link("mentions", linked, ent)     # degree>0 plain domain concept
    got = match_concepts(s, ["selection", "max_tokens", "authentication"])
    assert "selection" not in got
    assert "max_tokens" in got
    assert "authentication" in got
    # gate is opt-out: pre-gate demote-only behavior keeps everything
    ungated = match_concepts(
        s, ["selection", "max_tokens", "authentication"],
        drop_unlinked_plain=False,
    )
    assert "selection" in ungated
    s.close()


def test_shape0_floor_drops_peripheral_plain_word_once_pagerank_ran(tmp_path):
    """After PageRank is computed, a code-mentioned but peripheral plain word
    (degree>0, so the unlinked-plain gate misses it) is dropped by the shape-0
    salience floor, while a central plain concept and any shaped token survive.
    This is the second half of the cliquedb-claude fix: dictionary-common
    words that happen to appear in code."""
    from refmatrix import pagerank as pr
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_linkage_type("defines", directed=True, description="x")
    hub = s.add_concept("store")            # central plain domain concept
    fringe = s.add_concept("selection")     # peripheral plain word
    shaped = s.add_concept("max_tokens")    # shaped, exempt from the floor
    ents = [s.upsert_entity(kind="code", name=f"m{i}.py") for i in range(8)]
    for e in ents:                          # hub is co-mentioned everywhere
        s.link("defines", hub, e)
        s.link("mentions", hub, e)
    # ...and some document actually leans on it. Every real central domain
    # word carries a tf spike (`memory` peaks at 24, `hub` at 15); without
    # one, breadth alone now reads as a diffuse discourse word and the
    # concentration demotion floors it — which is the point of that fix.
    s.link("mentions", hub, ents[0], weight=12)
    s.link("mentions", fringe, ents[0])     # fringe: one lonely mention
    s.link("mentions", shaped, ents[0])     # shaped: also peripheral by degree
    pr.store_scores(s, pr.compute(s))
    got = match_concepts(s, ["store", "selection", "max_tokens"])
    assert "store" in got                   # central plain concept kept
    assert "max_tokens" in got              # shaped token exempt from floor
    assert "selection" not in got           # peripheral plain word floored out
    s.close()
