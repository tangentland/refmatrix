"""bsd-plan2-r6 remedy (round 7 of plan 2): the per-prompt recall hook's
budget covers EVERY leg that costs, not only the daemon RPCs.

#b-1  live, `--timeout 5` deployed: 12.8 s idle, 26.8 s / 18.9 s on the first
      two firings. The seconds were in (1) the rerank on the hub's shared
      model worker (`info` + `rerank` at the 300 s worker default), (2) the
      global store on the dense path (30 s × 3 retries, no budget), (3) the
      startup partition probe that ran on its own 5 s before the clock
      started. Now: the clock starts before the probe; the shared-worker
      client is constructed with the remaining budget and the rerank is
      SKIPPED (said on stderr) when less than RERANK_MIN_S remains or the
      worker times out; the global leg takes `_left()` with one attempt.
#s-2  the closure tests admit the additive shape no more: wall < budget +
      0.6 s, the deadline test runs at scope=both with a global spy, and
      the replica path has its own test.
#m-3  the PreCompact recall carries `--timeout 30`; `RMX_INVOCATION_SOURCE=hook`
      (every generated hook exports it) is hook mode for `memory recall`.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import hub as hub_mod
from refmatrix import verbs
from refmatrix.hooks import _claude_hook_block
from refmatrix.store import Store
from tests.test_hooks_reproducible import _cmds
from tests.test_plan2_remedy import _PingOnlyDaemon
from tests.test_plan3_remedy_r4 import _snapshot


@pytest.fixture
def held():
    d = _PingOnlyDaemon(seeded=True)
    try:
        yield d
    finally:
        d.close()


def _invoke(argv, stdin=None):
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, argv, input=stdin)
    return r, time.monotonic() - t0


# ---- #s-2 / #b-1(2): wall ≤ budget + 0.6 on the exact hook argv ----------------------

def test_recall_hook_wall_is_within_budget_on_a_held_writer(held, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    for argv, stdin in ((["memory", "recall", "--stdin-json", "--k", "5", "--scope", "both",
                          "--json", "--timeout", "1"], json.dumps({"prompt": "hello world"})),
                        (["memory", "recall", "--session-start", "--k", "10", "--scope", "both",
                          "--json", "--timeout", "1"], None)):
        r, elapsed = _invoke(argv, stdin)
        assert r.exit_code == 0, (argv, r.output)
        assert elapsed < 1.6, (argv, f"{elapsed:.2f}s for a 1 s budget — the probe runs before the clock")
        assert json.loads(r.stdout) == []
        assert "busy" in (r.stderr or ""), (argv, r.stderr)


# ---- #b-1(2): the global leg, one attempt under the deadline ------------------------------

def test_verb_recall_deadline_covers_the_global_leg_with_one_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr("refmatrix.discovery.daemon_status", lambda r, **kw: {"up": True, "busy": False, "pid": 1})
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda r: "p")
    monkeypatch.setattr(dm, "ping", lambda r, **kw: True)
    groot = tmp_path / "g" / ".refmatrix"; groot.mkdir(parents=True)
    monkeypatch.setattr(hub_mod, "global_store_root", lambda: groot)
    monkeypatch.setattr(hub_mod, "ensure_global_daemon", lambda: None)
    seen = []

    def call(r, op, args=None, timeout=60.0, retries=2, **kw):
        seen.append((str(r), op, round(timeout, 1), retries))
        if op == "partition_list":
            return {"ok": True, "result": {"rows": []}}
        if op in ("memory_recent", "memory_search"):
            return {"ok": True, "result": {"rows": []}}
        if op == "memory_recall":
            return {"ok": True, "result": {"hits": []}}
        return {"ok": True, "result": {}}
    monkeypatch.setattr(dm, "call", call)
    root = tmp_path / ".refmatrix"; root.mkdir()
    verbs.memory_recall(root, recent=True, scope="both", k=3, timeout=2.0)
    verbs.memory_recall(root, query="hello", scope="both", k=3, timeout=2.0)
    g = [s for s in seen if s[0] == str(groot)]
    assert len(g) == 2, seen
    assert all(rt == 0 for _, _, _, rt in g), g
    assert all(t <= 2.0 for _, _, t, _ in g), g


def test_global_leg_on_a_held_global_store_is_bounded_and_named(held, monkeypatch):
    """Simulation (b) from the r6 report: a fast project daemon, the GLOBAL
    store answers ping and stalls. `--scope both --timeout 1` must return
    within the budget with the global rows omitted, said on stderr."""
    base = Path(tempfile.mkdtemp(prefix="rmxg-", dir="/tmp"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    try:
        monkeypatch.setattr(cli_mod, "_root", lambda: root)
        monkeypatch.setattr(hub_mod, "global_store_root", lambda: held.root)
        monkeypatch.setattr(hub_mod, "ensure_global_daemon", lambda: None)
        r, elapsed = _invoke(["memory", "recall", "--session-start", "--k", "5", "--scope", "both",
                              "--json", "--timeout", "1"])
        assert r.exit_code == 0, r.output
        assert elapsed < 1.6, f"{elapsed:.2f}s"
        assert "global rows omitted" in (r.stderr or ""), r.stderr
    finally:
        dm.stop_daemon(root); shutil.rmtree(base, ignore_errors=True)


# ---- #b-1(1): the replica path — shared worker + rerank under the deadline ----------------

class _SilentModelSocket:
    """A models.sock that accepts and never answers: the hub mid-restart /
    a worker still loading — the 6.3 s `info` + 6.2 s `rerank` legs."""

    def __init__(self, path: Path):
        self.path = path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(path)); self.sock.listen(8)
        self.held: list = []
        self._stop = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._stop:
            try:
                c, _ = self.sock.accept()
                self.held.append(c)
            except OSError:
                return

    def close(self):
        self._stop = True
        for c in self.held:
            try:
                c.close()
            except OSError:
                pass
        self.sock.close()


def test_replica_path_is_bounded_when_the_shared_worker_stalls(held, monkeypatch):
    _snapshot(held.root)
    monkeypatch.setenv("RMX_MODEL_SOCK", str(held.base / "models.sock"))   # short path: sun_path
    monkeypatch.setenv("RMX_SHARED_MODELS", "1")
    from refmatrix import modelsrv
    ms = _SilentModelSocket(modelsrv.model_sock_path())
    try:
        monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
        r, elapsed = _invoke(["memory", "recall", "--stdin-json", "--k", "5", "--json",
                              "--timeout", "2"], json.dumps({"prompt": "hello world"}))
        assert r.exit_code == 0, r.output
        assert elapsed < 2.6, f"{elapsed:.2f}s for a 2 s budget (the worker legs ran unbounded)"
        assert json.loads(r.stdout) == []
        assert "busy" in (r.stderr or "") or "shared worker" in (r.stderr or ""), r.stderr
    finally:
        ms.close()


class _SlowReranker:
    model_name = "fake"

    def __init__(self, delay):
        self.delay = delay
        self.calls = 0

    def score(self, query, docs):
        self.calls += 1
        time.sleep(self.delay)
        return [1.0] * len(docs)


def _replica_store_with_rows(tmp_path):
    root = tmp_path / ".refmatrix"
    s = Store(root); s.init()
    from refmatrix.store import default_partition_name
    with s.with_partition(default_partition_name(root)):
        ids = [s.add_memory(name=f"m{i}", content=f"row {i} about hello", mtype="note")
               for i in range(3)]
    return root, s, ids


def test_rerank_is_skipped_and_said_when_the_budget_is_short(tmp_path, monkeypatch):
    root, s, ids = _replica_store_with_rows(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(cli_mod, "_reader_store", lambda: s)
    monkeypatch.setattr(cli_mod, "_resolve_partition", lambda: s.partition_name)
    from refmatrix import modelsrv, recall, reranker
    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", lambda role, **kw: object())
    monkeypatch.setattr(recall, "dense_recall", lambda st, emb, q, k, kinds: [(i, 0.1) for i in ids][:k])
    rr = _SlowReranker(3.0)
    monkeypatch.setattr(reranker, "shared_reranker", lambda log=None, **kw: rr)
    monkeypatch.setattr(reranker, "rerank_enabled", lambda: True)
    ws: list[str] = []
    t0 = time.monotonic()
    hits = cli_mod._replica_memory_recall("hello", k=3, kinds=["memory"], fuse=False, rerank=True,
                                          left=lambda d: min(d, 0.8), warnings=ws)
    assert time.monotonic() - t0 < 1.0
    assert hits and all(not h.get("reranked") for h in hits), hits
    assert rr.calls == 0, "the rerank ran with 0.8 s of budget left"
    assert any("rerank skipped" in w for w in ws), ws
    s.close()


def test_rerank_timeout_is_said_not_swallowed(tmp_path, monkeypatch):
    root, s, ids = _replica_store_with_rows(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(cli_mod, "_reader_store", lambda: s)
    monkeypatch.setattr(cli_mod, "_resolve_partition", lambda: s.partition_name)
    from refmatrix import modelsrv, recall, reranker
    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", lambda role, **kw: object())
    monkeypatch.setattr(recall, "dense_recall", lambda st, emb, q, k, kinds: [(i, 0.1) for i in ids][:k])

    class _Timing:
        model_name = "fake"

        def score(self, query, docs):
            raise TimeoutError("timed out")
    monkeypatch.setattr(reranker, "shared_reranker", lambda log=None, **kw: _Timing())
    monkeypatch.setattr(reranker, "rerank_enabled", lambda: True)
    ws: list[str] = []
    hits = cli_mod._replica_memory_recall("hello", k=3, kinds=["memory"], fuse=False, rerank=True,
                                          left=lambda d: min(d, 30.0), warnings=ws)
    assert hits and all(not h.get("reranked") for h in hits)
    assert any("rerank" in w and "timed out" in w for w in ws), ws
    s.close()


def test_shared_reranker_takes_a_timeout(monkeypatch):
    from refmatrix import modelsrv, reranker
    seen = {}

    class _Client:
        def __init__(self, role, *, log=None, timeout=None):
            seen["ctor"] = timeout

        def info(self, *, timeout=None):
            seen["info"] = timeout
            return {"model": "x"}
    monkeypatch.setattr(reranker, "rerank_enabled", lambda: True)
    monkeypatch.setattr(reranker, "rerank_available", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", _Client)
    assert reranker.shared_reranker(timeout=2.5) is not None
    assert seen == {"ctor": 2.5, "info": 2.5}, seen
    assert reranker.shared_reranker(timeout=2.5, probe_timeout=1.0) is not None
    assert seen == {"ctor": 2.5, "info": 1.0}, seen


def test_budget_spent_before_the_global_leg_keeps_the_project_rows(tmp_path, monkeypatch):
    """Live 2026-09-15 after the r7 deploy: the rerank probe ate the budget,
    `_left()` raised at the global leg and the hook exited 1 with a
    traceback. The project rows must come back and the omission be said."""
    monkeypatch.setattr("refmatrix.discovery.daemon_status", lambda r, **kw: {"up": True, "busy": False, "pid": 1})
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda r: "p")
    monkeypatch.setattr(dm, "ping", lambda r, **kw: True)
    monkeypatch.setattr(hub_mod, "global_store_root", lambda: tmp_path)
    monkeypatch.setattr(hub_mod, "ensure_global_daemon", lambda: None)
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_RECALL_REPLICA_FIRST", "0")

    def call(r, op, args=None, timeout=60.0, retries=2, **kw):
        if op == "partition_list":
            return {"ok": True, "result": {"rows": []}}
        if op == "memory_recall":
            time.sleep(0.5)
            return {"ok": True, "result": {"hits": [{"id": 7, "distance": 0.1}]}}
        if op == "memory_get":
            time.sleep(0.6)                      # the budget is gone AFTER this leg
            return {"ok": True, "result": {"memory": {"id": 7, "name": "m", "content": "c",
                                                       "mtype": "note", "tags": [], "metadata": {}}}}
        return {"ok": True, "result": {}}
    monkeypatch.setattr(dm, "call", call)
    r, elapsed = _invoke(["memory", "recall", "hello", "--k", "3", "--scope", "both", "--json",
                          "--timeout", "1"])
    assert r.exit_code == 0, r.output
    assert "Traceback" not in r.output
    assert [m["name"] for m in json.loads(r.stdout)] == ["m"], r.stdout
    assert "global rows omitted" in (r.stderr or ""), r.stderr


# ---- #m-3 the third recall hook ---------------------------------------------------------------

def test_precompact_recall_is_bounded_and_hook_env_is_hook_mode(tmp_path, held, monkeypatch):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    pre = [c for _, _, c in _cmds(block, "PreCompact") if "memory recall --recent" in c]
    assert pre and all("--timeout 30" in c for c in pre), pre
    # the generated env marks every hook; the CLI treats it as hook mode
    monkeypatch.setattr(cli_mod, "_root", lambda: held.root)
    monkeypatch.setenv("RMX_INVOCATION_SOURCE", "hook")
    r, elapsed = _invoke(["memory", "recall", "--recent", "--since", "1h", "--k", "20",
                          "--scope", "both", "--json", "--timeout", "1"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == [] and "busy" in (r.stderr or ""), r.stderr
    assert elapsed < 1.6, f"{elapsed:.2f}s"
