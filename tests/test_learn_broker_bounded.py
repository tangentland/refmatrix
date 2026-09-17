"""bug-049: the "fire-and-forget" learn ping blocked the CLI for 30 seconds.

`rmx grep` renders its hits and THEN brokers them to the daemon's
`learn_from_grep` writer. That broker passed `timeout=10.0` and inherited
`daemon.call`'s default `retries=2`, so three attempts plus backoff cost
10+10+10+0.05+0.10 = **30.15 s** whenever the daemon could not answer a WRITE
op in 10 s — measured directly against a socket that accepts and never replies:

    call(timeout=10.0)             -> 30.16s
    call(timeout=10.0, retries=0)  -> 10.00s

That is the wall in the telemetry: 104 of 1,165 `grep-replica` calls pinned at
30,178-30,222 ms, rising to 17% of calls on 2026-09-16. Every one of them had
already PRINTED its results; the user waited half a minute for a background
graph update, and `except Exception: pass` meant nothing ever said so.

Three call sites shared the defect (the context backstop at `timeout=30.0` was
worst at 90.15 s worst-case), so the fix is one helper all three use.
"""
from __future__ import annotations

import pathlib
import socket
import threading
import time

import pytest

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm


@pytest.fixture
def deaf_daemon():
    """A socket that accepts connections and never answers — the shape of a
    daemon busy holding `_store_lock` for a write.

    A SHORT mkdtemp root, not `tmp_path`: macOS caps `sun_path` at ~104 bytes
    and pytest's tmp_path blows straight past it."""
    import shutil, tempfile
    td = pathlib.Path(tempfile.mkdtemp(prefix="rmxL"))
    root = td / ".refmatrix"
    root.mkdir()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(dm.socket_path(root)))
    srv.listen(8)
    held = []

    def _accept():
        while True:
            try:
                c, _ = srv.accept()
                held.append(c)
            except OSError:
                return

    threading.Thread(target=_accept, daemon=True).start()
    yield root
    srv.close()
    for c in held:
        try:
            c.close()
        except OSError:
            pass
    shutil.rmtree(td, ignore_errors=True)


def test_the_learn_broker_is_bounded_well_under_the_old_wall(deaf_daemon, capsys):
    t0 = time.monotonic()
    cli_mod._broker_learn_from_grep(
        deaf_daemon, "somepattern", [{"file": "a.py", "line": 1}])
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, (
        f"the learn broker blocked {elapsed:.1f}s; it runs AFTER the results "
        f"are printed and must never be the reason a read feels slow")


def test_a_failed_learn_is_reported_not_swallowed(deaf_daemon, capsys, monkeypatch):
    """`except Exception: pass` on the graph-learning path is exactly the
    silence CLAUDE.md#no-silent-failures forbids: the index quietly stops
    learning and the only symptom is that retrieval gets worse over time.

    The case that must speak is a daemon that ANSWERED the ping and then
    failed the write — i.e. a live daemon whose writer is wedged. A ping that
    simply finds no daemon is the ordinary no-daemon case and stays quiet, or
    every grep outside a running store would nag."""
    monkeypatch.setattr(dm, "ping", lambda *a, **k: True)
    # want_result=True is the remaining RPC path (the caller reports what was
    # learned); the default path queues and cannot fail this way.
    cli_mod._broker_learn_from_grep(
        deaf_daemon, "somepattern", [{"file": "a.py", "line": 1}],
        want_result=True)
    err = capsys.readouterr().err
    assert "learn" in err.lower(), f"the dropped learn said nothing: {err!r}"


def test_no_daemon_at_all_stays_quiet(deaf_daemon, capsys, monkeypatch):
    """The common case must not nag: no daemon is not a failure."""
    monkeypatch.setattr(dm, "ping", lambda *a, **k: False)
    cli_mod._broker_learn_from_grep(
        deaf_daemon, "somepattern", [{"file": "a.py", "line": 1}])
    assert capsys.readouterr().err == ""


def test_the_broker_never_retries_a_write(deaf_daemon, monkeypatch):
    """A learn is best-effort. Retrying a WRITE three times multiplies the
    cost of the exact condition that made it fail — a busy writer."""
    seen = {}

    def _spy(root, op, args=None, **kw):
        seen["retries"] = kw.get("retries")
        seen["timeout"] = kw.get("timeout")
        raise TimeoutError("busy")

    monkeypatch.setattr(dm, "call", _spy)
    monkeypatch.setattr(dm, "ping", lambda *a, **k: True)
    cli_mod._broker_learn_from_grep(
        deaf_daemon, "p", [{"file": "a.py", "line": 1}], want_result=True)
    assert seen.get("retries") == 0, f"broker retried a write: {seen}"
    assert seen.get("timeout", 99) <= 5.0, f"broker budget too generous: {seen}"


def test_no_hits_does_not_touch_the_daemon(deaf_daemon, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(dm, "call", lambda *a, **k: called.__setitem__("n", 1))
    cli_mod._broker_learn_from_grep(deaf_daemon, "p", [])
    assert called["n"] == 0


def test_the_default_path_queues_instead_of_calling_the_daemon(deaf_daemon, monkeypatch):
    """bug-049 part 2: the read path stops asking for a write at all. N greps
    become one batched write on the daemon's flush tick."""
    from refmatrix import learn_queue as lq

    def _boom(*a, **k):
        raise AssertionError("the default learn path called the daemon")

    monkeypatch.setattr(dm, "call", _boom)
    t0 = time.monotonic()
    ok = cli_mod._broker_learn_from_grep(
        deaf_daemon, "somepattern", [{"file": "a.py", "line": 1}])
    elapsed = time.monotonic() - t0

    assert ok is True
    assert elapsed < 0.5, f"queuing took {elapsed:.2f}s; it is one append"
    assert lq.pending_lines(deaf_daemon) == 1
