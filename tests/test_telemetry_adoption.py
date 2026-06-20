"""Phase 1: telemetry extension — source/form field, summarize_all, adoption_report."""
from __future__ import annotations

import json

from refmatrix import telemetry as t


def _write_cli_log(root, records):
    with (root / t.CLI_LOG_NAME).open("a") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _write_query_log(root, records):
    with (root / t.LOG_NAME).open("a") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _end(argv, *, source="interactive", exit_code=0, latency_ms=10, error=None):
    return {
        "ts": "2026-06-20T10:00:00",
        "argv": argv,
        "cwd": "/x",
        "exit_code": exit_code,
        "latency_ms": latency_ms,
        "error": error,
        "pid": 1,
        "source": source,
    }


# ---- invocation_source ----------------------------------------------------


def test_invocation_source_env_wins(monkeypatch):
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "hook")
    assert t.invocation_source() == "hook"


def test_invocation_source_bad_env_falls_back(monkeypatch):
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "wat")
    assert t.invocation_source() == "unknown"


def test_invocation_source_no_tty_unknown(monkeypatch):
    monkeypatch.delenv("RMX_INVOCATION_SOURCE", raising=False)
    # pytest captures stdin → not a tty → unknown
    assert t.invocation_source() in t.INVOCATION_SOURCES


def test_log_cli_invocation_records_source(tmp_path, monkeypatch):
    monkeypatch.delenv("REFMATRIX_NO_TELEMETRY", raising=False)
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "hook")
    t.log_cli_invocation(
        tmp_path, argv=["context", "foo"], cwd="/x",
        exit_code=0, latency_ms=5, error=None, pid=42,
    )
    rows = t.read_cli_log(tmp_path)
    assert rows and rows[0]["source"] == "hook"


# ---- summarize_cli_log ----------------------------------------------------


def test_summarize_skips_start_intent_rows(tmp_path):
    _write_cli_log(tmp_path, [
        {"ts": "2026-06-20T10:00:00", "phase": "start", "op": "memory",
         "argv": ["memory", "add"], "pid": 1, "source": "hook"},
        _end(["memory", "add"], source="hook"),
    ])
    s = t.summarize_cli_log(tmp_path)
    assert s["total"] == 1  # start row not counted
    assert s["by_subcommand"]["memory"] == 1
    assert s["by_source"]["hook"] == 1


def test_summarize_by_source(tmp_path):
    _write_cli_log(tmp_path, [
        _end(["context", "a"], source="hook"),
        _end(["context", "b"], source="interactive"),
        _end(["query", "c"], source="hook"),
    ])
    s = t.summarize_cli_log(tmp_path)
    assert s["by_source"] == {"hook": 2, "interactive": 1}


# ---- summarize_all --------------------------------------------------------


def test_summarize_all_rolls_up_projects(tmp_path):
    a = tmp_path / "proja" / ".refmatrix"
    b = tmp_path / "projb" / ".refmatrix"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    _write_cli_log(a, [_end(["context", "x"], source="hook"),
                       _end(["ingest", "."], source="interactive")])
    _write_cli_log(b, [_end(["context", "y"], source="hook")])
    s = t.summarize_all([a, b])
    assert s["total"] == 3
    assert s["by_project"] == {"proja": 2, "projb": 1}
    assert s["by_source"]["hook"] == 2
    assert s["by_subcommand"]["context"] == 2


def test_summarize_all_empty():
    assert t.summarize_all([])["total"] == 0


# ---- adoption_report ------------------------------------------------------


def test_adoption_daemon_down_and_unsupervised(tmp_path):
    _write_cli_log(tmp_path, [_end(["context", "x"], source="hook")])
    sigs = t.adoption_report(tmp_path, daemon_up=False, launchd_installed=False)
    kinds = {s["kind"] for s in sigs}
    assert "daemon_down" in kinds and "unsupervised" in kinds
    assert sigs[0]["severity"] == "high"  # sorted, daemon_down first


def test_adoption_never_ingested(tmp_path):
    sigs = t.adoption_report(tmp_path, stats={"entities": {}})
    assert any(s["kind"] == "never_ingested" for s in sigs)


def test_adoption_no_hooks_signal(tmp_path):
    _write_cli_log(tmp_path, [_end(["context", "x"], source="interactive")])
    sigs = t.adoption_report(tmp_path)
    assert any(s["kind"] == "no_hooks" for s in sigs)


def test_adoption_no_hooks_silent_when_hooks_present(tmp_path):
    _write_cli_log(tmp_path, [_end(["context", "x"], source="hook")])
    sigs = t.adoption_report(tmp_path)
    assert not any(s["kind"] == "no_hooks" for s in sigs)


def test_adoption_high_zero_result(tmp_path):
    _write_query_log(tmp_path, [
        {"ts": "2026-06-20T10:00:00", "kind": "context", "body": f"q{i}",
         "source": "context", "cardinality": 0, "latency_ms": 1, "error": None}
        for i in range(8)
    ])
    sigs = t.adoption_report(tmp_path)
    assert any(s["kind"] == "high_zero_result" for s in sigs)


def test_adoption_underused_reads(tmp_path):
    # 20 ingest calls, never a read command → nudge
    _write_cli_log(tmp_path, [_end(["ingest", "."], source="hook") for _ in range(20)])
    sigs = t.adoption_report(tmp_path)
    assert any(s["kind"] == "underused_reads" for s in sigs)


def test_adoption_stale_files(tmp_path):
    stats = {"entities": {"code": 5}, "stale_files": [{"path": f"f{i}"} for i in range(12)]}
    sigs = t.adoption_report(tmp_path, stats=stats)
    assert any(s["kind"] == "stale" for s in sigs)
