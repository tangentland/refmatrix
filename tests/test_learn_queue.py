"""bug-049 part 2: N greps must not mean N writes.

Bounding the learn RPC (`retries=0`, 2 s) stopped `rmx grep` blocking for 30 s,
but left the cause: every grep miss asks the daemon for a WRITE, each taking
`_store_lock`, on a store whose writer is also serving ingest and watch-flush.
1,165 greps in this project's `query.log` is 1,165 lock acquisitions competing
with the work that made the lock slow in the first place.

So the client appends to a durable queue instead, and the daemon's EXISTING
30 s flush tick drains it — coalesced by pattern, deduped by (file, line),
applied under ONE lock acquisition. The queue also survives a daemon restart,
which the fire-and-forget RPC never did.

Nothing here may fail silently: a malformed line is counted, and a queue that
hits its bound says what it dropped (CLAUDE.md#no-silent-failures).
"""
from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import time

import pytest

from refmatrix import learn_queue as lq


@pytest.fixture
def root():
    td = pathlib.Path(tempfile.mkdtemp(prefix="rmxQ"))
    r = td / ".refmatrix"
    r.mkdir()
    yield r
    shutil.rmtree(td, ignore_errors=True)


def test_enqueue_never_touches_the_daemon(root, monkeypatch):
    """The whole point: the read path stops paying for a write."""
    import socket

    def _boom(*a, **k):
        raise AssertionError("enqueue opened a socket")

    monkeypatch.setattr(socket, "socket", _boom)
    n = lq.enqueue(root, "pat", [{"file": "a.py", "line": 3}])
    assert n == 1


def test_drain_coalesces_by_pattern_and_dedupes_hits(root):
    lq.enqueue(root, "alpha", [{"file": "a.py", "line": 1}])
    lq.enqueue(root, "alpha", [{"file": "a.py", "line": 1},
                               {"file": "b.py", "line": 7}])
    lq.enqueue(root, "beta", [{"file": "c.py", "line": 2}])

    batch = lq.drain(root)

    assert batch.dropped_malformed == 0
    by = {e["pattern"]: e["hits"] for e in batch.entries}
    assert set(by) == {"alpha", "beta"}
    # three enqueued alpha hits, two distinct
    assert sorted((h["file"], h["line"]) for h in by["alpha"]) == [
        ("a.py", 1), ("b.py", 7)]
    assert by["beta"] == [{"file": "c.py", "line": 2}]


def test_draining_empties_the_queue(root):
    lq.enqueue(root, "alpha", [{"file": "a.py", "line": 1}])
    assert lq.drain(root).entries
    assert lq.drain(root).entries == []


def test_a_write_during_the_drain_is_not_lost(root):
    """The drain rotates the file, so an append racing it lands in the NEXT
    batch rather than being truncated away."""
    lq.enqueue(root, "first", [{"file": "a.py", "line": 1}])
    rotated = lq.rotate(root)          # what drain does first
    lq.enqueue(root, "second", [{"file": "b.py", "line": 2}])

    batch = lq.read_rotated(rotated)
    assert [e["pattern"] for e in batch.entries] == ["first"]
    assert [e["pattern"] for e in lq.drain(root).entries] == ["second"]


def test_a_malformed_line_is_counted_not_silently_skipped(root):
    lq.enqueue(root, "good", [{"file": "a.py", "line": 1}])
    with lq.queue_path(root).open("a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")

    batch = lq.drain(root)

    assert [e["pattern"] for e in batch.entries] == ["good"]
    assert batch.dropped_malformed == 1


def test_the_queue_is_bounded_and_says_what_it_dropped(root, monkeypatch):
    """A grep loop must not be able to fill the disk, and must not be able to
    lose work quietly either."""
    monkeypatch.setattr(lq, "MAX_QUEUE_LINES", 5)
    for i in range(12):
        lq.enqueue(root, f"p{i}", [{"file": "a.py", "line": i}])

    batch = lq.drain(root)

    assert len(batch.entries) <= 5
    assert batch.dropped_overflow == 7, (
        f"overflow was not counted: {batch}")
    # The NEWEST work survives: an old pattern is likelier already learned.
    assert [e["pattern"] for e in batch.entries][-1] == "p11"


