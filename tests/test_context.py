"""Tests for `rmx context`."""
from __future__ import annotations

import json

import pytest

from refmatrix.context import (
    LINKAGE_LABELS,
    build_context,
    render_json,
    render_text,
)
from refmatrix.store import Store


@pytest.fixture
def filled(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    parser = s.add_concept("parser", description="anything that turns text into structure")
    foo = s.upsert_entity(kind="code", name="src/foo.py", path="/p/foo.py",
                          tldr="dispatch + parse")
    bar = s.upsert_entity(kind="code", name="src/bar.py", path="/p/bar.py",
                          tldr="caller of parser")
    readme = s.upsert_entity(kind="doc", name="README.md", path="/p/README.md",
                             tldr="overview")
    s.link("defines", parser, foo)
    s.link("called_by", parser, bar)
    s.weighted_link("mentions", parser, readme, weight=3.0)
    s.weighted_link("mentions", parser, foo, weight=1.0)
    yield s, dict(parser=parser, foo=foo, bar=bar, readme=readme)
    s.close()


def test_build_context_groups_by_linkage(filled):
    s, ids = filled
    b = build_context(s, "parser")
    assert b.anchor is not None
    assert b.anchor.kind == "concept"
    # we should see at least defines, called_by, mentions
    assert "defines" in b.groups
    assert "called_by" in b.groups
    assert "mentions" in b.groups
    # mentions is weighted; readme (w=3) should rank above foo (w=1)
    mentions_names = [e.entity.name for e in b.groups["mentions"]]
    assert mentions_names[0] == "README.md"


def test_build_context_returns_empty_for_unknown_symbol(filled):
    s, _ = filled
    b = build_context(s, "no-such-thing")
    assert b.anchor is None
    assert b.groups == {}


def test_build_context_respects_linkage_filter(filled):
    s, _ = filled
    b = build_context(s, "parser", linkages=["defines"])
    assert list(b.groups.keys()) == ["defines"]


def test_build_context_respects_max_entities(filled):
    s, _ = filled
    b = build_context(s, "parser", max_entities=2)
    assert b.total_entities() == 2
    assert b.truncated is True


def test_build_context_respects_token_budget(filled):
    s, _ = filled
    # Tiny budget — header alone may consume it. We expect truncation.
    b = build_context(s, "parser", max_tokens=10)
    assert b.truncated is True


def test_render_text_includes_labels_and_tldr(filled):
    s, _ = filled
    out = render_text(build_context(s, "parser"))
    assert "context for `parser`" in out
    assert LINKAGE_LABELS["defines"] in out
    assert "dispatch + parse" in out


def test_render_json_is_parseable_and_well_shaped(filled):
    s, _ = filled
    raw = render_json(build_context(s, "parser"))
    data = json.loads(raw)
    assert data["ref"] == "parser"
    assert data["anchor"]["kind"] == "concept"
    assert "groups" in data and isinstance(data["groups"], dict)
    assert all(
        all(set(item) >= {"name", "kind", "tldr", "linkage"} for item in entries)
        for entries in data["groups"].values()
    )
    assert "estimated_tokens" in data


def test_entity_anchored_context_pulls_concepts_and_siblings(filled):
    s, ids = filled
    # anchor on the foo file (an entity, not a concept)
    b = build_context(s, "src/foo.py")
    assert b.anchor is not None
    assert b.anchor.kind == "code"
    # We expect to see the parser concept in the bundle (foo is `defines` parser)
    flat_names = {
        entry.entity.name for entries in b.groups.values() for entry in entries
    }
    assert "parser" in flat_names
