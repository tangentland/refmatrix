"""bug-117: a rebuild from facts.log dropped every link / evidence row whose CONCEPT end is not an
entity of kind `concept` — a doc anchor, a memory row, a code symbol used as a `rel:` target.

The write side logged only the concept's NAME (`c`); the replay side looked it up as kind
`concept`. On cliquedb all 14,745 dead-concept evidence rows were `rel:` edges of that shape, found
by ch-bsd plan-16/22 r7 (`#code-facts`) while 22.2's replay-order rule was being specified.
"""
from __future__ import annotations

import json

import pytest

from refmatrix.store import Store


@pytest.fixture
def log_on(monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    yield


def _links(s: Store) -> set:
    con = s._connect()
    return {
        (lt, ck, cn, ek, en)
        for lt, ck, cn, ek, en in con.execute(
            """SELECT lt.name, c.kind, c.name, e.kind, e.name
               FROM entity_links el
               JOIN linkage_types lt ON lt.id = el.linkage_id
               JOIN entities c ON c.id = el.concept_id
               JOIN entities e ON e.id = el.entity_id""").fetchall()
    }


def _evidence(s: Store) -> set:
    con = s._connect()
    return {
        (lt, ck, cn, ek, en, f, ln)
        for lt, ck, cn, ek, en, f, ln in con.execute(
            """SELECT lt.name, c.kind, c.name, e.kind, e.name, ev.file, ev.line
               FROM linkage_evidence ev
               JOIN linkage_types lt ON lt.id = ev.linkage_id
               JOIN entities c ON c.id = ev.concept_id
               JOIN entities e ON e.id = ev.entity_id""").fetchall()
    }


def _seed_non_concept(s: Store) -> None:
    s.add_linkage_type("part-of")
    s.add_linkage_type("depends-on")
    doc = s.upsert_entity(kind="doc", name="adr-0004#rule-no-delete")
    mem = s.upsert_entity(kind="memory", name="feedback_x")
    code = s.upsert_entity(kind="code", name="src/a.py")
    plain = s.add_concept("parser")
    s.link("part-of", doc, code)
    s.link("depends-on", mem, code, weight=0.5)
    s.link("mentions", plain, code)
    s.add_evidence("part-of", doc, code, file="src/a.py", line=7)
    s.add_evidence("depends-on", mem, code, file="src/a.py", line=9)


def test_a_rebuild_keeps_links_and_evidence_whose_concept_is_not_kind_concept(tmp_path, log_on):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    _seed_non_concept(s)
    before_links, before_ev = _links(s), _evidence(s)
    assert ("part-of", "doc", "adr-0004#rule-no-delete", "code", "src/a.py") in before_links
    s.rebuild_index_from_log()
    assert _links(s) == before_links, f"lost: {before_links - _links(s)}"
    assert _evidence(s) == before_ev, f"lost: {before_ev - _evidence(s)}"
    s.close()


def test_an_unlink_of_a_non_concept_link_is_honoured_by_the_rebuild(tmp_path, log_on):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    doc = s.upsert_entity(kind="doc", name="README.md")
    code = s.upsert_entity(kind="code", name="src/a.py")
    other = s.upsert_entity(kind="code", name="src/b.py")
    s.link("mentions", doc, code)
    s.link("mentions", doc, other)
    s.unlink("mentions", doc, code)
    s.rebuild_index_from_log()
    links = _links(s)
    # The kept sibling makes this test able to fail: at HEAD every doc-concept link is
    # dropped, so "the unlinked one is gone" alone would pass by accident.
    assert ("mentions", "doc", "README.md", "code", "src/b.py") in links, links
    assert ("mentions", "doc", "README.md", "code", "src/a.py") not in links, links
    s.close()


def test_the_compacted_log_rebuilds_non_concept_rows_too(tmp_path, log_on):
    """`dump_catalog_to_log` is what every live facts.log becomes after a compaction."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    _seed_non_concept(s)
    before_links, before_ev = _links(s), _evidence(s)
    s.dump_catalog_to_log()
    dumped = [json.loads(l) for l in s.log_path.read_text().splitlines()]
    # The legacy fallback would rescue these unique names, so assert the dump itself names
    # the kind; otherwise a dump that forgot `c_kind` passes this test by accident.
    assert all(ev.get("c_kind") for ev in dumped if ev.get("op") in ("link", "evidence")), \
        [ev for ev in dumped if ev.get("op") in ("link", "evidence") and not ev.get("c_kind")]
    s.rebuild_index_from_log()
    assert _links(s) == before_links
    assert _evidence(s) == before_ev
    s.close()


def test_the_incremental_replay_resolves_non_concept_rows(tmp_path, log_on):
    """`apply_log_delta` replays events one at a time through `_apply_event_body`."""
    src = Store(tmp_path / "a" / ".refmatrix")
    src.init()
    _seed_non_concept(src)
    want_links, want_ev = _links(src), _evidence(src)
    src.close()
    dst = Store(tmp_path / "b" / ".refmatrix")
    dst.init()
    dst.log_path.write_bytes((tmp_path / "a" / ".refmatrix" / "facts.log").read_bytes())
    dst.apply_log_delta(0)
    assert _links(dst) == want_links, f"lost: {want_links - _links(dst)}"
    assert _evidence(dst) == want_ev
    dst.close()


def _legacy_log(path, events):
    with open(path, "w") as fh:
        for i, ev in enumerate(events):
            fh.write(json.dumps({"ts": 1000.0 + i, **ev}) + "\n")


def test_a_legacy_event_without_c_kind_resolves_by_unique_name(tmp_path, log_on):
    """Every log written before this fix carries no `c_kind`. A name held by exactly one
    entity in the partition resolves to it; a `concept` of that name still wins (the old rule)."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    _legacy_log(s.log_path, [
        {"op": "entity", "kind": "doc", "name": "README.md"},
        {"op": "entity", "kind": "code", "name": "src/a.py"},
        {"op": "entity", "kind": "concept", "name": "parser"},
        {"op": "entity", "kind": "doc", "name": "parser"},
        {"op": "link", "linkage": "mentions", "c": "README.md", "e_kind": "code", "e": "src/a.py"},
        {"op": "link", "linkage": "mentions", "c": "parser", "e_kind": "code", "e": "src/a.py"},
        {"op": "evidence", "linkage": "mentions", "c": "README.md", "e_kind": "code",
         "e": "src/a.py", "file": "src/a.py", "line": 3},
    ])
    s.rebuild_index_from_log()
    links = _links(s)
    assert ("mentions", "doc", "README.md", "code", "src/a.py") in links
    assert ("mentions", "concept", "parser", "code", "src/a.py") in links
    assert ("mentions", "doc", "parser", "code", "src/a.py") not in links
    assert ("mentions", "doc", "README.md", "code", "src/a.py", "src/a.py", 3) in _evidence(s)
    s.close()


