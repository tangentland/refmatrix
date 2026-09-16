"""`query.log` learns WHO asked — hook, human, MCP, or the machine itself.

RED first for task 9.1 (plan-9). `telemetry.invocation_source()` has existed and
been correct since the hook work; it is written into `cli.log` and was simply
never written into `query.log`. The cost of that omission is on record: the
`brief/unanswered` confound gate named this field as the cheapest signal that
would separate a question ASKED from a pattern GREPPED, and could not use it,
because 174 of 465 zero-result rows came from an always-on hook firing on "yes"
and "go" and nothing on the row said so.

Two things these tests pin that are easy to get wrong:

  * **`invocation` is not `source`.** `query.log`'s `source` already means the
    SURFACE (`scan-prompt`, `grep-replica`); `cli.log`'s `source` means the
    FORM. Overloading one name across two logs makes every later join wrong in
    a way no test would catch.
  * **Old rows still read.** 2,527 records predate the field. A reader that
    assumes it destroys the only baseline this work has.
"""
from __future__ import annotations

import json

import pytest

from refmatrix import telemetry
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _rows(store) -> list[dict]:
    p = store.root / telemetry.LOG_NAME
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _emit(store, *, kind="scan", body="a prompt", source="scan-prompt",
          cardinality=1):
    with telemetry.log_query(store, kind=kind, body=body, source=source) as t:
        t.cardinality = cardinality


# ── the field ──────────────────────────────────────────────────────────────

def test_a_hook_sourced_query_is_recorded_as_a_hook(store, monkeypatch):
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "hook")
    _emit(store)
    assert _rows(store)[-1]["invocation"] == "hook"


def test_an_unhinted_non_tty_query_is_recorded_as_unknown(store, monkeypatch):
    monkeypatch.delenv("RMX_INVOCATION_SOURCE", raising=False)
    _emit(store)
    assert _rows(store)[-1]["invocation"] == "unknown"


def test_an_unrecognised_value_is_not_written_through(store, monkeypatch):
    """A typo in a hook template must not create a new category silently."""
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "hoook")
    _emit(store)
    assert _rows(store)[-1]["invocation"] == "unknown"


def test_invocation_and_source_are_different_keys_on_the_same_record(store,
                                                                     monkeypatch):
    """`source` stays the SURFACE. Overloading it would break every join."""
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "hook")
    _emit(store, source="scan-prompt")
    row = _rows(store)[-1]
    assert row["source"] == "scan-prompt"
    assert row["invocation"] == "hook"
    assert row["source"] != row["invocation"]


def test_every_recognised_form_round_trips(store, monkeypatch):
    for form in telemetry.INVOCATION_SOURCES:
        if form == "unknown":
            continue
        monkeypatch.setenv("RMX_INVOCATION_SOURCE", form)
        _emit(store, body=f"q for {form}")
    got = [r["invocation"] for r in _rows(store)]
    assert got == [f for f in telemetry.INVOCATION_SOURCES if f != "unknown"]


# ── the summary ────────────────────────────────────────────────────────────

def test_summarize_partitions_the_row_set_by_invocation(store, monkeypatch):
    for form, n in (("hook", 3), ("interactive", 2)):
        monkeypatch.setenv("RMX_INVOCATION_SOURCE", form)
        for i in range(n):
            _emit(store, body=f"{form}-{i}")
    s = telemetry.summarize(store)
    assert s["by_invocation"] == {"hook": 3, "interactive": 2}
    assert sum(s["by_invocation"].values()) == s["total"]


def test_zero_results_can_be_sliced_by_invocation(store, monkeypatch):
    """The exact slice the failed brief/unanswered gate needed: which misses
    came from a human asking, and which from a hook firing on 'yes'."""
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "hook")
    _emit(store, body="yes", cardinality=0)
    _emit(store, body="go", cardinality=0)
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "interactive")
    _emit(store, body="slot rotation catalog sync", cardinality=0)
    s = telemetry.summarize(store)
    assert s["zero_result_count"] == 3
    assert s["zero_by_invocation"] == {"hook": 2, "interactive": 1}


# ── the history ────────────────────────────────────────────────────────────

def test_a_legacy_record_without_the_field_reads_as_unknown(store):
    """2,527 rows predate this field. A reader that assumes it kills the
    baseline."""
    p = store.root / telemetry.LOG_NAME
    p.write_text(json.dumps({
        "ts": "2026-06-03T17:12:14", "kind": "scan", "body": "old row",
        "source": "scan-prompt", "cardinality": 0, "latency_ms": 12,
        "error": None,
    }) + "\n")
    s = telemetry.summarize(store)
    assert s["total"] == 1
    assert s["by_invocation"] == {"unknown": 1}
    assert s["zero_by_invocation"] == {"unknown": 1}


def test_a_mixed_legacy_and_new_log_is_summarised_without_raising(store,
                                                                  monkeypatch):
    p = store.root / telemetry.LOG_NAME
    p.write_text(json.dumps({
        "ts": "2026-06-03T17:12:14", "kind": "grep", "body": "old",
        "source": "grep-replica", "cardinality": 3, "latency_ms": 9,
        "error": None,
    }) + "\n")
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "hook")
    _emit(store, body="new")
    s = telemetry.summarize(store)
    assert s["total"] == 2
    assert s["by_invocation"] == {"unknown": 1, "hook": 1}


# ── the rule that telemetry never breaks the command ───────────────────────

def test_a_failing_classifier_does_not_break_the_query(store, monkeypatch):
    """These logs are diagnostics, not memory. A counting failure must never
    fail the command it describes."""
    def boom():
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(telemetry, "invocation_source", boom)
    _emit(store)                       # must not raise
    rows = _rows(store)
    assert rows, "the record should still be written"
    assert rows[-1]["invocation"] == "unknown"
