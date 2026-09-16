"""bug-030 — the fleet waits longer to QUALIFY a worker than it allows for work.

The registry blamed a probe leaking its short timeout onto the persistent
socket. That mechanism cannot produce the observed symptom and was already
closed:

  * `d576a81` (2026-09-15 03:28) added the `finally` restore in
    `SharedWorkerClient.call`, covered by
    `test_a_timed_probe_does_not_shorten_the_next_call`.
  * `PROBE_TIMEOUT_S` is 45 and `SHARED_OP_TIMEOUT_S` is 30, so a leaked
    probe timeout would have made the next call LONGER, not shorter. It
    cannot yield a death at 30.8 s.
  * 30.8 s is the op budget itself.

The real defect is a pair of constants that each have a guard while their
RELATIONSHIP has none: `test_bug015_wedge` pins `PROBE_TIMEOUT_S >= 40.0`
with the comment "measured warm: embed 14.9 s, rerank 33 s", and separately
allows `SHARED_OP_TIMEOUT_S` anywhere in 5..60. So the project records that a
cold rerank takes 33 s and still permits a 30 s budget for the work.
"""

from __future__ import annotations

from refmatrix import daemon as dm
from refmatrix import modelsrv


# The figure the codebase itself measured on 2026-09-15 and wrote into
# `modelsrv.PROBE_TIMEOUT_S`'s docstring. Named once, asserted against, so a
# future edit to one budget cannot silently fall below it.
MEASURED_COLD_LOAD_S = 33.0


def test_the_work_budget_is_never_smaller_than_the_qualifying_budget():
    """If the fleet will wait `PROBE_TIMEOUT_S` to decide a worker is USABLE,
    it must wait at least that long for the worker to do the work. The
    inverted pair is what killed a 4h23m LongMemEval build at 30.8 s."""
    assert dm.SHARED_OP_TIMEOUT_S >= modelsrv.PROBE_TIMEOUT_S, (
        f"op budget {dm.SHARED_OP_TIMEOUT_S}s < probe budget "
        f"{modelsrv.PROBE_TIMEOUT_S}s: a worker that qualifies cannot deliver")


def test_the_work_budget_covers_a_measured_cold_load():
    """A cold worker loads its model inside the FIRST call. A budget under the
    measured cold load makes that call fail by construction."""
    assert dm.SHARED_OP_TIMEOUT_S >= MEASURED_COLD_LOAD_S, (
        f"op budget {dm.SHARED_OP_TIMEOUT_S}s < measured cold load "
        f"{MEASURED_COLD_LOAD_S}s (rerank, 2026-09-15)")


def test_the_probe_budget_still_covers_a_cold_load():
    """The other half of the pair, so raising one cannot lower the other."""
    assert modelsrv.PROBE_TIMEOUT_S >= MEASURED_COLD_LOAD_S


def test_the_op_budget_still_bounds_a_wedged_worker():
    """The op budget exists so a mute worker cannot hold a daemon for the
    300 s default (bug-015). Raising it must not discard that bound."""
    from refmatrix.subproc import DEFAULT_TIMEOUT_S
    assert dm.SHARED_OP_TIMEOUT_S < DEFAULT_TIMEOUT_S


def test_the_daemon_hands_its_client_the_op_budget(tmp_path, monkeypatch):
    """The invariant is worthless if the constant is not what reaches the
    client. Pinned end to end, not just as a number in a module."""
    seen = {}

    class _Client:
        def __init__(self, role, *, log=None, timeout=None):
            seen["timeout"] = timeout

        def info(self, *, timeout=None):
            seen["probe"] = timeout
            return {"model": "x"}

    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", _Client)
    d = dm.Daemon(tmp_path / ".refmatrix")
    d._log = lambda msg: None
    d._model_client("rerank")
    assert seen["timeout"] == dm.SHARED_OP_TIMEOUT_S
    assert seen["probe"] == modelsrv.PROBE_TIMEOUT_S
    assert seen["timeout"] >= seen["probe"], (
        "the daemon qualified the worker on a budget it will not grant the work")
