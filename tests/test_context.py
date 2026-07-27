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


def test_static_edge_group_carries_completeness_note(filled):
    """`called_by`/`calls` are static-extraction — the renderer must flag them
    as a lower bound, never a census (cliquedb bug #5fcfecd3862a, asks #2+#3)."""
    s, _ = filled
    out = render_text(build_context(s, "parser"))
    assert "completeness: static-extraction only" in out
    assert "lower bound, not a census" in out
    # Non-SQL anchor → general dynamic-dispatch wording, not the SQL variant.
    assert "dynamic-dispatch call sites" in out
    # The note attaches to the static-edge group, not to `mentions`.
    lines = out.splitlines()
    note_idx = next(i for i, ln in enumerate(lines) if "completeness:" in ln)
    header = next(lines[j] for j in range(note_idx, -1, -1) if "(" in lines[j]
                  and lines[j].endswith("):"))
    assert "called_by" in header


def test_completeness_note_sql_variant_calls_out_dynamic_sql(tmp_path):
    """SQL anchor → the note names dynamic SQL (`EXECUTE format`) explicitly."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    fn = s.add_concept("facet_key", description="clique key builder")
    caller = s.upsert_entity(kind="code", name="resolve_predicate",
                             path="/p/sql/D1_facade_verbs.sql", tldr="verb")
    s.link("calls", fn, caller)
    out = render_text(build_context(s, "facet_key"))
    assert "dynamic SQL (`EXECUTE format(...)`)" in out
    assert "not resolved" in out
    s.close()


def test_group_notes_surfaced_in_json(filled):
    s, _ = filled
    data = json.loads(render_json(build_context(s, "parser")))
    assert "group_notes" in data
    assert "called_by" in data["group_notes"]
    assert "static-extraction only" in data["group_notes"]["called_by"]
    # `mentions` is not a static-edge group → no note.
    assert "mentions" not in data["group_notes"]


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


def test_build_context_inlines_memory_body_for_bare_slug(tmp_path):
    """A slug that exists as BOTH a concept and a same-named memory anchors on
    the concept (concept-first resolution) but must still surface the memory
    body — `rmx context <slug>` should return content, not just a graph stub."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_concept("widget_notes", description="concept stub for the slug")
    s.add_memory(
        name="widget_notes",
        content="# Widget notes\n\nThe frobnicator must be primed first.",
        mtype="project",
    )
    b = build_context(s, "widget_notes")
    assert b.anchor is not None
    # concept-first resolution: anchor is the concept node...
    assert b.anchor.kind == "concept"
    # ...but the memory body is enriched onto the bundle.
    assert b.anchor_body is not None
    assert "frobnicator must be primed" in b.anchor_body
    assert "--- body ---" in render_text(b)
    s.close()


def test_kwic_line_whole_line_and_expand():
    from refmatrix.kwic import kwic_line
    body = "intro\nThe FOV wedge here\ntrailing\nmore"
    # default: just the whole matched line, term marked
    assert kwic_line(body, "fov wedge") == "The «FOV» wedge here"
    # expand=1: one context line each side
    assert kwic_line(body, "fov wedge", expand=1).splitlines() == [
        "intro", "The «FOV» wedge here", "trailing",
    ]
    # no hit → empty
    assert kwic_line(body, "absent") == ""


def test_build_context_content_fusion_surfaces_phrase_matches(tmp_path):
    """A natural-language phrase whose terms were never co-mentioned on one
    node has no graph anchor — content-ranked fusion (BM25 over `mentions`)
    must still surface the entities whose bodies contain the terms, ranked,
    under a `content` group."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    # weak anchor: the concept the phrase canonicalizes to, with NO edges
    s.add_concept("fov_wedge")
    fov = s.add_concept("fov")
    wedge = s.add_concept("wedge")
    cam = s.add_concept("camera")
    f1 = s.upsert_entity(kind="code", name="src/region_detection.py",
                         tldr="convert each camera FOV wedge to a polygon")
    f3 = s.upsert_entity(kind="doc", name="docs/spatial.md",
                         tldr="The FOV wedge as calibration primitive")
    f4 = s.upsert_entity(kind="doc", name="docs/unrelated.md",
                         tldr="camera mounting guide")
    for c, ent, w in [(fov, f1, 3.0), (wedge, f1, 2.0),
                      (fov, f3, 2.0), (wedge, f3, 3.0), (cam, f4, 5.0)]:
        s.weighted_link("mentions", c, ent, weight=w)
    s.flush_fragments()

    b = build_context(s, "fov wedge", max_entities=10)
    assert "content" in b.groups
    names = [e.entity.name for e in b.groups["content"]]
    # both-term docs surface; the camera-only doc does not
    assert "src/region_detection.py" in names
    assert "docs/spatial.md" in names
    assert "docs/unrelated.md" not in names
    # content hits carry KWIC snippets
    assert any(e.snippet for e in b.groups["content"])
    s.close()


def test_build_context_truncates_long_anchor_body_to_budget(tmp_path):
    """A long memory body must not swallow the whole bundle — it's capped to a
    fraction of max_tokens so the scan-prompt hook's small per-concept budget
    still leaves room for the graph view."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_concept("big_note", description="stub")
    s.add_memory(name="big_note", content="lorem ipsum " * 1000, mtype="project")
    b = build_context(s, "big_note", max_tokens=600)
    assert b.anchor_body is not None
    assert "body truncated to fit budget" in b.anchor_body
    s.close()
