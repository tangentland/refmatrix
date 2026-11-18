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
from tests.timing import assert_one_deadline, record_transport

# `verbs.memory_partition` probes the daemon once with `min(10.0, timeout)` (bsd-plan3-r4 #b-2).
PARTITION_PROBE_CAP_S = 10.0

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

def test_memory_get_verb_is_bounded_on_a_held_writer(held, monkeypatch):
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 16.0` is replaced by the mechanism:
    # the held daemon's calls are one attempt each, inside the read budget as one deadline.
    calls = record_transport(monkeypatch, dm)
    with pytest.raises(verbs.VerbBusyError):
        verbs.memory(held.root, action="get", name="x")
    assert_one_deadline(calls, budget=verbs.MEMORY_READ_BUDGET_S, root=held.root,
                        what="the read verb must give up within its budget")


def test_mcp_recall_default_timeout_is_bounded_on_a_held_writer(held, monkeypatch):
    assert inspect.signature(verbs.memory_recall).parameters["timeout"].default == 30.0
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 36.0` is replaced by the mechanism:
    # the default 30 s is one deadline across the held daemon's calls, one attempt each.
    calls = record_transport(monkeypatch, dm)
    with pytest.raises(verbs.VerbBusyError):
        verbs.memory_recall(held.root, recent=True)
    assert_one_deadline(calls, budget=30.0, root=held.root)


def test_memory_get_cli_reads_the_replica_within_the_budget_on_a_held_writer(held, monkeypatch):
    _snapshot(held.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 16.0` is replaced by the mechanism:
    # the held daemon is asked once, inside the read budget, before the replica serves the row.
    calls = record_transport(monkeypatch, dm)
    r = CliRunner().invoke(cli_mod.main, ["memory", "get", "held_row"])
    assert r.exit_code == 0, r.output
    assert "a row the replica can serve" in r.output
    assert "reading the replica" in r.output
    assert_one_deadline(calls, budget=verbs.MEMORY_READ_BUDGET_S, root=held.root,
                        what="to reach the replica")


def test_memory_recall_recent_cli_reads_the_replica_within_the_budget(held, monkeypatch):
    _snapshot(held.root)
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 12.0` is replaced by the mechanism:
    # `--timeout 5` is one deadline across the held daemon's calls, one attempt each.
    calls = record_transport(monkeypatch, dm)
    r = CliRunner().invoke(cli_mod.main, ["memory", "recall", "--recent", "--json", "--timeout", "5"])
    assert r.exit_code == 0, r.output
    assert "held_row" in r.output and "reading the replica" in r.output
    assert_one_deadline(calls, budget=5.0, root=held.root)


# ---- #s-3 promote + per-hit get through the typed wrapper -----------------------------

def test_promote_digest_is_typed_busy_on_a_held_writer(held, monkeypatch):
    from refmatrix import stm as stm_mod
    s = stm_mod.Stm(held.root, "s9")
    s.record("input", "hello")
    before = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in held.root.glob("catalog*.duckdb")}
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 36.0` is replaced by the mechanism:
    # the digest's write reaches the held daemon once, with `_promote_digest`'s 30 s budget.
    calls = record_transport(monkeypatch, dm)
    out = handoff._promote_digest(held.root, s)
    assert out.get("error") and "busy" in out["error"], out
    assert "TimeoutError" not in out["error"]
    assert_one_deadline(calls, budget=30.0, root=held.root)
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

def test_memory_partition_raises_busy_on_a_held_writer_without_a_replica(held, monkeypatch):
    """No replica to read (rotation layout before the first snapshot): the
    daemon decides, and a held writer is BUSY — never a guessed partition."""
    (held.root / "catalog.duckdb").rename(held.root / "catalog.A.duckdb")
    (held.root / "active").write_text("A")
    # 29.4 R3 class B (T0.3 + 29.4c, 2026-11-15): `elapsed < 16.0` is replaced by the mechanism:
    # the partition probe is one attempt under `memory_partition`'s 10 s probe cap.
    calls = record_transport(monkeypatch, dm)
    with pytest.raises(verbs.VerbBusyError):
        verbs.memory_partition(held.root)
    assert_one_deadline(calls, budget=PARTITION_PROBE_CAP_S, root=held.root)


def test_memory_partition_reads_the_replica_under_a_held_writer(held, monkeypatch):
    """With a replica the answer is lock-free and instant (plan-2 r8): the
    daemon is not asked at all. The replica is the SNAPSHOT — the held
    writer's own file is locked and never readable (2026-09-15)."""
    from refmatrix import discovery
    _snapshot(held.root)
    monkeypatch.setattr(dm, "call", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("asked the daemon")))
    assert verbs.memory_partition(held.root) == discovery.store_name(held.root)
    # 29.4 R3 class C (T0.3 + 29.4c, 2026-11-15): `elapsed < 1.0` ("instant") is an ordering
    # check: the answer came while the test held the writer, and no op that waits on the lock
    # reached the held daemon.
    assert [op for op in held.ops if op != "ping"] == [], held.ops


class _OldOpDaemon(_PingOnlyDaemon):
    """A daemon that answers `ping` and answers every other op with an ERROR, the way a daemon
    older than an op answers it (`unknown op …`). Nothing faked below the socket."""

    def _serve_one(self, c):
        import json as _json
        try:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = c.recv(65536)
                if not chunk:
                    return
                buf += chunk
            req = _json.loads(buf.decode() or "{}")
            op = req.get("op")
            self.ops.append(op)
            resp = ({"ok": True, "result": {"pid": self.pid, "version": "x"}} if op == "ping"
                    else {"ok": False, "error": f"unknown op {op}"})
            c.sendall((_json.dumps(resp) + "\n").encode())
        except OSError:
            pass
        finally:
            c.close()


def test_memory_partition_guesses_loudly_on_an_answered_error(caplog):
    """T0.4 R4.4 (ch-bsd plan-6 r1 #s-2): an ANSWERED error from `partition_list` is the one case
    the project default is a legitimate guess, and it is said, never mute: a `warning` naming the
    root, the daemon's error and the partition it falls back to. Through the real socket: no
    replica yet, a live daemon that answers ping and refuses the op. M4.4 (the warning is not
    logged) is red here."""
    from refmatrix import discovery
    d = _OldOpDaemon()
    try:
        with caplog.at_level("WARNING", logger="refmatrix.verbs"):
            got = verbs.memory_partition(d.root)
        project = discovery.store_name(d.root)
        assert got == project
        assert "partition_list" in d.ops, d.ops
        warned = [r.getMessage() for r in caplog.records
                  if r.name == "refmatrix.verbs" and r.levelname == "WARNING"]
        assert len(warned) == 1, warned
        assert str(d.root) in warned[0], warned
        assert "unknown op partition_list" in warned[0], warned
        assert repr(project) in warned[0], warned
    finally:
        d.close()


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
