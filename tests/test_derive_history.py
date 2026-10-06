"""Task 15.2: a derive records what it PRODUCED, and the record is kept.

`derive_stamps` answers "which code built what is in the store now" and upserts,
deliberately. That makes impact unanswerable: there is nothing to compare a
derive against. bug-039's own impact figures (31 -> 63 bundles, 206 -> 466 nodes)
came from a hand-rolled harness that no longer runs, so today a re-derive
reports no effect at all.

`derive_history` is append-only, capped, and carries the partition's structural
shape after each pass, so two derives diff directly.

WHAT THESE TESTS REFUSE TO FAKE. The no-op case (a derive that changes nothing
must be visibly a no-op) runs the REAL pass twice over an unchanged tree.
Calling `stamp_derive` twice by hand produces equal counts trivially and proves
nothing about the pass — it would be a test of the test.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from refmatrix.store import Store


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    yield s
    s.close()


def _gmd(dirpath: Path, name: str, body: str) -> Path:
    p = dirpath / f"{name}.md"
    p.write_text(
        f'---\ngmd: "0.1"\nid: {name}\ntitle: "{name}"\ntags: [t]\n---\n\n' + body)
    return p


def _real_gmd_pass(store: Store, paths: list[Path]) -> None:
    """The actual production pass, which stamps `gmd` at its end."""
    from refmatrix.ingest_gmd import ingest_gmd_paths
    ingest_gmd_paths(store, paths)


def _independent_counts(store: Store) -> dict:
    """Count the same tables by hand, so the recorded numbers are checked
    against something other than the code that recorded them."""
    con = store._connect()
    pid = store._partition_id
    q = lambda sql: con.execute(sql, (pid,)).fetchone()[0]
    return {
        "entities": q("SELECT count(*) FROM entities WHERE partition_id=?"),
        "concepts": q("SELECT count(*) FROM entities WHERE partition_id=? "
                      "AND kind='concept'"),
        "links": q("SELECT count(*) FROM entity_links el JOIN entities e "
                   "ON e.id=el.entity_id WHERE e.partition_id=?"),
        "evidence": q("SELECT count(*) FROM linkage_evidence ev JOIN entities e "
                      "ON e.id=ev.entity_id WHERE e.partition_id=?"),
        "tracked_files": q("SELECT count(*) FROM tracked_files WHERE partition_id=?"),
    }


# ---- the record exists and is right --------------------------------------

def test_a_derive_writes_one_history_row_with_correct_counts(store, tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    _real_gmd_pass(store, [_gmd(d, "alpha", "# Alpha {#root}\n\nBody. {#b}\n")])

    rows = store.derive_history()

    assert len(rows) == 1, rows
    row = rows[0]
    assert row["pass_name"] == "gmd"
    counts = row["counts"]
    independent = _independent_counts(store)
    for k, v in independent.items():
        assert counts[k] == v, f"{k}: recorded {counts.get(k)} != actual {v}"


def test_the_counts_carry_entities_by_kind(store, tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    _real_gmd_pass(store, [_gmd(d, "alpha", "# Alpha {#root}\n")])

    counts = store.derive_history()[0]["counts"]

    assert isinstance(counts.get("by_kind"), dict) and counts["by_kind"], counts
    assert sum(counts["by_kind"].values()) == counts["entities"]


# ---- the no-op case: the one that must not be faked ----------------------

def test_two_derives_of_an_unchanged_tree_have_identical_counts(store, tmp_path):
    """A derive that changes nothing must be VISIBLY a no-op, which is the
    whole point of recording counts. Driven by running the real pass twice."""
    d = tmp_path / "docs"
    d.mkdir()
    paths = [_gmd(d, "alpha", "# Alpha {#root}\n\nBody. {#b}\n")]
    _real_gmd_pass(store, paths)
    _real_gmd_pass(store, paths)

    rows = store.derive_history(pass_name="gmd")

    assert len(rows) == 2, [r["derived_at"] for r in rows]
    assert rows[0]["counts"] == rows[1]["counts"], (
        f"a no-op derive moved the counts:\n{rows[1]['counts']}\n"
        f"{rows[0]['counts']}")


def test_a_derive_that_adds_content_moves_the_counts(store, tmp_path):
    """And the control: if nothing ever moved, the no-op test above would pass
    against a function that records constants."""
    d = tmp_path / "docs"
    d.mkdir()
    first = _gmd(d, "alpha", "# Alpha {#root}\n")
    _real_gmd_pass(store, [first])
    before = store.derive_history(pass_name="gmd")[0]["counts"]

    second = _gmd(d, "beta", "# Beta {#root}\n\nrel: depends-on -> [[alpha]]\n")
    _real_gmd_pass(store, [first, second])

    after = store.derive_history(pass_name="gmd")[0]["counts"]
    assert after["entities"] > before["entities"], (before, after)


# ---- retention -----------------------------------------------------------

def test_history_is_capped_and_the_prune_is_counted(store, tmp_path):
    """An append-only table with no retention is bug-061 (`global:queues` at
    3,196 rows) wearing a different name."""
    cap = store.DERIVE_HISTORY_MAX
    for _ in range(cap + 3):
        store.stamp_derive("gmd")

    rows = store.derive_history(pass_name="gmd", limit=cap + 10)

    assert len(rows) == cap, len(rows)
    assert any(r.get("pruned") for r in rows), (
        "nothing recorded that rows were pruned; a silent drop is the thing "
        "this assertion exists to prevent")


def test_retention_is_per_pass(store, tmp_path):
    """One busy pass must not evict another pass's history."""
    cap = store.DERIVE_HISTORY_MAX
    store.stamp_derive("ingest")
    for _ in range(cap + 2):
        store.stamp_derive("gmd")

    # `limit` is the READER's cap (default 20) and is not the retention cap —
    # an earlier version of this test conflated them and read 20 of the 50
    # kept rows as a retention failure.
    assert len(store.derive_history(pass_name="ingest", limit=cap + 10)) == 1
    assert len(store.derive_history(pass_name="gmd", limit=cap + 10)) == cap


