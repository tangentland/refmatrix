"""`rmx grep` is documented as a grep drop-in, and the hook rewrites EVERY bare
grep to it — so a divergence from grep's output contract is not a formatting
nit, it is every script and every agent on this machine getting wrong answers.

Reported by a peer session 2026-09-22 after a SQL/data session, verified here
against a real-grep control obtained by direct exec:

  * 500 matches in, 100 out, exit 0, nothing said. `| tail -5` then returns the
    middle of the file, which is what the reporter actually hit and could not
    find a rule for.
  * `grep -c PAT file` prints `1`; the shim printed `/path/file:1`, so
    `n=$(grep -c ...)` yields a path instead of a number.

Real grep, verified by direct exec (no shell, no hook):
    grep -c ERROR t.txt         -> '1\\n'
    grep -c ERROR t.txt t.txt   -> '/tmp/t.txt:1\\n/tmp/t.txt:1\\n'
"""
from __future__ import annotations

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


# ---- truncation must never be silent --------------------------------------

def test_a_truncated_result_set_says_so_on_stderr(tmp_path, no_daemon, monkeypatch):
    """The reporter's `| tail -5` returned lines 101-105 of a 391-line file.
    Not reordering — the cap. A short read that exits 0 and says nothing is the
    worst failure shape this project has: the surface looks healthy and the
    answer is wrong."""
    f = _write(tmp_path, "many.txt", [f"line{i:04d} ERROR" for i in range(1, 501)])
    monkeypatch.chdir(tmp_path)

    res = CliRunner().invoke(
        cli_mod.main, ["grep", "--limit", "100", "ERROR", str(f)])
    body = [l for l in res.stdout.splitlines() if l.strip()]
    assert len(body) == 100, len(body)
    assert "truncated" in res.stderr.lower() or "more match" in res.stderr.lower(), (
        f"truncation was silent. stderr={res.stderr!r}")
    assert "500" in res.stderr or "400" in res.stderr, (
        f"the notice must quantify what was withheld: {res.stderr!r}")


def test_explicit_file_paths_are_not_capped_by_default(tmp_path, no_daemon, monkeypatch):
    """`grep PAT file` is a drop-in invocation and grep returns ALL matches.
    The default cap exists for index-style exploration, not for a file read."""
    f = _write(tmp_path, "many.txt", [f"line{i:04d} ERROR" for i in range(1, 501)])
    monkeypatch.chdir(tmp_path)

    res = CliRunner().invoke(cli_mod.main, ["grep", "ERROR", str(f)])
    body = [l for l in res.stdout.splitlines() if l.strip()]
    assert len(body) == 500, f"got {len(body)} of 500 — the drop-in path still caps"


# ---- -c must match grep's contract ----------------------------------------

def test_count_of_a_single_file_is_a_bare_number(tmp_path, no_daemon, monkeypatch):
    """`n=$(grep -c ERROR f)` must yield a number. Real grep: '1'."""
    f = _write(tmp_path, "t.txt", ["a", "ERROR x"])
    monkeypatch.chdir(tmp_path)

    res = CliRunner().invoke(cli_mod.main, ["grep", "-c", "ERROR", str(f)])
    assert res.stdout.strip() == "1", repr(res.stdout)


def test_count_of_multiple_files_keeps_the_path_prefix(tmp_path, no_daemon, monkeypatch):
    """Real grep prefixes only when there is more than one file. The fix must
    not flip that the other way."""
    a = _write(tmp_path, "a.txt", ["ERROR one"])
    b = _write(tmp_path, "b.txt", ["ERROR two", "ERROR three"])
    monkeypatch.chdir(tmp_path)

    res = CliRunner().invoke(
        cli_mod.main, ["grep", "-c", "ERROR", str(a), str(b)])
    out = [l for l in res.stdout.splitlines() if l.strip()]
    assert all(":" in l for l in out), out
    assert any(l.endswith(":1") for l in out) and any(l.endswith(":2") for l in out), out


def test_provenance_on_a_named_read_is_opt_in_via_n_and_H(tmp_path, no_daemon, monkeypatch):
    """The `-c` fix must not strip the prefix from output that ASKED for it.

    Renamed and re-aimed: the original required `path:line:text` from a BARE
    read, which grep does not print for one named file. The property worth
    holding is that `-n` and `-H` still work and still compose -- that is what
    keeps hits clickable for anyone who wants them."""
    f = _write(tmp_path, "t.txt", ["a", "ERROR x"])
    monkeypatch.chdir(tmp_path)

    bare = CliRunner().invoke(cli_mod.main, ["grep", "ERROR", str(f)])
    assert [l for l in bare.stdout.splitlines() if l.strip()] == ["ERROR x"], bare.stdout

    numbered = CliRunner().invoke(cli_mod.main, ["grep", "-n", "ERROR", str(f)])
    assert [l for l in numbered.stdout.splitlines() if l.strip()] == ["2:ERROR x"], numbered.stdout

    full = CliRunner().invoke(cli_mod.main, ["grep", "-nH", "ERROR", str(f)])
    line = next(l for l in full.stdout.splitlines() if "ERROR" in l)
    assert line.startswith(str(f)) and ":2:" in line, line


# ---- explicit file paths mean READ THAT FILE ------------------------------

def test_explicit_paths_read_the_FILE_not_the_index(tmp_path, no_daemon, monkeypatch):
    """`grep PAT file` must answer from the file, byte-exact.

    This is the true root of the reporter's "lines from the middle with line
    numbers that did not correspond": with explicit paths the INDEX answered,
    returning learned `query/PAT` evidence rows — duplicated once per learning
    run, only for lines it had learned, rendered as
    `path:line  [mentions]  query/PAT` instead of grep format. Measured on a
    500-match file: 1000 rows, each line up to 3x, covering ~100 lines.

    The index is for exploration (`rmx grep PATTERN` with no paths). When the
    caller names files, grep's contract is to read them."""
    f = _write(tmp_path, "t.txt", ["alpha ERROR", "beta ok", "gamma ERROR"])
    monkeypatch.chdir(tmp_path)

    res = CliRunner().invoke(cli_mod.main, ["grep", "ERROR", str(f)])
    body = [l for l in res.stdout.splitlines() if l.strip()]
    assert len(body) == 2, body
    assert all("[mentions]" not in l for l in body), (
        f"index rows leaked into a drop-in read: {body}")
    # Real grep prints BARE lines for ONE named file -- `grep ERROR t.txt` ->
    # "alpha ERROR\ngamma ERROR" by direct exec, and ripgrep agrees. This
    # assertion used to require `:1:` / `:3:`, i.e. the SHIM's `file:line:text`,
    # which is itself the divergence this file's docstring is about. Provenance
    # is opt-in via -n/-H, asserted in the test above.
    assert body == ["alpha ERROR", "gamma ERROR"], body


def test_the_index_answers_exploration_and_never_a_drop_in_read():
    """The routing rule, unit-tested because the integration case needs a store
    whose index has LEARNED the pattern — which a fresh tmp store never has, so
    an integration-only test passes for the wrong reason."""
    assert cli_mod._index_may_answer([]) is True           # `rmx grep PATTERN`
    assert cli_mod._index_may_answer([Path("f.txt")]) is False
    assert cli_mod._index_may_answer([Path("a"), Path("b")]) is False
