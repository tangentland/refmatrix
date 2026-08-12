"""`rmx describe` — every catalog fact about one entity, in one read."""
from __future__ import annotations

import json
import time

from click.testing import CliRunner

from refmatrix.cli import main
from refmatrix.store import Store


def _store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def _fixture(tmp_path):
    """A doc + its anchor + a code file, wired with mentions/part-of."""
    s = _store(tmp_path)
    src = tmp_path / "m.py"
    src.write_text("def parse():\n    return 1\n")
    doc = s.upsert_entity(kind="doc", name="docs/r.md", path=str(tmp_path / "r.md"))
    anchor = s.upsert_entity(kind="concept", name="r#intro",
                             path=str(tmp_path / "r.md"))
    code = s.upsert_entity(kind="code", name="m.py", path=str(src),
                           tldr="parses things", meta={"lang": "python"})
    parser = s.add_concept("parser")
    s.add_linkage_type("part-of", directed=True, description="x")
    s.link("mentions", parser, code, weight=3.0)
    s.link("part-of", anchor, doc)
    s.mark_tracked(str(src), src.stat().st_mtime)
    return s, {"doc": doc, "anchor": anchor, "code": code, "parser": parser}


def test_describe_entity_joins_every_table(tmp_path):
    s, ids = _fixture(tmp_path)
    d = s.describe_entity(ids["code"], include_vectors=False)

    e = d["entity"]
    assert e["id"] == ids["code"] and e["kind"] == "code"
    assert e["tldr"] == "parses things"
    assert e["meta"] == {"lang": "python"}          # JSON-decoded, not raw text
    assert e["partition"] == s.partition_name

    # outbound membership + its exact total
    assert d["links_out"]["total"] == 1
    row = d["links_out"]["shown"][0]
    assert (row["linkage"], row["concept"], row["weight"]) == \
        ("mentions", "parser", 3.0)

    # tracked_files record, with on-disk staleness resolved
    tf = d["tracked_file"]
    assert tf["path"] == str(tmp_path / "m.py")
    assert tf["stale"] is False

    assert d["memory"] is None                      # not a memory row
    assert d["pagerank"] is None                    # never computed
    s.close()


def test_describe_reports_inbound_edges_and_siblings(tmp_path):
    s, ids = _fixture(tmp_path)
    # `link(verb, concept, entity)` — the doc is the member, the anchor is
    # the concept — so part-of is OUTBOUND on the doc and INBOUND on the
    # anchor. The two share a path, so each is the other's sibling.
    doc = s.describe_entity(ids["doc"], include_vectors=False)
    assert [(r["linkage"], r["concept"]) for r in doc["links_out"]["shown"]] == \
        [("part-of", "r#intro")]
    assert doc["links_in"]["total"] == 0
    assert doc["siblings"]["shown"] == [
        {"id": ids["anchor"], "kind": "concept", "name": "r#intro"}]

    anchor = s.describe_entity(ids["anchor"], include_vectors=False)
    assert anchor["links_in"]["total"] == 1
    inb = anchor["links_in"]["shown"][0]
    assert inb["linkage"] == "part-of" and inb["name"] == "docs/r.md"
    assert inb["kind"] == "doc"
    s.close()


def test_describe_limits_truncate_rows_not_totals(tmp_path):
    s = _store(tmp_path)
    code = s.upsert_entity(kind="code", name="m.py", path="/x/m.py")
    for i in range(5):
        s.link("mentions", s.add_concept(f"c{i}"), code, weight=float(i))
    d = s.describe_entity(code, edge_limit=2, include_vectors=False)
    assert d["links_out"]["total"] == 5           # exact
    assert len(d["links_out"]["shown"]) == 2      # clipped
    assert [r["concept"] for r in d["links_out"]["shown"]] == ["c4", "c3"]
    s.close()


def test_describe_surfaces_memory_sidecar(tmp_path):
    s = _store(tmp_path)
    eid = s.add_memory(
        name="mem-one", content="body text", mtype="project",
        tags=["a", "b"], metadata={"source": "test"},
    )
    d = s.describe_entity(eid, include_vectors=False)
    m = d["memory"]
    assert m["content"] == "body text" and m["mtype"] == "project"
    assert m["tags"] == ["a", "b"]
    assert m["metadata"]["source"] == "test"
    s.close()


