"""bug-178 remedy r2: RED for three defects, killers for three surviving mutations (2026-11-09).

Audit: workflow/bullshit/2026-11-09-0159-bug178-bulk-write-r1-d13c4d7.md (`bsd-bug178-r1-d13c4d7`).
Spec:  workflow/plans/task-bug178-bulk-write-helper.md `#remedy-r2`.

RED (fail at the r1 tree on an assertion):
  * `_clear_gmd_content_hashes` skipped unparseable / non-dict meta with an uncounted `continue`
    (finding #b1, a memory path): `clear_tracked_stamps` must report `gmd_hashes_skipped`.
  * `pagerank.store_scores` swallowed a `commit()` failure with `except Exception: pass` (#b1).
    The failure here is REAL, not a patched commit: SQLite's `defer_foreign_keys` moves the FK
    check of `pagerank.entity_id -> entities.id` to COMMIT, so a score for an id with no entity
    makes `commit()` itself raise `IntegrityError`.
  * `bulk_write` pinned an Arrow `int64` column and let `pa.array` truncate `1.5` to `1` silently;
    `True` died with an `ArrowTypeError` that names no column (#m1). It must reject both, naming
    the column, and still accept ints (and integral floats).

Killers (behaviour that exists; each test must FAIL under the mutation the r1 audit saw survive):
  * m4 — the dup-key `updated_at` touch in `bulk_upsert_entity` (`if False and touch_rows`).
  * m2 — `bulk_write`'s `finally: duck.unregister(name)` (`finally: pass`).
  * m5 — the `DuckDBConnection.executemany` fence (`DUCK_EXECUTEMANY_MAX_ROWS = 10**12`).
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import tempfile
import time as _real_time
from contextlib import contextmanager
from pathlib import Path

import pytest

# ---- throwaway stores (short root: macOS sun_path) ---------------------------------------


@contextmanager
def _store(kind: str):
    from refmatrix.store import Store
    base = Path(tempfile.mkdtemp(prefix="b178r2", dir="/tmp"))
    s = Store(base / ".refmatrix", backend=kind)
    s.init()
    try:
        yield s
    finally:
        try:
            s.close()
        finally:
            shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(autouse=True)
def _quiet_log(monkeypatch):
    # facts.log is not the write under test.
    monkeypatch.setenv("RMX_LOG", "0")


def _registered_rmx(duck) -> list[str]:
    """Every `_rmx*` relation registered on THIS DuckDB connection. An Arrow table passed to
    `register()` shows up in `duckdb_views()` as a temporary, non-internal view of that name,
    visible only to the connection that registered it (not to its cursors)."""
    return sorted(r[0] for r in duck.execute(
        "SELECT view_name FROM duckdb_views() "
        "WHERE NOT internal AND starts_with(view_name, '_rmx')").fetchall())


# =========================================================================================
# 1. m4 killer — dup-key upsert `updated_at`, DuckDB vs SQLite's row-by-row sequence
# =========================================================================================

class _PinnedClock:
    """`refmatrix.store.time` stand-in: `time()` returns the pinned value, everything else is
    the real `time` module. Scoped to the store module (not a global `time.time` patch)."""

    def __init__(self, now: float) -> None:
        self.now = now

    def time(self) -> float:
        return self.now

    def __getattr__(self, name):
        return getattr(_real_time, name)


# name: (stored rows or None, batch, expected updated_at of key 'a')
# Lifted from the r1 auditor's probe1.py. Stored at t=100, batch at t=200. The sequence bumps
# `updated_at` whenever ANY step changes a field, so a batch that ends on the stored value
# still bumps (flip-flop, meta flip); one that only repeats the stored value does not.
_UPSERT_SCENARIOS = {
    "flipflop_back_to_stored": ([("doc", "a", "A", None, None)],
                                [("doc", "a", "B", None, None), ("doc", "a", "A", None, None)],
                                200.0),
    "agree_equal_stored": ([("doc", "a", "A", None, None)],
                           [("doc", "a", "A", None, None), ("doc", "a", None, None, None)],
                           100.0),
    "agree_new_value": ([("doc", "a", "A", None, None)],
                        [("doc", "a", "B", None, None), ("doc", "a", "B", None, None)],
                        200.0),
    "meta_flip": ([("doc", "a", None, None, {"k": 1})],
                  [("doc", "a", None, None, {"k": 2}), ("doc", "a", None, None, {"k": 1})],
                  200.0),
    "new_key_two_paths": (None,
                          [("doc", "a", "A", "t1", None), ("doc", "a", "B", None, {"x": 1})],
                          200.0),
    "mixed_fields": ([("doc", "a", "A", "T", {"k": 1})],
                     [("doc", "a", None, "T", None), ("doc", "a", None, None, {"k": 1}),
                      ("doc", "b", "P", None, None), ("doc", "a", "A", None, None)],
                     100.0),
    "triple_with_none_stored": ([("doc", "a", None, None, None)],
                                [("doc", "a", None, "X", None), ("doc", "a", None, "X", None),
                                 ("doc", "a", "Q", None, None)],
                                200.0),
}


def _upsert_run(kind: str, stored, batch, monkeypatch):
    from refmatrix import store as store_mod
    clock = _PinnedClock(100.0)
    monkeypatch.setattr(store_mod, "time", clock)
    try:
        with _store(kind) as s:
            if stored:
                s.bulk_upsert_entity(stored)
            clock.now = 200.0
            ids = s.bulk_upsert_entity(batch)
            rows = sorted(tuple(r) for r in s._connect().execute(
                "SELECT kind, name, path, tldr, meta, created_at, updated_at, protected, "
                "canonical_name FROM entities WHERE kind = 'doc'").fetchall())
            by_name = {r[1]: r for r in rows}
            id_of = {n: i for n, i in s._connect().execute(
                "SELECT name, id FROM entities WHERE kind = 'doc'").fetchall()}
            assert ids == [id_of[r[1]] for r in batch], f"{kind}: returned ids do not name rows"
            return rows, by_name
    finally:
        monkeypatch.setattr(store_mod, "time", _real_time)


@pytest.mark.timeout(120)
@pytest.mark.parametrize("scenario", sorted(_UPSERT_SCENARIOS))
def test_m4_dup_key_upsert_updated_at_matches_the_row_by_row_sequence(scenario, monkeypatch):
    stored, batch, want_updated = _UPSERT_SCENARIOS[scenario]
    ref_rows, _ = _upsert_run("sqlite", stored, batch, monkeypatch)
    got_rows, got = _upsert_run("duckdb", stored, batch, monkeypatch)
    # an anchor that is not the code under test: the expected bump, by hand
    assert got["a"][6] == want_updated, (
        f"{scenario}: DuckDB left updated_at={got['a'][6]} for key 'a'; the row-by-row "
        f"sequence leaves {want_updated} (the dup-key touch in bulk_upsert_entity, bug-178)")
    assert got_rows == ref_rows, (
        f"{scenario}: DuckDB set-based upsert differs from SQLite's row-by-row sequence\n"
        f"  sqlite: {ref_rows}\n  duckdb: {got_rows}")


# =========================================================================================
# 2. m2 killer — no `_rmx_*` registration survives a bulk write, success or failure
# =========================================================================================

def _store_site_names():
    from tests.test_bug178_bulk_write import STORE_SITES
    return sorted(STORE_SITES)


@pytest.mark.timeout(300)
@pytest.mark.parametrize("site", _store_site_names())
def test_m2_site_op_leaves_no_registered_bulk_view(site):
    from tests.test_bug178_bulk_write import STORE_SITES
    with _store("duckdb") as s:
        op, _dump, _ref, _n = STORE_SITES[site](s)
        duck = s._connect()._duck
        before = _registered_rmx(duck)
        op()
        assert s._connect()._duck is duck, "store swapped its connection mid-test"
        after = _registered_rmx(duck)
    assert after == before == [], (
        f"{site}: Arrow batch(es) still registered on the writer connection after the op: "
        f"{after} (bulk_write must ALWAYS unregister — bug-178 R1)")


@pytest.mark.timeout(120)
@pytest.mark.parametrize("op", ["bulk_link", "bulk_mark_tracked", "bulk_upsert_entity"])
def test_m2_arrow_branch_ops_leave_no_registered_bulk_view(op):
    with _store("duckdb") as s:
        concept = s.bulk_upsert_entity([("concept", "r2hub", None, None, None)])[0]
        ids = s.bulk_upsert_entity([("doc", f"r2_{i}", None, None, None) for i in range(50)])
        duck = s._connect()._duck
        if op == "bulk_link":
            s.bulk_link([("mentions", concept, e, None) for e in ids])
        elif op == "bulk_mark_tracked":
            s.bulk_mark_tracked([(f"/x/{i}", float(i)) for i in range(50)])
        else:
            s.bulk_upsert_entity([("doc", f"r2new_{i}", None, None, None) for i in range(50)])
        left = _registered_rmx(duck)
    assert left == [], f"{op}: still registered after the op: {left}"


@pytest.mark.timeout(60)
@pytest.mark.parametrize("wrapped", [False, True], ids=["raw-duckdb", "DuckDBConnection"])
def test_m2_failing_statement_in_outer_txn_unregisters_and_surfaces_the_error(wrapped):
    import duckdb
    from refmatrix import backend
    duck = duckdb.connect()
    con = backend.DuckDBConnection(duck) if wrapped else duck
    try:
        duck.execute("CREATE TABLE pk (a BIGINT PRIMARY KEY)")
        duck.execute("BEGIN")
        with pytest.raises(duckdb.ConstraintException):
            backend.bulk_write(con, "INSERT INTO pk SELECT a FROM {view}", ["a"],
                               [(1,), (1,)], types={"a": "int64"})
        duck.execute("ROLLBACK")              # an aborted txn refuses every query until then
        left = _registered_rmx(duck)
        assert left == [], (
            f"the failed statement's Arrow batch is still registered: {left} "
            f"(bulk_write's finally must unregister — bug-178 R1)")
        # and a successful write in the same connection leaves nothing behind either
        assert backend.bulk_write(con, "INSERT INTO pk SELECT a FROM {view}", ["a"],
                                  [(5,), (6,)], types={"a": "int64"}) == 2
        assert _registered_rmx(duck) == []
        assert duck.execute("SELECT count(*) FROM pk").fetchone()[0] == 2
    finally:
        duck.close()


# =========================================================================================
# 3. m5 killer — the runtime fence on DuckDBConnection.executemany (R3)
# =========================================================================================

def _wrapped_table():
    import duckdb
    from refmatrix import backend
    duck = duckdb.connect()
    duck.execute("CREATE TABLE em (a BIGINT)")
    return duck, backend.DuckDBConnection(duck)


@pytest.mark.timeout(60)
def test_m5_executemany_above_the_fence_raises_naming_bulk_write():
    from refmatrix import backend
    duck, con = _wrapped_table()
    try:
        before = backend.duck_executemany_calls()
        with pytest.raises(backend.DuckDBExecutemanyError, match="bulk_write"):
            con.executemany("INSERT INTO em VALUES (?)", [(i,) for i in range(33)])
        assert duck.execute("SELECT count(*) FROM em").fetchone()[0] == 0, (
            "the fenced call wrote rows before raising")
        assert backend.duck_executemany_calls() == before, "a refused call was counted"
    finally:
        duck.close()


@pytest.mark.timeout(60)
@pytest.mark.parametrize("n", [1, 32])
def test_m5_small_executemany_runs_counts_and_warns(n, caplog):
    from refmatrix import backend
    duck, con = _wrapped_table()
    try:
        before = backend.duck_executemany_calls()
        with caplog.at_level(logging.WARNING, logger="refmatrix.backend"):
            con.executemany("INSERT INTO em VALUES (?)", [(i,) for i in range(n)])
        assert duck.execute("SELECT count(*) FROM em").fetchone()[0] == n
        assert backend.duck_executemany_calls() == before + 1
        warns = [r for r in caplog.records
                 if r.name == "refmatrix.backend" and r.levelno == logging.WARNING
                 and "executemany" in r.getMessage()]
        assert len(warns) == 1, f"expected one counted warning, got {caplog.records}"
        assert f"{n} row" in warns[0].getMessage()
    finally:
        duck.close()


# =========================================================================================
# 4. RED — clear_tracked_stamps counts the meta rows it could not strip
# =========================================================================================

@pytest.mark.timeout(60)
@pytest.mark.parametrize("kind", ["duckdb", "sqlite"])
def test_red_clear_tracked_stamps_counts_skipped_gmd_meta(kind):
    with _store(kind) as s:
        s.bulk_upsert_entity([
            ("memory", "m_ok", None, None, {"gmd_content_hash": "h1", "gmd_pass2_done": True}),
            ("doc", "d_ok", None, None, {"gmd_content_hash": "h2", "keep": 1}),
            ("memory", "m_bad", None, None, None),
            ("memory", "m_list", None, None, None),
            ("memory", "m_plain", None, None, {"other": 1}),     # no stamp: not a skip
        ])
        con = s._connect()
        con.execute("UPDATE entities SET meta = '{gmd_content_hash' WHERE name = 'm_bad'")
        con.execute("UPDATE entities SET meta = '[\"gmd_content_hash\"]' WHERE name = 'm_list'")
        con.commit()
        r = s.clear_tracked_stamps()
        metas = dict(con.execute(
            "SELECT name, meta FROM entities WHERE kind IN ('doc','memory')").fetchall())
    assert r["gmd_hashes_cleared"] == 2, r
    assert "gmd_hashes_skipped" in r, (
        f"clear_tracked_stamps result {r} has no gmd_hashes_skipped: a memory row whose stamped "
        f"meta does not parse keeps its gmd_content_hash and is silently skipped on every "
        f"reingest (bug-178 r1 #b1, CLAUDE.md#no-silent-failures)")
    assert r["gmd_hashes_skipped"] == 2, r
    assert json.loads(metas["m_ok"]) == {} and json.loads(metas["d_ok"]) == {"keep": 1}
    assert metas["m_bad"] == "{gmd_content_hash"                 # left as is, but COUNTED
    assert metas["m_list"] == '["gmd_content_hash"]'


# =========================================================================================
# 5. RED — pagerank.store_scores lets a commit failure propagate
# =========================================================================================

def _pagerank_rows(con) -> list[tuple]:
    return [tuple(r) for r in con.execute(
        "SELECT entity_id, score, computed_at FROM pagerank ORDER BY entity_id").fetchall()]


@pytest.mark.timeout(60)
def test_red_store_scores_propagates_a_commit_failure():
    from refmatrix import pagerank
    with _store("sqlite") as s:
        eid = s.bulk_upsert_entity([("doc", "pr_real", None, None, None)])[0]
        con = s._connect()
        assert isinstance(con, sqlite3.Connection)
        con.commit()
        # A prior SUCCESSFUL replace (bsd r2 #s1, kills m9): the failed replace below must leave
        # these rows exactly as they were, and must not leave the connection in a transaction.
        assert pagerank.store_scores(s, {eid: 0.5}, now=0.25) == 1
        prior = _pagerank_rows(con)
        assert prior == [(eid, 0.5, 0.25)], prior
        # Real failure, nothing patched: the FK check moves to COMMIT, so the INSERT succeeds
        # and commit() itself raises for the score whose entity does not exist.
        con.execute("PRAGMA defer_foreign_keys = ON")
        ghost = eid + 10_000
        try:
            try:
                pagerank.store_scores(s, {eid: 1.0, ghost: 2.0}, now=1.0)
            except sqlite3.IntegrityError as e:
                raised = e
                # Observed BEFORE the `finally` cleanup below, which would otherwise mask a
                # missing rollback in store_scores (m9 survived r2 exactly that way).
                assert not con.in_transaction, (
                    "store_scores re-raised its commit failure but left the connection inside "
                    "the failed transaction: every later commit on the daemon's long-lived "
                    "connection trips over it (bug-178 bsd r2 #s1 — the rollback is missing)")
                assert _pagerank_rows(con) == prior, (
                    "the failed replace was not rolled back: the prior pagerank rows changed")
            else:
                raised = None
                # prove the failure mode is real at HEAD too: the swallowed commit is the one
                # that raises when asked again (so a RED here is the swallow, not the fixture)
                with pytest.raises(sqlite3.IntegrityError, match="(?i)foreign key"):
                    con.commit()
        finally:
            if con.in_transaction:
                con.rollback()
    assert raised is not None, (
        "pagerank.store_scores returned success while its commit() failed with a FOREIGN KEY "
        "IntegrityError — `except Exception: pass` swallowed it (bug-178 r1 #b1)")
    assert "foreign key" in str(raised).lower(), raised


# =========================================================================================
# 6. RED — bulk_write rejects non-integers bound for a pinned integer column
# =========================================================================================

_W = "INSERT INTO t SELECT hits, label FROM {view}"
_TYPES = {"hits": "int64", "label": "string"}


@contextmanager
def _int_table(wrapped: bool):
    import duckdb
    from refmatrix import backend
    duck = duckdb.connect()
    duck.execute("CREATE TABLE t (hits BIGINT, label VARCHAR)")
    try:
        yield duck, (backend.DuckDBConnection(duck) if wrapped else duck)
    finally:
        duck.close()


@pytest.mark.timeout(60)
@pytest.mark.parametrize("wrapped", [False, True], ids=["raw-duckdb", "DuckDBConnection"])
@pytest.mark.parametrize("bad", [1.5, True, -0.25], ids=["fractional", "bool", "neg-fraction"])
def test_red_bulk_write_rejects_non_int_for_pinned_int_column(bad, wrapped):
    from refmatrix import backend
    with _int_table(wrapped) as (duck, con):
        raised = None
        try:
            backend.bulk_write(con, _W, ["hits", "label"], [(3, "ok"), (bad, "x")],
                               types=_TYPES)
        except Exception as e:  # noqa: BLE001 — the type is the implementer's; the text is pinned
            raised = e
        rows = duck.execute("SELECT * FROM t").fetchall()
    assert raised is not None, (
        f"bulk_write accepted {bad!r} for the int64-pinned column 'hits' and stored "
        f"{rows} — Arrow truncates silently (bug-178 r1 #m1)")
    assert "hits" in str(raised), (
        f"bulk_write rejected {bad!r} but the error does not name the column: "
        f"{type(raised).__name__}: {raised}")
    assert rows == [], f"a rejected batch left rows behind: {rows}"


@pytest.mark.timeout(60)
@pytest.mark.parametrize("wrapped", [False, True], ids=["raw-duckdb", "DuckDBConnection"])
def test_bulk_write_accepts_ints_and_integral_values_for_pinned_int_column(wrapped):
    import numpy as np
    from refmatrix import backend
    with _int_table(wrapped) as (duck, con):
        n = backend.bulk_write(con, _W, ["hits", "label"],
                               [(2, "int"), (None, "null"), (np.int64(7), "np"),
                                (2 ** 62, "big"), (4.0, "integral-float")],
                               types=_TYPES)
        rows = sorted(duck.execute("SELECT label, hits FROM t").fetchall())
    assert n == 5
    assert rows == sorted([("int", 2), ("null", None), ("np", 7), ("big", 2 ** 62),
                           ("integral-float", 4)])


# =========================================================================================
# 7. m11 killer — `rmx reingest --force` PRINTS the GMD hashes it could not clear
# =========================================================================================

@pytest.mark.timeout(300)
def test_reingest_force_prints_the_gmd_hashes_it_did_not_clear(tmp_path, monkeypatch):
    """bsd r2 #m1 (kills m11). The count is pinned at `Store.clear_tracked_stamps` (test 4);
    the printed line is the half of CLAUDE.md#no-silent-failures ("counted AND printed") that
    nothing observed. Drives the real CLI, as tests/test_reingest.py does: an isolated scratch
    project, cwd-resolved root, sessions/embed/semantic off, no daemon (in-process store)."""
    from click.testing import CliRunner

    from refmatrix.cli import main
    from refmatrix.store import Store

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "code.py").write_text("x = 1\n")
    monkeypatch.chdir(proj)
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    runner = CliRunner()
    assert runner.invoke(main, ["init"], catch_exceptions=False).exit_code == 0

    # One stamped memory row whose meta does not parse as a JSON object: step 0/5 cannot strip
    # its hash, so it stays skipped by every reingest — and must say so.
    s = Store(proj / ".refmatrix")
    s.init()                                 # binds the default (project) partition
    s.bulk_upsert_entity([("memory", "m_bad_meta", None, None, None)])
    con = s._connect()
    con.execute("UPDATE entities SET meta = '{gmd_content_hash' WHERE name = 'm_bad_meta'")
    con.commit()
    s.close()

    r = runner.invoke(
        main,
        ["reingest", "--force", "--no-sessions", "--no-embed", "--no-semantic",
         "--memory-dir", str(tmp_path / "no-memory-dir")],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    assert "0/5 clear stamps" in r.output, r.output
    out = " ".join(r.output.split())         # rich wraps long lines at the runner's width
    assert "1 GMD content hash(es) NOT cleared" in out, (
        f"rmx reingest --force did not print the stamped row it could not clear "
        f"(bug-178 bsd r2 #m1):\n{r.output}")