# ---- the current-state contract is untouched -----------------------------

def test_derive_stamps_still_answers_exactly_what_it_did(store, tmp_path):
    """Four readers depend on the NOW semantics. This task adds a table; it
    must not quietly change the old one."""
    store.stamp_derive("gmd", version="9.9.9")
    store.stamp_derive("gmd", version="9.9.10")

    row = store._connect().execute(
        "SELECT pass_name, version FROM derive_stamps WHERE partition_id=?",
        (store._partition_id,)).fetchall()

    assert len(row) == 1, "derive_stamps must still hold ONE row per pass"
    assert row[0][1] == "9.9.10", "it must still be the LATEST"
    assert len(store.derive_history(pass_name="gmd")) == 2, (
        "...while the history keeps both")


# ---- unknown is not zero -------------------------------------------------

def test_a_store_with_a_stamp_but_no_history_reports_no_history(store, tmp_path):
    """A pre-15.2 store has stamps and no history rows. That must read as NO
    HISTORY, never as a derive that produced zero of everything — a zero
    baseline would make the next derive look like it created the whole graph."""
    store.stamp_derive("gmd")
    store._connect().execute("DELETE FROM derive_history")

    rows = store.derive_history(pass_name="gmd")

    assert rows == [], rows
    assert store.derive_status()["passes"][0]["pass_name"] == "gmd"


def test_the_table_is_created_on_an_older_store(tmp_path, monkeypatch):
    """A store built before this column set exists must gain the table on
    open, not raise."""
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    root = tmp_path / ".refmatrix"
    s = Store(root, backend="duckdb")
    s.init()
    s._connect().execute("DROP TABLE derive_history")
    s.close()

    s2 = Store(root, backend="duckdb")
    s2.init()
    s2.stamp_derive("gmd")
    assert len(s2.derive_history(pass_name="gmd")) == 1
    s2.close()


# ---- the counts are stored as data, not prose ---------------------------

def test_counts_round_trip_as_json(store, tmp_path):
    store.stamp_derive("gmd")

    raw = store._connect().execute(
        "SELECT counts FROM derive_history WHERE partition_id=?",
        (store._partition_id,)).fetchone()[0]

    assert isinstance(json.loads(raw), dict)


def test_counts_that_cannot_be_computed_are_recorded_as_an_error(store, monkeypatch):
    """A partial or empty counts object reads as REAL NUMBERS — `{}` would diff
    as "everything vanished" and zeros would diff as "the graph was emptied".
    So a failure records what failed, and the derive still stands: losing the
    derive would be worse than losing its record
    (CLAUDE.md#no-silent-failures)."""
    def _boom(self):
        raise RuntimeError("catalog went away mid-pass")
    monkeypatch.setattr(type(store), "derive_counts", _boom)

    store.stamp_derive("gmd")

    rows = store.derive_history(pass_name="gmd")
    assert len(rows) == 1, "the derive must still be recorded"
    assert "error" in rows[0]["counts"], rows[0]["counts"]
    assert "catalog went away" in rows[0]["counts"]["error"]
    assert "entities" not in rows[0]["counts"], (
        "a failed count must not also carry numbers that look real")