def test_describe_evidence_is_capped_but_counted(tmp_path):
    s = _store(tmp_path)
    code = s.upsert_entity(kind="code", name="m.py", path="/x/m.py")
    parser = s.add_concept("parser")
    s.link("mentions", parser, code, weight=1.0)
    for line in range(1, 6):
        s.add_evidence("mentions", parser, code, file="/x/m.py", line=line)
    d = s.describe_entity(code, evidence_limit=2, include_vectors=False)
    row = d["links_out"]["shown"][0]
    assert row["evidence_count"] == 5
    assert len(row["evidence"]) == 2
    s.close()


def test_find_describe_targets_resolution_order(tmp_path):
    s, ids = _fixture(tmp_path)
    src = str(tmp_path / "m.py")
    # id
    assert [t["id"] for t in s.find_describe_targets(str(ids["code"]))] == \
        [ids["code"]]
    # exact path
    assert [t["id"] for t in s.find_describe_targets(src)] == [ids["code"]]
    # name
    assert [t["id"] for t in s.find_describe_targets("docs/r.md")] == [ids["doc"]]
    # path suffix
    assert [t["id"] for t in s.find_describe_targets("m.py")] == [ids["code"]]
    # nothing
    assert s.find_describe_targets("no-such-ref") == []
    s.close()


def test_find_describe_targets_returns_all_ambiguous_matches(tmp_path):
    s = _store(tmp_path)
    a = s.upsert_entity(kind="code", name="a/__init__.py", path="/x/a/__init__.py")
    b = s.upsert_entity(kind="code", name="b/__init__.py", path="/x/b/__init__.py")
    got = {t["id"] for t in s.find_describe_targets("__init__.py")}
    assert got == {a, b}
    s.close()


def test_cli_describe_json_and_ambiguity(tmp_path, monkeypatch):
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    s, ids = _fixture(tmp_path)
    s.close()
    runner = CliRunner()

    r = runner.invoke(main, ["describe", "m.py", "--format", "json",
                             "--no-vectors"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["entity"]["id"] == ids["code"]
    assert payload["links_out"]["total"] == 1

    # text rendering names the tables it joined
    r2 = runner.invoke(main, ["describe", str(ids["code"]), "--no-vectors"])
    assert r2.exit_code == 0, r2.output
    # Header names the direction explicitly: these rows match on entity_id,
    # so the described entity is the TARGET side of the stored edge.
    assert "edges INTO this entity" in r2.output
    assert "tracked_file" in r2.output

    # unresolvable ref fails loudly instead of printing an empty dump
    r3 = runner.invoke(main, ["describe", "no-such-ref"])
    assert r3.exit_code != 0
    assert "no entity matches" in r3.output


def test_cli_describe_ambiguous_lists_then_first_picks(tmp_path, monkeypatch):
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    s = _store(tmp_path)
    s.upsert_entity(kind="code", name="a/__init__.py", path="/x/a/__init__.py")
    s.upsert_entity(kind="code", name="b/__init__.py", path="/x/b/__init__.py")
    s.close()
    runner = CliRunner()

    r = runner.invoke(main, ["describe", "__init__.py", "--format", "json"])
    assert r.exit_code == 0, r.output
    assert len(json.loads(r.output)["ambiguous"]) == 2

    r2 = runner.invoke(main, ["describe", "__init__.py", "--first",
                              "--format", "json", "--no-vectors"])
    assert r2.exit_code == 0, r2.output
    assert json.loads(r2.output)["entity"]["kind"] == "code"


def test_describe_flags_a_stale_tracked_file(tmp_path):
    s = _store(tmp_path)
    src = tmp_path / "m.py"
    src.write_text("x = 1\n")
    eid = s.upsert_entity(kind="code", name="m.py", path=str(src))
    s.mark_tracked(str(src), src.stat().st_mtime)
    # touch the file into the future: on-disk mtime now beats last_synced
    future = time.time() + 3600
    import os
    os.utime(src, (future, future))
    d = s.describe_entity(eid, include_vectors=False)
    assert d["tracked_file"]["stale"] is True
    s.close()
