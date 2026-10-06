"""bug-063 and bug-064: `-F` dropped in the rg branch, and `-l`/`-L` wrong.

`rmx grep` stands in for grep on EVERY bare grep (the PreToolUse rewrite), so a
divergence is not a formatting nit — every script and every agent on the machine
gets a wrong answer. Both rows below are **control-flow inversions**, the worst
shape in this family: `if cmd | grep -F 'a|b'` and `if grep -L ...` take the
branch they must not.

  bug-063  `-F` / `--fixed-strings` is accepted and silently DROPPED in the rg
           branch (`cmd += ["--regexp", pattern]`, never `-F`), so a literal
           containing a metacharacter is matched as a REGEX. `rmx grep -F
           'alpha|beta' a.txt` returned 2 matching lines and exit 0 where real
           grep returns nothing and exit 1. The grep branch honours it
           (`g_letters += "E" if regex else "F"`), so the defect is invisible
           wherever ripgrep is absent.

  bug-064  `-l` / `-L` return files in fan-out COMPLETION order instead of
           argument order, and `-L` returns the wrong exit code: grep exits 1
           when nothing matched even though `-L` printed filenames, because the
           status reflects MATCHES, not lines printed.

Every expectation here is pinned to a REAL-GREP control obtained by direct exec
in the same test — never to a remembered contract. An earlier probe that
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

HAS_RG = shutil.which("rg") is not None


@pytest.fixture
def no_daemon(monkeypatch):
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)


@pytest.fixture
def proj(tmp_path, monkeypatch, no_daemon):
    """A project with a real but EMPTY store, so every read falls to the tool
    floor — which is where both defects live.

    The store is real on purpose: with no store at all `_root()` resolves to the
    user-level one, so the test would either error out ("no refmatrix at ...")
    or read the developer's own global index. An earlier version of this fixture
    did the first and failed every case for a reason that had nothing to do with
    either bug."""
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    d = tmp_path / "t"
    d.mkdir()
    from refmatrix.store import Store
    s = Store(d / ".refmatrix", backend="duckdb")
    s.init()
    s.close()
    monkeypatch.chdir(d)
    return d


def _real_grep(args: list[str], cwd: Path) -> "tuple[str, int]":
    """Ground truth by direct exec — no shell, so neither the rewrite hook nor
    a `grep` shell function can reach it."""
    g = shutil.which("grep") or "/usr/bin/grep"
    r = subprocess.run([g, *args], capture_output=True, text=True, cwd=str(cwd))
    return r.stdout, r.returncode


def _rmx(args: list[str]):
    return CliRunner().invoke(cli_mod.main, ["grep", *args])


def _lines(s: str) -> list[str]:
    return [l for l in s.splitlines() if l.strip()]


# ---- bug-063: -F must make the pattern a literal --------------------------

@pytest.mark.skipif(not HAS_RG, reason="the defect lives in the rg branch")
def test_fixed_strings_does_not_match_as_a_regex(proj):
    """`-F 'alpha|beta'` matched BOTH lines through rg's regex alternation. Real
    grep looks for the literal text `alpha|beta`, finds nothing, exits 1."""
    (proj / "a.txt").write_text("alpha one\nbeta two\n")

    ctl_out, ctl_code = _real_grep(["-F", "alpha|beta", "a.txt"], proj)
    assert ctl_out == "" and ctl_code == 1, (ctl_out, ctl_code)

    res = _rmx(["-F", "alpha|beta", "a.txt"])

    assert _lines(res.stdout) == [], res.stdout
    assert res.exit_code == 1, (
        "exit 0 inverts `if cmd | grep -F 'a|b'` — the branch runs when it "
        f"must not (got {res.exit_code})")


@pytest.mark.skipif(not HAS_RG, reason="the defect lives in the rg branch")
def test_fixed_strings_matches_a_literal_metacharacter(proj):
    """The other direction: a line that really DOES contain the literal must
    still be found, so the fix cannot be "-F means never match"."""
    (proj / "a.txt").write_text("plain alpha\nthe alpha|beta literal\n")

    ctl_out, ctl_code = _real_grep(["-nF", "alpha|beta", "a.txt"], proj)
    assert ctl_code == 0 and len(_lines(ctl_out)) == 1, (ctl_out, ctl_code)

    res = _rmx(["-nF", "alpha|beta", "a.txt"])

    assert res.exit_code == 0, res.output
    assert _lines(res.stdout) == _lines(ctl_out), (res.stdout, ctl_out)


@pytest.mark.skipif(not HAS_RG, reason="the defect lives in the rg branch")
def test_fixed_strings_count_matches_the_control(proj):
    """The reported form: `-cF` over a registry table returned the file's line
    count because the unescaped pipes read as alternation."""
    (proj / "reg.md").write_text(
        "| bug-054 | one |\n| bug-055 | two |\n| bug-056 | three |\n")

    ctl_out, _ = _real_grep(["-cF", "| bug-054 |", "reg.md"], proj)
    assert ctl_out.strip() == "1", ctl_out

    res = _rmx(["-cF", "| bug-054 |", "reg.md"])

    assert res.stdout.strip() == ctl_out.strip(), (res.stdout, ctl_out)


@pytest.mark.skipif(not HAS_RG, reason="the defect lives in the rg branch")
def test_a_regex_is_still_a_regex_without_dash_f(proj):
    """-F is opt-in: `-E 'alpha|beta'` must still alternate."""
    (proj / "a.txt").write_text("alpha one\nbeta two\ngamma\n")

    ctl_out, _ = _real_grep(["-nE", "alpha|beta", "a.txt"], proj)
    assert len(_lines(ctl_out)) == 2, ctl_out

    res = _rmx(["-nE", "alpha|beta", "a.txt"])

    assert _lines(res.stdout) == _lines(ctl_out), (res.stdout, ctl_out)


# ---- bug-064: -l / -L order and exit status -------------------------------

def test_files_with_match_come_back_in_argument_order(proj):
    """`-l alpha a.txt b.txt` gave `b.txt, a.txt` — fan-out completion order.
    `grep -l X *.py | head -1` then picks an arbitrary file."""
    for name in ("a.txt", "b.txt", "c.txt"):
        (proj / name).write_text("alpha here\n")

    ctl_out, ctl_code = _real_grep(["-l", "alpha", "a.txt", "b.txt", "c.txt"], proj)
    assert _lines(ctl_out) == ["a.txt", "b.txt", "c.txt"], ctl_out

    res = _rmx(["-l", "alpha", "a.txt", "b.txt", "c.txt"])

    assert res.exit_code == ctl_code, (res.exit_code, ctl_code)
    assert [Path(l).name for l in _lines(res.stdout)] == ["a.txt", "b.txt", "c.txt"], \
        res.stdout


def test_files_without_match_come_back_in_argument_order(proj):
    for name in ("a.txt", "b.txt", "c.txt"):
        (proj / name).write_text("nothing here\n")

    ctl_out, _ = _real_grep(["-L", "zzz", "a.txt", "b.txt", "c.txt"], proj)
    assert _lines(ctl_out) == ["a.txt", "b.txt", "c.txt"], ctl_out

    res = _rmx(["-L", "zzz", "a.txt", "b.txt", "c.txt"])

    assert [Path(l).name for l in _lines(res.stdout)] == ["a.txt", "b.txt", "c.txt"], \
        res.stdout


def test_files_without_match_exits_one_when_nothing_matched(proj):
    """The sharper half. `-L` printing filenames does NOT mean a match was
    found — the status reflects MATCHES, so grep exits 1 here and every
    `if grep -L ...` built on it is inverted by a 0."""
    (proj / "a.txt").write_text("nothing\n")
    (proj / "b.txt").write_text("nothing either\n")

    ctl_out, ctl_code = _real_grep(["-L", "zzz", "a.txt", "b.txt"], proj)
    assert len(_lines(ctl_out)) == 2 and ctl_code == 1, (ctl_out, ctl_code)

    res = _rmx(["-L", "zzz", "a.txt", "b.txt"])

    assert len(_lines(res.stdout)) == 2, res.stdout
    assert res.exit_code == 1, (
        f"-L listed 2 files and exited {res.exit_code}; grep exits "
        f"{ctl_code} because nothing matched")


def test_files_without_match_exits_zero_when_something_matched(proj):
    """And the control for the above: when SOME file matched, `-L` lists the
    others and exits 0. A fix that always exits 1 passes the previous test and
    breaks this one."""
    (proj / "a.txt").write_text("alpha\n")
    (proj / "b.txt").write_text("nothing\n")

    ctl_out, ctl_code = _real_grep(["-L", "alpha", "a.txt", "b.txt"], proj)
    assert _lines(ctl_out) == ["b.txt"] and ctl_code == 0, (ctl_out, ctl_code)

    res = _rmx(["-L", "alpha", "a.txt", "b.txt"])

    assert [Path(l).name for l in _lines(res.stdout)] == ["b.txt"], res.stdout
    assert res.exit_code == 0, (res.exit_code, ctl_code)


def test_files_with_match_exits_one_when_nothing_matched(proj):
    (proj / "a.txt").write_text("nothing\n")

    _, ctl_code = _real_grep(["-l", "zzz", "a.txt"], proj)
    assert ctl_code == 1

    res = _rmx(["-l", "zzz", "a.txt"])

    assert res.exit_code == 1, res.exit_code


def test_files_without_match_prints_nothing_and_exits_zero_when_all_match(proj):
    """The half bug-064's row did not name, found by reading the code path
    rather than the report: with every file matching, `-L` prints NOTHING and
    grep exits 0 because a line was selected. The old code fell through to the
    empty-output branch, which says "no matches" and exits 1 — inverted again,
    in the direction the report never tested."""
    (proj / "a.txt").write_text("alpha\n")
    (proj / "b.txt").write_text("alpha too\n")

    ctl_out, ctl_code = _real_grep(["-L", "alpha", "a.txt", "b.txt"], proj)
    assert _lines(ctl_out) == [] and ctl_code == 0, (ctl_out, ctl_code)

    res = _rmx(["-L", "alpha", "a.txt", "b.txt"])

    assert _lines(res.stdout) == [], res.stdout
    assert res.exit_code == 0, (
        f"-L with every file matching exited {res.exit_code}; grep exits "
        f"{ctl_code} because a line was selected")


def test_a_directory_walk_still_lists_its_files(proj):
    """The ordering fix applies to NAMED paths only — re-sorting a walk would
    invent an order grep does not promise. The walk must still work."""
    (proj / "sub").mkdir()
    (proj / "sub" / "x.txt").write_text("alpha\n")
    (proj / "sub" / "y.txt").write_text("alpha\n")

    res = _rmx(["-l", "alpha", "sub"])

    assert res.exit_code == 0, res.output
    assert sorted(Path(l).name for l in _lines(res.stdout)) == ["x.txt", "y.txt"], \
        res.stdout


def test_the_grep_branch_gets_the_same_order_and_exit(proj, monkeypatch):
    """Both bugs were rg-branch defects, but the FIX is after the exec and so
    must hold for the grep branch too — the branch that runs wherever ripgrep
    is absent, and the one `-F` was always correct on."""
    # `_grep_rg_fallback` does `import shutil` inside the function, so the
    # object it resolves is the real module — patch that, not a module
    # attribute on cli (which does not exist and made this test error rather
    # than fail).
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which",
                        lambda n: None if n == "rg" else real_which(n))
    for name in ("a.txt", "b.txt"):
        (proj / name).write_text("nothing\n")

    res = _rmx(["-L", "zzz", "a.txt", "b.txt"])

    assert [Path(l).name for l in _lines(res.stdout)] == ["a.txt", "b.txt"], res.stdout
    assert res.exit_code == 1, res.exit_code
