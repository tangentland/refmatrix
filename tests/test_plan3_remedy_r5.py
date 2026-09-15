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
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, argv)
    elapsed = time.monotonic() - t0
    assert r.exit_code == 0, r.output
    assert "held_row" in r.output and "reading the replica" in r.output, r.output
    assert elapsed < 16.0, f"{elapsed:.1f}s — the bound lives in the verb; the twin must call it"
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
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, argv)
    elapsed = time.monotonic() - t0
    assert r.exit_code != 0, r.output
    assert "reading the replica" not in r.output, r.output
    assert "no read replica" in r.output, r.output
    assert "writes go through" not in r.output and "snapshot not built" not in r.output, r.output
    assert elapsed < 36.0, f"{elapsed:.1f}s"


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
    t0 = time.monotonic()
    out = search.federated_query("kind:memory")
    elapsed = time.monotonic() - t0
    assert out["projects"] == []
    assert [s["root"] for s in out["skipped"]] == [str(held_replica.root)], out
    assert "did not answer" in out["skipped"][0]["reason"], out["skipped"]
    assert elapsed < 25.0, f"{elapsed:.1f}s (was 60 s × retries)"
    assert held_replica.ops.count("query") == 1, held_replica.ops


@pytest.mark.timeout(60)
def test_federated_where_reports_the_stalled_memory_leg(held_replica, monkeypatch):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [held_replica.root])
    t0 = time.monotonic()
    out = search.federated_where("held")
    elapsed = time.monotonic() - t0
    roots = [s["root"] for s in out["skipped"]]
    assert str(held_replica.root) in roots, out["skipped"]
    reason = next(s["reason"] for s in out["skipped"] if s["root"] == str(held_replica.root))
    assert "did not answer" in reason, reason
    assert elapsed < 12.0, f"{elapsed:.1f}s"


@pytest.mark.timeout(60)
def test_federated_locate_names_a_straggler_past_the_fan_out_deadline(held_replica, monkeypatch):
    """`_locate_one_project` reads the replica only (it never asks the
    daemon), so a held writer cannot stall it; the pool's contract — a
    store still running past the deadline is NAMED — is proven with a
    per-project helper that sleeps past a 1 s deadline."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [held_replica.root])
    monkeypatch.setattr(search, "LOCATE_FANOUT_S", 1.0)
    monkeypatch.setattr(search, "_locate_one_project",
                        lambda root, filename, keywords: time.sleep(3.0) or {})
    t0 = time.monotonic()
    out = search.federated_locate(keywords=["held"])
    elapsed = time.monotonic() - t0
    assert out["results"] == []
    assert [s["root"] for s in out["skipped"]] == [str(held_replica.root)], out["skipped"]
    assert "did not answer within 1s" in out["skipped"][0]["reason"], out["skipped"]
    assert elapsed < 2.5, f"{elapsed:.1f}s"


@pytest.mark.timeout(60)
def test_federated_locate_on_a_held_writer_with_a_replica_skips_nothing(held_replica, monkeypatch):
    """The honest counterpart: locate needs no daemon, so a held writer with
    a replica is served, not skipped."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [held_replica.root])
    t0 = time.monotonic()
    out = search.federated_locate(keywords=["held"])
    assert out["skipped"] == [], out["skipped"]
    assert time.monotonic() - t0 < 10.0


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
