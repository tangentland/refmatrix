"""Task 29.4c R3 (`task-29.4-suite-health#r3-classes`, `#r3-bug228`, `#files-table`): the
helpers in `tests/timing.py` that replace wall-clock bounds.

RED at `c4b44d0`: `tests/timing.py` does not exist.

Contract pinned for GREEN:
- `HANG_GUARD_S`: one number, >= 60 s (plan-29 D14: far above any real duration; its only job
  is to turn a hang into a stack trace);
- `wait_for(predicate, *, timeout=HANG_GUARD_S, interval=..., what="...")`: polls until the
  predicate is truthy and returns that value; at the deadline it raises `AssertionError` whose
  message names `what` and the elapsed seconds (class A: the time goes in the message only);
- `with_budget(command, seconds)`: the generated command with its one `--timeout <n>` value
  replaced by `seconds`; raises unless it replaced exactly one token (29.4 #r3-bug228).
"""
from __future__ import annotations

import re

import pytest


def _t():
    from tests import timing
    return timing


def test_hang_guard_is_one_number_of_at_least_60_seconds():
    t = _t()
    assert isinstance(t.HANG_GUARD_S, (int, float)) and not isinstance(t.HANG_GUARD_S, bool)
    assert t.HANG_GUARD_S >= 60, t.HANG_GUARD_S


def test_wait_for_returns_the_predicates_value_as_soon_as_it_holds():
    calls = {"n": 0}

    def ready():
        calls["n"] += 1
        return "row" if calls["n"] == 3 else None

    assert _t().wait_for(ready, interval=0.01, what="the row") == "row"
    assert calls["n"] == 3, calls


def test_wait_for_raises_at_its_deadline_naming_what_and_the_elapsed_time():
    with pytest.raises(AssertionError) as ei:
        _t().wait_for(lambda: False, timeout=0.2, interval=0.02, what="the pid to exit")
    msg = str(ei.value)
    assert "the pid to exit" in msg, msg
    m = re.search(r"(\d+(?:\.\d+)?)\s*s", msg)
    assert m and float(m.group(1)) >= 0.2, msg


def _tokens(cmd: str) -> list:
    return cmd.split()


def test_with_budget_replaces_the_one_timeout_value():
    cmd = "export X=1; rmx memory recall --stdin-json --k 12 --pack --timeout 5"
    out = _t().with_budget(cmd, 60.0)
    a, b = _tokens(cmd), _tokens(out)
    assert len(a) == len(b), (cmd, out)
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert diff == [len(a) - 1], (cmd, out)
    assert float(b[-1]) == 60.0, out


def test_with_budget_raises_when_there_is_no_budget_token():
    with pytest.raises((ValueError, AssertionError)):
        _t().with_budget("rmx memory recall --stdin-json --pack", 60.0)


def test_with_budget_raises_when_there_are_two_budget_tokens():
    with pytest.raises((ValueError, AssertionError)):
        _t().with_budget("rmx a --timeout 5 && rmx b --timeout 5", 60.0)
