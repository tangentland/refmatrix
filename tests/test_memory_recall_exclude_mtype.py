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

    rows = json.loads(result.stdout)
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

    rows = json.loads(result.stdout)
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

    rows = json.loads(result.stdout)
    names = {r["name"] for r in rows}
    assert names == {"real-feedback"}, names


def _seed_session_mix(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    s.add_memory("real-feedback", "don't mock the db", mtype="feedback")
    s.add_memory("savestate_abc", "a multi-KB handoff body",
                 mtype="session/recall-state")
    s.add_memory("focus_summary_abc", "stm digest", mtype="session/digest")
    from refmatrix.store import default_partition_name
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    monkeypatch.setenv(
        "RMX_PARTITION", default_partition_name(tmp_path / ".refmatrix"))
    return s


def test_session_start_excludes_session_mtype_by_default(tmp_path, monkeypatch):
    """The always-on SessionStart hook mode (--session-start) must NOT re-dump
    save-state / STM-digest bodies — they blow the injection budget. session/*
    is excluded by default here even without an explicit --exclude-mtype
    (cliquedb UX report 2026-07-09). Real LTM still surfaces."""
    _seed_session_mix(tmp_path, monkeypatch)
    from refmatrix.cli import main as cli_main
    result = CliRunner().invoke(cli_main, [
        "memory", "recall", "--session-start", "--json"])
    assert result.exit_code == 0, result.output
    names = {r["name"] for r in json.loads(result.stdout)}
    assert "real-feedback" in names
    assert "savestate_abc" not in names
    assert "focus_summary_abc" not in names


def test_include_session_opts_back_in(tmp_path, monkeypatch):
    """--include-session restores session/* in the hook modes."""
    _seed_session_mix(tmp_path, monkeypatch)
    from refmatrix.cli import main as cli_main
    result = CliRunner().invoke(cli_main, [
        "memory", "recall", "--session-start", "--include-session", "--json"])
    assert result.exit_code == 0, result.output
    names = {r["name"] for r in json.loads(result.stdout)}
    assert {"savestate_abc", "focus_summary_abc"} <= names


def test_plain_recent_still_keeps_session_mtype(tmp_path, monkeypatch):
    """Back-compat: the default exclusion is scoped to the hook modes
    (--session-start / --stdin-json). A plain --recent must still return
    session memories (no silent drop outside the hooks)."""
    _seed_session_mix(tmp_path, monkeypatch)
    from refmatrix.cli import main as cli_main
    result = CliRunner().invoke(cli_main, [
        "memory", "recall", "--recent", "--json"])
    assert result.exit_code == 0, result.output
    names = {r["name"] for r in json.loads(result.stdout)}
    assert {"savestate_abc", "focus_summary_abc", "real-feedback"} <= names


def test_scope_both_filters_global_rows(tmp_path, monkeypatch):
    """Regression: --scope both must apply the mtype filter to GLOBAL rows too,
    not just project. The scope-both merge leaked promoted global save-state /
    digest rows straight past --exclude-mtype (cliquedb UX report 2026-07-09)."""
    _store(tmp_path, monkeypatch).add_memory("keep", "x", mtype="feedback")
    from refmatrix import cli as climod
    monkeypatch.setattr(
        climod, "_global_recall_rows",
        # `**kw` absorbs the ping budget the CLI now passes (`timeout`,
        # `retries`). The fake pinned the OLD signature, so the command died
        # with a TypeError the moment those were added — a fake that names
        # every parameter is a fake that breaks on every new one (bug-034).
        lambda q, *, k, recent, since_s, **kw: [
            {"name": "savestate_g", "mtype": "session/recall-state", "content": "h"},
            {"name": "global-feedback", "mtype": "feedback", "content": "f"}])
    from refmatrix.cli import main as cli_main
    from refmatrix.store import default_partition_name
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    monkeypatch.setenv(
        "RMX_PARTITION", default_partition_name(tmp_path / ".refmatrix"))
    result = CliRunner().invoke(cli_main, [
        "memory", "recall", "--recent", "--scope", "both",
        "--exclude-mtype", "session/*", "--json"])
    assert result.exit_code == 0, result.output
    names = {r["name"] for r in json.loads(result.stdout)}
    assert "savestate_g" not in names       # global session/* filtered out
    assert "global-feedback" in names        # global non-session kept
    assert "keep" in names                    # project row kept


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

    rows = json.loads(result.stdout)
    assert {r["name"] for r in rows} == {"keep"}
