"""Tests for `rmx grep` grep-style flag parsing and output rendering."""
from __future__ import annotations

import pytest

from refmatrix.cli import _parse_grep_flags, _render_grep_rows


def test_parse_empty():
    f = _parse_grep_flags(None)
    assert f["ignore_case"] is None
    assert f["files_only"] is False
    assert f["count"] is False
    assert f["invert"] is False
    assert f["word"] is False
    assert f["force_substring"] is False
    assert f["force_regex"] is False


def test_parse_single_letter():
    assert _parse_grep_flags("-i")["ignore_case"] is True
    assert _parse_grep_flags("-I")["ignore_case"] is False
    assert _parse_grep_flags("-l")["files_only"] is True
    assert _parse_grep_flags("-c")["count"] is True
    assert _parse_grep_flags("-v")["invert"] is True
    assert _parse_grep_flags("-w")["word"] is True
    assert _parse_grep_flags("-F")["force_substring"] is True
    assert _parse_grep_flags("-E")["force_regex"] is True


def test_parse_space_separated():
    f = _parse_grep_flags("-i -n -l")
    assert f["ignore_case"] is True
    assert f["files_only"] is True


def test_parse_bundled():
    f = _parse_grep_flags("-inl")
    assert f["ignore_case"] is True
    assert f["files_only"] is True


def test_parse_mixed():
    f = _parse_grep_flags("-i -cl")
    assert f["ignore_case"] is True
    assert f["count"] is True
    assert f["files_only"] is True


def test_parse_no_op_flags_accepted():
    # -r, -n, -H are no-ops but must not error
    f = _parse_grep_flags("-rnH")
    assert f["files_only"] is False
    assert f["count"] is False


def test_parse_missing_dash_errors():
    import click
    with pytest.raises(click.UsageError):
        _parse_grep_flags("inl")


def test_parse_unknown_letter_errors():
    import click
    with pytest.raises(click.UsageError):
        _parse_grep_flags("-z")


def test_parse_F_and_E_mutually_exclusive():
    import click
    with pytest.raises(click.UsageError):
        _parse_grep_flags("-FE")


def test_render_default(capsys):
    rows = [
        {"path": "src/a.py", "entity": "src/a.py", "line": 12,
         "linkage": "defines", "concept": "parser"},
        {"path": "src/b.py", "entity": "src/b.py", "line": 7,
         "linkage": "mentions", "concept": "parser"},
    ]
    gf = _parse_grep_flags(None)
    _render_grep_rows(rows, gf, limit=100)
    out = capsys.readouterr().out.splitlines()
    assert "src/a.py:12  [idx defines]  parser" in out
    assert "src/b.py:7  [idx mentions]  parser" in out


def test_render_files_only(capsys):
    rows = [
        {"path": "src/a.py", "entity": "src/a.py", "line": 12,
         "linkage": "defines", "concept": "parser"},
        {"path": "src/a.py", "entity": "src/a.py", "line": 44,
         "linkage": "defines", "concept": "parser"},
        {"path": "src/b.py", "entity": "src/b.py", "line": 7,
         "linkage": "mentions", "concept": "parser"},
    ]
    gf = _parse_grep_flags("-l")
    _render_grep_rows(rows, gf, limit=100)
    out = capsys.readouterr().out.splitlines()
    assert out == ["src/a.py", "src/b.py"]


def test_render_count(capsys):
    rows = [
        {"path": "src/a.py", "entity": "src/a.py", "line": 1,
         "linkage": "defines", "concept": "parser"},
        {"path": "src/a.py", "entity": "src/a.py", "line": 2,
         "linkage": "defines", "concept": "parser"},
        {"path": "src/a.py", "entity": "src/a.py", "line": 3,
         "linkage": "mentions", "concept": "parser"},
        {"path": "src/b.py", "entity": "src/b.py", "line": 1,
         "linkage": "mentions", "concept": "parser"},
    ]
    gf = _parse_grep_flags("-c")
    _render_grep_rows(rows, gf, limit=100)
    out = capsys.readouterr().out.splitlines()
    assert "src/a.py: 3" in out
    assert "src/b.py: 1" in out


def test_render_limit_applies_to_files_only(capsys):
    rows = [
        {"path": f"src/f{i}.py", "entity": f"src/f{i}.py", "line": 1,
         "linkage": "defines", "concept": "x"}
        for i in range(5)
    ]
    gf = _parse_grep_flags("-l")
    _render_grep_rows(rows, gf, limit=2)
    out = capsys.readouterr().out.splitlines()
    assert out == ["src/f0.py", "src/f1.py"]
