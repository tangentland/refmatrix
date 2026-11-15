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
        monkeypatch, tmp_path):
    """No daemon. `is_alive` turns false on its k-th call; the polls are counted, and the call
    returns True after exactly k of them under a grace it never comes near (HANG_GUARD_S). A
    stop that waited out its grace would poll ~20 times a second until the deadline."""
    from tests.timing import HANG_GUARD_S

    k = 4
    polls = {"n": 0}
    sent = []

    def is_alive(pid):
        assert pid == 4_000_001, pid
        polls["n"] += 1
        return polls["n"] < k

    monkeypatch.setattr(dm, "read_pid", lambda root: 4_000_001)
    monkeypatch.setattr(dm, "ping", lambda root, **kw: True)
    monkeypatch.setattr(dm, "call", lambda root, op, args=None, **kw: sent.append(op) or {})
    monkeypatch.setattr(dm, "is_alive", is_alive)
    report: dict = {}
    assert dm.graceful_stop(tmp_path / ".refmatrix", grace=HANG_GUARD_S, report=report) is True
    assert sent == ["stop"] and report.get("stop_op") == "sent", (sent, report)
    assert polls["n"] == k, polls


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
