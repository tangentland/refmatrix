"""bug-025 / todo G13: the rerank worker never said what it costs.

7/7 runs of the exact deployed hook argv burned the full 5 s budget with
`rerank failed (TimeoutError: timed out)` and 0 of 5 rows reranked, returning
exactly what `--no-rerank` returns in 0.79 s. bug-019's fix capped the pool
until ONE measurement fit; the cost was never made KNOWABLE to the caller, and
the same capped 10 x 700 pool took 9.26 / 14.08 / 3.72 s on three consecutive
tries.

Two halves, and both are required: a caller that skips politely while the
abandoned request keeps scoring has fixed nothing — the next caller's 1 s probe
still queues behind it.
"""
from __future__ import annotations

import io
import time

import pytest

from refmatrix import reranker as rr


# ---- half 1: the arithmetic ---------------------------------------------

def test_estimate_multiplies_by_the_queue_ahead_of_us():
    info = {"cost_s_per_doc": 0.4, "queue_depth": 2}
    assert rr.estimate_rerank_s(info, 10) == pytest.approx(12.0)


def test_estimate_with_an_empty_queue_is_the_single_caller_case():
    assert rr.estimate_rerank_s({"cost_s_per_doc": 0.4, "queue_depth": 0}, 5) \
        == pytest.approx(2.0)


def test_estimate_is_none_when_the_worker_has_no_samples():
    """An EMA with no samples reports nothing; a guess would be worse than
    silence, because the caller would act on it."""
    assert rr.estimate_rerank_s({"cost_s_per_doc": None, "queue_depth": 0}, 5) is None
    assert rr.estimate_rerank_s({}, 5) is None
    assert rr.estimate_rerank_s({"cost_s_per_doc": 0.4}, 0) == 0.0


# ---- half 1: the decision, in ONE place ---------------------------------

class _StubClient:
    def __init__(self, info: dict, *, scores=None):
        self._info = dict(info)
        self.calls: list[dict] = []
        self._scores = scores

    def info(self, *, timeout=None) -> dict:
        return self._info

    def call(self, op, payload=None, *, blob=None, timeout=None):
        self.calls.append({"op": op, **(payload or {})})
        n = len((payload or {}).get("docs") or [])
        return ({"ok": True, "scores": self._scores or [1.0] * n}, b"")


def test_a_pool_that_cannot_fit_is_skipped_with_the_numbers():
    """The incident shape: 0.42 s/doc, 2 queued, 10 docs, 3.8 s left."""
    c = _StubClient({"cost_s_per_doc": 0.42, "queue_depth": 2})
    r = rr.RemoteReranker(c, budget_s=3.8)
    with pytest.raises(rr.RerankSkipped) as e:
        r.score("q", ["doc"] * 10)
    msg = str(e.value)
    assert "10 docs" in msg and "0.42" in msg and "2 queued" in msg
    assert "3.8" in msg or "3.7" in msg          # remaining budget, named
    assert c.calls == [], "a skipped rerank must not reach the worker"


def test_the_same_pool_runs_when_the_budget_covers_it():
    c = _StubClient({"cost_s_per_doc": 0.42, "queue_depth": 2})
    r = rr.RemoteReranker(c, budget_s=30.0)
    assert r.score("q", ["doc"] * 10) == [1.0] * 10
    assert c.calls[0]["op"] == "rerank"


def test_an_unknown_cost_does_not_block_the_rerank():
    """No samples yet — the caller cannot refuse on data it does not have."""
    c = _StubClient({"cost_s_per_doc": None, "queue_depth": 0})
    r = rr.RemoteReranker(c, budget_s=1.0)
    assert r.score("q", ["a", "b"]) == [1.0, 1.0]


def test_a_reranker_with_no_budget_never_skips():
    c = _StubClient({"cost_s_per_doc": 99.0, "queue_depth": 9})
    r = rr.RemoteReranker(c)
    assert r.score("q", ["a"]) == [1.0]


def test_the_budget_shrinks_with_wall_clock(monkeypatch):
    """The budget is a DEADLINE, not a constant: a probe that ate 4 of 5 s
    leaves 1 s for the scoring decision, which is the live shape of bug-019."""
    now = [1000.0]
    monkeypatch.setattr(rr.time, "time", lambda: now[0])
    c = _StubClient({"cost_s_per_doc": 0.2, "queue_depth": 0})
    r = rr.RemoteReranker(c, budget_s=5.0)          # deadline = 1005
    now[0] = 1004.0                                  # 1 s left; 10 docs = 2 s
    with pytest.raises(rr.RerankSkipped):
        r.score("q", ["doc"] * 10)


