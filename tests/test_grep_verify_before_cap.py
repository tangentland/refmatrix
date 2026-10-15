"""ch-bsd r3 #b-1: verification must run BEFORE the cap, and a cap that bites
must say so.

bug-074 verified each index row against its real line AFTER the SQL `LIMIT`
had already cut the result to `limit` raw rows. Most raw rows on a real store
are `def`-line rows that verification drops, so the cap was spent on rows that
never reach the user. Measured on a copy of the live replica with the default
`--limit 100`:

    pattern     verified rows that exist    rmx grep PAT    stderr    exit
    error       96                          13              (empty)   0
    partition   128                         51              (empty)   0

13 of 96 with exit 0 and nothing on stderr — bug-058's shape (a short read
that looks successful). The fixture below reproduces it in miniature: the
`def`-line rows sort FIRST (`a.py` < `b.py`), so a cap applied to raw rows is
consumed entirely by rows verification then throws away.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root, backend="duckdb")
    s.init()
    yield s
    s.close()


def _seed(s: Store, proj) -> None:
    """8 rows on `def` lines of a.py (sorted first, never verify) and 3 rows
    on real `error` lines of b.py."""
    a = proj / "a.py"
    a.write_text("".join(f"def f{i}():\n    pass\n" for i in range(8)))
    b = proj / "b.py"
    b.write_text("x = 1\nan error here\nanother error\nlast error line\n")
    cid = s.add_concept("keyword/error")
    ea = s.upsert_entity("code", "a.py", path=str(a))
    eb = s.upsert_entity("code", "b.py", path=str(b))
    s.link("mentions", cid, ea)
    s.link("mentions", cid, eb)
    for i in range(8):
        s.add_evidence("mentions", cid, ea, file=str(a), line=2 * i + 1)
    for line in (2, 3, 4):
        s.add_evidence("mentions", cid, eb, file=str(b), line=line)


def test_the_cap_counts_verified_rows_not_raw_ones(store):
    _seed(store, store.root.parent)
    assert len(store.grep_evidence("error", limit=None)) == 3, "precondition"

    rows = store.grep_evidence("error", limit=3)

    assert len(rows) == 3, (
        "the cap was spent on def-line rows verification then dropped — a "
        f"silent short read: {rows}")
    assert {r["line"] for r in rows} == {2, 3, 4}


def test_a_cap_that_bites_is_reported_in_the_stats(store):
    _seed(store, store.root.parent)
    stats: dict = {}

    rows = store.grep_evidence("error", limit=2, verify_stats=stats)

    assert len(rows) == 2
    assert stats.get("capped") is True, stats


def test_a_cap_that_does_not_bite_is_not_reported(store):
    _seed(store, store.root.parent)
    stats: dict = {}

    rows = store.grep_evidence("error", limit=5, verify_stats=stats)

    assert len(rows) == 3
    assert stats.get("capped") is False, stats


@pytest.mark.parametrize("layout", ["replica", "direct"])
def test_the_cli_says_when_the_index_answer_was_capped(store, monkeypatch, layout):
    """The user-facing half: a capped index answer prints a stderr note, the
    way the stdin path and the floor already do. Without it, 13 of 96 reads
    exactly like 13 of 13."""
    proj = store.root.parent
    _seed(store, proj)
    store.close()
    if layout == "direct":
        legacy = store.root / "catalog.duckdb"
        if legacy.exists():
            shutil.move(str(legacy), str(store.root / "catalog.A.duckdb"))
        (store.root / "active").write_text("A\n")
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(proj)
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)  # 23.0 R2: cwd walk

    res = CliRunner().invoke(cli_mod.main, ["grep", "--no-fallback",
                                            "--limit", "2", "--", "error"])

    assert res.exit_code == 0, res.output
    assert res.stdout.count("b.py:") == 2, res.stdout
    assert "capped" in res.stderr and "--limit 2" in res.stderr, res.stderr


# ---- ch-bsd r4 #b-1: no OFFSET paging over a non-total order ---------------
#
# The r3 fix paged `LIMIT ? OFFSET ?` over `ORDER BY e.path, ev.line`, which
# ties whenever several concepts share one line. DuckDB does not promise a tie
# order between two queries, so at a page boundary one row came back twice
# and its sibling was lost (2 of 5 runs of `rmx grep error` on the replica).
# Paging was also up to 11x slower than one read. The fixture puts the old page
# boundary (row 256) INSIDE a group of verified ties.

def _seed_ties(s: Store, proj) -> None:
    f = proj / "t.py"
    f.write_text("def x():\nqq here\n")
    e = s.upsert_entity("code", "t.py", path=str(f))
    for i in range(250):                  # line 1: 250 rows that never verify
        c = s.add_concept(f"keyword/qq_a{i:03d}")
        s.link("mentions", c, e)
        s.add_evidence("mentions", c, e, file=str(f), line=1)
    for i in range(20):                   # line 2: 20 verified rows, tied
        c = s.add_concept(f"keyword/qq_b{i:03d}")
        s.link("mentions", c, e)
        s.add_evidence("mentions", c, e, file=str(f), line=2)


def test_a_capped_read_never_duplicates_or_loses_a_tied_row(store):
    _seed_ties(store, store.root.parent)
    full = store.grep_evidence("qq", limit=None)
    assert len(full) == 20, "precondition"
    key = lambda r: (r["path"], r["line"], r["linkage"], r["concept"])

    for _ in range(5):
        stats: dict = {}
        rows = store.grep_evidence("qq", limit=10, verify_stats=stats)
        keys = [key(r) for r in rows]
        assert len(keys) == len(set(keys)) == 10, f"duplicated rows: {keys}"
        assert keys == [key(r) for r in full[:10]], "not a prefix of the full read"
        assert stats["capped"] is True


# ---- ch-bsd r4 #b-5: a relative learned path verifies from ANY cwd ---------
#
# 515 of 747 raw `error` rows on the replica carry RELATIVE paths, learned
# before 321ff97 made new ones absolute. Verification read them against the
# process cwd, so `rmx grep error` returned 96 rows from the project root and 5
# from `src/`. They resolve against the project root (the store root's
# parent), which is what they were relative to when learned.

def test_a_relative_row_verifies_regardless_of_the_cwd(store, tmp_path, monkeypatch):
    proj = store.root.parent
    (proj / "src").mkdir()
    (proj / "src" / "a.py").write_text("x = 1\nan error here\n")
    c = store.add_concept("query/error")
    e = store.upsert_entity("code", "src/a.py", path="src/a.py")   # relative
    store.link("mentions", c, e)
    store.add_evidence("mentions", c, e, file="src/a.py", line=2)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    for cwd in (proj, proj / "src", elsewhere):
        monkeypatch.chdir(cwd)
        monkeypatch.delenv("REFMATRIX_ROOT", raising=False)  # 23.0 R2: cwd walk
        rows = store.grep_evidence("error")
        assert [r["line"] for r in rows] == [2], f"cwd={cwd}: {rows}"
        # ...and PRINTED with a path that exists from this cwd (r5 #b-1).
        assert Path(rows[0]["path"]).is_absolute(), rows
        assert Path(rows[0]["path"]).exists(), rows


# ---- ch-bsd r5 #b-1: printed with the path it was READ from -----------------
#
# bug-084 resolved a relative row against the project root for READING and
# returned the row with its unresolved spelling, so from a subdirectory 7 of 10
# printed paths did not exist, and one file split into two `-c` rows (its
# relative and its absolute spelling). The row now carries the resolved path,
# and rows are de-duplicated after resolution.

def test_a_relative_row_is_printed_resolved_and_merged(store, tmp_path, monkeypatch):
    proj = store.root.parent
    (proj / "src").mkdir()
    a = proj / "src" / "a.py"
    a.write_text("x = 1\nan error here\n")
    c = store.add_concept("query/error")
    rel = store.upsert_entity("code", "src/a.py", path="src/a.py")
    absent = store.upsert_entity("code", "a-abs", path=str(a))
    for e, f in ((rel, "src/a.py"), (absent, str(a))):
        store.link("mentions", c, e)
        store.add_evidence("mentions", c, e, file=f, line=2)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)  # 23.0 R2: cwd walk

    stats: dict = {}
    rows = store.grep_evidence("error", verify_stats=stats)

    assert {r["path"] for r in rows} == {str(a)}, rows
    assert all(Path(r["path"]).exists() for r in rows)
    # ONE printed row, and the collapse counted (ch-bsd r6 #b-1): a set-size
    # assert equalled 1 with the dedup deleted, while `-c` counted the one
    # matching line twice.
    assert len(rows) == 1, rows
    assert stats["merged"] == 1, stats


# ---- ch-bsd r6 #m-2: ordered and capped on the RESOLVED path -----------------
#
# The SQL total order sorts the STORED spelling, and `/` sorts before `s`, so a
# capped read took every absolute-spelled row before any relative one, and one
# file spelled both ways printed as two runs out of line order.

def test_the_cap_and_the_order_follow_the_resolved_path(store, tmp_path, monkeypatch):
    proj = store.root.parent
    (proj / "src").mkdir()
    a = proj / "src" / "a.py"
    b = proj / "src" / "b.py"
    a.write_text("an error\nx\nan error\n")
    b.write_text("an error\n")
    c = store.add_concept("query/error")
    rel_a = store.upsert_entity("code", "src/a.py", path="src/a.py")
    abs_a = store.upsert_entity("code", "a-abs", path=str(a))
    abs_b = store.upsert_entity("code", "b-abs", path=str(b))
    for e, f, ln in ((rel_a, "src/a.py", 1), (abs_a, str(a), 3), (abs_b, str(b), 1)):
        store.link("mentions", c, e)
        store.add_evidence("mentions", c, e, file=f, line=ln)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)  # 23.0 R2: cwd walk

    rows = store.grep_evidence("error", limit=None)
    assert [(r["path"], r["line"]) for r in rows] == [
        (str(a), 1), (str(a), 3), (str(b), 1)], rows

    capped = store.grep_evidence("error", limit=1)
    assert [(r["path"], r["line"]) for r in capped] == [(str(a), 1)], capped
