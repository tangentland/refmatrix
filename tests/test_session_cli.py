"""End-to-end CLI test for `rmx session ingest` (Phase B).

Builds a tiny JSONL fixture, points the CLI at it via REFMATRIX_ROOT, runs
`rmx session ingest --no-index`, asserts the card lands on disk in the
right place. The full ingest-into-partition path is covered by manually
exercising the same code path inline so we don't need a daemon."""
from __future__ import annotations

import json
import os
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
