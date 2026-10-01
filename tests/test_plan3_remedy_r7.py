"""bsd-plan3-r7 remedy (round 8): the `skipped` legs must be able to FIRE, and
the bound must cover the leg that costs the time.

Round 7 added two "said, never mute" legs and bounded one of promote's two
RPCs. Both halves were wrong in the same way — they were written against a
failure mode that does not occur:

#b-1  `federated_concept` and `_where_one_project` each wrap exactly one call,
      `_replica_bundle`, whose docstring is "Returns the render_json dict or {}
      on failure" and whose two internal `except Exception: return {}` make that
      true. So neither `except` can ever run, and the symptom round 7 claimed to
      delete still reproduces: an up-classified store with no
      `catalog.read.duckdb` yields `skipped=[]` and `rmx canon find X` answers
      "no live project hosts X", exit 0.

      THE TESTS ARE THE OTHER HALF OF THE DEFECT. Round 7's versions patched
      `_replica_bundle` into raising, so mutations against the `except` legs
      killed a test apiece and the mutation check passed on dead code. Equal
      verdicts on a faked collaborator are not a reproduction. Every test below
      breaks the REAL thing — it deletes the replica catalog off disk — and
      never patches `_replica_bundle`.

#b-2  `rmx memory promote` still costs 180.2 s, r6 #b-2's number to the decimal,
      one leg over: round 8 bounded the project-side READ and left the GLOBAL
      WRITE two lines below at `hub.global_call`'s `timeout=60, retries=2`
      default — the exact cost that function's own docstring says `retries=0`
      exists to prevent.

#m-5  promote is the one twin of four that does not subtract its partition probe
      from the budget: 15.0 s measured against a stated 10 s.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import discovery, search, verbs
from tests.test_plan2_remedy import _PingOnlyDaemon
from tests.test_plan3_remedy_r4 import _snapshot
from tests.test_plan3_remedy_r5 import _no_replica


@pytest.fixture
def up_without_replica():
    """A store whose daemon ANSWERS ping — so `_live_roots` classifies it `up`
    and the fan-out queries it — but which has no `catalog.read.duckdb`, so
    `cached_replica` raises inside `_replica_bundle`.

    This is a real daemon state, not a contrivance: it is the boot window
    `search.cached_replica` wrote a dedicated "no replica catalog to read at …"
    error for. That error's own caller discards it, which is what #b-1 is."""
    d = _PingOnlyDaemon(seeded=True)
    try:
        _no_replica(d.root)
        yield d
    finally:
        d.close()


# ---- #b-1: the skipped legs must fire on the REAL failure ------------------

def test_federated_concept_names_a_store_whose_replica_is_missing(
        up_without_replica, monkeypatch):
    """No patching of `_replica_bundle`. The replica file is gone from disk,
    which is how this fails in production."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [up_without_replica.root])
    out = search.federated_concept("held_row")
    assert out["projects"] == [], out
    assert out["skipped"], (
        "an up store with no replica was dropped silently — the except leg "
        "cannot fire because _replica_bundle returns {} instead of raising")
    reason = " ".join(s.get("reason", "") for s in out["skipped"])
    assert "replica" in reason.lower(), out["skipped"]


def test_federated_where_names_a_store_whose_replica_is_missing(
        up_without_replica, monkeypatch):
    """r6 #s-4's M3 leg, tested against the real failure this time."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [up_without_replica.root])
    monkeypatch.setattr(search, "_live_roots",
                        lambda: ([up_without_replica.root], []))
    out = search.federated_where("held")
    reason = " ".join(s.get("reason", "") for s in out["skipped"])
    assert "replica" in reason.lower(), out["skipped"]


