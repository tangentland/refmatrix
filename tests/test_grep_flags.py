"""Tests for `rmx grep` grep-style flag parsing, output rendering, stdin
mode, and PATHS filtering."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from refmatrix.cli import (
    _filter_rows_by_paths, _grep_stdin, _parse_grep_flags, _render_grep_rows,
)


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


# ---- stdin pipe mode ------------------------------------------------------


def test_grep_stdin_substring(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("alpha\nbeta\nalphabet\n"))
    _grep_stdin("alpha", regex=False, gf=_parse_grep_flags(None), limit=100)
    out = capsys.readouterr().out.splitlines()
    assert out == ["<stdin>:1:alpha", "<stdin>:3:alphabet"]


def test_grep_stdin_case_sensitive(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("Alpha\nalpha\nALPHA\n"))
    _grep_stdin("alpha", regex=False, gf=_parse_grep_flags("-I"), limit=100)
    out = capsys.readouterr().out.splitlines()
    assert out == ["<stdin>:2:alpha"]


def test_grep_stdin_default_case_insensitive(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("Alpha\nalpha\nALPHA\n"))
    _grep_stdin("alpha", regex=False, gf=_parse_grep_flags(None), limit=100)
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 3


def test_grep_stdin_regex(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("foo123\nfoo\nfoobar\n"))
    _grep_stdin(r"foo\d+", regex=True, gf=_parse_grep_flags(None), limit=100)
    out = capsys.readouterr().out.splitlines()
    assert out == ["<stdin>:1:foo123"]


def test_grep_stdin_word_boundary(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("cat\ncategory\nconcat\n"))
    _grep_stdin("cat", regex=False, gf=_parse_grep_flags("-w"), limit=100)
    out = capsys.readouterr().out.splitlines()
    assert out == ["<stdin>:1:cat"]


def test_grep_stdin_invert(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("alpha\nbeta\ngamma\n"))
    _grep_stdin("alpha", regex=False, gf=_parse_grep_flags("-v"), limit=100)
    out = capsys.readouterr().out.splitlines()
    assert out == ["<stdin>:2:beta", "<stdin>:3:gamma"]


def test_grep_stdin_count(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("hit\nmiss\nhit\nhit\n"))
    _grep_stdin("hit", regex=False, gf=_parse_grep_flags("-c"), limit=100)
    out = capsys.readouterr().out.splitlines()
    assert out == ["3"]


def test_grep_stdin_files_only_emits_stdin_label(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("hit\nhit\nhit\n"))
    _grep_stdin("hit", regex=False, gf=_parse_grep_flags("-l"), limit=100)
    out = capsys.readouterr().out.splitlines()
    assert out == ["<stdin>"]


def test_grep_stdin_files_only_no_hit_silent(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("alpha\nbeta\n"))
    _grep_stdin("missing", regex=False, gf=_parse_grep_flags("-l"), limit=100)
    out = capsys.readouterr().out
    assert out == ""


def test_grep_stdin_limit(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("hit\nhit\nhit\nhit\n"))
    _grep_stdin("hit", regex=False, gf=_parse_grep_flags(None), limit=2)
    out = capsys.readouterr().out.splitlines()
    assert out == ["<stdin>:1:hit", "<stdin>:2:hit"]


def test_grep_stdin_invalid_regex_raises(monkeypatch):
    import click as _click
    monkeypatch.setattr("sys.stdin", io.StringIO("anything\n"))
    with pytest.raises(_click.ClickException):
        _grep_stdin("(unclosed", regex=True, gf=_parse_grep_flags(None), limit=100)


# ---- PATHS filter ---------------------------------------------------------


def test_filter_rows_by_paths_empty_paths_returns_all():
    rows = [{"path": "/tmp/a.py", "entity": "a", "line": 1,
             "linkage": "defines", "concept": "x"}]
    assert _filter_rows_by_paths(rows, ()) == rows


def test_filter_rows_by_paths_restricts_to_subtree(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    f1 = sub / "a.py"
    f1.write_text("")
    f2 = tmp_path / "outside.py"
    f2.write_text("")
    rows = [
        {"path": str(f1), "entity": "a", "line": 1,
         "linkage": "defines", "concept": "x"},
        {"path": str(f2), "entity": "outside", "line": 1,
         "linkage": "defines", "concept": "y"},
    ]
    kept = _filter_rows_by_paths(rows, (sub,))
    assert len(kept) == 1
    assert kept[0]["entity"] == "a"


def test_filter_rows_by_paths_multiple_targets(tmp_path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    c_dir = tmp_path / "c"
    for d in (a_dir, b_dir, c_dir):
        d.mkdir()
    fa = a_dir / "x.py"; fa.write_text("")
    fb = b_dir / "y.py"; fb.write_text("")
    fc = c_dir / "z.py"; fc.write_text("")
    rows = [
        {"path": str(fa), "entity": "x", "line": 1, "linkage": "l", "concept": "c"},
        {"path": str(fb), "entity": "y", "line": 1, "linkage": "l", "concept": "c"},
        {"path": str(fc), "entity": "z", "line": 1, "linkage": "l", "concept": "c"},
    ]
    kept = _filter_rows_by_paths(rows, (a_dir, b_dir))
    names = {r["entity"] for r in kept}
    assert names == {"x", "y"}


def test_filter_rows_by_paths_exact_file_match(tmp_path):
    f = tmp_path / "exact.py"
    f.write_text("")
    rows = [
        {"path": str(f), "entity": "exact", "line": 1, "linkage": "l", "concept": "c"},
        {"path": str(tmp_path / "other.py"), "entity": "other", "line": 1,
         "linkage": "l", "concept": "c"},
    ]
    kept = _filter_rows_by_paths(rows, (f,))
    assert len(kept) == 1
    assert kept[0]["entity"] == "exact"


def test_filter_rows_by_paths_drops_pathless_rows(tmp_path):
    rows = [
        {"path": None, "entity": "x", "line": 1, "linkage": "l", "concept": "c"},
        {"path": "", "entity": "y", "line": 1, "linkage": "l", "concept": "c"},
    ]
    kept = _filter_rows_by_paths(rows, (tmp_path,))
    assert kept == []
