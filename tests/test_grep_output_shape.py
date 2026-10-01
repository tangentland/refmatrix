"""Output-shaping flags on a drop-in read, resolved in ONE place.

`rmx grep` is a grep drop-in and the rewrite hook sends every bare `grep` to
it, so there is no invocation that opted in to a different output shape. bug-058
fixed truncation and `-c`; this file covers the rest of the set and pins the
rule that produced all three defects:

    An output-shaping flag must be resolved ONCE, above the
    replica/daemon/direct/fallback fork — never per render path.

bug-060: `-o` was parsed into the flag dict (cli.py `_GREP_STDIN_SHORT`) and
honoured ONLY in `_grep_stdin`, because the whole group was gated on
`stdin_mode`. A named-file read therefore accepted `-o` and silently returned
whole lines, exit 0, nothing on stderr. Reported by agent `atldb-cycle` on the
bus 2026-09-28 (msg d1478bc851f4).

Every expectation below is pinned to a REAL-GREP control obtained by direct
exec in the same test, not to a remembered contract — the earlier probe that
"confirmed" `-c` was clean had been contaminated by a shell whose `grep` is
itself rewritten to the shim.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod


@pytest.fixture
def no_daemon(monkeypatch):
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n")
    return p


def _real_grep(args: list[str], cwd: Path) -> str:
    """Ground truth by direct exec — no shell, so the rewrite hook and the
    `grep`/`rg` shell functions cannot reach it."""
    g = shutil.which("grep") or "/usr/bin/grep"
    r = subprocess.run([g, *args], capture_output=True, text=True, cwd=str(cwd))
    return r.stdout


def _body(res) -> list[str]:
    return [l for l in res.stdout.splitlines() if l.strip()]


# ---- bug-060: -o on a named file ------------------------------------------

def test_only_matching_on_a_named_file_prints_the_matches(tmp_path, no_daemon, monkeypatch):
    """`rmx grep -o alpha f` returned `f:1:alpha beta alpha beta` — the whole
    line, in index format, exit 0, nothing on stderr. Real grep prints the
    matched substrings, one per line."""
    f = _write(tmp_path, "t.txt", ["alpha beta alpha beta", "Time: 1"])
    monkeypatch.chdir(tmp_path)

    control = _real_grep(["-o", "alpha", "t.txt"], tmp_path)
    assert control.split() == ["alpha", "alpha"], f"control changed: {control!r}"

    res = CliRunner().invoke(cli_mod.main, ["grep", "-o", "alpha", "t.txt"])
    assert res.exit_code == 0, res.output
    assert _body(res) == ["alpha", "alpha"], (
        f"-o was dropped on the named-file read: {res.stdout!r}")


def test_only_matching_is_honoured_through_the_flags_option_too(tmp_path, no_daemon, monkeypatch):
    """Both spellings reach the same resolver: bare `-o` in argv and
    `--flags '-o'`. A fix that only ungates one of them is half a fix."""
    f = _write(tmp_path, "t.txt", ["alpha beta alpha"])
    monkeypatch.chdir(tmp_path)

    res = CliRunner().invoke(
        cli_mod.main, ["grep", "--flags", "-o", "alpha", "t.txt"])
    assert res.exit_code == 0, res.output
    assert _body(res) == ["alpha", "alpha"], res.stdout


def test_only_matching_still_works_on_the_pipe(tmp_path):
    """The path that already worked must keep working — the fix ungates the
    flag, it does not move it.

    A REAL pipe via the shared helper: `CliRunner(input=...)` does not make
    `_is_stdin_piped()` true, so it silently takes the INDEX path and answers
    from the live store. That is a fixture that proves nothing about pipe mode,
    and it is how the first draft of this test "passed"."""
    from tests.test_grep_stdin_dialect import _run_grep_pipe
    res = _run_grep_pipe("alpha beta alpha\n", ["-o", "alpha"], tmp_path)
    assert res.returncode == 0, res.stderr
    assert res.stdout.split() == ["alpha", "alpha"], res.stdout


# ---- the prefix / line-number rules, against a real-grep control ----------

def test_line_number_flag_is_honoured_on_a_named_file(tmp_path, no_daemon, monkeypatch):
    f = _write(tmp_path, "t.txt", ["nope", "alpha here"])
    monkeypatch.chdir(tmp_path)

    control = _real_grep(["-n", "alpha", "t.txt"], tmp_path).strip()
    assert control == "2:alpha here", f"control changed: {control!r}"

    res = CliRunner().invoke(cli_mod.main, ["grep", "-n", "alpha", "t.txt"])
    assert _body(res) == ["2:alpha here"], res.stdout


def test_with_filename_flag_prefixes_a_single_file(tmp_path, no_daemon, monkeypatch):
    """`-H` forces the prefix grep omits for one file."""
    f = _write(tmp_path, "t.txt", ["alpha here"])
    monkeypatch.chdir(tmp_path)

    control = _real_grep(["-H", "alpha", "t.txt"], tmp_path).strip()
    assert control == "t.txt:alpha here", f"control changed: {control!r}"

    res = CliRunner().invoke(cli_mod.main, ["grep", "-H", "alpha", "t.txt"])
    assert _body(res) == ["t.txt:alpha here"], res.stdout


def test_no_filename_flag_strips_the_prefix_across_two_files(tmp_path, no_daemon, monkeypatch):
    """`-h` suppresses the prefix grep adds for multiple files.

    Two gates hid this one. click claims `-h` as its own help alias, so bare
    `-h` printed the help page instead of reaching the parser; and `--flags
    '-h'` was rejected outright because the accepted-letter string
    (`irIRnLlcvwFEH`) never listed `h` or `o`. A drop-in cannot refuse a flag
    the tool it stands in for accepts."""
    _write(tmp_path, "a.txt", ["alpha one"])
    _write(tmp_path, "b.txt", ["alpha two"])
    monkeypatch.chdir(tmp_path)

    control = _real_grep(["-h", "alpha", "a.txt", "b.txt"], tmp_path)
    assert sorted(control.split("\n")[:2]) == ["alpha one", "alpha two"], control

    res = CliRunner().invoke(
        cli_mod.main, ["grep", "-h", "alpha", "a.txt", "b.txt"])
    assert "Usage:" not in res.stdout, "click still eats -h as --help"
    assert sorted(_body(res)) == ["alpha one", "alpha two"], res.stdout


def test_flags_option_accepts_every_letter_the_argv_parser_accepts(tmp_path):
    """`--flags '-o'` and `--flags '-h'` were rejected as unknown letters while
    the same letters were legal in argv. One accepted set, not two."""
    for letter in ("o", "h"):
        gf = cli_mod._parse_grep_flags(f"-{letter}")
        assert isinstance(gf, dict), letter


def test_count_across_two_files_keeps_the_prefix(tmp_path, no_daemon, monkeypatch):
    """The other half of bug-059's rule: grep prefixes `-c` for 2+ files. A fix
    that drops the prefix unconditionally breaks this direction."""
    _write(tmp_path, "a.txt", ["alpha"])
    _write(tmp_path, "b.txt", ["alpha"])
    monkeypatch.chdir(tmp_path)

    control = sorted(_real_grep(["-c", "alpha", "a.txt", "b.txt"], tmp_path).split())
    assert control == ["a.txt:1", "b.txt:1"], f"control changed: {control!r}"

    res = CliRunner().invoke(
        cli_mod.main, ["grep", "-c", "alpha", "a.txt", "b.txt"])
    assert sorted(_body(res)) == ["a.txt:1", "b.txt:1"], res.stdout


# ---- the index must not answer a read that names its own corpus -----------

def test_a_named_file_read_never_consults_the_index(tmp_path, no_daemon, monkeypatch):
    """bug-058's gate, re-asserted here because its fix sat on an unmerged
    branch for eight days while the registry recorded it as shipped. If the
    index can answer a named read, every flag rule above is bypassable."""
    f = _write(tmp_path, "t.txt", ["alpha here"])
    monkeypatch.chdir(tmp_path)
    assert cli_mod._index_may_answer([f]) is False
    assert cli_mod._index_may_answer([]) is True


def test_count_with_no_match_prints_zero_and_exits_one(tmp_path, no_daemon, monkeypatch):
    """`n=$(grep -c PAT f)` must be a number even when nothing matches. The
    count is no longer computed by the tool, so the empty-result branch has to
    print it — a regression this fix could easily have introduced, since the
    old code let the tool's own `-c 0` output carry that case."""
    f = _write(tmp_path, "t.txt", ["nothing here"])
    monkeypatch.chdir(tmp_path)

    control = subprocess.run(
        [shutil.which("grep") or "/usr/bin/grep", "-c", "absent", "t.txt"],
        capture_output=True, text=True, cwd=str(tmp_path))
    assert control.stdout.strip() == "0" and control.returncode == 1, control

    res = CliRunner().invoke(cli_mod.main, ["grep", "-c", "absent", "t.txt"])
    assert res.exit_code == 1, res.output
    assert [l for l in res.stdout.splitlines() if l.strip()] == ["0"], res.stdout


def test_the_fallback_renderer_exists_exactly_once(tmp_path):
    """Structural, and earned: `_grep_run` carried an inlined COPY of
    `_grep_rg_fallback` whose own docstring said it had been "extracted from
    `_grep_run`" — the extraction happened, the original was never deleted, and
    bug-058 then patched both siblings instead of removing one. `-c` was fixed
    twice and `-o` missed twice. A second copy must fail the build, not wait for
    the next report."""
    src = Path(cli_mod.__file__).read_text()
    assert src.count('g_letters = ') == 1, (
        "a second rg/grep command builder reappeared — route it through "
        "_grep_rg_fallback instead")
    assert src.count("# rmx grep fallback via ") == 1, (
        "a second fallback banner reappeared, which means a second renderer")
