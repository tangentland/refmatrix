"""Task T0.3 + 29.4c: the no-daemon mechanism tests that bug-231's and bug-228's replacements
lean on (`task-29.4-suite-health#r3-bug231`, `#r3-bug228`; AC-6: "the mechanism tests are
green either way").

RED at `c4b44d0`: both import `tests.timing`, which does not exist. Their behavioural halves
characterise code that exists at base (`daemon.graceful_stop`'s poll loop; the generated
recall command's `--timeout 5`); the src mutation that kills the first is "graceful_stop waits
out the whole grace" (the poll count goes from k to hundreds).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from refmatrix import daemon as dm

from tests import task21_1_support as h


def test_bug231_graceful_stop_returns_when_the_pid_is_gone_not_at_the_deadline(
        tmp_path, monkeypatch):
    """No daemon answers here. The pid file names a test-owned child (`sleep`), so the REAL
    `ping` finds no socket and `graceful_stop` sends SIGTERM to that child; only `is_alive` is
    replaced (29.4 #r3-bug231; ch-bsd t03 r1 M2: ping and call are not patched), by a counter
    that turns false on its k-th call. The call must return True after exactly k polls under a
    grace it never comes near (HANG_GUARD_S); a stop that waited out its grace would poll ~20
    times a second until the deadline."""
    import subprocess
    import sys

    from tests.timing import HANG_GUARD_S

    root = tmp_path / ".refmatrix"
    root.mkdir()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    dm.pid_path(root).write_text(str(child.pid))
    k = 4
    polls = {"n": 0}
    real_is_alive = dm.is_alive

    def is_alive(pid):
        if pid != child.pid:
            return real_is_alive(pid)
        polls["n"] += 1
        return polls["n"] < k

    monkeypatch.setattr(dm, "is_alive", is_alive)
    report: dict = {}
    try:
        ok = dm.graceful_stop(root, grace=HANG_GUARD_S, report=report)
        assert ok is True, report
        assert report.get("signal") == "SIGTERM" and report.get("pid") == child.pid, report
        assert polls["n"] == k, polls
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


@pytest.fixture
def root():
    return Path(os.environ["REFMATRIX_ROOT"])


def test_bug228_the_generated_recall_command_carries_the_5s_budget_and_with_budget_swaps_only_it(
        root):
    """The split's no-daemon half: the generated UserPromptSubmit recall command carries the 5 s
    budget, and `with_budget(cmd, HANG_GUARD_S)` changes that one token and nothing else (the
    live half runs the swapped command)."""
    from tests.timing import HANG_GUARD_S, with_budget

    cmd = h.generated_cmd(root, "UserPromptSubmit", "memory recall --stdin-json")
    toks = cmd.split()
    idx = [i for i, t in enumerate(toks) if t == "--timeout"]
    assert len(idx) == 1 and float(toks[idx[0] + 1]) == 5.0, cmd
    out = with_budget(cmd, HANG_GUARD_S).split()
    assert len(out) == len(toks), (cmd, out)
    diff = [i for i, (a, b) in enumerate(zip(toks, out)) if a != b]
    assert diff == [idx[0] + 1] and float(out[idx[0] + 1]) == float(HANG_GUARD_S), (cmd, out)