def test_an_absent_queue_drains_to_nothing(root):
    batch = lq.drain(root)
    assert batch.entries == []
    assert batch.dropped_malformed == 0
    assert batch.dropped_overflow == 0


def test_hits_without_a_usable_shape_are_counted(root):
    lq.enqueue(root, "p", [{"file": "a.py", "line": 1}, {"nope": True}])
    batch = lq.drain(root)
    assert batch.entries[0]["hits"] == [{"file": "a.py", "line": 1}]
    assert batch.dropped_malformed == 1


# ---- the daemon side: one lock acquisition for the whole batch -------------


def _daemon_with_store(root):
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store

    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s
    d._log = lambda m: d.__dict__.setdefault("_logs", []).append(m)
    return d


def test_the_drain_applies_queued_hits_to_the_graph(root, tmp_path):
    """End to end: what the CLI queued is what the graph learns."""
    proj = root.parent
    f = proj / "sample.py"
    f.write_text("def target():\n    return 1\n", encoding="utf-8")

    d = _daemon_with_store(root)
    lq.enqueue(root, "target", [{"file": str(f), "line": 1}])

    report = d._drain_learn_queue()

    assert report["patterns"] == 1
    assert report["applied"] >= 1, f"nothing landed: {report}"
    assert lq.pending_lines(root) == 0
    d.store.close()


def test_the_drain_yields_the_writer_lock_between_entries(root):
    """SUPERSEDED CONTRACT. This test first asserted the drain took the lock
    exactly ONCE for the whole batch — which is starvation written as a test:
    a long batch would hold the writer against ingest, recall and save-state,
    trading the CLI's 30 s wall for a stalled daemon.

    The lock is taken PER ENTRY and released in between. Coalescing is what
    makes the queue cheap (N greps become M patterns with duplicate hits folded
    away); it was never the single acquisition. Releasing mid-batch is safe
    because each entry is its own write — the lock is never released inside an
    `s.transaction()`, which is the rule `ingest_path` follows.
    """
    proj = root.parent
    f = proj / "sample.py"
    f.write_text("x = 1\n", encoding="utf-8")

    d = _daemon_with_store(root)
    for i in range(8):
        lq.enqueue(root, f"pattern{i}", [{"file": str(f), "line": 1}])

    acquisitions = {"n": 0}
    real_lock = d._store_lock

    class _CountingLock:
        def __enter__(self):
            acquisitions["n"] += 1
            return real_lock.__enter__()

        def __exit__(self, *a):
            return real_lock.__exit__(*a)

    d._store_lock = _CountingLock()
    report = d._drain_learn_queue()
    d._store_lock = real_lock

    assert report["patterns"] == 8
    assert acquisitions["n"] == 8, (
        f"the drain took the writer lock {acquisitions['n']} times for 8 "
        f"entries; it must take it per entry and release in between so other "
        f"ops are not starved")
    d.store.close()


def test_another_thread_gets_the_writer_lock_DURING_the_drain(root, monkeypatch):
    """The property that actually matters, asserted on real evidence: a
    competing op gets the writer WHILE entries are still unprocessed, not
    after the batch finishes.

    The competitor records how many entries the drain had completed at the
    moment it won the lock. If the drain held the lock for the batch, that
    number would equal the total.
    """
    import threading
    from refmatrix import daemon as dmod

    proj = root.parent
    f = proj / "sample.py"
    f.write_text("x = 1\n", encoding="utf-8")

    d = _daemon_with_store(root)
    total = 20
    for i in range(total):
        lq.enqueue(root, f"pattern{i}", [{"file": str(f), "line": 1}])

    progress = {"done": 0}
    real_learn = dmod._learn_grep_hits

    def _slow_learn(store, pattern, hits, project_root):
        time.sleep(0.01)                       # make the window observable
        r = real_learn(store, pattern, hits, project_root)
        progress["done"] += 1
        return r

    monkeypatch.setattr(dmod, "_learn_grep_hits", _slow_learn)

    won_at = {"n": None}
    started = threading.Event()

    def _competitor():
        while progress["done"] < 1 and not started.is_set():
            time.sleep(0.001)
        with d._store_lock:
            won_at["n"] = progress["done"]

    ct = threading.Thread(target=_competitor, daemon=True)
    ct.start()
    d._drain_learn_queue()
    started.set()
    ct.join(10.0)

    assert won_at["n"] is not None, "the competing op never got the writer lock"
    assert won_at["n"] < total, (
        f"the competitor only got the lock after {won_at['n']}/{total} entries "
        f"— the drain held the writer for the whole batch")
    d.store.close()


