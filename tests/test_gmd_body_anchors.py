"""bug-036 — the linter and the store disagreed about what an anchor IS.

`tools/gmd/lint.py` makes any end-of-line `{#id}` addressable. `parse_gmd`
built a node only inside the heading branch. So a `rel:` edge pointing at a
list-item anchor linted clean and resolved to NOTHING in the graph: 71 of the
73 anchors in `workflow/bullshit/IMPRESSIONS.md` were invisible to the store,
including every per-run `{#imp-*}` the audit ledger cites.

GMD's own primer is the arbiter: an anchor is "a stable node id for any
heading, paragraph, or list item". The lint implemented that; the ingest did
not. Two parsers, one syntax, never compared until a repair pass compared them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from refmatrix.ingest_gmd import parse_gmd

REPO = Path(__file__).resolve().parents[1]


def _doc(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "d.md"
    p.write_text(
        '---\ngmd: "0.1"\nid: d\ntitle: "D"\ntags: [t]\n---\n\n' + body)
    return p


def test_a_list_item_anchor_becomes_a_node(tmp_path):
    doc = _doc(tmp_path, "# Root {#root}\n\n- first thing {#item-one}\n")
    ids = {n.id for n in parse_gmd(doc).nodes}
    assert "item-one" in ids, sorted(ids)


def test_a_paragraph_anchor_becomes_a_node(tmp_path):
    doc = _doc(tmp_path, "# Root {#root}\n\nA rule sentence. {#rule}\n")
    ids = {n.id for n in parse_gmd(doc).nodes}
    assert "rule" in ids, sorted(ids)


def test_a_body_anchor_is_a_child_of_its_enclosing_heading(tmp_path):
    doc = _doc(
        tmp_path,
        "# Root {#root}\n\n## Section {#sec}\n\n- a point {#point}\n")
    by_id = {n.id: n for n in parse_gmd(doc).nodes}
    assert by_id["point"].parent == "sec", by_id["point"].parent


def test_the_body_anchor_keeps_its_own_text_as_title(tmp_path):
    doc = _doc(tmp_path, "# Root {#root}\n\n- the sibling keeps the bug {#sib}\n")
    by_id = {n.id: n for n in parse_gmd(doc).nodes}
    assert "sibling keeps the bug" in by_id["sib"].title, by_id["sib"].title


def test_an_anchor_inside_a_code_fence_is_not_a_node(tmp_path):
    """The fence rule is the whole reason #b-2-r4 could delete a node. An
    anchor the parser has been told is code must stay code."""
    doc = _doc(
        tmp_path,
        "# Root {#root}\n\n```\n- not a node {#fenced}\n```\n\n- real {#real}\n")
    ids = {n.id for n in parse_gmd(doc).nodes}
    assert "fenced" not in ids, sorted(ids)
    assert "real" in ids


def test_inline_code_anchor_is_not_a_node(tmp_path):
    """`{#id}` written INSIDE backticks is being discussed, not declared."""
    doc = _doc(tmp_path, "# Root {#root}\n\nUse `{#quoted}` for ids.\n")
    ids = {n.id for n in parse_gmd(doc).nodes}
    assert "quoted" not in ids, sorted(ids)


def test_rel_attachment_is_unchanged_by_body_anchors(tmp_path):
    """DELIBERATE LIMITATION, measured before it was accepted.

    The spec says a `rel:` attaches to the nearest enclosing block WITH AN ID,
    which now includes a list item. Re-pointing those edges is a live graph
    mutation across the whole corpus, so this change makes body anchors
    RESOLVABLE without moving any existing edge. Splitting the two means the
    repair is reversible and the attachment question can be measured on its
    own. See bug-036."""
    doc = _doc(
        tmp_path,
        "# Root {#root}\n\n## Section {#sec}\n\n- a point {#point}\n"
        "rel: related-to -> [[other]]\n")
    by_id = {n.id: n for n in parse_gmd(doc).nodes}
    assert by_id["sec"].rels, "the edge still attaches to the heading"
    assert not by_id["point"].rels


def test_the_two_parsers_agree_on_the_ledger_that_exposed_this():
    """The regression that started it: the lint's anchor set and the store's
    node set, over the real file, must not diverge."""
    p = REPO / "workflow" / "bullshit" / "IMPRESSIONS.md"
    text = p.read_text()
    # Same shape the linter uses: an id declaration outside code fences.
    written, in_code = set(), False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        written.update(re.findall(r"\{#([A-Za-z0-9._-]+)\}", line))
    nodes = {n.id for n in parse_gmd(p).nodes}
    missing = sorted(written - nodes)
    assert not missing, f"{len(missing)} anchors invisible to the graph: {missing[:5]}"


@pytest.mark.parametrize("anchor", ["imp-two-paths", "imp-consolidated-0914",
                                    "imp-getsource-mid-run-edit"])
def test_cited_impression_anchors_resolve_in_the_graph(anchor):
    """Each of these is the target of a `rel:` edge in a committed ch-bsd
    report. A citation that resolves to nothing is a dangling edge whether or
    not a linter says so."""
    p = REPO / "workflow" / "bullshit" / "IMPRESSIONS.md"
    ids = {n.id for n in parse_gmd(p).nodes}
    assert anchor in ids, sorted(i for i in ids if i.startswith("imp-"))[:5]
