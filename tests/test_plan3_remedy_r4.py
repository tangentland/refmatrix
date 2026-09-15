"""bsd-plan3-r4 remedy (round 5 of plan 3): every read and write verb against
the HELD-WRITER simulation (`_PingOnlyDaemon`: answers ping, stalls every op),
not only the silent socket.

#b-1  `compose_recall_state` called a busy daemon a stale pid (the render's
      `busy` branch had no producer since 0.41.0). It classifies through
      `discovery.daemon_status`.
#b-2  `memory get` waited 390 s and the MCP recall 210 s to reach the replica
      on a held writer: read actions of the `memory` verb run under a budget
      with one attempt; the recall verb's default timeout is 30 s.
#s-3  `_promote_digest` and the dense per-hit `memory_get` go through `_call`
      (typed busy, one attempt).
#s-4  `memory_partition` raises busy on an op-level timeout instead of
      guessing the partition the following write lands on.
#m-6  a READ on a busy store with no replica dies with a read-worded error,
      not the write control point's.
"""
from __future__ import annotations

import inspect
import shutil
import time
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import handoff, verbs
from refmatrix import hub as hub_mod
from refmatrix.store import Store
from tests.test_plan2_remedy import _PingOnlyDaemon, _SilentDaemon

GMD_ROW = {"name": "held_row", "content": "a row the replica can serve", "mtype": "note"}


@pytest.fixture
def held():
    """Seeded store + a daemon that answers ping and stalls every op."""
    d = _PingOnlyDaemon(seeded=True)
    try:
        yield d
    finally:
        d.close()


def _snapshot(root: Path) -> None:
    """Write the lock-free read replica the way the daemon does, with one
    memory row in the project's default partition (the partition the CLI
    falls back to when the held writer stalls `partition_list`)."""
    from refmatrix.store import default_partition_name
    s = Store(root); s.init()
    with s.with_partition(default_partition_name(root)):
        s.add_memory(name=GMD_ROW["name"], content=GMD_ROW["content"], mtype=GMD_ROW["mtype"])
    d = dm.Daemon(root); d.store = s; d._log = lambda msg: None
    d._snapshot_catalog(force=True)
    s.close()


# ---- #b-1 recall-state --------------------------------------------------------------

def test_recall_state_reports_a_busy_daemon_as_busy_not_stale(tmp_path, monkeypatch):
    d = _SilentDaemon(seeded=True)
    try:
        memdir = tmp_path / "mem"; memdir.mkdir()
        monkeypatch.setenv("RMX_SESSION", "s1")
        rep = verbs.recall_state(d.root, memory_dir=str(memdir))
        assert rep["daemon"]["busy"] is True and rep["daemon"]["running"] is False
        assert rep["daemon"]["pid"] == d.pid
        assert not any("stale" in a for a in rep["anomalies"]), rep["anomalies"]
        assert any("busy" in a for a in rep["anomalies"]), rep["anomalies"]
        monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
        r = CliRunner().invoke(cli_mod.main, ["recall-state", "--memory-dir", str(memdir)])
        assert "busy pid" in r.output and "stale" not in r.output, r.output
    finally:
        d.close()


def test_recall_state_still_says_stale_for_a_dead_pid(tmp_path, monkeypatch):
    base = Path("/tmp") / f"rmxrs-{time.time_ns()}"
    root = base / ".refmatrix"; root.mkdir(parents=True)
    try:
        dm.pid_path(root).write_text("999999")
        memdir = tmp_path / "mem"; memdir.mkdir()
        monkeypatch.setenv("RMX_SESSION", "s1")
        rep = verbs.recall_state(root, memory_dir=str(memdir))
        assert rep["daemon"]["busy"] is False and rep["daemon"]["running"] is False
        assert any("stale" in a for a in rep["anomalies"]), rep["anomalies"]
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- #b-2 read budgets on a held writer ---------------------------------------------

def test_memory_get_verb_is_bounded_on_a_held_writer(held):
    t0 = time.monotonic()
    with pytest.raises(verbs.VerbBusyError):
        verbs.memory(held.root, action="get", name="x")
    assert time.monotonic() - t0 < 16.0, "the read verb must give up within its budget"


def test_mcp_recall_default_timeout_is_bounded_on_a_held_writer(held):
    assert inspect.signature(verbs.memory_recall).parameters["timeout"].default == 30.0
    t0 = time.monotonic()
    with pytest.raises(verbs.VerbBusyError):
        verbs.memory_recall(held.root, recent=True)
    assert time.monotonic() - t0 < 36.0


def test_memory_get_cli_reads_the_replica_within_the_budget_on_a_held_writer(held, monkeypatch):
    _snapshot(held.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["memory", "get", "held_row"])
    elapsed = time.monotonic() - t0
    assert r.exit_code == 0, r.output
    assert "a row the replica can serve" in r.output
    assert "reading the replica" in r.output
    assert elapsed < 16.0, f"{elapsed:.1f}s to reach the replica"


