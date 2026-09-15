"""Tests for `rmx grep` grep-style flag parsing, output rendering, stdin
mode, and PATHS filtering."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from refmatrix.cli import (
    _filter_rows_by_paths, _grep_bare_flags, _grep_stdin, _parse_grep_flags,
    _render_grep_rows,
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
    # 0.54.0 noise trim: the source tag left the per-line format — linkage
    # stays (signal), provenance moved off stdout.
    assert "src/a.py:12  [defines]  parser" in out
    assert "src/b.py:7  [mentions]  parser" in out


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
#
# Pipe mode stands in for grep inside arbitrary pipelines (a rewrite hook can
# put `rmx grep` anywhere `grep` was), so the contract is grep's, not rmx's:
# plain matching lines, no `path:` prefix unless -H, no `N:` unless -n, and
# exit 1 when nothing matched. Anything rmx adds goes AFTER that output and is
# suppressed here via RMX_GREP_NOTE=0 (its own tests cover placement).


@pytest.fixture(autouse=True)
def _no_index_addendum(monkeypatch):
    monkeypatch.setenv("RMX_GREP_NOTE", "0")


def _run_stdin(text, pattern, *, regex=False, flags=None, limit=None):
    """Feed `text` through _grep_stdin, returning (lines, exit_code)."""
    import sys as _sys
    _sys.stdin = io.StringIO(text)
    code = 0
    try:
        _grep_stdin(pattern, regex=regex, gf=_parse_grep_flags(flags),
                    limit=limit)
    except SystemExit as exc:
        code = exc.code
    return code


def test_grep_stdin_substring(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("alpha\nbeta\nalphabet\n"))
    code = _run_stdin("alpha\nbeta\nalphabet\n", "alpha")
    out = capsys.readouterr().out.splitlines()
    assert out == ["alpha", "alphabet"]
    assert code == 0


def test_grep_stdin_case_sensitive(capsys):
    _run_stdin("Alpha\nalpha\nALPHA\n", "alpha", flags="-I")
    out = capsys.readouterr().out.splitlines()
    assert out == ["alpha"]


def test_grep_stdin_case_sensitive_by_default(capsys):
    """grep is case-SENSITIVE unless -i; a pipe filter that quietly widened
    the match would be a wrong answer downstream."""
    _run_stdin("Alpha\nalpha\nALPHA\n", "alpha")
    out = capsys.readouterr().out.splitlines()
    assert out == ["alpha"]


def test_grep_stdin_ignore_case(capsys):
    _run_stdin("Alpha\nalpha\nALPHA\n", "alpha", flags="-i")
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 3


def test_grep_stdin_regex(capsys):
    _run_stdin("foo123\nfoo\nfoobar\n", r"foo\d+", regex=True)
    out = capsys.readouterr().out.splitlines()
    assert out == ["foo123"]


def test_grep_stdin_word_boundary(capsys):
    _run_stdin("cat\ncategory\nconcat\n", "cat", flags="-w")
    out = capsys.readouterr().out.splitlines()
    assert out == ["cat"]


def test_grep_stdin_invert(capsys):
    _run_stdin("alpha\nbeta\ngamma\n", "alpha", flags="-v")
    out = capsys.readouterr().out.splitlines()
    assert out == ["beta", "gamma"]


def test_grep_stdin_count(capsys):
    _run_stdin("hit\nmiss\nhit\nhit\n", "hit", flags="-c")
    out = capsys.readouterr().out.splitlines()
    assert out == ["3"]


def test_grep_stdin_files_only_emits_stdin_label(capsys):
    _run_stdin("hit\nhit\nhit\n", "hit", flags="-l")
    out = capsys.readouterr().out.splitlines()
    assert out == ["(standard input)"]


def test_grep_stdin_files_only_no_hit_silent(capsys):
    code = _run_stdin("alpha\nbeta\n", "missing", flags="-l")
    assert capsys.readouterr().out == ""
    assert code == 1


def test_grep_stdin_files_without_match(capsys):
    _run_stdin("alpha\nbeta\n", "missing", flags="-L")
    assert capsys.readouterr().out.splitlines() == ["(standard input)"]


def test_grep_stdin_line_numbers(capsys):
    gf = _parse_grep_flags(None)
    _grep_bare_flags(["-n"], gf, stdin_mode=True)
    import sys as _sys
    _sys.stdin = io.StringIO("alpha\nbeta\nalpha\n")
    with pytest.raises(SystemExit):
        _grep_stdin("alpha", regex=False, gf=gf, limit=None)
    assert capsys.readouterr().out.splitlines() == ["1:alpha", "3:alpha"]


def test_grep_stdin_with_filename(capsys):
    gf = _parse_grep_flags(None)
    _grep_bare_flags(["-H"], gf, stdin_mode=True)
    import sys as _sys
    _sys.stdin = io.StringIO("alpha\nbeta\n")
    with pytest.raises(SystemExit):
        _grep_stdin("alpha", regex=False, gf=gf, limit=None)
    assert capsys.readouterr().out.splitlines() == ["(standard input):alpha"]


def test_grep_stdin_only_matching(capsys):
    gf = _parse_grep_flags(None)
    _grep_bare_flags(["-o"], gf, stdin_mode=True)
    import sys as _sys
    _sys.stdin = io.StringIO("xx alpha yy alpha\n")
    with pytest.raises(SystemExit):
        _grep_stdin("alpha", regex=False, gf=gf, limit=None)
    assert capsys.readouterr().out.splitlines() == ["alpha", "alpha"]


def test_grep_stdin_quiet_is_exit_code_only(capsys):
    gf = _parse_grep_flags(None)
    _grep_bare_flags(["-q"], gf, stdin_mode=True)
    import sys as _sys
    _sys.stdin = io.StringIO("alpha\n")
    with pytest.raises(SystemExit) as exc:
        _grep_stdin("alpha", regex=False, gf=gf, limit=None)
    assert capsys.readouterr().out == ""
    assert exc.value.code == 0


def test_grep_stdin_max_count(capsys):
    gf = _parse_grep_flags(None)
    _grep_bare_flags(["-m", "2"], gf, stdin_mode=True)
    import sys as _sys
    _sys.stdin = io.StringIO("hit\nhit\nhit\nhit\n")
    with pytest.raises(SystemExit):
        _grep_stdin("hit", regex=False, gf=gf, limit=None)
    assert capsys.readouterr().out.splitlines() == ["hit", "hit"]


def test_grep_stdin_context_lines_and_group_separator(capsys):
    gf = _parse_grep_flags(None)
    _grep_bare_flags(["-C1"], gf, stdin_mode=True)
    import sys as _sys
    _sys.stdin = io.StringIO(
        "a\nHIT\nb\nc\nd\ne\nHIT\nf\n"
    )
    with pytest.raises(SystemExit):
        _grep_stdin("HIT", regex=False, gf=gf, limit=None)
    assert capsys.readouterr().out.splitlines() == [
        "a", "HIT", "b", "--", "e", "HIT", "f",
    ]


def test_grep_stdin_exit_code_1_on_no_match(capsys):
    code = _run_stdin("alpha\nbeta\n", "missing")
    assert capsys.readouterr().out == ""
    assert code == 1


def test_grep_stdin_unlimited_by_default(capsys):
    """A pipe filter must not silently truncate: --limit only caps when the
    caller asked for it (the CLI passes None otherwise)."""
    _run_stdin("hit\n" * 500, "hit")
    assert len(capsys.readouterr().out.splitlines()) == 500


def test_grep_stdin_explicit_limit_caps_and_says_so(capsys):
    _run_stdin("hit\n" * 10, "hit", limit=2)
    cap = capsys.readouterr()
    assert cap.out.splitlines() == ["hit", "hit"]
    assert "capped at --limit 2" in cap.err


def test_grep_stdin_addendum_follows_grep_output(capsys, monkeypatch):
    """rmx's index note is appended AFTER grep's output, never interleaved."""
    monkeypatch.setenv("RMX_GREP_NOTE", "1")
    monkeypatch.setattr(
        "refmatrix.cli._grep_stdin_addendum",
        lambda pattern, total: print(f"# rmx: {pattern} ({total})"),
    )
    _run_stdin("alpha\nbeta\nalpha\n", "alpha")
    assert capsys.readouterr().out.splitlines() == [
        "alpha", "alpha", "# rmx: alpha (2)",
    ]


def test_grep_stdin_addendum_suppressed_in_machine_modes(capsys, monkeypatch):
    """-c/-l/-q/-o feed `wc`, `$(…)` and `&&`; an extra line there is data
    corruption, so the note is skipped."""
    monkeypatch.setenv("RMX_GREP_NOTE", "1")
    monkeypatch.setattr(
        "refmatrix.cli._grep_stdin_addendum",
        lambda pattern, total: print("# rmx: SHOULD NOT APPEAR"),
    )
    _run_stdin("hit\nhit\n", "hit", flags="-c")
    assert capsys.readouterr().out.splitlines() == ["2"]


def test_grep_stdin_addendum_never_fails_the_pipe(capsys, monkeypatch):
    """No index / no daemon must not break a filter — the note is optional."""
    monkeypatch.setenv("RMX_GREP_NOTE", "1")
    monkeypatch.setattr(
        "refmatrix.daemon.ping",
        lambda root: (_ for _ in ()).throw(RuntimeError("no daemon")),
    )
    code = _run_stdin("alpha\n", "alpha")
    assert capsys.readouterr().out.splitlines() == ["alpha"]
    assert code == 0


def test_grep_stdin_invalid_regex_raises(monkeypatch):
    import click as _click
    monkeypatch.setattr("sys.stdin", io.StringIO("anything\n"))
    with pytest.raises(_click.ClickException):
        _grep_stdin("(unclosed", regex=True, gf=_parse_grep_flags(None),
                    limit=None)


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


# --- bare grep/rg flag compatibility (drop-in) ------------------------------

from refmatrix.cli import _split_grep_argv, _grep_bare_flags


def _bare(argv):
    ft, pat, paths, _ = _split_grep_argv(list(argv))
    gf = _parse_grep_flags(None)
    note, err, delegate = (_grep_bare_flags(ft, gf) if ft
                           else (None, None, []))
    return gf, pat, paths, note, err, delegate


def test_bare_flags_split_pattern_and_paths():
    gf, pat, paths, note, err, delegate = _bare(["-rn", "daemon", "src/"])
    assert err is None and not delegate
    assert pat == "daemon" and paths == ["src/"]
    assert note is not None  # -r -n ignored with a note


def test_bare_answer_flags_honored():
    gf, pat, _, _, err, delegate = _bare(["-i", "-l", "daemon"])
    assert err is None and not delegate and pat == "daemon"
    assert gf["ignore_case"] is True and gf["files_only"] is True
    gf2, *_ = _bare(["-inl", "X"])
    assert gf2["ignore_case"] and gf2["files_only"]


def test_bare_e_supplies_pattern_and_endflags():
    _, pat, paths, _, err, delegate = _bare(["-e", "-x", "--", "src/"])
    assert err is None and not delegate
    assert pat == "-x" and paths == ["src/"]


def test_bare_whole_line_and_word():
    gf, pat, _, _, err, delegate = _bare(["-w", "-x", "widget"])
    assert err is None and not delegate
    assert gf["word"] and gf["whole_line"]


def test_bare_path_filter_delegates():
    *_, err, delegate = _bare(["-g", "*.sql", "daemon", "src/"])
    assert err is None
    assert delegate and "-g" in delegate[0] and "path filter" in delegate[0]


def test_bare_include_delegates_and_consumes_value():
    _, pat, paths, _, err, delegate = _bare(
        ["--include=*.py", "daemon", "src/"])
    assert err is None and pat == "daemon" and paths == ["src/"]
    assert delegate and "--include" in delegate[0]


def test_bare_context_flag_delegates_and_consumes_value():
    gf, pat, paths, note, err, delegate = _bare(["-C", "3", "daemon"])
    assert err is None and pat == "daemon" and paths == []  # '3' consumed
    assert delegate and "-C" in delegate[0]


def test_bare_unknown_flag_delegates():
    *_, err, delegate = _bare(["-z", "daemon"])
    assert err is None
    assert delegate and "-z" in delegate[0]


def test_bare_long_forms():
    gf, pat, _, _, err, delegate = _bare(["--ignore-case", "--count", "foo"])
    assert err is None and not delegate
    assert gf["ignore_case"] and gf["count"]


def test_bare_conflicts_rejected():
    *_, err, _d = _bare(["-l", "-L", "x"])
    assert err and "-l and -L" in err


def test_bare_num_shorthand_delegates():
    *_, err, delegate = _bare(["-3", "daemon"])
    assert err is None
    assert delegate and "-3" in delegate[0]


def test_grep_stdin_addendum_writes_only_to_stderr(capsys, monkeypatch):
    """The index note is provenance, not grep output. On 2026-09-14 the
    PreToolUse rewrite turned `grep … | awk` into `rmx grep … | awk` and the
    `# rmx: … in the index` header landed in awk's input as `set -o #`.
    With a daemon answering, stdout must stay empty and the note goes to
    stderr — same contract as the rg-fallback banner."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    monkeypatch.setenv("RMX_GREP_NOTE", "1")
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)
    monkeypatch.setattr(daemon_mod, "call", lambda root, op, args, **kw: {
        "ok": True, "result": {"rows": [
            {"path": "src/x.py", "line": 7, "linkage": "mentions", "concept": "alpha"},
        ]},
    })
    monkeypatch.setattr(cli_mod, "_root", lambda: __import__("pathlib").Path("."))
    cli_mod._grep_stdin_addendum("alpha", 2)
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "# rmx: 'alpha' in the index" in cap.err
    assert "src/x.py:7" in cap.err
