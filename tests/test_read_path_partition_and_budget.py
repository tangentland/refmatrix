"""ch-bsd r9 #b-1 / #b-2: the read path answers from the RIGHT partition, and a
budgeted rerank is actually bounded.

#b-1: `_open_read_store` re-pointed the ONE shared in-memory mirror Store's
partition OUTSIDE the mirror's use-lock. Once r8 moved `_op_context` onto the
read path, a concurrent read for another partition could re-point the store
mid-op: 39 of 40 context ops answered from the wrong partition in r9's probe
(0 of 40 before). Every `_read_with_fallback` caller shared the hazard.

#b-2: `RemoteReranker.with_budget` set a deadline but `score` never passed the
remaining budget to the socket (the client's 45 s default held) and estimated
cost from a CACHED `info` (a stale queue depth). And the context op's rerank
now held the mirror's single-reader lock.

Real daemon shell + real DuckDB + real `_MemMirror`; the model worker client is
the external boundary.
"""
from __future__ import annotations

import threading
import time

import pytest

from refmatrix.store import Store


def _daemon(tmp_path):
    from refmatrix.daemon import Daemon, _MemMirror

    s = Store(tmp_path, backend="duckdb")
    s._connect()
    d = object.__new__(Daemon)
    d.root = tmp_path
    d._log = lambda *a, **k: None
    d.store = s
    d._store_lock = threading.Lock()
    d._snapshot_lock = threading.Lock()
    d._last_snapshot_ts = 0.0
    d._snapshot_dirty = False
    d._snapshot_event = threading.Event()
    d._snapshot_stop = threading.Event()
    d._swap_gate = threading.Condition()
    d._read_inflight = 0
    d._active_slot = None
    for part, name in (("pa", "alpha_only"), ("pb", "beta_only")):
        with s.with_partition(part):
            s.add_concept(name)
    s._conn.commit()
    d._snapshot_catalog(force=True)
    d._mem_mirror = _MemMirror(d)
    assert d._mem_mirror.refresh() is True
    return d, s


# ---- #b-1 ----------------------------------------------------------------

def test_concurrent_reads_on_two_partitions_never_cross(tmp_path):
    """The race lives BETWEEN a reader's re-point and its own use-lock: a
    second reader re-points the shared store in that gap. Two threads hammer
    opposite partitions; any answer from the other partition is a failure."""
    from refmatrix.daemon import _read_with_fallback

    d, s = _daemon(tmp_path)
    wrong: list[tuple[str, str]] = []
    barrier = threading.Barrier(2)

    def slow(rs):
        # a real read takes time inside the use-lock (r9's probe raced a
        # context build); that is what makes readers queue and re-point
        time.sleep(0.002)
        return rs._partition_name

    def run(part):
        barrier.wait()
        for _ in range(100):
            got = _read_with_fallback(d, part, slow)
            if got != part:
                wrong.append((part, got))

    ts = [threading.Thread(target=run, args=(p,)) for p in ("pa", "pb")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    s.close()
    assert wrong == [], f"{len(wrong)} of 200 reads answered from the other partition"


def test_an_unknown_partition_never_answers_from_the_mirrors_current_one(tmp_path):
    from refmatrix.daemon import _read_with_fallback

    d, s = _daemon(tmp_path)
    name = _read_with_fallback(d, "pb", lambda rs: rs._partition_name)
    assert name == "pb"
    got = _read_with_fallback(d, "nosuch", lambda rs: rs._partition_name)
    s.close()
    assert got != "pb", "answered from whatever the mirror was last pointed at"


def test_the_context_op_holds_no_shared_mirror_lock_while_scoring(tmp_path):
    from refmatrix.daemon import _op_context

    d, s = _daemon(tmp_path)
    free: list[bool] = []

    class _RR:
        def with_budget(self, b):
            return self

        def score(self, q, docs):
            got: list[bool] = []

            def probe():
                lk = d._mem_mirror.acquire_use()
                ok = lk.acquire(blocking=False)
                got.append(ok)
                if ok:
                    lk.release()

            t = threading.Thread(target=probe)
            t.start()
            t.join()
            free.append(got[0])
            return [0.0] * len(docs)

    d._maybe_rerank = lambda args: True
    d._reranker = lambda: _RR()
    d._request_snapshot = lambda: None
    # a corpus in partition pa that reaches the model (>= 2 bodied rows)
    from refmatrix.ingest import ingest_path
    docs = tmp_path / "docs"
    docs.mkdir()
    body = ("The daemon was SIGKILLed by macOS jetsam under memory pressure while the "
            "embed worker held the model. ") * 4
    for i in range(3):
        (docs / f"d{i}.md").write_text(f"# D{i}\n\n{body}\n")
    with s.with_partition("pa"):
        ingest_path(s, docs)
    s._conn.commit()
    d._snapshot_catalog(force=True)
    d._mem_mirror.refresh()

    _op_context(d, {"ref": "memory pressure", "format": "json", "partition": "pa",
                    "grep_backstop": False})
    s.close()
    assert free == [True], free


# ---- #b-2 ----------------------------------------------------------------

class _Client:
    """The worker boundary: records each call's timeout; `info` reports a
    queue that changes after the first probe (a cached header would miss it)."""

    def __init__(self, *, rerank_sleep=0.0, cost=0.01):
        self.calls: list[tuple[str, float | None]] = []
        self.infos = 0
        self.rerank_sleep = rerank_sleep
        self.cost = cost

    def info(self, timeout=None, fresh=False):
        # the cached header (fresh=False) always shows the first, idle queue
        if not fresh:
            return {"model": "m", "cost_s_per_doc": self.cost, "queue_depth": 0}
        self.infos += 1
        return {"model": "m", "cost_s_per_doc": self.cost,
                "queue_depth": 0 if self.infos == 1 else 500}

    def call(self, op, payload=None, *, blob=None, timeout=None):
        self.calls.append((op, timeout))
        if self.rerank_sleep:
            if timeout is not None and self.rerank_sleep > timeout:
                time.sleep(timeout)
                raise TimeoutError("timed out")
            time.sleep(self.rerank_sleep)
        return {"scores": [0.0] * len(payload["docs"])}, b""


def test_the_budget_reaches_the_socket(tmp_path):
    from refmatrix.reranker import RemoteReranker

    c = _Client()
    rr = RemoteReranker(c).with_budget(2.0)
    rr.score("q", ["a doc", "b doc"])
    rerank_timeouts = [t for op, t in c.calls if op == "rerank"]
    assert rerank_timeouts and rerank_timeouts[0] is not None and rerank_timeouts[0] <= 2.0


def test_the_estimate_uses_a_fresh_queue_depth(tmp_path):
    from refmatrix.reranker import RemoteReranker, RerankSkipped

    c = _Client(cost=0.05)
    RemoteReranker(c).with_budget(5.0).score("q", ["d"] * 4)    # queue 0: fits
    with pytest.raises(RerankSkipped):
        RemoteReranker(c).with_budget(5.0).score("q", ["d"] * 4)  # queue 500: does not


def test_a_busy_worker_costs_at_most_the_budget(tmp_path):
    from refmatrix.reranker import RemoteReranker, RerankSkipped

    c = _Client(rerank_sleep=3.0)
    t0 = time.time()
    with pytest.raises(RerankSkipped):
        RemoteReranker(c).with_budget(0.5).score("q", ["a", "b"])
    assert time.time() - t0 < 1.0
