"""Task 15.3: `rmx derive log` / `diff` / `status`, and a line that attributes.

Today's line — `derive[refmatrix]: 0.73.0 (running 0.74.1) — stale` — leads with
the VERSION comparison, which moves on every bump (34 in ten days, measured),
names no pass, and does not say whether the deriving code actually changed. So
it reads as noise and gets ignored, which is how bug-039's condition hid in a
status screen where every line already read fine.

These surfaces are READ-ONLY and assert on WORDS as well as numbers, because an
empty table and a genuine no-change result are indistinguishable to a caller
otherwise — the bug-058 shape, where a short read looks successful.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix.store import Store


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    d = tmp_path / "p"
    d.mkdir()
    s = Store(d / ".refmatrix", backend="duckdb")
    s.init()
    s.close()
    monkeypatch.chdir(d)
    return d


def _store(proj: Path) -> Store:
    return Store(proj / ".refmatrix", backend="duckdb")


def _gmd(dirpath: Path, name: str, body: str) -> Path:
    p = dirpath / f"{name}.md"
    p.write_text(
        f'---\ngmd: "0.1"\nid: {name}\ntitle: "{name}"\ntags: [t]\n---\n\n' + body)
    return p


def _derive(proj: Path, docs: list[Path]) -> None:
    """A REAL pass, so the history rows are real history."""
    from refmatrix.ingest_gmd import ingest_gmd_paths
    s = _store(proj)
    ingest_gmd_paths(s, docs)
    s.close()


def _run(args: list[str]):
    return CliRunner().invoke(cli_mod.main, args)


# ---- log ------------------------------------------------------------------

def test_log_prints_one_line_per_derive(proj):
    d = proj / "docs"
    d.mkdir()
    a = _gmd(d, "alpha", "# Alpha {#root}\n")
    _derive(proj, [a])
    _derive(proj, [a, _gmd(d, "beta", "# Beta {#root}\n")])

    res = _run(["derive", "log"])

    assert res.exit_code == 0, res.output
    # the pass is a HEADER, with its derives beneath it — better output than
    # this test first assumed (it asserted "gmd" twice)
    assert "gmd" in res.output, res.output
    assert res.output.count("v0.") >= 2, res.output
    assert "entities" in res.output, res.output
    assert "changed" in res.output, res.output


def test_log_on_a_store_with_no_history_says_so(proj):
    """Not an empty table. A caller cannot tell silence from breakage."""
    res = _run(["derive", "log"])

    assert res.exit_code == 0, res.output
    assert "no derive history" in res.output.lower(), res.output


def test_log_says_a_single_derive_has_nothing_to_compare(proj):
    """One row must not show a delta against zero — that would read as "this
    derive created the entire graph"."""
    d = proj / "docs"
    d.mkdir()
    _derive(proj, [_gmd(d, "alpha", "# Alpha {#root}\n")])

    res = _run(["derive", "log"])

    assert res.exit_code == 0, res.output
    assert "nothing to compare" in res.output.lower(), res.output


def test_log_json_carries_the_same_numbers(proj):
    d = proj / "docs"
    d.mkdir()
    _derive(proj, [_gmd(d, "alpha", "# Alpha {#root}\n")])

    res = _run(["derive", "log", "--json"])

    assert res.exit_code == 0, res.output
    rows = json.loads(res.stdout)
    assert rows and rows[0]["pass_name"] == "gmd"
    assert rows[0]["counts"]["entities"] > 0


# ---- diff -----------------------------------------------------------------

def test_diff_of_two_identical_derives_says_no_change(proj):
    """THE pre-registered acceptance (plan #2): a no-op derive must be visibly
    a no-op, and visibly means it says so."""
    d = proj / "docs"
    d.mkdir()
    docs = [_gmd(d, "alpha", "# Alpha {#root}\n\nBody. {#b}\n")]
    _derive(proj, docs)
    _derive(proj, docs)

    res = _run(["derive", "diff"])

    assert res.exit_code == 0, res.output
    assert "no change" in res.output.lower(), res.output
    # MEASURED, not assumed: the second identical derive leaves graph counts
    # untouched and moves `bitmap_fragments` 0 -> 3, because the first pass had
    # not flushed fragments yet. The plan's "all zeros" was wrong about the
    # system; the verdict is about graph content and the cache is reported
    # beside it rather than hidden.
    assert "materialized cache" in res.output.lower(), res.output


def test_diff_prints_the_keys_that_moved_and_omits_the_rest(proj):
    d = proj / "docs"
    d.mkdir()
    a = _gmd(d, "alpha", "# Alpha {#root}\n")
    _derive(proj, [a])
    _derive(proj, [a, _gmd(d, "beta", "# Beta {#root}\n\nMore. {#m}\n")])

    res = _run(["derive", "diff"])

    assert res.exit_code == 0, res.output
    assert "entities" in res.output, res.output
    assert "+" in res.output, res.output
    # a GRAPH key that did not move must not be listed in the verdict
    assert "memory_content" not in res.output.split("materialized")[0], res.output


def test_diff_with_one_derive_says_there_is_nothing_to_compare(proj):
    d = proj / "docs"
    d.mkdir()
    _derive(proj, [_gmd(d, "alpha", "# Alpha {#root}\n")])

    res = _run(["derive", "diff"])

    assert res.exit_code == 0, res.output
    assert "nothing to compare" in res.output.lower(), res.output


# ---- status ---------------------------------------------------------------

def test_status_names_the_pass_and_the_axis(proj):
    d = proj / "docs"
    d.mkdir()
    _derive(proj, [_gmd(d, "alpha", "# Alpha {#root}\n")])

    res = _run(["derive", "status"])

    assert res.exit_code == 0, res.output
    out = res.output.lower()
    assert "gmd" in out, res.output
    # the modules a pass's hash covers, so a reader can see WHY
    assert "ingest_gmd.py" in res.output, res.output