def test_an_ambiguous_legacy_name_is_counted_never_guessed(tmp_path, log_on):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    _legacy_log(s.log_path, [
        {"op": "entity", "kind": "doc", "name": "notes"},
        {"op": "entity", "kind": "memory", "name": "notes"},
        {"op": "entity", "kind": "code", "name": "src/a.py"},
        {"op": "link", "linkage": "mentions", "c": "notes", "e_kind": "code", "e": "src/a.py"},
        {"op": "evidence", "linkage": "mentions", "c": "notes", "e_kind": "code",
         "e": "src/a.py", "file": "x", "line": 1},
    ])
    out = s.rebuild_index_from_log()
    assert not any(l[2] == "notes" for l in _links(s)), "an ambiguous name was guessed"
    assert out.get("links_unresolved") == 1, out
    assert out.get("evidence_unresolved") == 1, out
    s.close()


def test_new_link_and_evidence_events_carry_the_concept_kind(tmp_path, log_on):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    _seed_non_concept(s)
    evs = [json.loads(l) for l in s.log_path.read_text().splitlines()]
    for ev in evs:
        if ev.get("op") in ("link", "unlink", "evidence"):
            assert ev.get("c_kind"), ev
    s.close()


def test_the_ingest_recorder_uses_the_edge_format_and_keeps_span_end(tmp_path):
    """The parallel-ingest recorder spelled an edge `src` / `dst` and silently dropped
    `span_end` from evidence. It now writes the one edge format (`edge_records`), so a
    recorded evidence row reaches the store with every field it was given."""
    from refmatrix.ingest_records import RecordingStore, apply_record
    rs = RecordingStore("a.md", str(tmp_path / "a.md"))
    c = rs.add_concept("parser")
    rs.add_evidence("mentions", c, "@doc", file="a.md", line=3, span_end=9)
    rec = rs.record
    ev = [op for op in rec.ops if op["op"] == "evidence"][0]
    assert {"linkage", "c_kind", "c", "e_kind", "e"} <= set(ev), ev
    s = Store(tmp_path / ".refmatrix")
    s.init()
    apply_record(s, rec)
    con = s._connect()
    rows = con.execute("SELECT line, span_end FROM linkage_evidence").fetchall()
    assert (3, 9) in [tuple(r) for r in rows], rows
    s.close()
