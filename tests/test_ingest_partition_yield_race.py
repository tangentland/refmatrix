"""bug-098: two cooperative daemon ingests write into each other's partition.

`_op_ingest_path` and the ingest-gmd job both bind the ONE shared writer
Store's partition (`with_partition`) and keep it bound across `_yield()`, which
releases `_store_lock`. Job A yields; job B takes the lock, binds its own
partition, and yields while still bound; A reacquires and writes into B's
partition. On 2026-10-08 a forced `rmx reingest` of the refmatrix store wrote
383 doc + 13 code + 221 concept rows, and its `ingest`/`semantic` derive
stamps, into `sessions-refmatrix` — while the hook's session-card ingest-gmd
job ran — and that partition had accumulated 2,658 code + 401 doc rows of the
project tree over time.

Real Store, real `_FairLock`, the real daemon ops; only the scheduling is
forced (yield on every unit) so the interleave happens in a test's time.
"""
from __future__ import annotations

import threading
import time
from collections import deque

import pytest

from refmatrix.store import Store


def _daemon(root):
    from refmatrix.daemon import Daemon, _FairLock

    s = Store(root, backend="duckdb")
    s.init()
    d = object.__new__(Daemon)
    d.root = root
    d.store = s
    d._store_lock = _FairLock()
    d._log = lambda *a, **k: None
    d._request_snapshot = lambda: None
    d._ingest_jobs = {}
    d._ingest_jobs_lock = threading.Lock()
    d._shutdown_event = threading.Event()
    d.memory_only = False
    return d, s


def _tree(base):
    proj = base / "proj"
    proj.mkdir()
    for i in range(30):
        (proj / f"note{i}.md").write_text(
            f"# Note {i}\n\nThe watcher flush re-synced file {i} under the store lock.\n")
        (proj / f"mod{i}.py").write_text(
            f"def handler_{i}(x):\n    return x + {i}\n")
    cards = base / "cards"
    cards.mkdir()
    files = []
    for i in range(30):
        p = cards / f"card{i}.md"
        p.write_text(f'---\ngmd: "0.1"\nid: card-{i}\ntitle: "Card {i}"\ntags: [session]\n---\n'
                     f"# Card {i} {{#root}}\n\nSession card {i} body.\n")
        files.append(p)
    return proj, files


def _pid(s, name):
    row = s._conn.execute("SELECT id FROM partitions WHERE name=?", (name,)).fetchone()
    return row[0] if row else None


