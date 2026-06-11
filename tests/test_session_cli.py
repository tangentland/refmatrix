"""End-to-end CLI test for `rmx session ingest` (Phase B).

Builds a tiny JSONL fixture, points the CLI at it via REFMATRIX_ROOT, runs
`rmx session ingest --no-index`, asserts the card lands on disk in the
right place. The full ingest-into-partition path is covered by manually
exercising the same code path inline so we don't need a daemon."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix.cli import (
    SESSIONS_PARTITION_PREFIX,
    _encode_claude_project_dir,
    main,
)


def _write_fixture_jsonl(path: Path) -> None:
    lines = [
        json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "test prompt"},
            "timestamp": "2026-06-03T00:00:00Z",
            "cwd": "/x/y/z",
            "gitBranch": "main",
        }),
        json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "test reply"}],
            },
            "timestamp": "2026-06-03T00:00:01Z",
        }),
    ]
    path.write_text("\n".join(lines) + "\n")
    # Backdate the fixture past the session-ingest active-skip window
    # (RMX_SESSION_INGEST_QUIET_S, default 300s). A just-written JSONL looks
    # like a still-live session and is skipped (active_skipped), yielding
    # built=0 — so every retrieval test downstream sees no card. Stamp the
    # mtime a day in the past so `session ingest` treats it as settled.
    old = time.time() - 86400
    os.utime(path, (old, old))


def test_encode_claude_project_dir():
    assert (
        _encode_claude_project_dir(Path("/Users/x/claude_tools/refmatrix"))
        == "-Users-x-claude-tools-refmatrix"
    )


def test_sessions_partition_prefix():
    assert SESSIONS_PARTITION_PREFIX == "sessions-"


def test_session_ingest_no_index(tmp_path, monkeypatch):
    """`rmx session ingest --no-index <path>` builds a card on disk."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    (tmp_path / ".refmatrix").mkdir()

    src = tmp_path / "test-session.jsonl"
    _write_fixture_jsonl(src)

    runner = CliRunner()
    result = runner.invoke(
        main, ["session", "ingest", "--no-index", "--verbose", str(src)]
    )
    assert result.exit_code == 0, result.output

    card = tmp_path / ".refmatrix" / "sessions" / "test-session.md"
    assert card.exists()
    body = card.read_text()
    assert 'gmd: "0.1"' in body
    assert "id: session-test-ses" in body
    assert "## User prompts {#prompts}" in body
    assert "- test prompt" in body
    assert "test reply" in body


def test_session_ingest_skips_unchanged_jsonl(tmp_path, monkeypatch):
    """Second run with the same JSONL should skip via content_hash match."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    (tmp_path / ".refmatrix").mkdir()

    src = tmp_path / "stable.jsonl"
    _write_fixture_jsonl(src)

    runner = CliRunner()
    r1 = runner.invoke(main, ["session", "ingest", "--no-index", str(src)])
    assert r1.exit_code == 0
    assert "built=1 skipped=0" in r1.output

    r2 = runner.invoke(main, ["session", "ingest", "--no-index", str(src)])
    assert r2.exit_code == 0
    assert "built=0 skipped=1" in r2.output


def test_session_ingest_force_rebuilds(tmp_path, monkeypatch):
    """--force rebuilds even when hash matches."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    (tmp_path / ".refmatrix").mkdir()

    src = tmp_path / "forced.jsonl"
    _write_fixture_jsonl(src)

    runner = CliRunner()
    runner.invoke(main, ["session", "ingest", "--no-index", str(src)])
    r = runner.invoke(
        main, ["session", "ingest", "--no-index", "--force", str(src)]
    )
    assert r.exit_code == 0
    assert "built=1 skipped=0" in r.output


