"""Every `rmx grep` telemetry row says WHAT answered it (task 14.1).

`query.log` recorded `source: "grep-replica"` for all 1,536 grep rows in this
project's log and nothing that distinguished *the index answered* from *the tool
floor answered* — the one quantity the grep→graph learning loop claims to move.
35 learn-path tests existed and every one tested the mechanism; none could see
the outcome.

The field is five-valued, not a boolean, because `_index_may_answer(paths)` is
`return not paths`: a drop-in read that NAMES files can never be served from the
learned index (bug-058 — a learned index served 1000 rows covering ~100 of a
file's 500 matching lines). A two-valued `index|floor` would score every correct
drop-in read as a learning miss and make the loop look dead where the tool floor
is the right answer.

    index   the learned index answered
    floor   the index was ELIGIBLE, had nothing, and rg/grep answered
    dropin  paths were named, so the index was never eligible
    stdin   a grep reading a pipe — a filter, byte-exact, consults nothing
    none    eligible, empty, --no-fallback: nothing answered

The `dropin` case below asserts against an index that DOES hold the pattern.
A test using an empty index passes against a two-valued implementation and
proves nothing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import telemetry as tel
from refmatrix.store import Store


# ---- fixtures -------------------------------------------------------------

@pytest.fixture
def no_daemon(monkeypatch):
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)


@pytest.fixture
def project(tmp_path, monkeypatch, no_daemon):
    """A real store under a real project tree, cwd'd into it."""
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    monkeypatch.delenv("REFMATRIX_NO_TELEMETRY", raising=False)
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    root = tmp_path / ".refmatrix"
    s = Store(root, backend="duckdb")
    s.init()
    s.close()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _seed_index(root: Path, concept: str, file_rel: str, line: int) -> None:
    """Put one concept + one evidence row in the index so a grep can hit it."""
    s = Store(root, backend="duckdb")
    c = s.add_concept(concept, description="seeded for the index case")
    e = s.upsert_entity(kind="code", name=file_rel, path=str(root.parent / file_rel))
    s.link("defines", c, e)
    s.add_evidence("defines", c, e, file=file_rel, line=line)
    s.close()


def _grep_rows(root: Path) -> list[dict]:
    p = root / "query.log"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("kind") == "grep":
            out.append(r)
    return out


def _last(root: Path) -> dict:
    rows = _grep_rows(root)
    assert rows, f"no grep row written to {root / 'query.log'}"
    return rows[-1]


def _run(args: list[str], **kw):
    return CliRunner().invoke(cli_mod.main, args, **kw)


# ---- the five values ------------------------------------------------------

def test_an_index_hit_says_index(project):
    (project / "src.py").write_text("def parser():\n    pass\n")
    _seed_index(project / ".refmatrix", "parser", "src.py", 1)

    res = _run(["grep", "parser"])
    assert res.exit_code == 0, res.output
    assert _last(project / ".refmatrix")["answered_by"] == "index"


def test_an_eligible_miss_says_floor(project):
    """No paths, so the index WAS eligible; it had nothing and rg/grep answered.
    This is the event the learning loop exists to prevent, and the only bucket
    whose rate learning can move."""
    (project / "t.txt").write_text("alpha beta\n")

    res = _run(["grep", "alpha"])
    assert res.exit_code == 0, res.output
    assert _last(project / ".refmatrix")["answered_by"] == "floor"


def test_a_named_path_says_dropin_even_when_the_index_holds_the_pattern(project):
    """Eligibility, not outcome, decides this one. The index holds `parser`
    here — a two-valued implementation would call this `index` or `floor` and
    either way would be wrong about what happened."""
    (project / "t.txt").write_text("def parser():\n")
    _seed_index(project / ".refmatrix", "parser", "t.txt", 1)

    res = _run(["grep", "parser", "t.txt"])
    assert res.exit_code == 0, res.output
    assert _last(project / ".refmatrix")["answered_by"] == "dropin"


