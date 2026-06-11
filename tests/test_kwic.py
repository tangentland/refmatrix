"""Tests for the KWIC snippet helper + context co-mention snippets."""
from __future__ import annotations

from refmatrix.context import (
    ContextEntry, _content_snippet, _render_entry, _section_text,
    build_context, content_only_bundle, render_text,
)
from refmatrix.kwic import kwic_def_line, kwic_line, kwic_one, query_terms
from refmatrix.store import Entity, Store


def test_query_terms_dedup_minlen_longest_first():
    assert query_terms("FOV fov a of field") == ["field", "fov", "of"]


def test_kwic_centers_on_match_and_marks_it():
    text = "alpha beta gamma fov delta epsilon zeta"
    out = kwic_one(text, "fov", width=20)
    assert "«fov»" in out
    assert "gamma" in out and "delta" in out


def test_kwic_preserves_original_case():
    out = kwic_one("the FovWedge default angle is 90", "fov", width=40)
    assert "«Fov»Wedge" in out


def test_kwic_collapses_whitespace():
    out = kwic_one("a\n\n   b   fov\tc", "fov", width=40)
    assert "\n" not in out and "\t" not in out


def test_kwic_empty_when_term_absent():
    assert kwic_one("nothing relevant here", "fov") == ""


def test_kwic_empty_on_missing_inputs():
    assert kwic_one("", "fov") == ""
    assert kwic_one("text", "") == ""
    assert kwic_one(None, "fov") == ""


def test_kwic_ellipsis_only_when_truncated():
    short = "fov is here"
    assert "…" not in kwic_one(short, "fov", width=200)
    long = "x " * 200 + "fov" + " y" * 200
    assert kwic_one(long, "fov", width=40).startswith("…")
    assert kwic_one(long, "fov", width=40).endswith("…")


def test_kwic_picks_earliest_among_terms():
    out = kwic_one("first camera then perspective marker", "perspective camera",
                   width=30)
    # 'camera' occurs earlier than 'perspective' -> window centers on it
    assert "«camera»" in out


_CODE = (
    "import os\n"
    "\n"
    "FOV_CONST = 90  # snapshot of the default\n"
    "\n"
    "def fov_wedge_polygon(angle):\n"
    "    \"\"\"Build the wedge for the camera snapshot.\"\"\"\n"
    "    return angle * 2\n"
    "\n"
    "def other():\n"
    "    return fov_wedge_polygon(45)\n"
)


def test_kwic_def_line_anchors_on_definition_not_first_hit():
    # 'fov' appears first on the FOV_CONST line; the def-anchored window must
    # land on the `def fov_wedge_polygon` line instead.
    out = kwic_def_line(_CODE, "fov wedge", "fov_wedge_polygon", expand=0)
    assert out == "def «fov»_wedge_polygon(angle):"


def test_kwic_def_line_expand_adds_grep_context():
    out = kwic_def_line(_CODE, "fov wedge", "fov_wedge_polygon", expand=1)
    lines = out.splitlines()
    assert lines == [
        "def «fov»_wedge_polygon(angle):",
        '    """Build the wedge for the camera snapshot."""',
    ]
    # ±2 reaches the blank-trimmed body below and the line above the def.
    out2 = kwic_def_line(_CODE, "fov wedge", "fov_wedge_polygon", expand=2)
    assert "return angle * 2" in out2


def test_kwic_def_line_marks_symbol_when_query_term_elsewhere():
    # Query term absent from the def line -> the symbol itself is marked.
    out = kwic_def_line(_CODE, "camera", "fov_wedge_polygon", expand=0)
    assert out == "def «fov_wedge_polygon»(angle):"


def test_kwic_def_line_empty_when_no_definition():
    assert kwic_def_line(_CODE, "fov", "nonexistent_symbol") == ""
    assert kwic_def_line("", "fov", "x") == ""
    assert kwic_def_line(_CODE, "fov", None) == ""


def test_content_snippet_reads_source_file_for_code_entity(tmp_path):
    """A code content-hit windows the real source file (grep -C), anchored on
    the symbol's def line — not the one-line tldr, which can't be expanded."""
    src = tmp_path / "region_detection.py"
    src.write_text(_CODE)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    eid = s.upsert_entity(kind="code",
                          name="region_detection.py::fov_wedge_polygon",
                          path=str(src), tldr="fov_wedge_polygon()",
                          meta={"norm_label": "fov_wedge_polygon()"})
    ent = s.get_entity_by_id(eid)
    snip, line = _content_snippet(s, ent, ["fov", "wedge"], expand=0)
    assert snip == "def «fov»_wedge_polygon(angle):"
    assert line == 5  # 1-based def line in _CODE
    snip, line = _content_snippet(s, ent, ["fov", "wedge"], expand=1)
    assert snip.splitlines()[0] == "def «fov»_wedge_polygon(angle):"
    assert len(snip.splitlines()) == 2  # def line + docstring (blank above trimmed)
    assert line == 5
    s.close()


