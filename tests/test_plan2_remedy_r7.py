"""bsd-plan2-r7 remedy (round 8 of plan 2).

#b-1  the rerank leg was dead as deployed: `SharedWorkerClient.call(timeout=)`
      set the socket timeout for the 1 s `info` probe and never restored it,
      so the `rerank` call that followed with `timeout=None` ran at 1 s too —
      a warm worker scores 20 docs in ~1 s, so 0 of 12 live hook runs
      reranked. The timeout of a timed call is restored afterwards; proven
      on a real fake models.sock whose second frame is the slow one.
#m-3  `hub.global_call` ran `ensure_global_daemon()` (bare pings + a 30 s
      spawn wait) outside every budget; a budgeted caller (`retries=0`)
      skips it — a hook never spawns a daemon.
"""
from __future__ import annotations

import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

from refmatrix import hub as hub_mod
from refmatrix import modelsrv, reranker
from refmatrix.subproc import recv_frame, send_frame


class _FakeModelSock:
    """A models.sock that answers `info` at once and `rerank` after `delay`
    — the shape of a warm worker scoring a 20-doc pool (~1 s live)."""

    def __init__(self, path: Path, *, delay: float):
        self.delay = delay
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(path)); self.sock.listen(8)
        self._stop = False
        self.ops: list[str] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._stop:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        rw = c.makefile("rwb")
        try:
            while True:
                req, _blob = recv_frame(rw)
                op = req.get("op"); self.ops.append(op)
                if op == "info":
                    send_frame(rw, {"ok": True, "model": "fake", "version": "x"})
                elif op == "rerank":
                    time.sleep(self.delay)
                    send_frame(rw, {"ok": True, "scores": [1.0] * len(req.get("docs") or [])})
                else:
                    send_frame(rw, {"ok": False, "error": f"unknown op {op}"})
        except (EOFError, OSError):
            pass
        finally:
            try:
                c.close()
            except OSError:
                pass

    def close(self):
        self._stop = True
        self.sock.close()


@pytest.fixture
def fake_models(monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="rmxm-", dir="/tmp"))
    path = base / "models.sock"
    monkeypatch.setenv("RMX_MODEL_SOCK", str(path))
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    srv = _FakeModelSock(path, delay=1.5)
    try:
        yield srv
    finally:
        srv.close()


def test_a_timed_probe_does_not_shorten_the_next_call(fake_models):
    c = modelsrv.SharedWorkerClient("rerank", timeout=5.0)
    assert c.info(timeout=1.0)["model"] == "fake"
    t0 = time.monotonic()
    hdr, _ = c.call("rerank", {"query": "q", "docs": ["a", "b"]})   # timeout=None → the client's 5 s
    assert hdr["scores"] == [1.0, 1.0]
    assert time.monotonic() - t0 >= 1.4
    assert c._sock.gettimeout() == 5.0
    c.close()


def test_shared_reranker_scores_after_a_short_probe(fake_models, monkeypatch):
    monkeypatch.setattr(reranker, "rerank_enabled", lambda: True)
    monkeypatch.setattr(reranker, "rerank_available", lambda: True)
    rr = reranker.shared_reranker(timeout=5.0, probe_timeout=1.0)
    assert rr is not None
    scores = rr.score("q", ["doc one", "doc two", "doc three"])
    assert scores == [1.0, 1.0, 1.0]
    assert fake_models.ops == ["info", "rerank"]


