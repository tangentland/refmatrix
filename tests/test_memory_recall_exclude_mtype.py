"""`rmx memory recall --exclude-mtype` regression guard.

Locks in the client-side mtype filter that hides legacy
intuition-MCP import noise (mostly `session-request` and
`session-milestone`) from recall output without requiring a
daemon-side change.

The filter applies on both the `--recent` path (rows arrive with
mtype already populated by `memory_recent`) and the hybrid ANN path
(mtype known after `memory_get` per hit). These tests exercise the
helper layer + a CLI smoke test of `--recent` end-to-end (the hybrid
path needs the daemon up and is covered by `test_memory.py` already).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix.store import Store


def _store(tmp_path, monkeypatch, backend="sqlite"):
    monkeypatch.setenv("RMX_BACKEND", backend)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def test_recent_with_exclude_mtype_drops_session_noise(tmp_path, monkeypatch):
    """CLI `recall --recent --exclude-mtype session-request,session-milestone`
    skips legacy session noise but keeps real memory rows.

    No daemon — `--recent` falls back to `_store()` directly when the
    daemon isn't running, which is the path this test exercises."""
    s = _store(tmp_path, monkeypatch)
    s.add_memory("real-feedback", "user said don't mock the db",
                 mtype="feedback")
    s.add_memory("imp-memory-4", "<task-notification>...</task-notification>",
                 mtype="session-request")
    s.add_memory("imp-memory-5", "Request: please commit",
                 mtype="session-milestone")
    s.add_memory("real-project-state", "shipping 0.4.7 today",
                 mtype="project")

    from refmatrix.cli import main as cli_main
    from refmatrix.store import default_partition_name
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    monkeypatch.setenv(
        "RMX_PARTITION", default_partition_name(tmp_path / ".refmatrix"),
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, [
        "memory", "recall", "--recent",
        "--exclude-mtype", "session-request,session-milestone",
        "--json",
    ])
    assert result.exit_code == 0, result.output

    rows = json.loads(result.output)
    names = {r["name"] for r in rows}
    assert "real-feedback" in names
    assert "real-project-state" in names
    assert "imp-memory-4" not in names
    assert "imp-memory-5" not in names


def test_recent_without_exclude_keeps_everything(tmp_path, monkeypatch):
    """Back-compat: omitting --exclude-mtype must NOT silently drop any
    row. The flag is opt-in."""
    s = _store(tmp_path, monkeypatch)
    s.add_memory("a", "x", mtype="note")
    s.add_memory("b", "y", mtype="session-request")
    s.add_memory("c", "z", mtype="session-milestone")

    from refmatrix.cli import main as cli_main
    from refmatrix.store import default_partition_name
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    monkeypatch.setenv(
        "RMX_PARTITION", default_partition_name(tmp_path / ".refmatrix"),
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, [
        "memory", "recall", "--recent", "--json",
    ])
    assert result.exit_code == 0, result.output

    rows = json.loads(result.output)
    assert {r["name"] for r in rows} == {"a", "b", "c"}


def test_recent_exclude_mtype_glob_prefix(tmp_path, monkeypatch):
    """A glob pattern hides every namespaced mtype under a prefix in one
    value: `--exclude-mtype 'session/*'` drops session/recall-state +
    session/digest while keeping real LTM. The cheat that lets namespaced
    mtypes (`<type>/<purpose>`) substitute for a dedicated purpose column."""
    s = _store(tmp_path, monkeypatch)
    s.add_memory("real-feedback", "don't mock the db", mtype="feedback")
    s.add_memory("savestate_abc", "handoff", mtype="session/recall-state")
    s.add_memory("focus_summary_abc", "digest", mtype="session/digest")

    from refmatrix.cli import main as cli_main
    from refmatrix.store import default_partition_name
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    monkeypatch.setenv(
        "RMX_PARTITION", default_partition_name(tmp_path / ".refmatrix"),
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, [
        "memory", "recall", "--recent",
        "--exclude-mtype", "session/*",
        "--json",
    ])
    assert result.exit_code == 0, result.output

    rows = json.loads(result.output)
    names = {r["name"] for r in rows}
    assert names == {"real-feedback"}, names


def test_recent_exclude_mtype_repeatable_flag(tmp_path, monkeypatch):
    """`--exclude-mtype` accepts repeated flags AND comma-separated lists
    interchangeably (matches the `--kinds` convention via
    `_split_kinds`)."""
    s = _store(tmp_path, monkeypatch)
    s.add_memory("keep", "x", mtype="feedback")
    s.add_memory("drop-a", "y", mtype="session-request")
    s.add_memory("drop-b", "z", mtype="session-milestone")

    from refmatrix.cli import main as cli_main
    from refmatrix.store import default_partition_name
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    monkeypatch.setenv(
        "RMX_PARTITION", default_partition_name(tmp_path / ".refmatrix"),
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, [
        "memory", "recall", "--recent",
        "--exclude-mtype", "session-request",
        "--exclude-mtype", "session-milestone",
        "--json",
    ])
    assert result.exit_code == 0, result.output

    rows = json.loads(result.output)
    assert {r["name"] for r in rows} == {"keep"}
