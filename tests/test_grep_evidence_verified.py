"""bug-074 / bug-073: an index row must hold the pattern on the line it names.

An index row is `(path, line)` from `linkage_evidence`. For a code symbol the
semantic ingest attaches a keyword concept to the enclosing SYMBOL'S DEFINITION
line, not to the line the token sits on — so `grep_evidence("error")` returned
`brief.py:155` (`def _pairs(...)`) whose body holds "error" at line 159. Right
for a graph, wrong for a grep drop-in. Measured on a real src+docs store,
precision against a literal `rg` control:

    pattern     unverified              verified
    error       66 rows prec 0.000      0 rows -> floor
    ERROR       66 rows prec 0.000      0 rows -> floor
    bitmap      46 rows prec 0.087      4 rows prec 1.000
    timeout     24 rows prec 0.542     13 rows prec 1.000
    partition  187 rows prec 0.230     43 rows prec 1.000
    pagerank    22 rows prec 0.227      5 rows prec 1.000

Cost +2-3.6 ms p50 (3.0 -> 5.4-6.6 ms), against a tool floor measured in tens
of ms to seconds. One read per DISTINCT file, cached.

It also closes the case half (bug-073): `c.name ILIKE` cannot honour case, so
`rmx grep ERROR` drew 66 rows on a corpus where real grep matches ERROR
nowhere. A case-correct line check drops all of them, and `-i` keeps them.

THE SAFETY PROPERTY, which is what makes this a filter and not a truncation:
every caller's shape is `if rows: render; return` then the tool floor, so a
fully-filtered answer degrades to REAL GREP, never to a false "no matches".
bug-058 was a short read that looked successful; this must not become one.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from refmatrix.store import Store, verify_evidence_rows

RMX = Path(__file__).resolve().parents[1] / ".venv-eval" / "bin" / "rmx"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    yield s
    s.close()


def _seed(s, tmp_path, *, concept: str, line: int, body: str):
    """One concept whose evidence points at `line` of a real file."""
    f = tmp_path / "mod.py"
    f.write_text(body)
    cid = s.add_concept(concept)
    eid = s.upsert_entity("code", f"{concept}-site", path=str(f))
    s.link("mentions", cid, eid)
    s.add_evidence("mentions", cid, eid, file=str(f), line=line)
    return f


# ---- the defect: evidence on the def line, token on another line ----------

def test_a_row_pointing_at_the_def_line_is_dropped(store, tmp_path):
    """THE bug-074 shape, reproduced exactly: evidence at the `def`, token
    three lines down."""
    _seed(store, tmp_path, concept="keyword/error", line=1,
          body="def handler():\n    pass\n    # an error happens here\n")

    assert store.grep_evidence("error", verify=False), "precondition"
    assert store.grep_evidence("error") == [], \
        "the def-line row survived verification"


def test_a_row_pointing_at_the_real_line_is_kept(store, tmp_path):
    _seed(store, tmp_path, concept="keyword/error", line=3,
          body="def handler():\n    pass\n    # an error happens here\n")

    rows = store.grep_evidence("error")
    assert len(rows) == 1, rows
    assert rows[0]["line"] == 3


# ---- case (bug-073) -------------------------------------------------------

def test_case_is_honoured_by_default(store, tmp_path):
    """`ILIKE` threw the caller's case away. `rmx grep ERROR` drew rows on a
    corpus where real grep matches ERROR nowhere."""
    _seed(store, tmp_path, concept="keyword/error", line=1,
          body="an error here\n")

    assert store.grep_evidence("error"), "lowercase must still match"
    assert store.grep_evidence("ERROR") == [], \
        "ERROR matched a line containing only lowercase 'error'"


def test_dash_i_keeps_the_case_insensitive_rows(store, tmp_path):
    _seed(store, tmp_path, concept="keyword/error", line=1,
          body="an error here\n")

    assert store.grep_evidence("ERROR", ignore_case=True), \
        "-i must keep what case-sensitivity drops"


# ---- the SAFETY property, end to end -------------------------------------

@pytest.mark.skipif(not RMX.exists(), reason="dev venv rmx not built")
def test_a_fully_filtered_answer_falls_through_to_the_floor(tmp_path):
    """The property that makes this a filter and not a truncation.

    The store holds ONE evidence row and it is wrong (points at line 1, where
    the pattern is absent). The file really does contain the pattern on line 3.
    Verification must empty the index answer AND the read must then return the
    REAL line from the tool floor — never "no matches", which would turn a
    wrong answer into a false negative (the bug-058 class, and worse).
    """
    f = tmp_path / "mod.py"
    f.write_text("def handler():\n    pass\n    # an error happens here\n")
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    cid = s.add_concept("keyword/error")
    eid = s.upsert_entity("code", "error-site", path=str(f))
    s.link("mentions", cid, eid)
    s.add_evidence("mentions", cid, eid, file=str(f), line=1)
    s.close()

    r = subprocess.run([str(RMX), "grep", "-n", "error"],
                       cwd=str(tmp_path), capture_output=True, text=True,
                       timeout=120)
    body = [l for l in r.stdout.splitlines()
            if l.strip() and not l.startswith("#")]

    assert r.returncode == 0, (r.returncode, r.stderr[:400])
    assert body, f"fell through to a false 'no matches': {r.stderr[:300]}"
    assert any(":3:" in l for l in body), body
    assert "rmx grep fallback" in r.stderr, (
        "the answer did not come from the floor — so either the index "
        "returned an unverified row, or the fall-through is gone")


# ---- the helper's own contract -------------------------------------------

def test_an_unreadable_file_is_dropped_and_COUNTED():
    """Never kept on faith, and never silently dropped either: a retrieval
    path that cannot verify a row says how many it could not."""
    stats: dict = {}
    rows = [{"path": "/nonexistent/nope.py", "line": 4, "concept": "x"}]

    assert verify_evidence_rows(rows, "anything", stats=stats) == []
    assert stats["unreadable"] == 1, stats
    assert stats["kept"] == 0


def test_a_row_past_the_end_of_the_file_is_dropped(tmp_path):
    f = tmp_path / "short.py"
    f.write_text("one line\n")
    stats: dict = {}
    rows = [{"path": str(f), "line": 99, "concept": "x"}]

    assert verify_evidence_rows(rows, "one", stats=stats) == []
    assert stats["dropped"] == 1, stats


def test_a_row_with_no_location_cannot_be_offered_as_a_hit(tmp_path):
    stats: dict = {}
    rows = [{"path": None, "line": None, "concept": "x"}]
    assert verify_evidence_rows(rows, "x", stats=stats) == []
    assert stats["dropped"] == 1


def test_regex_rows_are_verified_as_regexes(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def alpha():\n    beta\n")
    keep = [{"path": str(f), "line": 1, "concept": "c"}]
    drop = [{"path": str(f), "line": 2, "concept": "c"}]

    assert verify_evidence_rows(keep, r"^def ", regex=True) == keep
    assert verify_evidence_rows(drop, r"^def ", regex=True) == []


def test_an_unparseable_regex_verifies_nothing_rather_than_everything(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("anything\n")
    rows = [{"path": str(f), "line": 1, "concept": "c"}]

    assert verify_evidence_rows(rows, "(unclosed", regex=True) == [], \
        "a bad regex must not pass rows through unchecked"


def test_verify_false_returns_the_raw_rows(store, tmp_path):
    """The opt-out exists for a caller that wants concept provenance rather
    than grep-shaped hits; it must really skip the check."""
    _seed(store, tmp_path, concept="keyword/error", line=1,
          body="def handler():\n    # error\n")

    assert store.grep_evidence("error", verify=False)
    assert store.grep_evidence("error", verify=True) == []


def test_one_read_per_distinct_file(tmp_path, monkeypatch):
    """Cost control: the verification is on every rewritten grep, so N rows in
    one file must not be N reads."""
    f = tmp_path / "m.py"
    f.write_text("alpha\nalpha\nalpha\n")
    reads = {"n": 0}
    real = Path.read_text

    def counting(self, *a, **k):
        if self == f:
            reads["n"] += 1
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", counting)
    rows = [{"path": str(f), "line": i, "concept": "c"} for i in (1, 2, 3)]

    assert len(verify_evidence_rows(rows, "alpha")) == 3
    assert reads["n"] == 1, f"{reads['n']} reads for one file"
