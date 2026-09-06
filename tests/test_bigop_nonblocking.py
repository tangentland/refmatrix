"""Big commands must not starve the always-on surfaces.

Four mechanisms, one incident: a viascope partition merge blew the prompt
hooks' deadlines (RPC queued behind the writer for minutes), the CLI's own
300s socket timeout, and — after a bootout for a direct-store merge — the hub
watchdog respawned the daemon 44s later and took the catalog lock back.

1. hub watchdog maintenance pause (`rmx hub pause`)
2. merge_partition lock-yield batching (per-chunk lock, join classify)
3. daemon async job API (partition_merge async=true + job_status)
4. replica-first hook recall (falls back cleanly when legs are missing)
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from refmatrix.daemon import Daemon

import pytest

from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


# --- 1. watchdog pause ------------------------------------------------------


def _watchdog():
    from refmatrix.hub import Watchdog
    return Watchdog(interval=999)


def test_pause_blocks_restart_of_a_dead_daemon(tmp_path, monkeypatch):
    from refmatrix import hub as hub_mod
    wd = _watchdog()
    restarts = []
    monkeypatch.setattr(wd, "_restart", lambda root: restarts.append(root) or True)
    monkeypatch.setattr(hub_mod.daemon_mod, "ping", lambda *a, **k: False)
    monkeypatch.setattr(hub_mod.daemon_mod, "read_pid", lambda *a, **k: None)
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    wd._check(root)
    assert restarts, "sanity: unpaused dead daemon restarts"
    restarts.clear()
    wd.pause(root)
    wd._check(root)
    assert not restarts, "paused root must never restart"
    ring = wd.history[str(root.resolve())]
    assert ring[-1]["reason"] == "paused"


def test_pause_expires_and_resume_lifts(tmp_path):
    wd = _watchdog()
    root = tmp_path / ".refmatrix"
    root.mkdir()
    wd.pause(root, seconds=0.05)
    assert wd.is_paused(root)
    time.sleep(0.06)
    assert not wd.is_paused(root), "expired pause auto-reverts"
    wd.pause(root)                       # indefinite
    assert wd.is_paused(root)
    assert wd.resume(root) is True
    assert not wd.is_paused(root)
    assert wd.resume(root) is False      # idempotent


def test_pause_resets_banked_grace_misses(tmp_path, monkeypatch):
    """A long pause must not bank misses that SIGKILL the daemon the moment
    the pause lifts."""
    from refmatrix import hub as hub_mod
    wd = _watchdog()
    monkeypatch.setattr(hub_mod.daemon_mod, "ping", lambda *a, **k: False)
    monkeypatch.setattr(hub_mod.daemon_mod, "read_pid", lambda *a, **k: 1234)
    root = tmp_path / ".refmatrix"
    root.mkdir()
    key = str(root.resolve())
    wd.miss_counts[key] = 2
    wd.pause(root)
    wd._check(root)
    assert wd.miss_counts[key] == 0


# --- 2. merge lock-yield batching -------------------------------------------


class _CountingLock:
    def __init__(self):
        self.acquisitions = 0
        self._l = threading.Lock()

    def __enter__(self):
        self._l.acquire()
        self.acquisitions += 1
        return self

    def __exit__(self, *exc):
        self._l.release()
        return False


def _two_partitions(s: Store, n: int = 10):
    with s.with_partition("src-part"):
        for i in range(n):
            c = s.add_concept(f"shared{i}")           # collides
            s.link("mentions", c, s.upsert_entity(kind="code", name=f"s{i}.py"))
        s.add_concept("src-only")                     # reparents
    with s.with_partition("dst-part"):
        for i in range(n):
            s.add_concept(f"shared{i}")


def test_merge_takes_the_lock_per_chunk_not_once(store):
    _two_partitions(store, n=10)
    lk = _CountingLock()
    res = store.merge_partition("src-part", "dst-part",
                                lock=lk, chunk=3)
    assert res["entities_merged"] >= 10
    # classify + counts + >=4 collision chunks + reparent + tail: the whole
    # point is that this is MANY acquisitions, not one merge-wide hold.
    assert lk.acquisitions >= 6, lk.acquisitions


def test_merge_progress_fires_and_result_matches_unbatched(store):
    _two_partitions(store, n=7)
    ticks = []
    res = store.merge_partition(
        "src-part", "dst-part", chunk=2,
        progress=lambda ph, d, t: ticks.append((ph, d, t)))
    assert res["entities_merged"] >= 7
    assert res["entities_reparented"] >= 1
    phases = {ph for ph, _d, _t in ticks}
    assert "merge-collisions" in phases
    assert "merge-reparent" in phases
    # src partition dropped
    con = store._connect()
    assert con.execute("SELECT id FROM partitions WHERE name='src-part'"
                       ).fetchone() is None


def test_merge_progress_failure_is_swallowed(store):
    _two_partitions(store, n=3)

    def boom(*a):
        raise RuntimeError("progress sink died")

    res = store.merge_partition("src-part", "dst-part", chunk=1,
                                progress=boom)
    assert res["entities_merged"] >= 3


# --- 3. daemon async job API ------------------------------------------------


def _fake_daemon(store):
    d = SimpleNamespace()
    d.store = store
    d._st = lambda: store  # Daemon._st narrows the Optional store
    d._store_lock = threading.Lock()
    d._jobs = {}
    d._jobs_lock = threading.Lock()
    d._log = lambda _msg: None
    d._request_snapshot = lambda: None
    # Restructuring ops force a log snapshot (unlogged-write-paths fix);
    # the fake has no facts.log to rewrite — record the calls instead.
    d.compactions = []
    d._compact_factslog_if_needed = (
        lambda **kw: d.compactions.append(kw) or {})
    return cast("Daemon", d)


def test_async_merge_returns_job_id_then_completes(store):
    from refmatrix.daemon import _op_partition_merge, _op_job_status
    _two_partitions(store, n=5)
    d = _fake_daemon(store)
    out = _op_partition_merge(
        d, {"src": "src-part", "dst": "dst-part", "async": True})
    job = out.get("job")
    assert job and out.get("async") is True
    deadline = time.time() + 10
    st: dict = {"state": "timeout"}
    while time.time() < deadline:
        st = _op_job_status(d, {"job": job})
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert st["state"] == "done", st
    assert st["result"]["entities_merged"] >= 5
    # The merge is log-invisible; success MUST force a snapshot-compaction.
    assert getattr(d, "compactions") == [{"force": True}]


def test_job_status_unknown_and_listing(store):
    from refmatrix.daemon import _op_job_status
    d = _fake_daemon(store)
    assert "error" in _op_job_status(d, {"job": "nope"})
    assert _op_job_status(d, {}) == {"jobs": {}}


def test_dry_run_never_goes_async(store):
    from refmatrix.daemon import _op_partition_merge
    _two_partitions(store, n=2)
    d = _fake_daemon(store)
    out = _op_partition_merge(
        d, {"src": "src-part", "dst": "dst-part",
            "async": True, "dry_run": True})
    assert "job" not in out
    assert out["dry_run"] is True


# --- 4. replica-first recall degrades to None -------------------------------


def test_replica_recall_env_kill_switch(monkeypatch):
    from refmatrix.cli import _replica_memory_recall
    monkeypatch.setenv("RMX_RECALL_REPLICA_FIRST", "0")
    assert _replica_memory_recall(
        "q", k=5, kinds=["memory"], fuse=True, rerank=None) is None


def test_replica_recall_none_without_shared_workers(monkeypatch):
    from refmatrix import modelsrv
    from refmatrix.cli import _replica_memory_recall
    monkeypatch.delenv("RMX_RECALL_REPLICA_FIRST", raising=False)
    monkeypatch.setattr(modelsrv, "shared_available", lambda *a, **k: False)
    assert _replica_memory_recall(
        "q", k=5, kinds=["memory"], fuse=True, rerank=None) is None