def test_shared_reranker_carries_its_timeout_as_the_budget(monkeypatch):
    monkeypatch.setattr(rr, "rerank_enabled", lambda: True)
    monkeypatch.setattr(rr, "rerank_available", lambda: True)
    made = {}

    class _C(_StubClient):
        def __init__(self, role, **kw):
            super().__init__({"cost_s_per_doc": 0.1, "queue_depth": 0})
            made["timeout"] = kw.get("timeout")

    from refmatrix import modelsrv
    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", _C)
    r = rr.shared_reranker(timeout=7.0, probe_timeout=1.0)
    assert r is not None and made["timeout"] == 7.0
    assert r._deadline is not None


# ---- half 2: an expired frame is dropped --------------------------------

class _CountingReranker:
    def __init__(self, *a, **kw):
        self.scored = 0
        self.model_name = "stub"

    def _load(self):
        pass

    def score(self, query, docs):
        self.scored += 1
        return [1.0] * len(docs)


def _run_worker(frames: list[dict], monkeypatch) -> tuple[list[dict], _CountingReranker]:
    """Drive the REAL worker loop over in-memory pipes."""
    from refmatrix import embed_worker as ew
    from refmatrix.subproc import recv_frame, send_frame

    stub = _CountingReranker()
    monkeypatch.setattr("refmatrix.reranker.Reranker", lambda *a, **kw: stub)

    inbuf = io.BytesIO()
    for f in frames:
        send_frame(inbuf, f)
    inbuf.seek(0)
    outbuf = io.BytesIO()
    monkeypatch.setattr(ew, "CHAN_IN", inbuf)
    monkeypatch.setattr(ew, "CHAN_OUT", outbuf)
    ew.main(["--role", "rerank"])
    outbuf.seek(0)
    out = []
    while True:
        try:
            hdr, _ = recv_frame(outbuf)
        except EOFError:
            break
        out.append(hdr)
    return out, stub


def test_a_frame_whose_deadline_passed_is_never_scored(monkeypatch):
    out, stub = _run_worker([{
        "op": "rerank", "query": "q", "docs": ["a", "b"],
        "deadline": time.time() - 3.0,
    }], monkeypatch)
    assert out[0]["ok"] is False
    assert "deadline expired" in out[0]["error"]
    assert stub.scored == 0, "the worker scored a request its caller abandoned"


def test_a_frame_with_a_live_deadline_is_scored(monkeypatch):
    out, stub = _run_worker([{
        "op": "rerank", "query": "q", "docs": ["a", "b"],
        "deadline": time.time() + 60.0,
    }], monkeypatch)
    assert out[0]["ok"] is True and out[0]["scores"] == [1.0, 1.0]
    assert stub.scored == 1


def test_the_worker_reports_its_cost_after_it_has_measured_one(monkeypatch):
    out, _ = _run_worker([
        {"op": "info"},
        {"op": "rerank", "query": "q", "docs": ["a", "b", "c"]},
        {"op": "info"},
    ], monkeypatch)
    assert out[0]["cost_s_per_doc"] is None and out[0]["scored_docs"] == 0
    assert out[2]["scored_docs"] == 3
    assert out[2]["cost_s_per_doc"] is not None and out[2]["cost_s_per_doc"] >= 0.0


def test_the_ema_moves_toward_a_slow_call():
    from refmatrix.embed_worker import _RerankRole

    role = _RerankRole.__new__(_RerankRole)
    role._ema = None
    role._scored_docs = 0
    role._observe(1.0, 10)              # 0.1 s/doc, first sample seeds
    assert role._ema == pytest.approx(0.1)
    role._observe(10.0, 10)             # 1.0 s/doc
    assert 0.1 < role._ema < 1.0
    fast_then = role._ema
    role._observe(0.1, 10)              # 0.01 s/doc
    assert role._ema < fast_then


# ---- the server's half of the cost ---------------------------------------

def test_the_server_adds_its_queue_depth_to_info(monkeypatch):
    """The hub knows how many callers are waiting on a role and has never
    said so. Without it every caller estimates as if it were alone."""
    from refmatrix import modelsrv

    class _W:
        def __init__(self, *a, **kw):
            pass

        def call(self, op, payload=None, *, blob=None, timeout=None):
            return ({"ok": True, "model": "stub", "cost_s_per_doc": 0.2}, b"")

        def close(self, *, timeout=0.0):
            pass

    srv = modelsrv.ModelServer()
    monkeypatch.setattr(modelsrv, "WorkerClient", _W)
    srv._pending["rerank"] = 3
    hdr = srv._augment_info("rerank", {"ok": True, "model": "stub",
                                       "cost_s_per_doc": 0.2})
    assert hdr["queue_depth"] == 2          # ahead of the caller being served
    srv._pending["rerank"] = 0
    assert srv._augment_info("rerank", {"ok": True})["queue_depth"] == 0


