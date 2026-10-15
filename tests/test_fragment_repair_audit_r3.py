"""bug-105 hotfix round-3 audit regressions (ch-bsd `bsd-bug105-hotfix-r3-27b3653`, 2026-10-14).

Round 3 found the merge's home-binding rebind still outside the writer lock (#b3-1, the 7th
bug-098-class case), merge collisions whose fragment bits were never remapped from the SRC id to
the DST id so the repair dropped them as dead (#s3-1), unpinned report prints (#s3-2) and a silent
rmxd.log (#m3-2). The auditor's probes P1-P3 and P5-P8 are adopted; P4 (SQLite's best-effort
fragment-dir skip, #m3-1) is a known MEH on a non-production backend and stays open.
"""
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest
from pyroaring import BitMap64

from refmatrix import daemon as dm
from refmatrix.daemon import _FairLock
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
        out[(pid, L)] = {int(b) for b in BitMap64.deserialize(bytes(blob))}
    return out


def _seed(s, n=6):
    with s.with_partition("src"):
        for i in range(n):
            c = s.add_concept(f"shared{i}")
            s.link("mentions", c, s.upsert_entity(kind="doc", name=f"s{i}.md"))
        s.add_concept("src-only")
    with s.with_partition("dst"):
        for i in range(n):
            s.add_concept(f"shared{i}")
    s.flush_fragments()


# ---- P1: the real, NON-re-entrant _FairLock: no nested acquire, fragment steps held ----------
def test_p1_merge_with_real_fairlock_completes_and_holds_lock_for_fragment_steps(s, monkeypatch):
    _seed(s)
    lock = _FairLock()
    seen = []
    for name in ("flush_fragments", "_clear_fragment_caches", "repair_fragments"):
        orig = getattr(Store, name)

        def wrap(self, *a, _o=orig, _n=name, **k):
            seen.append((_n, lock.locked()))
            return _o(self, *a, **k)
        monkeypatch.setattr(Store, name, wrap)
    out = {}
    t = threading.Thread(target=lambda: out.update(
        r=s.merge_partition("src", "dst", lock=lock, chunk=2)), daemon=True)
    t.start(); t.join(30)
    assert not t.is_alive(), "merge deadlocked on the non-re-entrant _FairLock"
    assert out["r"]["fragments_repair"] is not None
    assert seen and all(held for _n, held in seen), seen
    assert not lock.locked()


# ---- P2: concurrent writer interleaving with a chunked merge, real _FairLock -----------------
def test_p2_concurrent_ops_during_merge_leave_every_link_in_its_entitys_partition(s):
    _seed(s, n=40)
    lock = _FairLock()
    home = s.partition_name
    stop = threading.Event(); errs = []
    with lock:
        hc = s.add_concept("home-k")

    def writer():
        i = 0
        try:
            while not stop.is_set():
                with lock:
                    with s.with_partition("dst"):
                        e = s.upsert_entity(kind="doc", name=f"w{i}.md")
                        s.link("mentions", hc, e)
                with lock:
                    e2 = s.upsert_entity(kind="doc", name=f"h{i}.md")
                    s.link("mentions", hc, e2)
                i += 1
                time.sleep(0.001)
        except Exception as ex:  # surfaced below
            errs.append(repr(ex))
    t = threading.Thread(target=writer, daemon=True); t.start()
    res = s.merge_partition("src", "dst", lock=lock, chunk=1)
    stop.set(); t.join(10)
    assert not errs, errs
    with lock:
        s.flush_fragments()
    con = s._connect()
    ent_part = dict(con.execute("SELECT id, partition_id FROM entities").fetchall())
    rows = _rows(s)
    missing = misplaced = 0
    for eid, cid in con.execute(
            "SELECT entity_id, concept_id FROM entity_links el JOIN linkage_types lt "
            "ON el.linkage_id = lt.id WHERE lt.name='mentions'").fetchall():
        if s._pack(cid, eid) not in rows.get((ent_part[eid], "mentions"), set()):
            missing += 1
    for (pid, L), bits in rows.items():
        for b in bits:
            if ent_part.get(b & 0xFFFFFFFF) != pid:
                misplaced += 1
    assert (missing, misplaced) == (0, 0), (missing, misplaced, res["fragments_repair"])
    assert s.partition_name == home


