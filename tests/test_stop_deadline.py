"""bug-051 (ch-bsd #s-1, 2026-09-16 post-deploy audit): the shutdown stages
each had their own budget and nobody added them up against the supervisor's.

`RMX_DAEMON_FLUSH_BUDGET_S` went 5 -> 15 in the bug-041 remedy, which put the
degraded stop at `10+10+10` (three pool drains) `+ 3+3+3+3` (thread joins)
`+ 15` (flush) `+ 5` (store close) = **59 s** against launchd's
`ExitTimeOut = 45`. Past ExitTimeOut launchd SIGKILLs, and a SIGKILL mid-close
is the documented cause of the entities ART-index corruption and the
2026-09-14 crash loop. The two stops bug-041 reproduced (39 s and 38 s) both
fitted inside 45 before the bump and both crossed it after.

The fix is not a smaller constant: it is ONE deadline that every stage spends
from, so no arithmetic has to be re-done by hand when a stage budget moves.
"""
from __future__ import annotations

import pytest

from refmatrix import daemon as dm
from refmatrix.launchctl import EXIT_TIMEOUT_S


class _Clock:
    """Deterministic monotonic: tests advance it, nothing sleeps."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _daemon(tmp_path):
    d = dm.Daemon(tmp_path / ".refmatrix")
    d._log = lambda m: d.__dict__.setdefault("_logs", []).append(m)
    return d


def _logs(d):
    return d.__dict__.get("_logs", [])


# ---- the deadline itself -------------------------------------------------

def test_a_fresh_deadline_grants_a_stage_its_full_budget():
    clock = _Clock()
    dl = dm._StopDeadline(EXIT_TIMEOUT_S, now=clock)
    assert dl.budget(10.0) == pytest.approx(10.0)


def test_a_stage_never_gets_more_than_is_left_of_the_supervisors_deadline():
    clock = _Clock()
    dl = dm._StopDeadline(EXIT_TIMEOUT_S, margin_s=2.0, now=clock)
    clock.advance(40.0)                       # 45 - 2 - 40 = 3 s left
    assert dl.budget(10.0) == pytest.approx(3.0)


def test_a_stage_reserves_room_for_the_stages_after_it():
    """A drain that spends the store-close budget strands the catalog lock —
    the reserve is what keeps close() inside the deadline."""
    clock = _Clock()
    dl = dm._StopDeadline(EXIT_TIMEOUT_S, margin_s=2.0, now=clock)
    clock.advance(35.0)                       # 8 s left, 5 of them owed to close
    assert dl.budget(10.0, reserve=5.0) == pytest.approx(3.0)


def test_an_exhausted_deadline_grants_zero_not_a_negative_budget():
    clock = _Clock()
    dl = dm._StopDeadline(EXIT_TIMEOUT_S, margin_s=2.0, now=clock)
    clock.advance(60.0)
    assert dl.left() == 0.0
    assert dl.budget(10.0) == 0.0
    assert dl.budget(10.0, reserve=5.0) == 0.0


def test_the_whole_degraded_stop_fits_inside_exit_timeout():
    """The #s-1 arithmetic, walked stage by stage with every stage timing out.

    Before the fix this sums to 59 s. With one deadline it cannot exceed
    ExitTimeOut, whatever the individual stage constants say.
    """
    clock = _Clock()
    start = clock.t
    dl = dm._StopDeadline(EXIT_TIMEOUT_S, margin_s=2.0, now=clock)
    close_reserve = 5.0

    # watcher join, three pool drains, four periodic-thread joins
    stages = [3.0, 10.0, 10.0, 10.0, 3.0, 3.0, 3.0]
    for want in stages:
        clock.advance(dl.budget(want, reserve=close_reserve))
    # the final flush keeps the close reserve back
    clock.advance(dl.budget(15.0, reserve=close_reserve))
    # the bounded store close spends what is left, up to its own budget
    clock.advance(dl.budget(close_reserve))

    assert clock.t - start <= EXIT_TIMEOUT_S, (
        f"stop took {clock.t - start:.1f}s against ExitTimeOut {EXIT_TIMEOUT_S:g}s")


@pytest.mark.parametrize("observed", [39.0, 38.0])
def test_the_two_reproduced_incidents_no_longer_cross_the_kill_line(observed):
    """bug-041's own log: 09:50:24 -> 09:51:03 (39 s) and 11:32:28 -> 11:33:06
    (38 s). With a flat 15 s flush both become 49 s / 48 s — over 45."""
    clock = _Clock()
    dl = dm._StopDeadline(EXIT_TIMEOUT_S, margin_s=2.0, now=clock)
    clock.advance(observed)
    flush = dl.budget(15.0, reserve=5.0)
    close = dl.budget(5.0)
    assert observed + flush + close <= EXIT_TIMEOUT_S


def test_the_deadline_honours_a_shortened_stop_grace(monkeypatch):
    """`RMX_STOP_GRACE_S` is the one number every supervisor reads (r3 #b-1);
    a daemon stopped on a shorter grace must shrink its stages to match."""
    monkeypatch.setenv("RMX_STOP_GRACE_S", "12")
    clock = _Clock()
    dl = dm._StopDeadline(dm.stop_grace_s(), margin_s=2.0, now=clock)
    assert dl.budget(10.0, reserve=5.0) == pytest.approx(5.0)


# ---- the flush stage reads the deadline ---------------------------------

def test_final_flush_says_why_it_skipped_when_the_budget_is_gone(tmp_path):
    """A skipped flush is the 'relational tables ahead of the bitmaps' surface
    that wedged viascope. Skipping it silently is the failure this repo bans."""
    d = _daemon(tmp_path)
    d.store = object()                     # never touched; the budget is 0
    assert d._final_flush(budget_s=0.0) is False
    line = next((m for m in _logs(d) if "final flush skipped" in m), None)
    assert line is not None, f"no line named the skipped flush: {_logs(d)}"
    assert "budget" in line and "stop" in line.lower(), line


def test_final_flush_derives_its_budget_from_elapsed_stop_time(tmp_path):
    """Called with how long the stop has already taken, the flush works out
    its own share instead of trusting a constant."""
    d = _daemon(tmp_path)
    d.store = object()
    assert d._final_flush(elapsed_s=EXIT_TIMEOUT_S) is False
    assert any("final flush skipped" in m for m in _logs(d)), _logs(d)


def test_the_flush_budget_is_capped_by_its_env_ceiling(monkeypatch):
    monkeypatch.setenv("RMX_DAEMON_FLUSH_BUDGET_S", "4")
    assert dm.remaining_flush_budget_s(0.0) == pytest.approx(4.0)


def test_the_flush_budget_shrinks_as_the_stop_drags(monkeypatch):
    monkeypatch.delenv("RMX_DAEMON_FLUSH_BUDGET_S", raising=False)
    full = dm.remaining_flush_budget_s(0.0)
    late = dm.remaining_flush_budget_s(35.0)
    assert late < full
    assert dm.remaining_flush_budget_s(EXIT_TIMEOUT_S) == 0.0
