"""bug-267 (ruling L151): stopping an in-process daemon must not end its host process.

WHY. `Daemon.serve_forever` always finished with `os._exit(0)` (`daemon.py` ~2220 at
c4b44d0): a belt-and-braces force exit so that `concurrent.futures`' atexit join of the pool
workers `_drain_pool` leaked cannot pin a daemon process alive holding DuckDB's file lock. That
is right for a daemon PROCESS, and wrong for a `Daemon` served on a thread inside another
process. T0.2's reaper stops a leaked in-process daemon through the weak `Daemon` registry
(ruling L142), and green-t02 measured the result (`green-wip-reaper-1.log`): the host pytest
died with exit 0 before printing its summary -- a failing session reported as passing.

What is pinned here:
- (1) In a CHILD pytest session (`tests/fixtures/suite_health/case_inprocess_stop.py`, run in a
  throwaway checkout with this checkout's conftest), a REAL in-process daemon serving on a
  non-main thread with no `signal.signal` double (ch-bsd T0.2 r1 B1, ruling L169) answers a
  ping and is stopped through the `stop` op, and another through the `_stop` flag. The
  session survives both, runs its third, deliberately failing test, prints its summary line,
  and exits with ITS OWN status (1). It finishes within the hang guard: no hang at interpreter
  shutdown from leaked pool workers.
- (2) Guards: a real daemon PROCESS still exits when stopped through the `stop` op, with no
  signal sent -- the detached one (`spawn_daemon_subprocess`, `rmx daemon start`) and the
  foreground one launchd runs (`rmx daemon start --no-detach`, `serve_foreground`). Its pid is
  gone within the deadline. They check only that the stop op alone ends a daemon process; no
  guard plants a leaked pool worker, so they do not show that the force exit is what ends it
  (ch-bsd T0.2 r1 MEH-2: mutation X4, `in_host` forced True, survives them).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix.store import Store

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_daemon_reaper import _alive, _inner_cmd, _inner_env, _inner_tree  # noqa: E402

# Hang guards, not bounds under test: the child boots two in-process daemons (~10-30 s idle);
# a daemon's stop drains its pools within its own grace.
_CHILD_HANG_GUARD_S = 420.0
_GONE_DEADLINE_S = 120.0


def _gone(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


# ---- (1) the in-process daemon ---------------------------------------------------------------

_STOP_TESTS = ("test_the_stop_op_ends_the_serve_thread_not_the_process",
               "test_the_stop_flag_ends_the_serve_thread_not_the_process")
_DELIBERATE = "test_zz_the_session_keeps_its_own_status"


def _first_e_line(out: str, test: str) -> str:
    """The first `E ` line of `test`'s section in the child's FAILURES / ERRORS output."""
    m = re.search(rf"^_+ (?:ERROR at \w+ of )?{re.escape(test)} _+$", out, re.M)
    if m is None:
        return "(no failure section)"
    nxt = re.search(r"^(_{3,} .* _{3,}|=+ .* =+)$", out[m.end():], re.M)
    body = out[m.end():m.end() + nxt.start()] if nxt else out[m.end():]
    return next((ln.strip() for ln in body.splitlines() if ln.startswith("E ")), "(no E line)")


def test_bug267_stopping_an_in_process_daemon_leaves_the_session_its_own_status(tmp_path):
    tree = _inner_tree(tmp_path, "case_inprocess_stop")
    info = tmp_path / "case-info.json"
    try:
        try:
            r = subprocess.run(_inner_cmd(), cwd=str(tree), env=_inner_env(info),
                               capture_output=True, text=True, timeout=_CHILD_HANG_GUARD_S)
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) \
                else (e.stdout or "")
            pytest.fail(f"the child session did not finish within {_CHILD_HANG_GUARD_S} s "
                        "after its in-process daemons were stopped (a hang at interpreter "
                        "shutdown: leaked pool workers joined by atexit?)\n" + out[-3000:])
        out = (r.stdout or "") + (r.stderr or "")
        # Judged by WHICH test failed, from the child's `-rA` outcome lines, never by E-line
        # text: pytest prints two E lines for the deliberate `assert False, "deliberate: …"`
        # (the message and `assert False`), and a text filter kept one of them on correct code
        # (lead, 2026-11-15, green-l169-red-nodes.log at be7ddb2). The two stop tests must
        # PASS and only the deliberate test may fail; a stop test that failed is named by the
        # first E line of its own section (at 1121b4e: the serve thread's ValueError).
        outcomes = dict((m.group(2), m.group(1)) for m in re.finditer(
            r"^(PASSED|FAILED|ERROR) tests/test_case\.py::(\w+)", out, re.M))
        bad = {t: outcomes.get(t, "no outcome") for t in _STOP_TESTS
               if outcomes.get(t) != "PASSED"}
        if outcomes and bad:
            why = {t: _first_e_line(out, t) for t in bad}
            pytest.fail(
                f"the child's in-process daemon tests did not pass (exit {r.returncode}): "
                + "; ".join(f"{t}: {o}: {why[t]}" for t, o in bad.items()) + "\n"
                + out[-3000:])
        others = {t: o for t, o in outcomes.items()
                  if t not in _STOP_TESTS and t != _DELIBERATE and o != "PASSED"}
        assert not others, f"unexpected child outcomes {others}:\n{out[-3000:]}"
        assert not outcomes or outcomes.get(_DELIBERATE) == "FAILED", (
            f"the deliberate test did not fail ({outcomes.get(_DELIBERATE)}):\n{out[-3000:]}")
        summary = re.search(r"^=+ .*\b1 failed, 2 passed\b.* =+$", out, re.M)
        assert summary is not None, (
            f"the child session never printed its summary (exit {r.returncode}): stopping an "
            "in-process daemon ended the HOST process (Daemon.serve_forever's os._exit, "
            "bug-267)\n" + out[-3000:])
        assert r.returncode == pytest.ExitCode.TESTS_FAILED, (
            f"the child session exited {r.returncode}, not its own status "
            f"{int(pytest.ExitCode.TESTS_FAILED)} (one test fails on purpose)\n" + out[-3000:])
    finally:
        if info.is_file():
            for b in json.loads(info.read_text()).get("bases", []):
                shutil.rmtree(b, ignore_errors=True)


# ---- (2) guards: a daemon PROCESS still exits when stopped ----------------------------------

@pytest.fixture
def store_base():
    base = Path(tempfile.mkdtemp(prefix="b267-", dir=os.environ["RMX_SANDBOX_ROOT"])).resolve()
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    try:
        s.init()
    finally:
        s.close()
    yield root
    pid = dm.read_pid(root)
    if pid and _alive(pid):
        os.kill(pid, signal.SIGKILL)
    shutil.rmtree(base, ignore_errors=True)


def test_bug267_guard_a_detached_daemon_process_exits_on_the_stop_op(store_base):
    """`rmx daemon start` (detached, `spawn_daemon_subprocess`): the stop op alone, no signal,
    ends the process within the deadline."""
    root = store_base
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid > 0 and dm.ping(root)
    dm.call(root, "stop", {}, retries=0)
    assert _gone(pid, _GONE_DEADLINE_S), (
        f"the detached daemon {pid} was asked to stop and is still alive after "
        f"{_GONE_DEADLINE_S} s: its process no longer exits once serve_forever returns")


def test_bug267_guard_a_foreground_daemon_process_exits_on_the_stop_op(store_base):
    """`rmx daemon start --no-detach` (`serve_foreground`, launchd's path): the stop op alone
    ends the process within the deadline, and the process exits 0."""
    root = store_base
    env = dict(os.environ, REFMATRIX_ROOT=str(root))
    p = subprocess.Popen([sys.executable, "-m", "refmatrix.cli", "daemon", "start",
                          "--no-detach", "--no-watch"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + _GONE_DEADLINE_S
        while not dm.ping(root, retries=0) and time.monotonic() < deadline \
                and p.poll() is None:
            time.sleep(0.2)
        assert dm.ping(root, retries=0), (
            f"the foreground daemon never answered (exit {p.poll()}): "
            + (p.stderr.read().decode(errors="replace")[-2000:] if p.poll() is not None
               else ""))
        dm.call(root, "stop", {}, retries=0)
        try:
            code = p.wait(timeout=_GONE_DEADLINE_S)
        except subprocess.TimeoutExpired:
            pytest.fail(f"the foreground daemon {p.pid} was asked to stop and is still alive "
                        f"after {_GONE_DEADLINE_S} s")
        assert code == 0, f"the foreground daemon exited {code}"
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        p.stderr.close()
