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


def test_a_hot_row_alerts_once_not_every_tick():
    """SUPERSEDED CONTRACT (bug-048 / ch-bsd #s-3).

    This test used to assert the opposite — "hot means wrong NOW; repetition is
    the point" — and that argument was made without ever measuring the firing
    rate. The rate refuted it: 37 of 60 live `global:queues` messages carried a
    hot row, and this project sat at `stale_files: 37` for 23 consecutive ticks
    (13 h 47 m) of byte-identical alerts. Repetition was not conveying "still
    wrong"; it was training the reader to ignore the channel, which is the
    missed-incident bug the old contract claimed to prevent.

    The incident is still announced immediately, and re-asserted on a long
    cycle — see `test_a_persistent_incident_is_re_asserted_eventually`.
    """
    bus = _Bus()
    h = _hub(bus, _HOT)
    assert hub_mod.Hub._queue_alert_once(h) is True
    for _ in range(2):
        assert hub_mod.Hub._queue_alert_once(h) is False
    assert len(bus.published) == 1


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


# ---- bug-048 (ch-bsd #s-3): the sibling operand had the same defect --------
#
# bug-043 changed `pending_refine` to `new_refine` and left `hot` alone, in the
# commit whose message is about checking sibling conditions. Measured on the
# live bus afterwards: 37 of 60 `global:queues` messages carried a hot row, and
# on 2026-09-15 this project's row sat at `stale_files: 37` for 23 CONSECUTIVE
# ticks — 09:49:47 to 23:37:02, 13 h 47 m of identical 30-minute alerts.
#
# A steady, unchanging stale count is not an incident recurring every 30
# minutes. It is ONE incident. The hot branch gets the same treatment the
# refinement branch got: announce on arrival and on change, re-assert rarely.

def _tick(h):
    return hub_mod.Hub._queue_alert_once(h)


def test_an_unchanging_hot_row_does_not_alert_every_tick():
    bus = _Bus()
    rows = [{"project": "refmatrix", "stale_files": 37}]
    h = _hub(bus, rows)

    assert _tick(h) is True, "the first hot tick must alert — it is news"
    fired = [_tick(h) for _ in range(23)]      # the observed 23-tick stretch
    assert not any(fired), (
        f"an unchanging hot row alerted {sum(fired)} more times; that is "
        f"bug-043's own failure on the sibling operand")
    assert len(bus.published) == 1


def test_a_new_store_going_hot_is_news():
    bus = _Bus()
    rows = [{"project": "refmatrix", "stale_files": 37}]
    h = _hub(bus, rows)
    assert _tick(h) is True
    assert _tick(h) is False

    rows.append({"project": "cliquedb", "stale_files": 4})
    assert _tick(h) is True, "a second store going hot is a new incident"


def test_a_row_that_gets_materially_worse_is_news():
    bus = _Bus()
    rows = [{"project": "refmatrix", "stale_files": 10}]
    h = _hub(bus, rows)
    assert _tick(h) is True
    assert _tick(h) is False

    rows[0]["stale_files"] = 400        # an order of magnitude worse
    assert _tick(h) is True, "a material escalation must not be suppressed"


def test_small_jitter_in_a_steady_backlog_is_not_news():
    """37 -> 38 -> 36 is the same incident breathing, not three incidents."""
    bus = _Bus()
    rows = [{"project": "refmatrix", "stale_files": 37}]
    h = _hub(bus, rows)
    assert _tick(h) is True
    for n in (38, 36, 39, 37):
        rows[0]["stale_files"] = n
        assert _tick(h) is False, f"jitter to {n} re-alerted"


def test_a_hot_row_that_clears_and_returns_is_news_again():
    bus = _Bus()
    rows = [{"project": "refmatrix", "stale_files": 5}]
    h = _hub(bus, rows)
    assert _tick(h) is True
    rows[0]["stale_files"] = 0
    assert _tick(h) is False            # clean tick: nothing to say
    rows[0]["stale_files"] = 5
    assert _tick(h) is True, "it came back — that is a new incident"


def test_a_persistent_incident_is_re_asserted_eventually(monkeypatch):
    """Suppression must not become amnesia: a still-broken fleet says so again
    on a long cycle, not on the 30-minute tick."""
    bus = _Bus()
    rows = [{"project": "refmatrix", "stale_files": 37}]
    h = _hub(bus, rows)
    assert _tick(h) is True
    assert _tick(h) is False

    # Walk the clock past the re-assert interval.
    now = [hub_mod.time.time() + hub_mod.HOT_REASSERT_S + 1]
    monkeypatch.setattr(hub_mod.time, "time", lambda: now[0])
    assert _tick(h) is True, "a persistent incident must be re-asserted"
    assert _tick(h) is False, "…and then go quiet again"