def test_a_piped_filter_says_stdin(project):
    """A grep that READS A PIPE is a filter (bug-005). Driven through a REAL
    pipe in a subprocess, the idiom tests/test_grep_stdin_dialect.py uses:
    CliRunner cannot make a pipe (its stdin has no fileno, so the FIONREAD
    probe the mode depends on can never fire), and patching that probe would
    fake the very branch under test."""
    feed = project / "stdin.txt"
    feed.write_text("alpha one\nbeta two\n")
    cmd = (f"cat {feed} | {sys.executable} -m refmatrix.cli grep alpha")
    res = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True,
                         cwd=str(project))

    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines() == ["alpha one"], res.stdout
    assert _last(project / ".refmatrix")["answered_by"] == "stdin"


def test_no_fallback_on_an_empty_index_says_none(project):
    (project / "t.txt").write_text("alpha\n")

    res = _run(["grep", "--no-fallback", "alpha"])
    assert res.exit_code == 1, res.output
    assert _last(project / ".refmatrix")["answered_by"] == "none"


# ---- one decision, not one per path ---------------------------------------

def test_the_replica_path_and_the_direct_path_agree(project):
    """`_grep_run` (direct) and `_grep_run_direct` (replica) are different
    functions reaching the same fallback. Four defects in this file came from
    deciding an output rule per path; this field must not become the fifth."""
    (project / "t.txt").write_text("alpha beta\n")
    root = project / ".refmatrix"

    res = _run(["grep", "alpha"])
    assert res.exit_code == 0, res.output
    direct = _last(root)["answered_by"]

    # Make the replica snapshot exist so `_should_via_replica` picks that path.
    active = root / "catalog.A.duckdb"
    if not active.exists():
        cands = sorted(root.glob("catalog*.duckdb"))
        assert cands, f"no catalog file under {root}"
        active = cands[0]
    shutil.copy2(active, root / "catalog.read.duckdb")

    res = _run(["grep", "alpha"])
    assert res.exit_code == 0, res.output
    replica = _last(root)["answered_by"]

    assert direct == replica == "floor"


def test_every_grep_row_carries_a_known_value(project):
    """A grep row that silently lacks the field is indistinguishable from a
    legacy row, which would let the instrument grow a hole nobody can see."""
    (project / "t.txt").write_text("alpha\n")
    _run(["grep", "alpha"])
    _run(["grep", "alpha", "t.txt"])
    _run(["grep", "--no-fallback", "zzz-nothing-matches-this"])

    rows = _grep_rows(project / ".refmatrix")
    assert len(rows) == 3
    for r in rows:
        assert r.get("answered_by") in tel.ANSWERED_BY, r


# ---- the sibling field: which arm wrote this row --------------------------

def test_the_row_records_the_effective_learn_state(project):
    (project / "t.txt").write_text("alpha\n")
    root = project / ".refmatrix"

    _run(["grep", "alpha"])
    assert _last(root)["learn"] is True

    _run(["grep", "--no-learn", "alpha"])
    assert _last(root)["learn"] is False


# ---- readers must not manufacture a number -------------------------------

def test_summarize_reports_pre_field_rows_as_unknown(tmp_path, monkeypatch):
    """The 1,536 historical rows cannot be re-scored: `body` holds the pattern
    and nothing holds the paths, so eligibility is unrecoverable. A reader that
    folded them into `floor` would invent the very number this field exists to
    measure."""
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    root = tmp_path / ".refmatrix"
    s = Store(root, backend="duckdb")
    s.init()
    legacy = {"ts": "2026-09-01T10:00:00", "kind": "grep", "body": "alpha",
              "source": "grep-replica", "invocation": "hook", "cardinality": 3,
              "latency_ms": 12, "outcome": "ok", "error": None}
    with (root / "query.log").open("a") as f:
        f.write(json.dumps(legacy) + "\n")

    out = tel.summarize(s)
    s.close()

    assert out["by_answered_by"] == {"unknown": 1}
