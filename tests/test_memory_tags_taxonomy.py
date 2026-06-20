"""Phase 2: memory tag taxonomy + tag filtering + retag."""
from __future__ import annotations

from refmatrix import taxonomy as tax
from refmatrix.store import Store


def _seed(s):
    s.add_memory(name="m1", content="alpha", mtype="feedback",
                 tags=["tone", "git-policy"])
    s.add_memory(name="m2", content="beta", mtype="project",
                 tags=["git-policy"])
    s.add_memory(name="m3", content="gamma", mtype="reference", tags=["url"])
    s.add_memory(name="m4", content="delta", mtype="observation", tags=None)


# ---- tag filtering --------------------------------------------------------


def test_iter_filter_single_tag(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        _seed(s)
        got = {m["name"] for m in s.iter_memories(tags=["git-policy"])}
        assert got == {"m1", "m2"}
    s.close()


def test_iter_filter_and_semantics(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        _seed(s)
        got = {m["name"] for m in s.iter_memories(
            tags=["tone", "git-policy"], tags_match="all")}
        assert got == {"m1"}  # only m1 has both
    s.close()


def test_iter_filter_any_semantics(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        _seed(s)
        got = {m["name"] for m in s.iter_memories(
            tags=["tone", "url"], tags_match="any")}
        assert got == {"m1", "m3"}
    s.close()


def test_quoted_like_no_substring_false_positive(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        s.add_memory(name="a", content="x", tags=["github"])
        s.add_memory(name="b", content="x", tags=["git"])
        got = {m["name"] for m in s.iter_memories(tags=["git"])}
        assert got == {"b"}  # "git" must NOT match "github"
    s.close()


def test_search_with_tag_filter(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        _seed(s)
        rows = s.search_memories("a", tags=["git-policy"])  # alpha/beta/gamma/delta contain 'a'
        names = {r["name"] for r in rows}
        assert names == {"m1", "m2"}
    s.close()


# ---- retag ----------------------------------------------------------------


def test_retag_add_remove(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        s.add_memory(name="m", content="x", tags=["tone"])
        new = s.retag_memory("m", add=["git-policy"], remove=["tone"])
        assert new == ["git-policy"]
        assert s.get_memory("m")["tags"] == ["git-policy"]
    s.close()


def test_retag_replace(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        s.add_memory(name="m", content="x", tags=["tone", "git-policy"])
        new = s.retag_memory("m", replace=["url"])
        assert new == ["url"]
    s.close()


def test_retag_preserves_content_and_mtype(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        s.add_memory(name="m", content="body-text", mtype="feedback", tags=["tone"])
        s.retag_memory("m", add=["workflow"])
        m = s.get_memory("m")
        assert m["content"] == "body-text" and m["mtype"] == "feedback"
        assert set(m["tags"]) == {"tone", "workflow"}
    s.close()


def test_retag_missing_returns_none(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        assert s.retag_memory("nope", add=["x"]) is None
    s.close()


# ---- taxonomy -------------------------------------------------------------


def test_taxonomy_default_seed_and_validate(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    known, unknown = tax.validate(["tone", "made-up-tag"])
    assert known == ["tone"] and unknown == ["made-up-tag"]


def test_taxonomy_add_and_category(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    tax.add_tag("custom", "my-tag", description="d")
    assert "my-tag" in tax.all_tags()
    assert tax.category_of("my-tag") == "custom"


def test_taxonomy_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    tax.add_tag("custom", "tmp-tag")
    assert tax.remove_tag("tmp-tag") is True
    assert "tmp-tag" not in tax.all_tags()
    assert tax.remove_tag("tmp-tag") is False
