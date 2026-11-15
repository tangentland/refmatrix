"""Test-side timing primitives that replace wall-clock bounds (task 29.4 R3, T0.3 + 29.4c,
2026-11-15).

Why this module exists: the suite asserted upper bounds on elapsed time (`stop took < 8.0`), and
under load those bounds decided the result, not the behaviour (bug-231: a graceful stop at 10.05 s
and 9.02 s against 8.0; bug-228: a live recall's 5 s budget spent by the embedder's cold load).
29.4 `#r3-rule`: a test does not assert an upper bound on elapsed time; what the bound protected
is asserted directly.

- `HANG_GUARD_S`: the ONE hang guard (plan-29 D14). It is far above any real duration; its only
  job is to turn a hang into a stack trace. The wall-clock census (`tests/wallclock_census.py`)
  exempts `< HANG_GUARD_S` only where the name is imported from here, and fails if this falls
  below 60.
- `wait_for`: class A's replacement. Wait for the OUTCOME under the hang guard; the elapsed time
  goes in the failure message only.
- `with_budget`: the one sanctioned way to run a generated command with its budget replaced
  (29.4 `#r3-bug228`, `#r3-budget-census`). The budget-outcome census matches the call by name,
  so a budget edited into a command any other way (a `str.replace`, an f-string) is not seen and
  fails the census.
"""
from __future__ import annotations

import re
import time
from typing import Callable, TypeVar

T = TypeVar("T")

HANG_GUARD_S = 60.0

# `--timeout <n>` with an int or float value, as the hook generators write it.
_BUDGET_TOKEN = re.compile(r"(?<=--timeout )\d+(?:\.\d+)?(?![\w.])")


def wait_for(predicate: Callable[[], T], *, timeout: float = HANG_GUARD_S,
             interval: float = 0.05, what: str = "the condition") -> T:
    """Poll `predicate` until it returns a truthy value, and return that value.

    At the deadline raise `AssertionError` naming `what` and the elapsed seconds. The deadline is
    a hang guard, never the assertion: a caller asserts the outcome the predicate returns. The
    clock is `time.monotonic()`, so a host sleep cannot make the guard fire early."""
    if timeout <= 0:
        raise ValueError(f"wait_for({what!r}): timeout must be > 0, got {timeout!r}")
    if interval <= 0:
        raise ValueError(f"wait_for({what!r}): interval must be > 0, got {interval!r}")
    t0 = time.monotonic()
    deadline = t0 + timeout
    while True:
        value = predicate()
        if value:
            return value
        now = time.monotonic()
        if now >= deadline:
            raise AssertionError(
                f"timed out waiting for {what}: elapsed {now - t0:.2f} s "
                f"(hang guard {timeout:g} s); last value {value!r}")
        time.sleep(min(interval, max(deadline - now, 0.0)))


def record_transport(monkeypatch, module, name: str = "call") -> list:
    """Class B's replacement (29.4 `#r3-classes`: "assert the mechanism: the timeout value that
    reached the transport, the number of attempts"). Wrap `module.<name>` (a daemon transport
    with the `(root, op, args, *, timeout=, retries=)` shape, `daemon.call` by default) so every
    call is recorded as `{"root", "op", "timeout", "retries"}` and the REAL function still runs:
    the budget path is exercised, only observed. Returns the list the calls are appended to."""
    import inspect

    real = getattr(module, name)
    params = inspect.signature(real).parameters
    defaults = {k: p.default for k, p in params.items()
                if p.default is not inspect.Parameter.empty}
    seen: list = []

    def recording(root, op, *args, **kw):
        seen.append({"root": str(root), "op": op,
                     "timeout": kw.get("timeout", defaults.get("timeout")),
                     "retries": kw.get("retries", defaults.get("retries"))})
        return real(root, op, *args, **kw)

    monkeypatch.setattr(module, name, recording)
    return seen


def assert_one_deadline(calls: list, *, budget: float, root=None, what: str = "") -> list:
    """Class B's assertion over `record_transport`'s list: the calls (to `root`, when given)
    exist, each is ONE attempt (`retries == 0`), and the timeouts that reached the transport sum
    to no more than `budget`, so the budget is one deadline across the calls, not a per-call
    allowance (the 60 s x 3 shape that made `memory get` wait 390 s, bsd-plan3-r4 #b-2).
    Returns the calls it checked."""
    mine = [c for c in calls if root is None or c["root"] == str(root)]
    label = f" ({what})" if what else ""
    assert mine, f"no transport call reached the daemon{label}: {calls}"
    retried = [c for c in mine if c["retries"] != 0]
    assert not retried, f"a budgeted call was allowed retries{label}: {retried}"
    total = sum(float(c["timeout"]) for c in mine)
    assert total <= budget + 1e-6, (
        f"the timeouts that reached the transport sum to {total:.2f} s against a {budget:g} s "
        f"budget{label}: {mine}")
    return mine


def with_budget(command: str, seconds: float) -> str:
    """Return `command` with its one `--timeout <n>` budget value replaced by `seconds`.

    Raises `ValueError` unless exactly one budget token is present: a command with no budget
    would run unbudgeted, and one with two would have only one of them swapped, so either way
    the test would not control which side of the budget its run falls on (29.4 `#r3-bug228`)."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        raise ValueError(f"with_budget: seconds must be a positive number, got {seconds!r}")
    found = _BUDGET_TOKEN.findall(command)
    if len(found) != 1:
        raise ValueError(
            f"with_budget: expected exactly one `--timeout <n>` budget token, found "
            f"{len(found)} in {command!r}")
    value = f"{float(seconds):g}"
    return _BUDGET_TOKEN.sub(value, command, count=1)
