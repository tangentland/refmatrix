"""ch-bsd r3 #s-6, the path half: a learned hit must carry an ABSOLUTE path.

`_grep_rg_fallback` handed the learn broker the file spelling `rg` printed,
which is the caller's argv spelling: relative whenever the grep named a
relative path. `_learn_grep_hits` then stored it, and bug-074's verification
later read it relative to whatever cwd the CLI or the daemon happened to have.
On the live replica, 69 of `error`'s 213 unreadable rows were exactly this
(`pytest-plan4-r4-red.log`).

The fix is at the PRODUCER, the one place that knows the cwd the tool ran in.
The display spelling is untouched (grep echoes argv); only the learned copy is
made absolute. `normpath`, never `resolve`: the spelling is the identity and a
symlink is not its target.
"""
from __future__ import annotations

import os
import types

import pytest


from refmatrix import cli as cli_mod


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_GREP_NOTE", "0")
    sub = tmp_path / "proj" / "sub"
    sub.mkdir(parents=True)
    (sub / "f.txt").write_text("x\nalpha here\n")
    monkeypatch.chdir(sub)
    return tmp_path / "proj"


def test_a_relative_argv_teaches_an_absolute_path(tree, capsys):
    got: list = []
    tlog = types.SimpleNamespace(cardinality=None, answered_by=None, learn=True)
    gf = cli_mod._parse_grep_flags("")

    cli_mod._grep_rg_fallback(pattern="alpha", regex=False, gf=gf, limit=None,
                              paths=["f.txt"], _tlog=tlog,
                              project_root=tree, learn_broker=got.extend)

    assert got, "nothing was handed to the learn broker"
    for h in got:
        assert os.path.isabs(h["file"]), f"learned a cwd-relative path: {h}"
        assert h["file"] == str(tree / "sub" / "f.txt"), h
    # The DISPLAY is still grep's: the argv spelling.
    assert "alpha here" in capsys.readouterr().out


@pytest.mark.parametrize("flags", [
    ["-rn"],                      # the default shape: was taught (r4 #b-5)
    ["-r"],                       # rg pads line numbers off a tty: r6 #s-1
    ["-rn", "-m", "5"],           # `5` was taken as the pattern: query/5
    ["-rn", "-c"], ["-rn", "-h"], ["-rn", "-l"], ["-rn", "-o"],
    ["-rn", "--count"],           # the long forms were never pinned (B2)
])
def test_the_delegate_teaches_nothing_and_prints_the_tool_output(
        tmp_path, monkeypatch, flags):
    """ch-bsd r6 #s-1 (user-approved): `_grep_delegate` runs the real tool and
    teaches NOTHING. r4/r5 guarded the teach on flag spellings; the output's
    shape is the user's, so `--include` taught padded line numbers, `-m 5`
    taught `query/5`, and the rows were protected. Output is unchanged."""
    from click.testing import CliRunner

    from refmatrix.store import Store

    monkeypatch.setenv("RMX_GREP_NOTE", "0")
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    (proj / "sub" / "a.txt").write_text("x\nalpha here\nalpha:3\n")
    s = Store(proj / ".refmatrix", backend="duckdb")
    s.init()
    s.close()
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(proj / "sub")

    res = CliRunner().invoke(cli_mod.main, ["grep", "--include=*.txt", *flags,
                                            "alpha", "."])

    assert res.exit_code == 0, res.output
    assert res.stdout.strip(), "the tool's output must still print"
    q = proj / ".refmatrix" / "learn.queue.jsonl"
    assert not q.exists() or not q.read_text().strip(), q.read_text()


def test_an_explicit_learn_on_a_delegated_call_says_it_was_ignored(tmp_path, monkeypatch):
    """ch-bsd r7 #m-4: the toggle branch says `--learn ignored`; the delegate
    branch taught nothing and said nothing."""
    from click.testing import CliRunner

    from refmatrix.store import Store

    monkeypatch.setenv("RMX_GREP_NOTE", "0")
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.txt").write_text("alpha here\n")
    Store(proj / ".refmatrix", backend="duckdb").init()
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(proj)

    r = CliRunner().invoke(cli_mod.main, ["grep", "--learn", "--include=*.txt", "-rn",
                                          "alpha", "."])
    assert "alpha here" in r.stdout
    assert "--learn ignored" in r.stderr, r.stderr
    quiet = CliRunner().invoke(cli_mod.main, ["grep", "--include=*.txt", "-rn", "alpha", "."])
    assert "--learn ignored" not in quiet.stderr
