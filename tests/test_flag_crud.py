"""CRUD for the protected / noise flags + entity forget (selector layer)."""
from __future__ import annotations

from refmatrix.store import Store


def _store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def test_find_entity_ids_selectors(tmp_path):
    s = _store(tmp_path)
    s.add_concept("alpha", protected=False)
    s.upsert_entity(kind="code", name="src/m.py", path="/x/m.py", protected=False)
    s.upsert_entity(kind="doc", name="docs/r.md", path="/x/r.md", protected=False)
    assert {r[1] for r in s.find_entity_ids()} >= {"alpha", "src/m.py", "docs/r.md"}
    assert [r[1] for r in s.find_entity_ids(names=["alpha"])] == ["alpha"]
    assert [r[1] for r in s.find_entity_ids(like="src/%")] == ["src/m.py"]
    assert [r[1] for r in s.find_entity_ids(kind="doc")] == ["docs/r.md"]
    s.close()


def test_protected_and_noise_set_clear(tmp_path):
    s = _store(tmp_path)
    s.add_concept("alpha", protected=False)
    s.upsert_entity(kind="code", name="m.py", path="/x/m.py", protected=False)
    # set protected by name
    r = s.set_flag_by_selector("protected", True, names=["alpha"])
    assert r["count"] == 1 and r["names"] == ["alpha"]
    assert s.find_entity_ids(names=["alpha"])[0][3] == 1
    # set noise by glob
    s.set_flag_by_selector("noise", True, like="m.%")
    assert s.find_entity_ids(names=["m.py"])[0][4] == 1
    # clear both
    s.set_flag_by_selector("protected", False, names=["alpha"])
    s.set_flag_by_selector("noise", False, names=["m.py"])
    assert s.find_entity_ids(names=["alpha"])[0][3] == 0
    assert s.find_entity_ids(names=["m.py"])[0][4] == 0
    # filter selectors round-trip
    s.set_flag_by_selector("protected", True, names=["alpha"])
    assert [r[1] for r in s.find_entity_ids(protected=True)] == ["alpha"]
    s.close()


def test_forget_dry_run_then_delete(tmp_path):
    s = _store(tmp_path)
    s.add_concept("alpha", protected=True)  # protected — forget still removes it
    dr = s.forget_by_selector(dry_run=True, names=["alpha"])
    assert dr["names"] == ["alpha"] and dr["forgotten"] == 0
    assert s.find_entity_ids(names=["alpha"])               # still present
    fr = s.forget_by_selector(names=["alpha"])
    assert fr["forgotten"] == 1
    assert not s.find_entity_ids(names=["alpha"])           # gone
    s.close()


def test_forget_by_namespace_spares_others(tmp_path):
    """The motivating case: bulk-forget learned `query/*` concepts (which
    prune-noise/vacuum spare because they're protected) while keeping the rest."""
    s = _store(tmp_path)
    s.add_concept("query/foo", protected=True)
    s.add_concept("query/bar", protected=True)
    s.add_concept("keepme", protected=True)
    assert set(s.forget_by_selector(dry_run=True, namespace="query")["names"]) == \
        {"query/foo", "query/bar"}
    s.forget_by_selector(namespace="query")
    assert not s.find_entity_ids(namespace="query")
    assert [r[1] for r in s.find_entity_ids(names=["keepme"])] == ["keepme"]
    s.close()


def test_set_entity_flag_survives_rebuild_from_log(tmp_path):
    """protect emits a replayable event → the flag persists across a
    rebuild-from-log (not just an in-memory UPDATE)."""
    s = _store(tmp_path)
    s.add_concept("alpha", protected=False)
    s.set_flag_by_selector("protected", True, names=["alpha"])
    # Wipe the catalog and replay purely from facts.log.
    s.rebuild_index_from_log()
    assert s.find_entity_ids(names=["alpha"])[0][3] == 1
    s.close()


def test_forget_by_selector_bulk_purges_and_cleans_bitmaps(tmp_path):
    """forget --kind code over many rows: rows + linkages + bitmap bits all
    drop in one batched pass; untouched concepts stay intact."""
    s = _store(tmp_path)
    shared = s.add_concept("shared")
    keep = s.add_concept("keepme")
    codes = [s.upsert_entity(kind="code", name=f"f{i}.py", path=f"/r/f{i}.py",
                             tldr="x") for i in range(6)]
    for e in codes:
        s.link("mentions", shared, e)
        s.link("defines", shared, e)
    doc = s.upsert_entity(kind="doc", name="d.md", path="/r/d.md")
    s.link("mentions", keep, doc)

    # dry-run previews, deletes nothing
    dry = s.forget_by_selector(dry_run=True, kind="code")
    assert dry["forgotten"] == 0 and len(dry["names"]) == 6

    res = s.forget_by_selector(kind="code")
    assert res["forgotten"] == 6
    con = s._connect()
    assert con.execute(
        "SELECT count(*) FROM entities WHERE kind='code'").fetchone()[0] == 0
    # only the keep->doc edge survives
    assert con.execute("SELECT count(*) FROM entity_links").fetchone()[0] == 1
    # shared's mention/defines bitmaps fully cleared; keep untouched
    assert len(s.load_bitmap("mentions", shared)) == 0
    assert len(s.load_bitmap("defines", shared)) == 0
    assert len(s.load_bitmap("mentions", keep)) == 1
    s.close()


def test_forget_by_selector_purges_concept_side_bits(tmp_path):
    """Forgetting a concept clears the rows where it is the concept side too."""
    s = _store(tmp_path)
    victim = s.add_concept("victim")
    e = s.upsert_entity(kind="code", name="a.py", path="/r/a.py")
    s.link("mentions", victim, e)
    assert len(s.load_bitmap("mentions", victim)) == 1
    s.forget_by_selector(names=["victim"])
    con = s._connect()
    assert con.execute(
        "SELECT count(*) FROM entities WHERE name='victim'").fetchone()[0] == 0
    assert len(s.load_bitmap("mentions", victim)) == 0
    s.close()
