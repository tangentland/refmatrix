"""scan-prompt drops function words (the/does/how) but keeps content words
(user, camera, get) matchable as concepts."""
from __future__ import annotations

from refmatrix.scan import _PROMPT_STOPWORDS, match_concepts
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
    # plus a real domain concept.
    for junk in ("THE", "Does", "How"):
        s.add_concept(junk)
    s.add_concept("camera")
    s.add_concept("user")
    got = match_concepts(s, ["how", "does", "the", "camera", "user"])
    assert "camera" in got
    assert "user" in got
    assert not ({"THE", "Does", "How"} & set(got))
    s.close()
