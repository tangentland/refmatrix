"""Uniform input grammar across the 3 read surfaces (audit-2 #5).

`context`, `scan-prompt`, and `memory recall` historically disagreed on how a
query is passed (positional-only / --text-or-stdin / positional-or-prompt), and
`scan-prompt` slurped raw stdin so a hook piping `{"prompt": "..."}` indexed the
braces as prose. `_resolve_query` is the one shared resolver; these tests pin
its precedence + the JSON-stdin footgun fix, plus smoke the CLI wiring."""
from __future__ import annotations

import io
import sys

import click
import pytest
from click.testing import CliRunner

from refmatrix.cli import _resolve_query, main


class _FakeStdin(io.StringIO):
    def __init__(self, data: str, tty: bool = False):
        super().__init__(data)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def _set_stdin(monkeypatch, data: str, tty: bool = False) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin(data, tty=tty))


# ---- precedence ----------------------------------------------------------

def test_positional_wins_over_everything(monkeypatch):
    _set_stdin(monkeypatch, '{"prompt":"STDIN"}')
    assert _resolve_query("pos", "txt", "prm", stdin_json=True) == "pos"


def test_text_over_prompt_over_stdin(monkeypatch):
    assert _resolve_query(None, "txt", "prm") == "txt"
    assert _resolve_query(None, None, "prm") == "prm"


def test_positional_is_stripped():
    assert _resolve_query("  hi  ") == "hi"


# ---- stdin gating --------------------------------------------------------

def test_read_stdin_false_does_not_consume_pipe(monkeypatch):
    # context / memory-recall pass read_stdin=False so a pipeline / --recent
    # doesn't silently eat stdin.
    _set_stdin(monkeypatch, "leak", tty=False)
    assert _resolve_query(None, read_stdin=False) == ""


def test_tty_stdin_not_read(monkeypatch):
    _set_stdin(monkeypatch, "should-not-read", tty=True)
    assert _resolve_query(None, read_stdin=True) == ""


def test_empty_stdin_returns_empty(monkeypatch):
    _set_stdin(monkeypatch, "   ", tty=False)
    assert _resolve_query(None, read_stdin=True) == ""


# ---- the footgun + JSON handling ----------------------------------------

def test_raw_json_envelope_extracts_prompt_not_braces(monkeypatch):
    """THE footgun: hook pipes the envelope with NO --stdin-json flag."""
    _set_stdin(monkeypatch, '{"prompt": "find auth bug", "cwd": "/x"}')
    assert _resolve_query(None, read_stdin=True) == "find auth bug"


def test_raw_prose_stdin_passthrough(monkeypatch):
    _set_stdin(monkeypatch, "just some words")
    assert _resolve_query(None, read_stdin=True) == "just some words"


def test_stdin_json_flag_parses_envelope(monkeypatch):
    _set_stdin(monkeypatch, '{"prompt": "hello"}')
    assert _resolve_query(None, stdin_json=True, read_stdin=False) == "hello"


def test_stdin_json_flag_invalid_raises(monkeypatch):
    _set_stdin(monkeypatch, "not json {")
    with pytest.raises(click.ClickException):
        _resolve_query(None, stdin_json=True, read_stdin=False)


def test_looks_like_json_but_invalid_falls_back_to_prose(monkeypatch):
    # Starts with `{` but isn't valid JSON and no explicit flag → treat as
    # prose, do NOT raise (best-effort for the bare-stdin scan-prompt path).
    _set_stdin(monkeypatch, "{not valid")
    assert _resolve_query(None, read_stdin=True) == "{not valid"


def test_empty_prompt_field_resolves_empty(monkeypatch):
    _set_stdin(monkeypatch, '{"prompt": ""}')
    assert _resolve_query(None, read_stdin=True) == ""


# ---- CLI wiring smoke (no store needed) ----------------------------------

def test_scan_prompt_accepts_positional_arg():
    # Previously errored "Got unexpected extra argument". Now positional is
    # accepted; an empty resolved prompt early-returns (exit 0) before any
    # store access.
    r = CliRunner().invoke(main, ["scan-prompt", ""])
    assert r.exit_code == 0, r.output
    assert "unexpected extra argument" not in r.output.lower()


def test_scan_prompt_help_advertises_uniform_grammar():
    r = CliRunner().invoke(main, ["scan-prompt", "--help"])
    assert "QUERY" in r.output
    assert "--text" in r.output
    assert "--stdin-json" in r.output


def test_context_help_has_text_and_stdin_json():
    r = CliRunner().invoke(main, ["context", "--help"])
    assert "--text" in r.output
    assert "--stdin-json" in r.output


def test_memory_recall_help_has_text():
    r = CliRunner().invoke(main, ["memory", "recall", "--help"])
    assert "--text" in r.output