def test_status_distinguishes_a_version_bump_from_a_code_change(proj):
    """A bump that touches no extractor must not read the same as a real code
    move. 34 bumps in ten days is why the old line reads as noise."""
    s = _store(proj)
    s.stamp_derive("gmd", version="0.0.1")      # old VERSION, current code hash
    s.close()

    res = _run(["derive", "status"])

    assert res.exit_code == 0, res.output
    out = res.output.lower()
    assert "0.0.1" in res.output
    assert "code" in out and ("unchanged" in out or "current" in out), (
        "status must say the deriving CODE did not move, not just that the "
        "version differs:\n" + res.output)


def test_status_reports_a_legacy_scheme_as_unknown(proj):
    """A pre-15.1 stamp holds a union hash and is not comparable. Unknown is
    its own answer and must not render as either fresh or behind."""
    s = _store(proj)
    s.stamp_derive("gmd", code_hash="deadbeef")   # untagged == legacy scheme
    s.close()

    res = _run(["derive", "status"])

    assert res.exit_code == 0, res.output
    assert "unknown" in res.output.lower(), res.output


# ---- it is a read -------------------------------------------------------

def test_the_surface_writes_nothing(proj):
    """Read-only, asserted through the shipped `--json` surface rather than a
    second Store handle: DuckDB refuses two connections to one file with
    different configurations, so an extra handle tests the harness."""
    d = proj / "docs"
    d.mkdir()
    _derive(proj, [_gmd(d, "alpha", "# Alpha {#root}\n")])

    before = json.loads(_run(["derive", "log", "--json", "--limit", "100"]).stdout)
    _run(["derive", "log"])
    _run(["derive", "diff"])
    _run(["derive", "status"])
    after = json.loads(_run(["derive", "log", "--json", "--limit", "100"]).stdout)

    assert len(after) == len(before) == 1, (before, after)
    assert [r["id"] for r in after] == [r["id"] for r in before], (
        "a read surface added or replaced history rows")


def test_the_warning_line_does_not_claim_code_is_unchanged_without_evidence():
    """A status dict with no per-pass detail (pre-15.1 shaped, or from a daemon
    that is) supports only the VERSION axis. Saying "no re-derive needed" there
    would be the reassuring half of a verdict never reached — so the line falls
    back to naming the versions and the command."""
    from refmatrix.cli import render_derive_warning

    legacy = {"stale": True, "oldest_version": "0.49.1",
              "running_version": "0.74.1", "reason": "derived by 0.49.1"}
    out = render_derive_warning(legacy)

    assert "reingest --force" in out, out
    assert "no re-derive needed" not in out, out


def test_the_warning_line_says_version_drift_when_the_code_is_verified_current():
    """And with the evidence present, it must NOT send anyone to re-derive:
    that would cost minutes to rebuild the same graph."""
    from refmatrix.cli import render_derive_warning

    verified = {
        "stale": True, "oldest_version": "0.73.0", "running_version": "0.74.1",
        "reason": "derived by gmd@0.73.0",
        "passes": [{"pass_name": "gmd", "version": "0.73.0",
                    "behind_code": False, "code_unknown": False,
                    "modules": ["ingest_gmd.py"]}],
    }
    out = render_derive_warning(verified)

    assert "version drift only" in out, out
    assert "reingest --force" not in out, out


def test_the_warning_line_names_the_pass_when_code_really_moved():
    from refmatrix.cli import render_derive_warning

    moved = {
        "stale": True, "oldest_version": "0.73.0", "running_version": "0.74.1",
        "behind_code": True, "reason": "gmd derived before the current code",
        "passes": [{"pass_name": "gmd", "version": "0.73.0",
                    "behind_code": True, "code_unknown": False,
                    "modules": ["ingest_gmd.py"]}],
    }
    out = render_derive_warning(moved)

    assert "gmd" in out and "CHANGED" in out, out
    assert "reingest --force" in out, out


# ---- the two defects the first REAL run exposed -------------------------

def test_a_store_without_the_table_reports_no_history(proj):
    """`rmx derive log` crashed against the live store on its first real run:
    the deployed daemon predates `derive_history`, so the catalog legitimately
    lacks the table. A store older than the feature has NO HISTORY — a real
    answer, not a CatalogException.

    Every test above passed while this was broken, which is
    feedback_green_tests_are_not_a_working_command: run the command once
    against real data."""
    s = _store(proj)
    s._connect().execute("DROP TABLE derive_history")
    s.close()

    res = _run(["derive", "log"])

    assert res.exit_code == 0, res.output
    assert "no derive history" in res.output.lower(), res.output


def test_a_busy_daemon_degrades_to_the_replica_and_says_so(proj, monkeypatch):
    """BUSY IS NOT ABSENT. A daemon that answers `ping` can still be holding
    the writer, and the first cut let the TimeoutError out — `rmx derive
    status` died with a traceback against the live store. Every test here
    stubbed `ping` to False, so none of them could see it."""
    d = proj / "docs"
    d.mkdir()
    _derive(proj, [_gmd(d, "alpha", "# Alpha {#root}\n")])

    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: True)

    def _timeout(*a, **k):
        raise TimeoutError("timed out")
    monkeypatch.setattr("refmatrix.daemon.call", _timeout)

    res = _run(["derive", "status"])

    assert res.exit_code == 0, res.output
    assert "did not answer" in res.output.lower(), res.output
    assert "gmd" in res.output, "it must still ANSWER, from the replica"

    res = _run(["derive", "log"])
    assert res.exit_code == 0, res.output
    assert "entities" in res.output, res.output