def test_content_snippet_code_falls_back_to_tldr_without_source(tmp_path):
    """Missing source file -> fall through to the tldr ladder, never crash."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    eid = s.upsert_entity(kind="code", name="gone.py::fov_calc",
                          path=str(tmp_path / "gone.py"),
                          tldr="computes the fov wedge")
    ent = s.get_entity_by_id(eid)
    assert _content_snippet(s, ent, ["fov"], expand=2) == ("computes the «fov» wedge", None)
    s.close()


def _code_ent(eid, name, path, **meta):
    return Entity(id=eid, kind="code", name=name, path=path,
                  tldr=name.split("::")[-1] + "()", meta=meta)


def test_render_entry_code_content_hit_leads_with_path_line():
    """#2: a code CONTENT hit prints `path:line` above the snippet so a reader
    can jump straight to the def."""
    e = ContextEntry(
        entity=_code_ent(1, "region_detection.py::fov_wedge_polygon",
                         "/abs/region_detection.py"),
        linkage="content", weight=9.0)
    e.snippet = "def «fov»_wedge_polygon(angle):"
    e.line = 5
    out = _render_entry(e).splitlines()
    assert "    /abs/region_detection.py:5" in out
    assert any("def «fov»_wedge_polygon" in ln for ln in out)
    # location must come BEFORE the snippet body
    assert out.index("    /abs/region_detection.py:5") < \
        next(i for i, ln in enumerate(out) if "def «fov»" in ln)


def test_append_content_hits_dedupes_identical_twins(tmp_path, monkeypatch):
    """#3: two paths with byte-identical code (a vendored / uat-workspace
    mirror) collapse to one result instead of eating two slots."""
    from refmatrix import context as C
    real = tmp_path / "region_detection.py"
    twin = tmp_path / "uat-workspace" / "region_detection.py"
    twin.parent.mkdir(parents=True)
    real.write_text(_CODE)
    twin.write_text(_CODE)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    rid = s.upsert_entity(kind="code", name="region_detection.py::fov_wedge_polygon",
                          path=str(real))
    tid = s.upsert_entity(kind="code",
                          name="uat-workspace/region_detection.py::fov_wedge_polygon",
                          path=str(twin))
    # Bypass the BM25 index: force both ids through content ranking, real first.
    monkeypatch.setattr(s, "content_rank",
                        lambda *a, **k: [(rid, 9.0), (tid, 8.0)])
    built: list = []
    C._append_content_hits(s, "fov wedge", built, seen_ids=set(),
                           max_entities=10, expand=0, include_sessions=False,
                           parent_cache={})
    assert len(built) == 1  # twin dropped
    assert built[0].entity.id == rid  # the higher-scoring (canonical) path kept
    s.close()


def test_content_only_bundle_and_anchorless_render(tmp_path, monkeypatch):
    """#1: a ref with no graph anchor still serves a ranked-grep bundle, and
    render_text shows the content group instead of `(unknown symbol)`."""
    from refmatrix import context as C
    src = tmp_path / "region_detection.py"
    src.write_text(_CODE)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    cid = s.upsert_entity(kind="code", name="region_detection.py::fov_wedge_polygon",
                          path=str(src))
    monkeypatch.setattr(s, "content_rank", lambda *a, **k: [(cid, 9.0)])
    b = content_only_bundle(s, "fov wedge")
    assert b.anchor is None
    assert b.groups.get("content"), "expected a content group"
    txt = render_text(b)
    assert "(unknown symbol)" not in txt
    assert "def «fov»_wedge_polygon" in txt
    assert f"{src}:5" in txt  # path:line present
    s.close()


def test_build_context_falls_back_to_content_when_ref_unresolved(tmp_path, monkeypatch):
    """#1: build_context with a non-resolving ref returns the content bundle."""
    from refmatrix import context as C
    src = tmp_path / "region_detection.py"
    src.write_text(_CODE)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    cid = s.upsert_entity(kind="code", name="region_detection.py::fov_wedge_polygon",
                          path=str(src))
    monkeypatch.setattr(s, "content_rank", lambda *a, **k: [(cid, 9.0)])
    b = build_context(s, "totally unregistered phrase")
    assert b.anchor is None
    assert b.groups.get("content")
    # --linkage filtering opts OUT of the fallback (back-compat).
    b2 = build_context(s, "totally unregistered phrase", linkages=["mentions"])
    assert b2.anchor is None and not b2.groups
    s.close()


