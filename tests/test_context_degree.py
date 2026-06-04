"""Tests for `rmx context --degree` and memory-body inclusion.

`build_context` was historically a one-hop walk that returned anchor +
linked entities with tldr blobs only. Memories had to be fetched
separately via `rmx memory get`. The `--degree` option adds:

  * Memory body inclusion: any kind='memory' entry in the bundle
    (anchor OR neighbor) carries its full body, closing the
    get-vs-context two-surfaces cliff.
  * Auto-scaled budgets for degree>0: when the caller did NOT
    explicitly override `max_entities` / `max_tokens`, they scale with
    the requested degree so a deeper request gets a deeper budget.
    Explicit overrides win.
  * `degree` propagation to the rendered bundle so downstream tools
    can show / branch on the requested depth.
"""
from __future__ import annotations

import json

import pytest

from refmatrix.context import build_context, render_json, render_text
from refmatrix.store import Store


@pytest.fixture
def memory_store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def test_anchor_memory_body_attached_to_bundle(memory_store):
    """The defining win: `context <memory-name>` returns the body,
    not just the entity row + linkage walk."""
    s = memory_store
    s.add_memory("policy-snapshot", "Use snapshot-tier for reads.",
                 mtype="curated")
    b = build_context(s, "policy-snapshot")
    assert b.anchor is not None
    assert b.anchor.kind == "memory"
    assert b.anchor_body == "Use snapshot-tier for reads."


def test_anchor_body_is_none_for_non_memory_anchors(memory_store):
    s = memory_store
    s.add_concept("parser")
    b = build_context(s, "parser")
    assert b.anchor is not None
    assert b.anchor.kind == "concept"
    assert b.anchor_body is None


def test_memory_neighbor_carries_body_through_one_hop_walk(memory_store):
    """A memory neighbor of a non-memory anchor must also carry its
    body — that's the value-add for code/doc anchors that reach
    into the memory layer via `mentions` / `recalls` / etc."""
    s = memory_store
    parser = s.add_concept("parser")
    note_id = s.add_memory("parser-quirk", "Tabs in indentation break it.",
                           mtype="observation")
    s.link("mentions", parser, note_id)
    b = build_context(s, "parser")
    flat = [
        e for entries in b.groups.values() for e in entries
    ]
    note_entries = [e for e in flat if e.entity.kind == "memory"]
    assert len(note_entries) == 1
    assert note_entries[0].body == "Tabs in indentation break it."


def test_degree_zero_is_the_default_and_keeps_current_walk(memory_store):
    """degree=0 must NOT regress the existing one-hop walk — it just
    adds memory bodies. A concept anchor with linked entities still
    gets the linkage groups."""
    s = memory_store
    parser = s.add_concept("parser")
    foo = s.upsert_entity(kind="code", name="foo.py", tldr="parses")
    s.link("defines", parser, foo)
    b = build_context(s, "parser")  # degree defaults to 0
    assert b.degree == 0
    assert "defines" in b.groups
    assert any(e.entity.name == "foo.py" for e in b.groups["defines"])


def test_degree_propagates_to_bundle(memory_store):
    s = memory_store
    s.add_concept("parser")
    b = build_context(s, "parser", degree=2)
    assert b.degree == 2


def test_degree_gt_zero_auto_scales_budgets_when_defaults_used(
    memory_store,
):
    """At degree=0 with the default 4000-token budget, a busy concept
    might truncate. At degree=2 (with the same default budget flowing
    through) the helper should multiply the budget by (1+degree)=3,
    fitting more before truncating. Verify the multiplier reaches
    the walk."""
    s = memory_store
    parser = s.add_concept("parser")
    # Plant enough entities so the scaled budget actually binds (60+).
    for i in range(80):
        eid = s.upsert_entity(kind="code", name=f"f{i}.py", tldr=f"e{i}")
        s.link("defines", parser, eid)

    base = build_context(s, "parser")  # degree=0, max_entities=20
    deep = build_context(s, "parser", degree=2)  # auto-scale to 60
    assert base.total_entities() == 20
    assert deep.total_entities() == 60


def test_explicit_max_entities_blocks_auto_scale(memory_store):
    """When the caller explicitly passes a budget, the auto-scale
    must NOT override it. The CLI signals 'explicit' via the
    `_entities_explicit=True` flag (its default for the helper)."""
    s = memory_store
    parser = s.add_concept("parser")
    for i in range(50):
        eid = s.upsert_entity(kind="code", name=f"f{i}.py", tldr=f"e{i}")
        s.link("defines", parser, eid)
    b = build_context(
        s, "parser", degree=2, max_entities=5,
        _entities_explicit=True,
    )
    assert b.total_entities() == 5  # capped at the user's number


def test_explicit_flag_false_lets_auto_scale_through(memory_store):
    """The flag default is False (auto-scale on degree>0); the CLI flips
    it to True only when click reports the param came from COMMANDLINE.
    Verify the helper behavior in that path."""
    s = memory_store
    parser = s.add_concept("parser")
    # Plant enough entities so the scaled budget actually binds.
    for i in range(80):
        eid = s.upsert_entity(kind="code", name=f"f{i}.py", tldr=f"e{i}")
        s.link("defines", parser, eid)
    b = build_context(
        s, "parser", degree=2, max_entities=20,
        _entities_explicit=False,
    )
    # Scaled to 20 * (1 + 2) = 60.
    assert b.total_entities() == 60


def test_render_text_shows_anchor_body_section_for_memory(memory_store):
    s = memory_store
    s.add_memory("policy-snapshot", "snapshot-tier for reads", mtype="curated")
    out = render_text(build_context(s, "policy-snapshot"))
    assert "--- body ---" in out
    assert "snapshot-tier for reads" in out


def test_render_text_shows_neighbor_memory_body_block(memory_store):
    s = memory_store
    parser = s.add_concept("parser")
    nid = s.add_memory("parser-quirk", "Tabs break indentation",
                       mtype="observation")
    s.link("mentions", parser, nid)
    out = render_text(build_context(s, "parser"))
    assert "Tabs break indentation" in out


def test_render_json_includes_anchor_body_and_neighbor_body(memory_store):
    s = memory_store
    parser = s.add_concept("parser")
    nid = s.add_memory("note", "body content here", mtype="observation")
    s.link("mentions", parser, nid)
    data = json.loads(render_json(build_context(s, "parser")))
    assert data["degree"] == 0
    assert "body" in data["anchor"]
    nbr = data["groups"]["mentions"][0]
    assert nbr["body"] == "body content here"
