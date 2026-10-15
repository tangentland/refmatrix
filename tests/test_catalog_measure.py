"""Task 18.1: the catalog measurement script (eval/catalog_maint/measure_catalogs.py).

The fleet run decides whether an offline reclaim (18.3) is built at all, so the script must be
right about the one number that matters (`r`, from a real rewrite), must never touch a live root
(bug-110: any close of a DuckDB file's descriptor drops the daemon's lock), and must never share
an in-process DuckDB opener (bug-112). Every test builds real DuckDB catalogs under tmp roots and
injects them; no test reads a live root.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import duckdb
import pytest

from refmatrix.store import Store

_REPO = Path(__file__).resolve().parents[1]
MiB = 1024 * 1024


def _load():
    spec = importlib.util.spec_from_file_location(
        "measure_catalogs", _REPO / "eval" / "catalog_maint" / "measure_catalogs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mc = _load()


def _root(base: Path, name: str, *, rows: int = 0, keep_ids: int | None = None,
          snapshot: bool = True) -> Path:
    """A `.refmatrix` root whose `catalog.read.duckdb` is a real Store catalog plus synthetic
    `entities` rows; `keep_ids` deletes every id above it and checkpoints (the F2 shape)."""
    root = base / name / ".refmatrix"
    s = Store(root, backend="duckdb")
    s.init()
    s.close()
    cat = root / "catalog.duckdb"
    if rows:
        con = duckdb.connect(str(cat))
        con.execute("INSERT INTO entities (kind, name, tldr, created_at, updated_at) "
                    "SELECT 'doc', 'n' || i, repeat(md5(i::VARCHAR), 4), 0, 0 "
                    f"FROM range({rows}) t(i)")
        con.execute("CHECKPOINT")
        if keep_ids is not None:
            con.execute(f"DELETE FROM entities WHERE id > {keep_ids}")
            con.execute("CHECKPOINT")
        con.close()
    os.replace(cat, root / "catalog.A.duckdb")
    (root / "active").write_text("A\n")
    if snapshot:
        subprocess.run(["/bin/cp", "-p", str(root / "catalog.A.duckdb"),
                        str(root / "catalog.read.duckdb")], check=True)
    return root


def _fingerprint(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        st = p.stat()
        out[str(p)] = (st.st_size, st.st_mtime_ns, st.st_ino)
    return out


@pytest.fixture
def scratch(tmp_path):
    return tmp_path / "scratch"


def test_ac1_reclaim_found_and_a_full_store_is_a0(tmp_path, scratch):
    """AC-1. 200,000 rows, 90 % deleted and checkpointed: the rewrite gives most of it back.
    `f` is reported but NOT asserted >= 0.80: on the real schema the index blocks keep it near
    0.6 while the rewrite reclaims > 0.8 (the proxy under-reads; that is Table B's reason)."""
    big = _root(tmp_path, "big", rows=200_000, keep_ids=20_000)
    full = _root(tmp_path, "full", rows=20_000)
    rows, v, code = mc.run([big, full], scratch, tmp_path / "out" / "rep",
                           min_reclaim_bytes=1 * MiB)
    assert code == 0
    b, f = rows
    assert b["gate"] == "pass" and b["r"] >= 0.80 and b["reclaimable"] > 0
    assert b["band_a"] == "A2"
    assert 0 < b["f"] <= b["r"]
    assert f["r"] < 0.20 and f["band_a"] == "A0"
    assert not scratch.exists()          # copies deleted after the report (R2)


def test_ac2_r_is_the_rewrite_not_the_proxy():
    # The spec's 100/40 MiB gives 60 MiB reclaimable, under Table A's own 64 MiB edge (A0);
    # 200/80 keeps r = 0.60 and clears the edge (spec amendment, 2026-10-15).
    d = mc.derive(file_bytes=200 * MiB, rewrite_bytes=80 * MiB, free_blocks=10,
                  total_blocks=100)
    assert d["r"] == pytest.approx(0.60) and d["f"] == pytest.approx(0.10)
    assert d["band_a"] == "A2" and d["band_b"] == "B-disagree"


def test_ac3_live_root_untouched_and_copied_by_child_cp(tmp_path, scratch, monkeypatch):
    root = _root(tmp_path, "live", rows=5_000)
    before = _fingerprint(root)
    argvs: list[list[str]] = []
    real = subprocess.run

    def spy(argv, *a, **kw):
        argvs.append([str(x) for x in argv])
        return real(argv, *a, **kw)

    import socket
    connects = []
    monkeypatch.setattr(socket.socket, "connect",
                        lambda self, *a: connects.append(a) or (_ for _ in ()).throw(
                            AssertionError("socket connect")))
    monkeypatch.setattr(mc.subprocess, "run", spy)
    _, _, code = mc.run([root], scratch, tmp_path / "out" / "rep", min_reclaim_bytes=1)
    assert code == 0
    assert connects == []
    assert _fingerprint(root) == before
    cps = [a for a in argvs if a[0] == "/bin/cp"]
    assert cps == [["/bin/cp", "-p", str(root / "catalog.read.duckdb"),
                    str(scratch / "live" / "snap.duckdb")]]
    assert not any("catalog.A.duckdb" in x for a in argvs for x in a)


def test_ac4_gate_can_fail(tmp_path, scratch):
    root = _root(tmp_path, "g", rows=1_000)

    def drop_row(target: Path):
        con = duckdb.connect(str(target))
        con.execute("DELETE FROM entities WHERE id = (SELECT min(id) FROM entities)")
        con.execute("CHECKPOINT")
        con.close()

    rows, v, code = mc.run([root], scratch, tmp_path / "out" / "rep", before_gate=drop_row)
    (row,) = rows
    assert row["gate"] == "fail" and code == 1
    assert any(d.startswith("table main.entities: copy=1000 rewrite=999")
               for d in row["gate_diffs"])
    assert "band_a" not in row and "band_c" not in row
    assert v["verdict"] == "INCOMPLETE"


def test_ac5_every_duckdb_statement_runs_in_a_child(tmp_path, scratch, monkeypatch):
    root = _root(tmp_path, "c", rows=1_000)
    calls = []
    monkeypatch.setattr(duckdb, "connect", lambda *a, **k: calls.append(a))
    rows, _, code = mc.run([root], scratch, tmp_path / "out" / "rep")
    assert code == 0 and calls == []
    pids = rows[0]["pids"]
    assert set(pids) == {"measure", "rewrite", "gate"}
    assert os.getpid() not in pids.values()


def test_ac6_a_missing_snapshot_is_a_counted_row(tmp_path, scratch):
    a = _root(tmp_path, "a", rows=500)
    b = _root(tmp_path, "b", rows=500, snapshot=False)
    c = _root(tmp_path, "c", rows=500)
    rows, v, code = mc.run([a, b, c], scratch, tmp_path / "out" / "rep")
    assert [r["root"] for r in rows] == [str(a), str(b), str(c)]
    assert rows[1]["error"] == "no snapshot"
    assert "error" not in rows[0] and "error" not in rows[2]
    assert code == 1 and v["verdict"] == "INCOMPLETE"
    lines = (tmp_path / "out" / "rep.jsonl").read_text().splitlines()
    assert len(lines) == 3 and json.loads(lines[1])["error"] == "no snapshot"


def test_ac7_bands_are_the_pre_registered_ones():
    assert mc.BANDS == {
        "min_reclaim_bytes": 64 * MiB, "a1_r": 0.20, "a2_r": 0.50, "b_agree": 0.10,
        "c0_s": 30.0, "c1_s": 120.0, "noisy_ratio": 1.5, "in_daemon_max_s": 5.0}
    assert mc.REHEARSALS == 3


def test_ac8_a_noisy_rehearsal_reruns_once_then_reports_noisy(tmp_path, scratch):
    root = _root(tmp_path, "n", rows=1_000)
    # run 0 of each batch of three takes 4x the others
    hook = lambda ix, s: (s + 1.0) * (4.0 if ix % 3 == 0 else 1.0)
    rows, _, code = mc.run([root], scratch, tmp_path / "out" / "rep", time_hook=hook)
    (row,) = rows
    assert code == 0
    assert row["rehearsal_reruns"] == 1 and len(row["rewrite_s_all"]) == 6
    assert row["band_c"] == "noisy"


def test_band_c_edges():
    assert mc.band_c(30.0) == "C0" and mc.band_c(30.01) == "C1"
    assert mc.band_c(120.0) == "C1" and mc.band_c(120.5) == "C2"


def test_verdict_rules():
    base = {"rewrite_s_max": 1.0, "band_b": "B-agree", "band_c": "C0"}
    assert mc.verdict([{**base, "root": "x", "band_a": "A0"}])["verdict"].startswith(
        "18.3 CLOSED")
    v = mc.verdict([{**base, "root": "x", "band_a": "A2"},
                    {**base, "root": "y", "band_a": "A1", "band_c": "C2",
                     "band_b": "B-disagree", "rewrite_s_max": 200.0}])
    assert v["reclaim_candidates"] == ["x"] and v["helix"] == ["y"]
    assert v["band_mode"] == "growth" and v["in_daemon_feasible"] is False