def test_memory_recall_recent_cli_reads_the_replica_within_the_budget(held, monkeypatch):
    _snapshot(held.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["memory", "recall", "--recent", "--json", "--timeout", "5"])
    elapsed = time.monotonic() - t0
    assert r.exit_code == 0, r.output
    assert "held_row" in r.output and "reading the replica" in r.output
    assert elapsed < 12.0, f"{elapsed:.1f}s"


# ---- #s-3 promote + per-hit get through the typed wrapper -----------------------------

def test_promote_digest_is_typed_busy_on_a_held_writer(held, monkeypatch):
    from refmatrix import stm as stm_mod
    s = stm_mod.Stm(held.root, "s9")
    s.record("input", "hello")
    before = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in held.root.glob("catalog*.duckdb")}
    t0 = time.monotonic()
    out = handoff._promote_digest(held.root, s)
    elapsed = time.monotonic() - t0
    assert out.get("error") and "busy" in out["error"], out
    assert "TimeoutError" not in out["error"]
    assert elapsed < 36.0, f"{elapsed:.1f}s"
    after = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in held.root.glob("catalog*.duckdb")}
    assert after == before, "the slot was written"


def test_dense_per_hit_get_goes_through_call(monkeypatch, tmp_path):
    """The per-hit `memory_get` in the dense loop used a bare daemon call:
    a timeout there was a raw TimeoutError out of the MCP tool."""
    root = tmp_path / ".refmatrix"; root.mkdir()
    seen = []

    def fake_call(r, op, payload, *, timeout=60.0, retries=2):
        seen.append((op, retries))
        if op == "memory_recall":
            return {"hits": [{"id": 7, "distance": 0.1}]}
        if op == "memory_get":
            return {"memory": {"id": 7, "name": "m", "content": "c", "mtype": "note",
                               "tags": [], "metadata": {}}}
        return {}
    monkeypatch.setattr(verbs, "_call", fake_call)
    monkeypatch.setattr(verbs, "memory_partition", lambda r, **kw: "p")
    monkeypatch.setattr(dm, "call", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("bare daemon.call")))
    res = verbs.memory_recall(root, query="hello", k=3, timeout=5.0)
    assert [m["name"] for m in res["memories"]] == ["m"]
    assert ("memory_get", 0) in seen, seen


# ---- #s-4 memory_partition on a held writer --------------------------------------------

def test_memory_partition_raises_busy_on_a_held_writer(held):
    t0 = time.monotonic()
    with pytest.raises(verbs.VerbBusyError):
        verbs.memory_partition(held.root)
    assert time.monotonic() - t0 < 16.0


def test_memory_partition_still_guesses_on_an_answered_error(monkeypatch, tmp_path):
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(verbs, "require_daemon", lambda r, **kw: {"up": True})
    monkeypatch.setattr(dm, "call", lambda *a, **kw: {"ok": False, "error": "no such op"})
    from refmatrix import discovery
    monkeypatch.setattr(discovery, "store_name", lambda r: "proj")
    assert verbs.memory_partition(root) == "proj"


# ---- global leg: one attempt under a budget ---------------------------------------------

def test_global_recall_rows_passes_retries_to_the_hub_call(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(hub_mod, "global_store_root", lambda: tmp_path)
    monkeypatch.setattr(hub_mod, "ensure_global_daemon", lambda: None)

    def fake_call(root, op, args, *, timeout=60.0, retries=2):
        seen.update(op=op, timeout=timeout, retries=retries)
        return {"ok": True, "result": {"rows": [{"name": "g"}]}}
    monkeypatch.setattr(dm, "call", fake_call)
    rows = verbs.global_recall_rows("q", k=5, recent=False, since_s=None, timeout=3.0, retries=0)
    assert rows[0]["scope"] == "global"
    assert seen == {"op": "memory_search", "timeout": 3.0, "retries": 0}, seen


# ---- #m-6 read on a busy store without a replica ------------------------------------------

def test_read_on_a_busy_store_without_a_replica_is_read_worded(monkeypatch):
    """The r4 probe's state: a BUSY root (silent socket) on a rotation-layout
    store before its first snapshot — `active` marker + the writer slot only
    (no `catalog.read.duckdb`, no symlink, no inactive slot)."""
    d = _SilentDaemon(seeded=True)
    try:
        (d.root / "catalog.duckdb").rename(d.root / "catalog.A.duckdb")
        (d.root / "active").write_text("A")
        for name in ("catalog.read.duckdb", "read_only.duckdb"):
            p = d.root / name
            if p.exists() or p.is_symlink():
                p.unlink()
        monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
        r = CliRunner().invoke(cli_mod.main, ["memory", "get", "x"])
    finally:
        d.close()
    assert r.exit_code != 0
    assert "no read replica" in r.output, r.output
    assert "writes go through" not in r.output, r.output
    assert "reading the replica" not in r.output, r.output
