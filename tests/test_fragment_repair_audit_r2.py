"""bug-105 hotfix round-2 audit regressions (ch-bsd `bsd-bug105-hotfix-r2-4fb803b`, 2026-10-14).

Round 2 found that 4fb803b's merge ran its store-wide fragment work (pre-flush, cache clear,
repair) outside the writer lock (#b2-1), that the merge's final cache clear discarded unlinks
made between chunks so the union repair resurrected them (#b2-1), that the repair called a
concept dead when it had no `concepts` row although typed edges use doc/memory/code entities as
the concept (#b2-2), and that merge threw the repair's report away (#s2-1). Each test is one of
the auditor's probes, adopted.
"""
import threading

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
    """Full packed bits per (partition_id, linkage) — concept AND entity, unlike the r1 file."""
    con = s._connect()
    out = {}
    for pid, L, blob in con._duck.execute(
            "SELECT partition_id, linkage, blob FROM bitmap_fragments").fetchall():
        out[(pid, L)] = {int(b) for b in BitMap64.deserialize(bytes(blob))}
    return out


class _RecLock:
    """Re-entrant stand-in for the daemon's _store_lock that records whether it is held."""
    def __init__(self):
        self._l = threading.RLock(); self.depth = 0

    def __enter__(self):
        self._l.acquire(); self.depth += 1; return self

    def __exit__(self, *a):
        self.depth -= 1; self._l.release()


def test_merge_store_wide_flush_and_repair_run_under_the_writer_lock(s, monkeypatch):
    lock = _RecLock()
    seen = []
    for name in ("flush_fragments", "_clear_fragment_caches", "repair_fragments"):
        orig = getattr(Store, name)

        def wrap(self, *a, _o=orig, _n=name, **k):
            seen.append((_n, lock.depth > 0))
            return _o(self, *a, **k)
        monkeypatch.setattr(Store, name, wrap)
    with s.with_partition("src"):
        c = s.add_concept("k"); e = s.upsert_entity(kind="doc", name="o.md")
        s.link("mentions", c, e)
    with s.with_partition("dst"):
        pass
    s.merge_partition("src", "dst", lock=lock)
    assert seen, "merge ran no fragment step"
    unlocked = [n for n, held in seen if not held]
    assert not unlocked, f"called outside the writer lock: {unlocked}"


def test_merge_interleaved_unlink_is_not_resurrected(s):
    home = s.partition_name
    c = s.add_concept("k"); a = s.upsert_entity(kind="doc", name="a.md")
    s.link("mentions", c, a); s.flush_fragments()
    hid = s.partition_id
    with s.with_partition("src"):
        e = s.upsert_entity(kind="doc", name="o.md"); s.link("mentions", c, e)
    done = []

    def progress(phase, d, t):
        if not done:
            done.append(1); s.unlink("mentions", c, a)   # dirty, not flushed
    s.merge_partition("src", home, lock=_RecLock(), progress=progress)
    assert done, "progress never fired"
    assert s._pack(c, a) not in _rows(s).get((hid, "mentions"), set())


def test_repair_does_not_call_a_live_wikilink_target_a_dead_concept(s, tmp_path):
    m1 = s.upsert_entity(kind="memory", name="m1"); m2 = s.upsert_entity(kind="memory", name="m2")
    s.link("mentions", m2, m1); s.flush_fragments()
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert rep["dropped_dead_concept"] == 0, rep
    assert rep["manifest"] is None, rep


def test_repair_keeps_a_fragment_only_bit_whose_concept_is_a_live_doc(s, tmp_path):
    d1 = s.upsert_entity(kind="doc", name="a.md"); d2 = s.upsert_entity(kind="doc", name="b.md")
    s.link("mentions", d2, d1); s.flush_fragments()
    s._connect()._duck.execute("DELETE FROM entity_links")
    s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    assert s._pack(d2, d1) in _rows(s).get((s.partition_id, "mentions"), set())


def test_merge_returns_the_repair_report_with_its_manifest(s):
    c = s.add_concept("k"); a = s.upsert_entity(kind="doc", name="a.md")
    s.link("mentions", c, a); s.flush_fragments()
    hid = s.partition_id
    bad = BitMap64([s._pack(999999, a), s._pack(c, a)])
    s._connect()._duck.execute(
        "UPDATE bitmap_fragments SET blob=? WHERE partition_id=? AND linkage='mentions'",
        [bad.serialize(), hid])
    s._clear_fragment_caches()
    with s.with_partition("src"):
        pass
    res = s.merge_partition("src", s.partition_name)
    rep = res.get("fragments_repair")
    assert rep is not None, res
    assert rep["dropped_dead_concept"] == 1 and rep["manifest"], rep
