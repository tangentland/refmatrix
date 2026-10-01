"""The hub reaps its own `global:queues` backlog.

`global:queues` is the hub's 30-minute fleet-health alert. Nothing ever removed
them, so the channel reached 3,044 of the bus's 3,193 active messages — the
channel the hub WRITES drowning every channel an agent reads, including
`proj:refmatrix:bugs`, where two real reports sat unanswered for three days and
two hours. bug-043 stopped the alert REPEATING a steady backlog; it did not
bound the history.

Retention belongs to the producer: the hub publishes these, so the hub reaps
them, on the tick that already wakes to publish. Deliberately scoped to the
hub's own machine-generated channels — a human- or agent-authored bug report on
`proj:*` is never reaped on a timer.
"""
from __future__ import annotations

import time

import pytest

from refmatrix import bus as bus_mod


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A throwaway RMX_HOME so the real `~/.refmatrix/bus/bus.db` is untouched:
    the tests that appended to the live `~/.refmatrix/hub.log` were filed as
    bug-023's family (ch-bsd plan-4 r4 #s-4), and this suite will not repeat it."""
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home"))
    return tmp_path


def _ts(days_ago: float) -> str:
    """The bus writes `time.strftime("%Y-%m-%dT%H:%M:%S")` — LOCAL time, fixed
    width, so `ts < ?` compares lexicographically. A cutoff built any other way
    (UTC, or a different precision) silently compares wrong."""
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() - days_ago * 86400))


def _seed(b, channel: str, days_ago: float, body: str) -> str:
    """Publish, then backdate the row — `publish` always stamps now."""
    msg = b.publish(channel, body, sender="hub")
    con = b._connect()
    try:
        con.execute("UPDATE bus_messages SET ts=? WHERE id=?",
                    (_ts(days_ago), msg["id"]))
        con.commit()
    finally:
        con.close()
    return msg["id"]


# ---- the primitive --------------------------------------------------------

def test_reap_channel_removes_only_rows_older_than_the_window(home):
    b = bus_mod.Bus()
    old = _seed(b, "global:queues", 5, "five days old")
    edge = _seed(b, "global:queues", 3.5, "past the window")
    fresh = _seed(b, "global:queues", 0.5, "twelve hours old")

    out = b.reap_channel("global:queues", older_than_days=3)
    assert out["purged"] == 2, out

    left = [m["id"] for m in b.history("global:queues", n=50)]
    assert fresh in left
    assert old not in left and edge not in left


def test_reap_channel_never_touches_another_channel(home):
    b = bus_mod.Bus()
    report = _seed(b, "proj:refmatrix:bugs", 30, "a month-old bug report")
    _seed(b, "global:queues", 30, "a month-old alert")

    out = b.reap_channel("global:queues", older_than_days=3)
    assert out["purged"] == 1, out
    assert report in [m["id"] for m in b.history("proj:refmatrix:bugs", n=50)], (
        "an agent-authored report was reaped — retention is producer-scoped")


def test_reap_channel_reports_zero_without_raising_on_an_empty_channel(home):
    b = bus_mod.Bus()
    out = b.reap_channel("global:queues", older_than_days=3)
    assert out["purged"] == 0 and out["ok"] is True, out


def test_reap_channel_carries_the_cutoff_it_used(home):
    """The count alone cannot be audited. The hub logs this, so an operator can
    tell 'nothing was old enough' from 'the cutoff was computed wrong'."""
    b = bus_mod.Bus()
    out = b.reap_channel("global:queues", older_than_days=3)
    assert "cutoff" in out and out["cutoff"][:2] == "20", out
    assert len(out["cutoff"]) == len("2026-10-01T10:00:00"), out["cutoff"]


def test_reap_channel_refuses_a_non_positive_window(home):
    """`older_than_days=0` would reap the alert the hub just published. The
    disable switch belongs to the CALLER's config, not to a 0 that silently
    means 'everything'."""
    b = bus_mod.Bus()
    _seed(b, "global:queues", 0.01, "just published")
    with pytest.raises(ValueError):
        b.reap_channel("global:queues", older_than_days=0)
    assert len(b.history("global:queues", n=5)) == 1


# ---- the hub tick --------------------------------------------------------

def test_the_alert_LOOP_reaps_the_channel_it_publishes(home, monkeypatch):
    """Runs the REAL loop, not the method.

    The first version of this test called `_bus_retention_once` directly and
    called itself a wiring test. Mutation G6 — deleting
    `self._bus_retention_once()` from `_queue_alert_loop` — left it GREEN, which
    is precisely the pattern this repo's ledger keeps filing: a helper tested in
    isolation cited as proof that something calls it. So drive the loop: one
    tick, then stop."""
    import threading
    from refmatrix import hub as hub_mod
    seen: list[tuple] = []

    def spy(self, channel, *, older_than_days):
        seen.append((channel, older_than_days))
        return {"ok": True, "purged": 0, "cutoff": _ts(older_than_days)}

    monkeypatch.setattr(bus_mod.Bus, "reap_channel", spy)
    monkeypatch.setattr(hub_mod, "QUEUE_ALERT_INTERVAL_S", 0.01)

    h = object.__new__(hub_mod.Hub)
    h.bus = bus_mod.Bus()
    h._stop = threading.Event()

    def one_tick_then_stop():
        h._stop.set()           # the loop finishes this iteration, then exits
        return False
    monkeypatch.setattr(hub_mod.Hub, "_queue_alert_once",
                        lambda self: one_tick_then_stop())

    hub_mod.Hub._queue_alert_loop(h)
    assert seen == [("global:queues", hub_mod.BUS_RETENTION_DAYS)], (
        f"the alert loop did not reap: {seen}")


def test_retention_is_three_days_by_default(home):
    from refmatrix import hub as hub_mod
    assert hub_mod.BUS_RETENTION_DAYS == 3.0, hub_mod.BUS_RETENTION_DAYS


def test_a_non_positive_retention_setting_disables_the_sweep(home, monkeypatch):
    """`RMX_HUB_BUS_RETENTION_DAYS=0` must disable, matching the shape
    `RMX_HUB_QUEUE_ALERT_INTERVAL<=0` already uses — and it must NOT reach the
    primitive, which rejects a zero window."""
    from refmatrix import hub as hub_mod
    called: list = []
    monkeypatch.setattr(bus_mod.Bus, "reap_channel",
                        lambda *a, **k: called.append(1))
    monkeypatch.setattr(hub_mod, "BUS_RETENTION_DAYS", 0.0)
    h = object.__new__(hub_mod.Hub)
    h.bus = bus_mod.Bus()
    assert hub_mod.Hub._bus_retention_once(h) == 0
    assert called == [], "a disabled sweep still called the primitive"


def test_a_failing_reap_is_logged_not_swallowed(home, monkeypatch):
    """No silent failures between the hub and the bus (CLAUDE.md
    #no-silent-failures). A reap that raises must say so and must not kill the
    alert tick."""
    from refmatrix import hub as hub_mod
    logged: list[str] = []

    def boom(*a, **k):
        raise sqlite_error()

    def sqlite_error():
        import sqlite3
        return sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(bus_mod.Bus, "reap_channel", boom)
    monkeypatch.setattr(hub_mod, "_log", lambda m: logged.append(m))
    h = object.__new__(hub_mod.Hub)
    h.bus = bus_mod.Bus()
    n = hub_mod.Hub._bus_retention_once(h)
    assert n == 0
    assert any("retention" in m and "locked" in m for m in logged), logged
