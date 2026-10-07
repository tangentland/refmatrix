"""ch-bsd r10 #m-1: side effects of splitting `_op_embed` into three phases.

r9 #s-1 moved the encode outside `_store_lock`. That opened three gaps r10
named and mutation-tested:

- two concurrent embed ops (save-state's `drain_memory_vectors` beside an
  `embed_start` job or `rmx embed`) select the SAME pending rows and the
  shared worker encodes them twice;
- a batch whose every row changed mid-encode returns `embedded=0` with rows
  pending, and both loops read `embedded == 0` as "done" — the CLI then
  stamps a COMPLETE embed derive pass over a partition with rows pending.
  `changed_while_encoding` had no reader (E3 survived);
- the `_PrecomputedQuery` refusal (R2) and the watch flush's vector-delete
  ACCUMULATION across roots (V16) were unpinned.

Real store and real `_op_embed`; the embedder is the model boundary.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from refmatrix.store import Store

BODY = ("The daemon was SIGKILLed by macOS jetsam under memory pressure while the "
        "embed worker held the model. ") * 4


class _SlowEmb:
    dim = 4
    model_name = "stub-embedder"

    def __init__(self, delay=0.3):
        self.delay = delay
        self.encoded: list[str] = []
        self._lk = threading.Lock()

    def embed_texts(self, texts):
        time.sleep(self.delay)
        with self._lk:
            self.encoded.extend(texts)
        return np.array([[1.0, 0.5, 0.25, 0.125]] * len(texts), dtype="float32")


class _D:
    def __init__(self, st, emb):
        self.store = st
        self._store_lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._emb = emb
        self.logged: list[str] = []

    def _st(self):
        return self.store

    def _embedder(self):
        return self._emb

    def _request_snapshot(self):
        pass

    def _log(self, msg):
        self.logged.append(msg)


def test_two_concurrent_embed_ops_encode_each_row_once(tmp_path):
    from refmatrix.daemon import _op_embed

    s = Store(tmp_path / ".refmatrix")
    s.init()
    for i in range(3):
        s.add_memory(name=f"e{i}", content=BODY + str(i))
    emb = _SlowEmb()
    d = _D(s, emb)
    outs: list[dict] = []
    barrier = threading.Barrier(2)

    def run():
        barrier.wait()
        outs.append(_op_embed(d, {"kinds": ["memory"], "limit": 10}))

    ts = [threading.Thread(target=run) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    s.close()
    assert len(emb.encoded) == 3, f"encoded {len(emb.encoded)} texts for 3 rows: {outs}"
    assert sorted(o["embedded"] for o in outs) == [0, 3], outs


# ---- the loops read `changed_while_encoding` -----------------------------

def test_drain_retries_a_batch_that_changed_entirely_while_encoding():
    from refmatrix.ingest_gmd import drain_memory_vectors

    replies = iter([
        {"embedded": 0, "remaining": 3, "changed_while_encoding": 3},
        {"embedded": 3, "remaining": 0, "changed_while_encoding": 0},
    ])
    out = drain_memory_vectors(lambda args: next(replies), partition="m", batches=5)
    assert out["error"] is None, out
    assert out["embedded"] == 3 and out["remaining"] == 0 and out["batches"] == 2, out


def test_drain_still_stops_on_a_batch_that_can_make_no_progress():
    from refmatrix.ingest_gmd import drain_memory_vectors

    calls = []

    def batch(args):
        calls.append(args)
        return {"embedded": 0, "remaining": 3, "changed_while_encoding": 0}

    out = drain_memory_vectors(batch, partition="m", batches=5)
    assert len(calls) == 1 and out["remaining"] == 3, out


@pytest.mark.parametrize("result,streak,want", [
    # rows changed under the encode: go again, they are still pending
    ({"embedded": 0, "remaining": 3, "changed_while_encoding": 3}, 0, "again"),
    # ...but not forever: a row rewritten on every pass is a partial pass
    ({"embedded": 0, "remaining": 3, "changed_while_encoding": 3}, 3, "partial"),
    # nothing pending: a complete pass
    ({"embedded": 5, "remaining": 0}, 0, "complete"),
    ({"embedded": 0, "remaining": 0, "skipped_empty": 4}, 0, "complete"),
    # no progress and rows still pending: NOT a complete pass
    ({"embedded": 0, "remaining": 3, "changed_while_encoding": 0}, 0, "partial"),
    # progress, rows left: next batch
    ({"embedded": 2, "remaining": 3}, 0, "again"),
])
def test_the_cli_embed_loop_verdict(result, streak, want):
    """Only `complete` lets `rmx embed` stamp the derive pass (task 15.4)."""
    from refmatrix.cli import _embed_batch_verdict

    assert _embed_batch_verdict(result, changed_streak=streak) == want


def test_the_cli_embed_loop_uses_the_verdict():
    """The verdict is THE decision, not a parallel copy of it."""
    from pathlib import Path

    from refmatrix import cli

    # from disk, not inspect: a mutation run edits src/ under a loaded module
    src = Path(cli.__file__).read_text()
    loop = src[src.index("total_embedded = 0\n    total_degraded"):]
    loop = loop[:loop.index("_stamp_derive_pass(root, part, \"embed\")")]
    assert "_embed_batch_verdict(" in loop
    assert "if embedded == 0 or remaining == 0" not in loop


# ---- R2 / V16 ------------------------------------------------------------

def test_the_precomputed_query_refuses_any_other_text():
    from refmatrix.daemon import _PrecomputedQuery

    vec = np.array([[1.0, 0.0]], dtype="float32")
    pq = _PrecomputedQuery(_SlowEmb(), "daemon jetsam", vec)
    assert pq.embed_texts(["daemon jetsam"]) is vec
    with pytest.raises(RuntimeError, match="under _store_lock"):
        pq.embed_texts(["something else"])
    with pytest.raises(RuntimeError):
        pq.embed_texts(["daemon jetsam", "daemon jetsam"])


def test_the_watch_flush_sums_vector_delete_failures_across_roots():
    from refmatrix.daemon import _sum_sync_reports

    tot = _sum_sync_reports([
        {"added": 1, "updated": 2, "purged": 3, "vector_delete_failed": 2},
        {"added": 4, "updated": 0, "purged": 1, "vector_delete_failed": 5,
         "cancelled": True},
        {"added": 0, "updated": 1, "purged": 0},
    ])
    assert tot == {"added": 5, "updated": 3, "purged": 4,
                   "vector_delete_failed": 7, "cancelled": True}


def test_the_watch_flush_uses_the_sum():
    from pathlib import Path

    from refmatrix import daemon

    src = Path(daemon.__file__).read_text()
    assert "_sum_sync_reports(" in src
    assert "total_vec_failed +=" not in src