def test_two_cooperative_ingests_never_write_into_each_others_partition(tmp_path, monkeypatch):
    from refmatrix.daemon import _op_ingest_path, _run_ingest_gmd_body

    monkeypatch.setenv("RMX_INGEST_YIELD_EVERY_UNITS", "1")
    monkeypatch.setenv("RMX_INGEST_YIELD_EVERY", "1")
    monkeypatch.setenv("RMX_INGEST_YIELD_SLEEP_S", "0.002")
    d, s = _daemon(tmp_path / ".refmatrix")
    proj, cards = _tree(tmp_path)
    home = s._partition_name
    with s.with_partition("sessions-x"):           # exists before either job starts
        pass
    s._conn.commit()
    d._ingest_jobs["j1"] = {"events": deque(maxlen=1000), "next_seq": 0,
                            "status": "running"}
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def a():
        try:
            barrier.wait()
            _op_ingest_path(d, {"path": str(proj), "semantic": True})
        except BaseException as exc:  # noqa: BLE001 — surfaced below
            errors.append(exc)

    def b():
        try:
            barrier.wait()
            time.sleep(0.05)       # land in the middle of A's run
            _run_ingest_gmd_body(d, "j1", cards, {"partition": "sessions-x"})
        except BaseException as exc:  # noqa: BLE001 — surfaced below
            errors.append(exc)

    ts = [threading.Thread(target=a), threading.Thread(target=b)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(120)
    assert not errors, errors

    home_id, sess_id = _pid(s, home), _pid(s, "sessions-x")
    con = s._conn
    stray_project = con.execute(
        "SELECT kind, name FROM entities WHERE partition_id=? AND kind IN ('code','doc') "
        "AND name NOT LIKE 'card%'", (sess_id,)).fetchall()
    stray_cards = con.execute(
        "SELECT name FROM entities WHERE partition_id=? AND name LIKE 'card%'",
        (home_id,)).fetchall()
    stamps = {(r[0], r[1]) for r in con.execute(
        "SELECT partition_id, pass_name FROM derive_stamps").fetchall()}
    s.close()
    assert stray_project == [], f"{len(stray_project)} project rows in the sessions partition"
    assert stray_cards == [], f"{len(stray_cards)} session-card rows in the project partition"
    assert (sess_id, "ingest") not in stamps and (sess_id, "semantic") not in stamps, stamps
    assert (home_id, "ingest") in stamps and (sess_id, "gmd") in stamps, stamps


# ---- the other direction: a lock-FREE op re-binding the writer's partition ----
#
# Found by the sweep for every way the shared writer's binding can change while
# its owner holds `_store_lock` (bug-098). `ping` (every hub watchdog tick) ran
# `_store_health`, which looped `with_partition` over every partition ON THE
# WRITER without the lock; `memory_score` and `memory_recall`'s concept
# prefilter did the same from the lock-free cli pool. Each such re-bind lands
# any write in flight under the lock in the wrong partition.

import numpy as np  # noqa: E402


def _writer_binding_moves(d, op, seconds=1.0):
    """Hold the lock with the writer bound to `pa` (an ingest's shape) while
    `op` runs on another thread; return every foreign binding observed."""
    s = d.store
    moved: list = []
    started, stop = threading.Event(), threading.Event()

    def writer():
        with d._store_lock, s.with_partition("pa"):
            want = s._partition_id
            started.set()
            while not stop.is_set():
                if s._partition_id != want:
                    moved.append(s._partition_name)
                time.sleep(0.0002)

    w = threading.Thread(target=writer)
    w.start()
    started.wait()
    errs: list = []

    def run():
        try:
            for _ in range(20):
                op()
        except Exception as exc:  # noqa: BLE001 — the op's own failure is not the subject
            errs.append(exc)

    o = threading.Thread(target=run, daemon=True)
    o.start()
    time.sleep(seconds)
    stop.set()
    w.join()
    o.join(10)
    return moved


def _read_daemon(tmp_path):
    from tests.test_read_path_partition_and_budget import _daemon
    return _daemon(tmp_path)


def test_ping_health_never_rebinds_the_writer(tmp_path):
    from refmatrix.daemon import _store_health

    d, s = _read_daemon(tmp_path)
    moved = _writer_binding_moves(d, lambda: _store_health(d))
    s.close()
    assert moved == [], f"the writer was re-bound {len(moved)}x: {sorted(set(moved))}"


def test_memory_score_never_rebinds_the_writer(tmp_path):
    from refmatrix.daemon import _op_memory_score

    d, s = _read_daemon(tmp_path)
    moved = _writer_binding_moves(
        d, lambda: _op_memory_score(d, {"concept": "beta_only", "partition": "pb"}))
    s.close()
    assert moved == [], f"the writer was re-bound {len(moved)}x: {sorted(set(moved))}"


def test_the_recall_prefilter_never_rebinds_the_writer(tmp_path):
    from refmatrix.daemon import _op_memory_recall

    class _Emb:
        dim = 4
        model_name = "stub"

        def embed_texts(self, texts):
            return np.array([[1.0, 0.5, 0.25, 0.125]] * len(texts), dtype="float32")

    d, s = _read_daemon(tmp_path)
    d._embedder = lambda: _Emb()
    d._maybe_rerank = lambda args: False
    moved = _writer_binding_moves(
        d, lambda: _op_memory_recall(d, {"query": "beta_only", "partition": "pb",
                                         "prefilter": True, "k": 3}))
    s.close()
    assert moved == [], f"the writer was re-bound {len(moved)}x: {sorted(set(moved))}"
