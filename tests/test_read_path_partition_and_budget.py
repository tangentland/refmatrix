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


_CONCEPTS = "SELECT count(*) FROM entities WHERE partition_id = ?"


@pytest.mark.parametrize("private", [False, True])
def test_an_unknown_partition_never_answers_from_another(tmp_path, private):
    """ch-bsd r10 #s-1: the snapshot Store's read-only fast path resolves a
    missing partition to id 1 and keeps the REQUESTED name, so the old
    assertion (on the name) passed while the op answered from the default
    partition. Assert on the id and the rows: a partition no store has
    answers EMPTY by default, and never creates itself on a read."""
    from refmatrix.daemon import _read_with_fallback

    d, s = _daemon(tmp_path)
    assert _read_with_fallback(d, "pb", lambda rs: rs._partition_name,
                               private=private) == "pb"
    got = _read_with_fallback(
        d, "nosuch",
        lambda rs: (rs._partition_id,
                    rs._connect().execute(_CONCEPTS, (rs._partition_id,)).fetchone()[0]),
        private=private)
    created = s._conn.execute(
        "SELECT count(*) FROM partitions WHERE name='nosuch'").fetchone()[0]
    s.close()
    pid, n = got
    assert n == 0, f"answered {n} rows from partition id {pid}"
    assert pid not in (1, 2, 3), pid
    assert created == 0, "a read created the partition"


@pytest.mark.parametrize("private", [False, True])
def test_the_context_op_refuses_an_unknown_partition(tmp_path, private):
    """A typo'd `-p` must not read as "no matches"."""
    from refmatrix.daemon import _read_with_fallback

    d, s = _daemon(tmp_path)
    seen: list = []
    with pytest.raises(ValueError, match="unknown partition 'nosuch'"):
        _read_with_fallback(d, "nosuch", lambda rs: seen.append(rs._partition_id),
                            private=private, missing="raise")
    s.close()
    assert seen == [], f"fn ran on {seen}"


@pytest.mark.parametrize("private", [False, True])
def test_a_partition_newer_than_the_snapshot_answers_from_its_own_rows(tmp_path, private):
    """Created on the writer inside the snapshot debounce: the read stores do
    not have it yet, the writer does. The answer must come from ITS id."""
    from refmatrix.daemon import _read_with_fallback

    d, s = _daemon(tmp_path)
    with s.with_partition("fresh"):
        s.add_concept("fresh_only")
    s._conn.commit()
    want = s._conn.execute("SELECT id FROM partitions WHERE name='fresh'").fetchone()[0]
    got = _read_with_fallback(d, "fresh", lambda rs: rs._partition_id, private=private)
    s.close()
    assert got == want, f"bound id {got}; 'fresh' is {want} (1 = the default partition)"


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

    def info(self, timeout=None, nowait=False):
        # the cached header (nowait=False) always shows the first, idle queue
        if not nowait:
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



def test_with_no_read_store_an_unknown_partition_is_neither_answered_nor_created(tmp_path):
    """K1 (ch-bsd r11 #m-1): the no-snapshot branch (early boot) reads the
    WRITER, whose `with_partition` CREATES a missing row. A read must not."""
    from refmatrix.daemon import _read_with_fallback

    d, s = _daemon(tmp_path)
    d._mem_mirror = None
    d._open_read_store = lambda *a, **k: None       # boot: no snapshot yet
    pid, n = _read_with_fallback(
        d, "nosuch",
        lambda rs: (rs._partition_id,
                    rs._connect().execute(_CONCEPTS, (rs._partition_id,)).fetchone()[0]))
    created = s._conn.execute(
        "SELECT count(*) FROM partitions WHERE name='nosuch'").fetchone()[0]
    with pytest.raises(ValueError, match="unknown partition"):
        _read_with_fallback(d, "nosuch", lambda rs: None, missing="raise")
    s.close()
    assert created == 0 and n == 0 and pid not in (1, 2, 3), (created, n, pid)
