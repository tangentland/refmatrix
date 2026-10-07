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


def test_the_delegate_branch_teaches_absolute_paths_too(tmp_path, monkeypatch):
    """ch-bsd r4 #b-5's sibling: `_grep_delegate` (flags the index cannot
    express, e.g. `--include`) taught the tool's cwd-relative spelling, the
    exact defect 321ff97 fixed one function over. Its learn call was also
    wrapped in a bare `except Exception: pass` on a memory path (bug-082)."""
    import json

    from click.testing import CliRunner

    from refmatrix.store import Store

    monkeypatch.setenv("RMX_GREP_NOTE", "0")
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    (proj / "sub" / "a.txt").write_text("x\nalpha here\n")
    s = Store(proj / ".refmatrix", backend="duckdb")
    s.init()
    s.close()
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(proj / "sub")

    res = CliRunner().invoke(cli_mod.main, ["grep", "--include=*.txt", "-rn",
                                            "alpha", "."])

    assert "alpha here" in res.stdout, res.output
    q = proj / ".refmatrix" / "learn.queue.jsonl"
    assert q.exists(), "nothing was taught"
    hits = [h for line in q.read_text().splitlines()
            for h in json.loads(line)["hits"]]
    assert hits and all(os.path.isabs(h["file"]) for h in hits), hits
    assert hits[0]["file"] == str(proj / "sub" / "a.txt"), hits
