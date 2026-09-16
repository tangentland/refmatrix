"""The brief index as GMD — and the round trip that proves it is regenerable.

RED first for task 8.3 (plan-8). `memory compile` states the contract this
follows: "the index is regenerable from the store, and the store is rebuildable
from the index." A derived doc that cannot survive that trip is a report, not a
node in the graph, and the next session cannot cite it.

The direction of the edge matters and has bitten this repo once already.
`consolidate.render_gmd` emits `catalogs` from the container to its members
precisely because emitting the store's own inverse (`part-of`) would have
claimed the subject is part of its own members. A brief CITES its evidence, so
the verb is `evidence-for` pointed at the brief — the evidence supports the
finding, not the other way round.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from refmatrix import brief


def _b(cls="singleton", label="lonely-note", finding="touched once",
       evidence=(4,), detail=None):
    return brief.Brief(cls=cls, label=label, finding=finding,
                       evidence=list(evidence), detail=detail or {})


def _render(briefs, **kw) -> str:
    return brief.render_gmd(briefs, **kw)


def _names(store_names):
    return {i: n for i, n in store_names.items()}


# ── the document ───────────────────────────────────────────────────────────

def test_render_passes_the_repo_linter_with_zero_errors(tmp_path):
    """Linted ALONGSIDE the docs it cites.

    An index is a doc full of outbound wikilinks; linting it alone always
    reports `dangling-doc` for every target outside the scanned set, which
    says nothing about the index. Writing the cited memories beside it is what
    actually tests that the edges resolve.
    """
    names = {1: "m-one", 2: "m-two", 3: "m-three", 4: "lonely-note"}
    doc = _render([_b(), _b(cls="orphan-concept", label="fast_exit",
                          finding="mentioned by 9, defined by none",
                          evidence=[1, 2, 3])],
                  names=names)
    (tmp_path / "memory-briefs.md").write_text(doc)
    for n in names.values():
        (tmp_path / f"{n}.md").write_text(
            f'---\ngmd: "0.1"\nid: {n}\ntitle: "{n}"\ntags: [memory]\n---\n\n'
            f'# {n} {{#root}}\n\nbody\n')
    lint = Path(__file__).resolve().parents[1] / "tools" / "gmd" / "lint.py"
    p = subprocess.run([sys.executable, str(lint), str(tmp_path)],
                       capture_output=True, text=True)
    assert "0 errors" in (p.stdout + p.stderr), p.stdout + p.stderr


def test_every_heading_carries_an_anchor():
    doc = _render([_b(), _b(cls="contradicted", label="a vs b",
                           finding="unresolved", evidence=[1, 2])],
                  names={1: "a", 2: "b", 4: "lonely-note"})
    for line in doc.splitlines():
        if line.startswith("#"):
            assert line.rstrip().endswith("}"), line


def test_the_doc_says_it_is_derived_and_names_its_regenerating_command():
    """`consolidate.render_gmd` carries the same line; a reader must never
    mistake a derived index for an authored one."""
    doc = _render([_b()], names={4: "lonely-note"})
    assert "rmx memory brief" in doc
    assert "erived" in doc          # "Derived, not authored"


def test_evidence_becomes_a_typed_edge_pointing_at_the_brief():
    """A brief cites its evidence: the evidence supports the finding."""
    doc = _render([_b(evidence=[7])], names={7: "the-memory"})
    assert "rel: evidence-for -> [[the-memory]]" in doc


def test_an_unnamed_evidence_id_is_reported_not_silently_dropped():
    """A `rel:` to an id nobody can resolve is a dangling edge, so it is not
    emitted as one — but it must still be VISIBLE, in both places that carry
    it. Two carriers that can mask each other is how a dropped field survives
    a green test suite (`impression_bsd_faked_wire_field`), so each is pinned
    on its own."""
    doc = _render([_b(evidence=[7, 99])], names={7: "the-memory"})
    assert "rel: evidence-for -> [[the-memory]]" in doc
    assert "rel: evidence-for -> [[99]]" not in doc, "dangling edge emitted"

    # carrier 1: the inline evidence list marks it unresolved
    ev_line = next(l for l in doc.splitlines() if l.startswith("Evidence ("))
    assert "`99` (unresolved)" in ev_line, ev_line
    assert ev_line.startswith("Evidence (2):"), "the COUNT must not shrink"

    # carrier 2: the standalone note states how many could not be resolved
    note = next(l for l in doc.splitlines()
                if "could not be resolved" in l)
    assert "1 evidence id(s)" in note, note
    assert "99" in note, note


def test_briefs_are_grouped_by_class_each_under_its_own_anchored_heading():
    doc = _render([_b(), _b(cls="orphan-concept", label="term",
                           finding="unpinned", evidence=[1])],
                  names={1: "m", 4: "lonely-note"})
    assert "{#singleton}" in doc
    assert "{#orphan-concept}" in doc


def test_an_empty_brief_set_still_renders_a_valid_document(tmp_path):
    """Zero briefs is a RESULT — a clean corpus — not an error, and the doc
    has to say so rather than emitting a broken stub."""
    doc = _render([], names={})
    out = tmp_path / "empty.md"
    out.write_text(doc)
    lint = Path(__file__).resolve().parents[1] / "tools" / "gmd" / "lint.py"
    p = subprocess.run([sys.executable, str(lint), str(out)],
                       capture_output=True, text=True)
    assert "0 errors" in (p.stdout + p.stderr), p.stdout + p.stderr
    assert "no briefs" in doc.lower()


# ── the round trip ─────────────────────────────────────────────────────────

def test_render_is_deterministic_for_the_same_input():
    briefs = [_b(cls="orphan-concept", label="b", finding="f", evidence=[2]),
              _b(cls="singleton", label="a", finding="f", evidence=[1])]
    names = {1: "m-a", 2: "m-b"}
    assert _render(briefs, names=names) == _render(briefs, names=names)


def test_render_is_order_independent_so_a_rerun_does_not_churn_the_file():
    """Two runs over the same store must produce the same bytes even if the
    detectors emitted in a different order — otherwise every run is a diff.

    The fixture puts SEVERAL briefs in ONE class: grouping by class already
    normalises across classes, so a within-class shuffle is the only shuffle
    that can prove the sort is doing work.
    """
    a = [_b(cls="singleton", label="c", finding="f", evidence=[3]),
         _b(cls="singleton", label="a", finding="f", evidence=[1]),
         _b(cls="singleton", label="b", finding="f", evidence=[2]),
         _b(cls="orphan-concept", label="z", finding="f", evidence=[1])]
    names = {1: "m-a", 2: "m-b", 3: "m-c"}
    first = _render(a, names=names)
    assert first == _render(list(reversed(a)), names=names)
    assert first == _render([a[1], a[3], a[2], a[0]], names=names)
    # and the order is the sorted one, not whichever arrived first
    labels = [l for l in first.splitlines() if l.startswith("### ")]
    assert labels == ["### z {#orphan-concept-z}", "### a {#singleton-a}",
                      "### b {#singleton-b}", "### c {#singleton-c}"]


def test_parse_gmd_recovers_every_brief_the_render_wrote():
    """The store is rebuildable from the index."""
    briefs = [_b(cls="singleton", label="lonely", finding="touched once",
                 evidence=[4]),
              _b(cls="orphan-concept", label="fast_exit",
                 finding="mentioned by 9, defined by none", evidence=[1, 2])]
    names = {1: "m-one", 2: "m-two", 4: "lonely"}
    doc = _render(briefs, names=names)
    back = brief.parse_gmd(doc)
    assert [(b["class"], b["label"]) for b in back] == [
        ("orphan-concept", "fast_exit"), ("singleton", "lonely")]
    assert back[0]["finding"] == "mentioned by 9, defined by none"


def test_render_parse_render_is_byte_identical():
    briefs = [_b(cls="contradicted", label="a vs b", finding="unresolved",
                 evidence=[1, 2])]
    names = {1: "a", 2: "b"}
    once = _render(briefs, names=names)
    twice = brief.render_gmd(
        [brief.Brief(cls=d["class"], label=d["label"], finding=d["finding"],
                     evidence=[1, 2]) for d in brief.parse_gmd(once)],
        names=names)
    assert once == twice
