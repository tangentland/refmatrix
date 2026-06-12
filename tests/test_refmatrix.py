"""End-to-end tests for refmatrix."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from refmatrix.query import QueryEngine
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _seed(s: Store):
    parser = s.add_concept("parser")
    tokenizer = s.add_concept("tokenizer")
    foo = s.upsert_entity(kind="code", name="src/foo.py")
    lex = s.upsert_entity(kind="code", name="src/lex.py")
    readme = s.upsert_entity(kind="doc", name="README.md")
    s.link("defines", parser, foo)
    s.link("mentions", parser, readme)
    s.link("defines", tokenizer, lex)
    s.link("related_to", parser, lex)
    return {"parser": parser, "tokenizer": tokenizer, "foo": foo, "lex": lex, "readme": readme}


def test_init_creates_layout(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    assert s.db_path.exists()
    assert s.queries_dir.is_dir()
    # bitmaps/ is the legacy on-disk fragment layout; we no longer create
    # it on fresh inits. fragments/ only materializes on SQLite backend.
    # default linkages exist
    names = {lk["name"] for lk in s.list_linkages()}
    assert {"mentions", "defines", "calls", "called_by", "imports", "is_a", "related-to"} <= names


def test_link_and_query_dsl(store):
    ids = _seed(store)
    qe = QueryEngine(store)
    assert list(qe.run("defines:parser")) == [ids["foo"]]
    assert set(qe.run("defines:parser OR mentions:parser")) == {ids["foo"], ids["readme"]}
    assert len(qe.run("defines:parser AND mentions:parser")) == 0
    assert set(qe.run("parser")) == {ids["foo"], ids["readme"], ids["lex"]}
    assert list(qe.run("defines:parser AND NOT mentions:parser")) == [ids["foo"]]


def test_pql(store):
    ids = _seed(store)
    qe = QueryEngine(store)
    assert list(qe.run_pql("Row(defines, parser)")) == [ids["foo"]]
    assert len(qe.run_pql("Intersect(Row(defines,parser), Row(related_to,parser))")) == 0
    assert set(qe.run_pql("Union(Row(defines,parser), Row(related_to,parser))")) == {ids["foo"], ids["lex"]}
    assert qe.run_pql("Count(Row(defines,parser))") == 1


def test_neighbors_walks_linkages(store):
    ids = _seed(store)
    qe = QueryEngine(store)
    nb = qe.neighbors("parser", depth=1)
    assert ids["foo"] in nb
    assert ids["readme"] in nb
    assert ids["lex"] in nb


def test_co_occurrence(store):
    ids = _seed(store)
    # link foo to both parser and tokenizer under 'defines'
    store.link("defines", ids["tokenizer"], ids["foo"])
    qe = QueryEngine(store)
    rows = qe.co_occurrence("parser", linkage="defines")
    assert ("tokenizer", 1) in rows


def test_unlink_clears_bit(store):
    ids = _seed(store)
    assert store.unlink("defines", ids["parser"], ids["foo"]) is True
    qe = QueryEngine(store)
    assert len(qe.run("defines:parser")) == 0
    assert store.unlink("defines", ids["parser"], ids["foo"]) is False  # idempotent


def test_export_import_roundtrip(store, tmp_path):
    ids = _seed(store)
    dump = tmp_path / "dump.json"
    payload = {
        "version": "test",
        "entities": [
            {"id": e.id, "kind": e.kind, "name": e.name, "path": e.path,
             "tldr": e.tldr, "meta": e.meta}
            for e in store.iter_entities()
        ],
        "linkage_types": store.list_linkages(),
        "bitmaps": {
            lk["name"]: {
                str(cid): list(store.load_bitmap(lk["name"], cid))
                for cid in store.iter_concept_ids_for_linkage(lk["name"])
            }
            for lk in store.list_linkages()
        },
    }
    dump.write_text(json.dumps(payload))

    s2 = Store(tmp_path / "other" / ".refmatrix")
    s2.init()
    id_remap = {}
    for e in payload["entities"]:
        new_id = s2.upsert_entity(kind=e["kind"], name=e["name"], path=e["path"],
                                  tldr=e["tldr"], meta=e["meta"])
        id_remap[e["id"]] = new_id
    for ln, rows in payload["bitmaps"].items():
        for cid, eids in rows.items():
            new_cid = id_remap[int(cid)]
            s2.link_many(ln, new_cid, [id_remap[x] for x in eids])

    qe2 = QueryEngine(s2)
    # parser concept name is preserved; expect same cardinality
    assert len(qe2.run("defines:parser")) == 1
    s2.close()


def test_tldr_ingester(tmp_path):
    from refmatrix.ingest import _ingest_tldr

    proj = tmp_path / "proj"
    cache = proj / ".tldr" / "cache"
    cache.mkdir(parents=True)
    (cache / "call_graph.json").write_text(json.dumps({
        "edges": [
            {"from_file": "a.py", "from_func": "f", "to_file": "b.py", "to_func": "g"},
            {"from_file": "a.py", "from_func": "f", "to_file": "c.py", "to_func": "h"},
        ],
        "languages": ["python"],
    }))
    s = Store(tmp_path / ".refmatrix")
    s.init()
    n = _ingest_tldr(s, proj)
    assert n > 0
    qe = QueryEngine(s)
    # `f` is a function-name concept; `Row(calls, g)` should contain a.py::f
    callers = qe.run_pql("Row(calls, g)")
    names = {s.get_entity_by_id(eid).name for eid in callers}
    assert "a.py::f" in names
    s.close()
