"""ch-bsd r8 #s-2: the context op's rerank never holds the WRITER lock.

2cd73b9 made every natural-language `context` op rerank, and `_op_context`
ran `build_context` (and so the model's `score`) inside `d._store_lock`, with
a reranker that had no deadline: a busy shared worker could hold the writer
for SHARED_OP_TIMEOUT_S (45 s), the lock-holding wedge class of bug-085.

The op now builds on the read path (`_read_with_fallback`, as `describe` and
`memory_get` do) and gives its reranker a budget. The model worker is the
external boundary stubbed here; the store, the op and context building are
real.
"""
from __future__ import annotations

import json
import threading

import pytest

from refmatrix.ingest import ingest_path
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    body = ("The daemon was SIGKILLed by macOS jetsam under memory pressure "
            "while the embed worker held the model. ") * 4
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(3):
        (docs / f"deaths{i}.md").write_text(f"# Death {i}\n\n{body}\n")
    ingest_path(s, docs)
    yield s
    s.close()


class _D:
    def __init__(self, st, *, read_store):
        self.store = st
        self._store_lock = threading.RLock()
        self._read = read_store
        self.lock_free_during_score: list[bool] = []
        self.budgets: list = []
        d = self

        class _RR:
            def with_budget(self, budget_s):
                d.budgets.append(budget_s)
                return self

            def score(self, query, docs):
                got: list[bool] = []

                def probe():
                    ok = d._store_lock.acquire(blocking=False)
                    got.append(ok)
                    if ok:          # released by the thread that took it
                        d._store_lock.release()

                t = threading.Thread(target=probe)
                t.start()
                t.join()
                d.lock_free_during_score.append(got[0])
                return [0.0] * len(docs)

        self._rr = _RR()

    def _st(self):
        return self.store

    def _open_read_store(self, partition, **kw):
        return self._read

    def _request_snapshot(self):
        pass

    def _log(self, msg):
        pass

    def _maybe_rerank(self, args):
        return True

    def _reranker(self):
        return self._rr


def test_the_phrase_rerank_runs_with_the_writer_lock_free(store, monkeypatch):
    from refmatrix.daemon import _op_context

    monkeypatch.setenv("RMX_CONTEXT_RERANK_S", "2.5")
    # The read store IS a Store; `_read_with_fallback` closes it, so hand it
    # a second handle on the same catalog.
    read = Store(store.root, read_only=False)
    d = _D(store, read_store=read)

    resp = _op_context(d, {"ref": "memory pressure", "format": "json",
                           "grep_backstop": False})

    assert json.loads(resp["body"])["groups"], resp
    assert d.lock_free_during_score == [True], d.lock_free_during_score
    assert d.budgets == [2.5]


def test_with_no_read_store_the_fallback_is_still_budgeted(store):
    from refmatrix.daemon import _op_context

    d = _D(store, read_store=None)
    _op_context(d, {"ref": "memory pressure", "format": "json", "grep_backstop": False})
    assert d.budgets and d.budgets[0] is not None and d.budgets[0] > 0
