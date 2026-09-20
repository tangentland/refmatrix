"""bug-052: the telemetry counted two CONVENTIONS as failures.

`grep-replica` showed 278 "errors" in `query.log`. 256 of them are
`SystemExit: 1` — grep's normal no-match exit, which `rmx grep` honours on
purpose — and 22 are `BrokenPipeError`, which is a downstream `| head` closing
the pipe. Real failures were about 6. `cli.log` carried the same distortion
from the other side: `error_rate` was computed as *nonzero exits / total*, so
every no-match grep counted against it.

Anything reading `error` or `error_rate` from those logs was reading noise as
failure — including the reader that found bug-049, which had to dismiss 272
rows by hand before the real signal was visible.

The fix is not to drop the rows. It is to say WHICH of the four things
happened, and reserve `error` for the one that is a failure.
"""
from __future__ import annotations

import json

import pytest

from refmatrix import telemetry as tel
from refmatrix.store import Store


# ---- classification ------------------------------------------------------

def test_a_clean_run_is_ok():
    assert tel.classify_outcome(None, None) == ("ok", None)


def test_an_explicit_zero_exit_is_ok():
    assert tel.classify_outcome(SystemExit, SystemExit(0)) == ("ok", None)


def test_the_no_match_exit_is_empty_not_an_error():
    """`rmx grep` exits 1 with silent stdout when nothing matched — the grep
    contract, implemented deliberately. 256 of the 278 'errors' were this."""
    outcome, error = tel.classify_outcome(SystemExit, SystemExit(1))
    assert outcome == "empty"
    assert error is None


def test_a_real_nonzero_exit_is_still_an_error():
    outcome, error = tel.classify_outcome(SystemExit, SystemExit(2))
    assert outcome == "error"
    assert error is not None and "2" in error


def test_a_closed_consumer_is_not_a_failure_of_ours():
    """`rmx grep ... | head -5` — head exits, the pipe closes, we raise. The
    command did its job; the reader stopped reading."""
    outcome, error = tel.classify_outcome(BrokenPipeError, BrokenPipeError(32, "Broken pipe"))
    assert outcome == "consumer-closed"
    assert error is None


def test_an_actual_exception_is_an_error_with_its_text():
    outcome, error = tel.classify_outcome(ValueError, ValueError("bad dsl"))
    assert outcome == "error"
    assert error == "ValueError: bad dsl"


def test_every_outcome_is_a_declared_one():
    for exc in (None, SystemExit(0), SystemExit(1), SystemExit(3),
                BrokenPipeError(), KeyError("k")):
        t = type(exc) if exc is not None else None
        assert tel.classify_outcome(t, exc)[0] in tel.OUTCOMES


# ---- the row that gets written -------------------------------------------

@pytest.fixture
def store(tmp_path):
    """A REAL store — `log_query` appends beside the catalog, and the sibling
    telemetry tests already pay this cost. No stand-in earns its keep here."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _rows(root):
    return [json.loads(ln) for ln in (root / tel.LOG_NAME).read_text().splitlines()]


def test_a_no_match_query_row_says_empty_and_carries_no_error(store):
    try:
        with tel.log_query(store, kind="grep", body="nothing", source="grep-replica") as t:
            t.cardinality = 0
            raise SystemExit(1)
    except SystemExit:
        pass
    row = _rows(store.root)[-1]
    assert row["outcome"] == "empty"
    assert row["error"] is None


def test_a_real_failure_row_still_names_the_exception(store):
    try:
        with tel.log_query(store, kind="dsl", body="x", source="query"):
            raise RuntimeError("daemon gone")
    except RuntimeError:
        pass
    row = _rows(store.root)[-1]
    assert row["outcome"] == "error"
    assert row["error"] == "RuntimeError: daemon gone"


# ---- the readers ---------------------------------------------------------

def test_summarize_does_not_count_a_no_match_as_an_error(store):
    for _ in range(3):
        try:
            with tel.log_query(store, kind="grep", body="q", source="grep-replica") as t:
                t.cardinality = 0
                raise SystemExit(1)
        except SystemExit:
            pass
    try:
        with tel.log_query(store, kind="grep", body="q", source="grep-replica"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    s = tel.summarize(store)
    assert s["error_count"] == 1, s
    assert s["by_outcome"]["empty"] == 3, s


def test_summarize_reclassifies_legacy_rows_written_before_the_field(store):
    """The 278 rows already on disk have no `outcome`. Re-reading them by the
    same rules is what makes the historical rate honest — rewriting the log
    is not on the table."""
    root = store.root
    legacy = [
        {"ts": "2026-09-16T09:00:00", "kind": "grep", "body": "a",
         "source": "grep-replica", "cardinality": 0, "latency_ms": 12,
         "error": "SystemExit: 1"},
        {"ts": "2026-09-16T09:00:01", "kind": "grep", "body": "b",
         "source": "grep-replica", "cardinality": 0, "latency_ms": 9,
         "error": "BrokenPipeError: [Errno 32] Broken pipe"},
        {"ts": "2026-09-16T09:00:02", "kind": "dsl", "body": "c",
         "source": "query", "cardinality": None, "latency_ms": 5,
         "error": "RuntimeError: real"},
    ]
    (root / tel.LOG_NAME).write_text(
        "\n".join(json.dumps(r) for r in legacy) + "\n")
    s = tel.summarize(store)
    assert s["error_count"] == 1, s
    assert s["by_outcome"]["empty"] == 1, s
    assert s["by_outcome"]["consumer-closed"] == 1, s


def test_cli_error_rate_excludes_the_no_match_convention():
    rows = [
        {"argv": ["grep", "zzz"], "exit_code": 1, "latency_ms": 10,
         "outcome": "empty", "error": None},
        {"argv": ["grep", "zzz"], "exit_code": 1, "latency_ms": 10,
         "outcome": "empty", "error": None},
        {"argv": ["query", "bad"], "exit_code": 1, "latency_ms": 10,
         "outcome": "error", "error": "ValueError: bad"},
        {"argv": ["context", "x"], "exit_code": 0, "latency_ms": 10,
         "outcome": "ok", "error": None},
    ]
    agg = tel._aggregate_cli_rows(rows)
    assert agg["error_count"] == 1, agg
    assert agg["error_rate"] == 0.25, agg
    # the raw fact is still reported, honestly named
    assert agg["nonzero_exit_rate"] == 0.75, agg
    assert agg["exit_codes"] == {1: 3, 0: 1}, agg


def test_cli_rows_without_an_outcome_are_classified_from_their_exit_code():
    rows = [
        {"argv": ["grep", "zzz"], "exit_code": 1, "latency_ms": 10, "error": None},
        {"argv": ["sync"], "exit_code": 2, "latency_ms": 10, "error": None},
    ]
    agg = tel._aggregate_cli_rows(rows)
    assert agg["by_outcome"]["empty"] == 1, agg
    assert agg["by_outcome"]["error"] == 1, agg
