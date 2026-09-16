"""bug-043: one stale refinement candidate re-published the whole fleet
snapshot every 30 minutes, forever.

Observed 2026-09-16 13:11 / 13:41 / 14:11 / 14:42 / 15:12 — five identical
`global:queues` alerts with EVERY row clean (`stale_files: 0`, no hot flag).
The publish gate is `if hot or pending_refine`, and one candidate from
2026-09-14 (channel `global:t`, body "hi") had been pending for two days. So a
backlog of one made the alert channel fire on a schedule with nothing
actionable in it — the same alert-fatigue failure the `derive_stale` gate was
designed twice to avoid, missed on the sibling condition.

A hot row is news every tick: it means something is wrong NOW. A pending
candidate is news ONCE: it means something arrived.
"""
from __future__ import annotations

from refmatrix import hub as hub_mod


class _Bus:
    def __init__(self, pending=()):
        self.pending = list(pending)
        self.published = []

    def refinement_queue(self, status):
        return [dict(c) for c in self.pending]

    def publish(self, channel, payload, *, sender, mtype):
        self.published.append((channel, payload))


def _hub(bus, rows):
    class _H:
        pass
    h = _H()
    h.bus = bus
    h._gather_queues = lambda: rows
    return h


_CLEAN = [{"project": "p", "root": "/r", "daemon_up": True, "stale_files": 0}]
_HOT = [{"project": "p", "root": "/r", "daemon_up": True, "stale_files": 7}]


def test_a_new_candidate_alerts_once_and_then_stays_quiet():
    bus = _Bus([{"id": "c1"}])
    h = _hub(bus, _CLEAN)
    assert hub_mod.Hub._queue_alert_once(h) is True
    assert len(bus.published) == 1
    # same backlog, nothing new: a steady queue is not news
    assert hub_mod.Hub._queue_alert_once(h) is False
    assert hub_mod.Hub._queue_alert_once(h) is False
    assert len(bus.published) == 1


def test_a_second_candidate_alerts_again():
    bus = _Bus([{"id": "c1"}])
    h = _hub(bus, _CLEAN)
    hub_mod.Hub._queue_alert_once(h)
    bus.pending.append({"id": "c2"})
    assert hub_mod.Hub._queue_alert_once(h) is True
    assert len(bus.published) == 2
    assert bus.published[-1][1]["refinement_pending"] == 2


def test_a_hot_row_alerts_every_tick():
    """Hot means wrong NOW; repetition is the point, and suppressing it would
    trade one alert-fatigue bug for a missed-incident bug."""
    bus = _Bus()
    h = _hub(bus, _HOT)
    for _ in range(3):
        assert hub_mod.Hub._queue_alert_once(h) is True
    assert len(bus.published) == 3


def test_a_hot_row_alerts_even_when_the_backlog_is_old():
    bus = _Bus([{"id": "c1"}])
    h = _hub(bus, _CLEAN)
    hub_mod.Hub._queue_alert_once(h)          # announces c1
    h._gather_queues = lambda: _HOT
    assert hub_mod.Hub._queue_alert_once(h) is True


def test_draining_and_re_adding_the_same_id_alerts_again():
    """A candidate that was rejected and a later one reusing the id is a new
    arrival, not the old backlog."""
    bus = _Bus([{"id": "c1"}])
    h = _hub(bus, _CLEAN)
    hub_mod.Hub._queue_alert_once(h)
    bus.pending.clear()
    assert hub_mod.Hub._queue_alert_once(h) is False
    bus.pending.append({"id": "c1"})
    assert hub_mod.Hub._queue_alert_once(h) is True


def test_an_empty_clean_fleet_never_alerts():
    bus = _Bus()
    h = _hub(bus, _CLEAN)
    assert hub_mod.Hub._queue_alert_once(h) is False
    assert bus.published == []


def test_the_payload_still_carries_the_count():
    bus = _Bus([{"id": "c1"}, {"id": "c2"}])
    h = _hub(bus, _CLEAN)
    hub_mod.Hub._queue_alert_once(h)
    assert bus.published[0][1]["refinement_pending"] == 2
    assert bus.published[0][1]["queues"] == _CLEAN