def test_the_drain_stops_at_its_budget_and_requeues_the_rest(root, monkeypatch):
    """A tick must not run long just because the queue is deep. What it does
    not reach goes BACK on the queue — dropping work to make a tick look fast
    is the cheap fix this project names."""
    from refmatrix import daemon as dmod

    proj = root.parent
    f = proj / "sample.py"
    f.write_text("x = 1\n", encoding="utf-8")

    d = _daemon_with_store(root)
    for i in range(10):
        lq.enqueue(root, f"pattern{i}", [{"file": str(f), "line": 1}])

    monkeypatch.setattr(dmod, "LEARN_DRAIN_BUDGET_S", -1.0)   # budget already spent
    report = d._drain_learn_queue()

    assert report["applied"] == 0
    assert lq.pending_lines(root) == 10, "the untouched entries were lost"
    logs = " ".join(d.__dict__.get("_logs", []))
    assert "budget" in logs and "requeued" in logs, logs
    d.store.close()


def test_a_shutdown_mid_drain_requeues_instead_of_dropping(root):
    proj = root.parent
    f = proj / "sample.py"
    f.write_text("x = 1\n", encoding="utf-8")

    d = _daemon_with_store(root)
    for i in range(6):
        lq.enqueue(root, f"pattern{i}", [{"file": str(f), "line": 1}])
    d._shutdown_event.set()

    report = d._drain_learn_queue()

    assert report["applied"] == 0
    assert lq.pending_lines(root) == 6
    assert "shutdown" in " ".join(d.__dict__.get("_logs", []))
    d.store.close()


def test_an_empty_queue_is_a_cheap_no_op(root):
    d = _daemon_with_store(root)
    report = d._drain_learn_queue()
    assert report == {"applied": 0, "patterns": 0}
    assert d.__dict__.get("_logs", []) == [], "a quiet tick must not log"
    d.store.close()


def test_losses_are_named_in_the_log(root, monkeypatch):
    monkeypatch.setattr(lq, "MAX_QUEUE_LINES", 2)
    proj = root.parent
    f = proj / "sample.py"
    f.write_text("x = 1\n", encoding="utf-8")
    d = _daemon_with_store(root)
    for i in range(5):
        lq.enqueue(root, f"p{i}", [{"file": str(f), "line": 1}])
    with lq.queue_path(root).open("a", encoding="utf-8") as fh:
        fh.write("{broken\n")

    d._drain_learn_queue()

    logs = " ".join(d.__dict__.get("_logs", []))
    assert "malformed" in logs and "over queue cap" in logs, logs
    d.store.close()


def test_health_reports_the_queue_depth(root):
    """A queue nothing reports is a quieter way to lose work: if the flush tick
    stops draining, the only symptom is retrieval slowly getting worse."""
    from refmatrix.daemon import _store_health

    d = _daemon_with_store(root)
    assert _store_health(d).get("learn_queue_pending") == 0
    lq.enqueue(root, "a", [{"file": "x.py", "line": 1}])
    lq.enqueue(root, "b", [{"file": "x.py", "line": 2}])
    assert _store_health(d).get("learn_queue_pending") == 2
    d.store.close()