def test_section_text_slices_the_right_anchor():
    body = (
        "# Card {#root}\n\nintro fov mention one\n\n"
        "## Decisions {#decisions}\n\nmiddle text\n\n"
        "## Notes {#notes}\n\ntail fov mention two\n"
    )
    sect = _section_text(body, "decisions")
    assert "middle text" in sect
    assert "tail fov mention two" not in sect
    assert "intro fov mention one" not in sect


def test_section_text_none_for_missing_anchor():
    assert _section_text("# x {#root}\nbody", "nope") is None


_FOV_BODY = (
    "# Camera spec {#root}\n\n## Decisions {#decisions}\n\n"
    + ("filler line about cameras. " * 40)
    + "FovWedge has safe defaults (angle=90) so the box still renders.\n"
)


def _filled(tmp_path):
    """A durable doc (kind=memory, non-session) co-mentioning `fov`, with the
    term buried in the body past any tldr cap."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    fov = s.add_concept("fov", description="field of view")
    mem = s.upsert_entity(kind="memory", name="spec-camera#decisions",
                          tldr="Assistant decisions — check rmx health")
    # add_memory upserts content; tldr=None there is COALESCE-preserved.
    s.add_memory("spec-camera#decisions", _FOV_BODY, mtype="doc")
    s.weighted_link("mentions", fov, mem, weight=5.0)
    return s, fov


def test_context_mention_snippet_surfaces_the_matched_line(tmp_path):
    s, _ = _filled(tmp_path)
    b = build_context(s, "fov")
    entries = b.groups.get("mentions", [])
    assert entries, "expected a mentions group"
    snip = entries[0].snippet
    assert snip is not None
    assert "«Fov»Wedge" in snip
    # The noisy whole-tldr summary must NOT be the payload.
    assert "check rmx health" not in snip
    s.close()


def test_context_mention_snippet_in_json_and_text(tmp_path):
    from refmatrix.context import render_json, render_text
    import json as _json
    s, _ = _filled(tmp_path)
    b = build_context(s, "fov")
    data = _json.loads(render_json(b))
    snippets = [e["snippet"] for e in data["groups"]["mentions"]]
    # The marker splits the token: "«Fov»Wedge", so assert on the marked form.
    assert any(sn and "«Fov»Wedge" in sn for sn in snippets)
    assert "«Fov»Wedge" in render_text(b)
    s.close()


def test_context_snippet_via_parent_section_fetch(tmp_path):
    """Concept-kind section neighbor (no own body) -> parent doc fetched and
    sliced to the section, KWIC over that."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    fov = s.add_concept("fov", description="field of view")
    # Section anchor as a concept (no body); parent doc holds the text.
    sec = s.upsert_entity(kind="concept", name="spec-cam#sec",
                          tldr="overview only, no term here")
    body = ("# Spec {#root}\n\n## Section {#sec}\n\n"
            + ("noise. " * 30) + "the FovWedge default angle is 90.\n")
    s.add_memory("spec-cam", body, mtype="doc")
    s.weighted_link("mentions", fov, sec, weight=2.0)
    b = build_context(s, "fov")
    snip = b.groups["mentions"][0].snippet
    assert snip and "«Fov»Wedge" in snip
    s.close()


def test_context_excludes_session_summaries_by_default(tmp_path):
    s, fov = _filled(tmp_path)
    # Add a session card that also co-mentions fov, with higher weight.
    sess = s.upsert_entity(kind="memory", name="session-deadbeef#decisions")
    s.add_memory("session-deadbeef#decisions",
                 "FovWedge mentioned in a session log.", mtype="session")
    s.weighted_link("mentions", fov, sess, weight=99.0)
    names = [e.entity.name for e in build_context(s, "fov").groups["mentions"]]
    assert "spec-camera#decisions" in names
    assert "session-deadbeef#decisions" not in names  # excluded despite w=99
    # Opt back in -> session appears.
    names2 = [e.entity.name
              for e in build_context(s, "fov", include_sessions=True)
              .groups["mentions"]]
    assert "session-deadbeef#decisions" in names2
    s.close()


def test_context_ranks_hits_before_non_hits(tmp_path):
    s, fov = _filled(tmp_path)  # spec-camera#decisions IS a hit (w=5)
    # A higher-weight doc that does NOT contain the term -> non-hit.
    nohit = s.upsert_entity(kind="doc", name="unrelated-doc",
                            tldr="talks about cameras but not the term")
    s.weighted_link("mentions", fov, nohit, weight=50.0)
    entries = build_context(s, "fov").groups["mentions"]
    # The hit (snippet present) ranks first despite lower co-mention weight.
    assert entries[0].snippet is not None
    assert entries[0].entity.name == "spec-camera#decisions"
    s.close()
