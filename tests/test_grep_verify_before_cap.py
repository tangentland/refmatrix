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

    res = CliRunner().invoke(cli_mod.main, ["grep", "--no-fallback",
                                            "--limit", "2", "--", "error"])

    assert res.exit_code == 0, res.output
    assert res.stdout.count("b.py:") == 2, res.stdout
    assert "capped" in res.stderr and "--limit 2" in res.stderr, res.stderr