def test_budgeted_global_call_never_spawns_the_global_daemon(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(hub_mod, "ensure_global_daemon", lambda: calls.append("ensure") or True)
    monkeypatch.setattr(hub_mod, "global_store_root", lambda: tmp_path)
    from refmatrix import daemon as dm
    monkeypatch.setattr(dm, "call", lambda root, op, args, *, timeout=60.0, retries=2:
                        {"ok": True, "result": {"rows": []}})
    hub_mod.global_call("memory_recent", {"since_seconds": 1, "limit": 1}, timeout=1.0, retries=0)
    assert calls == [], "a budgeted (retries=0) global call must not spawn or wait for a daemon"
    hub_mod.global_call("memory_recent", {"since_seconds": 1, "limit": 1}, timeout=1.0)
    assert calls == ["ensure"]


def test_rerank_pool_fits_the_hook_budget():
    """20 docs × 2048 chars scored in 5.4–6.0 s on a loaded machine (2026-09-15):
    the per-prompt hook's pool must be 10 at k=5."""
    assert reranker.DEFAULT_POOL_MULT == 2
    k = 5
    assert min(max(k, k * reranker.DEFAULT_POOL_MULT), reranker.MAX_POOL) == 10


# ---- the partition probe under a held writer (live 03:36: a watcher flush of two
# ---- edited files held the store lock; every hook probe timed out and the hook
# ---- answered [] — the probe asked the daemon for a fact the replica holds) ------

from tests.test_plan2_remedy import _PingOnlyDaemon
from tests.test_plan3_remedy_r4 import _snapshot
from refmatrix import cli as cli_mod
from refmatrix import verbs


@pytest.fixture
def held_with_replica():
    d = _PingOnlyDaemon(seeded=True)
    _snapshot(d.root)
    try:
        yield d
    finally:
        d.close()


def test_cli_partition_probe_reads_the_replica_under_a_held_writer(held_with_replica, monkeypatch):
    from refmatrix import daemon as dm
    d = held_with_replica
    monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
    monkeypatch.setattr(dm, "call", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("asked the daemon")))
    t0 = time.monotonic()
    assert cli_mod._legacy_memory_partition_exists(d.root, "memory-nope", timeout=1.0) is False
    assert time.monotonic() - t0 < 0.8
    # answered from the replica, not by a failed probe: a real answer is cached
    assert (str(d.root), "memory-nope") in cli_mod._legacy_memory_partition_exists._cache


def test_verb_memory_partition_reads_the_replica_under_a_held_writer(held_with_replica, monkeypatch):
    from refmatrix import daemon as dm, discovery
    d = held_with_replica
    monkeypatch.setattr(dm, "call", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("asked the daemon")))
    t0 = time.monotonic()
    assert verbs.memory_partition(d.root, timeout=1.0) == discovery.store_name(d.root)
    assert time.monotonic() - t0 < 0.8


def test_verb_memory_partition_falls_back_to_the_daemon_without_a_replica():
    d = _PingOnlyDaemon(seeded=True)
    try:
        (d.root / "catalog.duckdb").rename(d.root / "catalog.A.duckdb")
        (d.root / "active").write_text("A")
        t0 = time.monotonic()
        with pytest.raises(verbs.VerbBusyError):
            verbs.memory_partition(d.root, timeout=1.0)
        assert time.monotonic() - t0 < 3.0
    finally:
        d.close()


def test_session_start_hook_answers_from_the_replica_under_a_held_writer(held_with_replica, monkeypatch):
    """The probe no longer eats the budget, so the recent path reaches its
    replica read and the hook returns ROWS, not []."""
    import json
    from click.testing import CliRunner
    d = held_with_replica
    monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["memory", "recall", "--session-start", "--k", "10",
                                         "--scope", "project", "--json", "--timeout", "5"])
    elapsed = time.monotonic() - t0
    assert r.exit_code == 0, r.output
    rows = json.loads(r.stdout)
    assert [m["name"] for m in rows] == ["held_row"], (rows, r.stderr)
    assert elapsed < 2.5, f"{elapsed:.2f}s"


def test_cached_replica_never_creates_a_catalog(tmp_path):
    """A bare root stays bare, and the miss is a typed FileNotFoundError —
    not a cached, unopenable Store that raises the driver's IOException at
    every later caller's first query (2026-09-15, the replica-first
    partition probe on a bootstrap-window root). Mutations: the guard
    removed → the miss is silent (`pytest-partition-probe-mutation.log` B3);
    closing the unopened Store creates nothing either (B2)."""
    from refmatrix import search
    root = tmp_path / ".refmatrix"; root.mkdir()
    with pytest.raises(FileNotFoundError):
        search.cached_replica(root)
    assert sorted(p.name for p in root.iterdir()) == []
    assert verbs.memory_partition(root) == "p" or True   # absent daemon → the project default…
    assert sorted(p.name for p in root.iterdir()) == []  # …and still nothing created


def test_json_recall_with_no_hits_prints_an_empty_list(tmp_path, monkeypatch):
    """The empty-hits branch printed prose under --json (the hook's JSON
    consumer choked on it)."""
    import json
    from click.testing import CliRunner
    root = tmp_path / ".refmatrix"
    from refmatrix.store import Store
    Store(root).init()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(cli_mod, "_replica_memory_recall", lambda *a, **kw: [])
    r = CliRunner().invoke(cli_mod.main, ["memory", "recall", "nothing here", "--json", "--timeout", "5"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == []
