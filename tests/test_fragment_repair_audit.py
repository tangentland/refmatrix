"""bug-105 hotfix audit regressions (ch-bsd `bsd-bug105-hotfix-20c5ab4`, 2026-10-14).

The per-binding fragment cache (0d05525) stopped the cross-partition leak but broke two paths
that worked before it, and the repair (20c5ab4) had gaps. Each test below is one audit probe,
adopted from the auditor's probe file, plus the m8 mutant (the repair must leave no stale cache
that re-contaminates on the next write).
"""
import pytest
from pyroaring import BitMap64

from refmatrix.store import Store


@pytest.fixture
def s(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    st = Store(tmp_path / ".refmatrix", backend="duckdb"); st.init()
    yield st
    st.close()


def _rows(s):
    con = s._connect()
    out = {}
    for pid, L, blob in con._duck.execute(
            "SELECT partition_id, linkage, blob FROM bitmap_fragments").fetchall():
        out[(pid, L)] = {int(b) & 0xFFFFFFFF for b in BitMap64.deserialize(bytes(blob))}
    return out


def test_rename_with_dirty_cache_keeps_both_bits(s):
    with s.with_partition("p"):
        pid = s.partition_id
    s._partition_name, s._partition_id = "p", pid
    c = s.add_concept("k")
    a = s.upsert_entity(kind="doc", name="a.md")
    s.link("mentions", c, a)              # dirty under (pid, 'p'), not flushed
    s.rename_partition("p", "q")
    b = s.upsert_entity(kind="doc", name="b.md")
    s.link("mentions", c, b)              # now under (pid, 'q')
    s.flush_fragments()
    assert _rows(s).get((pid, "mentions")) == {a, b}


def test_transaction_exit_flushes_other_binding(s):
    c = s.add_concept("k")
    with s.transaction():
        with s.with_partition("other"):
            oid = s.partition_id
            e = s.upsert_entity(kind="doc", name="o.md")
            s.link("mentions", c, e)
    # transaction exit is the documented durability point for fragments
    assert _rows(s).get((oid, "mentions")) == {e}


def test_merge_moves_persisted_fragment_rows(s):
    with s.with_partition("src"):
        sid = s.partition_id
        c = s.add_concept("k")
        e = s.upsert_entity(kind="doc", name="o.md")
        s.link("mentions", c, e)
        s.flush_fragments()
    with s.with_partition("dst"):
        did = s.partition_id
    s.merge_partition("src", "dst")
    rows = _rows(s)
    assert (sid, "mentions") not in rows, rows
    assert rows.get((did, "mentions")) == {e}


def test_repair_drops_dead_concept_bits(s, tmp_path):
    c = s.add_concept("k")
    a = s.upsert_entity(kind="doc", name="a.md")
    s.link("mentions", c, a)
    s.flush_fragments()
    con = s._connect()
    frag = BitMap64.deserialize(bytes(con._duck.execute(
        "SELECT blob FROM bitmap_fragments WHERE linkage='mentions'").fetchone()[0]))
    frag.add(s._pack(888_888, a))          # live entity, dead concept, no entity_links row
    con._duck.execute("UPDATE bitmap_fragments SET blob=? WHERE linkage='mentions'",
                      [frag.serialize()])
    s._clear_fragment_caches()
    rep = s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    assert rep["dropped_dead_concept"] == 1 and rep["dropped_dead"] == 0
    assert _rows(s)[(s.partition_id, "mentions")] == {a}


def test_repair_orphan_partition_row_and_raw_alias(s, tmp_path):
    c = s.add_concept("k")
    a = s.upsert_entity(kind="doc", name="a.md")
    s.flush_fragments()
    con = s._connect()
    # a bit for live entity `a`, under a pid with no partitions row and a raw alias name
    con._duck.execute("INSERT INTO bitmap_fragments VALUES (?, ?, ?)",
                      [4242, "related_to", BitMap64([s._pack(c, a)]).serialize()])
    rep = s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    rows = _rows(s)
    assert (4242, "related_to") not in rows
    assert rows.get((s.partition_id, "related-to")) == {a}, rows
    assert rep["moved"] == 1


def test_repair_rolls_back_on_failure(s, tmp_path, monkeypatch):
    with s.with_partition("other"):
        c = s.add_concept("k")
        e = s.upsert_entity(kind="doc", name="o.md")
        s.link("mentions", c, e)
        s.flush_fragments()
    con = s._connect()
    con._duck.execute("INSERT INTO bitmap_fragments VALUES (?, 'mentions', ?)",
                      [s.partition_id, BitMap64([s._pack(c, e)]).serialize()])
    before = _rows(s)
    real = con._duck.execute
    n = {"i": 0}
    class Boom(Exception): pass
    def ex(sql, *a, **k):
        if sql.startswith("INSERT INTO bitmap_fragments"):
            n["i"] += 1
            if n["i"] == 1:
                raise Boom()
        return real(sql, *a, **k)
    import types
    duck = con._duck
    class W:
        def __getattr__(self, k): return getattr(duck, k)
        def execute(self, sql, *a, **k): return ex(sql, *a, **k)
    con._duck = W()
    with pytest.raises(Boom):
        s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    con._duck = duck
    assert _rows(s) == before


def test_sqlite_repair_leaves_an_unknown_partition_dir_and_reports_it(tmp_path, monkeypatch):
    """Audit #s-4: the SQLite repair deleted every *.rb64, including directories it never read."""
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    st = Store(tmp_path / ".refmatrix", backend="sqlite"); st.init()
    try:
        c = st.add_concept("k")
        a = st.upsert_entity(kind="doc", name="a.md")
        st.flush_fragments()
        d = st.fragments_dir / "gone-partition"
        d.mkdir(parents=True, exist_ok=True)
        (d / "mentions.rb64").write_bytes(BitMap64([st._pack(c, a)]).serialize())
        rep = st.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
        assert (d / "mentions.rb64").exists()
        assert str(d) in rep["unread_dirs"]
    finally:
        st.close()


def test_periodic_flush_guard_sees_other_binding_dirty(s):
    """Audit #b-1: the daemon tick gated on the home binding's dirty set only."""
    with s.with_partition("memory-x"):
        c = s.add_concept("k")
        e = s.upsert_entity(kind="memory", name="m1")
        s.link("mentions", c, e)
    assert s.has_dirty_fragments()
    assert s.dirty_fragment_count() == 1


def test_repair_leaves_no_stale_cache_to_recontaminate(s, tmp_path):
    """Audit #s-3 m8: after an applied repair, the next link + flush must not write back the
    contaminated bitmap still held in the cache."""
    home = s.partition_name
    c = s.add_concept("k")
    a = s.upsert_entity(kind="doc", name="a.md")
    s.link("mentions", c, a)
    s.flush_fragments()
    with s.with_partition("other"):
        oid = s.partition_id
        c2 = s.add_concept("k")
        b = s.upsert_entity(kind="doc", name="b.md")
        s.link("mentions", c2, b)
        s.flush_fragments()
    # contaminate the persisted home row AND load it into the cache
    con = s._connect()
    hid = s.partition_id
    con._duck.execute("UPDATE bitmap_fragments SET blob=? WHERE partition_id=? AND linkage='mentions'",
                      [BitMap64([s._pack(c, a), s._pack(c2, b)]).serialize(), hid])
    s._clear_fragment_caches()
    s._load_fragment("mentions")                       # cache now holds the foreign bit
    s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    x = s.upsert_entity(kind="doc", name="x.md")
    s.link("mentions", c, x)
    s.flush_fragments()
    assert _rows(s)[(hid, "mentions")] == {a, x}
    assert _rows(s)[(oid, "mentions")] == {b}


def test_dry_run_does_not_flush_dirty_cache(s, tmp_path):
    """Audit #m-1: a dry run must write nothing, including the dirty cache."""
    c = s.add_concept("k")
    a = s.upsert_entity(kind="doc", name="a.md")
    s.link("mentions", c, a)                          # dirty, not flushed
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert _rows(s).get((s.partition_id, "mentions")) is None
    assert rep["added_from_links"] == 0 and rep["kept"] == 1   # overlay saw the cached bit
