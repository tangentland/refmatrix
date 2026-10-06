"""bug-062: an EMPTY producer turned a pipeline into a TREE SEARCH.

    { true; } | rmx grep hello

exited **0** with unrelated repo hits where real grep prints nothing and exits
1 — so `if cmd | rmx grep PAT` took the match branch when it must take the
other one. The peer report it explains: a backgrounded
`psql -f dryrun.sql 2>&1 | grep -vE … | tail -45` whose output file came back
0 bytes CONTAINING repo matches.

THE ROW'S PREMISE WAS WRONG, and measuring is what showed it. bug-062 says "at
the fd level 'the producer emitted nothing' and 'there is no producer' are
indistinguishable: both are a FIFO at EOF", and concludes the fix needs a
product decision. On this platform they are NOT the same thing:

    bare command under the harness   fd 0 = character device (/dev/null)
    `{ true; } | cmd`                fd 0 = FIFO

So "is stdin a pipe?" is answerable without guessing, and `_is_stdin_piped`
was asking the wrong question — whether bytes are PENDING, which conflates an
empty pipe with no pipe. A FIFO is a pipe whether or not the producer wrote
anything, exactly as grep treats it.

Two tests in `test_grep_stdin_dialect.py` encoded the old contract and are
updated there with this measurement as the reason, not deleted.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from refmatrix.store import Store

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def proj(tmp_path):
    """A real project whose index HOLDS the pattern, so a tree search would
    produce hits — without that, this test cannot tell a correct empty answer
    from a tree search that happened to find nothing."""
    d = tmp_path / "t"
    d.mkdir()
    (d / "src.py").write_text("hello world\nhello again\n")
    s = Store(d / ".refmatrix", backend="duckdb")
    s.init()
    c = s.add_concept("hello", description="seeded")
    e = s.upsert_entity(kind="code", name="src.py", path=str(d / "src.py"))
    s.link("defines", c, e)
    s.add_evidence("defines", c, e, file="src.py", line=1)
    s.close()
    return d


def _env(proj: Path) -> dict:
    e = dict(os.environ)
    e["REFMATRIX_ROOT"] = str(proj / ".refmatrix")
    e["RMX_CLAUDE_HOOKS_DIR"] = str(proj / "hooks")
    e["RMX_LEARN"] = "0"
    return e


def _run(proj: Path, args: list[str], stdin_mode: str):
    """Run `rmx grep` with a REAL stdin of the requested shape.

    Shell-free on purpose: in this harness a shell `grep` is itself rewritten
    to the wrapper, so a control obtained through `sh -c` is contaminated — the
    mistake this project has now made three times.
    """
    cmd = [sys.executable, "-m", "refmatrix.cli", "grep", *args]
    kw = dict(capture_output=True, text=True, cwd=str(proj), env=_env(proj))
    if stdin_mode == "empty-pipe":
        return subprocess.run(cmd, input="", **kw)            # a real FIFO, no bytes
    if stdin_mode == "pipe-with-data":
        return subprocess.run(cmd, input="hello from the pipe\nbeta\n", **kw)
    if stdin_mode == "devnull":
        with open(os.devnull) as fh:
            return subprocess.run(cmd, stdin=fh, **kw)
    raise AssertionError(stdin_mode)


def _real_grep(proj: Path, args: list[str], stdin_mode: str):
    g = shutil.which("grep") or "/usr/bin/grep"
    kw = dict(capture_output=True, text=True, cwd=str(proj))
    if stdin_mode == "empty-pipe":
        return subprocess.run([g, *args], input="", **kw)
    if stdin_mode == "pipe-with-data":
        return subprocess.run([g, *args], input="hello from the pipe\nbeta\n", **kw)
    with open(os.devnull) as fh:
        return subprocess.run([g, *args], stdin=fh, **kw)


def _lines(s: str) -> list[str]:
    return [l for l in s.splitlines() if l.strip()]


# ---- the measurement the fix rests on ------------------------------------

def test_a_bare_invocation_and_an_empty_pipeline_differ_at_the_fd():
    """Pinned as a test because bug-062's analysis assumed the opposite, and
    the whole fix depends on it. If a future platform really does hand a bare
    command a FIFO, THIS fails first and explains why the rest will."""
    bare = subprocess.run(
        [sys.executable, "-c",
         "import os,stat;print(stat.S_ISFIFO(os.fstat(0).st_mode))"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL)
    piped = subprocess.run(
        [sys.executable, "-c",
         "import os,stat;print(stat.S_ISFIFO(os.fstat(0).st_mode))"],
        capture_output=True, text=True, input="")

    assert bare.stdout.strip() == "False", bare.stdout
    assert piped.stdout.strip() == "True", piped.stdout


# ---- bug-062 -------------------------------------------------------------

def test_an_empty_producer_is_an_empty_result_not_a_tree_search(proj):
    """The headline. The index HOLDS `hello`, so a tree search finds things —
    which is exactly how this shipped a wrong answer with exit 0."""
    ctl = _real_grep(proj, ["hello"], "empty-pipe")
    assert _lines(ctl.stdout) == [] and ctl.returncode == 1, ctl

    res = _run(proj, ["hello"], "empty-pipe")

    assert _lines(res.stdout) == [], (
        "an empty producer produced hits — the pipeline became a tree search\n"
        + res.stdout)
    assert res.returncode == 1, (
        f"exit {res.returncode} inverts `if cmd | rmx grep PAT`; grep exits "
        f"{ctl.returncode}")


def test_a_pipe_with_data_is_still_filtered(proj):
    """The control that keeps the fix honest: a real filter must still work,
    byte-for-byte against grep."""
    ctl = _real_grep(proj, ["hello"], "pipe-with-data")
    assert ctl.returncode == 0 and len(_lines(ctl.stdout)) == 1, ctl

    res = _run(proj, ["hello"], "pipe-with-data")

    assert _lines(res.stdout) == _lines(ctl.stdout), (res.stdout, ctl.stdout)
    assert res.returncode == 0


def test_a_bare_invocation_still_searches_the_index(proj):
    """The other control, and the reason the row thought a decision was
    needed: exploration must keep working when stdin is the harness's
    /dev/null. A fix that honours "no tty means piped" breaks every bare
    `rmx grep PATTERN` an agent types."""
    res = _run(proj, ["hello"], "devnull")

    assert res.returncode == 0, res.stderr
    assert _lines(res.stdout), "bare exploration returned nothing"


def test_an_empty_pipe_does_not_learn(proj):
    """A tree search also TAUGHT the graph from a pipeline that had no input.
    With the pipe honoured there is nothing to teach, so the queue stays
    empty — asserted because a silent write is how this would come back."""
    from refmatrix import learn_queue as lq
    env = _env(proj)
    env["RMX_LEARN"] = "1"
    # A pattern the INDEX does not hold but the file does, so pre-fix the tree
    # search reaches the floor, finds it, and teaches. Using an indexed pattern
    # made this pass for the wrong reason: the index answered, so no floor ran
    # and nothing would have been taught either way.
    subprocess.run([sys.executable, "-m", "refmatrix.cli", "grep", "again"],
                   input="", capture_output=True, text=True, cwd=str(proj),
                   env=env)

    assert lq.pending_lines(proj / ".refmatrix") == 0, (
        "an empty pipeline taught the graph what a TREE search found")


def test_a_file_redirect_is_filtered_like_grep_does(proj):
    """`rmx grep PAT < file` is stdin input to grep too. The pipe tests above
    cannot see this branch — a mutation deleting regular-file support left them
    all green."""
    feed = proj / "feed.txt"
    feed.write_text("hello from the file\nbeta\n")
    env = _env(proj)
    cmd = [sys.executable, "-m", "refmatrix.cli", "grep", "hello"]
    with feed.open() as fh:
        res = subprocess.run(cmd, stdin=fh, capture_output=True, text=True,
                             cwd=str(proj), env=env)
    g = shutil.which("grep") or "/usr/bin/grep"
    with feed.open() as fh:
        ctl = subprocess.run([g, "hello"], stdin=fh, capture_output=True,
                             text=True, cwd=str(proj))

    assert _lines(res.stdout) == _lines(ctl.stdout), (res.stdout, ctl.stdout)
    assert res.returncode == ctl.returncode == 0


def test_an_empty_file_redirect_is_empty_not_a_tree_search(proj):
    """And an EMPTY redirect must behave like an empty pipe, not like no
    stdin — the same inversion bug-062 had, by a different route."""
    feed = proj / "empty.txt"
    feed.write_text("")
    cmd = [sys.executable, "-m", "refmatrix.cli", "grep", "hello"]
    with feed.open() as fh:
        res = subprocess.run(cmd, stdin=fh, capture_output=True, text=True,
                             cwd=str(proj), env=_env(proj))

    assert _lines(res.stdout) == [], res.stdout
    assert res.returncode == 1, res.returncode


def test_a_tty_stdin_still_explores(proj):
    """A human at a terminal typing `rmx grep PATTERN` must search the index,
    not sit waiting to read the terminal. Driven through a REAL pty, because
    no other test in this file has a tty and a mutation deleting the isatty
    check passed all of them."""
    import pty
    master, slave = pty.openpty()
    try:
        res = subprocess.run(
            [sys.executable, "-m", "refmatrix.cli", "grep", "hello"],
            stdin=slave, capture_output=True, text=True, cwd=str(proj),
            env=_env(proj), timeout=60)
    finally:
        os.close(master)
        os.close(slave)

    assert res.returncode == 0, res.stderr
    assert _lines(res.stdout), "a tty invocation returned nothing"


def test_a_socket_stdin_explores_instead_of_blocking_forever(proj):
    """REGRESSION, found in-session minutes after bug-062 shipped.

    This harness gives a BACKGROUNDED command a unix socket on fd 0 — not
    /dev/null, not a FIFO. The first cut of the fd-shape rule counted
    `S_ISSOCK` as a stream, so `rmx grep PATTERN` tried to filter a socket that
    never delivers data and never delivers EOF, and blocked FOREVER: a real
    process sat at 0.11s CPU for five minutes with fd 0 = `unix ->0xfff1...`
    while an identical foreground grep took 0.21s.

    The line the fix draws, and why:
      * FIFO — a shell pipeline (`cmd | rmx grep PAT`). bug-062's case. Honour.
      * REG  — an explicit `< file` redirect. Honour.
      * SOCK — neither. Nothing in a pipeline hands a socket to a filter; here
        it is an artifact of how the harness runs a command, and treating it as
        a producer turns every backgrounded `rmx grep` into a hang. Explore.

    A hang is the worst failure shape available to a read command: it cannot be
    distinguished from slow, so it takes the whole turn.
    """
    import socket
    sock_parent, sock_child = socket.socketpair()
    try:
        res = subprocess.run(
            [sys.executable, "-m", "refmatrix.cli", "grep", "hello"],
            stdin=sock_child, capture_output=True, text=True, cwd=str(proj),
            env=_env(proj), timeout=30)
    except subprocess.TimeoutExpired:
        raise AssertionError(
            "rmx grep BLOCKED on a socket stdin — it read fd 0 as a stream "
            "that will never produce data or EOF")
    finally:
        sock_parent.close()
        sock_child.close()

    assert res.returncode == 0, res.stderr
    assert _lines(res.stdout), "a socket-stdin invocation returned nothing"