@pytest.mark.timeout(60)
def test_canon_find_does_not_claim_nowhere_when_a_store_could_not_be_read(
        up_without_replica, monkeypatch):
    """The exact sentence #s-3 was written to delete, still reproducing at
    round 7's HEAD: `no live project hosts held_row`, exit 0, no skipped line."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [up_without_replica.root])
    r = CliRunner().invoke(cli_mod.main, ["canon", "find", "held_row"])
    out = r.output
    if "no live project hosts" in out:
        assert "skipped" in out, (
            "told the operator the concept exists NOWHERE while a store could "
            f"not be read, with no skipped line: {out!r}")


def test_replica_bundle_reports_its_failure_to_a_caller_that_asks():
    """The 3-line fix, asserted directly: `_replica_bundle` keeps returning {}
    (every existing caller depends on that) but appends the reason to an
    `on_error` list when one is given. A caller cannot name a failure the callee
    swallows, and no amount of test-side patching changes that."""
    import inspect
    sig = inspect.signature(search._replica_bundle)
    assert "on_error" in sig.parameters, (
        "_replica_bundle has no way to report failure, so both skipped legs "
        "above are unreachable by construction")
    errs: list = []
    out = search._replica_bundle(Path("/nonexistent/.refmatrix"), "x",
                                 on_error=errs)
    assert out == {}, out
    assert errs, "a failing bundle reported nothing to its caller"


# ---- #b-2 / #m-5: the bound must cover the leg that costs the time ---------

@pytest.fixture
def held_global(tmp_path, monkeypatch):
    """A real project store that answers, plus a HELD GLOBAL writer: the global
    daemon answers ping and stalls every op. That is the state that costs
    180.2 s, and it is the half round 7 left unbounded."""
    from refmatrix import hub as hub_mod
    g = _PingOnlyDaemon(seeded=True)
    monkeypatch.setattr(hub_mod, "global_store_root", lambda: g.root)
    try:
        yield g
    finally:
        g.close()


@pytest.mark.timeout(90)
def test_promote_is_bounded_on_the_global_write_too(held_global, tmp_path, monkeypatch):
    """r6 #b-2's number, one leg over: round 7 bounded the project READ and left
    `hub.global_call` at the library default of 60 s x 3.

    The PROJECT read must SUCCEED for the global write to be reached — a first
    draft of this test used a held writer on both sides, promote failed fast on
    the read, and both assertions passed against the unbounded code. The thing
    under test is the global bound, so the global daemon is REAL (socket, held)
    and only the project-side read is answered."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    row = {"id": 7, "name": "held_row", "mtype": "project", "tags": [],
           "metadata": {}, "content": "body"}

    # Dispatch on ROOT. A blanket `monkeypatch.setattr("refmatrix.daemon.call")`
    # also answers the GLOBAL write, because `hub.global_call` routes through the
    # same function — the fake then returns ok:false in 0.00 s, every assertion
    # passes for free, and the test would pass identically against
    # `timeout=10000, retries=99`. That is the #b-1 defect shape reproduced
    # inside the fix for #b-2, and this file caught it once in a first draft and
    # then shipped it again by a different mechanism. Only the PROJECT root is
    # faked; the global side stays on the real held socket.
    import refmatrix.daemon as _dm
    real_call = _dm.call

    def call(root_, op, args=None, **kw):
        if Path(root_) != root:
            return real_call(root_, op, args, **kw)
        if op == "partition_list":
            return {"ok": True, "result": {"rows": [{"name": discovery.store_name(root_)}]}}
        if op == "memory_get":
            return {"ok": True, "result": {"memory": dict(row)}}
        return {"ok": False, "error": f"unexpected {op}"}
    monkeypatch.setattr(discovery, "daemon_status",
                        lambda r, **kw: {"up": True, "busy": False, "pid": 1})
    monkeypatch.setattr(_dm, "call", call)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)

    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
    elapsed = time.monotonic() - t0
    assert r.exit_code != 0, f"the held global store answered? {r.output!r}"
    assert elapsed < 40.0, (
        f"{elapsed:.1f}s — the global write is still unbounded "
        f"(60s x 3 = 180.2s was r6 #b-2's measurement, reproduced at r7)")
    assert held_global.ops.count("memory_add") <= 1, (
        f"retried a write on a stalled global store: {held_global.ops}")


@pytest.mark.timeout(60)
def test_promote_subtracts_its_partition_probe_from_the_budget(monkeypatch):
    """#m-5: the three sibling twins pass `max(0.5, _budget - elapsed)`; promote
    passed the whole budget, so the probe was spent twice over — 15.0 s measured
    against a stated 10 s."""
    # NO `_snapshot()`. With a replica on disk the partition probe is answered
    # from the replica and the 5 s is never spent, so the defect is invisible:
    # measured 10.0 s with a replica (passes) against 15.0 s without (fails),
    # and #m-5 named the state `[ping/replica=False]` explicitly. A test must
    # run in the state the finding measured.
    d = _PingOnlyDaemon(seeded=True)
    try:
        monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
        t0 = time.monotonic()
        CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
        elapsed = time.monotonic() - t0
        assert elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0, (
            f"{elapsed:.1f}s against a stated {verbs.MEMORY_READ_BUDGET_S:g}s — "
            f"the partition probe is not subtracted from the budget")
    finally:
        d.close()


def test_locate_names_a_store_whose_replica_is_missing(
        up_without_replica, monkeypatch):
    """The THIRD caller of `_replica_bundle`, found by sweeping the callers
    instead of fixing the two the finding quoted.

    `_locate_one_project` had no reasons channel at all, so a missing replica
    produced `{}`, `federated_locate` merged nothing, and `rmx locate` printed
    "no matches" with no skipped line — the r3 #b-2 symptom, fixed at the
    fan-out level and still live one frame down. Both of its legs are covered:
    the filename query and the keyword bundle."""
    monkeypatch.setattr(discovery, "discover_roots",
                        lambda: [up_without_replica.root])
    monkeypatch.setattr(search, "_live_roots",
                        lambda: ([up_without_replica.root], []))
    out = search.federated_locate(filename="held.md", keywords=["held"])
    assert out["results"] == [], out
    reason = " ".join(s.get("reason", "") for s in out["skipped"])
    assert reason, (
        "locate dropped an unreadable store silently — its per-project legs "
        "had no way to report, so the fan-out's skipped list never saw them")
    assert "replica" in reason.lower() or "failed" in reason.lower(), out["skipped"]