# ---- P3: the binding rebind at the merge's end (prescribed under the lock in r2) -------------
def test_p3_home_binding_rebind_happens_under_the_writer_lock(s):
    _seed(s)
    with s.with_partition("src"):
        sid = s.partition_id
    s._partition_name, s._partition_id = "src", sid   # daemon bound to SRC
    lock = _FairLock()
    log = []

    class Spy(Store):
        def __setattr__(self, k, v):
            if k == "_partition_name" and v == "dst":
                log.append(lock.locked())
            object.__setattr__(self, k, v)
    s.__class__ = Spy
    try:
        s.merge_partition("src", "dst", lock=lock, chunk=2)
    finally:
        s.__class__ = Store
    assert log and all(log), f"rebinding to dst with the lock held: {log}"


# ---- P5: daemon-up path end to end (spawned subprocess on a short tmp root, isolated HOME) ---
@pytest.fixture
def live(monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="r3b-", dir="/tmp"))
    home = base / "h"; home.mkdir()
    for k, v in {"HOME": str(home), "RMX_HOME": str(home / ".refmatrix"),
                 "RMX_SHARED_MODELS": "0", "RMX_MODEL_SOCK": str(base / "m.sock")}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    root = base / "p" / ".refmatrix"; root.parent.mkdir()
    st = Store(root); st.init()
    with st.with_partition("src"):
        c = st.add_concept("k"); e = st.upsert_entity(kind="doc", name="o.md")
        st.link("mentions", c, e)
        st.add_concept("k2")
    with st.with_partition("dst"):
        st.add_concept("k")
    with st.with_partition("src2"):
        c3 = st.add_concept("k3"); st.link("mentions", c3, st.upsert_entity(kind="doc", name="q.md"))
    st.flush_fragments(); st.close()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    try:
        yield root
    finally:
        dm.stop_daemon(root); shutil.rmtree(base, ignore_errors=True)


# P5 and P6 drove a LIVE daemon merge, which bug-105 r4 fenced (d9ae); the fence and the
# offline merge's report are pinned in test_fragment_repair_audit_r4.py.


# ---- P7: merge collisions — fragment bits are never remapped src_eid -> dst_eid ---------------
def test_p7_merge_collision_bits_are_remapped_not_reported_dropped(s, tmp_path):
    with s.with_partition("src"):
        sk = s.add_concept("k"); e = s.upsert_entity(kind="doc", name="o.md")
        s.link("mentions", sk, e)
        f = s.upsert_entity(kind="doc", name="frag-only.md")
        s.link("mentions", sk, f)
    with s.with_partition("dst"):
        dk = s.add_concept("k")
    s.flush_fragments()
    con = s._connect()
    con._duck.execute("DELETE FROM entity_links WHERE entity_id=?", [f])  # fragment-only bit
    res = s.merge_partition("src", "dst")
    rep = res["fragments_repair"]
    rows = _rows(s)
    with s.with_partition("dst"):
        did = s.partition_id
    got = rows.get((did, "mentions"), set())
    print("REPORT", rep, "dst bits", sorted(got), "dk", dk, "sk", sk)
    assert rep["dropped_dead_concept"] == 0, rep   # a remapped concept is not a dead one
    assert s._pack(dk, f) in got                    # the fragment-only bit follows the remap


def test_p8_cli_repair_index_fragments_dry_run_then_apply_daemon_up(live, monkeypatch):
    from click.testing import CliRunner
    from refmatrix import cli as cli_mod
    monkeypatch.chdir(live.parent)
    monkeypatch.setenv("REFMATRIX_ROOT", str(live))
    for argv in (["repair-index", "--fragments", "--dry-run"], ["repair-index", "--fragments"],
                 ["repair-index", "--fragments", "--dry-run"]):
        r = CliRunner().invoke(cli_mod.main, argv)
        print("$ rmx " + " ".join(argv) + "\n" + r.output)
        assert r.exit_code == 0, r.output
        assert "dropped_dead_concept=" in r.output and "links_skipped=" in r.output, r.output
    log = (live / "rmxd.log").read_text()
    print("RMXD:\n" + "\n".join(l for l in log.splitlines() if "repair_fragments" in l))
