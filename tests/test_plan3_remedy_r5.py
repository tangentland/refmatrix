"""bsd-plan3-r5 remedy (round 6 of plan 3): the bound lives in the verb and
the CLI twins must CALL it; a read never goes to the write proxy; a fan-out
says what it skipped.

#b-1  `rmx memory list` / `rmx memory search` waited 190 s on a held writer
      (bare `ping` gate → `_memory_daemon_call` at 60 s × 3) while the
      replica held the rows. Both twins route through `verbs.memory(...)`
      with the `get` twin's busy → replica fallthrough.
#s-2  On a held writer WITHOUT a replica the twins said "reading the
      replica" and then died on the write proxy's reader error. `_read_store`
      raises the one read-worded error when the daemon is up and there is
      no replica; "reading the replica" is printed only after a replica
      opened.
#s-3  `federated_query` waited 60 s on a held store and dropped it from both
      `projects` and `skipped`; the pooled fan-outs abandoned stragglers
      silently. Every fan-out names the store and why.
#m-4  the recall twin passes the partition it already resolved (one
      `partition_list` probe per command, like `get`).
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery, search, verbs
from tests.test_plan2_remedy import _PingOnlyDaemon
from tests.test_plan3_remedy_r4 import _snapshot
from tests.timing import assert_one_deadline, record_transport


@pytest.fixture
def held():
    d = _PingOnlyDaemon(seeded=True)
    try:
        yield d
    finally:
        d.close()


@pytest.fixture
def held_replica(held):
    _snapshot(held.root)
    return held


def _no_replica(root: Path) -> None:
    """Rotation layout before the first snapshot: the held writer's slot and
    the `active` marker only — nothing lock-free to read."""
    (root / "catalog.duckdb").rename(root / "catalog.A.duckdb")
    (root / "active").write_text("A")
    for name in ("catalog.read.duckdb", "read_only.duckdb"):
        p = root / name
        if p.exists() or p.is_symlink():
            p.unlink()


# ---- #b-1 the list/search twins call the verb ----------------------------------------

@pytest.mark.timeout(40)
@pytest.mark.parametrize("argv", [["memory", "list", "--limit", "3"],
                                  ["memory", "search", "held"]])
def test_list_and_search_twins_reach_the_replica_within_the_budget_on_a_held_writer(
        held_replica, monkeypatch, argv):
    monkeypatch.setattr(cli_mod, "_root", lambda: held_replica.root)
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 16.0` is replaced by the mechanism:
    # the bound lives in the verb, so the twin's calls to the held daemon are one attempt inside
    # the verb's read budget.
    calls = record_transport(monkeypatch, dm)
    r = CliRunner().invoke(cli_mod.main, argv)
    assert r.exit_code == 0, r.output
    assert "held_row" in r.output and "reading the replica" in r.output, r.output
    assert_one_deadline(calls, budget=verbs.MEMORY_READ_BUDGET_S, root=held_replica.root,
                        what="the bound lives in the verb; the twin must call it")
    assert held_replica.ops.count("memory_iter") + held_replica.ops.count("memory_search") == 1, \
        held_replica.ops           # one attempt, never the library's three


def test_list_and_search_twins_route_through_the_memory_verb(held_replica, monkeypatch):
    """The parity gate pairs `rmx_memory` with `get` only, so the wiring is
    asserted here: the verb is what the twins call."""
    seen = []
    real = verbs.memory

    def spy(root, action, **kw):
        seen.append((action, kw.get("timeout")))
        return real(root, action, **kw)
    monkeypatch.setattr(verbs, "memory", spy)
    monkeypatch.setattr(cli_mod, "_root", lambda: held_replica.root)
    CliRunner().invoke(cli_mod.main, ["memory", "list", "--limit", "3"])
    CliRunner().invoke(cli_mod.main, ["memory", "search", "held"])
    assert [a for a, _ in seen] == ["list", "search"], seen
    assert all(t is not None and t <= verbs.MEMORY_READ_BUDGET_S for _, t in seen), seen


# ---- #s-2 a read on a held writer without a replica says ONE read-worded thing ---------

@pytest.mark.timeout(60)
@pytest.mark.parametrize("argv", [["memory", "get", "x"],
                                  ["memory", "list", "--limit", "3"],
                                  ["memory", "search", "held"],
                                  ["memory", "recall", "--recent", "--timeout", "5"]])
def test_read_twins_on_a_held_writer_without_a_replica_never_say_reading_the_replica(
        held, monkeypatch, argv):
    _no_replica(held.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 36.0` is replaced by the mechanism:
    # the partition probe and the read share ONE deadline (the read budget, or the recall's
    # `--timeout`), one attempt each.
    calls = record_transport(monkeypatch, dm)
    r = CliRunner().invoke(cli_mod.main, argv)
    assert r.exit_code != 0, r.output
    assert "reading the replica" not in r.output, r.output
    assert "no read replica" in r.output, r.output
    assert "writes go through" not in r.output and "snapshot not built" not in r.output, r.output
    budget = (float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv
              else verbs.MEMORY_READ_BUDGET_S)
    assert_one_deadline(calls, budget=budget, root=held.root)


def test_read_store_raises_read_worded_when_the_daemon_is_up_without_a_replica(held, monkeypatch):
    """`_read_store` used to hand back the write proxy for an UP daemon (the
    proxy's first read then raised 'no lock-free reader … snapshot not
    built'); a read never goes to the proxy."""
    import click
    _no_replica(held.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    with pytest.raises(click.ClickException, match="no read replica"):
        cli_mod._read_store()


# ---- #s-3 fan-outs say what they skipped --------------------------------------------------

@pytest.mark.timeout(60)
def test_federated_query_reports_a_held_store_as_skipped_within_the_bound(held_replica, monkeypatch):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [held_replica.root])
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 25.0` (was 60 s x retries) is
    # replaced by the mechanism: the held store gets ONE `query` with the fan-out's op timeout.
    calls = record_transport(monkeypatch, dm)
    out = search.federated_query("kind:memory")
    assert out["projects"] == []
    assert [s["root"] for s in out["skipped"]] == [str(held_replica.root)], out
    assert "did not answer" in out["skipped"][0]["reason"], out["skipped"]
    assert_one_deadline(calls, budget=search.QUERY_OP_TIMEOUT_S, root=held_replica.root)
    assert held_replica.ops.count("query") == 1, held_replica.ops


@pytest.mark.timeout(60)
def test_federated_where_reports_the_stalled_memory_leg(held_replica, monkeypatch):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [held_replica.root])
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 12.0` is replaced by the mechanism:
    # the held store's memory leg is ONE call bounded by the where fan-out's memory-op timeout.
    calls = record_transport(monkeypatch, dm)
    out = search.federated_where("held")
    roots = [s["root"] for s in out["skipped"]]
    assert str(held_replica.root) in roots, out["skipped"]
    reason = next(s["reason"] for s in out["skipped"] if s["root"] == str(held_replica.root))
    assert "did not answer" in reason, reason
    assert_one_deadline(calls, budget=search.WHERE_MEMORY_OP_S, root=held_replica.root)


@pytest.mark.timeout(60)
def test_federated_locate_names_a_straggler_past_the_fan_out_deadline(held_replica, monkeypatch):
    """`_locate_one_project` reads the replica only (it never asks the
    daemon), so a held writer cannot stall it; the pool's contract — a
    store still running past the deadline is NAMED — is proven with a
    per-project helper that sleeps past a 1 s deadline."""
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 2.5` against a 3 s straggler is an
    # ordering check now. The per-project helper is held on an event the test owns, so the
    # fan-out returning at all (under the hang guard) means its 1 s deadline did not wait for
    # the straggler, which is still held when the result comes back.
    import threading

    from tests.timing import HANG_GUARD_S
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def straggler(root, filename, keywords):
        entered.set()
        release.wait(HANG_GUARD_S)
        finished.set()
        return {}, []

    monkeypatch.setattr(discovery, "discover_roots", lambda: [held_replica.root])
    monkeypatch.setattr(search, "LOCATE_FANOUT_S", 1.0)
    monkeypatch.setattr(search, "_locate_one_project", straggler)
    try:
        out = search.federated_locate(keywords=["held"])
        assert entered.is_set() and not finished.is_set(), "the fan-out waited for the straggler"
    finally:
        release.set()
    assert out["results"] == []
    assert [s["root"] for s in out["skipped"]] == [str(held_replica.root)], out["skipped"]
    assert "did not answer within 1s" in out["skipped"][0]["reason"], out["skipped"]


@pytest.mark.timeout(60)
def test_federated_locate_on_a_held_writer_with_a_replica_skips_nothing(held_replica, monkeypatch):
    """The honest counterpart: locate needs no daemon, so a held writer with
    a replica is served, not skipped."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [held_replica.root])
    out = search.federated_locate(keywords=["held"])
    assert out["skipped"] == [], out["skipped"]
    # 29.4 R3 class C (T0.3 + 29.4c, 2026-11-15): `elapsed < 10.0` stood for "locate does not
    # wait on the held writer". Asserted directly: the held daemon, which stalls every op but
    # ping, was asked nothing while the test held it.
    assert [op for op in held_replica.ops if op != "ping"] == [], held_replica.ops


# ---- #m-4 one partition probe per command ------------------------------------------------

@pytest.mark.timeout(90)
def test_recall_twin_probes_the_partition_once_on_a_held_writer_without_a_replica(held, monkeypatch):
    _no_replica(held.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    CliRunner().invoke(cli_mod.main, ["memory", "recall", "--recent", "--json", "--timeout", "30"])
    assert held.ops.count("partition_list") == 1, held.ops


@pytest.mark.timeout(60)
def test_get_twin_probes_the_partition_once_on_a_held_writer_without_a_replica(held, monkeypatch):
    _no_replica(held.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    CliRunner().invoke(cli_mod.main, ["memory", "get", "x"])
    assert held.ops.count("partition_list") == 1, held.ops