def test_session_ingest_walks_directory(tmp_path, monkeypatch):
    """Pass a directory: should glob *.jsonl recursively."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    (tmp_path / ".refmatrix").mkdir()

    src_dir = tmp_path / "sessions-src"
    src_dir.mkdir()
    _write_fixture_jsonl(src_dir / "s1.jsonl")
    _write_fixture_jsonl(src_dir / "s2.jsonl")

    runner = CliRunner()
    r = runner.invoke(
        main, ["session", "ingest", "--no-index", str(src_dir)]
    )
    assert r.exit_code == 0
    assert "total_jsonl=2" in r.output
    cards = sorted((tmp_path / ".refmatrix" / "sessions").glob("*.md"))
    assert len(cards) == 2


def test_session_ingest_empty_no_files(tmp_path, monkeypatch):
    """Empty target dir prints warning and exits clean."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    (tmp_path / ".refmatrix").mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()

    runner = CliRunner()
    r = runner.invoke(main, ["session", "ingest", "--no-index", str(empty)])
    assert r.exit_code == 0
    assert "no session JSONLs found" in r.output


# --- Phase C: retrieval ---------------------------------------------------

def _setup_indexed_store(tmp_path, monkeypatch) -> Path:
    """Init a store + ingest one fixture session end-to-end. Returns the
    JSONL source path so tests can re-reference it."""
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    src = tmp_path / "abc123.jsonl"
    _write_fixture_jsonl(src)
    runner = CliRunner()
    # init resolves its target dir from cwd or --path, not REFMATRIX_ROOT.
    # Point it at tmp_path so the resulting .refmatrix matches the env var.
    r0 = runner.invoke(main, ["init", "--path", str(tmp_path),
                              "--no-hooks", "--no-agents"])
    assert r0.exit_code == 0, r0.output
    r = runner.invoke(main, ["session", "ingest", str(src)])
    assert r.exit_code == 0, r.output
    return src


def test_session_list_shows_ingested_session(tmp_path, monkeypatch):
    _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(main, ["session", "list"])
    assert r.exit_code == 0, r.output
    assert "abc123" in r.output
    assert "main" in r.output  # branch


def test_session_list_json(tmp_path, monkeypatch):
    _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(main, ["session", "list", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert len(data) == 1
    assert data[0]["session_id"] == "abc123"
    assert data[0]["branch"] == "main"


def test_session_recall_finds_by_query(tmp_path, monkeypatch):
    _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(main, ["session", "recall", "test prompt"])
    assert r.exit_code == 0, r.output
    assert "abc123" in r.output


def test_session_recall_branch_filter_excludes(tmp_path, monkeypatch):
    _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(
        main, ["session", "recall", "test", "--branch", "nonexistent"]
    )
    assert r.exit_code == 0, r.output
    assert "no matching sessions" in r.output


def test_session_show_card(tmp_path, monkeypatch):
    _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(main, ["session", "show", "abc123", "--card"])
    assert r.exit_code == 0, r.output
    assert "## User prompts {#prompts}" in r.output
    assert "test prompt" in r.output


def test_session_show_raw_returns_jsonl_path(tmp_path, monkeypatch):
    src = _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(main, ["session", "show", "abc123", "--raw"])
    assert r.exit_code == 0, r.output
    assert str(src) in r.output


def test_session_show_turns_reparses_jsonl(tmp_path, monkeypatch):
    _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(main, ["session", "show", "abc123", "--turns"])
    assert r.exit_code == 0, r.output
    assert "test prompt" in r.output
    assert "test reply" in r.output


def test_session_show_unknown_id_errors(tmp_path, monkeypatch):
    _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(main, ["session", "show", "zzzzzz"])
    assert r.exit_code != 0
    assert "no session matching" in (r.output + str(r.exception or ""))


def test_session_stats(tmp_path, monkeypatch):
    _setup_indexed_store(tmp_path, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(main, ["session", "stats"])
    assert r.exit_code == 0, r.output
    assert "sessions: 1" in r.output
    assert "claude-opus-4-7" in r.output
