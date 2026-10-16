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
import statistics
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
          snapshot: bool = True, probe: bool = False) -> Path:
    """A `.refmatrix` root whose `catalog.read.duckdb` is a real Store catalog plus synthetic
    `entities` rows; `keep_ids` deletes every id above it and checkpoints (the F2 shape).
    `probe` adds an index-free table the AC-4 type / NOT NULL / CHECK variants can ALTER (DuckDB
    refuses those ALTERs on a table other entries depend on, e.g. `entities`; the type change
    goes on `c` because the CHECK depends on `a`)."""
    root = base / name / ".refmatrix"
    s = Store(root, backend="duckdb")
    s.init()
    s.close()
    cat = root / "catalog.duckdb"
    if probe:
        con = duckdb.connect(str(cat))
        con.execute("CREATE TABLE fp_probe (a INTEGER NOT NULL CHECK (a > 0), b VARCHAR, "
                    "c INTEGER)")
        con.execute("INSERT INTO fp_probe VALUES (2, 'x', 1), (3, 'y', 2)")
        con.close()
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


def _db_size(path: Path) -> tuple[int, int, int]:
    """The test's OWN reading of its fixture (never a live root): (total, used, free) blocks."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.execute("SELECT total_blocks, used_blocks, free_blocks "
                           "FROM pragma_database_size()").fetchone()
    finally:
        con.close()


def test_ac1_reclaim_found_and_a_full_store_is_a0(tmp_path, scratch):
    """AC-1. 200,000 rows, 95 % deleted and checkpointed: the rewrite gives most of it back.
    `f` is NOT asserted >= 0.80: on the real schema the index blocks keep it near 0.6 while the
    rewrite reclaims > 0.8 (the proxy under-reads; that is Table B's reason). Instead the row's
    block counts and `f` are pinned to this test's own `pragma_database_size` reading
    (ch-bsd r1 #s-4: `free := used` passed every test). 95 % rather than the spec's 90 %:
    at 90 % `r` sat on the 0.80 edge and failed 1 run in 8 (r1 #s-5); at 95 % it measured
    0.874-0.887. The no-delete store is 200,000 rows, not 20,000: a small file's size moves by
    whole 256 KiB blocks between builds, and at 20,000 / 50,000 rows `r` reached 0.04 / 0.22
    (measured 2026-10-15); at 200,000 it stayed <= 0.014."""
    big = _root(tmp_path, "big", rows=200_000, keep_ids=10_000)
    full = _root(tmp_path, "full", rows=200_000)
    total, used, free = _db_size(big / "catalog.read.duckdb")
    rows, v, code = mc.run([big, full], scratch, tmp_path / "out" / "rep",
                           min_reclaim_bytes=1 * MiB)
    assert code == 0
    b, f = rows
    assert (b["total_blocks"], b["used_blocks"], b["free_blocks"]) == (total, used, free)
    assert b["f"] == round(free / total, 4)
    assert b["gate"] == "pass" and b["r"] >= 0.80 and b["reclaimable"] > 0
    assert b["band_a"] == "A2"
    assert 0 < b["f"] <= b["r"]
    assert f["r"] < 0.20 and f["band_a"] == "A0"
    assert b["rewrite_bytes"] == int(statistics.median(b["rewrite_bytes_all"]))
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
    assert len(cps) == 1 and cps[0][:3] == ["/bin/cp", "-p", str(root / "catalog.read.duckdb")]
    dst = Path(cps[0][3])
    assert dst.name == "snap.duckdb" and dst.parent.parent == scratch
    assert dst.parent.name.startswith("live-")
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
    assert any(d.startswith("rows main.entities: copy=1000 rewrite=999")
               for d in row["gate_diffs"])
    assert "band_a" not in row and "band_c" not in row
    assert v["verdict"] == "INCOMPLETE"


# One variant per leg of `catalog_fingerprint` (ch-bsd r1 #s-3). Each asserts its OWN leg's diff,
# so removing that leg from the fingerprint fails exactly this variant.
_AC4_VARIANTS = {
    "content": (["UPDATE entities SET tldr = tldr || 'x' "
                 "WHERE id = (SELECT min(id) FROM entities)"], "content main.entities:"),
    "column-type": (["ALTER TABLE fp_probe ALTER COLUMN c TYPE BIGINT"], "columns main.fp_probe:"),
    "column-default": (["ALTER TABLE entities ALTER COLUMN meta SET DEFAULT 'x'"],
                       "columns main.entities:"),
    "constraint": (["ALTER TABLE fp_probe ALTER COLUMN a DROP NOT NULL"],
                   "constraints main.fp_probe:"),
    # Same rows, same columns, same constraint TYPES; only the CHECK's text moves (r2 #m-1:
    # the NOT NULL variant removes a whole row, so `constraint_type` alone still caught it).
    "check-text": (["CREATE TABLE fp_probe2 (a INTEGER NOT NULL CHECK (a > 1), b VARCHAR, "
                    "c INTEGER)",
                    "INSERT INTO fp_probe2 SELECT * FROM fp_probe",
                    "DROP TABLE fp_probe",
                    "ALTER TABLE fp_probe2 RENAME TO fp_probe"],
                   "constraints main.fp_probe:"),
    "index-sql": (["DROP INDEX idx_entities_noise",
                   "CREATE INDEX idx_entities_noise ON entities(protected)"],
                  "indexes main.idx_entities_noise:"),
    "sequence": (["SELECT nextval('seq_entities_id')"], "sequences main.seq_entities_id:"),
    "view": (["CREATE VIEW fp_view AS SELECT 1 AS one"], "views main.fp_view:"),
    "macro": (["CREATE MACRO fp_macro(a) AS a + 1"], "macros main.fp_macro:"),
    "type": (["CREATE TYPE fp_type AS ENUM ('a', 'b')"], "types main.fp_type:"),
}


@pytest.mark.parametrize("variant", sorted(_AC4_VARIANTS))
def test_ac4_every_gate_leg_can_fail(tmp_path, scratch, variant):
    stmts, prefix = _AC4_VARIANTS[variant]
    root = _root(tmp_path, "g", rows=200, probe=True)

    def mutate(target: Path):
        con = duckdb.connect(str(target))
        for sql in stmts:
            con.execute(sql).fetchall()     # a SELECT's nextval runs only when fetched
        con.execute("CHECKPOINT")
        con.close()

    rows, v, code = mc.run([root], scratch, tmp_path / "out" / "rep", before_gate=mutate)
    (row,) = rows
    assert row["gate"] == "fail" and code == 1, row.get("gate_diffs")
    assert any(d.startswith(prefix) for d in row["gate_diffs"]), row["gate_diffs"]
    if variant == "content":     # the content leg, not the count, caught it
        assert not any(d.startswith("rows ") for d in row["gate_diffs"])
    if variant == "check-text":  # ONLY the constraint text differs
        assert all(d.startswith("constraints main.fp_probe:") for d in row["gate_diffs"])
    assert "band_a" not in row and v["verdict"] == "INCOMPLETE"


def test_fingerprint_content_is_order_free_and_duplicates_do_not_cancel(tmp_path):
    def fp(*stmts):
        con = duckdb.connect(str(tmp_path / f"db{len(list(tmp_path.iterdir()))}.duckdb"))
        try:
            con.execute("CREATE TABLE t (v VARCHAR)")
            for sql in stmts:
                con.execute(sql)
            return mc.catalog_fingerprint(con)
        finally:
            con.close()

    asc = fp("INSERT INTO t VALUES ('a'), ('b'), ('c')")
    desc = fp("INSERT INTO t VALUES ('c'), ('b'), ('a')")
    assert mc.gate(asc, desc) == []
    # a pair of equal rows XORs to zero; the SUM keeps them apart
    aa = fp("INSERT INTO t VALUES ('a'), ('a')")
    bb = fp("INSERT INTO t VALUES ('b'), ('b')")
    assert [d.split(":")[0] for d in mc.gate(aa, bb)] == ["content main.t"]


def test_gate_reports_a_missing_leg():
    assert mc.gate({"rows": {}, "views": {}}, {"rows": {}}) == ["views: missing from rewrite"]


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


def test_rewrite_s_max_covers_the_noisy_first_batch(tmp_path, scratch):
    """ch-bsd r1 #m-2: the in-daemon ceiling read only the final batch's max."""
    root = _root(tmp_path, "n", rows=1_000)
    hook = lambda ix, s: 100.0 if ix == 0 else 1.0 + s / 1000
    rows, _, code = mc.run([root], scratch, tmp_path / "out" / "rep", time_hook=hook)
    (row,) = rows
    assert code == 0 and row["rehearsal_reruns"] == 1
    assert row["rewrite_s_max"] == 100.0 == max(row["rewrite_s_all"])
    assert row["band_c"] == "C0"         # the final batch is quiet


def test_rewrite_bytes_is_the_median_of_the_runs(tmp_path, scratch):
    """ch-bsd r1 #s-5: r1 kept the LAST run's size; sizes vary ~1.3 % run to run."""
    root = _root(tmp_path, "m", rows=1_000)
    rows, _, code = mc.run([root], scratch, tmp_path / "out" / "rep",
                           bytes_hook=lambda ix, b: b + (0, 100, 300)[ix])
    (row,) = rows
    base = row["rewrite_bytes_all"][0]
    assert code == 0 and row["rewrite_bytes_all"] == [base, base + 100, base + 300]
    assert row["rewrite_bytes"] == base + 100


def test_scratch_contents_survive_and_any_exception_is_a_row(tmp_path, scratch):
    """ch-bsd r1 #m-3: r1 removed the whole scratch dir, and an exception outside its list
    (a KeyError here) aborted the run with no report and left the copies behind."""
    scratch.mkdir()
    (scratch / "keep.txt").write_text("mine")
    (scratch / "other").mkdir()
    (scratch / "other" / "f").write_text("mine too")
    boom = _root(tmp_path, "boom", rows=500)
    ok = _root(tmp_path, "ok", rows=500)

    def explode(target: Path):
        if target.parent.name.startswith("boom-"):
            raise KeyError("spy")

    out = tmp_path / "out" / "rep"
    rows, v, code = mc.run([boom, ok], scratch, out, before_gate=explode)
    assert rows[0]["step"] == "unexpected" and rows[0]["error"] == "KeyError: 'spy'"
    assert "error" not in rows[1] and code == 1 and v["verdict"] == "INCOMPLETE"
    assert len(out.with_suffix(".jsonl").read_text().splitlines()) == 2
    assert out.with_suffix(".md").exists()
    assert sorted(p.name for p in scratch.iterdir()) == ["keep.txt", "other"]
    assert (scratch / "other" / "f").read_text() == "mine too"


def test_an_interrupt_still_writes_a_row_per_root(tmp_path, scratch):
    a = _root(tmp_path, "a", rows=300)
    b = _root(tmp_path, "b", rows=300)

    def stop(target: Path):
        raise KeyboardInterrupt

    out = tmp_path / "out" / "rep"
    with pytest.raises(KeyboardInterrupt):
        mc.run([a, b], scratch, out, before_gate=stop)
    lines = [json.loads(x) for x in out.with_suffix(".jsonl").read_text().splitlines()]
    assert [r["step"] for r in lines] == ["interrupted", "interrupted"]
    assert not scratch.exists()


def test_rows_record_duckdb_version_and_store_name(tmp_path, scratch, monkeypatch):
    """ch-bsd r1 #m-4: the tests' children ran duckdb 1.5.2 while the fleet ran 1.5.3 and no
    row said so; the global store was named after the user (`parent.name`)."""
    home = tmp_path / "home"
    glob = _root(home.parent, "home", rows=300)          # <tmp>/home/.refmatrix
    proj = _root(tmp_path, "proj", rows=300)
    monkeypatch.setattr(mc.Path, "home", classmethod(lambda cls: home))
    out = tmp_path / "out" / "rep"
    rows, _, code = mc.run([glob, proj], scratch, out)
    assert code == 0
    assert [r["store"] for r in rows] == ["global", "proj"]
    assert all(r["duckdb_version"] == duckdb.__version__ for r in rows)
    md = out.with_suffix(".md").read_text()
    assert f"| global |" in md and f"| {duckdb.__version__} |" in md
    assert mc.store_name(Path("/x/y/.refmatrix"), home=Path("/elsewhere")) == "y"


def test_children_on_different_duckdb_builds_are_an_error_row(tmp_path, scratch, monkeypatch):
    """`hash()` and the file format are build-specific: a gate comparing fingerprints from two
    duckdb builds proves nothing, so the row refuses (ch-bsd r1 #m-4)."""
    root = _root(tmp_path, "v", rows=300)
    real = mc._child

    def other_build(python, *args, step, **kw):
        out = real(python, *args, step=step, **kw)
        return {**out, "duckdb_version": "0.0.0"} if step == "rewrite" else out

    monkeypatch.setattr(mc, "_child", other_build)
    rows, _, code = mc.run([root], scratch, tmp_path / "out" / "rep")
    assert code == 1 and rows[0]["step"] == "version"
    assert "0.0.0" in rows[0]["error"] and not scratch.exists()


def test_fingerprint_sequence_leg_needs_fresh_opens(tmp_path):
    """The documented precondition of `catalog_fingerprint` (ch-bsd 18.1 r2 #s-1): a
    connection that has issued a sequence value (the daemon's writer shape: a fresh open of a
    checkpointed file, then one insert) differs from a fresh read of its own rewrite ONLY on
    the sequences leg; reopened fresh, the same file matches the rewrite exactly."""
    src, rw = tmp_path / "live.duckdb", tmp_path / "rewrite.duckdb"
    con = duckdb.connect(str(src))
    con.execute("CREATE SEQUENCE sq START 1")
    con.execute("CREATE TABLE t (i BIGINT DEFAULT nextval('sq'), v INTEGER)")
    con.execute("INSERT INTO t (v) SELECT range FROM range(5)")
    con.close()

    def fresh(path: Path) -> dict:
        c = duckdb.connect(str(path), read_only=True)
        try:
            return mc.catalog_fingerprint(c)
        finally:
            c.close()

    live = duckdb.connect(str(src))
    try:
        live.execute("INSERT INTO t (v) VALUES (99)")          # the daemon issues an id
        in_session = mc.catalog_fingerprint(live)
        db = live.execute("SELECT current_database()").fetchone()[0]
        live.execute(f"ATTACH '{rw}' AS n")
        live.execute(f'COPY FROM DATABASE "{db}" TO n')
        live.execute("CHECKPOINT n")
        live.execute("DETACH n")
    finally:
        live.close()
    rewrite = fresh(rw)
    diffs = mc.gate(in_session, rewrite)
    assert diffs and all(d.startswith("sequences main.sq:") for d in diffs), diffs
    assert mc.gate(fresh(src), rewrite) == []


def test_report_id_is_the_report_stem_and_render_from_reuses_rows(tmp_path, scratch):
    """ch-bsd 18.1 r2 #m-2: a re-run's report reused the earlier report's GMD id."""
    root = _root(tmp_path, "r", rows=300)
    out = tmp_path / "out" / "plan18-catalog-measure-20991231-r9"
    mc.run([root], scratch, out)
    md = out.with_suffix(".md").read_text()
    assert "\nid: plan18-catalog-measure-20991231-r9\n" in md
    again = tmp_path / "out" / "re-rendered"
    assert mc.main(["--out", str(again), "--render-from", str(out.with_suffix(".jsonl"))]) == 0
    md2 = again.with_suffix(".md").read_text()
    assert "\nid: re-rendered\n" in md2
    assert md2.split("## Per store")[1] == md.split("## Per store")[1]
