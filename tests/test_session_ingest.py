"""Tests for session_ingest.py — Phase A of the session-index pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from refmatrix.session_ingest import (
    SessionData,
    _dedup_consecutive,
    _is_boilerplate_prompt,
    _resolve_project_slug,
    build_card,
    ingest_session,
    parse_session_jsonl,
)


def _turn(**fields) -> str:
    return json.dumps(fields)


def _user_text(text: str, **extra) -> str:
    return _turn(
        type="user",
        message={"role": "user", "content": text},
        timestamp="2026-06-03T00:00:00Z",
        cwd="/Users/tholley/claude_tools/refmatrix",
        gitBranch="master",
        **extra,
    )


def _user_tool_result(tool_use_id: str = "tu_1") -> str:
    return _turn(
        type="user",
        message={
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}
            ],
        },
        timestamp="2026-06-03T00:00:00Z",
    )


def _assistant_text(text: str, *, model: str = "claude-opus-4-7") -> str:
    return _turn(
        type="assistant",
        message={
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": text}],
        },
        timestamp="2026-06-03T00:00:01Z",
        cwd="/Users/tholley/claude_tools/refmatrix",
        gitBranch="master",
    )


def _assistant_tool_use(name: str, **inp) -> str:
    return _turn(
        type="assistant",
        message={
            "role": "assistant",
            "model": "claude-opus-4-7",
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": name, "input": inp}
            ],
        },
        timestamp="2026-06-03T00:00:02Z",
    )


def _write_jsonl(tmp_path: Path, lines: list[str], filename: str) -> Path:
    p = tmp_path / filename
    p.write_text("\n".join(lines) + "\n")
    return p


def test_resolve_project_slug_prefers_cwd():
    assert (
        _resolve_project_slug("/Users/x/projects/foo", "-Users-x-projects-foo")
        == "Users/x/projects/foo"
    )


def test_resolve_project_slug_fallback_to_dir_decode():
    assert (
        _resolve_project_slug(None, "-Users-tholley-claude-tools-refmatrix")
        == "Users/tholley/claude/tools/refmatrix"
    )


def test_dedup_consecutive_collapses_runs():
    assert _dedup_consecutive(["a", "a", "a", "b", "a"]) == ["a (×3)", "b", "a"]


def test_dedup_consecutive_empty():
    assert _dedup_consecutive([]) == []


def test_is_boilerplate_prompt():
    assert _is_boilerplate_prompt("<system-reminder>x</system-reminder>")
    assert _is_boilerplate_prompt("<command-name>/clear</command-name>")
    assert not _is_boilerplate_prompt("real user prompt")


def test_parse_extracts_user_and_assistant(tmp_path):
    parent = tmp_path / "-Users-x-proj"
    parent.mkdir()
    p = _write_jsonl(
        parent,
        [
            _user_text("first prompt"),
            _assistant_text("first reply with commit 1a2b3c4"),
            _user_text("second prompt"),
            _assistant_text("second reply"),
        ],
        "abc12345-1111-2222-3333-444444444444.jsonl",
    )
    data = parse_session_jsonl(p)
    assert data.session_id == "abc12345-1111-2222-3333-444444444444"
    assert data.user_prompts == ["first prompt", "second prompt"]
    assert data.assistant_decisions == [
        "first reply with commit 1a2b3c4",
        "second reply",
    ]
    assert data.user_prompt_count == 2
    assert data.turn_count == 4
    assert "1a2b3c4" in data.commits
    assert data.models_used == ["claude-opus-4-7"]
    assert data.branch == "master"
    assert data.project_slug == "Users/tholley/claude_tools/refmatrix"


def test_parse_drops_tool_results_and_boilerplate(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    p = _write_jsonl(
        parent,
        [
            _user_text("<system-reminder>noise</system-reminder>"),
            _user_text("real prompt"),
            _user_tool_result(),
            _assistant_text("reply"),
        ],
        "s1.jsonl",
    )
    data = parse_session_jsonl(p)
    assert data.user_prompts == ["real prompt"]
    assert data.user_prompt_count == 1


def test_parse_collects_files_touched_from_tool_use(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    p = _write_jsonl(
        parent,
        [
            _user_text("edit foo"),
            _assistant_tool_use("Edit", file_path="/a/foo.py", old_string="x", new_string="y"),
            _assistant_tool_use("Write", file_path="/a/bar.py", content="..."),
            _assistant_tool_use("Bash", command="ls"),
        ],
        "s2.jsonl",
    )
    data = parse_session_jsonl(p)
    assert data.files_touched == ["/a/foo.py", "/a/bar.py"]
    assert dict(data.tool_counts) == {"Edit": 1, "Write": 1, "Bash": 1}


def test_parse_dedups_consecutive_identical_prompts(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    p = _write_jsonl(
        parent,
        [
            _user_text("retry"),
            _user_text("retry"),
            _user_text("retry"),
            _user_text("done"),
        ],
        "s3.jsonl",
    )
    data = parse_session_jsonl(p)
    assert data.user_prompts == ["retry (×3)", "done"]


def test_parse_ai_title_overrides_first_prompt(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    p = _write_jsonl(
        parent,
        [
            _user_text("set up daemon"),
            _turn(type="ai-title", aiTitle="Daemon Bootstrap", sessionId="s4"),
            _assistant_text("ok"),
        ],
        "s4.jsonl",
    )
    data = parse_session_jsonl(p)
    assert data.ai_title == "Daemon Bootstrap"


def test_parse_content_hash_stable(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    p = _write_jsonl(parent, [_user_text("x"), _assistant_text("y")], "s5.jsonl")
    h1 = parse_session_jsonl(p).content_hash
    h2 = parse_session_jsonl(p).content_hash
    assert h1 == h2 and len(h1) == 64


def test_parse_skips_malformed_lines(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    p = parent / "s6.jsonl"
    p.write_text(
        "\n".join([_user_text("good"), "not-json{{{", _assistant_text("reply")]) + "\n"
    )
    data = parse_session_jsonl(p)
    assert data.user_prompts == ["good"]
    assert data.assistant_decisions == ["reply"]


def test_build_card_has_required_sections(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    p = _write_jsonl(
        parent,
        [
            _user_text("how does X work"),
            _assistant_text("X works like Y"),
            _assistant_tool_use("Edit", file_path="/a/foo.py", old_string="", new_string=""),
        ],
        "s7.jsonl",
    )
    data = parse_session_jsonl(p)
    card = build_card(data)
    assert card.startswith("---\n")
    assert 'gmd: "0.1"' in card
    assert "id: session-s7" in card
    assert "## User prompts {#prompts}" in card
    assert "## Assistant decisions {#decisions}" in card
    assert "## Activity {#activity}" in card
    assert "- how does X work" in card
    assert "X works like Y" in card
    assert "- Files: /a/foo.py" in card
    assert "Edit:1" in card


def test_build_card_uses_ai_title(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    p = _write_jsonl(
        parent,
        [
            _user_text("p1"),
            _turn(type="ai-title", aiTitle="Cool Title"),
            _assistant_text("r1"),
        ],
        "s8.jsonl",
    )
    card = build_card(parse_session_jsonl(p))
    assert 'title: "Cool Title"' in card
    assert "# Cool Title {#root}" in card


def test_ingest_session_writes_card_file(tmp_path):
    parent = tmp_path / "-p"
    parent.mkdir()
    src = _write_jsonl(parent, [_user_text("q"), _assistant_text("a")], "s9.jsonl")
    dest = tmp_path / ".refmatrix" / "sessions"
    out, data = ingest_session(src, dest)
    assert out.exists()
    assert out.parent == dest
    assert out.name == "s9.md"
    assert "## User prompts" in out.read_text()