def test_the_client_stamps_a_deadline_from_its_own_timeout(monkeypatch):
    """A bounded client cannot forget: if it gave itself N seconds, the frame
    says so, and a worker that dequeues it late drops it."""
    from refmatrix import modelsrv

    sent = {}

    class _FakeSock:
        def settimeout(self, t):
            pass

    c = modelsrv.SharedWorkerClient("rerank", timeout=5.0)
    c._sock = _FakeSock()
    c._rw = object()
    monkeypatch.setattr(c, "_call_once",
                        lambda req, blob: (sent.update(req) or ({"ok": True}, b"")))
    t0 = time.time()
    c.call("rerank", {"query": "q", "docs": ["a"]}, timeout=4.0)
    assert t0 + 3.5 <= sent["deadline"] <= t0 + 4.5


# ---- the call sites ------------------------------------------------------

class _FakeStore:
    def with_partition(self, name):
        from contextlib import contextmanager

        @contextmanager
        def _s():
            yield self
        return _s()


def _wire_replica_leg(monkeypatch, *, cost, queue, scores=None):
    """Stand the replica recall leg up with everything below the rerank
    decision faked, so the test is about the DECISION."""
    from refmatrix import cli as cli_mod
    from refmatrix import modelsrv, recall
    from refmatrix.embedder import RemoteEmbedder

    monkeypatch.setenv("RMX_RECALL_REPLICA_FIRST", "1")
    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient",
                        lambda role, **kw: _StubClient({"cost_s_per_doc": cost,
                                                        "queue_depth": queue}))
    monkeypatch.setattr(RemoteEmbedder, "__init__", lambda self, c: None)
    monkeypatch.setattr(cli_mod, "_reader_store", lambda: _FakeStore())
    monkeypatch.setattr(cli_mod, "_resolve_partition", lambda: "p")
    hits = [(i, 0.5 - i / 100) for i in range(1, 11)]
    monkeypatch.setattr(recall, "dense_recall",
                        lambda *a, **kw: list(hits))
    monkeypatch.setattr(recall, "hybrid_memory_recall",
                        lambda *a, **kw: list(hits))
    client = _StubClient({"cost_s_per_doc": cost, "queue_depth": queue},
                         scores=scores)
    monkeypatch.setattr(rr, "shared_reranker",
                        lambda log=None, timeout=None, probe_timeout=None:
                        rr.RemoteReranker(client, budget_s=timeout))
    monkeypatch.setattr(rr, "collect_rerank_docs",
                        lambda s, h, **kw: ([(e, "body " * 40) for e, _ in h[:10]],
                                            [], []))
    return client


def test_the_replica_recall_leg_skips_and_says_the_numbers(monkeypatch):
    from refmatrix import cli as cli_mod

    client = _wire_replica_leg(monkeypatch, cost=0.42, queue=2)
    ws: list[str] = []
    rows = cli_mod._replica_memory_recall(
        "why did the daemon restart", k=5, kinds=["memory"], fuse=False,
        rerank=True, left=lambda default: 3.8, warnings=ws)

    assert rows and not any(r.get("reranked") for r in rows)
    assert any("rerank skipped" in w and "10 docs" in w and "queued" in w
               for w in ws), ws
    assert client.calls == [], "the worker was asked for a pool that cannot fit"


def test_the_replica_recall_leg_reranks_when_the_budget_covers_it(monkeypatch):
    from refmatrix import cli as cli_mod

    client = _wire_replica_leg(monkeypatch, cost=0.05, queue=0)
    ws: list[str] = []
    rows = cli_mod._replica_memory_recall(
        "why did the daemon restart", k=5, kinds=["memory"], fuse=False,
        rerank=True, left=lambda default: 30.0, warnings=ws)

    assert rows and all(r.get("reranked") for r in rows)
    assert [c["op"] for c in client.calls] == ["rerank"]
    assert "deadline" in client.calls[0], "the frame carried no deadline"
    assert not [w for w in ws if "rerank" in w], ws


def test_the_scan_bundle_leg_keeps_bm25_order_and_says_why(monkeypatch, capsys):
    """`scan-prompt`'s leg goes through `context._rerank_bodied`. A skip there
    must not be swallowed — the hook's stderr is a log channel."""
    from refmatrix import context as ctx

    hits = [(1, 0.9), (2, 0.8), (3, 0.7)]

    class _S:
        def get_entity_by_id(self, eid):
            return type("E", (), {"kind": "memory"})()

    monkeypatch.setattr("refmatrix.embedder.extract_text_for_entity",
                        lambda s, eid, kind: "x" * 400)
    monkeypatch.setattr(rr, "collect_rerank_docs",
                        lambda store, h, **kw: ([(e, "x" * 400) for e, _ in h],
                                                [], []))
    client = _StubClient({"cost_s_per_doc": 5.0, "queue_depth": 3})
    reranker = rr.RemoteReranker(client, budget_s=1.0)

    out = ctx._rerank_bodied(_S(), reranker, "q", list(hits))
    assert out == hits, "a skipped rerank must leave retrieval order alone"
    assert client.calls == []
    assert "rerank skipped" in capsys.readouterr().err
